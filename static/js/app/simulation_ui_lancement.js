/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-27
 * Date de modification : 2026-11-27
 * Objet : Declenchement de la simulation SWMM et gestion DWF dans le lancement (extrait de static/js/app/simulation_ui.js)
 * ================================================================================
 */

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

            // LOT P1.5.3 — DWF : la valeur de l'interrupteur est transmise
            // explicitement (true/false) ; null si la section n'a pas pu
            // être évaluée → le serveur applique sa règle par défaut.
            const chkDwf = document.getElementById('sim-chk-dwf-actif');
            const dwfActif = (chkDwf && !chkDwf.disabled) ? chkDwf.checked : null;

            // Option C (SHP.md §7bis) — altimétrie terrain : opt-in explicite.
            const chkAlt = document.getElementById('sim-chk-altimetrie-terrain');
            const altimetrieTerrain = chkAlt ? chkAlt.checked : false;

            const payloadBody = {
                scenario_key: isBms ? 'bms_alerte' : scen,
                dwf_actif: dwfActif,
                altimetrie_terrain: altimetrieTerrain,
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
                bms_profil: bmsProfil,
                etat_reseau: (typeof window.lireConfigurationEtatReseau === 'function') ? window.lireConfigurationEtatReseau() : null
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
                    let errDwfIncompatibles = null;
                    try {
                        const rawText = await r.text();
                        try {
                            const errData = JSON.parse(rawText);
                            // LOT P1.5.3 — 422 compatibilité DWF : le detail
                            // est un objet {message, apports_incompatibles}.
                            if (errData && errData.detail && typeof errData.detail === 'object') {
                                if (Array.isArray(errData.detail.apports_incompatibles)) {
                                    errDwfIncompatibles = errData.detail.apports_incompatibles;
                                }
                                errMsg = errData.detail.message || errMsg;
                            } else {
                                errMsg = (errData && (errData.detail || errData.message)) || errMsg;
                            }
                        } catch (_) {
                            if (rawText && rawText.length < 250) errMsg = rawText;
                        }
                    } catch (__) {}
                    if (r.status === 401 || r.status === 403) {
                        errMsg = "Session expirée. Veuillez rafraîchir la page ou vous reconnecter.";
                    } else if (r.status === 500 && (!errMsg || errMsg === 'Erreur 500')) {
                        errMsg = "Erreur interne 500 du serveur lors du calcul SWMM 5.2.";
                    }
                    const err = new Error(errMsg);
                    err.dwfIncompatibles = errDwfIncompatibles;
                    throw err;
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

                // Rafraîchir la fiabilité du bassin dans le sélecteur
                if (window._fiabiliteParBassin && clusterId) {
                    const _cidF = String(data && data.meta && data.meta.cluster_id !== undefined && data.meta.cluster_id !== null ? data.meta.cluster_id : clusterId);
                    window._fiabiliteParBassin[_cidF] = data;
                }
                if (typeof window._decorerOptionsFiabilite === 'function') {
                    window._decorerOptionsFiabilite();
                }

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
                        nb_ouvrages_raccordes: nbRacc,
                        provenance: data.provenance,
                        kpis: data.kpis,
                        meta: data.meta
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

                // Ouverture automatique de la fenêtre dédiée des résultats si préférence active (par défaut activée)
                const autoOpenPref = localStorage.getItem('swmm_auto_open_results');
                if (autoOpenPref !== 'false' && typeof window.ouvrirModalResultatsSimulation === 'function') {
                    setTimeout(() => {
                        window.ouvrirModalResultatsSimulation();
                    }, 350);
                }
            })
            .catch(err => {
                arreterOverlaySimulation();
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-play me-2"></i> Lancer la Simulation SWMM 5.2';
                statusDiv.style.display = 'block';
                if (err && Array.isArray(err.dwfIncompatibles) && err.dwfIncompatibles.length > 0) {
                    // LOT P1.5.3 — incompatibilité DWF : message précis +
                    // accès direct au panneau de réconciliation. Aucune
                    // relance automatique : décision explicite de l'ingénieur.
                    const n = err.dwfIncompatibles.length;
                    const details = err.dwfIncompatibles.slice(0, 4).map(d =>
                        `• apport ${d.apport_id != null ? d.apport_id : '?'} (nœud ${d.node_id || '?'}) : ${d.motif || d.code || 'incompatible'}${d.code ? ' [' + d.code + ']' : ''}`
                    ).join('<br>');
                    const suite = n > 4 ? `<br><small>… et ${n - 4} autre(s)</small>` : '';
                    statusDiv.innerHTML =
                        `<span style="color:#fbbf24;"><i class="fas fa-exclamation-triangle me-1"></i> <b>Apports DWF incompatibles (${n})</b> — la simulation n'a pas été lancée.</span><br>` +
                        `<small style="color:#cbd5e1; display:block; margin:6px 0;">${details}${suite}</small>` +
                        `<button type="button" onclick="ouvrirModalApportsDwf()" style="background: rgba(245,158,11,0.2); border: 1px solid rgba(245,158,11,0.6); color: #fbbf24; border-radius: 6px; padding: 5px 12px; font-size: 0.76rem; font-weight: 700; cursor: pointer;">
                            <i class="fas fa-tools me-1"></i> Ouvrir le panneau de réconciliation DWF
                        </button>`;
                } else {
                    statusDiv.innerHTML = `<span style="color: #ef4444;"><i class="fas fa-exclamation-triangle me-1"></i> Erreur : ${err.message}</span>`;
                }
                if (typeof window.mettreAJourIndicateurBassin === 'function') {
                    window.mettreAJourIndicateurBassin(clusterId, { status: 'selected' });
                }
            });
        };
