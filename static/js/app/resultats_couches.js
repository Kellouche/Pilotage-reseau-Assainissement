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
                if (!carte.hasLayer(couches.conduites)) {
                    couches.conduites.addTo(carte);
                    const el = document.getElementById('f-conduites');
                    if (el) el.checked = true;
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
        window.chargerEtAfficherSousBassins = function() {
            const token = localStorage.getItem('swmm_access_token');
            const headers = token ? { 'Authorization': `Bearer ${token}` } : {};

            fetch('/api/v1/network/subcatchments', { headers, credentials: 'include' })
                .then(r => r.json())
                .then(fc => {
                    couches.subcatchments.clearLayers();
                    if (!fc || !fc.features || fc.features.length === 0) {
                        return;
                    }
                    
                    const count = fc.subcatchments_count || fc.features.length;
                    const totArea = (fc.total_area_ha || 0).toFixed(2);
                    const nbBv = (window._clustersData && (window._clustersData.clusters_crees || (window._clustersData.resultats && window._clustersData.resultats.length))) || null;
                    const bvPrefix = nbBv ? `${nbBv} BV • ` : '';
                    const bvSuffix = nbBv ? ` (${nbBv} bassins d'exutoires)` : '';
                    const badge = document.getElementById('badge-subcatchments-count');
                    if (badge) badge.innerText = `${bvPrefix}${count} SB (${totArea} ha)`;
                    const legend = document.getElementById('subcatchments-legend');
                    if (legend) legend.innerHTML = `Surface drainée : <b>${totArea} ha</b> sur <b>${count} sous-bassins</b>${bvSuffix}.`;

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
                    miniStatsEl.innerHTML = `<span style="color: #38bdf8; font-weight: 700;">Zone : ${meta.cluster_nom || ('Bassin ' + meta.cluster_id)}</span> | Conduites: <b>${meta.conduits_count}</b> | Regards: <b>${meta.junctions_count + 1}</b>`;
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

            const subLeg = document.getElementById('subcatchments-legend');
            if (subLeg) {
                if (isTargeted) {
                    subLeg.innerHTML = `Périmètre simulé : <b style="color: #38bdf8;">${meta.cluster_nom || ('Bassin ' + meta.cluster_id)}</b> (${meta.total_area_ha} ha drainés vers l'exutoire ${meta.outfall_code || ''}).`;
                } else {
                    subLeg.innerHTML = `Surface drainée totale : <b>${meta.total_area_ha} ha</b> sur <b>${meta.subcatchments_count} sous-bassins</b>.`;
                }
            }

            // 3. Section Bassin Sélectionné dans la barre latérale
            const bSec = document.getElementById('bassin-section');
            if (bSec) bSec.style.display = 'block';

            const bSel = document.getElementById('bassin-select');
            if (bSel && isTargeted) {
                let found = false;
                for (let opt of bSel.options) {
                    if (opt.value === String(meta.cluster_id)) {
                        found = true; break;
                    }
                }
                if (!found) {
                    const newOpt = document.createElement('option');
                    newOpt.value = String(meta.cluster_id);
                    newOpt.textContent = `${meta.cluster_id}. ${meta.cluster_nom || 'Bassin ' + meta.cluster_id}`;
                    bSel.appendChild(newOpt);
                }
                bSel.value = String(meta.cluster_id);
            }

            // Conserver une barre latérale sobre : afficher la fiche standard du bassin sans le cartouche lourd de simulation
            if (isTargeted) {
                afficherInfoBassin(meta.cluster_id);
                if (typeof highlightCluster === 'function') {
                    highlightCluster(meta.cluster_id, window._activeClusterLayer || (typeof couches !== 'undefined' ? couches.bassins : null));
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
                if (isTargeted) {
                    legTitle.innerHTML = `<i class="fas fa-layer-group me-1"></i> SWMM 5.2 — ${meta.cluster_nom || ('Bassin ' + meta.cluster_id)}`;
                } else {
                    legTitle.innerHTML = `<i class="fas fa-layer-group me-1"></i> Légende SWMM 5.2`;
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
                        <span>${meta.cluster_nom || ('Bassin ' + meta.cluster_id)}</span>
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
                if (f.properties.type === 'bassin_urbain' && String(f.properties.cluster_id) === String(meta.cluster_id)) {
                    if (!layer._originalTooltip) {
                        const curTip = layer.getTooltip();
                        layer._originalTooltip = curTip ? curTip.getContent() : null;
                    }
                    const fullSimTooltip = window.genererTooltipBassinVersantHtml ? window.genererTooltipBassinVersantHtml(f.properties, data) : simCardHtml;
                    layer.unbindTooltip();
                    layer.bindTooltip(fullSimTooltip, {
                        sticky: true,
                        direction: 'left',
                        offset: [-15, 0],
                        opacity: 0.98,
                        className: 'sim-bassin-tooltip'
                    });
                    layer._isSimulatedBassin = true;
                    layer.off('mouseout.bassinFix mouseover.simBassin mouseout.simBassin');
                    layer.on('mouseout.bassinFix', function() {
                        if (typeof this.closeTooltip === 'function') {
                            try { this.closeTooltip(); } catch(_) {}
                        }
                    });
                    layer.on('mouseover.simBassin', function() {
                        this.setStyle({
                            color: '#0284c7',
                            weight: 3.5,
                            fillColor: '#38bdf8',
                            fillOpacity: 0.32,
                            dashArray: '7, 4'
                        });
                    });
                    layer.on('mouseout.simBassin', function() {
                        this.setStyle({
                            color: '#0284c7',
                            weight: 3.5,
                            fillColor: '#38bdf8',
                            fillOpacity: 0.20,
                            dashArray: '7, 4'
                        });
                    });
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
                                    <span>${meta.cluster_nom || ('Bassin ' + meta.cluster_id)}</span>
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
                        sbLayer.bindTooltip(sbTooltipHtml, {
                            sticky: true,
                            direction: 'left',
                            offset: [-15, 0],
                            opacity: 0.98,
                            className: 'sim-bassin-tooltip'
                        });
                        sbLayer.off('mouseout.sbFix');
                        sbLayer.on('mouseout.sbFix', function() {
                            if (typeof this.closeTooltip === 'function') {
                                try { this.closeTooltip(); } catch(_) {}
                            }
                        });
                    }
                });
            }
        }
