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
                ${estTopo ? `<button type="button" class="aux-sonde-btn" data-id="${c.id}" title="Sonde altimétrique : activer puis cliquer sur la carte pour lire la cote terrain (recliquer pour désactiver)" style="background:rgba(148,163,184,0.15); border:1px solid rgba(148,163,184,0.35); color:#cbd5e1; border-radius:5px; padding:1px 6px; font-size:0.65rem; cursor:pointer;">⌖ sonde</button>` : ''}
            `;
            div.querySelector('input[type=checkbox]').addEventListener('change', (e) => {
                basculerCouche(c.id, e.target.checked);
            });
            const btnSonde = div.querySelector('.aux-sonde-btn');
            if (btnSonde) {
                btnSonde.addEventListener('click', () => activerSonde(c.id));
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
