/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Popups détaillés des tronçons et formulaire d'édition des attributs SIG
 * ================================================================================
 */

// ==========================================
        // CADRAGE ET ZOOM PROPORTIONNEL SUR LE BASSIN VERSANT
        // ==========================================
        function zoomerSurBassin(clusterId, clusterLayer, targetBounds) {
            const map = window.carte || (typeof carte !== 'undefined' ? carte : null);
            if (!clusterId || !map) return;
            const cid = String(clusterId);

            // Priorité 0 : Bounds explicites fournis directement (ex: clic sur polygone)
            if (targetBounds && typeof targetBounds.isValid === 'function' && targetBounds.isValid()) {
                map.invalidateSize(true);
                map.flyToBounds(targetBounds, {
                    padding: [50, 50],
                    maxZoom: 16,
                    duration: 0.9,
                    easeLinearity: 0.25
                });
                return;
            }

            // Priorité 1 : Bounding box du polygone de bassin urbain (Emprise exacte sans les tronçons orphelins distants)
            let bBounds = null;
            if (window._bassinBounds) {
                bBounds = window._bassinBounds[cid] || window._bassinBounds[String(cid)] || (isNaN(parseInt(cid)) ? null : window._bassinBounds[parseInt(cid)]);
            }

            if (!bBounds || (typeof bBounds.isValid === 'function' && !bBounds.isValid())) {
                const searchLayers = [
                    clusterLayer,
                    window._activeClusterLayer,
                    (typeof couches !== 'undefined' ? couches.bassins : null)
                ];
                for (let sl of searchLayers) {
                    if (sl && typeof sl.eachLayer === 'function') {
                        sl.eachLayer(l => {
                            if (bBounds) return;
                            const f = l.feature;
                            if (f && f.properties && String(f.properties.cluster_id) === cid && f.properties.type === 'bassin_urbain') {
                                if (l.getBounds && typeof l.getBounds === 'function' && l.getBounds().isValid()) {
                                    bBounds = l.getBounds();
                                }
                            }
                        });
                    }
                    if (bBounds) break;
                }
            }

            // Fallback géométrie GeoJSON pure
            if (!bBounds && window._clustersData && Array.isArray(window._clustersData.features)) {
                for (let f of window._clustersData.features) {
                    if (f && f.properties && String(f.properties.cluster_id) === cid && f.properties.type === 'bassin_urbain') {
                        try {
                            const tmpL = L.geoJSON(f);
                            if (tmpL.getBounds && tmpL.getBounds().isValid()) {
                                bBounds = tmpL.getBounds();
                                break;
                            }
                        } catch(e) {}
                    }
                }
            }

            if (bBounds && typeof bBounds.isValid === 'function' && bBounds.isValid()) {
                map.invalidateSize(true);
                map.flyToBounds(bBounds, {
                    padding: [50, 50],
                    maxZoom: 16,
                    duration: 0.9,
                    easeLinearity: 0.25
                });
                return;
            }

            // Priorité 2 : Si aucun polygone de bassin n'existe, délimiter via l'exutoire et les conduites proches (< 1.5 km)
            let exLatLng = null;
            if (window._activeClusterLayer && typeof window._activeClusterLayer.eachLayer === 'function') {
                window._activeClusterLayer.eachLayer(l => {
                    const f = l.feature;
                    if (f && f.properties && f.properties.type === 'exutoire' && String(f.properties.cluster_id) === cid) {
                        if (l.getLatLng) exLatLng = l.getLatLng();
                    }
                });
            }

            const fallbackBounds = L.latLngBounds();
            let hasGeom = false;
            const clLayer = clusterLayer || window._activeClusterLayer || (typeof couches !== 'undefined' ? couches.bassins : null);
            if (clLayer && typeof clLayer.eachLayer === 'function') {
                clLayer.eachLayer(layer => {
                    const f = layer.feature;
                    if (!f || !f.properties || String(f.properties.cluster_id) !== cid) return;
                    if (layer.getBounds && typeof layer.getBounds === 'function' && layer.getBounds().isValid()) {
                        const b = layer.getBounds();
                        if (!exLatLng || map.distance(b.getCenter(), exLatLng) < 1500) {
                            fallbackBounds.extend(b);
                            hasGeom = true;
                        }
                    } else if (layer.getLatLng && typeof layer.getLatLng === 'function' && layer.getLatLng()) {
                        const ll = layer.getLatLng();
                        if (!exLatLng || map.distance(ll, exLatLng) < 1500) {
                            fallbackBounds.extend(ll);
                            hasGeom = true;
                        }
                    }
                });
            }

            if (exLatLng) {
                fallbackBounds.extend(exLatLng);
                hasGeom = true;
            }

            if (hasGeom && fallbackBounds.isValid()) {
                map.invalidateSize(true);
                map.flyToBounds(fallbackBounds, {
                    padding: [50, 50],
                    maxZoom: 16,
                    duration: 0.9,
                    easeLinearity: 0.25
                });
            }
        }

        function afficherInfoBassin(clusterId) {
            const infoDiv = document.getElementById('bassin-info');
            if (!_activeClusterLayer || clusterId === null || clusterId === undefined || clusterId === '') {
                infoDiv.innerHTML = '';
                const miniStatsEl = document.getElementById('mini-stats');
                if (miniStatsEl && window._rawNetworkData && window._rawNetworkData.compteurs) {
                    const c = window._rawNetworkData.compteurs;
                    const pName = window._rawNetworkData.project_name || 'Réseau Actif';
                    miniStatsEl.innerHTML = `<span style="color: #38bdf8; font-weight: 700;">Zone : ${pName}</span> | Conduites: <b>${c.conduites || 0}</b> | Regards: <b>${c.regards || 0}</b>`;
                    miniStatsEl.style.background = 'rgba(255, 255, 255, 0.06)';
                    miniStatsEl.style.border = 'none';
                    miniStatsEl.style.color = '#94a3b8';
                }
                return;
            }
            let nb = 0;
            let longueur = 0;
            let bassinProperties = null;
            _activeClusterLayer.eachLayer(layer => {
                const f = layer.feature;
                if (!f) return;
                if (f.geometry && (f.geometry.type === 'LineString' || f.geometry.type === 'MultiLineString') && String(f.properties.cluster_id) === String(clusterId)) {
                    nb++;
                    longueur += (f.properties.longueur || 0);
                }
                if (f.properties && f.properties.type === 'bassin_urbain' && String(f.properties.cluster_id) === String(clusterId)) {
                    bassinProperties = f.properties;
                }
            });
            if (bassinProperties) {
                nb = bassinProperties.nb_conduites !== undefined ? bassinProperties.nb_conduites : (bassinProperties.nb_troncons ?? nb);
                longueur = bassinProperties.longueur_totale_m !== undefined ? bassinProperties.longueur_totale_m : longueur;
            }
            // Synchronisation stricte avec la simulation active si ce bassin est le périmètre simulé
            let displaySurf = (bassinProperties && bassinProperties.surface_ha !== undefined && bassinProperties.surface_ha !== null) ? bassinProperties.surface_ha : null;
            if (window._dernierResultatSimulation && window._dernierResultatSimulation.meta && String(window._dernierResultatSimulation.meta.cluster_id) === String(clusterId)) {
                if (window._dernierResultatSimulation.meta.conduits_count !== undefined) {
                    nb = window._dernierResultatSimulation.meta.conduits_count;
                }
                if (window._dernierResultatSimulation.meta.total_area_ha !== undefined) {
                    displaySurf = window._dernierResultatSimulation.meta.total_area_ha;
                }
            }
            const nom = _bassinNoms && _bassinNoms[clusterId] ? _bassinNoms[clusterId] : `Bassin ${clusterId}`;
            const surfHa = displaySurf !== null ? `${displaySurf} ha` : 'N/A';
            const nbReg = (bassinProperties && bassinProperties.nb_regards !== undefined && bassinProperties.nb_regards !== null) ? bassinProperties.nb_regards : 'N/A';
            const nbOrph = (bassinProperties && bassinProperties.nb_regards_orphelins !== undefined && bassinProperties.nb_regards_orphelins !== null) ? bassinProperties.nb_regards_orphelins : 0;
            const typEx = (bassinProperties && bassinProperties.exutoire_type) ? bassinProperties.exutoire_type.toUpperCase() : 'EXUTOIRE';
            const bColor = (bassinProperties && bassinProperties.couleur) ? bassinProperties.couleur : '#38bdf8';

            // Mise à jour synchrone du bandeau haut latéral avec la zone sélectionnée
            const miniStatsEl = document.getElementById('mini-stats');
            if (miniStatsEl) {
                miniStatsEl.innerHTML = `<span style="color: #38bdf8; font-weight: 700;">Zone : ${nom}</span> | Conduites: <b>${nb}</b> | Regards: <b>${nbReg}</b>`;
                miniStatsEl.style.background = 'rgba(56, 189, 248, 0.15)';
                miniStatsEl.style.border = '1px solid rgba(56, 189, 248, 0.3)';
                miniStatsEl.style.color = '#f8fafc';
            }

            // Le détail exhaustif est déjà présenté interactivement dans l'infobulle cartographique au survol
            if (infoDiv) infoDiv.innerHTML = '';

            // Détection spatiale et affichage cartographique automatique des ouvrages spéciaux proches
            if (typeof window.actualiserAlerteOuvrageDeporte === 'function' && clusterId) {
                window.actualiserAlerteOuvrageDeporte(clusterId);
            }
        }

        // Reprise du projet en cours depuis la modale
        window.reprendreProjetEnCours = function() {
            sessionStorage.setItem('projet_charge', 'true');
            montrerModalProjet(false);
            chargerDonneesInitiales();
        };

        // Fonctions d'édition
        let currentEditProperties = null;
        let currentEditType = null;
        let currentEditId = null;

        window.editConduit = (index) => {
            openEditModal(window.conduitProperties[index], 'conduite');
        };

        window.editRegard = (index) => {
            openEditModal(window.regardProperties[index], 'regards');
        };

        function conduitPopup(feature, index) {
            const p = feature.properties || {};
            const uNode = p.ID_AMONT || p.id_amont || p.amont || '';
            const dNode = p.ID_AVAL || p.id_aval || p.aval || '';
            const cName = (uNode && dNode) ? `${uNode} ➔ ${dNode}` : (p.conduit_id || p.CODE || p.code || `C_${index + 1}`);
            const rawLong = p.Longeur !== undefined ? p.Longeur : (p.longueur !== undefined ? p.longueur : p.LONGUEUR);
            const longTxt = (rawLong !== undefined && rawLong !== null && !isNaN(rawLong)) ? `${parseFloat(rawLong).toFixed(1)} m` : 'N/A';
            const rawDiam = p.DIAMETRE !== undefined ? p.DIAMETRE : (p.diametre !== undefined ? p.diametre : p.DIAM);
            const diamTxt = (rawDiam !== undefined && rawDiam !== null && !isNaN(rawDiam)) ? `${parseFloat(rawDiam).toFixed(0)} mm` : '600 mm';
            const mat = p.MATERIAU || p.materiau || 'Béton';

            return `<div style="font-family: inherit; font-size: 12px; color: #1e293b; min-width: 210px; line-height: 1.4;">
                <div style="font-weight: 800; font-size: 13px; color: #0284c7; margin-bottom: 5px; display: flex; align-items: center; gap: 5px;">
                    <i class="fas fa-water"></i> Conduite C_${index + 1}
                </div>
                <div style="background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 6px; padding: 6px 8px; margin-bottom: 8px; font-size: 11px;">
                    <div><span style="color: #64748b;">Raccordement :</span> <b style="color: #0369a1;">${cName}</b></div>
                    <div><span style="color: #64748b;">Diamètre :</span> <b>${diamTxt}</b></div>
                    <div><span style="color: #64748b;">Longueur :</span> <b>${longTxt}</b></div>
                    <div><span style="color: #64748b;">Matériau :</span> <b>${mat}</b></div>
                </div>
                <button onclick="editConduit(${index})" style="width: 100%; padding: 5px 10px; background: #0284c7; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: 600;">
                    <i class="fas fa-edit me-1"></i> Modifier la canalisation
                </button>
            </div>`;
        }

        function regardPopup(feature, index) {
            const p = feature.properties || {};
            const rCode = String(p.Code !== undefined ? p.Code : (p.code !== undefined ? p.code : (p.CODE !== undefined ? p.CODE : (p.id || p.fid || (index !== undefined ? index + 1 : 'N/A')))));
            const cleanCode = rCode.endsWith('.0') ? rCode.slice(0, -2) : rCode;
            const prof = p.Profondeur !== undefined ? p.Profondeur : (p.profondeur !== undefined ? p.profondeur : p.PROFONDEUR);
            const profTxt = (prof !== undefined && prof !== null && prof !== '' && !isNaN(prof)) ? `${parseFloat(prof).toFixed(2)} m` : 'Non renseignée';
            const ctn = p.COTTN !== undefined ? p.COTTN : (p.cottn !== undefined ? p.cottn : p.cote_tampon);
            const ctnTxt = (ctn !== undefined && ctn !== null && ctn !== '' && !isNaN(ctn)) ? `${parseFloat(ctn).toFixed(2)} m` : '--';
            const typeReg = p.TYPERES || p.type_regard || p.type || 'Standard';

            return `<div style="font-family: inherit; font-size: 12px; color: #1e293b; min-width: 210px; line-height: 1.4;">
                <div style="font-weight: 800; font-size: 13px; color: #0284c7; margin-bottom: 5px; display: flex; align-items: center; gap: 5px;">
                    <i class="fas fa-bullseye"></i> Regard N° ${cleanCode}
                </div>
                <div style="background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 6px; padding: 6px 8px; margin-bottom: 8px; font-size: 11px;">
                    <div><span style="color: #64748b;">Sous-Bassin drainé :</span> <b style="color: #059669;">SB_${cleanCode}</b></div>
                    <div><span style="color: #64748b;">Cote Tampon (TN) :</span> <b>${ctnTxt}</b></div>
                    <div><span style="color: #64748b;">Profondeur :</span> <b>${profTxt}</b></div>
                    <div><span style="color: #64748b;">Type réseau :</span> <b>${typeReg}</b></div>
                </div>
                <button onclick="editRegard(${index})" style="width: 100%; padding: 5px 10px; background: #0284c7; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: 600;">
                    <i class="fas fa-edit me-1"></i> Modifier l'ouvrage
                </button>
            </div>`;
        }

        function openEditModal(properties, type) {
            currentEditProperties = properties;
            currentEditType = type;
            currentEditId = properties.conduit_id || properties.fid || properties.id || properties.Code || properties.code;

            const title = type === 'conduite' ? 'Modifier Conduite' : `Modifier ${type.charAt(0).toUpperCase() + type.slice(1)}`;
            document.getElementById('modal-title').textContent = title;

            const form = document.getElementById('edit-form');
            form.innerHTML = '';

            if (type === 'conduite') {
                addField(form, 'longueur', 'Longueur (m)', properties.longueur || properties.LONGUEUR || properties.Longeur || '');
                addField(form, 'diametre', 'Diamètre (mm)', properties.diametre || properties.DIAMETRE || '');
                addField(form, 'materiau', 'Matériau', properties.materiau || properties.MATERIAU || '');
                addField(form, 'f_nom', 'Nom', properties.f_nom || properties.NOM || '');
            } else if (type === 'regards') {
                addField(form, 'code', 'Code Regard', properties.code || properties.Code || properties.CODE || '');
                addField(form, 'type_regard', 'Type', properties.type_regard || properties.TYPERES || '');
                addField(form, 'diametre', 'Diamètre', properties.diametre || properties.DIAMETRES || '');
                addField(form, 'profondeur', 'Profondeur', properties.profondeur || properties.Profondeur || '');
            } else {
                addField(form, 'nom', 'Nom', properties.nom || '');
                addField(form, 'type', 'Type', properties.type || '');
            }

            document.getElementById('edit-modal').style.display = 'flex';
        }

        function addField(form, name, label, value) {
            const div = document.createElement('div');
            div.style.marginBottom = '10px';
            div.innerHTML = `
                <label style="display: block; margin-bottom: 5px;">${label}:</label>
                <input type="text" name="${name}" value="${escapeHtml(value)}" style="width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px;">
            `;
            form.appendChild(div);
        }

        async function saveEdit() {
            const formData = new FormData(document.getElementById('edit-form'));
            const updateData = {};

            for (let [key, value] of formData.entries()) {
                if (value.trim()) {
                    if (['longueur', 'diametre', 'profondeur'].includes(key)) {
                        updateData[key] = parseFloat(value);
                    } else {
                        updateData[key] = value;
                    }
                }
            }

            const endpoint = currentEditType === 'conduite'
                ? `/api/v1/network/conduites/${currentEditId}`
                : `/api/v1/network/regards/${currentEditId}`;

            try {
                const response = await fetch(endpoint, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(updateData)
                });

                if (response.ok) {
                    alert('Modifications enregistrées');
                    document.getElementById('edit-modal').style.display = 'none';
                    location.reload();
                } else {
                    alert('Erreur lors de la sauvegarde');
                }
            } catch (error) {
                console.error('Erreur:', error);
                alert('Erreur réseau');
            }
        }

        function escapeHtml(value) {
            return String(value)
                .replace(/&/g, '&')
                .replace(/</g, '<')
                .replace(/>/g, '>')
                .replace(/"/g, '"')
                .replace(/'/g, '&#039;');
        }

        document.getElementById('cancel-btn').addEventListener('click', () => {
            document.getElementById('edit-modal').style.display = 'none';
        });

        document.getElementById('close-btn-header').addEventListener('click', () => {
            document.getElementById('edit-modal').style.display = 'none';
        });

        // Logique de glisser-déposer (Drag & Drop) pour la modale
        const editModal = document.getElementById('edit-modal');
        const modalHeader = document.getElementById('modal-header');
        let isDragging = false;
        let offsetX, offsetY;

        modalHeader.addEventListener('mousedown', (e) => {
            isDragging = true;
            offsetX = e.clientX - editModal.getBoundingClientRect().left;
            offsetY = e.clientY - editModal.getBoundingClientRect().top;
            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });

        function onMouseMove(e) {
            if (!isDragging) return;
            editModal.style.left = (e.clientX - offsetX) + 'px';
            editModal.style.top = (e.clientY - offsetY) + 'px';
        }

        function onMouseUp() {
            isDragging = false;
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
        }

        document.getElementById('save-btn').addEventListener('click', saveEdit);
