/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Mise à jour des indicateurs décisionnels, débits hydrologiques et KPIs SWMM
 * ================================================================================
 */

window.mettreAJourIndicateursEtKpisSimulation = function(data) {
    if (!data) return;
    const k = data.kpis || {};
    const coh = k.coherence_hydrologique || {};

            // 3. Mettre à jour les indicateurs KPIs dans la modale
            if (data.kpis) {
                const k = data.kpis;
                const errVal = k.routing_continuity_error_pct || 0;
                const contEl = document.getElementById('kpi-continuity');
                if (contEl) contEl.innerText = (errVal > 0 ? '+' : '') + window.formaterNombre(errVal, 2) + ' %';
                const peakEl = document.getElementById('kpi-peak-outflow');
                if (peakEl) peakEl.innerText = window.formaterNombre(k.peak_outflow_m3s || 0, 3) + ' m³/s';
                
                const peakTimeEl = document.getElementById('kpi-peak-time');
                if (peakTimeEl) peakTimeEl.innerText = k.peak_time_str || '--';

                const maxVelEl = document.getElementById('kpi-max-velocity');
                if (maxVelEl) {
                    const vVal = k.max_velocity_ms || 0;
                    maxVelEl.innerHTML = `${window.formaterNombre(vVal, 2)} m/s <small style="font-size:0.65rem; display:block; color:${k.autocurage_color || '#34d399'}; font-weight:600;">${k.autocurage_statut || 'Autocurage'}</small>`;
                }

                // Ligne 2 : Volumes et Surcharges
                const vRunoffEl = document.getElementById('kpi-vol-runoff');
                if (vRunoffEl) {
                    const rVal = k.total_runoff_volume_m3;
                    vRunoffEl.innerText = (rVal !== undefined && rVal !== null ? Math.round(rVal).toLocaleString('fr-FR') : '--') + ' m³';
                }

                const vInfilEl = document.getElementById('kpi-vol-infil');
                if (vInfilEl) {
                    const iVal = k.total_infiltration_volume_m3;
                    vInfilEl.innerText = (iVal !== undefined && iVal !== null ? Math.round(iVal).toLocaleString('fr-FR') : '--') + ' m³';
                }

                const cEffEl = document.getElementById('kpi-coeff-eff');
                if (cEffEl) cEffEl.innerText = window.formaterNombre(k.effective_runoff_coeff !== undefined ? k.effective_runoff_coeff : 0.70, 2);

                const surchPctEl = document.getElementById('kpi-surcharge-pct');
                if (surchPctEl) surchPctEl.innerText = `${window.formaterNombre(k.surcharged_length_pct || 0, 1)} % (${window.formaterNombre(k.surcharged_length_m || 0, 1)} m)`;

                // Contrôle de cohérence Pluie-Débit (Méthode Rationnelle)
                const coh = k.coherence_pluie_debit;
                if (coh) {
                    const badgeEl = document.getElementById('kpi-coherence-badge');
                    if (badgeEl) {
                        badgeEl.innerText = coh.badge || coh.statut;
                        badgeEl.style.background = (coh.color || '#10b981') + '22';
                        badgeEl.style.color = coh.color || '#10b981';
                        badgeEl.style.border = `1px solid ${coh.color || '#10b981'}55`;
                    }
                    const qSimEl = document.getElementById('kpi-coh-qsim');
                    if (qSimEl) qSimEl.innerText = `${window.formaterNombre(coh.q_simule_m3s, 3)} m³/s`;
                    const qRatEl = document.getElementById('kpi-coh-qrat');
                    if (qRatEl) qRatEl.innerText = `${window.formaterNombre(coh.q_rationnel_m3s, 3)} m³/s (Ratio: ${coh.ratio})`;
                    const msgEl = document.getElementById('kpi-coherence-msg');
                    if (msgEl) msgEl.innerText = coh.message;
                }

                // Module Bilan Hydraulique & Ouvrages Spéciaux : Mise à jour indicateur dans la modale
                const orphBox = document.getElementById('sim-orphelin-kpi-box');
                if (orphBox) {
                    const qDerive = (data.kpis && typeof data.kpis.q_derive_m3s === 'number') ? data.kpis.q_derive_m3s : ((data.kpis && typeof data.kpis.q_deleste_m3s === 'number') ? data.kpis.q_deleste_m3s : 0.0);
                    const qExutoire = (data.kpis && typeof data.kpis.q_exutoire_m3s === 'number') ? data.kpis.q_exutoire_m3s : ((data.kpis && typeof data.kpis.peak_outflow_m3s === 'number') ? data.kpis.peak_outflow_m3s : 0.0);
                    const qGenere = (data.kpis && typeof data.kpis.q_genere_m3s === 'number') ? data.kpis.q_genere_m3s : (qExutoire + qDerive);
                    const nbOrph = (data.kpis && data.kpis.nb_ouvrages_raccordes) || 0;
                    const tauxDerive = (data.kpis && typeof data.kpis.taux_derive_pct === 'number') ? data.kpis.taux_derive_pct : (qGenere > 0 ? ((qDerive / qGenere) * 100.0) : 0.0);
                    const tauxExutoire = (data.kpis && typeof data.kpis.taux_exutoire_pct === 'number') ? data.kpis.taux_exutoire_pct : Math.max(0, 100.0 - tauxDerive);

                    const qGenereStr = window.formaterNombre(qGenere, 3);
                    const qExutoireStr = window.formaterNombre(qExutoire, 3);
                    const qDeriveStr = window.formaterNombre(qDerive, 3);
                    const tauxDeriveStr = window.formaterNombre(tauxDerive, 1);
                    const tauxExutoireStr = window.formaterNombre(tauxExutoire, 1);

                    orphBox.style.display = 'block';
                    const bEl = document.getElementById('kpi-orphelin-badge');
                    const gEl = document.getElementById('kpi-orphelin-qgenere');
                    const eEl = document.getElementById('kpi-orphelin-qexutoire');
                    const qEl = document.getElementById('kpi-orphelin-qdeleste');
                    const dEl = document.getElementById('kpi-orphelin-desc');

                    if (gEl) gEl.innerText = `${qGenereStr} m³/s`;
                    if (eEl) eEl.innerText = `${qExutoireStr} m³/s (${tauxExutoireStr}%)`;

                    if (qDerive > 0) {
                        if (bEl) {
                            bEl.innerText = `Soulagement réseau : ${tauxDeriveStr}%`;
                            bEl.style.background = 'rgba(6, 182, 212, 0.25)';
                            bEl.style.color = '#22d3ee';
                            bEl.style.borderColor = 'rgba(6, 182, 212, 0.5)';
                        }
                        if (qEl) qEl.innerText = `${qDeriveStr} m³/s (${tauxDeriveStr}%)`;
                        if (dEl) dEl.innerHTML = `<i class="fas fa-check-circle text-emerald-400 me-1"></i> <b>${nbOrph} ouvrage(s) spécial(aux) actif(s)</b> : ${qDeriveStr} m³/s captés (${tauxDeriveStr}% du débit produit), soulageant d'autant le collecteur principal.`;
                    } else {
                        if (bEl) {
                            bEl.innerText = `Soulagement réseau : 0,0%`;
                            bEl.style.background = 'rgba(16, 185, 129, 0.2)';
                            bEl.style.color = '#34d399';
                            bEl.style.borderColor = 'rgba(16, 185, 129, 0.4)';
                        }
                        if (qEl) qEl.innerText = `0,000 m³/s (0,0%)`;
                        if (dEl) dEl.innerHTML = `<i class="fas fa-info-circle text-sky-400 me-1"></i> <b>Scénario sans ouvrage spécial raccordé</b> : 100,0% du débit produit (${qGenereStr} m³/s) transite vers le collecteur et l'exutoire principal.`;
                    }
                }

                // Double Échelle de Surface : Urbaine Drainée vs Impluvium Convexe
                const surfUrb = document.getElementById('kpi-surf-urbaine');
                if (surfUrb) surfUrb.innerText = `${(data.meta && data.meta.total_area_ha) ? data.meta.total_area_ha : '--'} ha`;
                const ratioDrain = document.getElementById('kpi-ratio-drainage');
                if (ratioDrain) ratioDrain.innerText = `(Ratio: ${data.meta && data.meta.ratio_drainage_pct ? data.meta.ratio_drainage_pct : 55} %)`;

                // Données hydro-météorologiques certifiées (ANRH / UHBC)
                const pluvioStation = (data.kpis && data.kpis.pluvio_station) || (data.meta && data.meta.pluvio_station) || 'Station ANRH Chlef Siège (010501)';
                const pluvioPeriode = (data.kpis && data.kpis.pluvio_periode_retour) || (data.meta && data.meta.pluvio_periode_retour) || 'T = 10 ans (Décennale)';
                const pluvioImax = (data.kpis && data.kpis.pluvio_intensite_max_mmh) !== undefined ? data.kpis.pluvio_intensite_max_mmh : ((data.meta && data.meta.pluvio_intensite_max_mmh) || 74.9);
                const pluvioPtot = (data.kpis && data.kpis.pluvio_hauteur_totale_mm) || (data.meta && data.meta.pluvio_hauteur_totale_mm) || 42.8;
                const pluvioMontana = (data.kpis && data.kpis.pluvio_montana) || (data.meta && data.meta.pluvio_montana) || 'I(t) = 9.334 · t^(-0.745)';
                const pluvioSource = (data.kpis && data.kpis.pluvio_source) || (data.meta && data.meta.pluvio_source) || 'ANRH Antenne Chlef / UHBC Laboratoire Eau & Environnement (Code 010501)';

                const badgeStEl = document.getElementById('kpi-pluvio-station-badge');
                if (badgeStEl) badgeStEl.innerText = pluvioStation;
                const perEl = document.getElementById('kpi-pluvio-periode');
                if (perEl) perEl.innerText = pluvioPeriode;
                const imaxEl = document.getElementById('kpi-pluvio-imax');
                if (imaxEl) imaxEl.innerText = `${Number(pluvioImax).toFixed(1)} mm/h`;
                const ptotEl = document.getElementById('kpi-pluvio-ptot');
                if (ptotEl) ptotEl.innerText = `${Number(pluvioPtot).toFixed(1)} mm`;
                const montEl = document.getElementById('kpi-pluvio-montana');
                if (montEl) montEl.innerText = pluvioMontana;
                const srcEl = document.getElementById('kpi-pluvio-source-note');
                if (srcEl) srcEl.innerHTML = `<i class="fas fa-database me-1" style="color: #38bdf8;"></i> ${pluvioSource}`;
            }

            const resultsCard = document.getElementById('sim-results-card');
            if (resultsCard) {
                const bassinTitle = document.getElementById('sim-results-bassin-title');
                if (bassinTitle) {
                    if (data.meta && data.meta.cluster_nom) {
                        const typoInfo = data.meta.typologie_nom ? ` &bull; 🏷️ ${data.meta.typologie_nom}` : '';
                        bassinTitle.innerHTML = `<i class="fas fa-sitemap me-1"></i> Périmètre simulé : <b>${data.meta.cluster_nom}</b> (Bassin ${data.meta.cluster_id}) &bull; ${data.meta.junctions_count + 1} regards, ${data.meta.conduits_count} conduites (${data.meta.total_area_ha} ha)${typoInfo}`;
                        bassinTitle.style.display = 'block';
                    } else {
                        const typoInfo = data.meta && data.meta.typologie_nom ? ` &bull; 🏷️ ${data.meta.typologie_nom}` : '';
                        bassinTitle.innerHTML = `<i class="fas fa-globe me-1"></i> Périmètre simulé : <b>Réseau Complet</b> &bull; ${data.meta ? data.meta.conduits_count : ''} conduites${typoInfo}`;
                        bassinTitle.style.display = 'block';
                    }
                }
                resultsCard.style.display = 'block';

                // Personnaliser le nom du fichier .INP et .RPT à télécharger avec le nom du réseau
                const projNom = (window._rawNetworkData && window._rawNetworkData.project_name) || (data.meta && data.meta.project_name) || 'modele_swmm';
                const bassinNom = (data.meta && (data.meta.bassin_nom || data.meta.cluster_nom)) || '';
                const baseNomFichier = (projNom + (bassinNom ? '_' + bassinNom : '')).replace(/[^\w\-_.]+/g, '_').replace(/_+/g, '_').replace(/^_+|_+$/g, '');
                
                const btnInp = document.getElementById('btn-download-inp');
                if (btnInp) {
                    btnInp.setAttribute('download', `${baseNomFichier}.inp`);
                    btnInp.setAttribute('title', `Télécharger le fichier modèle SWMM : ${baseNomFichier}.inp`);
                }
                const btnRpt = document.getElementById('btn-download-rpt');
                if (btnRpt) {
                    btnRpt.setAttribute('download', `${baseNomFichier}.rpt`);
                    btnRpt.setAttribute('title', `Télécharger le rapport de calcul : ${baseNomFichier}.rpt`);
                }
            }

            // Afficher l'analyse de sensibilité du buffer Voronoï
            if (data.buffer_sensitivity && typeof afficherAnalyseSensibiliteBuffer === 'function') {
                afficherAnalyseSensibiliteBuffer(data.buffer_sensitivity, window._activeBufferM);
            }

            // Mettre à jour l'ensemble de l'IHM latérale pour refléter la zone simulée
            mettreAJourIHMZoneSimulee(data);

            // Mettre à jour l'indicateur supérieur de bassin versant (Option 1 : Lecture Hydraulique)
            if (data.meta && data.meta.cluster_id && typeof window.mettreAJourIndicateurBassin === 'function') {
                const kp = data.kpis || {};
                const qMax = (typeof kp.peak_outflow_m3s === 'number') ? kp.peak_outflow_m3s : 0.0;
                const qExutoire = (typeof kp.q_exutoire_m3s === 'number') ? kp.q_exutoire_m3s : qMax;
                const qDerive = (typeof kp.q_derive_m3s === 'number') ? kp.q_derive_m3s : ((typeof kp.q_deleste_m3s === 'number') ? kp.q_deleste_m3s : 0.0);
                const qGenere = (typeof kp.q_genere_m3s === 'number') ? kp.q_genere_m3s : (qExutoire + qDerive);
                const nbRacc = kp.nb_ouvrages_raccordes || 0;
                const tauxDerive = (typeof kp.taux_derive_pct === 'number') ? kp.taux_derive_pct : (qGenere > 0 ? ((qDerive / qGenere) * 100.0) : 0.0);
                const tauxExutoire = (typeof kp.taux_exutoire_pct === 'number') ? kp.taux_exutoire_pct : Math.max(0, 100.0 - tauxDerive);

                window.mettreAJourIndicateurBassin(data.meta.cluster_id, {
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

            // Centrer et zoomer immédiatement la carte sur la zone simulée
            zoomerSurZoneSimulee(data);


};
