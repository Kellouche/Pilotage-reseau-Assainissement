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

            // Remplir la fenêtre dédiée de restitution des résultats
            if (typeof window.remplirModalResultatsSimulation === 'function') {
                window.remplirModalResultatsSimulation(data);
            }
};

// ================================================================================
// CONTRÔLEUR DE LA MODALE DÉDIÉE DE RÉSULTATS SWMM 5.2 (Figma-grade HD)
// ================================================================================

window._detailsConduitesFiltreStatut = 'tous';
window._detailsRegardsFiltreStatut = 'tous';

window.basculerAutoOpenResults = function(checked) {
    localStorage.setItem('swmm_auto_open_results', checked ? 'true' : 'false');
};

window.ouvrirModalResultatsSimulation = function() {
    const modal = document.getElementById('modal-resultats-simulation');
    if (!modal) return;

    const chk = document.getElementById('chk-auto-open-results');
    if (chk) {
        chk.checked = (localStorage.getItem('swmm_auto_open_results') !== 'false');
    }

    if (window._dernierResultatSimulation) {
        window.remplirModalResultatsSimulation(window._dernierResultatSimulation);
    }
    modal.style.display = 'flex';
};

window.fermerModalResultatsSimulation = function() {
    const modal = document.getElementById('modal-resultats-simulation');
    if (modal) modal.style.display = 'none';
};

window.basculerOngletResultats = function(tabKey) {
    const tabs = ['kpi', 'details', 'ia'];
    tabs.forEach(t => {
        const pane = document.getElementById('onglet-res-' + t);
        const btn = document.getElementById('tab-btn-res-' + t);
        if (pane) pane.style.display = (t === tabKey) ? 'block' : 'none';
        if (btn) {
            if (t === tabKey) {
                btn.style.borderBottom = '2.5px solid #38bdf8';
                btn.style.color = '#38bdf8';
                btn.style.fontWeight = '700';
            } else {
                btn.style.borderBottom = '2.5px solid transparent';
                btn.style.color = '#94a3b8';
                btn.style.fontWeight = '600';
            }
        }
    });
};

window.basculerSousOngletDetails = function(subKey) {
    const subConduites = document.getElementById('subtab-content-conduites');
    const subRegards = document.getElementById('subtab-content-regards');
    const btnConduites = document.getElementById('btn-subtab-conduites');
    const btnRegards = document.getElementById('btn-subtab-regards');

    if (subKey === 'conduites') {
        if (subConduites) subConduites.style.display = 'block';
        if (subRegards) subRegards.style.display = 'none';
        if (btnConduites) { btnConduites.style.background = '#0284c7'; btnConduites.style.color = '#ffffff'; }
        if (btnRegards) { btnRegards.style.background = 'transparent'; btnRegards.style.color = '#94a3b8'; }
    } else {
        if (subConduites) subConduites.style.display = 'none';
        if (subRegards) subRegards.style.display = 'block';
        if (btnConduites) { btnConduites.style.background = 'transparent'; btnConduites.style.color = '#94a3b8'; }
        if (btnRegards) { btnRegards.style.background = '#0284c7'; btnRegards.style.color = '#ffffff'; }
    }
};

window.filtrerConduitesParStatut = function(statut) {
    window._detailsConduitesFiltreStatut = statut;
    const btns = document.querySelectorAll('.btn-filter-cond');
    btns.forEach(b => {
        b.style.fontWeight = 'normal';
        b.style.boxShadow = 'none';
        b.classList.remove('active');
    });
    if (window.event && window.event.currentTarget) {
        window.event.currentTarget.classList.add('active');
        window.event.currentTarget.style.fontWeight = 'bold';
        window.event.currentTarget.style.boxShadow = '0 0 10px rgba(56,189,248,0.3)';
    }
    window.filtrerTableauDetailsOuvrages();
};

window.filtrerRegardsParStatut = function(statut) {
    window._detailsRegardsFiltreStatut = statut;
    const btns = document.querySelectorAll('.btn-filter-reg');
    btns.forEach(b => {
        b.style.fontWeight = 'normal';
        b.style.boxShadow = 'none';
        b.classList.remove('active');
    });
    if (window.event && window.event.currentTarget) {
        window.event.currentTarget.classList.add('active');
        window.event.currentTarget.style.fontWeight = 'bold';
        window.event.currentTarget.style.boxShadow = '0 0 10px rgba(56,189,248,0.3)';
    }
    window.filtrerTableauDetailsOuvrages();
};

window.filtrerTableauDetailsOuvrages = function() {
    const input = document.getElementById('inp-search-details-ouvrage');
    const q = (input && input.value ? input.value : '').toLowerCase().trim();

    // Filtrage des conduites
    const condRows = document.querySelectorAll('#tbody-details-conduites tr');
    condRows.forEach(row => {
        if (!row.getAttribute('data-id')) return;
        const statut = row.getAttribute('data-statut') || '';
        const id = (row.getAttribute('data-id') || '').toLowerCase();
        const amont = (row.getAttribute('data-amont') || '').toLowerCase();
        const aval = (row.getAttribute('data-aval') || '').toLowerCase();

        const matchStatut = (window._detailsConduitesFiltreStatut === 'tous') || (statut === window._detailsConduitesFiltreStatut);
        const matchSearch = (!q) || id.includes(q) || amont.includes(q) || aval.includes(q);

        row.style.display = (matchStatut && matchSearch) ? '' : 'none';
    });

    // Filtrage des regards
    const regRows = document.querySelectorAll('#tbody-details-regards tr');
    regRows.forEach(row => {
        if (!row.getAttribute('data-id')) return;
        const statut = row.getAttribute('data-statut') || '';
        const id = (row.getAttribute('data-id') || '').toLowerCase();

        const matchStatut = (window._detailsRegardsFiltreStatut === 'tous') || (statut === window._detailsRegardsFiltreStatut);
        const matchSearch = (!q) || id.includes(q);

        row.style.display = (matchStatut && matchSearch) ? '' : 'none';
    });
};

window.remplirModalResultatsSimulation = function(data) {
    if (!data) return;
    const k = data.kpis || {};
    const meta = data.meta || {};
    const cRes = data.conduit_results || {};
    const nRes = data.node_results || {};

    // 1. En-tête : Badge bassin & Sous-titre
    const badgeBassin = document.getElementById('res-modal-badge-bassin');
    if (badgeBassin) {
        badgeBassin.textContent = meta.cluster_nom || meta.bassin_nom || (meta.cluster_id ? ('Bassin ' + meta.cluster_id) : 'Réseau Complet');
    }
    const subTitle = document.getElementById('res-modal-subtitle');
    if (subTitle) {
        const scenNom = (meta.scenario_nom || meta.scenario || (k.pluvio_periode_retour ? ('Pluie ' + k.pluvio_periode_retour) : 'SWMM 5.2 Dynamic Wave'));
        subTitle.textContent = `Scénario : ${scenNom} • Résolution 1D Saint-Venant (EPA Dynamic Wave)`;
    }

    // 2. Détection de criticité globale & Verdict Banner
    let floodedCount = 0;
    let surchargedNodesCount = 0;
    Object.values(nRes).forEach(n => {
        if (n.status === 'flooded' || (n.flooding_m3 && n.flooding_m3 > 0)) floodedCount++;
        else if (n.status === 'surcharged') surchargedNodesCount++;
    });

    let surchargedPipesCount = 0;
    let moderatePipesCount = 0;
    let freePipesCount = 0;
    Object.values(cRes).forEach(c => {
        const qR = Number(c.flow_ratio || 0);
        const dR = Number(c.depth_ratio || 0);
        const maxR = Math.max(qR, dR);
        if (c.status === 'surcharge' || maxR >= 1.0) surchargedPipesCount++;
        else if (c.status === 'critique' || c.status === 'moderee' || maxR >= 0.70) moderatePipesCount++;
        else freePipesCount++;
    });

    const banner = document.getElementById('res-verdict-banner');
    const vIcon = document.getElementById('res-verdict-icon');
    const vBadge = document.getElementById('res-verdict-badge');
    const vText = document.getElementById('res-verdict-text');
    const vQpeak = document.getElementById('res-verdict-qpeak');
    const vFlooded = document.getElementById('res-verdict-flooded');
    const vCont = document.getElementById('res-verdict-continuity');

    const qPeakVal = (typeof k.peak_outflow_m3s === 'number') ? k.peak_outflow_m3s : (typeof data.peak_outflow_m3s === 'number' ? data.peak_outflow_m3s : 0.0);
    if (vQpeak) vQpeak.textContent = window.formaterNombre(qPeakVal, 3) + ' m³/s';
    if (vFlooded) vFlooded.textContent = floodedCount > 0 ? `${floodedCount} regard${floodedCount > 1 ? 's' : ''}` : (surchargedNodesCount > 0 ? `${surchargedNodesCount} en charge` : '0 (Aucun)');
    const contErr = k.routing_continuity_error_pct || 0;
    if (vCont) vCont.textContent = (contErr > 0 ? '+' : '') + window.formaterNombre(contErr, 2) + ' %';

    if (banner && vIcon && vBadge && vText) {
        if (floodedCount > 0) {
            banner.style.background = 'linear-gradient(90deg, rgba(239, 68, 68, 0.22) 0%, rgba(15, 23, 42, 0.8) 100%)';
            banner.style.borderBottom = '1.5px solid rgba(239, 68, 68, 0.6)';
            vIcon.style.background = '#ef4444';
            vIcon.style.boxShadow = '0 0 16px rgba(239, 68, 68, 0.65)';
            vIcon.innerHTML = '<i class="fas fa-triangle-exclamation"></i>';
            vBadge.textContent = `DÉBORDEMENT DÉTECTÉ (${floodedCount} REGARD${floodedCount > 1 ? 'S' : ''})`;
            vBadge.style.background = 'rgba(239, 68, 68, 0.25)';
            vBadge.style.color = '#fca5a5';
            vBadge.style.border = '1px solid rgba(239, 68, 68, 0.5)';
            vText.textContent = `Refoulement critique en surface constaté · Débordement sur ${floodedCount} regard(s) de visite sous cet événement.`;
        } else if (surchargedPipesCount > 0 || surchargedNodesCount > 0) {
            banner.style.background = 'linear-gradient(90deg, rgba(245, 158, 11, 0.22) 0%, rgba(15, 23, 42, 0.8) 100%)';
            banner.style.borderBottom = '1.5px solid rgba(245, 158, 11, 0.6)';
            vIcon.style.background = '#f59e0b';
            vIcon.style.boxShadow = '0 0 16px rgba(245, 158, 11, 0.65)';
            vIcon.innerHTML = '<i class="fas fa-exclamation-circle"></i>';
            vBadge.textContent = 'VIGILANCE — MISE EN CHARGE';
            vBadge.style.background = 'rgba(245, 158, 11, 0.25)';
            vBadge.style.color = '#fde68a';
            vBadge.style.border = '1px solid rgba(245, 158, 11, 0.5)';
            vText.textContent = `Réseau sous pression sans débordement de surface · ${surchargedPipesCount} tronçon(s) saturé(s) à pleine capacité.`;
        } else {
            banner.style.background = 'linear-gradient(90deg, rgba(16, 185, 129, 0.22) 0%, rgba(15, 23, 42, 0.8) 100%)';
            banner.style.borderBottom = '1.5px solid rgba(16, 185, 129, 0.6)';
            vIcon.style.background = '#10b981';
            vIcon.style.boxShadow = '0 0 16px rgba(16, 185, 129, 0.65)';
            vIcon.innerHTML = '<i class="fas fa-check-circle"></i>';
            vBadge.textContent = 'CONFORME — AUCUN DÉBORDEMENT';
            vBadge.style.background = 'rgba(16, 185, 129, 0.25)';
            vBadge.style.color = '#6ee7b7';
            vBadge.style.border = '1px solid rgba(16, 185, 129, 0.5)';
            vText.textContent = `Capacité d'évacuation satisfaisante · L'ensemble des débits transite en régime à surface libre sans reflux.`;
        }
    }

    // 3. Tab 1 : KPIs dans la modale dédiée
    const mCont = document.getElementById('modal-kpi-continuity');
    if (mCont) mCont.textContent = (contErr > 0 ? '+' : '') + window.formaterNombre(contErr, 2) + ' %';
    const mPeak = document.getElementById('modal-kpi-peak-outflow');
    if (mPeak) mPeak.textContent = window.formaterNombre(qPeakVal, 3) + ' m³/s';
    const mTime = document.getElementById('modal-kpi-peak-time');
    if (mTime) mTime.textContent = k.peak_time_str || '--';
    const mVel = document.getElementById('modal-kpi-max-velocity');
    if (mVel) {
        const vVal = k.max_velocity_ms || 0;
        mVel.textContent = window.formaterNombre(vVal, 2) + ' m/s';
    }
    const mAutoCur = document.getElementById('modal-kpi-autocurage-desc');
    if (mAutoCur) {
        mAutoCur.textContent = k.autocurage_statut || 'Autocurage certifié';
        mAutoCur.style.color = k.autocurage_color || '#34d399';
    }
    const mRunoff = document.getElementById('modal-kpi-vol-runoff');
    if (mRunoff) {
        const rVal = k.total_runoff_volume_m3;
        mRunoff.textContent = (rVal !== undefined && rVal !== null ? Math.round(rVal).toLocaleString('fr-FR') : '--') + ' m³';
    }
    const mInfil = document.getElementById('modal-kpi-vol-infil');
    if (mInfil) {
        const iVal = k.total_infiltration_volume_m3;
        mInfil.textContent = (iVal !== undefined && iVal !== null ? Math.round(iVal).toLocaleString('fr-FR') : '--') + ' m³';
    }
    const mCoeff = document.getElementById('modal-kpi-coeff-eff');
    if (mCoeff) mCoeff.textContent = window.formaterNombre(k.effective_runoff_coeff !== undefined ? k.effective_runoff_coeff : 0.70, 2);
    const mSurch = document.getElementById('modal-kpi-surcharge-pct');
    if (mSurch) mSurch.textContent = `${window.formaterNombre(k.surcharged_length_pct || 0, 1)} % (${window.formaterNombre(k.surcharged_length_m || 0, 1)} m)`;

    // Sollicitation pluviométrique
    const pluvioStation = k.pluvio_station || meta.pluvio_station || 'Station ANRH Chlef Siège (010501)';
    const pluvioPeriode = k.pluvio_periode_retour || meta.pluvio_periode_retour || 'T = 10 ans (Décennale)';
    const pluvioImax = k.pluvio_intensite_max_mmh !== undefined ? k.pluvio_intensite_max_mmh : (meta.pluvio_intensite_max_mmh || 74.9);
    const pluvioPtot = k.pluvio_hauteur_totale_mm || meta.pluvio_hauteur_totale_mm || 42.8;
    const pluvioMontana = k.pluvio_montana || meta.pluvio_montana || 'I(t) = 9.334 · t^(-0.745)';

    const stBadge = document.getElementById('modal-kpi-pluvio-station-badge');
    if (stBadge) stBadge.textContent = pluvioStation;
    const pPer = document.getElementById('modal-kpi-pluvio-periode');
    if (pPer) pPer.textContent = pluvioPeriode;
    const pImax = document.getElementById('modal-kpi-pluvio-imax');
    if (pImax) pImax.textContent = `${Number(pluvioImax).toFixed(1)} mm/h`;
    const pPtot = document.getElementById('modal-kpi-pluvio-ptot');
    if (pPtot) pPtot.textContent = `${Number(pluvioPtot).toFixed(1)} mm`;
    const pMont = document.getElementById('modal-kpi-pluvio-montana');
    if (pMont) pMont.textContent = pluvioMontana;

    // Contrôle cohérence rationnelle
    const coh = k.coherence_pluie_debit;
    if (coh) {
        const cBadge = document.getElementById('modal-kpi-coherence-badge');
        if (cBadge) {
            cBadge.textContent = coh.badge || coh.statut;
            cBadge.style.background = (coh.color || '#10b981') + '22';
            cBadge.style.color = coh.color || '#10b981';
            cBadge.style.border = `1px solid ${coh.color || '#10b981'}55`;
        }
        const cQsim = document.getElementById('modal-kpi-coh-qsim');
        if (cQsim) cQsim.textContent = `${window.formaterNombre(coh.q_simule_m3s, 3)} m³/s`;
        const cQrat = document.getElementById('modal-kpi-coh-qrat');
        if (cQrat) cQrat.textContent = `${window.formaterNombre(coh.q_rationnel_m3s, 3)} m³/s (Ratio: ${coh.ratio})`;
        const cMsg = document.getElementById('modal-kpi-coherence-msg');
        if (cMsg) cMsg.textContent = coh.message;
    }

    // Ouvrages spéciaux & délestage
    const orphBox = document.getElementById('modal-sim-orphelin-kpi-box');
    if (orphBox) {
        const qDerive = (typeof k.q_derive_m3s === 'number') ? k.q_derive_m3s : ((typeof k.q_deleste_m3s === 'number') ? k.q_deleste_m3s : 0.0);
        const qExutoire = (typeof k.q_exutoire_m3s === 'number') ? k.q_exutoire_m3s : qPeakVal;
        const qGenere = (typeof k.q_genere_m3s === 'number') ? k.q_genere_m3s : (qExutoire + qDerive);
        const nbOrph = k.nb_ouvrages_raccordes || 0;
        const tauxDerive = (typeof k.taux_derive_pct === 'number') ? k.taux_derive_pct : (qGenere > 0 ? ((qDerive / qGenere) * 100.0) : 0.0);
        const tauxExutoire = (typeof k.taux_exutoire_pct === 'number') ? k.taux_exutoire_pct : Math.max(0, 100.0 - tauxDerive);

        orphBox.style.display = 'block';
        const bEl = document.getElementById('modal-kpi-orphelin-badge');
        const gEl = document.getElementById('modal-kpi-orphelin-qgenere');
        const eEl = document.getElementById('modal-kpi-orphelin-qexutoire');
        const qEl = document.getElementById('modal-kpi-orphelin-qdeleste');
        const dEl = document.getElementById('modal-kpi-orphelin-desc');

        if (gEl) gEl.textContent = `${window.formaterNombre(qGenere, 3)} m³/s`;
        if (eEl) eEl.textContent = `${window.formaterNombre(qExutoire, 3)} m³/s (${window.formaterNombre(tauxExutoire, 1)}%)`;
        if (qEl) qEl.textContent = `${window.formaterNombre(qDerive, 3)} m³/s (${window.formaterNombre(tauxDerive, 1)}%)`;

        if (qDerive > 0) {
            if (bEl) {
                bEl.textContent = `Soulagement réseau : ${window.formaterNombre(tauxDerive, 1)}%`;
                bEl.style.background = 'rgba(6, 182, 212, 0.25)';
                bEl.style.color = '#22d3ee';
                bEl.style.borderColor = 'rgba(6, 182, 212, 0.5)';
            }
            if (dEl) dEl.innerHTML = `<i class="fas fa-check-circle text-emerald-400 me-1"></i> <b>${nbOrph} ouvrage(s) spécial(aux) actif(s)</b> : ${window.formaterNombre(qDerive, 3)} m³/s captés (${window.formaterNombre(tauxDerive, 1)}% du débit produit).`;
        } else {
            if (bEl) {
                bEl.textContent = `Soulagement réseau : 0,0%`;
                bEl.style.background = 'rgba(16, 185, 129, 0.2)';
                bEl.style.color = '#34d399';
                bEl.style.borderColor = 'rgba(16, 185, 129, 0.4)';
            }
            if (dEl) dEl.innerHTML = `<i class="fas fa-info-circle text-sky-400 me-1"></i> Scénario sans ouvrage spécial : 100,0% du débit transite vers l'exutoire principal.`;
        }
    }

    // 4. Tab 2 : Remplissage des tableaux Conduites et Regards
    const tbodyCond = document.getElementById('tbody-details-conduites');
    const badgeCond = document.getElementById('badge-count-conduites');
    const condKeys = Object.keys(cRes);
    if (badgeCond) badgeCond.textContent = condKeys.length;

    if (tbodyCond) {
        if (condKeys.length === 0) {
            tbodyCond.innerHTML = `<tr><td colspan="7" style="padding:24px; text-align:center; color:#64748b;">Aucun tronçon de conduite dans ce périmètre</td></tr>`;
        } else {
            let htmlCond = '';
            condKeys.forEach(kId => {
                const c = cRes[kId];
                const qR = Number(c.flow_ratio || 0);
                const dR = Number(c.depth_ratio || 0);
                const maxR = Math.max(qR, dR);
                const rPct = Math.round(maxR * 100);

                let statutClass = 'libre';
                let col = '#10b981';
                if (c.status === 'surcharge' || maxR >= 1.0) {
                    statutClass = 'surcharge';
                    col = '#ef4444';
                } else if (c.status === 'critique' || c.status === 'moderee' || maxR >= 0.70) {
                    statutClass = 'moderee';
                    col = '#f59e0b';
                }

                const u = String(c.u_node || '--');
                const d = String(c.d_node || '--');
                const diam = c.diam_mm || (c.geom1 ? Math.round(c.geom1 * 1000) : 600);
                const pente = (c.slope !== undefined) ? (Number(c.slope) * 100).toFixed(2) : '--';
                const qMaxStr = window.formaterNombre(c.max_flow_cms || c.q_max || 0, 3);
                const vMaxStr = window.formaterNombre(c.max_velocity_ms || 0, 2);

                htmlCond += `
                    <tr data-statut="${statutClass}" data-id="${kId}" data-amont="${u}" data-aval="${d}" style="border-bottom: 1px solid rgba(255,255,255,0.05); transition: background 0.15s;" onmouseover="this.style.background='rgba(56,189,248,0.06)'" onmouseout="this.style.background='transparent'">
                        <td style="padding: 9px 12px; font-weight: 700; color: #f8fafc;">
                            <span style="font-family: monospace; background: rgba(255,255,255,0.06); padding: 2px 6px; border-radius: 4px;">${kId}</span>
                        </td>
                        <td style="padding: 9px 12px; color: #cbd5e1;">${u} &rarr; ${d}</td>
                        <td style="padding: 9px 12px; color: #94a3b8;">DN ${diam} mm</td>
                        <td style="padding: 9px 12px; color: #94a3b8;">${pente} %</td>
                        <td style="padding: 9px 12px; color: #38bdf8; font-weight: 700;">${qMaxStr} m³/s</td>
                        <td style="padding: 9px 12px; color: #cbd5e1;">${vMaxStr} m/s</td>
                        <td style="padding: 9px 12px;">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <div style="flex: 1; height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden;">
                                    <div style="width: ${Math.min(100, rPct)}%; height: 100%; background: ${col};"></div>
                                </div>
                                <span style="font-weight: 800; color: ${col}; font-size: 0.76rem; width: 44px; text-align: right;">${rPct}%</span>
                            </div>
                        </td>
                    </tr>
                `;
            });
            tbodyCond.innerHTML = htmlCond;
        }
    }

    // Regards
    const tbodyReg = document.getElementById('tbody-details-regards');
    const badgeReg = document.getElementById('badge-count-regards');

    // Indexer les données SIG géographiques disponibles (regards, noeuds, rejets)
    const gisNodesMap = {};
    if (window._rawNetworkData && window._rawNetworkData.couches) {
        ['regards', 'noeuds', 'rejets'].forEach(layerKey => {
            const layerObj = window._rawNetworkData.couches[layerKey];
            if (layerObj && Array.isArray(layerObj.features)) {
                layerObj.features.forEach(f => {
                    const p = f.properties || {};
                    const rawCode = p.Code !== undefined ? p.Code : (p.code !== undefined ? p.code : (p.CODE || p.id || ''));
                    if (rawCode !== undefined && rawCode !== null && rawCode !== '') {
                        const strCode = String(rawCode).trim();
                        gisNodesMap[strCode] = p;
                        if (strCode.endsWith('.0')) gisNodesMap[strCode.slice(0, -2)] = p;
                    }
                });
            }
        });
    }

    const nhMap = (data.timeseries && data.timeseries.node_hydraulics) || {};
    const depthMaxMap = data.node_depth_maxima || (data.kpis && data.kpis.node_depth_maxima) || {};

    // Fusion de l'ensemble des regards simulés (nRes, depthMaxMap, meta.simulated_nodes)
    const allNodeIdsSet = new Set(Object.keys(nRes));
    Object.keys(depthMaxMap).forEach(id => allNodeIdsSet.add(id));
    if (data.meta && Array.isArray(data.meta.simulated_nodes)) {
        data.meta.simulated_nodes.forEach(id => allNodeIdsSet.add(String(id)));
    }
    const nodeKeys = Array.from(allNodeIdsSet);
    if (badgeReg) badgeReg.textContent = nodeKeys.length;

    if (tbodyReg) {
        if (nodeKeys.length === 0) {
            tbodyReg.innerHTML = `<tr><td colspan="6" style="padding:24px; text-align:center; color:#64748b;">Aucun regard dans ce périmètre</td></tr>`;
        } else {
            let htmlReg = '';
            nodeKeys.forEach(nId => {
                const cleanId = String(nId).endsWith('.0') ? String(nId).slice(0, -2) : String(nId);
                const n = nRes[nId] || nRes[cleanId] || {};
                const gisProps = gisNodesMap[nId] || gisNodesMap[cleanId] || {};
                const nh = nhMap[nId] || nhMap[cleanId] || {};
                const dm = depthMaxMap[nId] || depthMaxMap[cleanId] || {};

                // 1. Cote Tampon (TN)
                let tnVal = null;
                if (n.rim_elev !== undefined && n.rim_elev !== null) tnVal = Number(n.rim_elev);
                else if (gisProps.COTETN !== undefined && gisProps.COTETN !== null && gisProps.COTETN !== '') tnVal = Number(gisProps.COTETN);
                else if (gisProps.COTTN !== undefined && gisProps.COTTN !== null && gisProps.COTTN !== '') tnVal = Number(gisProps.COTTN);
                else if (gisProps.cote_tampon !== undefined && gisProps.cote_tampon !== null && gisProps.cote_tampon !== '') tnVal = Number(gisProps.cote_tampon);
                else if (gisProps.Cote_TN !== undefined && gisProps.Cote_TN !== null && gisProps.Cote_TN !== '') tnVal = Number(gisProps.Cote_TN);
                else if (gisProps.TN !== undefined && gisProps.TN !== null && gisProps.TN !== '') tnVal = Number(gisProps.TN);
                else if (gisProps.Z_TN !== undefined && gisProps.Z_TN !== null && gisProps.Z_TN !== '') tnVal = Number(gisProps.Z_TN);
                else if (gisProps.Z_SOL !== undefined && gisProps.Z_SOL !== null && gisProps.Z_SOL !== '') tnVal = Number(gisProps.Z_SOL);
                else if (gisProps.ELEVATION !== undefined && gisProps.ELEVATION !== null && gisProps.ELEVATION !== '') tnVal = Number(gisProps.ELEVATION);

                // 2. Cote Radier
                let radierVal = null;
                if (n.invert_elev !== undefined && n.invert_elev !== null) radierVal = Number(n.invert_elev);
                else if (nh.invert_m !== undefined && nh.invert_m !== null) radierVal = Number(nh.invert_m);
                else if (gisProps.COTERAD !== undefined && gisProps.COTERAD !== null && gisProps.COTERAD !== '') radierVal = Number(gisProps.COTERAD);
                else if (gisProps.COTRAD !== undefined && gisProps.COTRAD !== null && gisProps.COTRAD !== '') radierVal = Number(gisProps.COTRAD);
                else if (gisProps.cote_radier !== undefined && gisProps.cote_radier !== null && gisProps.cote_radier !== '') radierVal = Number(gisProps.cote_radier);
                else if (gisProps.PROFRADI !== undefined && gisProps.PROFRADI !== null && gisProps.PROFRADI !== '') radierVal = Number(gisProps.PROFRADI);

                // Fallbacks croisés entre Radier et Tampon
                const profStruct = Number(gisProps.PROFONDEUR || gisProps.profondeur || n.max_depth_structure || 2.0);
                if (tnVal === null && radierVal !== null) {
                    tnVal = radierVal + profStruct;
                } else if (radierVal === null && tnVal !== null) {
                    radierVal = tnVal - profStruct;
                }

                // 3. Cote d'eau max (HGL)
                let hmaxVal = null;
                if (n.max_head_m !== undefined && n.max_head_m !== null) hmaxVal = Number(n.max_head_m);
                else if (n.max_hgl_m !== undefined && n.max_hgl_m !== null) hmaxVal = Number(n.max_hgl_m);
                else if (dm.max_hgl_m !== undefined && dm.max_hgl_m !== null) hmaxVal = Number(dm.max_hgl_m);
                else if (nh.rpt_max_head_m !== undefined && nh.rpt_max_head_m !== null) hmaxVal = Number(nh.rpt_max_head_m);
                else if (nh.max_head_m !== undefined && nh.max_head_m !== null) hmaxVal = Number(nh.max_head_m);
                else if (radierVal !== null && (n.max_depth_m !== undefined || dm.max_depth_m !== undefined)) {
                    hmaxVal = radierVal + Number(n.max_depth_m !== undefined ? n.max_depth_m : dm.max_depth_m);
                }

                // 4. Tirant d'eau max
                let depthVal = null;
                if (n.max_depth_m !== undefined && n.max_depth_m !== null) depthVal = Number(n.max_depth_m);
                else if (dm.max_depth_m !== undefined && dm.max_depth_m !== null) depthVal = Number(dm.max_depth_m);
                else if (nh.max_depth_m !== undefined && nh.max_depth_m !== null) depthVal = Number(nh.max_depth_m);
                else if (hmaxVal !== null && radierVal !== null) depthVal = Math.max(0, hmaxVal - radierVal);

                // 5. Statut et classification
                const isFlooded = (n.status === 'flooded' || (n.flood_volume_m3 && n.flood_volume_m3 > 0) || (tnVal !== null && hmaxVal !== null && hmaxVal >= tnVal && (n.hours_flooded > 0 || (n.flood_volume_m3 > 0))));
                const isSurcharged = (!isFlooded && (n.status === 'surcharged' || (n.hours_surcharged && n.hours_surcharged > 0) || (n.surcharge_depth_m && n.surcharge_depth_m > 0)));
                let statutClass = isFlooded ? 'debordement' : (isSurcharged ? 'charge' : 'libre');

                // Chaînes formatées pour l'affichage
                const tnStr = (tnVal !== null && !isNaN(tnVal)) ? `${tnVal.toFixed(2)} m` : '--';
                const radStr = (radierVal !== null && !isNaN(radierVal)) ? `${radierVal.toFixed(2)} m` : '--';
                const hmaxStr = (hmaxVal !== null && !isNaN(hmaxVal)) ? `${hmaxVal.toFixed(2)} m` : '--';
                const depthStr = (depthVal !== null && !isNaN(depthVal)) ? `${depthVal.toFixed(2)} m` : '--';

                let cellCharge = '';
                if (isFlooded) {
                    const debordH = (tnVal !== null && hmaxVal !== null && hmaxVal >= tnVal) ? (hmaxVal - tnVal) : 0.0;
                    cellCharge = `<div style="color: #f87171; font-weight: 700;">+${debordH.toFixed(2)} m (Refoulement)</div><div style="font-size: 0.68rem; color: #fca5a5;">Tampon submergé</div>`;
                } else if (isSurcharged) {
                    const surchH = n.surcharge_depth_m ? Number(n.surcharge_depth_m) : ((depthVal && radierVal && tnVal) ? Math.max(0, depthVal - (tnVal - radierVal)) : 0.0);
                    const revanche = (tnVal !== null && hmaxVal !== null) ? Math.max(0, tnVal - hmaxVal) : null;
                    const revStr = (revanche !== null) ? `Revanche : ${revanche.toFixed(2)} m` : 'Sous pression';
                    cellCharge = `<div style="color: #fbbf24; font-weight: 700;">En charge (+${surchH.toFixed(2)} m)</div><div style="font-size: 0.68rem; color: #fde68a;">${revStr}</div>`;
                } else {
                    const revanche = (tnVal !== null && hmaxVal !== null) ? Math.max(0, tnVal - hmaxVal) : null;
                    const revStr = (revanche !== null) ? `Revanche : ${revanche.toFixed(2)} m` : 'Régime libre';
                    cellCharge = `<div style="color: #34d399; font-weight: 600;">Écoulement libre</div><div style="font-size: 0.68rem; color: #94a3b8;">${revStr}</div>`;
                }

                const volFlood = Number(n.flood_volume_m3 || n.flooding_m3 || 0);
                const volDebStr = volFlood > 0 ? `${volFlood.toFixed(1)} m³` : '0 m³';

                let badgeHtml = '';
                if (isFlooded) {
                    badgeHtml = `<span style="background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); padding: 2px 8px; border-radius: 4px; font-weight: 700; font-size: 0.72rem;">🔴 Débordement</span>`;
                } else if (isSurcharged) {
                    badgeHtml = `<span style="background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); padding: 2px 8px; border-radius: 4px; font-weight: 700; font-size: 0.72rem;">🟠 En charge</span>`;
                } else {
                    badgeHtml = `<span style="background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); padding: 2px 8px; border-radius: 4px; font-weight: 600; font-size: 0.72rem;">🟢 Libre</span>`;
                }

                htmlReg += `
                    <tr data-statut="${statutClass}" data-id="${nId}" style="border-bottom: 1px solid rgba(255,255,255,0.05); transition: background 0.15s;" onmouseover="this.style.background='rgba(56,189,248,0.06)'" onmouseout="this.style.background='transparent'">
                        <td style="padding: 8px 12px; font-weight: 700; color: #f8fafc;">
                            <span style="font-family: monospace; background: rgba(255,255,255,0.06); padding: 2px 6px; border-radius: 4px;">${nId}</span>
                        </td>
                        <td style="padding: 8px 12px;">
                            <div style="font-weight: 700; color: #f8fafc;">${tnStr}</div>
                            <div style="font-size: 0.68rem; color: #64748b;">Radier : ${radStr}</div>
                        </td>
                        <td style="padding: 8px 12px;">
                            <div style="font-weight: 800; color: #38bdf8;">${hmaxStr}</div>
                            <div style="font-size: 0.68rem; color: #94a3b8;">Tirant max : ${depthStr}</div>
                        </td>
                        <td style="padding: 8px 12px;">${cellCharge}</td>
                        <td style="padding: 8px 12px; color: ${volFlood > 0 ? '#f87171' : '#64748b'}; font-weight: ${volFlood > 0 ? '800' : 'normal'};">${volDebStr}</td>
                        <td style="padding: 8px 12px;">${badgeHtml}</td>
                    </tr>
                `;
            });
            tbodyReg.innerHTML = htmlReg;
        }
    }

    const badgeCritCount = document.getElementById('badge-tab-details-count');
    if (badgeCritCount) {
        const totalCrit = floodedCount + surchargedPipesCount;
        if (totalCrit > 0) {
            badgeCritCount.textContent = totalCrit;
            badgeCritCount.style.display = 'inline-block';
        } else {
            badgeCritCount.style.display = 'none';
        }
    }

    // 5. Tab 3 : Diagnostic IA & Sensibilité Voronoï
    const iaBox = document.getElementById('modal-ia-diagnostic-content');
    if (iaBox) {
        const diagObj = (data.multi_agents && data.multi_agents.diagnostic) || {};
        const diagSynthese = diagObj.synthese || diagObj.recommandations || null;
        if (diagSynthese && typeof diagSynthese === 'string') {
            iaBox.innerHTML = `<div style="line-height: 1.6; color: #e2e8f0;">${diagSynthese}</div>`;
        } else if (Array.isArray(diagSynthese)) {
            iaBox.innerHTML = `<ul style="margin: 0; padding-left: 20px; line-height: 1.6;">${diagSynthese.map(r => `<li>${r}</li>`).join('')}</ul>`;
        } else {
            let recoPipes = surchargedPipesCount > 0 ? `Renforcement ou recalibrage recommandé sur <b>${surchargedPipesCount} tronçon(s)</b> en saturation hydraulique.` : `Le dimensionnement actuel des conduites est adapté aux débits de pointe décennaux.`;
            let recoNodes = floodedCount > 0 ? `Mise en œuvre prioritaire de bassins d'orage ou surélévation de tampons sur <b>${floodedCount} regard(s)</b> pour éliminer les inondations urbaines.` : `Aucun refoulement critique en surface.`;
            iaBox.innerHTML = `
                <div style="line-height: 1.6; color: #e2e8f0;">
                    <p style="margin: 0 0 8px 0;"><i class="fas fa-check-circle text-sky-400 me-2"></i><b>Analyse d'Écoulement Saint-Venant 1D :</b> Débit de pointe simulé à l'exutoire de <b>${window.formaterNombre(qPeakVal, 3)} m³/s</b> avec une vitesse maximale de <b>${window.formaterNombre(k.max_velocity_ms || 0, 2)} m/s</b>.</p>
                    <p style="margin: 0 0 8px 0;"><i class="fas fa-tools text-amber-400 me-2"></i><b>Prescription Génie Civil :</b> ${recoPipes}</p>
                    <p style="margin: 0;"><i class="fas fa-shield-halved text-emerald-400 me-2"></i><b>Sécurisation Ouvrages :</b> ${recoNodes}</p>
                </div>
            `;
        }
    }

    // Analyse de sensibilité du buffer Voronoï
    if (data.buffer_sensitivity && typeof afficherAnalyseSensibiliteBuffer === 'function') {
        const currentVal = window._activeBufferM || (data.meta && data.meta.buffer_m) || 35.0;
        const curve = data.buffer_sensitivity.curve || [];
        const mGrid = document.getElementById('modal-sim-buffer-tiles-grid');
        if (mGrid && curve.length > 0) {
            let htmlGrid = '';
            curve.forEach(c => {
                const isRec = c.is_recommended || (Math.round(c.buffer_m) === 45);
                const isSelected = (Math.round(c.buffer_m) === Math.round(currentVal));
                const borderColor = isSelected ? '#10b981' : (isRec ? 'rgba(56, 189, 248, 0.5)' : 'rgba(255,255,255,0.1)');
                const bg = isSelected ? 'rgba(16, 185, 129, 0.12)' : (isRec ? 'rgba(56, 189, 248, 0.08)' : 'rgba(255,255,255,0.03)');

                htmlGrid += `
                    <div style="background: ${bg}; border: 1.5px solid ${borderColor}; border-radius: 10px; padding: 12px 14px; display: flex; flex-direction: column; justify-content: space-between; position: relative;">
                        ${isRec ? `<span style="position: absolute; top: -8px; right: 8px; font-size: 0.65rem; background: #0284c7; color: white; padding: 1px 7px; border-radius: 4px; font-weight: 700;">POINT INFLEXION</span>` : ''}
                        <div>
                            <div style="font-size: 0.86rem; font-weight: 800; color: ${isSelected ? '#34d399' : (isRec ? '#38bdf8' : '#e2e8f0')}; margin-bottom: 2px;">
                                Buffer ${Math.round(c.buffer_m)} m ${isSelected ? '✅' : ''}
                            </div>
                            <div style="font-size: 0.72rem; color: #94a3b8; margin-bottom: 6px;">
                                ${c.buffer_m === 35 ? 'Voirie stricte' : (c.buffer_m === 45 ? 'Îlots comblés (Optimal)' : 'Périphérie élargie')}
                            </div>
                            <div style="font-size: 1.05rem; font-weight: 800; color: #f8fafc; margin-bottom: 2px;">
                                ${c.surface_ha} ha ${c.gain_pct > 0 ? `<small style="font-size: 0.72rem; color: #34d399; font-weight: 700;">+${c.gain_pct}%</small>` : ''}
                            </div>
                            <div style="font-size: 0.74rem; color: #cbd5e1;">
                                Débit : <b style="color: ${isRec ? '#38bdf8' : '#f8fafc'};">${c.peak_flow_m3s} m³/s</b>
                            </div>
                        </div>
                        <button onclick="validerChoixBuffer(${c.buffer_m})" style="width: 100%; margin-top: 10px; padding: 6px; font-size: 0.75rem; font-weight: 700; border-radius: 6px; cursor: pointer; border: none; background: ${isSelected ? '#10b981' : (isRec ? 'linear-gradient(135deg, #0284c7, #0369a1)' : 'rgba(255,255,255,0.08)')}; color: white;">
                            ${isSelected ? '<i class="fas fa-check"></i> Actif' : (isRec ? '⭐ Valider 45m' : `Valider ${Math.round(c.buffer_m)}m`)}
                        </button>
                    </div>
                `;
            });
            mGrid.innerHTML = htmlGrid;
        }
    }
};
