/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Préchargement silencieux, infobulles enrichies et partitionnement des bassins
 * ================================================================================
 */

// ==========================================
        // INFOBULLE NOIRE ENRICHIE DES BASSINS VERSANTS
        // ==========================================
        window.genererTooltipBassinVersantHtml = function(p, simData = null) {
            if (!p) return '';
            const cid = p.cluster_id !== undefined ? p.cluster_id : (p.id_bassin || '');
            const nom = p.nom || p.nom_exutoire || `Bassin ${cid}`;
            
            let typEx = 'EXUTOIRE';
            if (p.exutoire_type) typEx = String(p.exutoire_type).toUpperCase();
            else if (p.libelle_type) typEx = String(p.libelle_type).toUpperCase();
            else if (p.type_ouvrage) typEx = String(p.type_ouvrage).toUpperCase();

            if (typEx.includes('DEVERSOIR') || typEx.includes('DVO')) typEx = 'DEVERSOIR_ORAGE';
            else if (typEx.includes('STEP')) typEx = 'STATION_EPURATION_STEP';
            else if (typEx.includes('POMPAGE') || typEx.includes('RELEVAGE')) typEx = 'STATION_POMPAGE';
            else if (typEx.includes('REJET') || typEx.includes('OUED')) typEx = 'REJET_NATUREL';

            let surfHa = 'N/A';
            if (p.surface_ha !== undefined && p.surface_ha !== null) {
                surfHa = `${Number(p.surface_ha).toFixed(2)} ha`;
            }

            const nbReg = (p.nb_regards !== undefined && p.nb_regards !== null) ? p.nb_regards : 'N/A';
            const nbOrph = parseInt(p.nb_regards_orphelins || 0, 10);

            const nbCond = (p.nb_conduites !== undefined && p.nb_conduites !== null) ? p.nb_conduites : (p.nb_troncons !== undefined ? p.nb_troncons : 'N/A');
            const longM = (p.longueur_totale_m !== undefined && p.longueur_totale_m !== null) ? Math.round(Number(p.longueur_totale_m)) : null;
            const longStr = longM !== null ? ` (${longM} m)` : '';

            // Vérifier si ce bassin est actuellement simulé (dans simData ou window._dernierResultatSimulation)
            const activeSim = simData || (window._dernierResultatSimulation && window._dernierResultatSimulation.meta && String(window._dernierResultatSimulation.meta.cluster_id) === String(cid) ? window._dernierResultatSimulation : null);
            const isSimulated = !!(activeSim && activeSim.meta && String(activeSim.meta.cluster_id) === String(cid));

            let html = `
                <div style="font-family: inherit; font-size: 12px; min-width: 220px; color: #f8fafc; padding: 2px; line-height: 1.45;">
                    <div style="font-weight: 800; color: #38bdf8; font-size: 13px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.15); padding-bottom: 4px; margin-bottom: 6px;">
                        <span>${nom}</span>
                        ${isSimulated ? '<span style="font-size: 10px; background: rgba(56,189,248,0.25); color: #38bdf8; padding: 1px 6px; border-radius: 4px; font-weight: 800;">SIMULÉ</span>' : ''}
                    </div>
                    <div style="color: #94a3b8; font-size: 11px; margin-bottom: 3px;">🏷️ Type : <b style="color: #f1f5f9;">${typEx}</b></div>
                    <div style="color: #cbd5e1; margin-bottom: 2px;">📐 Surface : <b style="color: #38bdf8;">${surfHa}</b></div>
                    <div style="color: #cbd5e1; margin-bottom: 2px;">📍 Regards : <b>${nbReg}</b> ${nbOrph > 0 ? `<span style="color:#f59e0b; font-size: 10px;">(${nbOrph} orphelins rattachés)</span>` : ''}</div>
                    <div style="color: #cbd5e1; margin-bottom: 2px;">📏 Conduites : <b>${nbCond}</b>${longStr}</div>
                    ${p.zone_collecte ? `<div style="color: #94a3b8; font-size: 10.5px; margin-top: 2px;">🏘️ Zone : <b>${p.zone_collecte}</b></div>` : ''}
            `;

            // Si le bassin a été simulé, ajouter le volet hydraulique complet
            if (isSimulated && activeSim.kpis) {
                const k = activeSim.kpis;
                const m = activeSim.meta || {};
                const qExutoire = parseFloat(k.q_exutoire_m3s !== undefined ? k.q_exutoire_m3s : (k.peak_outflow_m3s || 0));
                const qDerive = parseFloat(k.q_derive_m3s !== undefined ? k.q_derive_m3s : (k.q_deleste_m3s || 0));
                const qGenere = parseFloat(k.q_genere_m3s !== undefined ? k.q_genere_m3s : (qExutoire + qDerive));
                const nbOuv = parseInt(k.nb_ouvrages_raccordes || 0, 10);
                const tauxDerive = k.taux_derive_pct !== undefined ? parseFloat(k.taux_derive_pct) : (qGenere > 0 ? ((qDerive / qGenere) * 100.0) : 0.0);
                const tauxExutoire = k.taux_exutoire_pct !== undefined ? parseFloat(k.taux_exutoire_pct) : Math.max(0, 100.0 - tauxDerive);

                const qGenereStr = window.formaterNombre ? window.formaterNombre(qGenere, 3) : qGenere.toFixed(3);
                const qExutoireStr = window.formaterNombre ? window.formaterNombre(qExutoire, 3) : qExutoire.toFixed(3);
                const qDeriveStr = window.formaterNombre ? window.formaterNombre(qDerive, 3) : qDerive.toFixed(3);
                const tauxDeriveStr = window.formaterNombre ? window.formaterNombre(tauxDerive, 1) : tauxDerive.toFixed(1);
                const tauxExutoireStr = window.formaterNombre ? window.formaterNombre(tauxExutoire, 1) : tauxExutoire.toFixed(1);

                html += `
                    <div style="border-top: 1px solid rgba(255,255,255,0.15); padding-top: 5px; margin-top: 5px;">
                        <div style="color: #38bdf8; font-size: 11px; margin-bottom: 2px;">🌧️ Sollicitation : <b>${(Number(k.pluvio_intensite_max_mmh || m.pluvio_intensite_max_mmh || 62.0)).toFixed(1)} mm/h</b> <small style="color:#94a3b8;">(${m.pluvio_periode_retour || k.pluvio_periode_retour || 'T=10 ans'})</small></div>
                        <div style="color: #38bdf8; font-weight: 700;">🌊 Débit généré : <b>${qGenereStr} m³/s</b></div>
                        <div style="color: #34d399; font-size: 11px; margin-left: 6px;">► Vers exutoire principal : <b>${qExutoireStr} m³/s</b> (${tauxExutoireStr}%)</div>
                        ${qDerive > 0 ? `<div style="color: #22d3ee; font-size: 11px; margin-left: 6px;"><i class="fas fa-random"></i> Dérivé (${nbOuv} ouv. spéc.) : <b>${qDeriveStr} m³/s</b> (${tauxDeriveStr}%)</div>` : ''}
                        <div style="color: #38bdf8; font-weight: 700; margin-top: 3px;">💧 Erreur continuité : <b>${(k.routing_continuity_error_pct || 0).toFixed(2)} %</b></div>
                    </div>
                `;
            }

            html += `</div>`;
            return html;
        };

        // Gestion et fonction globale de sectorisation / détection des clusters
        window._isPartitioningInProgress = false;
        window._partitioningCallbacks = [];
        window.lancerPartitionnementBassins = function(onSuccessCallback, messageOverlay, afficherOverlay = false, rezoomer = false) {
            if (window._isPartitioningInProgress) {
                console.warn('[clusters] Partitionnement déjà en cours, enregistrement du rappel.');
                if (typeof onSuccessCallback === 'function') {
                    window._partitioningCallbacks.push(onSuccessCallback);
                }
                return;
            }
            window._isPartitioningInProgress = true;
            if (typeof onSuccessCallback === 'function') {
                window._partitioningCallbacks.push(onSuccessCallback);
            }
            const btn = document.getElementById('detect-cluster-btn');
            const statusDiv = document.getElementById('cluster-status');
            
            // Afficher l'overlay uniquement si demandé explicitement
            if (afficherOverlay) {
                montrerChargement(true, messageOverlay || 'Analyse topologique et partitionnement des bassins versants...');
            }
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Partitionnement...';
            }
            if (statusDiv) {
                statusDiv.style.display = 'block';
                statusDiv.innerHTML = '<span style="color:#38bdf8;"><i class="fas fa-spinner fa-spin me-1"></i> Détection et tracé automatique des bassins versants...</span>';
            }
            
            // Effacer les anciens clusters
            clusterCouche.clearLayers();
            couches.bassins.clearLayers();
            
            // Appeler l'API de détection des clusters
            return fetch('/api/v1/clusters/recalculate-all?persist=false', { method: 'POST' })
                .then(response => {
                    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                    return response.json();
                })
                .then(clusterData => {
                    window._clustersData = clusterData;
                    clusterData.features = (clusterData.resultats || []).flatMap(result =>
                        result.geojson && Array.isArray(result.geojson.features)
                            ? result.geojson.features
                            : []
                    );
                    if (clusterData.features && clusterData.features.length > 0) {
                        const clusterLayer = L.geoJSON(clusterData, {
                            style: (feature) => {
                                const typeColors = {
                                    step:    { color: '#c0392b', fill: '#e74c3c' },
                                    station: { color: '#1a6fa0', fill: '#3498db' },
                                    ouvrage: { color: '#7d3c98', fill: '#9b59b6' },
                                    rejet:   { color: '#d35400', fill: '#e67e22' }
                                };
                                if (feature.properties.type === 'bassin_urbain') {
                                    const tc = typeColors[feature.properties.exutoire_type]
                                            || { color: '#27ae60', fill: '#2ecc71' };
                                    return {
                                        color:       tc.color,
                                        fillColor:   tc.fill,
                                        fillOpacity: 0.18,
                                        weight:      3,
                                        opacity:     0.95,
                                        dashArray:   '8, 5'
                                    };
                                }
                                // Tronçons (LineString) : couleur issue de la classification
                                return {
                                    color:   feature.properties.couleur || '#3498db',
                                    weight:  2.5,
                                    opacity: 0.75
                                };
                            },
                            pointToLayer: (feature, latlng) => {
                                if (feature.properties.type === 'exutoire') {
                                    const typeColors = {
                                        step: '#e74c3c',
                                        station: '#3498db',
                                        ouvrage: '#9b59b6',
                                        rejet: '#e67e22'
                                    };
                                    const color = typeColors[feature.properties.exutoire_type] || '#27ae60';
                                    return L.circleMarker(latlng, {
                                        pane: 'nodesPane',
                                        radius: 10,
                                        fillColor: color,
                                        color: '#fff',
                                        weight: 3,
                                        opacity: 1,
                                        fillOpacity: 1
                                    });
                                }
                                return L.marker(latlng);
                            },
                            onEachFeature: (feature, layer) => {
                                if (feature.properties.type === 'bassin_urbain') {
                                    const cid = String(feature.properties.cluster_id);
                                    if (!window._bassinProperties) window._bassinProperties = {};
                                    window._bassinProperties[cid] = feature.properties;
                                    if (feature.properties.nom) {
                                        window._bassinProperties[String(feature.properties.nom)] = feature.properties;
                                    }
                                    if (!window._bassinNoms) window._bassinNoms = {};
                                    window._bassinNoms[cid] = feature.properties.nom || ('Bassin ' + cid);
                                    if (feature.properties.nom) {
                                        window._bassinNoms[String(feature.properties.nom)] = feature.properties.nom;
                                    }

                                    const tipHtml = window.genererTooltipBassinVersantHtml(feature.properties);
                                    layer.bindTooltip(tipHtml, {
                                        sticky: true,
                                        direction: 'left',
                                        offset: [-15, 0],
                                        opacity: 0.98,
                                        className: 'sim-bassin-tooltip'
                                    });
                                    layer.bindPopup(tipHtml);

                                    layer.on('click', function(e) {
                                        L.DomEvent.stopPropagation(e);
                                        const cid = feature.properties.cluster_id;
                                        highlightCluster(cid, clusterLayer);
                                        // Sync dropdown
                                        const sel = document.getElementById('bassin-select');
                                        if (sel) sel.value = String(cid);
                                        afficherInfoBassin(cid);
                                        const bnds = (layer.getBounds && typeof layer.getBounds === 'function') ? layer.getBounds() : null;
                                        zoomerSurBassin(cid, clusterLayer, bnds);
                                    });

                                    layer.on('mouseover', function() {
                                        const fCid = String(feature.properties.cluster_id);
                                        if (_selectedClusterId !== null && fCid !== _selectedClusterId) {
                                            this.setStyle({ fillOpacity: 0.22, weight: 1.8 });
                                        } else {
                                            this.setStyle({ fillOpacity: 0.55, weight: 3.5 });
                                        }
                                    });
                                    layer.on('mouseout', function() {
                                        const fCid = String(feature.properties.cluster_id);
                                        const bColor = feature.properties.couleur || '#38bdf8';
                                        if (_selectedClusterId === null) {
                                            this.setStyle({ fillOpacity: 0.18, weight: 1.8, color: bColor, fillColor: bColor, dashArray: '5, 4' });
                                        } else if (fCid === _selectedClusterId) {
                                            this.setStyle({ fillOpacity: 0.45, weight: 3.5, color: '#ffffff', fillColor: bColor, dashArray: null });
                                        } else {
                                            this.setStyle({ fillOpacity: 0.04, weight: 0.8, color: '#64748b', fillColor: '#334155', dashArray: '4, 4' });
                                        }
                                    });
                                } else if (feature.properties.type === 'exutoire') {
                                    const p = feature.properties;
                                    const typLabels = {
                                        step: '🔴 Station d\'Épuration (STEP)',
                                        station: '🔵 Station de relevage / pompage',
                                        ouvrage: '🟣 Ouvrage spécial',
                                        rejet: '🟠 Rejet naturel (Oued)'
                                    };
                                    const typLabel = typLabels[p.exutoire_type] || (p.libelle_type || '⚪ Exutoire');
                                    const tipHtml = `
                                        <div style="font-family: inherit; font-size: 12px; min-width: 210px; line-height: 1.45;">
                                            <div style="font-weight: 800; color: #38bdf8; font-size: 13px; border-bottom: 1px solid rgba(0,0,0,0.1); padding-bottom: 3px; margin-bottom: 5px;">
                                                <i class="fas fa-sign-out-alt me-1"></i> ${p.nom || 'Exutoire'}
                                            </div>
                                            <div><b>Catégorie :</b> ${typLabel}</div>
                                            <div><b>Bassin rattaché :</b> Bassin N° ${p.cluster_id || '?'}</div>
                                            ${p.h_seuil ? `<div><b>Seuil $H_s$ :</b> <span style="color:#d97706; font-weight:700;">${p.h_seuil} m</span></div>` : ''}
                                            ${p.milieu_rec ? `<div><b>Milieu récepteur :</b> ${p.milieu_rec}</div>` : ''}
                                        </div>
                                    `;
                                    layer.bindTooltip(tipHtml, {
                                        sticky: true,
                                        direction: 'left',
                                        offset: [-15, 0],
                                        opacity: 0.98
                                    });
                                    layer.bindPopup(tipHtml);
                                    layer.on('click', function(e) {
                                        L.DomEvent.stopPropagation(e);
                                        const cid = p.cluster_id;
                                        if (cid !== null && cid !== undefined) {
                                            highlightCluster(cid, clusterLayer);
                                            const sel = document.getElementById('bassin-select');
                                            if (sel) sel.value = String(cid);
                                            afficherInfoBassin(cid);
                                            zoomerSurBassin(cid, clusterLayer);
                                        }
                                    });
                                } else if (feature.geometry && (feature.geometry.type === 'LineString' || feature.geometry.type === 'MultiLineString')) {
                                    const p = feature.properties;
                                    layer.bindTooltip(
                                        `<b>Conduite ${p.conduit_id || ''}</b><br>` +
                                        `📏 ${p.longueur ? p.longueur.toFixed(1) + ' m' : 'N/A'} &nbsp;|&nbsp; ` +
                                        `⌀ ${p.diametre || 'N/A'} mm<br>` +
                                        `Matériau: ${p.materiau || 'N/A'}<br>` +
                                        `Bassin n° ${p.cluster_id || '?'}`,
                                        { sticky: true }
                                    );
                                    layer.on('click', function(e) {
                                        L.DomEvent.stopPropagation(e);
                                        const cid = p.cluster_id;
                                        if (cid !== null && cid !== undefined) {
                                            highlightCluster(cid, clusterLayer);
                                            const sel = document.getElementById('bassin-select');
                                            if (sel) sel.value = String(cid);
                                            afficherInfoBassin(cid);
                                            zoomerSurBassin(cid, clusterLayer);
                                        }
                                    });
                                }
                            }
                        });

                        // Réinitialiser les couches d'affichage
                        couches.bassins.clearLayers();
                        clusterCouche.clearLayers();
                        couches.orphelins.clearLayers();

                        // Séparer les bassins des tronçons pour la gestion des couches (Bassins Versants prioritaires sur Voronoï)
                        clusterLayer.eachLayer(layer => {
                            if (layer.feature && layer.feature.properties && layer.feature.properties.type === 'bassin_urbain') {
                                layer.options.pane = 'bassinsPane';
                                layer.addTo(couches.bassins);
                            } else {
                                layer.options.pane = 'pipesPane';
                                layer.addTo(clusterCouche);
                            }
                        });

                        // S'assurer que les couches sont effectivement attachées et visibles sur la carte
                        if (!carte.hasLayer(couches.bassins)) couches.bassins.addTo(carte);
                        if (!carte.hasLayer(clusterCouche)) clusterCouche.addTo(carte);

                        // Alimenter la couche dédiée des tronçons et regards orphelins (déconnectés)
                        const orphelinsGeo = clusterData.orphelins_conduites;
                        const orphelinsRegGeo = clusterData.orphelins_regards;
                        const nbOrphelins = clusterData.nb_troncons_orphelins || (orphelinsGeo && orphelinsGeo.features ? orphelinsGeo.features.length : 0);
                        const nbRegOrphelins = clusterData.nb_regards_orphelins || (orphelinsRegGeo && orphelinsRegGeo.features ? orphelinsRegGeo.features.length : 0);
                        if (orphelinsGeo && orphelinsGeo.features && orphelinsGeo.features.length > 0) {
                            L.geoJSON(orphelinsGeo, {
                                style: {
                                    color: '#f59e0b',
                                    weight: 3.0,
                                    opacity: 0.9,
                                    dashArray: '5, 5'
                                },
                                onEachFeature: (feature, layer) => {
                                    const p = feature.properties || {};
                                    layer.bindTooltip(
                                        `<b>⚠️ Tronçon orphelin (déconnecté)</b><br>` +
                                        `ID: ${p.conduit_id || 'N/A'}<br>` +
                                        `📏 ${p.longueur ? p.longueur.toFixed(1) + ' m' : 'N/A'} &nbsp;|&nbsp; ⌀ ${p.diametre || 'N/A'} mm<br>` +
                                        `Matériau: ${p.materiau || 'N/A'}<br>` +
                                        `<em>Non raccordé hydrauliquement au réseau principal</em>`,
                                        { sticky: true }
                                    );
                                }
                            }).addTo(couches.orphelins);
                        }
                        if (orphelinsRegGeo && orphelinsRegGeo.features && orphelinsRegGeo.features.length > 0) {
                            L.geoJSON(orphelinsRegGeo, {
                                pointToLayer: (feature, latlng) => {
                                    return L.circleMarker(latlng, {
                                        radius: 3.5,
                                        fillColor: '#f59e0b',
                                        color: '#78350f',
                                        weight: 1,
                                        opacity: 0.9,
                                        fillOpacity: 0.85
                                    });
                                },
                                onEachFeature: (feature, layer) => {
                                    const p = feature.properties || {};
                                    layer.bindTooltip(
                                        `<b>⚠️ Regard orphelin (déconnecté)</b><br>` +
                                        `Code: ${p.code_regard || 'N/A'}<br>` +
                                        `Voie: ${p.nom_voie || 'N/A'}<br>` +
                                        `Commune: ${p.commune || 'N/A'}<br>` +
                                        `Distance au réseau: ${p.distance_rattachement_m || p.distance_reseau_m || 'N/A'} m`,
                                        { sticky: true }
                                    );
                                }
                            }).addTo(couches.orphelins);
                        }
                        const badgeOrph = document.getElementById('badge-orphelins-count');
                        if (badgeOrph) badgeOrph.textContent = `(${nbOrphelins} tr. • ${nbRegOrphelins} reg.)`;

                        _activeClusterLayer = clusterLayer;
                        window._activeClusterLayer = clusterLayer;
                        
                        const nbBassins = clusterData.clusters_crees || clusterData.features.filter(f => f.properties && f.properties.type === 'bassin_urbain').length;
                        const nbTroncons = clusterData.troncons_connectes !== undefined ? clusterData.troncons_connectes : clusterData.features.filter(f => f.geometry && (f.geometry.type === 'LineString' || f.geometry.type === 'MultiLineString')).length;
                        
                        if (statusDiv) {
                            statusDiv.innerHTML = `
                                <div style="margin-top: 6px; padding: 6px 8px; background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 6px; font-size: 0.75rem;">
                                    <div style="color: #38bdf8; font-weight: 600; margin-bottom: 3px;"><i class="fas fa-check-circle me-1"></i> Partitionnement terminé</div>
                                    <div style="color: #f8fafc;"><b>${nbBassins}</b> bassins versants d'exutoires</div>
                                    <div style="color: #cbd5e1;"><b>${nbTroncons}</b> tronçons reliés aux exutoires</div>
                                    ${nbOrphelins > 0 ? `<div style="color: #f59e0b;"><b>${nbOrphelins}</b> tronçons & <b>${nbRegOrphelins}</b> regards orphelins (déconnectés)</div>` : ''}
                                </div>
                            `;
                        }
                        
                        // Construire le menu déroulant des bassins
                        peuplerDropdownBassins(clusterData, clusterLayer);
                        
                        // S'assurer que rien n'est grisé au départ
                        highlightCluster(null, clusterLayer);
                        
                        // Activer la case à cocher des bassins
                        const chkBassins = document.getElementById('f-bassins');
                        const lblBassins = document.getElementById('label-bassins');
                        if (chkBassins) {
                            chkBassins.disabled = false;
                            chkBassins.checked = true;
                        }
                        if (lblBassins) {
                            lblBassins.style.color = 'inherit';
                            lblBassins.style.fontWeight = 'bold';
                        }

                        if (rezoomer && clusterLayer.getBounds && clusterLayer.getBounds().isValid()) {
                            carte.fitBounds(clusterLayer.getBounds(), { padding: [50, 50] });
                        }

                        // Exécuter tous les callbacks en attente
                        const callbacks = (window._partitioningCallbacks || []).slice();
                        window._partitioningCallbacks = [];
                        callbacks.forEach(cb => {
                            try { cb(clusterData); } catch(errCb) { console.error('[clusters] Erreur callback:', errCb); }
                        });
                    } else {
                        if (statusDiv) statusDiv.textContent = 'Aucun bassin détecté';
                        window._partitioningCallbacks = [];
                    }
                })
                .catch(error => {
                    console.error('Erreur partitionnement bassins:', error);
                    if (statusDiv) statusDiv.textContent = 'Erreur lors de la détection des bassins';
                    window._partitioningCallbacks = [];
                })
                .finally(() => {
                    window._isPartitioningInProgress = false;
                    if (afficherOverlay) {
                        montrerChargement(false);
                    }
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = '<i class="fas fa-sitemap me-1"></i> Partitionner bassins versants (Exutoires)';
                    }
                });
        };

        // Écouteur rétrocompatible sur le bouton de détection des clusters s'il est présent
        const detectBtnEl = document.getElementById('detect-cluster-btn');
        if (detectBtnEl) {
            detectBtnEl.addEventListener('click', function() {
                window.lancerPartitionnementBassins(null, null, true, true);
            });
        }
