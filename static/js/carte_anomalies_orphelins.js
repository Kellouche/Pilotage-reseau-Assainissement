/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-27
 * Date de modification : 2026-11-27
 * Objet : Zoom anomalie, fusion orphelins et localision/pulse sur carte (extrait de static/js/carte_anomalies.js)
 * ================================================================================
 */

function zoomToAnomalie(valueStr) {
    if (!valueStr) return;

    // value can be "id|lat,lng" or "lat,lng" or just an id
    let targetId = null;
    let lat = null, lng = null;

    if (valueStr.includes('|')) {
        const parts = valueStr.split('|');
        targetId = parts[0];
        const coords = parts[1].split(',').map(Number);
        if (coords.length === 2) { lat = coords[0]; lng = coords[1]; }
    } else if (valueStr.includes(',')) {
        const coords = valueStr.split(',').map(Number);
        if (coords.length === 2) { lat = coords[0]; lng = coords[1]; }
    } else {
        targetId = valueStr;
    }

    if (lat !== null && lng !== null) {
        map.setView([lat, lng], 18);
    }

    // Nettoyer ancien highlight
    if (currentGeometryHighlight && map.hasLayer(currentGeometryHighlight)) {
        map.removeLayer(currentGeometryHighlight);
        currentGeometryHighlight = null;
    }

    // Si on a un ID, tenter de trouver la géométrie et la surligner
    let foundLayer = null;
    if (targetId && typeof findLayerById === 'function') {
        // try exact find
        foundLayer = findLayerById(conduitesLayer, targetId) || findLayerById(regardsLayer, targetId);
        // fallback: try numeric comparisons or property-based match
        if (!foundLayer && conduitesLayer && conduitesLayer.eachLayer) {
            conduitesLayer.eachLayer(l => {
                try {
                    const p = l.feature && l.feature.properties || {};
                    const candidates = [p.fid, p.FID, p.id, p.ID, p.ID_AMONT, p.ID_AVAL, p.CODE, p.code, l.feature && l.feature.id];
                    for (let c of candidates) {
                        if (c !== undefined && c !== null && c.toString() === targetId.toString()) { foundLayer = l; break; }
                    }
                } catch (e) { }
            });
        }

        if (foundLayer) {
            if (foundLayer.getLatLngs) {
                currentGeometryHighlight = L.polyline(foundLayer.getLatLngs(), { color: '#ff0000', weight: 12, opacity: 0.8, dashArray: '10,15' }).addTo(map);
            } else if (foundLayer.getLatLng) {
                currentGeometryHighlight = L.circleMarker(foundLayer.getLatLng(), { radius: 20, color: '#ff0000', weight: 5, opacity: 0.9, fillColor: 'transparent' }).addTo(map);
            }
        }

        // Toujours tenter d'ouvrir la modal de correction (fallback si aucune géométrie trouvée)
        try {
            setTimeout(() => {
                if (typeof openCorrectionModal === 'function') {
                    // Récupérer le type d'anomalie depuis l'option sélectionnée
                    const sel = document.getElementById(`select-anomalies-${currentTab}`);
                    const optSelected = sel?.options?.[sel.selectedIndex];
                    const anomType = optSelected?.dataset?.anomalieType || 'conduite';
                    openCorrectionModal(targetId, anomType);
                }
            }, 250);
        } catch (e) { console.warn('openCorrectionModal failed', e); }
    } else if (targetId) {
        // if we only have an id and not found, still try open modal
        try { setTimeout(() => { if (typeof openCorrectionModal === 'function') openCorrectionModal(targetId, 'conduite'); }, 250); } catch (e) { }
    }

    // Attendre un peu que le zoom se termine pour ouvrir le popup si un marqueur ponctuel existe
    setTimeout(() => {
        let popupOpened = false;
        if (lat !== null && lng !== null) {
            Object.values(anomaliesLayers).forEach(layer => {
                if (typeof layer.eachLayer === 'function') {
                    layer.eachLayer(marker => {
                        if (typeof marker.getLatLng === 'function') {
                            const ll = marker.getLatLng();
                            if (Math.abs(ll.lat - lat) < 0.0001 && Math.abs(ll.lng - lng) < 0.0001) {
                                marker.openPopup();
                                popupOpened = true;
                            }
                        }
                    });
                }
            });
        }

        // Si pas de popup mais surlignage existant, ouvrir une bulle temporaire
        if (!popupOpened && currentGeometryHighlight) {
            try { currentGeometryHighlight.bindPopup(`<b>Objet ciblé : ${targetId || 'Inconnu'}</b>`).openPopup(); } catch (e) { }
        }
    }, 500);
}

// ============================================================================
// Éléments orphelins (regards/nœuds isolés + tronçons hors graphe ou sans
// exutoire) — endpoint GET /api/v1/network/orphelins, listing cliquable.
// ============================================================================

// Fusionne la réponse /network/orphelins dans le rapport qualité : les
// éléments orphelins deviennent des catégories d'anomalies natives
// (marqueurs, compteurs, listes déroulantes et onglet dédiés).
function fusionnerOrphelins(anomData, orphelins) {
    if (!anomData || !orphelins) return;
    if (!anomData.anomalies || typeof anomData.anomalies !== 'object') {
        anomData.anomalies = {};
    }
    const anomalies = anomData.anomalies;

    anomalies.orphelins_regards = (orphelins.noeuds_orphelins || []).map(n => {
        const typeLbl = (n.type_noeud || 'noeud').toLowerCase();
        const details = [n.nom, n.nom_voie, n.commune].filter(v => v && String(v).trim() && String(v).trim().toLowerCase() !== 'nan');
        return {
            type: 'regard_orphelin',
            severite: 'majeure',
            id_regard: n.id,
            code: n.id,
            latitude: n.lat,
            longitude: n.lng,
            description: `Nœud ${typeLbl} « ${n.id} » isolé : aucune conduite amont ni aval ne s'y rattache${details.length ? ' — ' + details.join(' · ') : ''}`,
            _orphelin: {
                genre: 'regard',
                id: n.id,
                type_noeud: n.type_noeud,
                nom: n.nom,
                nom_voie: n.nom_voie,
                commune: n.commune,
                lat: n.lat,
                lng: n.lng
            }
        };
    });

    anomalies.orphelins_troncons = (orphelins.troncons_orphelins || []).map(t => {
        const libelle = (t.amont && t.aval) ? `${t.amont} → ${t.aval}` : (t.id || 'tronçon');
        const horsGraphe = t.motif === 'hors_graphe';
        return {
            type: 'troncon_orphelin',
            severite: horsGraphe ? 'majeure' : 'mineure',
            id_conduite: t.id,
            fid: t.id,
            id_amont: t.amont,
            id_aval: t.aval,
            latitude: t.lat,
            longitude: t.lng,
            description: `${t.detail || 'Tronçon orphelin'}${t.type_conduite ? ' · ' + t.type_conduite : ''}${t.longueur_m ? ' · ' + Math.round(t.longueur_m) + ' m' : ''}`,
            _orphelin: {
                genre: 'troncon',
                id: t.id,
                libelle: libelle,
                amont: t.amont,
                aval: t.aval,
                motif: t.motif,
                detail: t.detail,
                type_conduite: t.type_conduite,
                longueur_m: t.longueur_m,
                diametre_mm: t.diametre_mm,
                lat: t.lat,
                lng: t.lng
            }
        };
    });
}

// ---------------------------------------------------------------------------
// Listing cliquable des orphelins
// ---------------------------------------------------------------------------
let _orphelinsItems = [];

function _escHtml(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function _texteRechercheOrphelin(it) {
    const o = it._orphelin || {};
    return [
        o.id, o.libelle, o.amont, o.aval, o.type_noeud, o.nom, o.nom_voie,
        o.commune, o.type_conduite, o.detail
    ].filter(Boolean).join(' ').toLowerCase();
}

function rendreListeOrphelins() {
    const listEl = document.getElementById('orphelins-list');
    const searchWrap = document.getElementById('orphelins-search-container');
    const statsEl = document.getElementById('stats-orphelins');
    if (!listEl) return;

    _orphelinsItems = [];
    const regards = anomaliesData && anomaliesData.orphelins_regards ? anomaliesData.orphelins_regards : [];
    const troncons = anomaliesData && anomaliesData.orphelins_troncons ? anomaliesData.orphelins_troncons : [];

    regards.forEach(a => _orphelinsItems.push(a));
    troncons.forEach(a => _orphelinsItems.push(a));

    const nR = regards.length, nT = troncons.length;
    if (statsEl) {
        statsEl.innerHTML = `
            <div class="diagnostic-stats">
                <div><strong>Total:</strong> ${nR + nT} éléments orphelins</div>
                <div style="color:#e74c3c;"><strong>Nœuds isolés:</strong> ${nR}</div>
                <div style="color:#3498db;"><strong>Tronçons:</strong> ${nT}</div>
            </div>`;
    }

    if (!_orphelinsItems.length) {
        listEl.style.display = 'block';
        listEl.innerHTML = '<div class="orphelins-empty">Aucun élément orphelin détecté — le réseau est entièrement connecté.</div>';
        if (searchWrap) searchWrap.style.display = 'none';
        return;
    }

    if (searchWrap) searchWrap.style.display = 'block';
    const q = (document.getElementById('orphelins-search') || {}).value || '';
    filtrerListeOrphelins(q);
}

function filtrerListeOrphelins(val) {
    const listEl = document.getElementById('orphelins-list');
    if (!listEl) return;
    const q = (typeof val === 'string' ? val : ((document.getElementById('orphelins-search') || {}).value || '')).trim().toLowerCase();

    const visibles = _orphelinsItems.filter(it => !q || _texteRechercheOrphelin(it).includes(q));
    if (!visibles.length) {
        listEl.innerHTML = '<div class="orphelins-empty">Aucun résultat pour ce filtre.</div>';
        return;
    }

    listEl.innerHTML = visibles.map(a => {
        const o = a._orphelin || {};
        const estRegard = o.genre === 'regard';
        const cls = estRegard ? 'orphelin-regard' : (o.motif === 'hors_graphe' ? 'orphelin-hors-graphe' : 'orphelin-troncon');
        const ico = estRegard ? '🕳️' : '❓';
        let titre, sous;
        if (estRegard) {
            titre = `${o.type_noeud === 'regard' || !o.type_noeud ? 'Regard' : o.type_noeud} ${o.id}`;
            sous = [o.nom, o.nom_voie, o.commune].filter(v => v && String(v).trim() && String(v).trim().toLowerCase() !== 'nan').join(' · ') || 'aucune connexion';
        } else {
            titre = o.libelle || `Tronçon ${o.id}`;
            const motifTxt = o.motif === 'hors_graphe' ? 'hors graphe (extrémité non résolue)' : 'composante sans exutoire';
            const tech = [o.type_conduite, o.longueur_m ? Math.round(o.longueur_m) + ' m' : null, o.diametre_mm ? 'Ø' + o.diametre_mm : null].filter(Boolean).join(' · ');
            sous = [motifTxt, tech].filter(Boolean).join(' — ');
        }
        return `<div class="orphelin-item ${cls}" data-idx="${_orphelinsItems.indexOf(a)}" title="${_escHtml(a.description || titre)}">
            <span class="orphelin-ico">${ico}</span>
            <span class="orphelin-main">
                <span class="orphelin-titre">${_escHtml(titre)}</span><br>
                <span class="orphelin-sous">${_escHtml(sous)}</span>
            </span>
            <span class="orphelin-zoom"><i class="fas fa-map-marker-alt"></i></span>
        </div>`;
    }).join('');

    listEl.querySelectorAll('.orphelin-item').forEach(el => {
        el.addEventListener('click', () => {
            const it = _orphelinsItems[parseInt(el.dataset.idx, 10)];
            if (it) localiserOrphelin(it);
        });
    });
}

// ---------------------------------------------------------------------------
// Localisation sur la carte active — fonctionne sur n'importe quelle carte
// Leaflet exposée (window.carte du cockpit, window.map ou `map` global).
// ---------------------------------------------------------------------------
let _orphelinPulse = null;
let _orphelinHighlight = null;

function _estCarteLeaflet(c) {
    return !!(c && typeof c.setView === 'function' && typeof c.getCenter === 'function'
        && typeof c.addLayer === 'function');
}

function _carteActiveOrphelins() {
    const candidats = [];
    if (typeof window !== 'undefined') {
        candidats.push(window.carte, window.map, window.leafletMap);
    }
    try { candidats.push(map); } catch (e) { /* noop */ }
    try { candidats.push(carte); } catch (e) { /* noop */ }
    return candidats.find(_estCarteLeaflet) || null;
}

function _pulseOrphelin(carte, lat, lng, label) {
    if (typeof L === 'undefined') return;
    if (_orphelinPulse) {
        try { carte.removeLayer(_orphelinPulse); } catch (e) { /* noop */ }
        _orphelinPulse = null;
    }
    const icon = L.divIcon({
        className: 'pulse-regard-icon',
        html: '<div class="pulse-regard-wrap"><div class="pulse-regard-ring"></div><div class="pulse-regard-core"></div></div>',
        iconSize: [34, 34],
        iconAnchor: [17, 17]
    });
    if (!carte.getPane('searchPulsePane')) {
        try {
            const p = carte.createPane('searchPulsePane');
            p.style.zIndex = 900;
        } catch (e) { /* noop */ }
    }
    _orphelinPulse = L.marker([lat, lng], { icon: icon, zIndexOffset: 1000, pane: 'searchPulsePane' }).addTo(carte);
    if (label) {
        _orphelinPulse.bindTooltip(String(label), {
            permanent: true, direction: 'top', offset: [0, -20], className: 'pulse-regard-label'
        });
    }
    setTimeout(() => {
        if (_orphelinPulse) {
            const el = _orphelinPulse.getElement && _orphelinPulse.getElement();
            if (el) el.classList.add('fade-out');
            setTimeout(() => {
                try { if (_orphelinPulse) carte.removeLayer(_orphelinPulse); } catch (e) { /* noop */ }
                _orphelinPulse = null;
            }, 700);
        }
    }, 8000);
}

function localiserOrphelin(anomalie) {
    const o = (anomalie && anomalie._orphelin) || {};
    const lat = anomalie && anomalie.latitude != null ? anomalie.latitude : o.lat;
    const lng = anomalie && anomalie.longitude != null ? anomalie.longitude : o.lng;
    const carte = _carteActiveOrphelins();
    if (!carte || lat == null || lng == null || !isFinite(lat) || !isFinite(lng)) {
        if (typeof showNotification === 'function') showNotification('Position indisponible pour cet élément.', 'warning');
        return;
    }

    const estRegard = o.genre === 'regard';
    const titre = estRegard ? `Regard ${o.id}` : (o.libelle || `Tronçon ${o.id}`);

    // Centrage — même garde-fou que la recherche : pendant ~8 s aucun
    // rendu asynchrone ne doit détourner la vue.
    try { window._rechercheCentrageJusqua = Date.now() + 8000; } catch (e) { /* noop */ }
    try { carte.setView([lat, lng], 18); } catch (e) { /* noop */ }
    _pulseOrphelin(carte, lat, lng, titre);

    // Surlignage de la géométrie si la couche est chargée (carte /carte)
    let carteMap = null;
    try { carteMap = (typeof map !== 'undefined' && _estCarteLeaflet(map)) ? map : null; } catch (e) { carteMap = null; }
    if (carteMap && carteMap === carte) {
        if (_orphelinHighlight && carteMap.hasLayer(_orphelinHighlight)) {
            try { carteMap.removeLayer(_orphelinHighlight); } catch (e) { /* noop */ }
            _orphelinHighlight = null;
        }
        const cibleId = o.id || anomalie.id_regard || anomalie.id_conduite || anomalie.fid;
        if (cibleId && typeof findLayerById === 'function') {
            const layer = findLayerById(estRegard ? regardsLayer : conduitesLayer, cibleId)
                || findLayerById(conduitesLayer, cibleId)
                || findLayerById(regardsLayer, cibleId);
            if (layer) {
                try {
                    if (layer.getLatLngs) {
                        _orphelinHighlight = L.polyline(layer.getLatLngs(), { color: '#e74c3c', weight: 10, opacity: 0.85, dashArray: '8,10' }).addTo(carteMap);
                    } else if (layer.getLatLng) {
                        _orphelinHighlight = L.circleMarker(layer.getLatLng(), { radius: 18, color: '#e74c3c', weight: 5, opacity: 0.9, fillColor: 'transparent' }).addTo(carteMap);
                    }
                    setTimeout(() => {
                        if (_orphelinHighlight && carteMap.hasLayer(_orphelinHighlight)) {
                            try { carteMap.removeLayer(_orphelinHighlight); } catch (e) { /* noop */ }
                            _orphelinHighlight = null;
                        }
                    }, 12000);
                } catch (e) { /* noop */ }
            }
        }
    }

    // Ouvre la popup d'anomalie si un marqueur correspond (carte /carte)
    setTimeout(() => {
        try {
            const cibleLat = lat, cibleLng = lng;
            Object.values(anomaliesLayers || {}).forEach(layer => {
                if (typeof layer.eachLayer === 'function') {
                    layer.eachLayer(marker => {
                        if (typeof marker.getLatLng === 'function') {
                            const ll = marker.getLatLng();
                            if (Math.abs(ll.lat - cibleLat) < 0.0001 && Math.abs(ll.lng - cibleLng) < 0.0001) {
                                marker.openPopup();
                            }
                        }
                    });
                }
            });
        } catch (e) { /* noop */ }
    }, 450);
}
window.localiserOrphelin = localiserOrphelin;
