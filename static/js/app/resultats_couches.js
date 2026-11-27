/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-27
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
