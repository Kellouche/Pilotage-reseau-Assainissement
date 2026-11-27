/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-27
 * Date de modification : 2026-11-27
 * Objet : Affichage automatique de la simulation par bassin et selecteur (extrait de static/js/app/bassins_selection.js)
 * ================================================================================
 */

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
            //    (identité stable : cluster_id / exutoire / bassin_ref — jamais le nom)
            if (window._dernierResultatSimulation && _simCorrespondAuBassin(window._dernierResultatSimulation, cidStr)) {
                const m = window._dernierResultatSimulation.meta || {};
                const _rawMNom = String(m.bassin_nom || m.cluster_nom || '').trim();
                const mNom = (_rawMNom && !/^\d+$/.test(_rawMNom)) ? _rawMNom : (nomBassin || _rawMNom);
                if (leg) {
                    leg.classList.add('active-legend');
                    leg.style.display = 'block';
                }
                if (legTitle) {
                    legTitle.innerHTML = `<i class="fas fa-layer-group me-1"></i> SWMM 5.2 — ${mNom || nomBassin}`;
                }
                if (typeof window.actualiserLegendeDwf === 'function') {
                    window.actualiserLegendeDwf(window._dernierResultatSimulation);
                }
                return;
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
            //    (identité stable — la clé « nom » du cache est ambiguë entre
            //    bassins homonymes, on vérifie toujours meta avant d'accepter)
            let cached = null;
            if (window._simulationsCache) {
                const _direct = window._simulationsCache[cidStr] || (nomBassin && window._simulationsCache[nomBassin]);
                if (_direct && _simCorrespondAuBassin(_direct, cidStr)) {
                    cached = _direct;
                } else {
                    for (const _k of Object.keys(window._simulationsCache)) {
                        const _cand = window._simulationsCache[_k];
                        if (_cand && _cand.status === 'success' && _simCorrespondAuBassin(_cand, cidStr)) {
                            cached = _cand;
                            break;
                        }
                    }
                }
            }

            if (cached && cached.status === 'success' && cached.conduit_results && Object.keys(cached.conduit_results).length > 0) {
                window._dernierResultatSimulation = cached;
                afficherResultatsSimulation(cached);
                if (leg) {
                    leg.classList.add('active-legend');
                    leg.style.display = 'block';
                }
                if (legTitle) {
                    const _rawDisp = String((cached.meta && (cached.meta.cluster_nom || cached.meta.bassin_nom)) || '').trim();
                    const dispNom = (_rawDisp && !/^\d+$/.test(_rawDisp)) ? _rawDisp : (nomBassin || _rawDisp);
                    legTitle.innerHTML = `<i class="fas fa-layer-group me-1"></i> SWMM 5.2 — ${dispNom}`;
                }
                if (typeof window.actualiserLegendeDwf === 'function') {
                    window.actualiserLegendeDwf(cached);
                }
                if (typeof window.mettreAJourIndicateurBassin === 'function') {
                    window.mettreAJourIndicateurBassin(cidStr, cached);
                }
                return;
            }

            // 3. Interroger le serveur pour charger la simulation enregistrée de ce bassin
            if (window._simBassinEnChargement === cidStr) return; // Déjà en cours de requête pour ce bassin
            window._simBassinEnChargement = cidStr;

            const token = localStorage.getItem('swmm_access_token');
            const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
            fetch('/api/v1/simulations/bassin/' + encodeURIComponent(cidStr), { headers, credentials: 'include' })
                .then(r => r.json())
                .then(d => {
                    window._simBassinEnChargement = null;
                    // Vérifier que l'utilisateur est toujours sur ce bassin
                    if (_selectedClusterId !== cidStr) return;

                    if (d && d.status === 'success' && d.conduit_results && Object.keys(d.conduit_results).length > 0) {
                        if (!window._simulationsCache) window._simulationsCache = {};
                        window._simulationsCache[cidStr] = d;
                        if (nomBassin) window._simulationsCache[nomBassin] = d;
                        if (window._fiabiliteParBassin) window._fiabiliteParBassin[cidStr] = d;
                        window._dernierResultatSimulation = d;
                        afficherResultatsSimulation(d);
                        if (leg) {
                            leg.classList.add('active-legend');
                            leg.style.display = 'block';
                        }
                        if (legTitle) {
                            const _rawDisp = String((d.meta && (d.meta.cluster_nom || d.meta.bassin_nom)) || '').trim();
                            const dispNom = (_rawDisp && !/^\d+$/.test(_rawDisp)) ? _rawDisp : (nomBassin || _rawDisp);
                            legTitle.innerHTML = `<i class="fas fa-layer-group me-1"></i> SWMM 5.2 — ${dispNom}`;
                        }
                        if (typeof window.actualiserLegendeDwf === 'function') {
                            window.actualiserLegendeDwf(d);
                        }
                        if (typeof window.mettreAJourIndicateurBassin === 'function') {
                            window.mettreAJourIndicateurBassin(cidStr, d);
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
                        if (typeof window.mettreAJourIndicateurBassin === 'function') {
                            window.mettreAJourIndicateurBassin(cidStr, { status: 'unsimulated' });
                        }
                    }
                })
                .catch(err => {
                    window._simBassinEnChargement = null;
                    console.warn("Vérification simulation bassin:", err);
                    if (_selectedClusterId === cidStr) {
                        if (typeof reinitialiserAffichageSimulation === 'function') {
                            reinitialiserAffichageSimulation();
                        }
                        if (leg) {
                            leg.classList.remove('active-legend');
                            leg.style.display = 'none';
                        }
                        if (typeof window.mettreAJourIndicateurBassin === 'function') {
                            window.mettreAJourIndicateurBassin(cidStr, { status: 'unsimulated' });
                        }
                    }
                });
        };

        window.reinitialiserSelectionBassin = function(e) {
            if (e && e.stopPropagation) e.stopPropagation();
            _selectedClusterId = null;
            const sel = document.getElementById('bassin-select');
            if (sel) sel.value = '';
            const selIsole = document.getElementById('isoles-select');
            if (selIsole) selIsole.value = '';
            const infoIsole = document.getElementById('isoles-info');
            if (infoIsole) infoIsole.style.display = 'none';
            window._selectedIsolateId = null;
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
            window._selectedClusterId = _selectedClusterId;
            window.mettreAJourIndicateurBassin(_selectedClusterId);
            // Sous-bassins Voronoï : refiltrer surfaces/ha sur le bassin choisi
            if (typeof window.filtrerSousBassinsPourBassin === 'function') {
                window.filtrerSousBassinsPourBassin(_selectedClusterId);
            }

            // Mémoriser le dernier bassin ouvert, cloisonné par projet —
            // permet à l'application de se rouvrir sur le même bassin.
            try {
                const _pn = (window._rawNetworkData && (window._rawNetworkData.project_name || window._rawNetworkData.project_id)) || null;
                if (_selectedClusterId) {
                    localStorage.setItem('drainpilot_dernier_bassin', JSON.stringify({ projet: _pn, cluster: _selectedClusterId }));
                } else {
                    localStorage.removeItem('drainpilot_dernier_bassin');
                }
            } catch (e) {}

            // Synchroniser les dropdowns si l'appel vient du clic carte
            if (typeof window.synchroniserSelectionBassinOuIsole === 'function') {
                window.synchroniserSelectionBassinOuIsole(_selectedClusterId);
            } else {
                const sel = document.getElementById('bassin-select');
                if (sel && sel.value !== (_selectedClusterId || '')) {
                    sel.value = _selectedClusterId || '';
                }
            }
            afficherInfoBassin(_selectedClusterId);

            // Synchronisation intelligente et sécurisée de l'affichage de simulation
            if (typeof window.gererAffichageSimulationPourBassin === 'function') {
                window.gererAffichageSimulationPourBassin(_selectedClusterId);
            }

            // Maintenir cochés et affichés les rejets et la STEP uniquement si aucune simulation thématique n'est affichée
            const _simActive = !!(window._dernierResultatSimulation && couches && couches.res_conduites && carte.hasLayer(couches.res_conduites));
            if (!_simActive) {
                if (couches && couches.rejets && !carte.hasLayer(couches.rejets)) couches.rejets.addTo(carte);
                const elRejSync = document.getElementById('f-rejets');
                if (elRejSync) elRejSync.checked = true;

                if (couches && couches.step && !carte.hasLayer(couches.step)) couches.step.addTo(carte);
                const elStepSync = document.getElementById('f-step');
                if (elStepSync) elStepSync.checked = true;
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
                        const isSim = (layer._isSimulatedBassin === true) || _simCorrespondAuBassin(window._dernierResultatSimulation, fCid)
                            || (window._simulationsCache && Object.keys(window._simulationsCache).some(_k => {
                                const _c = window._simulationsCache[_k];
                                return _c && _c.status === 'success' && _simCorrespondAuBassin(_c, fCid);
                            }));
                        if (isSim) {
                            // Bassin simulé : maintien impératif de la teinte bleu ciel
                            layer.setStyle({ color: '#0284c7', fillColor: '#38bdf8', fillOpacity: 0.20, weight: 3.5, dashArray: '7, 4' });
                        } else {
                            // Bassin non simulé : actif avec bordure nette et couleur du cluster
                            layer.setStyle({ color: '#ffffff', fillColor: bColor, fillOpacity: 0.45, weight: 3.5, dashArray: null });
                        }
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

        /**
         * Restaure le dernier bassin ouvert au chargement du réseau.
         * Cloisonné par projet : un bassin d'un autre projet/organisation
         * n'est jamais restauré. Sans effet si le cluster n'existe plus.
         */
        window.restaurerDernierBassin = function () {
            try {
                const brut = localStorage.getItem('drainpilot_dernier_bassin');
                if (!brut) return false;
                const d = JSON.parse(brut);
                if (!d || !d.cluster) return false;
                const projetCourant = (window._rawNetworkData && (window._rawNetworkData.project_name || window._rawNetworkData.project_id)) || null;
                if (d.projet && projetCourant && String(d.projet) !== String(projetCourant)) return false;
                const cid = String(d.cluster);

                // Le cluster doit exister dans le réseau fraîchement chargé
                let existe = false;
                const sel = document.getElementById('bassin-select');
                if (sel) {
                    for (let i = 0; i < sel.options.length; i++) {
                        if (sel.options[i].value === cid) { existe = true; break; }
                    }
                }
                if (!existe && window._clustersData) {
                    existe = !!(window._clustersData[cid] || window._clustersData[Number(cid)]);
                }
                if (!existe) return false;

                highlightCluster(cid, window._activeClusterLayer || (typeof couches !== 'undefined' ? couches.bassins : null));
                const gl = window._activeClusterLayer || (typeof couches !== 'undefined' ? couches.bassins : null);
                if (gl && gl.getBounds && gl.getBounds().isValid()) {
                    carte.fitBounds(gl.getBounds(), { padding: [50, 50], maxZoom: 17 });
                }
                return true;
            } catch (e) {
                return false;
            }
        };

        // Synchronise la sélection entre le sélecteur de bassins collecteurs
        // et le sélecteur d'ouvrages/exutoires isolés.
        window.synchroniserSelectionBassinOuIsole = function(cid) {
            const sel = document.getElementById('bassin-select');
            const selIsole = document.getElementById('isoles-select');
            const infoIsole = document.getElementById('isoles-info');
            const cidStr = (cid !== null && cid !== undefined) ? String(cid) : '';

            if (!cidStr) {
                if (sel) sel.value = '';
                if (selIsole) selIsole.value = '';
                if (infoIsole) infoIsole.style.display = 'none';
                window._selectedIsolateId = null;
                return;
            }

            const estIsole = Boolean(window._bassinsIsoleIds && window._bassinsIsoleIds.has(cidStr));

            if (estIsole) {
                if (sel) sel.value = '';
                if (selIsole) selIsole.value = cidStr;
                if (infoIsole) infoIsole.style.display = 'block';
                window._selectedIsolateId = cidStr;
            } else {
                if (sel) sel.value = cidStr;
                if (selIsole) selIsole.value = '';
                if (infoIsole) infoIsole.style.display = 'none';
                window._selectedIsolateId = null;
            }
        };

        function peuplerDropdownBassins(geojsonData, clusterLayer) {
            const sel = document.getElementById('bassin-select');
            const selIsole = document.getElementById('isoles-select');
            const secIsole = document.getElementById('isoles-section');
            const badgeIsole = document.getElementById('badge-isoles-count');
            const infoIsole = document.getElementById('isoles-info');

            _bassinBounds = {};
            _bassinNoms = {};

            // Extraire les bassins (polygones) et construire leurs bounds
            const bassins = geojsonData.features.filter(f => f.properties && f.properties.type === 'bassin_urbain');

            // Séparation stricte : collecteurs simulables vs ouvrages/exutoires isolés
            const collecteurs = [];
            const isoles = [];

            bassins.forEach(f => {
                const cid = f.properties.cluster_id;
                let nom = f.properties.nom || `Bassin ${cid}`;
                // Rendre les identifiants techniques SIG plus conviviaux (ex. 0_rejets_346980 -> Exutoire 346980)
                nom = nom.replace(/^(\d+)_rejets_(\w+)/i, 'Exutoire $2');
                nom = nom.replace(/^(\d+)_ouvrages_speciaux_(\w+)/i, 'Ouvrage $2');
                f.properties.nom_affiche = nom;

                _bassinNoms[String(cid)] = nom;
                if (!window._bassinProperties) window._bassinProperties = {};
                window._bassinProperties[String(cid)] = f.properties;
                // Protection anti-collision homonymes (ex. Carmella 93 ha vs Carmella 0.35 ha) :
                // Ne stocker par clé textuelle 'nom' QUE si non encore enregistré, ou si le candidat actuel a plus de regards
                if (nom) {
                    const existant = window._bassinProperties[String(nom)];
                    if (!existant || (parseInt(f.properties.nb_regards || 0) > parseInt(existant.nb_regards || 0))) {
                        window._bassinProperties[String(nom)] = f.properties;
                        _bassinNoms[String(nom)] = nom;
                    }
                }

                const nbReg = parseInt(f.properties.nb_regards || 0);
                const nbCond = parseInt(f.properties.nb_conduites || 0);
                const surf = parseFloat(f.properties.surface_ha || 0.0);

                // Seuil strict pour les collecteurs simulables :
                // Doit comporter au moins 3 regards ET 3 conduites (ou surface >= 1.0 ha avec au moins 2 conduites).
                // Tout élément avec 1 ou 2 regards est classé dans les ouvrages et exutoires isolés (non simulables).
                const estCollecteur = (nbReg >= 3 && nbCond >= 3) || (surf >= 1.0 && nbCond >= 2);

                if (estCollecteur) {
                    f.properties.est_isole = false;
                    collecteurs.push(f);
                } else {
                    f.properties.est_isole = true;
                    isoles.push(f);
                }
            });

            window._bassinsCollecteurs = collecteurs;
            window._bassinsIsoles = isoles;
            window._bassinsIsoleIds = new Set(isoles.map(f => String(f.properties.cluster_id)));

            // Tri alphabétique strict des deux listes (par nom affiché)
            const triAlphabetique = (a, b) => {
                const nomA = (a.properties.nom_affiche || a.properties.nom || '').trim().toLowerCase();
                const nomB = (b.properties.nom_affiche || b.properties.nom || '').trim().toLowerCase();
                return nomA.localeCompare(nomB, 'fr', { sensitivity: 'base', numeric: true });
            };

            collecteurs.sort(triAlphabetique);
            isoles.sort(triAlphabetique);

            // 1. Peuplement du sélecteur principal (#bassin-select) — STRICTEMENT QUE LES BASSINS COLLECTEURS
            sel.innerHTML = `<option value="">-- Choisir un bassin versant (${collecteurs.length}) --</option>`;
            collecteurs.forEach(f => {
                const cid = f.properties.cluster_id;
                const nom = f.properties.nom_affiche || f.properties.nom || `Bassin ${cid}`;
                const surf = f.properties.surface_ha !== undefined ? ` (${f.properties.surface_ha} ha)` : '';
                const reg = (f.properties.nb_regards && f.properties.nb_regards > 0) ? ` • ${f.properties.nb_regards} reg.` : '';
                const opt = document.createElement('option');
                opt.value = cid;
                if (f.properties.bassin_ref) opt.dataset.bassinRef = f.properties.bassin_ref;
                if (f.properties.exutoire_id !== undefined && f.properties.exutoire_id !== null) {
                    opt.dataset.exutoireId = f.properties.exutoire_id;
                }
                opt.textContent = `${nom}${surf}${reg}`;
                sel.appendChild(opt);
            });

            // 2. Peuplement de la sous-section dédiée aux ouvrages et exutoires isolés (Option A)
            if (selIsole && secIsole) {
                if (isoles.length > 0) {
                    secIsole.style.display = 'block';
                    if (badgeIsole) badgeIsole.textContent = `${isoles.length}`;
                    selIsole.innerHTML = `<option value="">-- Choisir un ouvrage isolé (${isoles.length}) --</option>`;
                    isoles.forEach(f => {
                        const cid = f.properties.cluster_id;
                        const nom = f.properties.nom_affiche || f.properties.nom || `Ouvrage ${cid}`;
                        const surf = f.properties.surface_ha !== undefined ? ` (${f.properties.surface_ha} ha)` : '';
                        const reg = (f.properties.nb_regards && f.properties.nb_regards > 0) ? ` • ${f.properties.nb_regards} reg.` : '';
                        const opt = document.createElement('option');
                        opt.value = cid;
                        if (f.properties.bassin_ref) opt.dataset.bassinRef = f.properties.bassin_ref;
                        if (f.properties.exutoire_id !== undefined && f.properties.exutoire_id !== null) {
                            opt.dataset.exutoireId = f.properties.exutoire_id;
                        }
                        opt.textContent = `📍 ${nom}${surf}${reg}`;
                        selIsole.appendChild(opt);
                    });

                    selIsole.onchange = function() {
                        const cid = this.value;
                        if (sel) sel.value = ''; // Réinitialiser le sélecteur de bassins collecteurs
                        window._selectedIsolateId = cid || null;

                        if (infoIsole) {
                            infoIsole.style.display = cid ? 'block' : 'none';
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
                } else {
                    secIsole.style.display = 'none';
                    selIsole.innerHTML = '<option value="">-- Aucun ouvrage isolé --</option>';
                    if (badgeIsole) badgeIsole.textContent = '0';
                    if (infoIsole) infoIsole.style.display = 'none';
                }
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

            // Badges de fiabilité : charger la liste des simulations
            // (une seule fois) pour préfixer les bassins simulés.
            _chargerFiabiliteParBassin();
            window._bassinBounds = _bassinBounds;
            window._bassinNoms = _bassinNoms;

            // Mettre à jour dynamiquement le badge avec le nombre de bassins collecteurs
            const totalCollecteurs = collecteurs.length;
            const badge = document.getElementById('badge-subcatchments-count');
            if (badge && totalCollecteurs > 0) {
                const curText = badge.innerText || '';
                const parts = curText.split('•');
                const sbPart = parts.length > 1 ? parts[parts.length - 1].trim() : (curText.includes('SB') ? curText : '');
                badge.innerText = `${totalCollecteurs} BV${sbPart ? ' • ' + sbPart : ''}`;
            }

            // Afficher la section
            document.getElementById('bassin-section').style.display = 'block';

            // Écouteur du dropdown unique (onchange direct pour éviter les doublons d'écouteurs)
            sel.onchange = function() {
                const cid = this.value;
                if (selIsole) selIsole.value = '';
                if (infoIsole) infoIsole.style.display = 'none';
                window._selectedIsolateId = null;

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
