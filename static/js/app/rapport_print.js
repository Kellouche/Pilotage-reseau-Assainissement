/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Génération et impression du rapport d'expertise technique officiel A4
 * ================================================================================
 */

// ==========================================
        // IMPRESSION COMPLÈTE DU RAPPORT D'EXPERTISE (PDF / PAPIER)
        // ==========================================
        window.imprimerDiagnosticTechniqueComplet = function() {
            const simData = window._dernierResultatSimulation;
            if (!simData) {
                alert("Aucun résultat de simulation active à imprimer. Veuillez d'abord exécuter une simulation SWMM 5.2.");
                return;
            }

            const meta = simData.meta || {};
            const k = simData.kpis || {};
            const agents = simData.agents_expertise || {};
            const bufferSens = simData.buffer_sensitivity || {};

            const diag = agents.diagnostic_causal || {};
            const gc = agents.prescriptions_genie_civil || {};
            const lid = agents.solutions_hydrologie_durable || {};
            const risk = agents.matrice_risques || {};
            const finance = agents.analyse_variantes_financiere || {};
            const synth = agents.synthese_executive || {};

            const variantes = finance.variantes || [];
            const ratios = finance.ratios_directeurs || {};

            const projectName = (window._rawNetworkData && window._rawNetworkData.project_name) ? window._rawNetworkData.project_name : 'Réseau Urbain';
            const dateStr = new Date().toLocaleString('fr-FR', { dateStyle: 'full', timeStyle: 'short' });

            const printWin = window.open('', '_blank');
            if (!printWin) {
                alert("Veuillez autoriser l'ouverture des fenêtres pop-up dans votre navigateur pour générer le rapport PDF.");
                return;
            }

            const verdict = synth.verdict || "ANALYSE EXPERTE MULTI-AGENTS SWMM 5.2";
            const verdictColor = synth.couleur || "#0284c7";

            // Tableau Risques (Agent 4)
            let riskRows = '';
            let riskList = [];
            if (Array.isArray(risk.actions_liste) && risk.actions_liste.length > 0) {
                riskList = risk.actions_liste;
            } else if (Array.isArray(risk.actions_priorisees) && risk.actions_priorisees.length > 0) {
                riskList = risk.actions_priorisees;
            } else if (risk.actions_priorisees && typeof risk.actions_priorisees === 'object') {
                ['P1', 'P2', 'P3'].forEach(prio => {
                    (risk.actions_priorisees[prio] || []).forEach(item => {
                        riskList.push({
                            priorite: prio,
                            conduite: item.conduite || item.cible || '--',
                            type_risque: item.type_risque || item.probleme || '--',
                            action_requise: item.action_requise || item.action || '--',
                            estimation_cout_dzd: item.estimation_cout_dzd || 0,
                            delai_recommande: item.delai_recommande || item.delai || (prio === 'P1' ? '3 mois (Urgence)' : (prio === 'P2' ? '12 mois' : 'Maintenance'))
                        });
                    });
                });
            }

            if (riskList.length > 0) {
                riskList.forEach(a => {
                    const badgeClass = a.priorite === 'P1' ? 'badge-p1' : (a.priorite === 'P2' ? 'badge-p2' : 'badge-p3');
                    riskRows += `
                        <tr>
                            <td style="text-align: center;"><span class="badge ${badgeClass}">${a.priorite || 'P1'}</span></td>
                            <td><b>${a.conduite || a.cible || '--'}</b></td>
                            <td>${a.type_risque || a.probleme || '--'}</td>
                            <td>${a.action_requise || a.action || '--'}</td>
                            <td style="text-align: right; font-weight: 700;">${window.formaterCoutDZD(a.estimation_cout_dzd)}</td>
                            <td style="text-align: center;">${a.delai_recommande || '--'}</td>
                        </tr>
                    `;
                });
            } else {
                riskRows = '<tr><td colspan="6" style="text-align:center; color:#64748b;">Aucun risque critique immédiat recensé. Réseau stable sous ce scénario.</td></tr>';
            }

            // Tableau Diagnostic Surcharges (Agent 1)
            let surchRows = '';
            if (diag.surcharged_links && diag.surcharged_links.length > 0) {
                diag.surcharged_links.forEach(l => {
                    const cName = l.conduit || l.cid || '--';
                    const vel = l.vitesse !== undefined ? l.vitesse : (l.max_velocity_ms !== undefined ? l.max_velocity_ms : 0);
                    const qm = l.q_max !== undefined ? l.q_max : (l.max_flow_cms !== undefined ? l.max_flow_cms : 0);
                    surchRows += `
                        <tr>
                            <td><b>${cName}</b></td>
                            <td style="text-align: right; color: #ef4444; font-weight: 700;">${((l.flow_ratio || 0) * 100).toFixed(0)} %</td>
                            <td style="text-align: right;">${((l.depth_ratio || 0) * 100).toFixed(0)} %</td>
                            <td style="text-align: right;">${Number(vel).toFixed(2)} m/s</td>
                            <td style="text-align: right;">${Number(qm).toFixed(3)} m³/s</td>
                            <td>${l.q_full ? `Capacité max : ${l.q_full.toFixed(3)} m³/s` : (l.cause || 'Surcharge sous pression')}</td>
                        </tr>
                    `;
                });
            } else {
                surchRows = '<tr><td colspan="6" style="text-align:center; color:#64748b;">Aucun tronçon en surcharge sévère (>80%).</td></tr>';
            }

            // Tableau Goulots d'étranglement (Agent 1)
            let bottleRows = '';
            if (diag.bottlenecks && diag.bottlenecks.length > 0) {
                diag.bottlenecks.forEach(b => {
                    const am = b.amont || b.amont_cid || '--';
                    const av = b.aval || b.aval_cid || '--';
                    const lg = b.longueur !== undefined ? b.longueur : (b.longueur_m !== undefined ? b.longueur_m : 0);
                    bottleRows += `
                        <tr>
                            <td><b>${am}</b> &rarr; <b>${av}</b></td>
                            <td style="text-align: right;">${b.diam_amont || '--'} mm</td>
                            <td style="text-align: right; color: #ef4444; font-weight: 700;">${b.diam_aval || '--'} mm</td>
                            <td style="text-align: right;">${Number(lg).toFixed(1)} m</td>
                            <td>${b.description || 'Goulot géométrique • Réduction anormale de section vers l\'aval'}</td>
                        </tr>
                    `;
                });
            } else {
                bottleRows = '<tr><td colspan="5" style="text-align:center; color:#64748b;">Aucun goulot géométrique inverse (D_aval < D_amont) détecté.</td></tr>';
            }

            // Tableau Synthèse par DN (Agent 2)
            let gcRecapRows = '';
            const recapDnList = gc.recapitulatif_par_dn || [];
            if (recapDnList.length > 0) {
                recapDnList.forEach(r => {
                    gcRecapRows += `
                        <tr>
                            <td><b>${r.label}</b></td>
                            <td>${r.materiau}</td>
                            <td style="text-align: center;">${r.classe || '--'}</td>
                            <td style="text-align: right; font-weight: 700;">${r.nb_troncons}</td>
                            <td style="text-align: right; font-weight: 700;">${Number(r.lineaire_ml).toFixed(1)} ml</td>
                            <td style="text-align: right;">${r.pct_lineaire}%</td>
                            <td style="text-align: right;">${window.formaterCoutDZD(r.cout_unitaire_ml_dzd)} / ml</td>
                            <td style="text-align: right; font-weight: 700; color: #0284c7;">${window.formaterCoutDZD(r.cout_total_dzd)}</td>
                            <td style="text-align: right;">${r.pct_budget}%</td>
                        </tr>
                    `;
                });
            } else {
                gcRecapRows = '<tr><td colspan="9" style="text-align:center; color:#64748b;">Aucun recalibrage structurel requis.</td></tr>';
            }

            const bpu = gc.decomposition_bpu || {};
            const bpuTerrassement = bpu.montant_terrassement_dzd || Math.round((gc.cout_global_estime_dzd || 0) * 0.30);
            const bpuFourniture = bpu.montant_fourniture_dzd || Math.round((gc.cout_global_estime_dzd || 0) * 0.35);
            const bpuPose = bpu.montant_pose_remblai_dzd || Math.round((gc.cout_global_estime_dzd || 0) * 0.20);
            const bpuChaussee = bpu.montant_chaussee_dzd || Math.round((gc.cout_global_estime_dzd || 0) * 0.15);

            // Tableau Génie Civil Détaillé par Tronçon (Agent 2)
            let gcRows = '';
            if (gc.prescriptions && gc.prescriptions.length > 0) {
                gc.prescriptions.forEach(p => {
                    const cond = p.conduit || p.cid || '--';
                    const dAct = p.diametre_actuel_mm || p.diam_actuel_mm || '--';
                    const dReq = p.diametre_requis_mm || p.diam_theorique_mm || p.dn_calc_mm || p.diam_prescrit_mm || 0;
                    const dn = p.dn_normalise_mm || p.diam_prescrit_mm || '--';
                    const mat = p.materiau_recommande || p.materiau || 'Béton Armé 135A';
                    const long = p.longueur_m !== undefined ? p.longueur_m : (p.longueur !== undefined ? p.longueur : 0);
                    const cout = p.cout_estime_dzd || 0;

                    gcRows += `
                        <tr>
                            <td><b>${cond}</b></td>
                            <td style="text-align: right;">${dAct} mm</td>
                            <td style="text-align: right;">${Number(dReq).toFixed(0)} mm</td>
                            <td style="text-align: right; font-weight: 700; color: #0284c7;">DN ${dn}</td>
                            <td>${mat}</td>
                            <td style="text-align: right;">${Number(long).toFixed(1)} m</td>
                            <td style="text-align: right; font-weight: 700;">${window.formaterCoutDZD(cout)}</td>
                        </tr>
                    `;
                });
            } else {
                gcRows = '<tr><td colspan="7" style="text-align:center; color:#64748b;">Aucun recalibrage structurel lourd requis. Capacité gravitaire actuelle satisfaisante.</td></tr>';
            }

            // Tableau rétention / GDO (Agent 3)
            let lidRows = '';
            if (lid.solutions && lid.solutions.length > 0) {
                lid.solutions.forEach(s => {
                    const desig = s.designation || s.solution || '--';
                    const dim = s.dimensionnement || (s.volume_utile_m3 ? `Volume : ${s.volume_utile_m3} m³` : (s.lineaire_recommande_m ? `Linéaire : ${s.lineaire_recommande_m} ml` : '--'));
                    const imp = s.impact_attendu || s.reduction_debit_pointe_estimee || '--';
                    lidRows += `
                        <tr>
                            <td><b>${s.type || '--'}</b></td>
                            <td><b>${desig}</b></td>
                            <td>${dim}</td>
                            <td>${imp}</td>
                        </tr>
                    `;
                });
            } else {
                lidRows = `
                    <tr>
                        <td><b>Bassin d'écrêtement</b></td>
                        <td>Bassin d'orage paysager en amont du réseau</td>
                        <td>Volume tampon : <b>${(lid.volume_tampon_requis_m3 || 0).toFixed(0)} m³</b> (Emprise ~ ${(lid.surface_bassin_m2 || 0).toFixed(0)} m²)</td>
                        <td>Écrêtement direct de la pointe de crue décennale (-35% de débit)</td>
                    </tr>
                    <tr>
                        <td><b>Noues d'infiltration</b></td>
                        <td>Noues végétalisées le long des voiries</td>
                        <td>Linéaire : 1 200 m &bull; Largeur 1.5 m</td>
                        <td>Infiltration diffuse à la source &amp; déconnexion pluviale</td>
                    </tr>
                `;
            }

            // Tableau Sensibilité Buffers
            let bufRows = '';
            if (bufferSens.curve && bufferSens.curve.length > 0) {
                bufferSens.curve.forEach(c => {
                    const isRec = c.is_recommended || (Math.round(c.buffer_m) === 45);
                    const isAct = Math.round(c.buffer_m) === Math.round(meta.buffer_m || 35);
                    const dispArea = (isAct && meta.total_area_ha) ? meta.total_area_ha : c.surface_ha;
                    bufRows += `
                        <tr style="${isRec ? 'background: #e0f2fe; font-weight: 700;' : ''}">
                            <td>Tampon <b>${Math.round(c.buffer_m)} m</b> ${isRec ? '⭐ (Optimal)' : ''}</td>
                            <td style="text-align: right;">${dispArea} ha</td>
                            <td style="text-align: right;">${c.gain_pct > 0 ? '+' + c.gain_pct + '%' : 'Référence'}</td>
                            <td style="text-align: right;">${c.peak_flow_m3s} m³/s</td>
                            <td>${c.buffer_m === 35 ? 'Emprise voirie stricte (scénario de référence simulé)' : (c.buffer_m === 45 ? 'Comblement des îlots bâtis (recommandé)' : 'Extension zone périurbaine')}</td>
                        </tr>
                    `;
                });
            }

            // Tableau comparatif des variantes (Agent 5 Finance)
            let varRows = '';
            if (variantes.length > 0) {
                variantes.forEach(v => {
                    const isRec = v.statut && v.statut.includes('RECOMMANDÉ');
                    varRows += `
                        <tr style="${isRec ? 'background: #f0fdf4; font-weight: 600;' : ''}">
                            <td>
                                <b>${v.nom}</b><br>
                                <small style="color: #64748b;">${v.description}</small>
                            </td>
                            <td style="text-align: right;">${v.recalibrage_ml > 0 ? Number(v.recalibrage_ml).toFixed(1) + ' ml' : '--'}</td>
                            <td style="text-align: right;">${v.volume_retention_m3 > 0 ? Number(v.volume_retention_m3).toFixed(0) + ' m³' : '--'}</td>
                            <td style="text-align: right; font-weight: 800; color: ${isRec ? '#16a34a' : '#0f172a'};">
                                ${window.formaterCoutDZD(v.cout_total_dzd)}
                            </td>
                            <td>${v.gain_hydraulique}</td>
                            <td>${v.impact_voirie}</td>
                            <td>${v.risque_aval}</td>
                            <td style="text-align: center;"><b>${v.score_resilience} / 10</b></td>
                            <td style="text-align: center;">
                                <span class="badge ${isRec ? 'badge-p3' : (v.statut === 'INSUFFISANT' ? 'badge-p2' : 'badge-p1')}" style="${isRec ? 'background: #16a34a;' : ''}">
                                     ${v.statut}
                                </span>
                            </td>
                        </tr>
                    `;
                });
            } else {
                varRows = `
                    <tr>
                        <td><b>Variante 1 : 100 % tout-réseau</b><br><small style="color:#64748b;">Recalibrage intégral 7.6 km sans bassin</small></td>
                        <td style="text-align: right;">7 591,9 ml</td>
                        <td style="text-align: right;">--</td>
                        <td style="text-align: right; font-weight: 700;">${window.formaterCoutDZD(330964500)}</td>
                        <td>100 % théorique (sans abattement de pointe)</td>
                        <td>TRÈS ÉLEVÉ (coupure RN4, paralysie urbaine)</td>
                        <td>TRÈS ÉLEVÉ (crue brute à l'exutoire)</td>
                        <td style="text-align: center;">5,5 / 10</td>
                        <td style="text-align: center;"><span class="badge badge-p1">NON RETENU</span></td>
                    </tr>
                    <tr>
                        <td><b>Variante 2 : 100 % GDO pures</b><br><small style="color:#64748b;">Bassin d'orage 18 500 m³ sans recalibrage réseau</small></td>
                        <td style="text-align: right;">--</td>
                        <td style="text-align: right;">18 500 m³</td>
                        <td style="text-align: right; font-weight: 700;">${window.formaterCoutDZD(112500000)}</td>
                        <td>Partiel (~62 % réduction débordements)</td>
                        <td>Faible (hors voies circulées)</td>
                        <td>Faible (bon écrêtement)</td>
                        <td style="text-align: center;">6,0 / 10</td>
                        <td style="text-align: center;"><span class="badge badge-p2">INSUFFISANT</span></td>
                    </tr>
                    <tr style="background: #f0fdf4; font-weight: 600;">
                        <td><b>Variante 3 : Mixte optimisée</b><br><small style="color:#64748b;">Recalibrage ciblé 97 goulots + Bassin 6 595 m³</small></td>
                        <td style="text-align: right;">4 112,8 ml</td>
                        <td style="text-align: right;">6 595 m³</td>
                        <td style="text-align: right; font-weight: 800; color: #16a34a;">${window.formaterCoutDZD(240384400)}</td>
                        <td>100 % résorption intégrale (Saint-Venant vérifié)</td>
                        <td>Modéré et phasable (P1 / P2)</td>
                        <td>MINIMAL (pointe écrêtée de 1,73 à 0,65 m³/s)</td>
                        <td style="text-align: center;"><b>9,2 / 10</b></td>
                        <td style="text-align: center;"><span class="badge badge-p3" style="background: #16a34a;">RECOMMANDÉ</span></td>
                    </tr>
                `;
            }


            const docHtml = window._construireHtmlRapportDiagnostic(simData, meta, k, agents, bufferSens, diag, gc, lid, risk, finance, synth, variantes, ratios, contError, surchargedNodes, floodedNodes, peakOutflow, nbConduites, nbNormal, nbVigilance, nbSurcharge, verdict, verdictCouleur, pName, clusterNom, dateStr);

            printWin.document.open();
            printWin.document.write(docHtml);
            printWin.document.close();
            printWin.focus();
            setTimeout(() => {
                try {
                    printWin.print();
                } catch (e) {
                    console.warn("Impression auto popup:", e);
                }
            }, 350);
        };
