/**
 * ============================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-08
 * Date de modification : 2026-11-08
 * Objet : Rendu des couches de resultats SWMM (conduites, regards, raccordements orphelins)
 * ================================================================================
 */

// Rendu des resultats de simulation sur la carte : coloration des conduites
// (taux de charge / remplissage), surcharges et debordements des regards,
// puis integration des collecteurs de delestage et ouvrages speciaux.
// Extrait verbatim de resultats_affichage.js (regle 600 lignes).
window._rendreCouchesResultatsSimulation = function (ctx) {
            const data = ctx.data;
            const nRes = ctx.nRes;
            const _couleurConduite = ctx._couleurConduite;
            const _trouverResultatConduite = ctx._trouverResultatConduite;
            const pompeParCid = ctx.pompeParCid;
            const _estRefoulementResultat = ctx._estRefoulementResultat;
            // 1. Conduites : coloration dynamique selon taux de charge Q/Qmax & remplissage
            if (window._rawNetworkData && window._rawNetworkData.couches && window._rawNetworkData.couches.conduites) {
                const pipesGeo = window._rawNetworkData.couches.conduites;
                L.geoJSON(pipesGeo, {
                    pane: 'swmmResultsPane',
                    filter: (feature) => {
                        return !!_trouverResultatConduite(feature.properties);
                    },
                    style: (feature) => {
                        const r = _trouverResultatConduite(feature.properties);
                        if (!r) return { opacity: 0, weight: 0 };

                        const col = _couleurConduite(r);
                        const isSurcharge = (r.status === 'surcharge' || (r.depth_ratio >= 1.0) || (r.flow_ratio >= 1.0));
                        const isCritique = (r.status === 'critique' || (r.depth_ratio >= 0.8));
                        const isModeree = (r.status === 'moderee' || (r.depth_ratio >= 0.5) || (r.flow_ratio >= 0.5));
                        const w = isSurcharge ? 6.5 : (isCritique ? 5.5 : (isModeree ? 4.8 : 4.0));
                        const estRef = _estRefoulementResultat(r);
                        return {
                            color: col,
                            weight: w,
                            opacity: 1.0,
                            lineCap: 'round',
                            lineJoin: 'round',
                            dashArray: estRef ? '6 4' : null
                        };
                    },
                    onEachFeature: (feature, layer) => {
                        const p = feature.properties || {};
                        const r = _trouverResultatConduite(p);
                        if (!r) return;
                        const u = String(r.u_node || p.ID_AMONT || p.id_amont || '').replace(/\.0$/, '').trim();
                        const d = String(r.d_node || p.ID_AVAL || p.id_aval || '').replace(/\.0$/, '').trim();
                        const diam = p.DIAMETRE || p.diametre || (r.diam_mm || 600);

                        const qPct = (r.flow_ratio * 100).toFixed(0);
                        const dPct = (r.depth_ratio * 100).toFixed(0);
                        const estRef = _estRefoulementResultat(r);
                        const pompeId = pompeParCid[String(r.link_id || '')] || '';
                        const popupHtml = `
                            <div style="font-family: inherit; font-size: 12px; min-width: 230px; line-height: 1.45;">
                                <div style="font-weight: 800; font-size: 13px; color: ${_couleurConduite(r)}; margin-bottom: 6px; border-bottom: 1px solid rgba(0,0,0,0.1); padding-bottom: 4px;">
                                    <i class="fas fa-water me-1"></i> Conduite ${r.link_id || ''} (${u} &rarr; ${d})
                                </div>
                                <div style="margin-bottom: 5px; font-weight: 700; color: ${_couleurConduite(r)}; font-size: 11.5px;">
                                    Taux de charge : ${r.label || 'Normal'}
                                </div>
                                ${estRef ? `<div style="margin-bottom: 5px; font-weight: 700; color: #dc2626; font-size: 11.5px;">
                                    ⛽ Réseau sous pression — refoulement${pompeId ? ` · Pompe <b>${pompeId}</b>` : ''}
                                </div>` : ''}
                                <table style="width: 100%; border-collapse: collapse; font-size: 11px;">
                                    <tr><td style="color:#64748b; padding:2px 0;">Charge Q/Qmax :</td><td style="font-weight:700; text-align:right; color:${_couleurConduite(r)};">${qPct} %</td></tr>
                                    <tr><td style="color:#64748b; padding:2px 0;">Remplissage H/D :</td><td style="font-weight:700; text-align:right;">${dPct} %</td></tr>
                                    <tr><td style="color:#64748b; padding:2px 0;">Débit de pointe :</td><td style="font-weight:700; text-align:right;">${(r.max_flow_cms || 0).toFixed(3)} m³/s</td></tr>
                                    <tr><td style="color:#64748b; padding:2px 0;">Vitesse maximale :</td><td style="font-weight:700; text-align:right;">${(r.max_velocity_ms || 0).toFixed(2)} m/s</td></tr>
                                    <tr><td style="color:#64748b; padding:2px 0;">Diamètre :</td><td style="font-weight:700; text-align:right;">${diam} mm</td></tr>
                                    <tr><td style="color:#64748b; padding:2px 0;">Longueur :</td><td style="font-weight:700; text-align:right;">${(r.length || 0).toFixed(1)} m</td></tr>
                                </table>
                            </div>
                        `;
                        layer.bindPopup(popupHtml);
                        window._enregistrerInfobulleSim(layer, `<b>${r.link_id || 'Conduite'}</b> (${u}&rarr;${d}) : Q/Qmax = <b>${qPct}%</b> (${r.label})`, { direction: 'top', offset: [0, -6], opacity: 0.98 });

                        // Interaction de survol épurée sans bringToFront pour préserver le cycle des événements Leaflet
                        layer.on('mouseover', function() {
                            const isS = (r.status === 'surcharge' || (r.depth_ratio >= 1.0) || (r.flow_ratio >= 1.0));
                            const isC = (r.status === 'critique' || (r.depth_ratio >= 0.8));
                            const hW = isS ? 8.0 : (isC ? 7.0 : 6.0);
                            this.setStyle({ weight: hW, opacity: 1.0 });
                        });
                        layer.on('mouseout', function() {
                            const isS = (r.status === 'surcharge' || (r.depth_ratio >= 1.0) || (r.flow_ratio >= 1.0));
                            const isC = (r.status === 'critique' || (r.depth_ratio >= 0.8));
                            const initW = isS ? 6.0 : (isC ? 5.0 : 4.0);
                            this.setStyle({ weight: initW, opacity: 1.0 });
                        });

                        // Clic sur conduite en mode profil en long ou sélection DWF : capture sans ouvrir de popup
                        layer.on('click', function(e) {
                            if (window._dwfPickModeActive) {
                                L.DomEvent.stop(e);
                                const cMap = window.carte || window.map;
                                if (cMap) cMap.closePopup();
                                if (this.closePopup) this.closePopup();
                                return false;
                            }
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
                        layer.on('popupopen', function() {
                            if (window._dwfPickModeActive) {
                                const cMap = window.carte || window.map;
                                if (cMap) cMap.closePopup();
                                if (this.closePopup) this.closePopup();
                            }
                        });
                    }
                }).addTo(couches.res_conduites);
            }

            // 2. Regards : surcharges hydrauliques (orange) et débordements en surface (rouge)
            if (window._rawNetworkData && window._rawNetworkData.couches && window._rawNetworkData.couches.regards) {
                const nodesGeo = window._rawNetworkData.couches.regards;
                const simNodesSet = new Set((data.meta && data.meta.simulated_nodes || []).map(String));

                const injectesDwfMap = {};
                let _listeInjectesDwf = [];
                if (typeof window.dwfExtraireProvenance === 'function') {
                    const _ext = window.dwfExtraireProvenance(data);
                    if (_ext && Array.isArray(_ext.injectes)) _listeInjectesDwf = _ext.injectes;
                }
                if (_listeInjectesDwf.length === 0) {
                    const _provDwf = (data && data.provenance && data.provenance.apports_dwf)
                        || (data && data.kpis && data.kpis.provenance ? data.kpis.provenance.apports_dwf : null);
                    if (_provDwf) {
                        if (Array.isArray(_provDwf.injectes)) _listeInjectesDwf = _provDwf.injectes;
                        else if (Array.isArray(_provDwf)) _listeInjectesDwf = _provDwf;
                    } else if (data && data.meta && Array.isArray(data.meta.apports_dwf)) {
                        _listeInjectesDwf = data.meta.apports_dwf;
                    }
                }
                _listeInjectesDwf.forEach(a => {
                    if (a && a.node_id != null) {
                        const k = String(a.node_id).trim();
                        injectesDwfMap[k] = a;
                        if (k.endsWith('.0')) injectesDwfMap[k.slice(0, -2)] = a;
                    }
                });

                L.geoJSON(nodesGeo, {
                    pane: 'swmmNodesPane',
                    filter: (feature) => {
                        const p = feature.properties || {};
                        const rawCode = p.Code !== undefined ? p.Code : (p.code !== undefined ? p.code : (p.CODE || p.id || ''));
                        const nid = String(rawCode).trim();
                        const cleanNid = nid.endsWith('.0') ? nid.slice(0, -2) : nid;
                        const r = nRes[cleanNid] || nRes[nid] || (cleanNid ? nRes[parseInt(cleanNid)] : null);
                        return (r && (r.status === 'flooded' || r.status === 'surcharged')) || simNodesSet.has(cleanNid) || Boolean(injectesDwfMap[cleanNid] || injectesDwfMap[nid]);
                    },
                    pointToLayer: (feature, latlng) => {
                        const p = feature.properties || {};
                        const rawCode = p.Code !== undefined ? p.Code : (p.code !== undefined ? p.code : (p.CODE || p.id || ''));
                        const nid = String(rawCode).trim();
                        const cleanNid = nid.endsWith('.0') ? nid.slice(0, -2) : nid;
                        const r = nRes[cleanNid] || nRes[nid] || (cleanNid ? nRes[parseInt(cleanNid)] : null);
                        const isFlooded = (r && r.status === 'flooded');
                        const isSurcharged = (r && r.status === 'surcharged');
                        const dwfInj = injectesDwfMap[cleanNid] || injectesDwfMap[nid];

                        if (dwfInj) {
                            // Regard avec apport DWF injecté : halo cyan éclatant (#06b6d4)
                            return L.circleMarker(latlng, {
                                pane: 'swmmNodesPane',
                                radius: isFlooded ? 6.5 : (isSurcharged ? 5.5 : 4.5),
                                color: '#06b6d4',
                                fillColor: isFlooded ? '#dc2626' : (isSurcharged ? '#ea580c' : '#0284c7'),
                                weight: 2.8,
                                opacity: 1,
                                fillOpacity: 0.95
                            });
                        }

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
                        const dwfInj = injectesDwfMap[cleanNid] || injectesDwfMap[nid];

                        // Interception pour la sélection DWF ou le Profil en Long hydraulique (Phase 6.A)
                        // Doit être attachée même sans résultat détaillé (écoulement normal)
                        layer.on('click', function(e) {
                            if (window._dwfPickModeActive) {
                                L.DomEvent.stop(e);
                                const cMap = window.carte || window.map;
                                if (cMap) cMap.closePopup();
                                if (this.closePopup) this.closePopup();
                                setTimeout(() => {
                                    if (cMap) cMap.closePopup();
                                    if (this.closePopup) this.closePopup();
                                }, 10);
                                if (cleanNid && typeof window.dwfAppliquerNoeudSelectionne === 'function') {
                                    window.dwfAppliquerNoeudSelectionne(cleanNid, e.latlng);
                                }
                                return false;
                            }
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

                        const isFlooded = (r && r.status === 'flooded');
                        const isSurcharged = (r && r.status === 'surcharged');
                        const headerColor = isFlooded ? '#dc2626' : (isSurcharged ? '#ea580c' : '#0284c7');
                        const title = isFlooded ? '🚨 DÉBORDEMENT EN SURFACE (INONDATION)' : (isSurcharged ? '⚠️ MISE EN CHARGE HYDRAULIQUE' : 'ℹ️ ÉCOULEMENT NORMAL');

                        const dwfSectionHtml = dwfInj ? `
                            <div style="margin-top: 6px; padding: 6px 8px; background: rgba(6,182,212,0.12); border: 1px solid rgba(6,182,212,0.4); border-radius: 6px;">
                                <div style="font-weight: 800; color: #38bdf8; font-size: 11px; margin-bottom: 2px;">
                                    💧 Apport de temps sec (DWF) injecté
                                </div>
                                <div style="font-size: 11px; color: #f8fafc;">
                                    Débit moyen injecté : <b style="color: #34d399;">${(parseFloat(dwfInj.debit_moyen_m3s || 0) * 1000).toFixed(2)} L/s</b> (${dwfInj.debit_moyen_m3s} m³/s)
                                </div>
                                <div style="font-size: 10px; color: #94a3b8; margin-top: 2px;">
                                    Nature : <b>${dwfInj.nature || 'domestique'}</b> · Profil : <b>${dwfInj.profile_key || 'constant'}</b>
                                    ${dwfInj.code_apport ? ` · Réf : <b style="color:#cbd5e1;">${dwfInj.code_apport}</b>` : ''}
                                </div>
                            </div>
                        ` : '';

                        const popupHtml = `
                            <div style="font-family: inherit; font-size: 12px; min-width: 220px;">
                                <div style="font-weight: 800; font-size: 13px; color: ${headerColor}; margin-bottom: 6px;">
                                    ${title}
                                </div>
                                <div style="margin-bottom: 4px;">Regard de visite : <b>${cleanNid}</b></div>
                                ${r ? `
                                <table style="width: 100%; border-collapse: collapse; font-size: 11px;">
                                    <tr><td style="color:#64748b; padding:2px 0;">Mise en charge :</td><td style="font-weight:700; text-align:right;">${(r.hours_surcharged || 0).toFixed(2)} h</td></tr>
                                    ${isFlooded ? `
                                        <tr><td style="color:#64748b; padding:2px 0;">Durée débordement :</td><td style="font-weight:700; text-align:right; color:#dc2626;">${(r.hours_flooded || 0).toFixed(2)} h</td></tr>
                                        <tr><td style="color:#64748b; padding:2px 0;">Débit de crête débordé :</td><td style="font-weight:700; text-align:right; color:#dc2626;">${(r.peak_flood_flow_cms || 0).toFixed(3)} m³/s</td></tr>
                                        <tr><td style="color:#64748b; padding:2px 0;">Volume total inondé :</td><td style="font-weight:700; text-align:right; color:#dc2626;">${(r.flood_volume_m3 && r.flood_volume_m3 > 0) ? (r.flood_volume_m3 < 1.0 ? `${Number(r.flood_volume_m3).toFixed(2)} m³ (${Math.round(r.flood_volume_m3 * 1000)} L)` : `${Number(r.flood_volume_m3).toFixed(1)} m³`) : '< 0.05 m³'}</td></tr>
                                    ` : ''}
                                </table>
                                ` : ''}
                                ${dwfSectionHtml}
                            </div>
                        `;
                        const volTooltipStr = (r && r.flood_volume_m3 && r.flood_volume_m3 > 0)
                            ? (r.flood_volume_m3 < 1.0 ? `${Number(r.flood_volume_m3).toFixed(2)} m³` : `${Number(r.flood_volume_m3).toFixed(1)} m³`)
                            : '< 0.05 m³';
                        const dwfTooltipExtra = dwfInj
                            ? `<br><span style="color:#38bdf8; font-size:10.5px;">💧 Débit DWF injecté : <b>${(parseFloat(dwfInj.debit_moyen_m3s || 0) * 1000).toFixed(2)} L/s</b> (${dwfInj.nature || 'domestique'}${dwfInj.code_apport ? ' · ' + dwfInj.code_apport : ''})</span>`
                            : '';
                        layer.bindPopup(popupHtml);
                        window._enregistrerInfobulleSim(layer, `<b>${isFlooded ? '🚨 Débordement' : (isSurcharged ? '⚠️ Surcharge' : 'Regard')} : ${cleanNid}</b>${dwfTooltipExtra}${isFlooded ? ` (${volTooltipStr})` : ''}`, { direction: 'top', offset: [0, -6], opacity: 0.98 });
                        
                        layer.on('popupopen', function() {
                            if (window._dwfPickModeActive || (window.profilLongState && window.profilLongState.active)) {
                                const cMap = window.carte || window.map;
                                if (cMap) cMap.closePopup();
                                if (this.closePopup) this.closePopup();
                            }
                        });

                        // Interaction de survol épurée avec conservation du style DWF
                        layer.on('mouseover', function() {
                            const curR = isFlooded ? 5.5 : (isSurcharged ? 4.0 : (dwfInj ? 4.5 : 2.5));
                            const curW = dwfInj ? 3.4 : 2.2;
                            this.setStyle({ radius: curR + 1.8, weight: curW });
                        });
                        layer.on('mouseout', function() {
                            const curR = isFlooded ? 5.5 : (isSurcharged ? 4.0 : (dwfInj ? 4.5 : 2.5));
                            const curW = dwfInj ? 2.8 : (isFlooded ? 1.5 : (isSurcharged ? 1.2 : 0.8));
                            this.setStyle({ radius: curR, weight: curW });
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
                        window._enregistrerInfobulleSim(polyRacc, `⚡ <b>Collecteur de délestage actif (DN 600)</b> &rarr; ${ro.nom} (${ro.distance_m} m)`, { sticky: true, opacity: 0.98 });

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
                        window._enregistrerInfobulleSim(markerActif, `🎯 <b>${ro.nom}</b><br><span style="color:#10b981; font-weight:700;">Mise en eau confirmée (Variante 0)</span>`, { sticky: true });

                        markerActif.on('click', function(e) {
                            if (window._dwfPickModeActive) {
                                L.DomEvent.stop(e);
                                const cMap = window.carte || window.map;
                                if (cMap) cMap.closePopup();
                                if (this.closePopup) this.closePopup();
                                if (ro.regard_proche_id && typeof window.dwfAppliquerNoeudSelectionne === 'function') {
                                    window.dwfAppliquerNoeudSelectionne(ro.regard_proche_id, e.latlng);
                                }
                                return false;
                            }
                        });
                        markerActif.on('popupopen', function() {
                            if (window._dwfPickModeActive) {
                                const cMap = window.carte || window.map;
                                if (cMap) cMap.closePopup();
                                if (this.closePopup) this.closePopup();
                            }
                        });
                        couches.res_conduites.addLayer(polyRacc);
                        couches.res_regards.addLayer(markerActif);
                    }
                });
            }
};
