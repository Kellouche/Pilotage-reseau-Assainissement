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
        _chargement: false,
        nomsImportes: new Set(),  // basenames (sans ext.) des fichiers déjà importés
        _listeChargee: false,
        _prefs: {}               // layer_id -> bool : choix utilisateur persistant
    };

    // Palette + motifs de traits : chaque couche satellite reçoit un style
    // distinct et STABLE (dérivé du layer_id) — teinte et pointillé se
    // distinguent d'une couche à l'autre sans collision avec le réseau.
    const PALETTE_AUX = ['#38bdf8', '#34d399', '#fbbf24', '#f87171', '#a78bfa',
        '#f472b6', '#22d3ee', '#a3e635', '#fb923c', '#e879f9', '#facc15', '#4ade80'];
    const DASH_AUX = [null, '7,4', '2,4', '10,4,2,4', '4,2', '12,4,3,4', '1,4'];

    function _hashStr(s) {
        let h = 2166136261;
        const str = String(s || '');
        for (let i = 0; i < str.length; i++) {
            h ^= str.charCodeAt(i);
            h = Math.imul(h, 16777619);
        }
        return h >>> 0;
    }

    /** Style stable par couche : couleur + pointillé dérivés du layer_id. */
    function _styleCouche(meta) {
        if (meta._styleAux) return meta._styleAux;
        const h = _hashStr(meta.id || meta.nom || '');
        meta._styleAux = {
            couleur: PALETTE_AUX[h % PALETTE_AUX.length],
            dash: DASH_AUX[(h >>> 8) % DASH_AUX.length],
            poids: 1.4 + ((h >>> 16) % 3) * 0.5
        };
        return meta._styleAux;
    }

    /** Basename normalisé (minuscules, sans extension) pour comparer fichiers. */
    function _baseSansExt(nom) {
        const n = String(nom || '');
        const i = n.lastIndexOf('.');
        return (i >= 0 ? n.slice(0, i) : n).toLowerCase();
    }

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
        const st = _styleCouche(couche);
        const t = (couche.geom_type || '').toLowerCase();
        if (t.includes('polygon') || t.includes('multipolygon')) {
            return {
                color: st.couleur, weight: st.poids, dashArray: st.dash || null,
                fillColor: st.couleur, fillOpacity: 0.10
            };
        }
        // Lignes / autres géométries vectorielles
        return {
            color: st.couleur, weight: st.poids, dashArray: st.dash || null, opacity: 0.9
        };
    }

    function pointToLayer(couche, feature, latlng) {
        const st = _styleCouche(couche);
        const estTopo = couche.type === 'altimetrie_points';
        return L.circleMarker(latlng, {
            radius: estTopo ? 1.6 : 4,
            color: estTopo ? '#64748b' : st.couleur,
            weight: estTopo ? 0.5 : 1.5,
            fillColor: estTopo ? '#94a3b8' : st.couleur,
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
            var _urlAux = `/api/v1/projets/${encodeURIComponent(pid)}/aux-layers`;
            if (typeof window._urlAvecSnapshot === 'function') _urlAux = window._urlAvecSnapshot(_urlAux);
            const d = await fetchJSON(_urlAux);
            AUX.couches = {};
            AUX.nomsImportes = new Set();
            (d.couches || []).forEach(c => {
                AUX.couches[c.id] = { meta: c, groupe: L.layerGroup(), visible: false, charge: false };
                // Basename du fichier source → exclusion de la liste d'import
                if (c.fichier_source) AUX.nomsImportes.add(_baseSansExt(c.fichier_source));
            });
            AUX._listeChargee = true;
            rendreListe(d.couches || []);
        } catch (e) {
            console.warn('[aux_layers] liste indisponible :', e.message);
            rendreListe([]);
        }
    }

    function _lirePrefCouche(layerId) {
        try {
            const val = localStorage.getItem('drainpilot_aux_pref_' + layerId);
            if (val !== null) return val === 'true';
        } catch (_) {}
        if (AUX._prefs[layerId] !== undefined) return AUX._prefs[layerId];
        // Règle d'or : aucune couche satellite lourde ne démarre cochée automatiquement.
        // L'activation est un choix explicite et volontaire de l'utilisateur.
        return false;
    }

    function _sauverPrefCouche(layerId, checked) {
        AUX._prefs[layerId] = !!checked;
        try {
            localStorage.setItem('drainpilot_aux_pref_' + layerId, checked ? 'true' : 'false');
        } catch (_) {}
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
            const st = _styleCouche(c);
            const couleur = (c.type === 'altimetrie_points') ? TYPE_COULEURS[c.type] : st.couleur;
            const lib = TYPE_LIBELLES[c.type] || 'SIG';
            const estTopo = c.type === 'altimetrie_points' && c.statut === 'ok';
            // Choix utilisateur persistant dans localStorage (décoché par défaut)
            const cocheInitial = _lirePrefCouche(c.id);
            const div = document.createElement('div');
            div.className = 'layer-item';
            div.style.cssText = 'display:flex; align-items:center; gap:6px; flex-wrap:wrap;';
            div.innerHTML = `
                <input type="checkbox" id="aux-f-${c.id}" ${cocheInitial ? 'checked' : ''}>
                <span class="layer-indicator" style="background:${couleur}; border-radius:50%; width:9px; height:9px;"></span>
                <span style="font-size:0.75rem; color:#cbd5e1; flex:1; min-width:90px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${c.nom} — ${lib} — ${c.nb_features} entités">${c.nom}</span>
                <span style="font-size:0.62rem; color:#64748b;">${c.nb_features} objets</span>
                ${estTopo ? `<button type="button" class="aux-sonde-btn" data-id="${c.id}" title="Sonde altimétrique : activer puis cliquer sur la carte pour lire la cote terrain (recliquer pour désactiver)" style="background:rgba(148,163,184,0.15); border:1px solid rgba(148,163,184,0.35); color:#cbd5e1; border-radius:5px; padding:1px 6px; font-size:0.65rem; cursor:pointer;">⌖ sonde</button>
                <button type="button" class="aux-suspects-btn" data-id="${c.id}" title="File de revue P1 : conduites dont le sens d'écoulement est suspect au regard du terrain" style="background:rgba(245,158,11,0.15); border:1px solid rgba(245,158,11,0.4); color:#fbbf24; border-radius:5px; padding:1px 6px; font-size:0.65rem; cursor:pointer;">⇄ écoulement</button>` : ''}
                <button type="button" class="aux-del-btn" data-id="${c.id}" title="Supprimer définitivement cette couche satellite" style="background:rgba(248,113,113,0.12); border:1px solid rgba(248,113,113,0.35); color:#fca5a5; border-radius:5px; padding:1px 6px; font-size:0.65rem; cursor:pointer; flex:none;">🗑</button>
            `;
            div.querySelector('input[type=checkbox]').addEventListener('change', (e) => {
                _sauverPrefCouche(c.id, e.target.checked);
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
            const btnDel = div.querySelector('.aux-del-btn');
            if (btnDel) {
                btnDel.addEventListener('click', () => supprimerCouche(c.id));
            }
            cont.appendChild(div);

            // Activer les couches cochées : altimétrie « ok » par défaut,
            // sauf si l'utilisateur les a explicitement désactivées.
            if (cocheInitial) {
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
        var url = `/api/v1/projets/${encodeURIComponent(AUX.projectId)}/aux-layers/${meta.id}/geojson` +
            (b ? `?bounds=${b}` : '');
        if (typeof window._urlAvecSnapshot === 'function') url = window._urlAvecSnapshot(url);
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
    // Suppression d'une couche satellite (backend DELETE + purge locale)
    // ------------------------------------------------------------------
    async function supprimerCouche(layerId) {
        const c = AUX.couches[layerId];
        const nom = (c && c.meta && c.meta.nom) || layerId;
        if (!confirm(`Supprimer définitivement la couche « ${nom} » ?\n\nCette action retire la couche de la carte et efface ses données stockées.`)) return;
        const m = carte();
        try {
            await fetchJSON(
                `/api/v1/projets/${encodeURIComponent(AUX.projectId)}/aux-layers/${layerId}`,
                { method: 'DELETE' }
            );
        } catch (e) {
            if (typeof window.dialogueNotifier === 'function') {
                window.dialogueNotifier({ message: 'Suppression impossible : ' + e.message, type: 'error' });
            } else {
                alert('Suppression impossible : ' + e.message);
            }
            return;
        }
        // Nettoyage local : sonde, couche carte, registre — puis rechargement
        // de la liste depuis le serveur (source à réimporter redeviendra
        // proposée dans la liste d'import).
        desactiverSonde(layerId);
        if (m && c && c.groupe) {
            try { m.removeLayer(c.groupe); } catch (_) {}
        }
        delete AUX.couches[layerId];
        await chargerListeCouches();
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
            var _urlElev = `/api/v1/projets/${encodeURIComponent(AUX.projectId)}/aux-layers/${layerId}/elevation?lng=${lng}&lat=${lat}`;
            if (typeof window._urlAvecSnapshot === 'function') _urlElev = window._urlAvecSnapshot(_urlElev);
            const r = await fetchJSON(_urlElev);
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
    // ── État interne du scan dossier ────────────────────────────────────────
    // _auxDossierIndex : basename -> { shp, sidecars, autres }
    // _auxEntrees      : éléments affichables { cle, genre, ok, deja, entry, fichier }
    // _auxSelectionnes : Set des « cle » cochées (multisélection)
    let _auxDossierIndex = {};
    let _auxEntrees = [];
    let _auxSelectionnes = new Set();
    let nomDossierGlobal = '(dossier)';

    window.ouvrirModalAuxLayer = function () {
        const m = document.getElementById('modal-aux-layer');
        if (!m) return;
        // Réinitialisation complète à chaque ouverture
        _auxDossierIndex = {};
        _auxEntrees = [];
        _auxSelectionnes = new Set();
        const statut = document.getElementById('aux-upload-statut');
        if (statut) statut.style.display = 'none';
        const liste = document.getElementById('aux-shp-liste');
        if (liste) liste.style.display = 'none';
        const opts = document.getElementById('aux-options-bloc');
        if (opts) opts.style.display = 'none';
        const btn = document.getElementById('btn-aux-upload');
        if (btn) { btn.disabled = true; btn.style.opacity = '0.4'; btn.style.cursor = 'not-allowed'; }
        const lbl = document.getElementById('aux-folder-label');
        if (lbl) lbl.textContent = 'Cliquez ici pour choisir un dossier…';
        const fileEl = document.getElementById('aux-file');
        if (fileEl) fileEl.value = '';
        m.style.display = 'flex';
    };

    window.fermerModalAuxLayer = function () {
        const m = document.getElementById('modal-aux-layer');
        if (m) m.style.display = 'none';
    };

    window.auxMajChampZ = function () {
        const type = document.getElementById('aux-type');
        const wrap = document.getElementById('aux-champ-z');
        if (wrap && type) wrap.style.display = (type.value === 'altimetrie_points') ? 'block' : 'none';
    };

    /** Active/désactive les options et le bouton Importer selon la sélection. */
    function _majEtatSelectionAux() {
        const opts = document.getElementById('aux-options-bloc');
        const btn  = document.getElementById('btn-aux-upload');
        const n = _auxSelectionnes.size;
        if (opts) {
            opts.style.display = n ? 'block' : 'none';
            if (n) window.auxMajChampZ();
        }
        if (btn) {
            const act = n > 0;
            btn.disabled = !act;
            btn.style.opacity = act ? '1' : '0.4';
            btn.style.cursor = act ? 'pointer' : 'not-allowed';
        }
    }

    /**
     * Rend la liste des fichiers cochables : exclut les fichiers déjà
     * importés (basename présent côté serveur), affiche un compteur de
     * masquage, et câble les cases à cocher (multisélection).
     */
    function _rendreItemsAux() {
        const itemsEl = document.getElementById('aux-shp-items');
        const listeEl = document.getElementById('aux-shp-liste');
        if (!itemsEl) return;
        // Purger la sélection des entrées devenues invalides
        _auxEntrees.forEach(e => { if (e.deja || !e.ok) _auxSelectionnes.delete(e.cle); });
        const dispo = _auxEntrees.filter(e => !e.deja);
        const nbMasques = _auxEntrees.length - dispo.length;

        itemsEl.innerHTML = '';
        if (!dispo.length) {
            itemsEl.innerHTML = '<div style="color:#94a3b8;font-size:0.8rem;padding:8px;">' +
                (nbMasques
                    ? `Toutes les couches SIG reconnues de ce dossier sont déjà importées (${nbMasques} masquée${nbMasques > 1 ? 's' : ''}).`
                    : 'Aucune couche SIG reconnue dans ce dossier.') +
                '</div>';
        } else {
            dispo.forEach(e => {
                const label = document.createElement('label');
                label.style.cssText = 'display:flex;align-items:center;gap:10px;padding:8px 10px;cursor:pointer;border-radius:6px;transition:background .15s;';
                label.onmouseover = () => { label.style.background = 'rgba(56,189,248,0.07)'; };
                label.onmouseout = () => { label.style.background = 'transparent'; };

                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.checked = _auxSelectionnes.has(e.cle);
                cb.disabled = !e.ok;
                cb.title = e.ok ? '' : 'Sidecars requis manquants (.shx/.dbf)';
                cb.style.cssText = 'accent-color:#0ea5e9;width:16px;height:16px;cursor:pointer;flex-shrink:0;';
                cb.addEventListener('change', () => {
                    if (cb.checked) _auxSelectionnes.add(e.cle); else _auxSelectionnes.delete(e.cle);
                    _majEtatSelectionAux();
                });

                const info = document.createElement('div');
                info.style.cssText = 'flex:1;min-width:0;';
                const nomDiv = document.createElement('div');
                nomDiv.style.cssText = 'font-size:0.82rem;font-weight:600;color:#f1f5f9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
                nomDiv.textContent = e.nom;
                const metaDiv = document.createElement('div');
                metaDiv.style.cssText = 'font-size:0.68rem;color:#64748b;';
                const badge = document.createElement('span');
                badge.style.color = e.ok ? '#34d399' : '#f59e0b';
                badge.textContent = e.ok
                    ? (e.genre === 'direct' ? `✔ ${String(e.ext || '').toUpperCase()}` : `✔ ${e.nbSidecars} sidecar(s)`)
                    : '⚠ sidecars manquants';
                metaDiv.append(`${(e.taille / 1024).toFixed(1)} Ko  ·  `, badge);
                info.appendChild(nomDiv);
                info.appendChild(metaDiv);

                label.appendChild(cb);
                label.appendChild(info);
                itemsEl.appendChild(label);
            });

            if (nbMasques) {
                const note = document.createElement('div');
                note.style.cssText = 'font-size:0.7rem;color:#64748b;padding:6px 8px 2px;';
                note.textContent = `— ${nbMasques} couche${nbMasques > 1 ? 's' : ''} déjà importée${nbMasques > 1 ? 's' : ''} masquée${nbMasques > 1 ? 's' : ''} —`;
                itemsEl.appendChild(note);
            }
        }

        // Auto-coche si une seule couche importable
        const importables = dispo.filter(e => e.ok);
        if (importables.length === 1 && !_auxSelectionnes.size) {
            _auxSelectionnes.add(importables[0].cle);
            const cb = itemsEl.querySelector('input[type=checkbox]:not(:disabled)');
            if (cb) cb.checked = true;
        }

        if (listeEl) listeEl.style.display = 'block';
        _majEtatSelectionAux();

        // Libellé dossier : nombre de couches détectées (pas de fichiers —
        // un .shp + ses sidecars compte pour une seule couche).
        const lblDos = document.getElementById('aux-folder-label');
        if (lblDos && _auxEntrees.length) {
            lblDos.textContent = `📂 ${nomDossierGlobal}  — ${_auxEntrees.length} couche${_auxEntrees.length > 1 ? 's' : ''} détectée${_auxEntrees.length > 1 ? 's' : ''}`;
        }
    }

    // Pont inter-fichiers : les fonctions du module d'import/suspects
    // (aux_layers_import.js) partagent cet etat et ces helpers.
    window._auxInt = {
        AUX: AUX, _hashStr: _hashStr, _styleCouche: _styleCouche,
        _baseSansExt: _baseSansExt, authHeaders: authHeaders, fetchJSON: fetchJSON,
        carte: carte, boundsCourants: boundsCourants, styleFeature: styleFeature,
        pointToLayer: pointToLayer, resoudreProjectId: resoudreProjectId,
        chargerListeCouches: chargerListeCouches, _lirePrefCouche: _lirePrefCouche,
        _sauverPrefCouche: _sauverPrefCouche, rendreListe: rendreListe,
        chargerGeoJSON: chargerGeoJSON, basculerCouche: basculerCouche,
        majCouchesVisibles: majCouchesVisibles, supprimerCouche: supprimerCouche,
        activerSonde: activerSonde, desactiverSonde: desactiverSonde,
        onSondeClick: onSondeClick, _majEtatSelectionAux: _majEtatSelectionAux,
        _rendreItemsAux: _rendreItemsAux, TYPE_LIBELLES: TYPE_LIBELLES,
        PALETTE_AUX: PALETTE_AUX, DASH_AUX: DASH_AUX
    };
})();
