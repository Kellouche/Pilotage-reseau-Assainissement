/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Calques cartographiques de résultats : flèches de sens, sous-bassins et focus
 * ================================================================================
 */

window.addEventListener('DOMContentLoaded', initSaaSNavbar);

        // ==========================================
        // GESTION COUCHES THÉMATIQUES (POINTS 1 & 2)
        // ==========================================
        window.basculerCoucheSousBassins = function(checked) {
            if (checked) couches.subcatchments.addTo(carte);
            else carte.removeLayer(couches.subcatchments);
        };

        window.basculerCoucheResultatsRegards = function(checked) {
            if (checked) couches.res_regards.addTo(carte);
            else carte.removeLayer(couches.res_regards);
        };

        window.basculerCoucheResultatsConduites = function(checked) {
            if (checked) {
                couches.res_conduites.addTo(carte);
                if (carte.hasLayer(couches.conduites)) {
                    carte.removeLayer(couches.conduites);
                    const el = document.getElementById('f-conduites');
                    if (el) el.checked = false;
                }
            } else {
                carte.removeLayer(couches.res_conduites);
                // Restaurer la couche physique seulement si sa case est cochée
                const el = document.getElementById('f-conduites');
                if (el && el.checked && !carte.hasLayer(couches.conduites)) {
                    couches.conduites.addTo(carte);
                } else if ((!el || !el.checked) && carte.hasLayer(couches.conduites)) {
                    carte.removeLayer(couches.conduites);
                }
            }
        };

        // ==========================================
        // POINT 3 : SENS D'ÉCOULEMENT DISCRET (AMONT ➔ AVAL)
        // ==========================================
        window.basculerSensEcoulement = function(checked) {
            const el1 = document.getElementById('f-sens-ecoulement');
            const el2 = document.getElementById('f-res-sens-ecoulement');
            if (el1) el1.checked = checked;
            if (el2) el2.checked = checked;

            if (checked) {
                if (couches.sens_ecoulement.getLayers().length === 0) {
                    genererFlechesSensEcoulement();
                }
                couches.sens_ecoulement.addTo(carte);
            } else {
                carte.removeLayer(couches.sens_ecoulement);
            }
        };

        window.genererFlechesSensEcoulement = function() {
            couches.sens_ecoulement.clearLayers();
            if (!window._rawNetworkData || !window._rawNetworkData.couches || !window._rawNetworkData.couches.conduites) return;

            // Indexer les coordonnées exactes des regards pour orientation infaillible Amont -> Aval
            const nodeCoords = {};
            if (window._rawNetworkData.couches.regards && window._rawNetworkData.couches.regards.features) {
                window._rawNetworkData.couches.regards.features.forEach(f => {
                    const p = f.properties || {};
                    const nid = String(p.Code || p.code || p.CODE || p.id || '');
                    if (nid && f.geometry && f.geometry.coordinates) {
                        nodeCoords[nid] = f.geometry.coordinates;
                    }
                });
            }

            const conduitsGeo = window._rawNetworkData.couches.conduites;
            conduitsGeo.features.forEach((feat, idx) => {
                const geom = feat.geometry;
                if (!geom) return;

                let lineCoords = [];
                if (geom.type === 'LineString') {
                    lineCoords = geom.coordinates;
                } else if (geom.type === 'MultiLineString' && geom.coordinates.length > 0) {
                    lineCoords = geom.coordinates[0];
                }
                if (!lineCoords || lineCoords.length < 2) return;

                const pProps = feat.properties || {};
                const uId = String(pProps.ID_AMONT || pProps.id_amont || '');
                const dId = String(pProps.ID_AVAL || pProps.id_aval || '');

                let pAmont = null, pAval = null;
                if (uId && dId && nodeCoords[uId] && nodeCoords[dId]) {
                    pAmont = nodeCoords[uId];
                    pAval = nodeCoords[dId];
                } else {
                    pAmont = lineCoords[0];
                    pAval = lineCoords[lineCoords.length - 1];
                }

                // Point milieu le long de la conduite
                const midIdx = Math.floor(lineCoords.length / 2);
                const midPt = lineCoords[midIdx];
                const midLat = midPt[1];
                const midLng = midPt[0];

                // Calcul du cap (bearing) trigonométrique Amont -> Aval
                const dy = pAval[1] - pAmont[1];
                const dx = (pAval[0] - pAmont[0]) * Math.cos(midLat * Math.PI / 180);
                const angleDeg = Math.atan2(-dy, dx) * 180 / Math.PI;

                const arrowIcon = L.divIcon({
                    className: 'flow-arrow-marker',
                    html: `<div style="transform: rotate(${angleDeg.toFixed(1)}deg); font-size: 13px; font-weight: 900; color: #38bdf8; text-shadow: 0 0 4px rgba(0,0,0,0.9); opacity: 0.85; pointer-events: none; user-select: none;">➤</div>`,
                    iconSize: [16, 16],
                    iconAnchor: [8, 8]
                });

                const marker = L.marker([midLat, midLng], {
                    icon: arrowIcon,
                    interactive: false
                });
                couches.sens_ecoulement.addLayer(marker);
            });
        };

        // ==========================================
        // POINT 1 : SECTORISATION SURFACES VORONOÏ
        // ==========================================
        // FC brut des sous-bassins Voronoï (réseau entier) — conservé pour
        // pouvoir refiltrer par bassin sélectionné sans nouvel appel API.
        window._sousBassinsFC = null;

        // Rend le FC fourni (total ou filtré par bassin) : badge, légende,
        // calques Leaflet. `estFiltre` = vue « bassin sélectionné ».
        window._rendreSousBassins = function(fc, estFiltre) {
            couches.subcatchments.clearLayers();
            if (!fc || !fc.features || fc.features.length === 0) {
                return;
            }

            const count = fc.subcatchments_count || fc.features.length;
            const totArea = (fc.total_area_ha || 0).toFixed(2);
            const nbBv = (window._clustersData && (window._clustersData.clusters_crees || (window._clustersData.resultats && window._clustersData.resultats.length))) || null;
            const bvPrefix = (!estFiltre && nbBv) ? `${nbBv} BV • ` : '';
            const bvSuffix = (!estFiltre && nbBv) ? ` (${nbBv} bassins d'exutoires)` : '';
            const badge = document.getElementById('badge-subcatchments-count');
            if (badge) badge.innerText = `${bvPrefix}${count} SB (${totArea} ha)`;
            const legend = document.getElementById('subcatchments-legend');
            if (legend) legend.innerHTML = estFiltre
                ? `Surface drainée du bassin sélectionné : <b>${totArea} ha</b> sur <b>${count} sous-bassins</b>.`
                : `Surface drainée : <b>${totArea} ha</b> sur <b>${count} sous-bassins</b>${bvSuffix}.`;

            // Optimisation majeure de fluidité : n'attacher les infobulles et événements hover lourds
            // que sur les sous-bassins filtrés (ou petits ensembles). Sur 10 500 polygones globaux,
            // créer 10 500 infobulles et 21 000 écouteurs freeze le navigateur et consomme la RAM.
            const attacherInteractions = estFiltre || (count <= 300);

            L.geoJSON(fc, {
                pane: 'voronoiPane',
                style: {
                    color: '#059669',
                    weight: 1.5,
                    opacity: 0.85,
                    fillColor: '#10b981',
                    fillOpacity: 0.18,
                    dashArray: '4, 4'
                },
                onEachFeature: (feature, layer) => {
                    if (!attacherInteractions) return;
                    const p = feature.properties || {};
                    const sId = p.subcatchment_id || p.id || 'SB';
                    const aHa = (p.area_ha || 0).toFixed(3);
                    const aM2 = (p.area_m2 || 0).toFixed(0);
                    const outNode = p.outlet || '--';
                    const imp = (p.imperv_pct || 70).toFixed(0);
                    const slope = (p.slope_pct || 0.5).toFixed(1);

                    const tooltipHtml = `
                        <div style="font-family: inherit; font-size: 12px; line-height: 1.4;">
                            <div style="font-weight: 800; color: #059669; margin-bottom: 3px; display: flex; align-items: center; gap: 5px;">
                                <i class="fas fa-draw-polygon"></i> Sous-Bassin ${sId}
                            </div>
                            <div style="margin-bottom: 3px;"><span style="color: #64748b;">Exutoire récepteur :</span> <b>Regard N° ${outNode}</b></div>
                            <div>Surface drainée : <b>${aHa} ha</b> (${aM2} m²)</div>
                            <div>Imperméabilisation : <b>${imp} %</b></div>
                            <div>Pente moyenne : <b>${slope} %</b></div>
                        </div>
                    `;
                    layer.bindTooltip(tooltipHtml, { sticky: true, opacity: 0.95 });
                    
                    layer.on('mouseover', function(e) {
                        if (_activeGlobalTooltip && _activeGlobalTooltip !== layer.getTooltip()) {
                            try {
                                if (_activeGlobalTooltip._source && typeof _activeGlobalTooltip._source.closeTooltip === 'function') {
                                    _activeGlobalTooltip._source.closeTooltip();
                                }
                            } catch(_) {}
                        }
                        layer.setStyle({ fillOpacity: 0.38, weight: 2.5, color: '#10b981' });
                    });
                    layer.on('mouseout', function() {
                        if (typeof this.closeTooltip === 'function') {
                            try { this.closeTooltip(); } catch(_) {}
                        }
                        if (_activeGlobalTooltip === this.getTooltip()) {
                            _activeGlobalTooltip = null;
                        }
                        layer.setStyle({ fillOpacity: 0.18, weight: 1.5, color: '#059669' });
                    });
                }
            }).addTo(couches.subcatchments);
        };

        /**
         * Filtre les sous-bassins Voronoï pour le bassin sélectionné :
         * un SB appartient au bassin si son exutoire (`outlet`) est un
         * nœud (u/v) des conduites du cluster affiché. clusterId = null
         * → vue réseau complet. Si l'appartenance est indéterminable
         * (bassin manuel sans edges cluster), on conserve la vue totale.
         */
        window.filtrerSousBassinsPourBassin = function(clusterId) {
            const fc = window._sousBassinsFC;
            if (!fc || !fc.features || !fc.features.length) return;
            const cid = (clusterId === null || clusterId === undefined || clusterId === '') ? null : String(clusterId);
            if (!cid) {
                window._rendreSousBassins(fc, false);
                return;
            }
            // Jointure SB ↔ bassin : les deux portent `id_bassin`
            // (ex. cluster id_bassin=6 « Zone 04 » ↔ SB id_bassin=6.0).
            // L'`outlet` d'un SB est son propre nœud d'exutoire — il ne
            // doit PAS être comparé aux nœuds du bassin.
            const idsBassins = new Set();
            const exutoiresBassins = new Set();
            // cid peut être positionnel (« 3 »), « exutoire:<id> » ou une
            // basin_ref — on accepte les trois espaces d'identité.
            const cidExutoire = cid.toLowerCase().startsWith('exutoire:')
                ? cid.slice('exutoire:'.length) : '';
            const gl = window._activeClusterLayer || (typeof couches !== 'undefined' ? couches.bassins : null);
            if (gl && gl.eachLayer) {
                gl.eachLayer(function(layer) {
                    const ft = layer.feature;
                    if (!ft || !ft.properties) return;
                    const pr = ft.properties;
                    const match = String(pr.cluster_id) === cid
                        || (cidExutoire && String(pr.exutoire_id) === cidExutoire)
                        || String(pr.bassin_ref || '') === cid
                        || String(pr.bassin_ref || '') === ('exutoire:' + cidExutoire);
                    if (!match) return;
                    // Seules les features « bassin » portent id_bassin /
                    // exutoire_id (les marqueurs exutoire et conduites
                    // du même cluster_id n'ont pas id_bassin).
                    if (pr.id_bassin !== undefined && pr.id_bassin !== null && pr.id_bassin !== '') {
                        idsBassins.add(Number(pr.id_bassin));
                    }
                    if (pr.exutoire_id !== undefined && pr.exutoire_id !== null && pr.exutoire_id !== '') {
                        exutoiresBassins.add(String(pr.exutoire_id));
                    }
                });
            }
            if (!idsBassins.size && !exutoiresBassins.size) {
                // Calque cluster pas encore chargé (ordre de chargement) :
                // une seule reprise différée, sinon vue réseau complet.
                if (!window._filtreSbRetry) {
                    window._filtreSbRetry = true;
                    setTimeout(function() {
                        window._filtreSbRetry = false;
                        window.filtrerSousBassinsPourBassin(clusterId);
                    }, 4000);
                }
                window._rendreSousBassins(fc, false);
                return;
            }
            const feats = fc.features.filter(function(f) {
                const p = f.properties || {};
                const ibOk = p.id_bassin !== undefined && p.id_bassin !== null && p.id_bassin !== ''
                    && idsBassins.has(Number(p.id_bassin));
                const exOk = p.exutoire_id !== undefined && p.exutoire_id !== null
                    && String(p.exutoire_id) !== 'orphelin'
                    && exutoiresBassins.has(String(p.exutoire_id));
                return ibOk || exOk;
            });
            const aire = feats.reduce(function(acc, f) {
                return acc + (parseFloat(f.properties && f.properties.area_ha) || 0);
            }, 0);
            window._rendreSousBassins({
                type: 'FeatureCollection',
                features: feats,
                subcatchments_count: feats.length,
                total_area_ha: Math.round(aire * 10000) / 10000
            }, true);
        };

        window.chargerEtAfficherSousBassins = function() {
            const token = localStorage.getItem('swmm_access_token');
            const headers = token ? { 'Authorization': `Bearer ${token}` } : {};

            var _urlSub = '/api/v1/network/subcatchments';
            if (typeof window._urlAvecSnapshot === 'function') _urlSub = window._urlAvecSnapshot(_urlSub);
            fetch(_urlSub, { headers, credentials: 'include' })
                .then(r => r.json())
                .then(fc => {
                    window._sousBassinsFC = fc;
                    window._rendreSousBassins(fc, false);
                    if (window._selectedClusterId) {
                        window.filtrerSousBassinsPourBassin(window._selectedClusterId);
                    }
                })
                .catch(err => console.warn('Erreur chargement sous-bassins:', err));
        };

        // ==========================================
        // GESTION DU FOCUS SUR LA ZONE SIMULÉE (ZOOM À GRANDE ÉCHELLE & IHM)
        // ==========================================
        window.zoomerSurZoneSimulee = function(data, cibleMaxZoom = 19) {
            const map = window.carte || (typeof carte !== 'undefined' ? carte : null);
            if (!data || !map) return;
            const meta = data.meta || {};
            let bounds = null;

            // Priorité 1 : Bounding box directe et certifiée des conduites et regards SWMM simulés
            try {
                if (couches.res_conduites && typeof couches.res_conduites.getBounds === 'function') {
                    const cb = couches.res_conduites.getBounds();
                    if (cb && cb.isValid && cb.isValid()) bounds = L.latLngBounds(cb.getSouthWest(), cb.getNorthEast());
                }
                if (couches.res_regards && typeof couches.res_regards.getBounds === 'function') {
                    const rb = couches.res_regards.getBounds();
                    if (rb && rb.isValid && rb.isValid()) {
                        if (bounds) bounds.extend(rb);
                        else bounds = L.latLngBounds(rb.getSouthWest(), rb.getNorthEast());
                    }
                }
            } catch(e) {}

            // Priorité 2 : Bounding box certifiée WGS84 envoyée directement par le solveur SWMM 5.2
            if ((!bounds || !bounds.isValid()) && meta.bbox && Array.isArray(meta.bbox) && meta.bbox.length === 4) {
                const [minLat, minLon, maxLat, maxLon] = meta.bbox;
                if (!isNaN(minLat) && !isNaN(minLon) && !isNaN(maxLat) && !isNaN(maxLon)) {
                    bounds = L.latLngBounds([minLat, minLon], [maxLat, maxLon]);
                }
            }

            // Priorité 3 : Bounds du bassin pré-calculés lors de la sectorisation
            if ((!bounds || !bounds.isValid()) && meta.cluster_id) {
                const bMap = window._bassinBounds || (typeof _bassinBounds !== 'undefined' ? _bassinBounds : null);
                if (bMap) {
                    const b = bMap[meta.cluster_id] || bMap[String(meta.cluster_id)];
                    if (b && b.isValid && b.isValid()) bounds = b;
                }
            }

            if (bounds && bounds.isValid()) {
                window._lastSimBounds = bounds;
                map.invalidateSize(true);
                // Effet de zoom fluide cinématographique (flyToBounds) à grande échelle sur la zone simulée
                map.flyToBounds(bounds, {
                    padding: [35, 35],
                    maxZoom: cibleMaxZoom || 19,
                    duration: 1.0,
                    easeLinearity: 0.25
                });
            }
        };
        const zoomerSurZoneSimulee = window.zoomerSurZoneSimulee;

        function mettreAJourIHMZoneSimulee(data) {
            if (!data) return;
            const meta = data.meta || {};
            const k = data.kpis || {};
            const isTargeted = !!meta.cluster_id;

            // 1. Panneau d'Ingénierie : Mini-stats de l'en-tête
            const miniStatsEl = document.getElementById('mini-stats');
            if (miniStatsEl) {
                if (isTargeted) {
                    // meta.bassin_nom peut contenir l'identifiant brut
                    // (« 459 ») : on ne retient qu'un vrai nom métier.
                    const _cidM = String(meta.cluster_id !== undefined && meta.cluster_id !== null ? meta.cluster_id : '');
                    const _nomMeta = [meta.cluster_nom, meta.bassin_nom]
                        .map(v => String(v || '').trim())
                        .find(v => v && !/^\d+$/.test(v) && !/^Bassin\s+\d+$/i.test(v) && v !== _cidM);
                    const _nomBassin = _nomMeta
                        || (window._bassinNoms && window._bassinNoms[_cidM])
                        || `Bassin ${_cidM}`;
                    miniStatsEl.innerHTML = `<span style="color: #38bdf8; font-weight: 700;">Bassin : ${_nomBassin}</span> | Conduites: <b>${meta.conduits_count}</b> | Regards: <b>${meta.junctions_count + 1}</b>`;
                    miniStatsEl.style.background = 'rgba(56, 189, 248, 0.15)';
                    miniStatsEl.style.border = '1px solid rgba(56, 189, 248, 0.3)';
                    miniStatsEl.style.color = '#f8fafc';
                } else {
                    miniStatsEl.innerHTML = `Réseau Complet | Conduites: <b>${meta.conduits_count}</b> | Exutoires: <b>${meta.outfalls_count || 1}</b>`;
                    miniStatsEl.style.background = 'rgba(255, 255, 255, 0.06)';
                    miniStatsEl.style.border = 'none';
                    miniStatsEl.style.color = '#94a3b8';
                }
            }

            // 2. Section 2 Hydrologie : Badge & Description
            const badgeSb = document.getElementById('badge-subcatchments-count');
            if (badgeSb) {
                if (isTargeted) {
                    badgeSb.innerHTML = `${meta.subcatchments_count} SB (${meta.total_area_ha} ha)`;
                    badgeSb.style.background = 'rgba(16, 185, 129, 0.2)';
                    badgeSb.style.color = '#34d399';
                } else {
                    badgeSb.innerHTML = `${meta.subcatchments_count} SB (${meta.total_area_ha} ha)`;
                    badgeSb.style.background = '';
                    badgeSb.style.color = '';
                }
            }

            // Réseau sous pression : pompes et tronçons de refoulement modélisés
            const _rfTraites = Array.isArray(meta.refoulements_traites) ? meta.refoulements_traites : [];
            const _nbPompes = _rfTraites.filter(x => x && x.tete_refoulement).length;
            const _rfTxt = _rfTraites.length > 0
                ? ` · ⛽ <b style="color:#fca5a5;">${_nbPompes} pompe(s)</b>, ${_rfTraites.length} tronçon(s) sous pression`
                : '';

            const subLeg = document.getElementById('subcatchments-legend');
            if (subLeg) {
                if (isTargeted) {
                    subLeg.innerHTML = `Périmètre simulé : <b style="color: #38bdf8;">${meta.cluster_nom || meta.bassin_nom || ('Bassin ' + meta.cluster_id)}</b> (${meta.total_area_ha} ha drainés vers l'exutoire ${meta.outfall_code || ''})${_rfTxt}.`;
                } else {
                    subLeg.innerHTML = `Surface drainée totale : <b>${meta.total_area_ha} ha</b> sur <b>${meta.subcatchments_count} sous-bassins</b>${_rfTxt}.`;
                }
            }

            // 3. Section Bassin Sélectionné dans la barre latérale
            const bSec = document.getElementById('bassin-section');
            if (bSec) bSec.style.display = 'block';

            const bSel = document.getElementById('bassin-select');
            let valeurBassin = null;
            if (bSel && isTargeted) {
                const cidMeta = String(meta.cluster_id);
                // meta.cluster_id est dans l'espace exutoire (ex. 234) alors
                // que le dropdown utilise le cluster_id positionnel (ex. 87).
                // Retrouver l'option du dropdown via data-exutoire-id /
                // data-bassin-ref / nom du bassin avant de créer un fantôme.
                const nomMeta = String(meta.cluster_nom || meta.bassin_nom || '').trim().toLowerCase();
                const cidMetaBas = cidMeta.toLowerCase();
                // Priorité 1 : nom du bassin — discriminant fiable car les
                // exutoire_id peuvent entrer en collision avec le
                // cluster_id d'un autre bassin (ex. exutoire 4 = Bensouna
                // alors que meta.cluster_id=4 = Rejet Lbatimat).
                if (nomMeta) {
                    for (let opt of bSel.options) {
                        const txt = String(opt.textContent || '').trim().toLowerCase();
                        // Frontière de mot : « rn 4 » ne doit pas matcher « rn 45 ».
                        if (txt === nomMeta || txt.startsWith(nomMeta + ' ')
                                || txt.startsWith(nomMeta + '(')) {
                            valeurBassin = opt.value; break;
                        }
                    }
                }
                // Priorité 2 : cluster_id exact, puis exutoire/bassin_ref.
                if (!valeurBassin) {
                    for (let opt of bSel.options) {
                        if (opt.value === cidMeta) { valeurBassin = opt.value; break; }
                        const exId = String(opt.dataset.exutoireId || '').trim().toLowerCase();
                        const bref = String(opt.dataset.bassinRef || '').trim().toLowerCase();
                        if ((exId && exId === cidMetaBas)
                                || (bref && bref === ('exutoire:' + cidMetaBas))) {
                            valeurBassin = opt.value; break;
                        }
                    }
                }
                if (!valeurBassin) {
                    const newOpt = document.createElement('option');
                    newOpt.value = cidMeta;
                    newOpt.textContent = `${meta.cluster_id}. ${meta.cluster_nom || 'Bassin ' + meta.cluster_id}`;
                    bSel.appendChild(newOpt);
                    valeurBassin = cidMeta;
                }
                bSel.value = valeurBassin;
            }

            // Conserver une barre latérale sobre : afficher la fiche standard du bassin sans le cartouche lourd de simulation
            if (isTargeted) {
                // Passer l'identité du dropdown (cluster_id positionnel) :
                // highlightCluster/afficherInfoBassin comparent aux
                // properties.cluster_id des couches cartographiques.
                const cidAffichage = valeurBassin || meta.cluster_id;
                afficherInfoBassin(cidAffichage);
                if (typeof highlightCluster === 'function') {
                    highlightCluster(cidAffichage, window._activeClusterLayer || (typeof couches !== 'undefined' ? couches.bassins : null));
                }
            }

            // 4. Mettre en valeur les sous-bassins Voronoï du périmètre simulé
            if (couches.subcatchments) {
                const nRes = data.node_results || {};
                const simNodes = new Set((meta.simulated_nodes || []).map(String));
                couches.subcatchments.eachLayer(layer => {
                    const p = (layer.feature && layer.feature.properties) ? layer.feature.properties : {};
                    const outlet = String(p.outlet || '');
                    if (isTargeted) {
                        const isSim = (simNodes.size > 0) ? simNodes.has(outlet) : (nRes[outlet] || (meta.outfall_code && outlet === String(meta.outfall_code)));
                        if (isSim) {
                            layer.setStyle({
                                color: '#10b981',
                                fillColor: '#10b981',
                                fillOpacity: 0.12,
                                weight: 1.2,
                                opacity: 0.8
                            });
                        } else {
                            layer.setStyle({
                                color: '#475569',
                                fillColor: '#334155',
                                fillOpacity: 0.02,
                                weight: 0.5,
                                opacity: 0.10
                            });
                        }
                    } else {
                        layer.setStyle({
                            color: '#059669',
                            fillColor: '#10b981',
                            fillOpacity: 0.18,
                            weight: 1.5,
                            opacity: 0.85
                        });
                    }
                });
            }

            // 5. Mettre à jour le titre de la légende flottante
            const legTitle = document.querySelector('#sim-floating-legend span');
            if (legTitle) {
                const _warnVersion = meta.gpkg_version_mismatch
                    ? ' <span style="color:#f59e0b; font-size:0.72rem; font-weight:700;" title="Cette simulation provient d\'une autre version du GeoPackage que le réseau actuellement affiché">⚠ autre version réseau</span>'
                    : '';
                if (isTargeted) {
                    legTitle.innerHTML = `<i class="fas fa-layer-group me-1"></i> SWMM 5.2 — ${meta.cluster_nom || meta.bassin_nom || ('Bassin ' + meta.cluster_id)}${_warnVersion}`;
                } else {
                    legTitle.innerHTML = `<i class="fas fa-layer-group me-1"></i> Légende SWMM 5.2${_warnVersion}`;
                }
            }

            // 6. Déplacer les détails de simulation sur la fenêtre de survol de la zone d'étude (bassin et sous-bassins)
            mettreAJourTooltipZoneSimulee(data);
        }

        function mettreAJourTooltipZoneSimulee(data) {
            if (!data || !data.meta) return;
            const meta = data.meta;
            const k = data.kpis || {};
            const isTargeted = !!meta.cluster_id;
            if (!isTargeted) return;

            const qExutoire = parseFloat(k.q_exutoire_m3s !== undefined ? k.q_exutoire_m3s : (k.peak_outflow_m3s || 0));
            const qDerive = parseFloat(k.q_derive_m3s !== undefined ? k.q_derive_m3s : (k.q_deleste_m3s || 0));
            const qGenere = parseFloat(k.q_genere_m3s !== undefined ? k.q_genere_m3s : (qExutoire + qDerive));
            const nbOuv = parseInt(k.nb_ouvrages_raccordes || 0, 10);
            const tauxDerive = k.taux_derive_pct !== undefined ? parseFloat(k.taux_derive_pct) : (qGenere > 0 ? ((qDerive / qGenere) * 100.0) : 0.0);
            const tauxExutoire = k.taux_exutoire_pct !== undefined ? parseFloat(k.taux_exutoire_pct) : Math.max(0, 100.0 - tauxDerive);

            const simCardHtml = `
                <div style="font-family: inherit; font-size: 12px; min-width: 220px; color: #f8fafc; padding: 2px;">
                    <div style="font-weight: 800; color: #38bdf8; font-size: 13px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.15); padding-bottom: 4px; margin-bottom: 6px;">
                        <span>${meta.cluster_nom || meta.bassin_nom || ('Bassin ' + meta.cluster_id)}</span>
                        <span style="font-size: 10px; background: rgba(56,189,248,0.25); color: #38bdf8; padding: 1px 6px; border-radius: 4px; font-weight: 800;">SIMULÉ</span>
                    </div>
                    <div style="color: #94a3b8; font-size: 11px; margin-bottom: 3px;">🏷️ Exutoire récepteur : <b>${meta.outfall_code || 'N/A'}</b></div>
                    <div style="color: #38bdf8; font-size: 11px; margin-bottom: 2px;">🌧️ Sollicitation : <b>${(Number(k.pluvio_intensite_max_mmh || meta.pluvio_intensite_max_mmh || 62.0)).toFixed(1)} mm/h</b> <small style="color:#94a3b8;">(${meta.pluvio_periode_retour || k.pluvio_periode_retour || 'T=10 ans'})</small></div>
                    <div style="margin-bottom: 2px;">📐 Surface drainée : <b>${meta.total_area_ha} ha</b> (${meta.subcatchments_count} sous-bassins)</div>
                    <div style="margin-bottom: 2px;">📍 Regards : <b>${meta.junctions_count + 1}</b> ${k.flooded_nodes_count > 0 ? `<span style="color:#ef4444; font-weight:700;">(${k.flooded_nodes_count} débordements)</span>` : ''}</div>
                    <div style="margin-bottom: 2px;">📏 Conduites : <b>${meta.conduits_count}</b></div>
                    <div style="border-top: 1px solid rgba(255,255,255,0.1); padding-top: 4px; margin-top: 4px;">
                        <div style="color: #38bdf8; font-weight: 700;">🌊 Débit généré : <b>${qGenere.toFixed(3)} m³/s</b></div>
                        <div style="color: #34d399; font-size: 11px; margin-left: 6px;">► Vers exutoire principal : <b>${qExutoire.toFixed(3)} m³/s</b> (${tauxExutoire.toFixed(1)}%)</div>
                        ${qDerive > 0 ? `<div style="color: #22d3ee; font-size: 11px; margin-left: 6px;"><i class="fas fa-random"></i> Dérivé (${nbOuv} ouv. spéc.) : <b>${qDerive.toFixed(3)} m³/s</b> (${tauxDerive.toFixed(1)}%)</div>` : ''}
                    </div>
                    <div style="color: #38bdf8; font-weight: 700; margin-top: 3px;">💧 Erreur continuité : <b>${(k.routing_continuity_error_pct || 0).toFixed(2)} %</b></div>
                </div>
            `;

            // 1. Mettre à jour les polygones de bassins versants dans couches.bassins et window._activeClusterLayer
            const updateBassinLayer = (layer) => {
                const f = layer.feature;
                if (!f || !f.properties) return;
                if (f.properties.type !== 'bassin_urbain') return;
                // meta.cluster_id est dans l'espace exutoire : le polygone
                // doit aussi matcher via exutoire_id / bassin_ref.
                const fp = f.properties;
                const cidMeta = String(meta.cluster_id).toLowerCase();
                const exF = String(fp.exutoire_id || '').trim().toLowerCase();
                const brefF = String(fp.bassin_ref || '').trim().toLowerCase();
                const matchBassin = String(fp.cluster_id) === String(meta.cluster_id)
                    || (exF && exF === cidMeta)
                    || (brefF && brefF === ('exutoire:' + cidMeta));
                if (matchBassin) {
                    if (!layer._originalTooltip) {
                        const curTip = layer.getTooltip();
                        layer._originalTooltip = curTip ? curTip.getContent() : null;
                    }
                    const fullSimTooltip = window.genererTooltipBassinVersantHtml ? window.genererTooltipBassinVersantHtml(f.properties, data) : simCardHtml;
                    layer.unbindTooltip();
                    window._enregistrerInfobulleSim(layer, fullSimTooltip, {
                        sticky: true,
                        direction: 'left',
                        offset: [-15, 0],
                        opacity: 0.98,
                        className: 'sim-bassin-tooltip'
                    });
                    layer._isSimulatedBassin = true;
                    // NB : les écouteurs namespacés Leaflet (« type.ns ») ne se
                    // déclenchent pas sur les événements DOM réels — handlers
                    // simples référencés pour permettre un retrait ciblé.
                    if (layer._simBassinHandlers) {
                        layer.off('mouseover', layer._simBassinHandlers.over);
                        layer.off('mouseout', layer._simBassinHandlers.out);
                    }
                    const _bassinOver = function() {
                        this.setStyle({
                            color: '#0284c7',
                            weight: 3.5,
                            fillColor: '#38bdf8',
                            fillOpacity: 0.32,
                            dashArray: '7, 4'
                        });
                    };
                    const _bassinOut = function() {
                        this.setStyle({
                            color: '#0284c7',
                            weight: 3.5,
                            fillColor: '#38bdf8',
                            fillOpacity: 0.20,
                            dashArray: '7, 4'
                        });
                    };
                    layer._simBassinHandlers = { over: _bassinOver, out: _bassinOut };
                    layer.on('mouseover', _bassinOver);
                    layer.on('mouseout', _bassinOut);
                    try { layer.unbindPopup(); } catch(_) {}
                    layer.options.pane = 'bassinsPane';
                    layer.setStyle({
                        color: '#0284c7',
                        weight: 3.5,
                        fillColor: '#38bdf8',
                        fillOpacity: 0.20,
                        dashArray: '7, 4'
                    });
                    try { layer.bringToFront(); } catch(e) {}
                }
            };

            if (couches.bassins) couches.bassins.eachLayer(updateBassinLayer);
            if (window._activeClusterLayer) window._activeClusterLayer.eachLayer(updateBassinLayer);

            // 2. Mettre à jour les sous-bassins versants Voronoï du périmètre simulé
            if (couches.subcatchments) {
                const nRes = data.node_results || {};
                const simNodes = new Set((meta.simulated_nodes || []).map(String));
                couches.subcatchments.eachLayer(sbLayer => {
                    const p = (sbLayer.feature && sbLayer.feature.properties) ? sbLayer.feature.properties : {};
                    const outlet = String(p.outlet || '');
                    const isSim = (simNodes.size > 0) ? simNodes.has(outlet) : (nRes[outlet] || (meta.outfall_code && outlet === String(meta.outfall_code)));
                    if (isSim) {
                        if (!sbLayer._originalTooltip) {
                            const curTip = sbLayer.getTooltip();
                            sbLayer._originalTooltip = curTip ? curTip.getContent() : null;
                        }
                        const sId = p.subcatchment_id || p.id || 'SB';
                        const aHa = (p.area_ha || 0).toFixed(2);
                        const sbTooltipHtml = `
                            <div style="font-family: inherit; font-size: 12px; min-width: 220px; color: #f8fafc; padding: 2px;">
                                <div style="font-weight: 800; color: #38bdf8; font-size: 13px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.15); padding-bottom: 4px; margin-bottom: 6px;">
                                    <span>${meta.cluster_nom || meta.bassin_nom || ('Bassin ' + meta.cluster_id)}</span>
                                    <span style="font-size: 10px; background: rgba(56,189,248,0.25); color: #38bdf8; padding: 1px 6px; border-radius: 4px; font-weight: 800;">SIMULÉ</span>
                                </div>
                                <div style="color: #94a3b8; font-size: 11px; margin-bottom: 3px;">🏷️ Exutoire récepteur : <b>${meta.outfall_code || 'N/A'}</b></div>
                                <div style="margin-bottom: 2px;">📐 Surface drainée : <b>${meta.total_area_ha} ha</b> (${meta.subcatchments_count} sous-bassins)</div>
                                <div style="margin-bottom: 2px;">📍 Regards : <b>${meta.junctions_count + 1}</b> ${k.flooded_nodes_count > 0 ? `<span style="color:#ef4444; font-weight:700;">(${k.flooded_nodes_count} débordements)</span>` : ''}</div>
                                <div style="margin-bottom: 2px;">📏 Conduites : <b>${meta.conduits_count}</b></div>
                                <div style="border-top: 1px solid rgba(255,255,255,0.1); padding-top: 4px; margin-top: 4px;">
                                    <div style="color: #38bdf8; font-weight: 700;">🌊 Débit généré : <b>${qGenere.toFixed(3)} m³/s</b></div>
                                    <div style="color: #34d399; font-size: 11px; margin-left: 6px;">► Vers exutoire principal : <b>${qExutoire.toFixed(3)} m³/s</b> (${tauxExutoire.toFixed(1)}%)</div>
                                    ${qDerive > 0 ? `<div style="color: #22d3ee; font-size: 11px; margin-left: 6px;"><i class="fas fa-random"></i> Dérivé (${nbOuv} ouv. spéc.) : <b>${qDerive.toFixed(3)} m³/s</b> (${tauxDerive.toFixed(1)}%)</div>` : ''}
                                </div>
                                <div style="color: #38bdf8; font-weight: 700; margin-bottom: 5px; margin-top: 3px;">💧 Erreur continuité : <b>${(k.routing_continuity_error_pct || 0).toFixed(2)} %</b></div>
                                <div style="border-top: 1px dashed rgba(255,255,255,0.15); padding-top: 4px; color: #94a3b8; font-size: 10.5px;">
                                    <i class="fas fa-draw-polygon me-1"></i> Sous-bassin local ${sId} &bull; Regard N° ${outlet} (${aHa} ha)
                                </div>
                            </div>
                        `;
                        sbLayer.unbindTooltip();
                        window._enregistrerInfobulleSim(sbLayer, sbTooltipHtml, {
                            sticky: true,
                            direction: 'left',
                            offset: [-15, 0],
                            opacity: 0.98,
                            className: 'sim-bassin-tooltip'
                        });
                    }
                });
            }

            // 7. Couverture exhaustive : toute infobulle de bassin/sous-bassin
            // non déjà enregistrée (polygones hors zone simulée ou appariement
            // impossible) est aussi soumise à la bascule « Infobulles au
            // survol » — sinon la fiche reste affichée et la case à cocher
            // semble sans effet sur elle.
            const _dejaEnregistree = function (layer) {
                return (window._simTipLayers || []).some(function (e) { return e.layer === layer; });
            };
            const _couvrirInfobulles = function (grp) {
                if (!grp || !grp.eachLayer) return;
                grp.eachLayer(function (l) {
                    if (_dejaEnregistree(l)) return;
                    if (!l.getTooltip || !l.getTooltip()) return;
                    const cur = l.getTooltip().getContent();
                    if (!cur) return;
                    if (!l._originalTooltip) l._originalTooltip = cur;
                    l.unbindTooltip();
                    window._enregistrerInfobulleSim(l, cur, {
                        sticky: true,
                        direction: 'left',
                        offset: [-15, 0],
                        opacity: 0.98,
                        className: 'sim-bassin-tooltip'
                    });
                });
            };
            _couvrirInfobulles(couches.bassins);
            _couvrirInfobulles(window._activeClusterLayer);
            _couvrirInfobulles(couches.subcatchments);
        }
