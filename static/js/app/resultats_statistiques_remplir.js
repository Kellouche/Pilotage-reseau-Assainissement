/**
 * Projet : DrainPilot 5.2 — Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-27 | Date de modification : 2026-11-27
 * Objet : Remplissage modale résultats simulation (extrait resultats_statistiques.js)
 */

window.remplirModalResultatsSimulation = function(data) {
    if (!data) return;
    const k = data.kpis || {};
    const meta = data.meta || {};
    const cRes = data.conduit_results || {};
    const nRes = data.node_results || {};

    // 1. En-tête : Badge bassin, Badge État du Réseau & Sous-titre
    const badgeBassin = document.getElementById('res-modal-badge-bassin');
    if (badgeBassin) {
        badgeBassin.textContent = _resoudreNomMetierBassinResultats(meta);
        if (meta.cluster_id !== undefined && meta.cluster_id !== null) {
            badgeBassin.title = `Exutoire / Cluster : ${meta.cluster_id}`;
        }
    }

    const etat = meta.etat_reseau || (data.parameters && data.parameters.etat_reseau) || null;
    const badgeEtat = document.getElementById('res-modal-badge-etat');
    let etatLabelSub = 'État : Nominal (Curé)';
    const estDegrade = etat && !etat.est_nominal && (
        (etat.colmatage_pct && etat.colmatage_pct > 0)
        || (etat.facteur_vieillissement && etat.facteur_vieillissement > 1.0)
        || etat.appliquer_depots_sig
    );

    if (estDegrade) {
        const parts = [];
        if (etat.colmatage_pct > 0) {
            parts.push(`${etat.colmatage_pct}% dépôt${etat.cible_colmatage === 'faibles_pentes' ? ' (<' + (etat.seuil_pente_pct || 0.5) + '%)' : ''}`);
        }
        if (etat.facteur_vieillissement > 1.0) {
            parts.push(`n ×${Number(etat.facteur_vieillissement).toFixed(2)}`);
        }
        if (etat.appliquer_depots_sig) {
            parts.push(`+SIG (${etat.nb_depots_sig_appliques || 0})`);
        }
        const nbCol = etat.nb_conduits_colmates > 0 ? ` • ${etat.nb_conduits_colmates} cond.` : '';
        const scenEtat = etat.scenario_nom && etat.scenario_nom !== 'nominal' ? etat.scenario_nom : 'Personnalisé';
        etatLabelSub = `État ${scenEtat} : ${parts.join(' • ')}${nbCol}`;

        if (badgeEtat) {
            const sev = (etat.colmatage_pct >= 20 || etat.facteur_vieillissement >= 1.4);
            badgeEtat.innerHTML = `<i class="fas fa-water me-1"></i>${etatLabelSub}`;
            badgeEtat.style.color = sev ? '#fca5a5' : '#fbbf24';
            badgeEtat.style.background = sev ? 'rgba(239, 68, 68, 0.18)' : 'rgba(245, 158, 11, 0.18)';
            badgeEtat.style.borderColor = sev ? 'rgba(239, 68, 68, 0.45)' : 'rgba(245, 158, 11, 0.45)';
        }
    } else if (badgeEtat) {
        badgeEtat.innerHTML = `<i class="fas fa-check-circle me-1"></i>État : Nominal (Curé)`;
        badgeEtat.style.color = '#34d399';
        badgeEtat.style.background = 'rgba(16, 185, 129, 0.15)';
        badgeEtat.style.borderColor = 'rgba(16, 185, 129, 0.35)';
    }

    const subTitle = document.getElementById('res-modal-subtitle');
    if (subTitle) {
        const scenNom = (meta.scenario_nom || meta.scenario || (k.pluvio_periode_retour ? ('Pluie ' + k.pluvio_periode_retour) : 'SWMM 5.2 Dynamic Wave'));
        subTitle.textContent = `Scénario : ${scenNom} • ${etatLabelSub} • Résolution 1D Saint-Venant`;
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

    // Décomptes dynamiques des filtres Conduites
    const cAll = document.getElementById('count-filter-cond-tous');
    if (cAll) cAll.textContent = condKeys.length;
    const cSur = document.getElementById('count-filter-cond-surcharge');
    if (cSur) cSur.textContent = surchargedPipesCount;
    const cMod = document.getElementById('count-filter-cond-moderee');
    if (cMod) cMod.textContent = moderatePipesCount;
    const cLib = document.getElementById('count-filter-cond-libre');
    if (cLib) cLib.textContent = freePipesCount;

    if (tbodyCond) {
        if (condKeys.length === 0) {
            tbodyCond.innerHTML = `<tr><td colspan="8" style="padding:24px; text-align:center; color:#64748b;">Aucun tronçon de conduite dans ce périmètre</td></tr>`;
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
                const isCritique = (c.status === 'surcharge' || maxR >= 1.0);
                if (isCritique) {
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

                const btnMapStyle = isCritique 
                    ? 'background: rgba(239, 68, 68, 0.2); border: 1px solid rgba(239, 68, 68, 0.5); color: #fca5a5; box-shadow: 0 0 8px rgba(239, 68, 68, 0.35);'
                    : 'background: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.35); color: #38bdf8;';
                const btnProfilStyle = isCritique 
                    ? 'background: rgba(245, 158, 11, 0.2); border: 1px solid rgba(245, 158, 11, 0.5); color: #fde68a; box-shadow: 0 0 8px rgba(245, 158, 11, 0.35);'
                    : 'background: rgba(168, 85, 247, 0.15); border: 1px solid rgba(168, 85, 247, 0.4); color: #c084fc;';

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
                        <td style="padding: 9px 12px; text-align: center;">
                            <div style="display: flex; gap: 6px; justify-content: center; align-items: center;">
                                <button type="button" onclick="localiserElementSurCarte('conduite', '${kId}')" title="Positionner et voir sur la carte" style="width: 27px; height: 27px; display: inline-flex; align-items: center; justify-content: center; border-radius: 6px; cursor: pointer; transition: all 0.15s; ${btnMapStyle}" onmouseover="this.style.transform='scale(1.1)'" onmouseout="this.style.transform='scale(1)'">
                                    <i class="fas fa-crosshairs" style="font-size: 0.72rem;"></i>
                                </button>
                                <button type="button" onclick="ouvrirProfilDepuisModal('conduite', '${kId}', '${u}', '${d}')" title="Tracer le profil en long (HGL)" style="width: 27px; height: 27px; display: inline-flex; align-items: center; justify-content: center; border-radius: 6px; cursor: pointer; transition: all 0.15s; ${btnProfilStyle}" onmouseover="this.style.transform='scale(1.1)'" onmouseout="this.style.transform='scale(1)'">
                                    <i class="fas fa-chart-line" style="font-size: 0.72rem;"></i>
                                </button>
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

    let regFloodedCount = 0;
    let regSurchargedCount = 0;
    let regFreeCount = 0;

    if (tbodyReg) {
        if (nodeKeys.length === 0) {
            tbodyReg.innerHTML = `<tr><td colspan="7" style="padding:24px; text-align:center; color:#64748b;">Aucun regard dans ce périmètre</td></tr>`;
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

                if (isFlooded) regFloodedCount++;
                else if (isSurcharged) regSurchargedCount++;
                else regFreeCount++;

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

                const isCritiqueReg = isFlooded || isSurcharged;
                const btnRegMapStyle = isFlooded
                    ? 'background: rgba(239, 68, 68, 0.25); border: 1.5px solid #ef4444; color: #fca5a5; box-shadow: 0 0 10px rgba(239, 68, 68, 0.45);'
                    : (isSurcharged ? 'background: rgba(245, 158, 11, 0.22); border: 1.5px solid #f59e0b; color: #fde68a; box-shadow: 0 0 8px rgba(245, 158, 11, 0.4);'
                                    : 'background: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.35); color: #38bdf8;');

                const btnRegProfilStyle = isCritiqueReg
                    ? 'background: rgba(168, 85, 247, 0.25); border: 1.5px solid #a855f7; color: #e9d5ff; box-shadow: 0 0 8px rgba(168, 85, 247, 0.4);'
                    : 'background: rgba(168, 85, 247, 0.15); border: 1px solid rgba(168, 85, 247, 0.4); color: #c084fc;';

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
                        <td style="padding: 8px 12px; text-align: center;">
                            <div style="display: flex; gap: 6px; justify-content: center; align-items: center;">
                                <button type="button" onclick="localiserElementSurCarte('regard', '${nId}')" title="Positionner et voir le regard ${nId} sur la carte" style="width: 27px; height: 27px; display: inline-flex; align-items: center; justify-content: center; border-radius: 6px; cursor: pointer; transition: all 0.15s; ${btnRegMapStyle}" onmouseover="this.style.transform='scale(1.1)'" onmouseout="this.style.transform='scale(1)'">
                                    <i class="fas fa-crosshairs" style="font-size: 0.72rem;"></i>
                                </button>
                                <button type="button" onclick="ouvrirProfilDepuisModal('regard', '${nId}')" title="Tracer le profil en long (HGL) passant par le regard ${nId}" style="width: 27px; height: 27px; display: inline-flex; align-items: center; justify-content: center; border-radius: 6px; cursor: pointer; transition: all 0.15s; ${btnRegProfilStyle}" onmouseover="this.style.transform='scale(1.1)'" onmouseout="this.style.transform='scale(1)'">
                                    <i class="fas fa-chart-line" style="font-size: 0.72rem;"></i>
                                </button>
                            </div>
                        </td>
                    </tr>
                `;
            });
            tbodyReg.innerHTML = htmlReg;
        }
    }

    // Décomptes dynamiques des filtres Regards
    const rAll = document.getElementById('count-filter-reg-tous');
    if (rAll) rAll.textContent = nodeKeys.length;
    const rDeb = document.getElementById('count-filter-reg-debordement');
    if (rDeb) rDeb.textContent = regFloodedCount;
    const rChg = document.getElementById('count-filter-reg-charge');
    if (rChg) rChg.textContent = regSurchargedCount;
    const rLib = document.getElementById('count-filter-reg-libre');
    if (rLib) rLib.textContent = regFreeCount;

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
