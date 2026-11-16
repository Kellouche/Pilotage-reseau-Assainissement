/**
 * Couches SIG « satellite » — SHP.md (P0)
 * Superposition cartographique bornée + sonde altimétrique + import piloté.
 * Aucune interaction avec le GPKG projet ni le moteur SWMM.
 */
(function () {
    'use strict';

    const AUX = {
        projectId: null,
        couches: {},          // layer_id -> {meta, groupe, visible, sondeActive}
        sondeLayerId: null,   // layer_id de la couche en mode sonde
        _moveendBind: false,
        _chargement: false
    };

    const TYPE_LIBELLES = {
        altimetrie_points: 'Altimétrie',
        bv_officiel: 'BV officiels',
        metrologie: 'Métrologie',
        autre: 'SIG'
    };
    const TYPE_COULEURS = {
        altimetrie_points: '#94a3b8',
        bv_officiel: '#34d399',
        metrologie: '#f472b6',
        autre: '#a78bfa'
    };

    // ------------------------------------------------------------------
    // Utilitaires
    // ------------------------------------------------------------------
    function authHeaders() {
        const h = { 'Accept': 'application/json' };
        const tk = localStorage.getItem('swmm_access_token');
        if (tk) h['Authorization'] = 'Bearer ' + tk;
        return h;
    }

    async function fetchJSON(url, opts) {
        const r = await fetch(url, Object.assign({ credentials: 'include', headers: authHeaders() }, opts || {}));
        if (!r.ok) {
            let detail = r.statusText;
            try { const j = await r.json(); detail = j.detail || detail; } catch (e) {}
            throw new Error(detail);
        }
        return r.json();
    }

    function carte() { return window.carte || window.map || null; }

    function boundsCourants() {
        const m = carte();
        if (!m) return null;
        const b = m.getBounds();
        return `${b.getWest()},${b.getSouth()},${b.getEast()},${b.getNorth()}`;
    }

    // ------------------------------------------------------------------
    // Style par type de couche
    // ------------------------------------------------------------------
    function styleFeature(couche, feature) {
        const couleur = TYPE_COULEURS[couche.type] || '#a78bfa';
        const t = (couche.geom_type || '').toLowerCase();
        if (t.includes('polygon') || t.includes('multipolygon')) {
            return { color: couleur, weight: 1.5, fillColor: couleur, fillOpacity: 0.12 };
        }
        return null; // points → pointToLayer
    }

    function pointToLayer(couche, feature, latlng) {
        const couleur = TYPE_COULEURS[couche.type] || '#a78bfa';
        const estTopo = couche.type === 'altimetrie_points';
        return L.circleMarker(latlng, {
            radius: estTopo ? 1.6 : 4,
            color: estTopo ? '#64748b' : couleur,
            weight: estTopo ? 0.5 : 1.5,
            fillColor: estTopo ? '#94a3b8' : couleur,
            fillOpacity: estTopo ? 0.55 : 0.9
        });
    }

    // ------------------------------------------------------------------
    // Chargement & affichage des couches
    // ------------------------------------------------------------------
    async function resoudreProjectId() {
        if (AUX.projectId) return AUX.projectId;
        const d = await fetchJSON('/api/v1/network/datasets?_t=' + Date.now());
        const ap = d && d.active_project;
        if (ap && ap.id) AUX.projectId = ap.id;
        return AUX.projectId;
    }

    async function chargerListeCouches() {
        const pid = await resoudreProjectId();
        if (!pid) { rendreListe([]); return; }
        try {
            const d = await fetchJSON(`/api/v1/projets/${encodeURIComponent(pid)}/aux-layers`);
            AUX.couches = {};
            (d.couches || []).forEach(c => {
                AUX.couches[c.id] = { meta: c, groupe: L.layerGroup(), visible: false, charge: false };
            });
            rendreListe(d.couches || []);
        } catch (e) {
            console.warn('[aux_layers] liste indisponible :', e.message);
            rendreListe([]);
        }
    }

    function rendreListe(couches) {
        const cont = document.getElementById('aux-layers-list');
        const vide = document.getElementById('aux-layers-vide');
        if (!cont) return;
        cont.innerHTML = '';
        if (!couches.length) {
            if (vide) vide.style.display = 'block';
            return;
        }
        if (vide) vide.style.display = 'none';
        couches.forEach(c => {
            const couleur = TYPE_COULEURS[c.type] || '#a78bfa';
            const lib = TYPE_LIBELLES[c.type] || 'SIG';
            const estTopo = c.type === 'altimetrie_points' && c.statut === 'ok';
            const div = document.createElement('div');
            div.className = 'layer-item';
            div.style.cssText = 'display:flex; align-items:center; gap:6px; flex-wrap:wrap;';
            div.innerHTML = `
                <input type="checkbox" id="aux-f-${c.id}" ${estTopo ? 'checked' : ''}>
                <span class="layer-indicator" style="background:${couleur}; border-radius:50%; width:9px; height:9px;"></span>
                <span style="font-size:0.75rem; color:#cbd5e1; flex:1; min-width:90px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${c.nom} — ${lib} — ${c.nb_features} entités">${c.nom}</span>
                <span style="font-size:0.62rem; color:#64748b;">${lib} · ${c.nb_features}</span>
                ${estTopo ? `<button type="button" class="aux-sonde-btn" data-id="${c.id}" title="Sonde altimétrique : activer puis cliquer sur la carte pour lire la cote terrain (recliquer pour désactiver)" style="background:rgba(148,163,184,0.15); border:1px solid rgba(148,163,184,0.35); color:#cbd5e1; border-radius:5px; padding:1px 6px; font-size:0.65rem; cursor:pointer;">⌖ sonde</button>
                <button type="button" class="aux-suspects-btn" data-id="${c.id}" title="File de revue P1 : conduites dont le sens d'écoulement est suspect au regard du terrain" style="background:rgba(245,158,11,0.15); border:1px solid rgba(245,158,11,0.4); color:#fbbf24; border-radius:5px; padding:1px 6px; font-size:0.65rem; cursor:pointer;">⇄ écoulement</button>` : ''}
            `;
            div.querySelector('input[type=checkbox]').addEventListener('change', (e) => {
                basculerCouche(c.id, e.target.checked);
            });
            const btnSonde = div.querySelector('.aux-sonde-btn');
            if (btnSonde) {
                btnSonde.addEventListener('click', () => activerSonde(c.id));
            }
            const btnSuspects = div.querySelector('.aux-suspects-btn');
            if (btnSuspects) {
                btnSuspects.addEventListener('click', () => ouvrirModalSuspects(c.id));
            }
            cont.appendChild(div);

            // Pré-activer les couches altimétriques OK
            if (estTopo) {
                basculerCouche(c.id, true);
            }
        });
    }

    async function chargerGeoJSON(couche) {
        // couche = entrée AUX.couches {meta, groupe, visible, seq}
        const meta = couche.meta || couche;
        const m = carte();
        if (!m) return;
        const zoom = m.getZoom();
        // Les couches à très fort volume (topo) ne sont chargées qu'à zoom suffisant
        const nf = meta.nb_features || 0;
        const zoomMin = nf > 50000 ? 16 : (nf > 20000 ? 15 : 0);
        if (zoom < zoomMin) {
            if (couche.groupe) couche.groupe.clearLayers();
            return;
        }
        const b = boundsCourants();
        const url = `/api/v1/projets/${encodeURIComponent(AUX.projectId)}/aux-layers/${meta.id}/geojson` +
            (b ? `?bounds=${b}` : '');
        try {
            const d = await fetchJSON(url);
            const seq = couche.seq = (couche.seq || 0) + 1;
            if (couche.groupe) couche.groupe.clearLayers();
            const gj = {
                type: 'FeatureCollection',
                features: d.features || []
            };
            L.geoJSON(gj, {
                style: (f) => styleFeature(meta, f),
                pointToLayer: (f, ll) => pointToLayer(meta, f, ll),
                onEachFeature: (f, l) => {
                    if (f.properties) {
                        const props = Object.entries(f.properties)
                            .slice(0, 12)
                            .map(([k, v]) => `${k}: ${v}`).join('<br>');
                        l.bindTooltip(props, { sticky: true, className: 'aux-tooltip' });
                    }
                }
            }).addTo(couche.groupe);
        } catch (e) {
            console.warn('[aux_layers] geojson', couche.id, e.message);
        }
    }

    function basculerCouche(layerId, on) {
        const c = AUX.couches[layerId];
        if (!c) return;
        const m = carte();
        if (!m) return;
        c.visible = on;
        if (on) {
            if (!m.hasLayer(c.groupe)) c.groupe.addTo(m);
            chargerGeoJSON(c);
        } else {
            m.removeLayer(c.groupe);
            desactiverSonde(layerId);
        }
    }

    function majCouchesVisibles() {
        Object.values(AUX.couches).forEach(c => {
            if (c.visible) chargerGeoJSON(c);
        });
    }

    // ------------------------------------------------------------------
    // Sonde altimétrique
    // ------------------------------------------------------------------
    function activerSonde(layerId) {
        const m = carte();
        if (!m) return;
        if (AUX.sondeLayerId === layerId) {
            desactiverSonde(layerId);
            return;
        }
        desactiverSonde();
        AUX.sondeLayerId = layerId;
        const c = AUX.couches[layerId];
        if (c) {
            c.sondeActive = true;
            const btn = document.querySelector(`.aux-sonde-btn[data-id="${layerId}"]`);
            if (btn) { btn.textContent = '⌖ sonde ON'; btn.style.background = 'rgba(56,189,248,0.3)'; }
        }
        m.getContainer().style.cursor = 'crosshair';
        m.on('click', onSondeClick);
        if (typeof window.dialogueNotifier === 'function') {
            window.dialogueNotifier({
                message: 'Sonde altimétrique active : cliquez sur la carte pour lire la cote terrain — recliquez sur ⌖ ou Échap pour quitter.',
                type: 'info'
            });
        }
    }

    function desactiverSonde(layerId) {
        const m = carte();
        if (AUX.sondeLayerId) {
            const c = AUX.couches[AUX.sondeLayerId];
            if (c) c.sondeActive = false;
            const btn = document.querySelector(`.aux-sonde-btn[data-id="${AUX.sondeLayerId}"]`);
            if (btn) { btn.textContent = '⌖ sonde'; btn.style.background = 'rgba(148,163,184,0.15)'; }
            if (m) m.off('click', onSondeClick);
        }
        AUX.sondeLayerId = null;
        if (m) m.getContainer().style.cursor = '';
    }
    window.desactiverSondeAux = desactiverSonde;

    async function onSondeClick(e) {
        const layerId = AUX.sondeLayerId;
        if (!layerId || !AUX.projectId) return;
        const { lat, lng } = e.latlng;
        try {
            const r = await fetchJSON(
                `/api/v1/projets/${encodeURIComponent(AUX.projectId)}/aux-layers/${layerId}/elevation?lng=${lng}&lat=${lat}`
            );
            const confCouleur = { haute: '#34d399', moyenne: '#fbbf24', faible: '#f87171', aucune: '#94a3b8' }[r.confiance] || '#94a3b8';
            const html = r.statut === 'ok'
                ? `<b>Cote terrain estimée : ${r.z_terrain_m} m</b><br>
                   <span style="color:${confCouleur};">Confiance : ${r.confiance}</span>
                   (${r.distance_point_topo_m} m du point topo le plus proche)<br>
                   <span style="font-size:0.72rem;color:#94a3b8;">${r.avertissement}</span>`
                : `<b>${r.message || 'Hors emprise'}</b><br>
                   <span style="font-size:0.72rem;color:#94a3b8;">Distance au point topo : ${r.distance_point_topo_m} m</span>`;
            L.popup({ closeButton: true })
                .setLatLng(e.latlng)
                .setContent(`<div style="font-size:0.8rem;line-height:1.5;color:#0f172a;">${html}</div>`)
                .openOn(carte());
        } catch (err) {
            L.popup().setLatLng(e.latlng).setContent(
                `<div style="font-size:0.8rem;color:#b91c1c;">Sonde indisponible : ${err.message}</div>`
            ).openOn(carte());
        }
        // La sonde reste active pour plusieurs mesures ; 2e clic sur ⌖ ou Échap pour quitter
    }

    // Échap désactive la sonde
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && AUX.sondeLayerId) desactiverSonde();
    });

    // ------------------------------------------------------------------
    // Import (modale)
    // ------------------------------------------------------------------
    window.ouvrirModalAuxLayer = function () {
        const m = document.getElementById('modal-aux-layer');
        if (!m) return;
        document.getElementById('aux-upload-statut').style.display = 'none';
        m.style.display = 'flex';
    };
    window.fermerModalAuxLayer = function () {
        const m = document.getElementById('modal-aux-layer');
        if (m) m.style.display = 'none';
    };
    window.auxMajChampZ = function () {
        const type = document.getElementById('aux-type').value;
        const wrap = document.getElementById('aux-champ-z');
        if (wrap) wrap.style.display = (type === 'altimetrie_points') ? 'block' : 'none';
    };

    window.envoyerCoucheAux = async function () {
        const fileEl = document.getElementById('aux-file');
        const statutEl = document.getElementById('aux-upload-statut');
        const btn = document.getElementById('btn-aux-upload');
        if (!fileEl || !fileEl.files || !fileEl.files.length) {
            statutEl.style.display = 'block';
            statutEl.style.background = 'rgba(248,113,113,0.12)';
            statutEl.style.color = '#fca5a5';
            statutEl.textContent = 'Sélectionnez un fichier (.shp + sidecars, .gpkg, .geojson ou .zip).';
            return;
        }
        const pid = await resoudreProjectId();
        if (!pid) {
            statutEl.style.display = 'block';
            statutEl.style.background = 'rgba(248,113,113,0.12)';
            statutEl.style.color = '#fca5a5';
            statutEl.textContent = 'Aucun projet actif : chargez d\'abord un réseau.';
            return;
        }

        const fd = new FormData();
        // Shapefile : tous les fichiers sélectionnés (shp + sidecars) sous 'files'
        Array.from(fileEl.files).forEach(f => fd.append('files', f));
        fd.append('type', document.getElementById('aux-type').value);
        const nom = document.getElementById('aux-nom').value.trim();
        if (nom) fd.append('nom', nom);
        const cz = document.getElementById('aux-colonne-z').value.trim();
        if (cz) fd.append('colonne_z', cz);

        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Import en cours…';
        statutEl.style.display = 'block';
        statutEl.style.background = 'rgba(56,189,248,0.12)';
        statutEl.style.color = '#7dd3fc';
        statutEl.textContent = 'Import et indexation en cours — les grosses couches (topo) peuvent prendre quelques instants…';

        try {
            // fetch brut : FormData → ne pas fixer Content-Type
            const r = await fetch(`/api/v1/projets/${encodeURIComponent(pid)}/aux-layers`, {
                method: 'POST',
                credentials: 'include',
                headers: authHeaders(),
                body: fd
            });
            const j = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(j.detail || r.statusText);

            const c = j.couche || {};
            statutEl.style.background = 'rgba(52,211,153,0.12)';
            statutEl.style.color = '#6ee7b7';
            statutEl.textContent = `Couche « ${c.nom} » importée : ${c.nb_features} entités` +
                (c.grille_altimetrie ? ` — grille IDW ${c.grille_altimetrie.resolution_m} m, ${c.grille_altimetrie.nb_points} points cotés.` : '') +
                (j.avertissement ? ` ⚠ ${j.avertissement}` : '');

            fileEl.value = '';
            document.getElementById('aux-nom').value = '';
            document.getElementById('aux-colonne-z').value = '';
            await chargerListeCouches();
        } catch (e) {
            statutEl.style.background = 'rgba(248,113,113,0.12)';
            statutEl.style.color = '#fca5a5';
            statutEl.textContent = 'Échec de l\'import : ' + e.message;
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-upload me-1"></i> Importer';
        }
    };

    // ------------------------------------------------------------------
    // File de revue P1 : suspects de sens d'écoulement (lecture seule)
    // ------------------------------------------------------------------
    const COULEURS_SEV = { fort: '#ef4444', moyen: '#f59e0b', faible: '#38bdf8' };
    const COULEURS_CONF = { haute: '#34d399', moyenne: '#fbbf24', faible: '#f87171', aucune: '#94a3b8' };

    function _suspectsFiltres() {
        return {
            sev: (document.getElementById('suspects-filtre-sev') || {}).value || '',
            conf: (document.getElementById('suspects-filtre-conf') || {}).value || '',
            txt: ((document.getElementById('suspects-filtre-texte') || {}).value || '').toLowerCase(),
        };
    }

    function _suspectsFiltresAppliquer(liste) {
        const f = _suspectsFiltres();
        return (liste || []).filter(s => {
            if (f.sev && s.severite !== f.sev) return false;
            if (f.conf && s.confiance !== f.conf) return false;
            if (f.txt && !(String(s.amont).includes(f.txt) || String(s.aval).includes(f.txt))) return false;
            return true;
        });
    }

    window.ouvrirModalSuspects = async function (layerId) {
        const m = document.getElementById('modal-suspects');
        if (!m || !AUX.projectId) return;
        AUX.suspectsLayerId = layerId;
        m.style.display = 'flex';
        const corps = document.getElementById('suspects-corps');
        const stats = document.getElementById('suspects-stats');
        if (corps) corps.innerHTML = '<div style="color:#94a3b8;font-size:0.85rem;">Analyse en cours…</div>';
        if (stats) stats.innerHTML = '<span style="color:#94a3b8;">Chargement…</span>';
        try {
            const d = await fetchJSON(
                `/api/v1/projets/${encodeURIComponent(AUX.projectId)}/aux-layers/${layerId}/suspects-ecoulement`
            );
            AUX.suspectsData = d;
            _rendreStatsSuspects(d);
            _rendreAvertSuspects(d);
            rendreTableSuspects();
        } catch (e) {
            if (corps) corps.innerHTML = `<div style="color:#f87171;font-size:0.85rem;">Analyse impossible : ${e.message}</div>`;
        }
    };

    window.fermerModalSuspects = function () {
        const m = document.getElementById('modal-suspects');
        if (m) m.style.display = 'none';
        _effacerSuspectsCarte();
    };

    function _rendreStatsSuspects(d) {
        const stats = document.getElementById('suspects-stats');
        const sous = document.getElementById('suspects-sous-titre');
        if (!stats) return;
        if (sous && d.layer_nom) sous.textContent = `${d.layer_nom} — analyse terrain IDW, file de revue`;
        if (d.statut !== 'ok') {
            stats.innerHTML = `<span style="color:#fbbf24;">${d.statut === 'perime' ? 'Artefact périmé — recalcul requis' : (d.raison || d.statut)}</span>`;
            return;
        }
        const ps = d.par_severite || {};
        stats.innerHTML = `
            <span><b style="color:#e2e8f0;">${d.nb_conduites_analysées}</b> <span style="color:#94a3b8;">conduites analysées</span></span>
            <span><b style="color:#f87171;">${ps.fort || 0}</b> <span style="color:#94a3b8;">forts</span></span>
            <span><b style="color:#fbbf24;">${ps.moyen || 0}</b> <span style="color:#94a3b8;">moyens</span></span>
            <span><b style="color:#7dd3fc;">${ps.faible || 0}</b> <span style="color:#94a3b8;">faibles</span></span>
            <span style="color:#64748b;">(suspects affichés : ${Math.min((d.suspects || []).length, 300)})</span>`;
    }

    function _rendreAvertSuspects(d) {
        const el = document.getElementById('suspects-avert');
        if (el && d.avertissement) el.textContent = d.avertissement;
    }

    window.rendreTableSuspects = function () {
        const corps = document.getElementById('suspects-corps');
        if (!corps) return;
        const d = AUX.suspectsData;
        if (!d || d.statut !== 'ok') return;
        const liste = _suspectsFiltresAppliquer(d.suspects || []);
        const MAX = 150;
        const shown = liste.slice(0, MAX);
        if (!shown.length) {
            corps.innerHTML = '<div style="color:#94a3b8;font-size:0.85rem;padding:12px 0;">Aucun suspect pour ces filtres.</div>';
            return;
        }
        let html = `<table style="width:100%; border-collapse:collapse; font-size:0.74rem;">
            <thead><tr style="color:#64748b; text-align:left; border-bottom:1px solid rgba(255,255,255,0.1);">
                <th style="padding:5px 6px;">Sévérité</th><th style="padding:5px 6px;">Conduite</th>
                <th style="padding:5px 6px; text-align:right;">Long.</th>
                <th style="padding:5px 6px; text-align:right;">Δ terrain</th>
                <th style="padding:5px 6px; text-align:right;">Pente contr.</th>
                <th style="padding:5px 6px; text-align:right;">Δ radier</th>
                <th style="padding:5px 6px;">Confiance</th><th style="padding:5px 6px;">Motifs</th>
                <th style="padding:5px 6px;"></th>
            </tr></thead><tbody>`;
        shown.forEach((s, i) => {
            const cc = COULEURS_CONF[s.confiance] || '#94a3b8';
            const sc = COULEURS_SEV[s.severite] || '#94a3b8';
            html += `<tr style="border-bottom:1px solid rgba(255,255,255,0.05); cursor:pointer;" 
                onmouseover="this.style.background='rgba(56,189,248,0.06)'" onmouseout="this.style.background='transparent'"
                onclick="centrerSuspect(${i})">
                <td style="padding:5px 6px;"><span style="color:${sc}; font-weight:700;">●</span> ${s.severite}</td>
                <td style="padding:5px 6px; font-family:monospace;">${s.amont} → ${s.aval}</td>
                <td style="padding:5px 6px; text-align:right;">${s.longueur_m} m</td>
                <td style="padding:5px 6px; text-align:right; color:#f87171;">+${s.ecart_terrain_m} m</td>
                <td style="padding:5px 6px; text-align:right;">${s.pente_contre_pct} %</td>
                <td style="padding:5px 6px; text-align:right;">${s.ecart_radier_m != null ? '+' + s.ecart_radier_m + ' m' : '—'}</td>
                <td style="padding:5px 6px;"><span style="color:${cc};">${s.confiance}</span></td>
                <td style="padding:5px 6px; color:#94a3b8; max-width:340px;">${(s.motifs || []).join(' ; ')}</td>
                <td style="padding:5px 6px;"><button onclick="event.stopPropagation(); centrerSuspect(${i})" style="background:transparent;border:1px solid rgba(56,189,248,0.4);color:#7dd3fc;border-radius:5px;padding:1px 8px;font-size:0.68rem;cursor:pointer;">⌖</button></td>
            </tr>`;
        });
        html += `</tbody></table>`;
        if (liste.length > MAX) {
            html += `<div style="color:#64748b;font-size:0.72rem;padding:8px 0;">… et ${liste.length - MAX} autres (affinez les filtres ou zoomez sur la carte).</div>`;
        }
        corps.innerHTML = html;
        AUX._suspectsFiltresCourants = liste;
    };

    window.centrerSuspect = function (idx) {
        const liste = AUX._suspectsFiltresCourants || [];
        const s = liste[idx];
        const m = carte();
        if (!s || !m) return;
        // Milieu approximatif entre amont et aval
        const lat = (s.lat_amont != null && s.lat_aval != null)
            ? (s.lat_amont + s.lat_aval) / 2 : s.lat_amont;
        const lng = (s.lng_amont != null && s.lng_aval != null)
            ? (s.lng_amont + s.lng_aval) / 2 : s.lng_amont;
        if (lat == null || lng == null) return;
        m.setView([lat, lng], 17);
        L.popup({ closeButton: true })
            .setLatLng([lat, lng])
            .setContent(`<div style="font-size:0.8rem;line-height:1.5;">
                <b>Suspect ${s.severite}</b> — ${s.amont} → ${s.aval}<br>
                Terrain : ${s.z_terrain_amont} → ${s.z_terrain_aval} m<br>
                Δ = +${s.ecart_terrain_m} m (${s.pente_contre_pct} %)<br>
                <span style="color:#64748b;">${(s.motifs || []).join(' ; ')}</span><br>
                <span style="color:#b45309;">File de revue — aucune correction auto.</span>
            </div>`).openOn(m);
    };

    window.afficherSuspectsCarte = function () {
        const m = carte();
        if (!m) return;
        _effacerSuspectsCarte();
        const liste = _suspectsFiltresAppliquer(AUX.suspectsData && AUX.suspectsData.suspects || []);
        const CAP = 500;
        AUX._suspectsGroupe = L.layerGroup();
        liste.slice(0, CAP).forEach(s => {
            const lat = (s.lat_amont != null && s.lat_aval != null) ? (s.lat_amont + s.lat_aval) / 2 : s.lat_amont;
            const lng = (s.lng_amont != null && s.lng_aval != null) ? (s.lng_amont + s.lng_aval) / 2 : s.lng_amont;
            if (lat == null || lng == null) return;
            const col = COULEURS_SEV[s.severite] || '#94a3b8';
            L.circleMarker([lat, lng], {
                radius: s.severite === 'fort' ? 7 : 5,
                color: '#0f172a', weight: 1,
                fillColor: col, fillOpacity: 0.75,
            }).bindTooltip(`${s.severite.toUpperCase()} — ${s.amont} → ${s.aval}<br>Δ terrain +${s.ecart_terrain_m} m`,
                { sticky: true })
              .addTo(AUX._suspectsGroupe);
        });
        AUX._suspectsGroupe.addTo(m);
        if (typeof window.dialogueNotifier === 'function') {
            window.dialogueNotifier({
                message: `${Math.min(liste.length, CAP)} suspects affichés sur la carte (filtrés).`,
                type: 'info'
            });
        }
    };

    function _effacerSuspectsCarte() {
        const m = carte();
        if (m && AUX._suspectsGroupe) {
            m.removeLayer(AUX._suspectsGroupe);
            AUX._suspectsGroupe = null;
        }
    }

    // ------------------------------------------------------------------
    // Initialisation
    // ------------------------------------------------------------------
    function initialiser() {
        window.auxMajChampZ && window.auxMajChampZ();
        chargerListeCouches();
        const m = carte();
        if (m && !AUX._moveendBind) {
            AUX._moveendBind = true;
            let t = null;
            m.on('moveend', () => {
                clearTimeout(t);
                t = setTimeout(majCouchesVisibles, 400);
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialiser);
    } else {
        initialiser();
    }
    // Le projet peut se charger après le DOM : on retente la résolution du projectId
    setTimeout(() => { if (!AUX.projectId) chargerListeCouches(); }, 8000);

    window.AUX_LAYERS = AUX;
})();
