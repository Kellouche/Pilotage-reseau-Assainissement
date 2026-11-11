/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Modale de simulation SWMM, sélection pluviométrique et raccordements orphelins
 * ================================================================================
 */

window.dessinerRaccordementsOrphelinsSurCarte = function() {
            if (!window.carte) return;
            if (window._coucheRaccordementsOrphelins) {
                window.carte.removeLayer(window._coucheRaccordementsOrphelins);
            }
            window._coucheRaccordementsOrphelins = L.featureGroup();

            const chks = document.querySelectorAll('.sim-chk-ouvrage-orphelin');
            const candidats = window._ouvragesOrphelinsCandidats || [];
            let countActive = 0;

            chks.forEach(chk => {
                if (chk.checked) {
                    const idx = parseInt(chk.getAttribute('data-index'), 10);
                    const o = candidats[idx];
                    if (o && o.regard_coord_wgs84 && o.ouvrage_coord_wgs84) {
                        countActive++;
                        const rPt = o.regard_coord_wgs84; // [lat, lon]
                        const oPt = o.ouvrage_coord_wgs84; // [lat, lon]

                        // Ligne en tireté cyan vive représentant le raccordement physique projeté
                        const poly = L.polyline([rPt, oPt], {
                            color: '#06b6d4',
                            weight: 5,
                            dashArray: '8, 8',
                            opacity: 1.0,
                            pane: window.carte.getPane('swmmNodesPane') ? 'swmmNodesPane' : 'overlayPane'
                        });
                        const coutFmt = window.formaterCoutDZD(o.cout_estime_dzd);
                        poly.bindTooltip(
                            `⚡ <b>Variante 0 : Raccordement Opportuniste Immédiat</b><br>` +
                            `<b>${o.nom}</b><br>` +
                            `Distance : ${o.distance_m} m du Regard ${o.regard_proche_id}<br>` +
                            `DN 600 mm &bull; Coût estimé : ${coutFmt}<br>` +
                            `<span style="color:#4ade80; font-weight:700;">Gain économique : &gt; 90%</span>`,
                            { sticky: true }
                        );

                        // Marqueur stylisé sur l'ouvrage orphelin avec dimensionnement dynamique ajusté au zoom
                        const curZoom = window.carte.getZoom ? window.carte.getZoom() : 15;
                        const rOuv = calculerRayonOuvrageSpecial(curZoom);
                        const markerOuv = L.circleMarker(oPt, { 
                            pane: window.carte.getPane('swmmNodesPane') ? 'swmmNodesPane' : 'overlayPane',
                            radius: rOuv,
                            color: '#ffffff',
                            fillColor: o.badge_color || '#a855f7',
                            weight: 2.5,
                            opacity: 1.0,
                            fillOpacity: 0.95,
                            className: 'orphan-zoom-marker'
                        });
                        markerOuv.bindTooltip(`<b>${o.nom}</b><br>Ouvrage existant non raccordé dans le SIG (Distance : ${o.distance_m} m)`, { direction: 'top', offset: [0, -6] });

                        window._coucheRaccordementsOrphelins.addLayer(poly);
                        window._coucheRaccordementsOrphelins.addLayer(markerOuv);
                    }
                }
            });

            if (countActive > 0) {
                window._coucheRaccordementsOrphelins.addTo(window.carte);
            }
        };

        window.chargerOuvragesOrphelinsProches = function(clusterId) {
            const orphSection = document.getElementById('sim-ouvrages-orphelins-section');
            const orphListe = document.getElementById('sim-ouvrages-liste');
            const countBadge = document.getElementById('sim-ouvrages-count-badge');
            if (!orphSection || !orphListe) return;

            if (!clusterId) {
                orphSection.style.display = 'none';
                if (window._coucheRaccordementsOrphelins && window.carte) {
                    window.carte.removeLayer(window._coucheRaccordementsOrphelins);
                }
                return;
            }

            orphListe.innerHTML = '<div style="font-size:0.75rem; color:#94a3b8;"><i class="fas fa-circle-notch fa-spin me-1"></i> Détection spatiale des ouvrages orphelins à proximité...</div>';
            orphSection.style.display = 'block';

            const token = localStorage.getItem('swmm_access_token');
            const headers = {};
            if (token) headers['Authorization'] = `Bearer ${token}`;

            fetch(`/api/v1/clusters/${clusterId}/ouvrages-proches?rayon_m=45`, { headers: headers, credentials: 'include' })
            .then(r => r.json())
            .then(data => {
                const ouvrages = data.ouvrages || [];
                window._ouvragesOrphelinsCandidats = ouvrages;

                if (ouvrages.length === 0) {
                    window._ouvragesOrphelinsCandidatsSelectionnes = [];
                    if (countBadge) {
                        countBadge.textContent = '0 ouvrage adjacent';
                    }
                    orphListe.innerHTML = '<div style="font-size:0.75rem; color:#94a3b8; padding: 6px 2px;"><i class="fas fa-info-circle me-1 text-info"></i> Aucun ouvrage spécial adjacent (&le; 45 m) pour ce bassin. Le modèle simulera l\'écoulement gravitaire pur sans dérivation artificielle.</div>';
                    orphSection.style.display = 'block';
                    if (window._coucheRaccordementsOrphelins && window.carte) {
                        window.carte.removeLayer(window._coucheRaccordementsOrphelins);
                    }
                    return;
                }

                if (countBadge) {
                    countBadge.textContent = `${ouvrages.length} ouvrage(s) détecté(s)`;
                }

                let html = '';
                ouvrages.forEach((o, i) => {
                    const coutFmt = window.formaterCoutDZD(o.cout_estime_dzd);
                    html += `
                    <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(148, 163, 184, 0.25); border-radius: 8px; padding: 9px 12px; transition: all 0.2s;">
                        <label style="display: flex; align-items: flex-start; gap: 10px; cursor: pointer; margin-bottom: 0;">
                            <input type="checkbox" class="sim-chk-ouvrage-orphelin" data-index="${i}" checked style="accent-color: #06b6d4; width: 17px; height: 17px; margin-top: 2px; cursor: pointer;">
                            <div style="flex: 1;">
                                <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                                    <span class="badge" style="background: ${o.badge_color}; color: #fff; font-size: 0.68rem; font-weight: 600;">${o.type_label}</span>
                                    <strong style="color: #f8fafc; font-size: 0.82rem;">${o.nom}</strong>
                                    <span style="color: #38bdf8; font-size: 0.74rem; font-weight: 600;">— Distance : ${o.distance_m} m du Regard ${o.regard_proche_id}</span>
                                </div>
                                <div style="font-size: 0.72rem; color: #94a3b8; margin-top: 3px; display: flex; gap: 12px; flex-wrap: wrap;">
                                    <span><i class="fas fa-arrows-alt-h me-1 text-info"></i> DN 600 mm recommandé</span>
                                    <span><i class="fas fa-coins me-1 text-warning"></i> Coût estimé : <b style="color: #fbbf24;">${coutFmt}</b></span>
                                    <span style="color: #4ade80; font-weight: 600;"><i class="fas fa-shield-alt me-1"></i> Soulagement immédiat</span>
                                </div>
                            </div>
                        </label>
                    </div>`;
                });

                orphListe.innerHTML = html;
                orphSection.style.display = 'block';

                // Écouter les cases à cocher pour actualiser dynamiquement la carte
                document.querySelectorAll('.sim-chk-ouvrage-orphelin').forEach(input => {
                    input.addEventListener('change', () => {
                        window.dessinerRaccordementsOrphelinsSurCarte();
                    });
                });

                // Dessiner immédiatement les tracés en tiretés sur Leaflet
                window.dessinerRaccordementsOrphelinsSurCarte();
            })
            .catch(err => {
                console.warn('[Ouvrages orphelins] Erreur fetch:', err);
                orphSection.style.display = 'none';
            });
        };

        window.actualiserAlerteOuvrageDeporte = function(clusterId) {
            // 1. Détection intelligente des ouvrages orphelins proches (< 120 m)
            window.chargerOuvragesOrphelinsProches(clusterId);

            // 2. Gestion de l'exutoire déporté propre au cluster (fallback rétrocompatible)
            const box = document.getElementById('sim-deporte-box');
            if (!box) return;
            if (!clusterId || !window._clustersData || !window._clustersData.features) {
                box.style.display = 'none';
                return;
            }
            const f = window._clustersData.features.find(feat => 
                feat.properties && String(feat.properties.cluster_id) === String(clusterId) && (feat.properties.type === 'bassin_urbain' || feat.properties.type === 'exutoire')
            );
            if (f && f.properties && f.properties.est_deporte) {
                const p = f.properties;
                const dist = p.distance_regard_proche_m !== undefined ? p.distance_regard_proche_m + ' m' : 'quelques mètres';
                const regId = p.regard_proche_id || 'regard le plus proche';
                const nomOuv = p.nom || `Bassin ${clusterId}`;
                document.getElementById('sim-deporte-titre').innerHTML = `<i class="fas fa-exclamation-triangle me-1"></i> Ouvrage spécial déporté : ${nomOuv} (${dist})`;
                document.getElementById('sim-deporte-desc').innerHTML = `L'ouvrage <b>${nomOuv}</b> est géométriquement situé à <b>${dist}</b> du regard collecteur <b>${regId}</b> (distance supérieure au seuil topographique standard de 1.0 m).`;
                document.getElementById('sim-deporte-label-chk').innerHTML = `<b>Valider le raccordement hydraulique au regard amont ${regId}</b>`;
                document.getElementById('sim-chk-valider-raccordement').checked = true;
                box.style.display = 'block';
            } else {
                box.style.display = 'none';
            }
        };

        window.fermerModalSimulation = function() {
            const m = document.getElementById('modal-simulation');
            if (m) m.style.display = 'none';
            if (window.carte) {
                // S'assurer que le calque de résultats est bien affiché et les couches physiques masquées
                if (typeof clusterCouche !== 'undefined' && clusterCouche && carte.hasLayer(clusterCouche)) {
                    carte.removeLayer(clusterCouche);
                }
                if (carte.hasLayer(couches.conduites)) carte.removeLayer(couches.conduites);
                if (carte.hasLayer(couches.regards)) carte.removeLayer(couches.regards);
                if (!carte.hasLayer(couches.res_conduites)) couches.res_conduites.addTo(carte);
                if (!carte.hasLayer(couches.res_regards)) couches.res_regards.addTo(carte);

                // Afficher la légende interactive
                const leg = document.getElementById('sim-floating-legend');
                if (leg && window._dernierResultatSimulation) {
                    leg.classList.add('active-legend');
                    leg.style.display = 'block';
                }

                // Déclencher un recentrage et zoom fluide précis sur la zone simulée
                setTimeout(() => {
                    carte.invalidateSize(true);
                    if (window._dernierResultatSimulation) {
                        if (typeof window.zoomerSurZoneSimulee === 'function') {
                            window.zoomerSurZoneSimulee(window._dernierResultatSimulation, 19);
                        } else {
                            zoomerSurZoneSimulee(window._dernierResultatSimulation);
                        }
                        mettreAJourIHMZoneSimulee(window._dernierResultatSimulation);
                    } else if (window._lastSimBounds && window._lastSimBounds.isValid && window._lastSimBounds.isValid()) {
                        carte.flyToBounds(window._lastSimBounds, {
                            padding: [35, 35],
                            maxZoom: 19,
                            duration: 1.0,
                            easeLinearity: 0.25
                        });
                    }
                }, 50);
            }
        };

        // ==========================================
        // GESTION DYNAMIQUE DE LA PLUVIOMÉTRIE (Référentiel ANRH / UHBC Chlef)
        // ==========================================
        window._scenariosPluieInfo = {
            'pluie_decennale': {
                imax: 74.9,
                station: 'Station ANRH Chlef Siège (010501)',
                duree: 4.0,
                note: 'Paramétrage ANRH Chlef Siège (UHBC) : Formule Montana I(t) = 9.334 · t⁻⁰·⁷⁴⁵ &bull; Hyétogramme Chicago centré (tc = 15 min) &bull; P₂₄ = 56.0 mm &bull; Hauteur cumulée P = 42.8 mm [Standard Réglementaire ONA].'
            },
            'pluie_cinquantennale': {
                imax: 120.0,
                station: 'Station ANRH Chlef Siège (010501)',
                duree: 4.0,
                note: 'Crise Majeure Cinquantennale ANRH Chlef : Formule Montana I(t) = 15.795 · t⁻⁰·⁷⁶⁰ &bull; P₂₄ = 81.0 mm &bull; Hauteur cumulée P = 67.5 mm.'
            },
            'pluie_centennale': {
                imax: 144.5,
                station: 'Station ANRH Chlef Siège (010501)',
                duree: 4.0,
                note: 'Crue Historique Centennale ANRH Chlef : Formule Montana I(t) = 19.338 · t⁻⁰·⁷⁶⁴ &bull; P₂₄ = 94.0 mm &bull; Hauteur cumulée P = 81.0 mm.'
            },
            'pluie_biennale': {
                imax: 45.0,
                station: 'Station ANRH Chlef Siège (010501)',
                duree: 4.0,
                note: 'Pluie Courante Biennale ANRH Chlef : Formule Montana I(t) = 5.250 · t⁻⁰·⁷²⁰ &bull; P₂₄ = 34.0 mm &bull; Hauteur cumulée P = 26.0 mm.'
            },
            'pluie_orage_2h': {
                imax: 92.5,
                station: 'Station ANRH Chlef Siège (010501)',
                duree: 2.0,
                note: 'Orage d\'été brutal méditerranéen convectif concentré sur 60 min avec pic à 92.5 mm/h (T ≈ 20 ans) &bull; P₂₄ = 66.5 mm.'
            },
            'temps_sec_pur': {
                imax: 0.0,
                station: 'Régime d\'Étiage Sans Pluie',
                duree: 24.0,
                note: 'Temps Sec Pur : Transit exclusif du débit d\'étiage des eaux usées (DWF) sans apport pluvial &bull; I = 0 mm/h.'
            },
            'personnalise': {
                imax: 74.9,
                station: 'Profil Saisi par l\'Utilisateur',
                duree: 4.0,
                note: 'Pluie personnalisée proportionnelle : l\'hyétogramme est généré d\'après l\'intensité de pointe spécifiée par l\'ingénieur.'
            }
        };

        window.onChangementStationPluie = function(stationId) {
            const badge = document.getElementById('sim-pluvio-station-badge');
            if (badge) badge.innerText = 'Chargement station...';
            
            fetch(`/api/v1/simulations/scenarios?station_id=${encodeURIComponent(stationId)}`)
                .then(r => r.ok ? r.json() : null)
                .then(data => {
                    if (data && data.scenarios) {
                        const newScenInfo = {};
                        const stName = (data.station && data.station.nom) ? data.station.nom : stationId;
                        const stCode = (data.station && data.station.code_anrh) ? `(${data.station.code_anrh})` : '';
                        
                        data.scenarios.forEach(sc => {
                            newScenInfo[sc.key] = {
                                imax: sc.intensite_max_defaut || 74.9,
                                station: `${stName} ${stCode}`,
                                duree: sc.duree_heures || 4.0,
                                note: sc.description || (sc.formule_montana ? `Formule Montana : ${sc.formule_montana}` : '')
                            };
                        });
                        window._scenariosPluieInfo = newScenInfo;
                        
                        const scenSel = document.getElementById('sim-select-scenario');
                        const curVal = scenSel ? scenSel.value : 'pluie_decennale';
                        window.onChangementScenarioPluie(curVal);
                    }
                })
                .catch(err => {
                    console.warn("Erreur chargement scénarios station:", err);
                });
        };

        window.onChangementScenarioPluie = function(scenKey) {
            if (scenKey === 'bms_onm') {
                window.basculerModePluie('bms');
                return;
            }
            if (window._modePluieActif === 'bms') {
                window.basculerModePluie('projet');
            }
            const info = window._scenariosPluieInfo[scenKey] || window._scenariosPluieInfo['pluie_decennale'];
            const inp = document.getElementById('sim-input-intensite-max');
            if (inp) inp.value = info.imax;
            const badge = document.getElementById('sim-pluvio-station-badge');
            if (badge) badge.innerText = info.station;
            const noteText = document.getElementById('sim-pluvio-note-text');
            if (noteText) noteText.innerHTML = info.note;
            const dureeSel = document.getElementById('sim-select-duree');
            if (dureeSel && info.duree) dureeSel.value = String(info.duree);
        };

        window.onChangementIntensitePluie = function(valStr) {
            const val = parseFloat(String(valStr).replace(',', '.'));
            const scenSel = document.getElementById('sim-select-scenario');
            const noteText = document.getElementById('sim-pluvio-note-text');
            const badge = document.getElementById('sim-pluvio-station-badge');
            if (isNaN(val) || val < 0) return;

            let matchedKey = null;
            for (const [k, s] of Object.entries(window._scenariosPluieInfo)) {
                if (k !== 'personnalise' && Math.abs(s.imax - val) < 0.05) {
                    matchedKey = k;
                    break;
                }
            }
            if (matchedKey && scenSel) {
                scenSel.value = matchedKey;
                const info = window._scenariosPluieInfo[matchedKey];
                if (badge) badge.innerText = info.station;
                if (noteText) noteText.innerHTML = info.note;
            } else if (scenSel) {
                scenSel.value = 'personnalise';
                if (badge) badge.innerText = 'Saisie Manuelle Utilisateur';
                if (noteText) noteText.innerHTML = `✏️ <b>Intensité personnalisée :</b> $I_{max} = ${val.toFixed(1)}\\text{ mm/h}$ &bull; Hyétogramme SWMM proportionnel &bull; Débit rationnel attendu $Q_{rat} = \\frac{C \\cdot I \\cdot A}{360}$.`;
            }
        };

        // ==========================================
        // GESTION DU MODULE BMS (Bulletin Météorologique Spécial - ONM Algérie)
        // ==========================================
        window._modePluieActif = 'projet';

        window.basculerModePluie = function(mode) {
            window._modePluieActif = mode;
            const btnProjet = document.getElementById('tab-mode-pluie-projet');
            const btnBms = document.getElementById('tab-mode-pluie-bms');
            const secProjet = document.getElementById('section-pluie-projet');
            const secBms = document.getElementById('section-pluie-bms');
            const badgeStation = document.getElementById('sim-pluvio-station-badge');

            if (mode === 'bms') {
                if (btnProjet) {
                    btnProjet.style.background = 'transparent';
                    btnProjet.style.color = '#94a3b8';
                }
                if (btnBms) {
                    btnBms.style.background = '#ea580c';
                    btnBms.style.color = 'white';
                }
                if (secProjet) secProjet.style.display = 'none';
                if (secBms) secBms.style.display = 'block';
                if (badgeStation) badgeStation.innerText = 'Mode alerte météo (BMS ONM)';
                window.onChangementParametresBMS();
            } else {
                if (btnProjet) {
                    btnProjet.style.background = '#0284c7';
                    btnProjet.style.color = 'white';
                }
                if (btnBms) {
                    btnBms.style.background = 'transparent';
                    btnBms.style.color = '#94a3b8';
                }
                if (secProjet) secProjet.style.display = 'block';
                if (secBms) secBms.style.display = 'none';
                const scenSel = document.getElementById('sim-select-scenario');
                const curVal = scenSel ? scenSel.value : 'pluie_decennale';
                window.onChangementScenarioPluie(curVal);
            }
        };

        window.setBMSCumul = function(val) {
            const inp = document.getElementById('sim-bms-cumul-mm');
            if (inp) {
                inp.value = String(val);
                window.onChangementParametresBMS();
            }
        };

        window.onChangementParametresBMS = function() {
            const radJaune = document.getElementById('lbl-bms-vigilance-jaune');
            const radOrange = document.getElementById('lbl-bms-vigilance-orange');
            const radRouge = document.getElementById('lbl-bms-vigilance-rouge');
            const inputVigilance = document.querySelector('input[name="bms-vigilance"]:checked');
            const vigilance = inputVigilance ? inputVigilance.value : 'orange';

            // Ajustement visuel des 3 pilules de vigilance
            [
                { el: radJaune, val: 'jaune', col: '#eab308', bg: 'rgba(234, 179, 8, 0.25)', border: '1.5px solid #eab308' },
                { el: radOrange, val: 'orange', col: '#fb923c', bg: 'rgba(249, 115, 22, 0.25)', border: '1.5px solid #f97316' },
                { el: radRouge, val: 'rouge', col: '#f87171', bg: 'rgba(239, 68, 68, 0.25)', border: '1.5px solid #ef4444' }
            ].forEach(cfg => {
                if (!cfg.el) return;
                if (cfg.val === vigilance) {
                    cfg.el.style.background = cfg.bg;
                    cfg.el.style.border = cfg.border;
                    cfg.el.style.fontWeight = '800';
                } else {
                    cfg.el.style.background = 'rgba(255, 255, 255, 0.04)';
                    cfg.el.style.border = '1px solid rgba(255, 255, 255, 0.12)';
                    cfg.el.style.fontWeight = '600';
                }
            });

            const cumulInput = document.getElementById('sim-bms-cumul-mm');
            const cumul = parseFloat((cumulInput && cumulInput.value) || 30.0);
            const hDeb = document.getElementById('sim-bms-heure-debut') ? document.getElementById('sim-bms-heure-debut').value : '07:00';
            const hFin = document.getElementById('sim-bms-heure-fin') ? document.getElementById('sim-bms-heure-fin').value : '21:00';
            const profil = document.getElementById('sim-bms-profil') ? document.getElementById('sim-bms-profil').value : 'cloche';

            // Calcul de la durée en heures
            let duree = 14.0;
            try {
                const [h1, m1] = hDeb.split(':').map(Number);
                const [h2, m2] = hFin.split(':').map(Number);
                let t1 = h1 + m1 / 60.0;
                let t2 = h2 + m2 / 60.0;
                if (t2 <= t1) t2 += 24.0;
                duree = Math.round((t2 - t1) * 10) / 10;
            } catch (_) {}

            const dureeBadge = document.getElementById('sim-bms-duree-badge');
            if (dureeBadge) dureeBadge.textContent = `⏱️ ${duree} h d'alerte`;

            // Estimation de crête indicative
            let iMaxEstime = 0.0;
            if (profil === 'uniforme') {
                iMaxEstime = Math.round((cumul / Math.max(1.0, duree)) * 10) / 10;
            } else if (profil === 'orage_concentre') {
                iMaxEstime = Math.round(((cumul * 0.75) / 2.0) * 10) / 10;
            } else {
                iMaxEstime = Math.round(((cumul / Math.max(1.0, duree)) * 2.4) * 10) / 10;
            }

            const previewText = document.getElementById('sim-bms-preview-text');
            const previewBox = document.getElementById('sim-bms-preview-note');
            const borderCol = (vigilance === 'rouge') ? '#ef4444' : ((vigilance === 'jaune') ? '#eab308' : '#f97316');
            if (previewBox) previewBox.style.borderLeftColor = borderCol;

            const symbole = (vigilance === 'rouge') ? '🔴' : ((vigilance === 'jaune') ? '🟡' : '🟠');
            if (previewText) {
                previewText.innerHTML = `${symbole} <b>Alerte BMS Vigilance ${vigilance.charAt(0).toUpperCase() + vigilance.slice(1)} :</b> ` +
                    `cumul de <b>${cumul.toFixed(1)} mm</b> prévu entre <b>${hDeb}</b> et <b>${hFin}</b> (${duree} h). ` +
                    `Intensité de crête estimée : <b>${iMaxEstime.toFixed(1)} mm/h</b>.`;
            }

            // Mettre à jour la durée de calcul globale dans la modale
            const dureeSel = document.getElementById('sim-select-duree');
            if (dureeSel) {
                const simDuree = Math.min(24.0, Math.ceil(duree + 1.0));
                let optFound = false;
                for (let i = 0; i < dureeSel.options.length; i++) {
                    if (parseFloat(dureeSel.options[i].value) === simDuree) {
                        dureeSel.selectedIndex = i;
                        optFound = true;
                        break;
                    }
                }
                if (!optFound) {
                    dureeSel.value = simDuree >= 20 ? '24.0' : (simDuree >= 10 ? '12.0' : '6.0');
                }
            }
        };

        window.basculerSaisieTelegrammeBMS = function() {
            const c = document.getElementById('sim-bms-telegramme-container');
            if (c) {
                c.style.display = (c.style.display === 'none' || !c.style.display) ? 'block' : 'none';
                if (c.style.display === 'block') {
                    const txt = document.getElementById('sim-bms-telegramme-texte');
                    if (txt) txt.focus();
                }
            }
        };

        window.analyserEtAppliquerTelegrammeBMS = function() {
            const txtEl = document.getElementById('sim-bms-telegramme-texte');
            const texte = (txtEl && txtEl.value) ? txtEl.value.trim() : '';
            if (!texte) {
                alert("Veuillez coller le texte officiel du bulletin météorologique spécial (ONM).");
                return;
            }

            // 1. Détection du niveau de vigilance (jaune, orange, rouge)
            let vigTrouve = null;
            if (/\b(rouge|red)\b/i.test(texte)) {
                vigTrouve = 'rouge';
            } else if (/\b(orange)\b/i.test(texte)) {
                vigTrouve = 'orange';
            } else if (/\b(jaune|yellow)\b/i.test(texte)) {
                vigTrouve = 'jaune';
            }
            if (vigTrouve) {
                const rad = document.querySelector(`input[name="bms-vigilance"][value="${vigTrouve}"]`);
                if (rad) rad.checked = true;
            }

            // 2. Détection du cumul de pluie (ex: "30 à 50 mm", "40 mm", "20-40 mm")
            const regPlage = /(\d+(?:[.,]\d+)?)\s*(?:à|a|-|\/)\s*(\d+(?:[.,]\d+)?)\s*mm/i;
            const regUnique = /(\d+(?:[.,]\d+)?)\s*mm/i;
            let cumulTrouve = null;

            const matchPlage = texte.match(regPlage);
            if (matchPlage) {
                const c1 = parseFloat(matchPlage[1].replace(',', '.'));
                const c2 = parseFloat(matchPlage[2].replace(',', '.'));
                // Retenir la borne supérieure de l'averse ou la moyenne
                cumulTrouve = Math.max(c1, c2);
            } else {
                const matchUnique = texte.match(regUnique);
                if (matchUnique) {
                    cumulTrouve = parseFloat(matchUnique[1].replace(',', '.'));
                }
            }

            if (cumulTrouve && !isNaN(cumulTrouve) && cumulTrouve > 0) {
                const cumulInput = document.getElementById('sim-bms-cumul-mm');
                if (cumulInput) cumulInput.value = String(Math.round(cumulTrouve));
            }

            // 3. Détection des heures de validité (ex: "de 07h00 à 21h00", "07:00 au 21:00")
            const regHeures = /(?:de|a partir de|du)?\s*(\d{1,2})[h:](\d{2})?\s*(?:à|a|-|au|\/)\s*(\d{1,2})[h:](\d{2})?/i;
            const matchH = texte.match(regHeures);
            if (matchH) {
                const h1 = String(parseInt(matchH[1], 10)).padStart(2, '0');
                const m1 = String(parseInt(matchH[2] || '0', 10)).padStart(2, '0');
                const h2 = String(parseInt(matchH[3], 10)).padStart(2, '0');
                const m2 = String(parseInt(matchH[4] || '0', 10)).padStart(2, '0');

                const debEl = document.getElementById('sim-bms-heure-debut');
                const finEl = document.getElementById('sim-bms-heure-fin');
                if (debEl) debEl.value = `${h1}:${m1}`;
                if (finEl) finEl.value = `${h2}:${m2}`;
            }

            // 4. Détection de date (ex: "12/11/2026", "12-11-2026")
            const regDate = /(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{4})/;
            const matchDate = texte.match(regDate);
            if (matchDate) {
                const j = String(parseInt(matchDate[1], 10)).padStart(2, '0');
                const m = String(parseInt(matchDate[2], 10)).padStart(2, '0');
                const a = matchDate[3];
                const dateEl = document.getElementById('sim-bms-date');
                if (dateEl) dateEl.value = `${a}-${m}-${j}`;
            }

            // Fermer l'encadré et actualiser
            const cont = document.getElementById('sim-bms-telegramme-container');
            if (cont) cont.style.display = 'none';

            window.onChangementParametresBMS();
        };

        window.telechargerOrdreMissionTerrain = function() {
            window.location.href = '/api/v1/simulations/bms/ordre-mission-pdf';
        };

        window.basculerInfobulleBMS = function(event) {
            if (event) event.stopPropagation();
            const pop = document.getElementById('topbar-bms-popover');
            if (!pop) return;
            pop.style.display = (pop.style.display === 'none' || !pop.style.display) ? 'block' : 'none';
        };

        window.fermerInfobulleBMS = function(event) {
            if (event) event.stopPropagation();
            const pop = document.getElementById('topbar-bms-popover');
            if (pop) pop.style.display = 'none';
        };

        // Fermer l'infobulle au clic extérieur
        document.addEventListener('click', function(e) {
            const pop = document.getElementById('topbar-bms-popover');
            const pill = document.getElementById('topbar-bms-pill');
            if (pop && pop.style.display === 'block') {
                if (!pop.contains(e.target) && (!pill || !pill.contains(e.target))) {
                    pop.style.display = 'none';
                }
            }
        });

        window.declencherSimulationSWMM = function() {
            const scen = document.getElementById('sim-select-scenario').value;
            const duree = parseFloat(document.getElementById('sim-select-duree').value);
            const pasRoutage = parseInt(document.getElementById('sim-select-step').value);
            const penteInput = document.getElementById('sim-pente-moyenne');
            let penteVal = null;
            if (penteInput && penteInput.value !== undefined && penteInput.value !== '') {
                penteVal = parseFloat(String(penteInput.value).replace(',', '.'));
            }
            if (isNaN(penteVal) || penteVal === null) penteVal = 1.0;
            const simBassinSel = document.getElementById('sim-select-bassin');
            const simBassinVal = simBassinSel ? simBassinSel.value : '';
            const clusterId = (simBassinVal && !isNaN(Number(simBassinVal))) ? parseInt(simBassinVal, 10) : (simBassinVal || null);
            // Étape 3A : la référence métier `bassin_ref` est la valeur principale
            // transmise ; l'identifiant ordinal reste envoyé pour compatibilité.
            const simOpt = simBassinSel && simBassinSel.selectedOptions ? simBassinSel.selectedOptions[0] : null;
            const bassinRef = (simOpt && simOpt.dataset && simOpt.dataset.bassinRef) ? simOpt.dataset.bassinRef : null;

            if (!clusterId) {
                const statusDiv = document.getElementById('sim-status-message');
                if (statusDiv) {
                    statusDiv.style.display = 'block';
                    statusDiv.innerHTML = '<span style="color:#ef4444;"><i class="fas fa-exclamation-triangle me-1"></i> <b>Règle hydraulique :</b> Veuillez sélectionner un bassin versant sectorisé avant de lancer la simulation.</span>';
                }
                return;
            }

            const chkDeporte = document.getElementById('sim-chk-valider-raccordement');
            const validerRaccord = chkDeporte ? chkDeporte.checked : true;

            const typoSolVal = document.getElementById('sim-select-typologie-sol') ? document.getElementById('sim-select-typologie-sol').value : 'habitat_mixte';
            const impervInpEl = document.getElementById('sim-imperv-pct');
            let impervVal = null;
            if (impervInpEl && impervInpEl.value !== undefined && impervInpEl.value !== '') {
                impervVal = parseFloat(String(impervInpEl.value).replace(',', '.'));
            }
            if (isNaN(impervVal) || impervVal === null || impervVal <= 0) impervVal = null;

            const intensiteInp = document.getElementById('sim-input-intensite-max');
            let intensiteVal = null;
            if (intensiteInp && intensiteInp.value !== undefined && intensiteInp.value !== '') {
                intensiteVal = parseFloat(String(intensiteInp.value).replace(',', '.'));
            }
            if (isNaN(intensiteVal) || intensiteVal === null || intensiteVal < 0) intensiteVal = null;

            const btn = document.getElementById('btn-run-sim-action');
            const statusDiv = document.getElementById('sim-status-message');
            const resultsCard = document.getElementById('sim-results-card');

            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-circle-notch fa-spin me-2"></i> Calcul Saint-Venant en cours...';
            statusDiv.style.display = 'block';
            statusDiv.innerHTML = '⚡ <b>Résolution hydrodynamique EPA SWMM 5.2 en cours...</b><br><small style="color: #94a3b8;">Génération .inp &bull; Équations 1D DYNWAVE &bull; Infiltration Horton</small>';
            resultsCard.style.display = 'none';

            // Activer l'overlay de verrouillage complet et démarrer le chronomètre
            const overlay = document.getElementById('sim-blocking-overlay');
            const chronoEl = document.getElementById('sim-chrono-display');
            const phaseEl = document.getElementById('sim-blocking-phase');
            if (overlay) overlay.style.display = 'flex';
            if (chronoEl) chronoEl.textContent = '00:00.0';
            const simStartTime = Date.now();
            const simChronoInterval = setInterval(() => {
                const elapsedMs = Date.now() - simStartTime;
                const totalSec = Math.floor(elapsedMs / 1000);
                const mins = String(Math.floor(totalSec / 60)).padStart(2, '0');
                const secs = String(totalSec % 60).padStart(2, '0');
                const tenths = Math.floor((elapsedMs % 1000) / 100);
                if (chronoEl) chronoEl.textContent = `${mins}:${secs}.${tenths}`;

                if (phaseEl) {
                    if (totalSec < 2) {
                        phaseEl.innerHTML = `<i class="fas fa-circle-notch fa-spin" style="color: #38bdf8;"></i><span>Génération du modèle .INP &amp; hydrologie Voronoï...</span>`;
                    } else if (totalSec < 5) {
                        phaseEl.innerHTML = `<i class="fas fa-cog fa-spin" style="color: #38bdf8;"></i><span>Résolution équations 1D de Saint-Venant (PySWMM)...</span>`;
                    } else {
                        phaseEl.innerHTML = `<i class="fas fa-robot" style="color: #a855f7;"></i><span>Diagnostic causal multi-agents &amp; cartographie...</span>`;
                    }
                }
            }, 100);

            function arreterOverlaySimulation() {
                clearInterval(simChronoInterval);
                if (overlay) overlay.style.display = 'none';
            }

            if (typeof window.mettreAJourIndicateurBassin === 'function') {
                window.mettreAJourIndicateurBassin(clusterId, { status: 'simulating' });
            }

            const token = localStorage.getItem('swmm_access_token');
            const headers = { 'Content-Type': 'application/json' };
            if (token) headers['Authorization'] = `Bearer ${token}`;

            const stSel = document.getElementById('sim-select-station');
            const stationId = stSel ? stSel.value : 'chlef_anrh_siege';

            // Récupérer les raccordements d'ouvrages orphelins cochés
            const raccordementsSelectionnes = [];
            const chksOrph = document.querySelectorAll('.sim-chk-ouvrage-orphelin');
            const candidatsOrph = window._ouvragesOrphelinsCandidats || [];
            chksOrph.forEach(chk => {
                if (chk.checked) {
                    const idx = parseInt(chk.getAttribute('data-index'), 10);
                    if (candidatsOrph[idx]) {
                        raccordementsSelectionnes.push(candidatsOrph[idx]);
                    }
                }
            });
            window._ouvragesOrphelinsCandidatsSelectionnes = raccordementsSelectionnes;

            const isBms = (window._modePluieActif === 'bms');
            let bmsVigilance = 'orange';
            let bmsCumul = 30.0;
            let bmsHDeb = '07:00';
            let bmsHFin = '21:00';
            let bmsProfil = 'cloche';

            if (isBms) {
                const inputVig = document.querySelector('input[name="bms-vigilance"]:checked');
                bmsVigilance = inputVig ? inputVig.value : 'orange';
                bmsCumul = parseFloat((document.getElementById('sim-bms-cumul-mm') && document.getElementById('sim-bms-cumul-mm').value) || 30.0);
                bmsHDeb = document.getElementById('sim-bms-heure-debut') ? document.getElementById('sim-bms-heure-debut').value : '07:00';
                bmsHFin = document.getElementById('sim-bms-heure-fin') ? document.getElementById('sim-bms-heure-fin').value : '21:00';
                bmsProfil = document.getElementById('sim-bms-profil') ? document.getElementById('sim-bms-profil').value : 'cloche';
            }

            const payloadBody = {
                scenario_key: isBms ? 'bms_alerte' : scen,
                duree_heures: duree,
                pas_routage_sec: pasRoutage,
                pente_moyenne_pct: penteVal,
                cluster_id: clusterId,
                bassin_ref: bassinRef,
                buffer_m: window._activeBufferM || 35.0,
                valider_raccordement: validerRaccord,
                typologie_sol: typoSolVal,
                imperv_pct: impervVal,
                intensite_max_mmh: isBms ? null : intensiteVal,
                station_id: stationId,
                raccordements_orphelins: raccordementsSelectionnes,
                bms_mode: isBms,
                bms_vigilance: bmsVigilance,
                bms_cumul_mm: bmsCumul,
                bms_heure_debut: bmsHDeb,
                bms_heure_fin: bmsHFin,
                bms_profil: bmsProfil
            };

            fetch('/api/v1/simulations/run', {
                method: 'POST',
                headers: headers,
                credentials: 'include',
                body: JSON.stringify(payloadBody)
            })
            .then(async r => {
                if (!r.ok) {
                    let errMsg = `Erreur ${r.status}`;
                    try {
                        const rawText = await r.text();
                        try {
                            const errData = JSON.parse(rawText);
                            errMsg = errData.detail || errData.message || errMsg;
                        } catch (_) {
                            if (rawText && rawText.length < 250) errMsg = rawText;
                        }
                    } catch (__) {}
                    if (r.status === 401 || r.status === 403) {
                        errMsg = "Session expirée. Veuillez rafraîchir la page ou vous reconnecter.";
                    } else if (r.status === 500 && (!errMsg || errMsg === 'Erreur 500')) {
                        errMsg = "Erreur interne 500 du serveur lors du calcul SWMM 5.2.";
                    }
                    throw new Error(errMsg);
                }
                return r.json();
            })
            .then(data => {
                arreterOverlaySimulation();
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-redo me-2"></i> Relancer la simulation';
                if (data && data.cached) {
                    statusDiv.style.display = 'block';
                    statusDiv.innerHTML = '<span style="color: #10b981; font-weight: 600;"><i class="fas fa-bolt me-1"></i> Résultats restaurés depuis la sauvegarde (paramètres inchangés)</span>';
                    setTimeout(() => { if (statusDiv && statusDiv.innerHTML && statusDiv.innerHTML.includes('restaurés')) statusDiv.style.display = 'none'; }, 4500);
                } else {
                    statusDiv.style.display = 'none';
                }

                if (!window._simulationsCache) window._simulationsCache = {};
                if (data && data.meta && data.meta.cluster_id) {
                    window._simulationsCache[String(data.meta.cluster_id)] = data;
                }
                if (data && data.meta && data.meta.bassin_nom) {
                    window._simulationsCache[String(data.meta.bassin_nom)] = data;
                }
                if (data && data.meta && data.meta.cluster_nom) {
                    window._simulationsCache[String(data.meta.cluster_nom)] = data;
                }
                if (clusterId) {
                    window._simulationsCache[String(clusterId)] = data;
                }
                window._dernierResultatSimulation = data;

                // Actualiser le bandeau d'alerte BMS dans la modale
                const bmsBanner = document.getElementById('sim-bms-alert-banner');
                const bmsInfo = (data && data.meta && data.meta.bms_info) || (data && data.kpis && data.kpis.bms_info);
                if (bmsBanner) {
                    if (bmsInfo) {
                        bmsBanner.style.display = 'block';
                        const bTitle = document.getElementById('bms-banner-title');
                        const bBadge = document.getElementById('bms-banner-badge');
                        const bDesc = document.getElementById('bms-banner-desc');
                        const vig = (bmsInfo.vigilance || 'orange').toLowerCase();
                        const sym = bmsInfo.symbole || (vig === 'rouge' ? '🔴' : (vig === 'jaune' ? '🟡' : '🟠'));
                        const col = vig === 'rouge' ? '#ef4444' : (vig === 'jaune' ? '#eab308' : '#f97316');

                        bmsBanner.style.borderColor = col;
                        bmsBanner.style.background = vig === 'rouge' ? 'rgba(239, 68, 68, 0.2)' : (vig === 'jaune' ? 'rgba(234, 179, 8, 0.2)' : 'rgba(249, 115, 22, 0.2)');
                        if (bTitle) {
                            bTitle.style.color = col;
                            bTitle.innerHTML = `${sym} Bulletin météorologique spécial (BMS ONM) — Vigilance ${vig.charAt(0).toUpperCase() + vig.slice(1)}`;
                        }
                        if (bBadge) {
                            bBadge.style.background = col;
                            bBadge.textContent = `Alerte de crise (${vig.toUpperCase()})`;
                        }
                        if (bDesc) {
                            bDesc.innerHTML = `Précipitations de <b>${bmsInfo.cumul_mm || 30} mm</b> modélisées sur <b>${bmsInfo.duree_heures || 14} h</b> (${bmsInfo.heure_debut || '07:00'} → ${bmsInfo.heure_fin || '21:00'}). Pic estimé : <b>${(bmsInfo.intensite_pic_mmh || 0).toFixed(1)} mm/h</b>.`;
                        }
                    } else {
                        bmsBanner.style.display = 'none';
                    }
                }

                // Actualiser le badge discret BMS dans la barre supérieure (Header)
                const topbarBmsPill = document.getElementById('topbar-bms-pill');
                const topbarBmsLabel = document.getElementById('topbar-bms-label');
                const topbarBmsPopover = document.getElementById('topbar-bms-popover-content');
                const actionBmsMission = document.getElementById('action-item-bms-mission');

                if (bmsInfo) {
                    const vig = (bmsInfo.vigilance || 'orange').toLowerCase();
                    const sym = bmsInfo.symbole || (vig === 'rouge' ? '🔴' : (vig === 'jaune' ? '🟡' : '🟠'));
                    const col = vig === 'rouge' ? '#ef4444' : (vig === 'jaune' ? '#eab308' : '#f97316');
                    const dText = bmsInfo.date_texte || '12 nov.';

                    if (topbarBmsPill) {
                        topbarBmsPill.style.display = 'inline-flex';
                        topbarBmsPill.style.borderColor = col;
                        topbarBmsPill.style.color = col;
                    }
                    if (topbarBmsLabel) {
                        topbarBmsLabel.textContent = `BMS actif : ${dText} (${bmsInfo.heure_debut}-${bmsInfo.heure_fin}) • ${bmsInfo.cumul_mm} mm`;
                    }
                    if (topbarBmsPopover) {
                        const qPeak = ((data.kpis && data.kpis.peak_outflow_m3s) || (data && data.peak_outflow_m3s) || 0).toFixed(3);
                        const flCount = (data.kpis && data.kpis.flooded_nodes_count) || (data && data.flooded_nodes_count) || 0;
                        const surCount = (data.kpis && data.kpis.surcharged_nodes_count) || (data && data.surcharged_nodes_count) || 0;

                        topbarBmsPopover.innerHTML = `
                            <div style="margin-bottom: 6px;"><b>Vigilance :</b> <span style="color: ${col}; font-weight: 800;">${sym} ${vig.toUpperCase()}</span></div>
                            <div style="margin-bottom: 6px;"><b>Épisode :</b> ${dText} de ${bmsInfo.heure_debut} à ${bmsInfo.heure_fin} (${bmsInfo.duree_heures} h)</div>
                            <div style="margin-bottom: 6px;"><b>Précipitations :</b> ${bmsInfo.cumul_mm} mm cumulés (crête ${(bmsInfo.intensite_pic_mmh || 0).toFixed(1)} mm/h)</div>
                            <div style="margin-bottom: 6px;"><b>Débit à l'exutoire :</b> <span style="color: #38bdf8; font-weight: 700;">${qPeak} m³/s</span></div>
                            <div style="color: #fca5a5;"><b>Diagnostic critique :</b> ${flCount} regard(s) débordant(s), ${surCount} en charge</div>
                        `;
                    }
                    if (actionBmsMission) {
                        actionBmsMission.classList.remove('disabled');
                        actionBmsMission.style.opacity = '1';
                        actionBmsMission.style.pointerEvents = 'auto';
                        actionBmsMission.style.cursor = 'pointer';
                    }
                } else {
                    if (topbarBmsPill) topbarBmsPill.style.display = 'none';
                    const pop = document.getElementById('topbar-bms-popover');
                    if (pop) pop.style.display = 'none';
                    if (actionBmsMission) {
                        actionBmsMission.classList.add('disabled');
                        actionBmsMission.style.opacity = '0.45';
                        actionBmsMission.style.pointerEvents = 'none';
                        actionBmsMission.style.cursor = 'not-allowed';
                    }
                }
                
                if (typeof window.mettreAJourIndicateurBassin === 'function') {
                    const kp = (data && data.kpis) || {};
                    const qMax = (typeof kp.peak_outflow_m3s === 'number') ? kp.peak_outflow_m3s : 0.0;
                    const qExutoire = (typeof kp.q_exutoire_m3s === 'number') ? kp.q_exutoire_m3s : qMax;
                    const qDerive = (typeof kp.q_derive_m3s === 'number') ? kp.q_derive_m3s : ((typeof kp.q_deleste_m3s === 'number') ? kp.q_deleste_m3s : 0.0);
                    const qGenere = (typeof kp.q_genere_m3s === 'number') ? kp.q_genere_m3s : (qExutoire + qDerive);
                    const nbRacc = kp.nb_ouvrages_raccordes || 0;
                    const tauxDerive = (typeof kp.taux_derive_pct === 'number') ? kp.taux_derive_pct : (qGenere > 0 ? ((qDerive / qGenere) * 100.0) : 0.0);
                    const tauxExutoire = (typeof kp.taux_exutoire_pct === 'number') ? kp.taux_exutoire_pct : Math.max(0, 100.0 - tauxDerive);

                    window.mettreAJourIndicateurBassin(clusterId, { 
                        status: 'simulated', 
                        peak_flow: qMax,
                        q_exutoire_m3s: qExutoire,
                        q_derive_m3s: qDerive,
                        q_genere_m3s: qGenere,
                        taux_derive_pct: tauxDerive,
                        taux_exutoire_pct: tauxExutoire,
                        nb_ouvrages_raccordes: nbRacc
                    });
                }

                // Mettre à jour et afficher les couches thématiques Leaflet
                afficherResultatsSimulation(data);

                // Fermeture automatique de la fenêtre modale de simulation
                if (typeof window.fermerModalSimulation === 'function') {
                    window.fermerModalSimulation();
                }

                // Déclencher le zoom automatique à grande échelle pour visualiser le résultat
                if (typeof window.zoomerSurZoneSimulee === 'function') {
                    setTimeout(() => {
                        window.zoomerSurZoneSimulee(data, 19);
                    }, 100);
                }
            })
            .catch(err => {
                arreterOverlaySimulation();
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-play me-2"></i> Lancer la Simulation SWMM 5.2';
                statusDiv.style.display = 'block';
                statusDiv.innerHTML = `<span style="color: #ef4444;"><i class="fas fa-exclamation-triangle me-1"></i> Erreur : ${err.message}</span>`;
                if (typeof window.mettreAJourIndicateurBassin === 'function') {
                    window.mettreAJourIndicateurBassin(clusterId, { status: 'selected' });
                }
            });
        };
