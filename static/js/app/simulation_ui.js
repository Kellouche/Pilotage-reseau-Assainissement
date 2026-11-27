/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-27
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
                    if (typeof window.actualiserLegendeDwf === 'function') {
                        window.actualiserLegendeDwf(window._dernierResultatSimulation);
                    }
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

        // ==========================================
        // LOT P1.5.3 — APPORTS DWF DANS LE LANCEMENT
        // ==========================================
        // Les compteurs proviennent des API existantes (/network/datasets,
        // /apports?actif_seulement, /apports/a-reconcilier) : aucune règle
        // de compatibilité n'est dupliquée côté client.
        window._dwfSimulationInfo = { charge: false, actifs: 0, compatibles: 0, incompatibles: 0, projetId: null };

        window.chargerInfosDwfSimulation = async function(clusterIdParam) {
            const section = document.getElementById('sim-dwf-section');
            const stats = document.getElementById('sim-dwf-stats');
            const chk = document.getElementById('sim-chk-dwf-actif');
            const alerte = document.getElementById('sim-dwf-alerte-incompat');
            const alerteTxt = document.getElementById('sim-dwf-alerte-texte');
            const info = window._dwfSimulationInfo;
            info.charge = false;
            if (!section || !stats) return;

            const simBassinEl = document.getElementById('sim-select-bassin');
            const cidRaw = (clusterIdParam !== undefined && clusterIdParam !== null)
                ? clusterIdParam
                : (simBassinEl ? simBassinEl.value : (window._selectedClusterId || ''));
            const cidClean = String(cidRaw || '').trim();
            const cidQuery = (cidClean && cidClean.toLowerCase() !== 'tous') ? `&cluster_id=${encodeURIComponent(cidClean)}` : '';

            const token = localStorage.getItem('swmm_access_token');
            const headers = {};
            if (token) headers['Authorization'] = `Bearer ${token}`;
            const j = { headers: headers, credentials: 'include' };

            try {
                const ds = await fetch('/api/v1/network/datasets?_t=' + Date.now(), j).then(r => r.ok ? r.json() : null);
                const ap = ds && ds.active_project;
                if (!ap || !ap.id) {
                    section.style.display = 'block';
                    stats.innerHTML = '<i class="fas fa-info-circle me-1" style="color:#94a3b8;"></i> Aucun projet actif : les apports DWF ne sont pas évalués.';
                    if (chk) { chk.checked = false; chk.disabled = true; }
                    if (alerte) alerte.style.display = 'none';
                    return;
                }
                info.projetId = ap.id;
                const pid = `project_id=${encodeURIComponent(ap.id)}`;
                const [apports, recon] = await Promise.all([
                    fetch((typeof window._urlAvecSnapshot === 'function' ? window._urlAvecSnapshot(`/api/v1/apports?${pid}&actif_seulement=true${cidQuery}`) : `/api/v1/apports?${pid}&actif_seulement=true${cidQuery}`), j).then(r => r.ok ? r.json() : []),
                    fetch(`/api/v1/apports/a-reconcilier?${pid}${cidQuery}`, j).then(r => r.ok ? r.json() : null),
                ]);
                const actifs = Array.isArray(apports) ? apports : [];
                const incompatibles = (recon && Array.isArray(recon.incompatibles)) ? recon.incompatibles : [];
                const nIncompat = (recon && typeof recon.count === 'number') ? recon.count : incompatibles.length;
                info.actifs = actifs.length;
                info.incompatibles = nIncompat;
                info.compatibles = Math.max(0, actifs.length - nIncompat);
                info.charge = true;

                section.style.display = 'block';
                if (chk) chk.disabled = false;

                const scopeLib = cidQuery ? 'sur ce bassin' : 'pour ce projet';
                if (actifs.length === 0) {
                    stats.innerHTML = `<i class="fas fa-info-circle me-1" style="color:#6ee7b7;"></i> <b>0 apport DWF actif</b> ${scopeLib} — comportement historique inchangé.`;
                    if (chk) chk.checked = false;
                } else {
                    stats.innerHTML =
                        `<b style="color:#34d399;">${actifs.length} apport(s) actif(s)</b> ${scopeLib} — ` +
                        `<b style="color:#6ee7b7;">${info.compatibles} compatible(s)</b> avec le réseau courant — ` +
                        `<b style="color:${nIncompat > 0 ? '#fbbf24' : '#6ee7b7'};">${nIncompat} incompatible(s)</b>.` +
                        (nIncompat > 0 ? ' La simulation sera refusée tant que les apports incompatibles ne sont pas réconciliés.' : '');
                    if (chk) chk.checked = (info.compatibles > 0 || nIncompat === 0);
                }

                if (alerte && alerteTxt) {
                    if (nIncompat > 0) {
                        alerteTxt.textContent = `${nIncompat} apport(s) DWF incompatible(s) avec la version du réseau — réconciliation requise avant injection.`;
                        alerte.style.display = 'block';
                    } else {
                        alerte.style.display = 'none';
                    }
                }
            } catch (err) {
                console.warn('[DWF] Évaluation des apports impossible :', err);
                section.style.display = 'block';
                stats.innerHTML = '<i class="fas fa-exclamation-triangle me-1" style="color:#fbbf24;"></i> Apports DWF non évalués (API indisponible) — le comportement par défaut du serveur s\'applique.';
                if (chk) { chk.checked = false; chk.disabled = false; }
                if (alerte) alerte.style.display = 'none';
            }
        };
