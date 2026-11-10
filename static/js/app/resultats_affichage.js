/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Affichage des résultats hydrauliques SWMM, coloration des conduites et surcharges
 * ================================================================================
 */

// ==========================================
        // POINTS 2 & 3 : COUCHES RÉSULTATS SWMM 5.2
        // ==========================================
        window.afficherResultatsSimulation = function(data) {
            if (!data || !data.conduit_results || !data.node_results) return;
            window._dernierResultatSimulation = data;

            // Assurer l'existence de panes z-index dédiés pour que les résultats SWMM soient toujours visibles au-dessus des sous-bassins et clusters
            if (!carte.getPane('swmmResultsPane')) {
                const p = carte.createPane('swmmResultsPane');
                p.style.zIndex = 620;
            } else {
                carte.getPane('swmmResultsPane').style.zIndex = 620;
            }
            if (!carte.getPane('swmmNodesPane')) {
                const p = carte.createPane('swmmNodesPane');
                p.style.zIndex = 650;
            } else {
                carte.getPane('swmmNodesPane').style.zIndex = 650;
            }
            if (carte.getPane('tooltipPane')) {
                carte.getPane('tooltipPane').style.zIndex = 1000;
            }
            if (carte.getPane('popupPane')) {
                carte.getPane('popupPane').style.zIndex = 1100;
            }

            // Afficher la légende interactive sur la carte uniquement suite à la simulation
            const leg = document.getElementById('sim-floating-legend');
            if (leg) {
                leg.classList.add('active-legend');
                leg.style.display = 'block';
            }

            // Afficher le badge "Enveloppe de criticité" sur la carte (maximums observés)
// Seulement si le player temporel n'est pas ouvert
            const badgeCrit = document.getElementById('map-criticality-badge');
            const tsActive = window.timeSliderState && window.timeSliderState.active;
            if (badgeCrit && !tsActive) {
                badgeCrit.classList.remove('hidden');
            }

            // Masquer les couches physiques brutes et les clusters pour éviter tout conflit de couleur avec la simulation
            if (typeof clusterCouche !== 'undefined' && clusterCouche && carte.hasLayer(clusterCouche)) {
                carte.removeLayer(clusterCouche);
            }
            if (carte.hasLayer(couches.conduites)) {
                carte.removeLayer(couches.conduites);
                const el = document.getElementById('f-conduites');
                if (el) el.checked = false;
            }
            if (carte.hasLayer(couches.regards)) {
                carte.removeLayer(couches.regards);
                const el = document.getElementById('f-regards');
                if (el) el.checked = false;
            }
            // Maintenir impérativement cochés et visibles les exutoires (rejets) et la station d'épuration (STEP)
            if (couches.rejets && !carte.hasLayer(couches.rejets)) {
                couches.rejets.addTo(carte);
            }
            const elRejets = document.getElementById('f-rejets');
            if (elRejets) elRejets.checked = true;

            if (couches.step && !carte.hasLayer(couches.step)) {
                couches.step.addTo(carte);
            }
            const elStep = document.getElementById('f-step');
            if (elStep) elStep.checked = true;

            // Retirer la couche de prévisualisation en pointillés (remplacée par les résultats de simulation)
            if (window._coucheRaccordementsOrphelins && window.carte) {
                window.carte.removeLayer(window._coucheRaccordementsOrphelins);
                window._coucheRaccordementsOrphelins.clearLayers();
            }

            if (!carte.hasLayer(couches.res_conduites)) couches.res_conduites.addTo(carte);
            if (!carte.hasLayer(couches.res_regards)) couches.res_regards.addTo(carte);

            // Nettoyer les couches de résultats existantes
            couches.res_conduites.clearLayers();
            couches.res_regards.clearLayers();

            const cRes = data.conduit_results;
            const nRes = data.node_results;

            // Indexer les conduites par extrémités (u_node, d_node) pour un appariement direct infaillible
            const conduitByNodes = {};
            Object.values(cRes).forEach(r => {
                const u = String(r.u_node || '').replace(/\.0$/, '').trim();
                const d = String(r.d_node || '').replace(/\.0$/, '').trim();
                if (u && d) {
                    conduitByNodes[`${u}->${d}`] = r;
                    conduitByNodes[`${d}->${u}`] = r;
                }
            });

            // 1. Conduites : coloration dynamique selon taux de charge Q/Qmax & remplissage
            if (window._rawNetworkData && window._rawNetworkData.couches && window._rawNetworkData.couches.conduites) {
                const pipesGeo = window._rawNetworkData.couches.conduites;
                L.geoJSON(pipesGeo, {
                    pane: 'swmmResultsPane',
                    filter: (feature) => {
                        const p = feature.properties || {};
                        const u = String(p.ID_AMONT || p.id_amont || '').replace(/\.0$/, '').trim();
                        const d = String(p.ID_AVAL || p.id_aval || '').replace(/\.0$/, '').trim();
                        return !!(conduitByNodes[`${u}->${d}`] || conduitByNodes[`${d}->${u}`]);
                    },
                    style: (feature) => {
                        const p = feature.properties || {};
                        const u = String(p.ID_AMONT || p.id_amont || '').replace(/\.0$/, '').trim();
                        const d = String(p.ID_AVAL || p.id_aval || '').replace(/\.0$/, '').trim();
                        const r = conduitByNodes[`${u}->${d}`] || conduitByNodes[`${d}->${u}`];
                        if (!r) return { opacity: 0, weight: 0 };

                        const col = r.color || '#10b981';
                        const isSurcharge = (r.status === 'surcharge' || (r.depth_ratio >= 1.0) || (r.flow_ratio >= 1.0));
                        const isCritique = (r.status === 'critique' || (r.depth_ratio >= 0.8));
                        const w = isSurcharge ? 6.0 : (isCritique ? 5.0 : 4.0);
                        return {
                            color: col,
                            weight: w,
                            opacity: 1.0,
                            lineCap: 'round',
                            lineJoin: 'round'
                        };
                    },
                    onEachFeature: (feature, layer) => {
                        const p = feature.properties || {};
                        const u = String(p.ID_AMONT || p.id_amont || '').replace(/\.0$/, '').trim();
                        const d = String(p.ID_AVAL || p.id_aval || '').replace(/\.0$/, '').trim();
                        const r = conduitByNodes[`${u}->${d}`] || conduitByNodes[`${d}->${u}`];
                        if (!r) return;
                        const diam = p.DIAMETRE || p.diametre || (r.diam_mm || 600);

                        const qPct = (r.flow_ratio * 100).toFixed(0);
                        const dPct = (r.depth_ratio * 100).toFixed(0);
                        const popupHtml = `
                            <div style="font-family: inherit; font-size: 12px; min-width: 230px; line-height: 1.45;">
                                <div style="font-weight: 800; font-size: 13px; color: ${r.color}; margin-bottom: 6px; border-bottom: 1px solid rgba(0,0,0,0.1); padding-bottom: 4px;">
                                    <i class="fas fa-water me-1"></i> Conduite ${r.link_id || ''} (${u} &rarr; ${d})
                                </div>
                                <div style="margin-bottom: 5px; font-weight: 700; color: ${r.color}; font-size: 11.5px;">
                                    Taux de charge : ${r.label || 'Normal'}
                                </div>
                                <table style="width: 100%; border-collapse: collapse; font-size: 11px;">
                                    <tr><td style="color:#64748b; padding:2px 0;">Charge Q/Qmax :</td><td style="font-weight:700; text-align:right; color:${r.color};">${qPct} %</td></tr>
                                    <tr><td style="color:#64748b; padding:2px 0;">Remplissage H/D :</td><td style="font-weight:700; text-align:right;">${dPct} %</td></tr>
                                    <tr><td style="color:#64748b; padding:2px 0;">Débit de pointe :</td><td style="font-weight:700; text-align:right;">${(r.max_flow_cms || 0).toFixed(3)} m³/s</td></tr>
                                    <tr><td style="color:#64748b; padding:2px 0;">Vitesse maximale :</td><td style="font-weight:700; text-align:right;">${(r.max_velocity_ms || 0).toFixed(2)} m/s</td></tr>
                                    <tr><td style="color:#64748b; padding:2px 0;">Diamètre :</td><td style="font-weight:700; text-align:right;">${diam} mm</td></tr>
                                    <tr><td style="color:#64748b; padding:2px 0;">Longueur :</td><td style="font-weight:700; text-align:right;">${(r.length || 0).toFixed(1)} m</td></tr>
                                </table>
                            </div>
                        `;
                        layer.bindPopup(popupHtml);
                        layer.bindTooltip(`<b>${r.link_id || 'Conduite'}</b> (${u}&rarr;${d}) : Q/Qmax = <b>${qPct}%</b> (${r.label})`, { direction: 'top', offset: [0, -6], opacity: 0.98 });
                        
                        // Interaction de survol épurée sans bringToFront pour préserver le cycle des événements Leaflet
                        layer.on('mouseover', function() {
                            const isS = (r.status === 'surcharge' || (r.depth_ratio >= 1.0) || (r.flow_ratio >= 1.0));
                            const isC = (r.status === 'critique' || (r.depth_ratio >= 0.8));
                            const hW = isS ? 8.0 : (isC ? 7.0 : 6.0);
                            this.setStyle({ weight: hW, opacity: 1.0 });
                            this.openTooltip();
                        });
                        layer.on('mouseout', function() {
                            const isS = (r.status === 'surcharge' || (r.depth_ratio >= 1.0) || (r.flow_ratio >= 1.0));
                            const isC = (r.status === 'critique' || (r.depth_ratio >= 0.8));
                            const initW = isS ? 6.0 : (isC ? 5.0 : 4.0);
                            this.setStyle({ weight: initW, opacity: 1.0 });
                            this.closeTooltip();
                        });

                        // Clic sur conduite en mode profil en long : capture le regard cible sans ouvrir de popup
                        layer.on('click', function(e) {
                            if (window.profilLongState && window.profilLongState.active) {
                                L.DomEvent.stop(e);
                                const cMap = window.carte || window.map;
                                if (cMap) cMap.closePopup();
                                if (this.closePopup) this.closePopup();
                                const targetNode = (window.profilLongState.step === 'amont') ? u : d;
                                if (targetNode && window.handleRegardClickForProfil) {
                                    window.handleRegardClickForProfil(targetNode, e.latlng);
                                }
                                return false;
                            }
                        });
                    }
                }).addTo(couches.res_conduites);
            }

            // 2. Regards : surcharges hydrauliques (orange) et débordements en surface (rouge)
            if (window._rawNetworkData && window._rawNetworkData.couches && window._rawNetworkData.couches.regards) {
                const nodesGeo = window._rawNetworkData.couches.regards;
                const simNodesSet = new Set((data.meta && data.meta.simulated_nodes || []).map(String));

                L.geoJSON(nodesGeo, {
                    pane: 'swmmNodesPane',
                    filter: (feature) => {
                        const p = feature.properties || {};
                        const rawCode = p.Code !== undefined ? p.Code : (p.code !== undefined ? p.code : (p.CODE || p.id || ''));
                        const nid = String(rawCode).trim();
                        const cleanNid = nid.endsWith('.0') ? nid.slice(0, -2) : nid;
                        const r = nRes[cleanNid] || nRes[nid] || (cleanNid ? nRes[parseInt(cleanNid)] : null);
                        return (r && (r.status === 'flooded' || r.status === 'surcharged')) || simNodesSet.has(cleanNid);
                    },
                    pointToLayer: (feature, latlng) => {
                        const p = feature.properties || {};
                        const rawCode = p.Code !== undefined ? p.Code : (p.code !== undefined ? p.code : (p.CODE || p.id || ''));
                        const nid = String(rawCode).trim();
                        const cleanNid = nid.endsWith('.0') ? nid.slice(0, -2) : nid;
                        const r = nRes[cleanNid] || nRes[nid] || (cleanNid ? nRes[parseInt(cleanNid)] : null);
                        const isFlooded = (r && r.status === 'flooded');
                        const isSurcharged = (r && r.status === 'surcharged');

                        if (isFlooded) {
                            return L.circleMarker(latlng, {
                                pane: 'swmmNodesPane',
                                radius: 5.5,
                                color: '#ffffff',
                                fillColor: '#dc2626',
                                weight: 1.5,
                                opacity: 1,
                                fillOpacity: 0.95
                            });
                        } else if (isSurcharged) {
                            return L.circleMarker(latlng, {
                                pane: 'swmmNodesPane',
                                radius: 4.0,
                                color: '#ffffff',
                                fillColor: '#ea580c',
                                weight: 1.2,
                                opacity: 1,
                                fillOpacity: 0.9
                            });
                        } else {
                            return L.circleMarker(latlng, {
                                pane: 'swmmNodesPane',
                                radius: 2.5,
                                color: '#ffffff',
                                fillColor: '#0284c7',
                                weight: 0.8,
                                opacity: 0.85,
                                fillOpacity: 0.75
                            });
                        }
                    },
                    onEachFeature: (feature, layer) => {
                        const p = feature.properties || {};
                        const rawCode = p.Code !== undefined ? p.Code : (p.code !== undefined ? p.code : (p.CODE || p.id || ''));
                        const nid = String(rawCode).trim();
                        const cleanNid = nid.endsWith('.0') ? nid.slice(0, -2) : nid;
                        const r = nRes[cleanNid] || nRes[nid] || (cleanNid ? nRes[parseInt(cleanNid)] : null);
                        if (!r) {
                            layer.bindTooltip(`Regard ${cleanNid} (Écoulement normal)`, { sticky: true });
                            return;
                        }

                        const isFlooded = (r.status === 'flooded');
                        const isSurcharged = (r.status === 'surcharged');
                        const headerColor = isFlooded ? '#dc2626' : (isSurcharged ? '#ea580c' : '#0284c7');
                        const title = isFlooded ? '🚨 DÉBORDEMENT EN SURFACE (INONDATION)' : (isSurcharged ? '⚠️ MISE EN CHARGE HYDRAULIQUE' : 'ℹ️ ÉCOULEMENT NORMAL');

                        const popupHtml = `
                            <div style="font-family: inherit; font-size: 12px; min-width: 220px;">
                                <div style="font-weight: 800; font-size: 13px; color: ${headerColor}; margin-bottom: 6px;">
                                    ${title}
                                </div>
                                <div style="margin-bottom: 4px;">Regard de visite : <b>${cleanNid}</b></div>
                                <table style="width: 100%; border-collapse: collapse; font-size: 11px;">
                                    <tr><td style="color:#64748b; padding:2px 0;">Mise en charge :</td><td style="font-weight:700; text-align:right;">${(r.hours_surcharged || 0).toFixed(2)} h</td></tr>
                                    ${isFlooded ? `
                                        <tr><td style="color:#64748b; padding:2px 0;">Durée débordement :</td><td style="font-weight:700; text-align:right; color:#dc2626;">${(r.hours_flooded || 0).toFixed(2)} h</td></tr>
                                        <tr><td style="color:#64748b; padding:2px 0;">Débit de crête débordé :</td><td style="font-weight:700; text-align:right; color:#dc2626;">${(r.peak_flood_flow_cms || 0).toFixed(3)} m³/s</td></tr>
                                        <tr><td style="color:#64748b; padding:2px 0;">Volume total inondé :</td><td style="font-weight:700; text-align:right; color:#dc2626;">${(r.flood_volume_m3 && r.flood_volume_m3 > 0) ? (r.flood_volume_m3 < 1.0 ? `${Number(r.flood_volume_m3).toFixed(2)} m³ (${Math.round(r.flood_volume_m3 * 1000)} L)` : `${Number(r.flood_volume_m3).toFixed(1)} m³`) : '< 0.05 m³'}</td></tr>
                                    ` : ''}
                                </table>
                            </div>
                        `;
                        const volTooltipStr = (r.flood_volume_m3 && r.flood_volume_m3 > 0)
                            ? (r.flood_volume_m3 < 1.0 ? `${Number(r.flood_volume_m3).toFixed(2)} m³` : `${Number(r.flood_volume_m3).toFixed(1)} m³`)
                            : '< 0.05 m³';
                        layer.bindPopup(popupHtml);
                        layer.bindTooltip(`<b>${isFlooded ? '🚨 Débordement' : (isSurcharged ? '⚠️ Surcharge' : 'Regard')} : ${cleanNid}</b>${isFlooded ? ` (${volTooltipStr})` : ''}`, { direction: 'top', offset: [0, -6], opacity: 0.98 });
                        
                        // Interception pour le Profil en Long hydraulique (Phase 6.A)
                        layer.on('click', function(e) {
                            if (window.profilLongState && window.profilLongState.active) {
                                L.DomEvent.stop(e);
                                const cMap = window.carte || window.map;
                                if (cMap) cMap.closePopup();
                                if (this.closePopup) this.closePopup();
                                setTimeout(() => {
                                    if (cMap) cMap.closePopup();
                                    if (this.closePopup) this.closePopup();
                                }, 10);

                                if (cleanNid && window.handleRegardClickForProfil) {
                                    window.handleRegardClickForProfil(cleanNid, e.latlng);
                                }
                                return false;
                            }
                        });

                        layer.on('popupopen', function() {
                            if (window.profilLongState && window.profilLongState.active) {
                                const cMap = window.carte || window.map;
                                if (cMap) cMap.closePopup();
                                if (this.closePopup) this.closePopup();
                            }
                        });

                        // Interaction de survol épurée sans bringToFront
                        layer.on('mouseover', function() {
                            const curR = isFlooded ? 5.5 : (isSurcharged ? 4.0 : 2.5);
                            this.setStyle({ radius: curR + 1.8, weight: 2.2 });
                            this.openTooltip();
                        });
                        layer.on('mouseout', function() {
                            const curR = isFlooded ? 5.5 : (isSurcharged ? 4.0 : 2.5);
                            const curW = isFlooded ? 1.5 : (isSurcharged ? 1.2 : 0.8);
                            this.setStyle({ radius: curR, weight: curW });
                            this.closeTooltip();
                        });
                    }
                }).addTo(couches.res_regards);
            }

            // 2bis. Intégration cartographique des collecteurs de délestage et ouvrages spéciaux mis en eau (Variante 0)
            const raccOrph = (data && data.meta && Array.isArray(data.meta.raccordements_orphelins))
                ? data.meta.raccordements_orphelins
                : (window._ouvragesOrphelinsCandidatsSelectionnes || []);
            if (Array.isArray(raccOrph) && raccOrph.length > 0) {
                raccOrph.forEach((ro) => {
                    if (ro.regard_coord_wgs84 && ro.ouvrage_coord_wgs84) {
                        const rPt = ro.regard_coord_wgs84;
                        const oPt = ro.ouvrage_coord_wgs84;
                        const coutFmt = window.formaterCoutDZD(ro.cout_estime_dzd);
                        
                        // Collecteur de secours (tracé cyan néon épais et net avec opacité 100%)
                        const polyRacc = L.polyline([rPt, oPt], {
                            pane: 'swmmResultsPane',
                            color: '#06b6d4',
                            weight: 6.0,
                            opacity: 1.0,
                            lineCap: 'round',
                            lineJoin: 'round'
                        });

                        const popupHtml = `
                            <div style="font-family: inherit; font-size: 12px; min-width: 250px; line-height: 1.45;">
                                <div style="font-weight: 800; font-size: 13px; color: #06b6d4; margin-bottom: 6px; border-bottom: 1px solid rgba(0,0,0,0.1); padding-bottom: 4px;">
                                    ⚡ Collecteur de Décharge de Secours (Variante 0)
                                </div>
                                <div style="margin-bottom: 5px; font-weight: 700; color: #10b981; font-size: 11.5px;">
                                    Raccordement Actif &bull; Ouvrage mis en eau
                                </div>
                                <table style="width: 100%; border-collapse: collapse; font-size: 11px;">
                                    <tr><td style="color:#64748b; padding:2px 0;">Destination :</td><td style="font-weight:700; text-align:right;">${ro.nom}</td></tr>
                                    <tr><td style="color:#64748b; padding:2px 0;">Regard amont :</td><td style="font-weight:700; text-align:right;">Regard ${ro.regard_proche_id}</td></tr>
                                    <tr><td style="color:#64748b; padding:2px 0;">Longueur :</td><td style="font-weight:700; text-align:right;">${ro.distance_m} m</td></tr>
                                    <tr><td style="color:#64748b; padding:2px 0;">Diamètre :</td><td style="font-weight:700; text-align:right;">DN 600 mm</td></tr>
                                    <tr><td style="color:#64748b; padding:2px 0;">Coût estimé :</td><td style="font-weight:700; text-align:right; color:#f59e0b;">${coutFmt}</td></tr>
                                    <tr><td style="color:#64748b; padding:2px 0;">Gain économique :</td><td style="font-weight:700; text-align:right; color:#10b981;">&gt; 90% d'économie</td></tr>
                                </table>
                            </div>
                        `;
                        polyRacc.bindPopup(popupHtml);
                        polyRacc.bindTooltip(`⚡ <b>Collecteur de délestage actif (DN 600)</b> &rarr; ${ro.nom} (${ro.distance_m} m)`, { sticky: true, opacity: 0.98 });

                        // Marqueur de l'ouvrage spécial récepteur activé avec dimensionnement dynamique ajusté au zoom
                        const curZ = carte.getZoom ? carte.getZoom() : 15;
                        const rActif = calculerRayonOuvrageSpecial(curZ);
                        const markerActif = L.circleMarker(oPt, {
                            pane: 'swmmNodesPane',
                            radius: rActif,
                            color: '#ffffff',
                            fillColor: ro.badge_color || '#06b6d4',
                            weight: 2.5,
                            opacity: 1.0,
                            fillOpacity: 0.95,
                            className: 'orphan-zoom-marker'
                        });
                        markerActif.bindPopup(`
                            <div style="font-family: inherit; font-size: 12px; min-width: 240px;">
                                <div style="font-weight: 800; font-size: 13px; color: ${ro.badge_color || '#06b6d4'}; margin-bottom: 6px;">
                                    🎯 OUVRAGE SPÉCIAL EN SERVICE (MISE EN EAU)
                                </div>
                                <div style="font-weight: 700; margin-bottom: 4px;">${ro.nom}</div>
                                <div style="font-size: 11px; color: #475569; line-height: 1.4;">
                                    Cet ouvrage existant reçoit le débit délesté du Regard <b>${ro.regard_proche_id}</b> par un collecteur de <b>${ro.distance_m} m</b> (DN 600 mm).
                                </div>
                            </div>
                        `);
                        markerActif.bindTooltip(`🎯 <b>${ro.nom}</b><br><span style="color:#10b981; font-weight:700;">Mise en eau confirmée (Variante 0)</span>`, { sticky: true });

                        couches.res_conduites.addLayer(polyRacc);
                        couches.res_regards.addLayer(markerActif);
                    }
                });
            }

            // Assurer que les couches de résultats sont bien au premier plan
            try {
                if (couches.res_conduites && couches.res_conduites.bringToFront) couches.res_conduites.bringToFront();
                if (couches.res_regards && couches.res_regards.bringToFront) couches.res_regards.bringToFront();
            } catch(e) {}

            // Cadrage automatique et centrage optimal sur le sous-bassin / réseau simulé
            try {
                let boundsToFit = null;
                if (couches.res_conduites && couches.res_conduites.getLayers().length > 0) {
                    boundsToFit = couches.res_conduites.getBounds();
                } else if (window._activeClusterLayer && window._activeClusterLayer.getBounds && window._activeClusterLayer.getBounds().isValid()) {
                    boundsToFit = window._activeClusterLayer.getBounds();
                }
                if (boundsToFit && boundsToFit.isValid()) {
                    carte.fitBounds(boundsToFit, { padding: [35, 35], maxZoom: 19 });
                }
            } catch(e) {
                console.warn("Erreur cadrage zoom simulation:", e);
            }

            if (typeof window.mettreAJourIndicateursEtKpisSimulation === 'function') {
                window.mettreAJourIndicateursEtKpisSimulation(data);
            }
            window._dernierResultatSimulation = data;
            if (typeof activerActionsSimulation === 'function') {
                activerActionsSimulation(true);
            }
        };
