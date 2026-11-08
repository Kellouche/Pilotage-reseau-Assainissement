/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Réinitialisation de la simulation, masquage des couches et restitution au chargement
 * ================================================================================
 */

window.reinitialiserAffichageSimulation = function() {
            if (couches.res_conduites) couches.res_conduites.clearLayers();
            if (couches.res_regards) couches.res_regards.clearLayers();
            if (couches.sens_ecoulement) couches.sens_ecoulement.clearLayers();
            if (window._coucheRaccordementsOrphelins) {
                window._coucheRaccordementsOrphelins.clearLayers();
                if (window.carte && window.carte.hasLayer(window._coucheRaccordementsOrphelins)) {
                    window.carte.removeLayer(window._coucheRaccordementsOrphelins);
                }
            }

            // Rétablir la visibilité normale de la couche physique des conduites
            if (!carte.hasLayer(couches.conduites)) {
                couches.conduites.addTo(carte);
            }
            const elCond = document.getElementById('f-conduites');
            if (elCond) elCond.checked = true;

            // Rétablir la visibilité normale de la couche physique des regards
            if (!carte.hasLayer(couches.regards)) {
                couches.regards.addTo(carte);
            }
            const elReg = document.getElementById('f-regards');
            if (elReg) elReg.checked = true;

            // Rétablir et maintenir toujours cochés les rejets et la STEP
            if (couches.rejets && !carte.hasLayer(couches.rejets)) {
                couches.rejets.addTo(carte);
            }
            const elRej = document.getElementById('f-rejets');
            if (elRej) elRej.checked = true;

            if (couches.step && !carte.hasLayer(couches.step)) {
                couches.step.addTo(carte);
            }
            const elStep = document.getElementById('f-step');
            if (elStep) elStep.checked = true;

            // Rétablir la couche de clusters sectorisés
            if (typeof clusterCouche !== 'undefined' && clusterCouche && !carte.hasLayer(clusterCouche)) {
                clusterCouche.addTo(carte);
            }

            // Rétablir l'opacité normale des lignes de cluster
            if (window._activeClusterLayer) {
                window._activeClusterLayer.eachLayer(l => {
                    if (l instanceof L.Polyline && !(l instanceof L.Polygon)) {
                        l.setStyle({ opacity: 0.85 });
                    }
                });
            }

            const elSens = document.getElementById('f-sens-ecoulement');
            if (elSens) elSens.checked = false;

            // Masquer la légende flottante de simulation
            const leg = document.getElementById('sim-floating-legend');
            if (leg) {
                leg.classList.remove('active-legend');
                leg.style.display = 'none';
            }

            // Masquer la carte de résultats et réinitialiser les KPIs
            const resCard = document.getElementById('sim-results-card');
            if (resCard) resCard.style.display = 'none';

            const statusMsg = document.getElementById('sim-status-message');
            if (statusMsg) statusMsg.style.display = 'none';

            const kpiContinuity = document.getElementById('kpi-continuity');
            if (kpiContinuity) kpiContinuity.innerText = '--';
            const kpiPeak = document.getElementById('kpi-peak-outflow');
            if (kpiPeak) kpiPeak.innerText = '--';
            const kpiFlooded = document.getElementById('kpi-flooded-count');
            if (kpiFlooded) kpiFlooded.innerText = '--';
            const kpiSub = document.getElementById('kpi-subcatchments');
            if (kpiSub) kpiSub.innerText = '--';

            // Rétablir les statistiques globales du Panneau d'Ingénierie
            if (window._rawNetworkData && window._rawNetworkData.compteurs) {
                const c = window._rawNetworkData.compteurs;
                const pName = window._rawNetworkData.project_name || 'Réseau Actif';
                const miniStatsEl = document.getElementById('mini-stats');
                if (miniStatsEl) {
                    miniStatsEl.innerHTML = `<span style="color: #38bdf8; font-weight: 700;">Zone : ${pName}</span> | Conduites: <b>${c.conduites || 0}</b> | Regards: <b>${c.regards || 0}</b>`;
                    miniStatsEl.style.background = 'rgba(255,255,255,0.06)';
                    miniStatsEl.style.border = 'none';
                    miniStatsEl.style.color = '#94a3b8';
                }
            }

            // Rétablir le badge et la légende des sous-bassins
            const badgeSb = document.getElementById('badge-subcatchments-count');
            if (badgeSb && window._rawNetworkData && window._rawNetworkData.compteurs) {
                const nbBv = (window._clustersData && (window._clustersData.clusters_crees || (window._clustersData.resultats && window._clustersData.resultats.length))) || null;
                const bvStr = nbBv ? `${nbBv} BV &bull; ` : '';
                badgeSb.innerHTML = `${bvStr}${window._rawNetworkData.compteurs.regards || 0} SB`;
                badgeSb.style.background = '';
                badgeSb.style.color = '';
            }

            // Rétablir le style uniforme et infobulles initiales des sous-bassins Voronoï
            if (couches.subcatchments) {
                couches.subcatchments.eachLayer(layer => {
                    layer.setStyle({
                        color: '#059669',
                        fillColor: '#10b981',
                        fillOpacity: 0.18,
                        weight: 1.5,
                        opacity: 0.85
                    });
                    if (layer._originalTooltip) {
                        layer.unbindTooltip();
                        layer.bindTooltip(layer._originalTooltip, { sticky: true, opacity: 0.95 });
                        layer._originalTooltip = null;
                    }
                });
            }

            // Rétablir les infobulles initiales des bassins
            const restoreBassinTooltip = (layer) => {
                layer._isSimulatedBassin = false;
                layer.off('mouseover.simBassin mouseout.simBassin');
                const f = layer.feature;
                if (f && f.properties && f.properties.type === 'bassin_urbain') {
                    const baseTip = window.genererTooltipBassinVersantHtml ? window.genererTooltipBassinVersantHtml(f.properties, null) : layer._originalTooltip;
                    if (baseTip) {
                        layer.unbindTooltip();
                        layer.bindTooltip(baseTip, {
                            sticky: true,
                            direction: 'left',
                            offset: [-15, 0],
                            opacity: 0.98,
                            className: 'sim-bassin-tooltip'
                        });
                        layer.bindPopup(baseTip);
                    }
                    layer._originalTooltip = null;
                } else if (layer._originalTooltip) {
                    layer.unbindTooltip();
                    layer.bindTooltip(layer._originalTooltip, { sticky: true });
                    layer._originalTooltip = null;
                }
            };
            if (couches.bassins) couches.bassins.eachLayer(restoreBassinTooltip);
            if (window._activeClusterLayer) window._activeClusterLayer.eachLayer(restoreBassinTooltip);

            // Rétablir le titre de la légende flottante
            const legTitle = document.querySelector('#sim-floating-legend span');
            if (legTitle) legTitle.innerHTML = `<i class="fas fa-layer-group me-1"></i> Légende SWMM 5.2`;

            window._dernierResultatSimulation = null;
            window._lastSimBounds = null;
            if (typeof activerActionsSimulation === 'function') {
                activerActionsSimulation(false);
            }
        };

        // ==========================================
        // POINT 3 : PERSISTANCE & RE-AFFICHAGE SANS RECALCUL
        // ==========================================
        window.chargerDerniereSimulation = function() {
            const token = localStorage.getItem('swmm_access_token');
            const headers = token ? { 'Authorization': `Bearer ${token}` } : {};

            fetch('/api/v1/simulations/latest', { headers, credentials: 'include' })
                .then(r => r.json())
                .then(data => {
                    if (data && data.status === 'success' && data.conduit_results && Object.keys(data.conduit_results).length > 0) {
                        window._dernierResultatSimulation = data;
                        if (!window._simulationsCache) window._simulationsCache = {};
                        if (data.meta && data.meta.cluster_id) {
                            window._simulationsCache[String(data.meta.cluster_id)] = data;
                        }
                        if (data.meta && data.meta.bassin_nom) {
                            window._simulationsCache[String(data.meta.bassin_nom)] = data;
                        }
                        if (data.meta && data.meta.cluster_nom) {
                            window._simulationsCache[String(data.meta.cluster_nom)] = data;
                        }
                        if (typeof activerActionsSimulation === 'function') {
                            activerActionsSimulation(true);
                        }
                        if (data.meta && data.meta.cluster_id && typeof window.mettreAJourIndicateurBassin === 'function') {
                            window.mettreAJourIndicateurBassin(data.meta.cluster_id, {
                                status: 'simulated',
                                ...(data.kpis || {})
                            });
                        }
                    } else {
                        reinitialiserAffichageSimulation();
                    }
                })
                .catch(e => {
                    console.warn('Simulation précédente indisponible:', e);
                    reinitialiserAffichageSimulation();
                });
        };

        // ==========================================
        // MODALE DE SIMULATION & DÉCLENCHEMENT SWMM
        // ==========================================
        window.ouvrirModalSimulation = function(forceOpen = false) {
            // Vérifier si des bassins sont disponibles ET effectivement dessinés sur la carte
            const mainBassinSel = document.getElementById('bassin-select');
            const simBassinSel = document.getElementById('sim-select-bassin');
            const hasOptions = (mainBassinSel && mainBassinSel.options.length > 1) || 
                               (simBassinSel && simBassinSel.options.length > 1);
            const hasLayersDrawn = (typeof couches !== 'undefined' && couches.bassins && couches.bassins.getLayers().length > 0) ||
                                  (window._activeClusterLayer && window._activeClusterLayer.getLayers && window._activeClusterLayer.getLayers().length > 0);

            const isSectorise = (forceOpen === true) || (hasOptions && hasLayersDrawn);

            if (!isSectorise) {
                if (window._isPartitioningInProgress) {
                    console.log("[Simulation] Partitionnement des bassins déjà en cours, attente du tracé...");
                    montrerChargement(true, 'Règle hydraulique : Partitionnement et tracé des bassins en cours...');
                    if (!window._partitioningCallbacks) window._partitioningCallbacks = [];
                    window._partitioningCallbacks.push(function() {
                        montrerChargement(false);
                        window.ouvrirModalSimulation(true);
                    });
                    return;
                }
                window.lancerPartitionnementBassins(function() {
                    window.ouvrirModalSimulation(true);
                }, 'Règle hydraulique : Partitionnement automatique des bassins versants...', true, false);
                return;
            }

            const m = document.getElementById('modal-simulation');
            if (m) {
                // Synchroniser les options de bassin depuis #bassin-select ou window._clustersData
                const simBassinSel = document.getElementById('sim-select-bassin');
                const mainBassinSel = document.getElementById('bassin-select');
                if (simBassinSel) {
                    if (mainBassinSel && mainBassinSel.options.length > 1) {
                        simBassinSel.innerHTML = mainBassinSel.innerHTML;
                        if (simBassinSel.options.length > 0) {
                            simBassinSel.options[0].textContent = '-- Sélectionnez un bassin versant sectorisé --';
                            simBassinSel.options[0].disabled = true;
                        }
                        if (_selectedClusterId) {
                            simBassinSel.value = _selectedClusterId;
                        } else if (simBassinSel.options.length > 1) {
                            simBassinSel.selectedIndex = 1;
                        }
                    } else if (window._clustersData && window._clustersData.resultats && window._clustersData.resultats.length > 0) {
                        simBassinSel.innerHTML = '<option value="" disabled selected>-- Sélectionnez un bassin versant sectorisé --</option>';
                        window._clustersData.resultats.forEach(res => {
                            const cl = res.cluster || {};
                            const cid = cl.id !== undefined ? cl.id : (res.cluster_id || '');
                            const nom = cl.nom || res.nom || `Bassin ${cid}`;
                            const surf = cl.surface_ha ? ` (${Number(cl.surface_ha).toFixed(1)} ha)` : '';
                            const newOpt = document.createElement('option');
                            newOpt.value = cid;
                            newOpt.textContent = `${nom}${surf}`;
                            simBassinSel.appendChild(newOpt);
                        });
                        if (_selectedClusterId) {
                            simBassinSel.value = _selectedClusterId;
                        } else if (simBassinSel.options.length > 1) {
                            simBassinSel.selectedIndex = 1;
                        }
                    } else if (window._bassinNoms && Object.keys(window._bassinNoms).length > 0) {
                        simBassinSel.innerHTML = '<option value="" disabled selected>-- Sélectionnez un bassin versant sectorisé --</option>';
                        Object.keys(window._bassinNoms).forEach(cid => {
                            const newOpt = document.createElement('option');
                            newOpt.value = cid;
                            newOpt.textContent = `${window._bassinNoms[cid]}`;
                            simBassinSel.appendChild(newOpt);
                        });
                        if (window._selectedClusterId) {
                            simBassinSel.value = window._selectedClusterId;
                        } else if (simBassinSel.options.length > 1) {
                            simBassinSel.selectedIndex = 1;
                        }
                    }
                    simBassinSel.onchange = function() {
                        if (this.value) {
                            _selectedClusterId = this.value;
                            if (mainBassinSel) mainBassinSel.value = this.value;
                            highlightCluster(this.value, window._activeClusterLayer || couches.bassins);
                            afficherInfoBassin(this.value);
                            actualiserAlerteOuvrageDeporte(this.value);
                            zoomerSurBassin(this.value, window._activeClusterLayer || couches.bassins);
                            if (typeof window.mettreAJourIndicateurBassin === 'function') {
                                window.mettreAJourIndicateurBassin(this.value);
                            }
                        }
                    };
                    actualiserAlerteOuvrageDeporte(simBassinSel.value);
                    if (simBassinSel.value) {
                        zoomerSurBassin(simBassinSel.value, window._activeClusterLayer || couches.bassins);
                    }

                    // Configuration du sélecteur d'occupation du sol et % imperv (Palier 1)
                    const typoSolSel = document.getElementById('sim-select-typologie-sol');
                    const impervInp = document.getElementById('sim-imperv-pct');
                    if (typoSolSel && impervInp) {
                        const typoMap = {
                            'centre_urbain_dense': 85,
                            'habitat_collectif': 75,
                            'habitat_mixte': 65,
                            'habitat_individuel': 50,
                            'zone_activites_indus': 80,
                            'periurbain_semi_rural': 35,
                            'espaces_verts_friches': 15
                        };
                        typoSolSel.onchange = function() {
                            if (typoMap[this.value] !== undefined) {
                                impervInp.value = typoMap[this.value];
                            }
                        };
                    }

                    // Initialiser le scénario et l'intensité pluviométrique par défaut
                    const scenSel = document.getElementById('sim-select-scenario');
                    const imaxInp = document.getElementById('sim-input-intensite-max');
                    if (scenSel && imaxInp && (!imaxInp.value || imaxInp.value === '')) {
                        if (typeof window.onChangementScenarioPluie === 'function') {
                            window.onChangementScenarioPluie(scenSel.value || 'pluie_decennale');
                        }
                    }
                }
                m.style.display = 'flex';
            }
        };
