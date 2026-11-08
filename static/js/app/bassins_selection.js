/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Synchronisation du bandeau de bassin, zoom proportionnel et dropdown
 * ================================================================================
 */

// ==========================================
        // SYNCHRONISATION INDICATEUR BASSIN / BASSINS EN COURS
        // ==========================================
        window.mettreAJourIndicateurBassin = function(clusterId, state = {}) {
            const topPill = document.getElementById('topbar-bassin-pill');
            const topIcon = document.getElementById('topbar-bassin-icon');
            const topText = document.getElementById('topbar-bassin-text');
            const topBadge = document.getElementById('topbar-bassin-badge');
            const topReset = document.getElementById('topbar-bassin-reset-btn');

            const cidStr = (clusterId !== null && clusterId !== undefined && clusterId !== '') ? String(clusterId) : null;
            const totalBassins = (window._clustersData && window._clustersData.clusters_crees) || (window._bassinNoms ? Object.keys(window._bassinNoms).length : 77) || 77;

            // État 1 : Simulation en cours
            if (state.status === 'simulating') {
                const nom = (window._bassinNoms && cidStr && window._bassinNoms[cidStr]) ? window._bassinNoms[cidStr] : `Bassin ${cidStr || ''}`;
                if (topIcon) topIcon.innerHTML = '<i class="fas fa-circle-notch fa-spin" style="color: #fbbf24;"></i>';
                if (topText) topText.innerHTML = `Simulation en cours : <span style="color: #fbbf24; font-weight: 700;">${nom}</span>`;
                if (topBadge) {
                    topBadge.innerText = 'CALCUL SWMM 5.2';
                    topBadge.style.background = 'rgba(245, 158, 11, 0.2)';
                    topBadge.style.color = '#f59e0b';
                }
                if (topReset) topReset.style.display = 'none';
                return;
            }

            // Détection automatique si le bassin possède une simulation active ou mise en cache
            let simActive = null;
            if (state.status === 'simulated' && (state.q_genere_m3s !== undefined || state.peak_flow !== undefined || state.q_exutoire_m3s !== undefined)) {
                simActive = state;
            } else if (cidStr) {
                const lastSim = window._dernierResultatSimulation;
                if (lastSim && lastSim.meta) {
                    const mId = String(lastSim.meta.cluster_id !== undefined && lastSim.meta.cluster_id !== null ? lastSim.meta.cluster_id : '');
                    const mNom = String(lastSim.meta.bassin_nom || lastSim.meta.cluster_nom || '');
                    if (mId === cidStr || mNom === cidStr || (window._bassinNoms && (window._bassinNoms[cidStr] === mNom || window._bassinNoms[cidStr] === mId))) {
                        simActive = lastSim;
                    }
                }
                if (!simActive && window._simulationsCache) {
                    simActive = window._simulationsCache[cidStr];
                    if (!simActive && window._bassinNoms && window._bassinNoms[cidStr]) {
                        simActive = window._simulationsCache[window._bassinNoms[cidStr]];
                    }
                }
            }

            // État 2 : Simulation terminée avec succès (Affichage des métriques hydrauliques complètes)
            if (simActive) {
                const kp = simActive.kpis || simActive;
                const m = simActive.meta || {};
                const nom = m.cluster_nom || (window._bassinNoms && cidStr && window._bassinNoms[cidStr]) || `Bassin ${cidStr || ''}`;

                const qExutoire = (kp.q_exutoire_m3s !== undefined) ? parseFloat(kp.q_exutoire_m3s) : (kp.peak_flow ? parseFloat(kp.peak_flow) : (kp.peak_outflow_m3s ? parseFloat(kp.peak_outflow_m3s) : 0.0));
                const qDerive = (kp.q_derive_m3s !== undefined) ? parseFloat(kp.q_derive_m3s) : (kp.q_deleste_ls ? (parseFloat(kp.q_deleste_ls) / 1000.0) : (kp.q_deleste_m3s ? parseFloat(kp.q_deleste_m3s) : 0.0));
                const qGenere = (kp.q_genere_m3s !== undefined) ? parseFloat(kp.q_genere_m3s) : (qExutoire + qDerive);
                const nbRacc = parseInt(kp.nb_ouvrages_raccordes || 0, 10);
                const tauxDerive = (kp.taux_derive_pct !== undefined) ? parseFloat(kp.taux_derive_pct) : (qGenere > 0 ? ((qDerive / qGenere) * 100.0) : 0.0);
                const tauxExutoire = (kp.taux_exutoire_pct !== undefined) ? parseFloat(kp.taux_exutoire_pct) : Math.max(0, 100.0 - tauxDerive);

                const qGenereStr = window.formaterNombre(qGenere, 3);
                const qExutoireStr = window.formaterNombre(qExutoire, 3);
                const qDeriveStr = window.formaterNombre(qDerive, 3);
                const tauxDeriveStr = window.formaterNombre(tauxDerive, 1);
                const tauxExutoireStr = window.formaterNombre(tauxExutoire, 1);

                if (topIcon) topIcon.innerHTML = '<i class="fas fa-check-circle" style="color: #34d399;"></i>';
                if (topText) topText.innerHTML = `Bassin simulé : <span style="color: #34d399; font-weight: 700;">${nom}</span>`;
                if (topBadge) {
                    topBadge.innerText = qDerive > 0 ? `Soulagement : ${tauxDeriveStr}% (${qDeriveStr} m³/s)` : `Soulagement : 0,0% (${qGenereStr} m³/s)`;
                    topBadge.style.background = qDerive > 0 ? 'rgba(6, 182, 212, 0.2)' : 'rgba(16, 185, 129, 0.2)';
                    topBadge.style.color = qDerive > 0 ? '#06b6d4' : '#34d399';
                }
                if (topReset) topReset.style.display = 'inline-block';
                return;
            }

            // État 3 : Aucun bassin individuel sélectionné (Mode Réseau Global)
            if (!cidStr) {
                if (topIcon) topIcon.innerHTML = '<i class="fas fa-network-wired" style="color: #38bdf8;"></i>';
                if (topText) topText.innerHTML = `Bassins en cours : <span style="color: #38bdf8; font-weight: 700;">Tous les bassins</span>`;
                if (topBadge) {
                    topBadge.innerText = `${totalBassins} BV`;
                    topBadge.style.background = 'rgba(56, 189, 248, 0.15)';
                    topBadge.style.color = '#38bdf8';
                }
                if (topReset) topReset.style.display = 'none';
                return;
            }

            // État 4 : Un bassin individuel est sélectionné (Extraction robuste des métadonnées)
            let nom = (window._bassinNoms && window._bassinNoms[cidStr]) ? window._bassinNoms[cidStr] : `Bassin ${cidStr}`;
            let surfHa = '';
            let nbRegards = '';
            let nbConduites = '';
            let longStr = '';
            let bColor = '#38bdf8';

            // 1. Recherche prioritaire dans le dictionnaire direct indexé
            let p = window._bassinProperties ? window._bassinProperties[cidStr] : null;
            if (!p && window._bassinProperties && window._bassinNoms && window._bassinNoms[cidStr]) {
                p = window._bassinProperties[window._bassinNoms[cidStr]];
            }

            // 2. Recherche de secours dans les couches GeoJSON
            if (!p && couches && couches.bassins) {
                couches.bassins.eachLayer(l => {
                    const f = l.feature;
                    if (f && f.properties && f.properties.type === 'bassin_urbain') {
                        if (String(f.properties.cluster_id) === cidStr || String(f.properties.nom) === cidStr) {
                            p = f.properties;
                        }
                    }
                });
            }
            if (!p && window._activeClusterLayer) {
                window._activeClusterLayer.eachLayer(l => {
                    const f = l.feature;
                    if (f && f.properties && f.properties.type === 'bassin_urbain') {
                        if (String(f.properties.cluster_id) === cidStr || String(f.properties.nom) === cidStr) {
                            p = f.properties;
                        }
                    }
                });
            }
            if (!p && window._clustersData && Array.isArray(window._clustersData.features)) {
                const match = window._clustersData.features.find(f => f.properties && f.properties.type === 'bassin_urbain' && (String(f.properties.cluster_id) === cidStr || String(f.properties.nom) === cidStr));
                if (match) p = match.properties;
            }

            if (p) {
                if (p.nom) nom = p.nom;
                if (p.surface_ha !== undefined && p.surface_ha !== null) surfHa = `${Number(p.surface_ha).toFixed(2)} ha`;
                if (p.nb_regards !== undefined && p.nb_regards !== null) nbRegards = `${p.nb_regards} reg.`;
                if (p.nb_conduites !== undefined) nbConduites = `${p.nb_conduites} cond.`;
                else if (p.nb_troncons !== undefined) nbConduites = `${p.nb_troncons} cond.`;
                if (p.longueur_totale_m) longStr = `(${Math.round(p.longueur_totale_m)} m)`;
                if (p.couleur) bColor = p.couleur;
            }

            if (topIcon) topIcon.innerHTML = `<i class="fas fa-draw-polygon" style="color: ${bColor};"></i>`;
            if (topText) topText.innerHTML = `Bassin en cours : <span style="color: #f8fafc; font-weight: 700;">${nom}</span>`;
            if (topBadge) {
                topBadge.innerText = surfHa || (nbRegards ? `${nbRegards} • ${nbConduites}` : `ID ${cidStr}`);
                topBadge.style.background = 'rgba(56, 189, 248, 0.15)';
                topBadge.style.color = '#38bdf8';
            }
            if (topReset) topReset.style.display = 'inline-block';
        };

        // GESTION AUTOMATIQUE DE L'AFFICHAGE DE SIMULATION PAR BASSIN
        // Garantit la cohérence stricte : n'affiche jamais la simulation d'un autre bassin
        window.gererAffichageSimulationPourBassin = function(clusterId) {
            const leg = document.getElementById('sim-floating-legend');
            const legTitle = document.querySelector('#sim-floating-legend span');

            if (!clusterId) {
                // Mode Réseau Global : nettoyer l'affichage des résultats SWMM
                if (typeof reinitialiserAffichageSimulation === 'function') {
                    reinitialiserAffichageSimulation();
                }
                if (leg) {
                    leg.classList.remove('active-legend');
                    leg.style.display = 'none';
                }
                if (legTitle) legTitle.innerHTML = `<i class="fas fa-layer-group me-1"></i> Légende SWMM 5.2`;
                return;
            }

            const cidStr = String(clusterId);
            const nomBassin = (window._bassinNoms && window._bassinNoms[cidStr]) || cidStr;

            // 1. Vérifier si la simulation actuellement affichée correspond déjà à ce bassin
            if (window._dernierResultatSimulation && window._dernierResultatSimulation.meta) {
                const m = window._dernierResultatSimulation.meta;
                const mCid = String(m.cluster_id !== undefined && m.cluster_id !== null ? m.cluster_id : '');
                const mNom = String(m.bassin_nom || m.cluster_nom || '');
                if (mCid === cidStr || mNom === cidStr || mNom === nomBassin || (nomBassin && mNom.toLowerCase() === nomBassin.toLowerCase())) {
                    if (leg) {
                        leg.classList.add('active-legend');
                        leg.style.display = 'block';
                    }
                    if (legTitle) {
                        legTitle.innerHTML = `<i class="fas fa-layer-group me-1"></i> SWMM 5.2 — ${mNom || nomBassin}`;
                    }
                    return;
                }
            }

            // 2. Nettoyage immédiat : ne jamais laisser flotter la simulation d'un autre bassin
            if (typeof reinitialiserAffichageSimulation === 'function') {
                reinitialiserAffichageSimulation();
            }
            if (leg) {
                leg.classList.remove('active-legend');
                leg.style.display = 'none';
            }

            // 3. Vérifier si ce bassin a une simulation dans le cache client
            let cached = null;
            if (window._simulationsCache) {
                cached = window._simulationsCache[cidStr] || (nomBassin && window._simulationsCache[nomBassin]);
            }

            if (cached && cached.status === 'success' && cached.conduit_results && Object.keys(cached.conduit_results).length > 0) {
                window._dernierResultatSimulation = cached;
                afficherResultatsSimulation(cached);
                if (leg) {
                    leg.classList.add('active-legend');
                    leg.style.display = 'block';
                }
                if (legTitle) {
                    const dispNom = (cached.meta && (cached.meta.cluster_nom || cached.meta.bassin_nom)) || nomBassin;
                    legTitle.innerHTML = `<i class="fas fa-layer-group me-1"></i> SWMM 5.2 — ${dispNom}`;
                }
                return;
            }

            // 3. Interroger le serveur pour charger la simulation enregistrée de ce bassin
            const token = localStorage.getItem('swmm_access_token');
            const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
            fetch('/api/v1/simulations/bassin/' + encodeURIComponent(cidStr), { headers, credentials: 'include' })
                .then(r => r.json())
                .then(d => {
                    // Vérifier que l'utilisateur est toujours sur ce bassin
                    if (_selectedClusterId !== cidStr) return;

                    if (d && d.status === 'success' && d.conduit_results && Object.keys(d.conduit_results).length > 0) {
                        if (!window._simulationsCache) window._simulationsCache = {};
                        window._simulationsCache[cidStr] = d;
                        if (nomBassin) window._simulationsCache[nomBassin] = d;
                        window._dernierResultatSimulation = d;
                        afficherResultatsSimulation(d);
                        if (leg) {
                            leg.classList.add('active-legend');
                            leg.style.display = 'block';
                        }
                        if (legTitle) {
                            const dispNom = (d.meta && (d.meta.cluster_nom || d.meta.bassin_nom)) || nomBassin;
                            legTitle.innerHTML = `<i class="fas fa-layer-group me-1"></i> SWMM 5.2 — ${dispNom}`;
                        }
                    } else {
                        // Aucun calcul sauvegardé pour ce bassin : nettoyer les résultats précédents
                        if (typeof reinitialiserAffichageSimulation === 'function') {
                            reinitialiserAffichageSimulation();
                        }
                        if (leg) {
                            leg.classList.remove('active-legend');
                            leg.style.display = 'none';
                        }
                        if (legTitle) legTitle.innerHTML = `<i class="fas fa-layer-group me-1"></i> Légende SWMM 5.2`;
                    }
                })
                .catch(err => {
                    console.warn("Vérification simulation bassin:", err);
                    if (_selectedClusterId === cidStr) {
                        if (typeof reinitialiserAffichageSimulation === 'function') {
                            reinitialiserAffichageSimulation();
                        }
                        if (leg) {
                            leg.classList.remove('active-legend');
                            leg.style.display = 'none';
                        }
                    }
                });
        };

        window.reinitialiserSelectionBassin = function(e) {
            if (e && e.stopPropagation) e.stopPropagation();
            _selectedClusterId = null;
            const sel = document.getElementById('bassin-select');
            if (sel) sel.value = '';
            const simSel = document.getElementById('sim-select-bassin');
            if (simSel) simSel.value = '';
            highlightCluster(null, window._activeClusterLayer || couches.bassins);
            afficherInfoBassin(null);
            if (window._activeClusterLayer && window._activeClusterLayer.getBounds && window._activeClusterLayer.getBounds().isValid()) {
                carte.fitBounds(window._activeClusterLayer.getBounds(), { padding: [50, 50] });
            }
            window.mettreAJourIndicateurBassin(null);
        };

        function highlightCluster(clusterId, geojsonLayer) {
            _selectedClusterId = (clusterId === null || clusterId === undefined || clusterId === '') ? null : String(clusterId);
            window.mettreAJourIndicateurBassin(_selectedClusterId);

            // Synchroniser le dropdown si l'appel vient du clic carte
            const sel = document.getElementById('bassin-select');
            if (sel && sel.value !== (_selectedClusterId || '')) {
                sel.value = _selectedClusterId || '';
            }
            afficherInfoBassin(_selectedClusterId);

            // Synchronisation intelligente et sécurisée de l'affichage de simulation
            if (typeof window.gererAffichageSimulationPourBassin === 'function') {
                window.gererAffichageSimulationPourBassin(_selectedClusterId);
            }

            geojsonLayer = geojsonLayer || window._activeClusterLayer || (typeof couches !== 'undefined' ? couches.bassins : null);
            if (!geojsonLayer) return;

            geojsonLayer.eachLayer(layer => {
                const feature = layer.feature;
                if (!feature) return;

                // Cas 1 : Tronçons (LineString / MultiLineString)
                if (feature.geometry && (feature.geometry.type === 'LineString' || feature.geometry.type === 'MultiLineString')) {
                    const fCid = feature.properties ? String(feature.properties.cluster_id) : '';
                    const cColor = feature.properties ? feature.properties.couleur || '#38bdf8' : '#38bdf8';

                    if (_selectedClusterId === null) {
                        // Vue globale : toutes les conduites ont la couleur de leur bassin
                        layer.setStyle({ color: cColor, weight: 2.4, opacity: 0.85 });
                    } else if (fCid === _selectedClusterId) {
                        // Conduite du bassin sélectionné : mise en valeur éclatante
                        layer.setStyle({ color: cColor, weight: 4.5, opacity: 1.0 });
                        try { layer.bringToFront(); } catch(e) {}
                    } else {
                        // Autre bassin : grisé et discret
                        layer.setStyle({ color: '#475569', weight: 1.2, opacity: 0.18 });
                    }
                }
                // Cas 2 : Polygones de Bassins Versants
                else if (feature.properties && feature.properties.type === 'bassin_urbain') {
                    const fCid = feature.properties ? String(feature.properties.cluster_id) : '';
                    const bColor = feature.properties ? feature.properties.couleur || '#38bdf8' : '#38bdf8';

                    if (_selectedClusterId === null) {
                        // Vue globale : tous les bassins versants colorés
                        layer.setStyle({
                            color: bColor,
                            fillColor: bColor,
                            fillOpacity: 0.18,
                            weight: 1.8,
                            dashArray: '5, 4'
                        });
                    } else if (fCid === _selectedClusterId) {
                        // Bassin sélectionné : actif avec bordure nette et couleur soutenue
                        layer.setStyle({
                            color: '#ffffff',
                            fillColor: bColor,
                            fillOpacity: 0.45,
                            weight: 3.5,
                            dashArray: null
                        });
                        try { layer.bringToFront(); } catch(e) {}
                    } else {
                        // Les 78 autres bassins versants : grisés
                        layer.setStyle({
                            color: '#64748b',
                            fillColor: '#334155',
                            fillOpacity: 0.04,
                            weight: 0.8,
                            dashArray: '4, 4'
                        });
                    }
                }
            });

            // Harmoniser également la couche des sous-bassins Voronoï avec la sélection
            if (typeof couches !== 'undefined' && couches.subcatchments && typeof couches.subcatchments.eachLayer === 'function') {
                couches.subcatchments.eachLayer(sbLayer => {
                    const feat = sbLayer.feature;
                    if (!feat || !feat.properties) return;
                    const sbBassinId = (feat.properties.id_bassin !== undefined && feat.properties.id_bassin !== null) ? String(feat.properties.id_bassin) : null;
                    const isOrph = feat.properties.is_orphelin === 1 || feat.properties.is_orphelin === true || !sbBassinId;
                    
                    if (_selectedClusterId === null) {
                        // Vue globale : style standard
                        if (isOrph) {
                            sbLayer.setStyle({ color: '#f59e0b', fillColor: '#f59e0b', fillOpacity: 0.15, weight: 1.0, dashArray: '3, 3' });
                        } else {
                            sbLayer.setStyle({ color: '#059669', fillColor: '#10b981', fillOpacity: 0.18, weight: 1.5, dashArray: '4, 4' });
                        }
                    } else if (sbBassinId === _selectedClusterId) {
                        // Sous-bassin du bassin sélectionné : mise en valeur en arrière-plan du bassin versant
                        sbLayer.setStyle({ color: '#10b981', fillColor: '#10b981', fillOpacity: 0.38, weight: 2.2, dashArray: null });
                    } else {
                        // Autre sous-bassin : estompé
                        sbLayer.setStyle({ color: '#64748b', fillColor: '#334155', fillOpacity: 0.02, opacity: 0.12, weight: 0.5, dashArray: '4, 4' });
                    }
                });
            }
        }

        function peuplerDropdownBassins(geojsonData, clusterLayer) {
            const sel = document.getElementById('bassin-select');
            sel.innerHTML = '<option value="">-- Choisir un bassin versant --</option>';
            _bassinBounds = {};
            _bassinNoms = {};

            // Extraire les bassins (polygones) et construire leurs bounds
            const bassins = geojsonData.features.filter(f => f.properties && f.properties.type === 'bassin_urbain');

            // Séparation en deux listes selon la présence d'un réseau collecteur amont
            const collecteurs = [];
            const isoles = [];

            bassins.forEach(f => {
                const cid = f.properties.cluster_id;
                const nom = f.properties.nom || `Bassin ${cid}`;
                _bassinNoms[cid] = nom;
                if (!window._bassinProperties) window._bassinProperties = {};
                window._bassinProperties[String(cid)] = f.properties;
                if (nom) {
                    window._bassinProperties[String(nom)] = f.properties;
                    _bassinNoms[String(nom)] = nom;
                }

                const nbReg = parseInt(f.properties.nb_regards || 0);
                const nbCond = parseInt(f.properties.nb_conduites || 0);
                const surf = parseFloat(f.properties.surface_ha || 0.0);

                // Un bassin appartient aux collecteurs s'il a au moins un regard ou conduite connectée ou surface > 0.45 ha
                if (nbReg > 0 || nbCond > 2 || surf > 0.45) {
                    collecteurs.push(f);
                } else {
                    isoles.push(f);
                }
            });

            // Tri alphabétique strict des deux listes (par nom)
            const triAlphabetique = (a, b) => {
                const nomA = (a.properties.nom || '').trim().toLowerCase();
                const nomB = (b.properties.nom || '').trim().toLowerCase();
                return nomA.localeCompare(nomB, 'fr', { sensitivity: 'base', numeric: true });
            };

            collecteurs.sort(triAlphabetique);
            isoles.sort(triAlphabetique);

            // Groupe 1 : Bassins versants collecteurs (réseau connecté)
            if (collecteurs.length > 0) {
                const grpCol = document.createElement('optgroup');
                grpCol.label = `── Bassins versants collecteurs (${collecteurs.length}) ──`;
                collecteurs.forEach(f => {
                    const cid = f.properties.cluster_id;
                    const nom = f.properties.nom || `Bassin ${cid}`;
                    const surf = f.properties.surface_ha !== undefined ? ` (${f.properties.surface_ha} ha)` : '';
                    const reg = (f.properties.nb_regards && f.properties.nb_regards > 0) ? ` • ${f.properties.nb_regards} reg.` : '';
                    const opt = document.createElement('option');
                    opt.value = cid;
                    opt.textContent = `${nom}${surf}${reg}`;
                    grpCol.appendChild(opt);
                });
                sel.appendChild(grpCol);
            }

            // Groupe 2 : Exutoires & Ouvrages ponctuels isolés (sans réseau amont)
            if (isoles.length > 0) {
                const grpIso = document.createElement('optgroup');
                grpIso.label = `── Exutoires et ouvrages ponctuels sans réseau (${isoles.length}) ──`;
                isoles.forEach(f => {
                    const cid = f.properties.cluster_id;
                    const nom = f.properties.nom || `Bassin ${cid}`;
                    const surf = f.properties.surface_ha !== undefined ? ` (${f.properties.surface_ha} ha)` : '';
                    const opt = document.createElement('option');
                    opt.value = cid;
                    opt.textContent = `${nom}${surf} (isolé)`;
                    grpIso.appendChild(opt);
                });
                sel.appendChild(grpIso);
            }

            // Calculer les bounds de chaque bassin depuis le layer Leaflet (si disponible)
            if (clusterLayer && typeof clusterLayer.eachLayer === 'function') {
                clusterLayer.eachLayer(layer => {
                    const feature = layer.feature;
                    if (!feature || feature.properties.type !== 'bassin_urbain') return;
                    const cid = feature.properties.cluster_id;
                    try {
                        const b = (typeof layer.getBounds === 'function') ? layer.getBounds() : null;
                        if (b && typeof b.isValid === 'function' && b.isValid()) {
                            _bassinBounds[cid] = b;
                            _bassinBounds[String(cid)] = b;
                            if (!isNaN(parseInt(cid))) _bassinBounds[parseInt(cid)] = b;
                        }
                    } catch(e) {}
                });
            }
            window._bassinBounds = _bassinBounds;
            window._bassinNoms = _bassinNoms;

            // Mettre à jour dynamiquement le badge avec le nombre exact de bassins détectés
            const totalBassins = bassins.length;
            const badge = document.getElementById('badge-subcatchments-count');
            if (badge && totalBassins > 0) {
                const curText = badge.innerText || '';
                const parts = curText.split('•');
                const sbPart = parts.length > 1 ? parts[parts.length - 1].trim() : (curText.includes('SB') ? curText : '');
                badge.innerText = `${totalBassins} BV${sbPart ? ' • ' + sbPart : ''}`;
            }

            // Afficher la section
            document.getElementById('bassin-section').style.display = 'block';

            // Écouteur du dropdown unique (onchange direct pour éviter les doublons d'écouteurs)
            sel.onchange = function() {
                const cid = this.value;
                
                // Activer le bouton supprimer SI c'est un bassin manuel
                const btnDelete = document.getElementById('btn-delete-bassin');
                if (btnDelete) {
                    if (cid && String(cid).startsWith('M_')) {
                        btnDelete.disabled = false;
                        btnDelete.style.color = '#e74c3c';
                    } else {
                        btnDelete.disabled = true;
                        btnDelete.style.color = '';
                    }
                }

                if (!cid) {
                    highlightCluster(null, clusterLayer);
                    afficherInfoBassin(null);
                    return;
                }
                
                const finalCid = cid.startsWith('M_') ? cid : parseInt(cid);
                highlightCluster(finalCid, clusterLayer);
                afficherInfoBassin(finalCid);
                zoomerSurBassin(finalCid, clusterLayer);
            };
        }
