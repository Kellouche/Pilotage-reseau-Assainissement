/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Modèle HTML des onglets experts du collège multi-agents (Diagnostic, GDO, Risques, Finances)
 * ================================================================================
 */

window._construireHtmlCorpsInterpretation = function(simData, k, cRes, nRes, meta, agents, bufferSens, diag, gc, lid, risk, finance, synth, variantes, ratios, contError, surchargedNodes, floodedNodes, peakOutflow, nbConduites, nbNormal, nbVigilance, nbSurcharge, verdict, verdictCouleur) {
    let html = `
                <!-- Barre supérieure synthétique -->
                <div style="background: rgba(255, 255, 255, 0.03); border: 1px solid ${verdictCouleur}55; border-left: 6px solid ${verdictCouleur}; border-radius: 12px; padding: 14px 18px; margin-bottom: 12px;">
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
                        <span style="font-size: 1.05rem; font-weight: 800; color: ${verdictCouleur}; display: flex; align-items: center; gap: 8px;">
                            <i class="fas fa-brain"></i> ${verdict}
                        </span>
                        <span style="font-size: 0.75rem; background: ${verdictCouleur}22; color: ${verdictCouleur}; border: 1px solid ${verdictCouleur}55; padding: 3px 10px; border-radius: 20px; font-weight: 700;">
                            ${meta.cluster_nom ? meta.cluster_nom : 'Réseau Complet'} &bull; ${meta.scenario ? meta.scenario : 'SWMM 5.2'}
                        </span>
                    </div>
                    <p style="margin: 0; color: #cbd5e1; font-size: 0.86rem; line-height: 1.45;">
                        ${synth.recommandation_cle || "Analyse automatisée par l'équipe de 5 agents d'expertise : identification des causes racines, calculs de dimensionnement génie civil et solutions alternatives."}
                    </p>
                </div>

                <!-- Cadre Hydro-Météorologique de Dimensionnement (Référentiel ANRH / UHBC Chlef) -->
                <div style="background: rgba(14, 165, 233, 0.08); border: 1px solid rgba(56, 189, 248, 0.35); border-left: 5px solid #38bdf8; border-radius: 10px; padding: 10px 16px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; font-size: 0.82rem;">
                    <div>
                        <span style="color: #94a3b8;"><i class="fas fa-cloud-showers-heavy me-1" style="color: #38bdf8;"></i> Station Hydro-Météo :</span>
                        <b style="color: #f8fafc; margin-left: 6px;">${meta.pluvio_station || k.pluvio_station || 'Station ANRH Chlef Siège (010501)'}</b>
                        <span style="color: #94a3b8; margin-left: 10px;">&bull; Formule Montana :</span>
                        <code style="color: #fbbf24; margin-left: 4px; font-size: 0.78rem;">${meta.pluvio_montana || k.pluvio_montana || 'I(t) = 9.334 · t^(-0.745)'}</code>
                    </div>
                    <div>
                        <span style="color: #94a3b8;">Intensité Pointe Imax :</span>
                        <span style="color: #38bdf8; font-weight: 900; font-size: 1.05rem; margin-left: 6px;">${k.pluvio_intensite_max_mmh || meta.pluvio_intensite_max_mmh || 74.9} mm/h</span>
                        <span style="font-size: 0.72rem; color: #7dd3fc; background: rgba(56,189,248,0.18); border: 1px solid rgba(56,189,248,0.4); padding: 2px 7px; border-radius: 4px; margin-left: 6px; font-weight: 700;">${meta.pluvio_periode_retour || k.pluvio_periode_retour || 'T = 10 ans'}</span>
                    </div>
                </div>

                <!-- Cadre de Validation Hydrologique (Horton / Voronoï / SWMM) -->
                <div style="background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 10px 16px; margin-bottom: 16px; display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; font-size: 0.78rem;">
                    <div>
                        <span style="color: #94a3b8; display: block; font-size: 0.7rem; text-transform: uppercase;">Discrétisation spatiale</span>
                        <b style="color: #f8fafc;">${meta.subcatchments_count || 703} Sous-bassins</b>
                        <span style="color: #64748b; display: block; font-size: 0.68rem;">Voronoï (${meta.buffer_m || 35}m) &bull; ${meta.total_area_ha || 117.83} ha</span>
                    </div>
                    <div>
                        <span style="color: #94a3b8; display: block; font-size: 0.7rem; text-transform: uppercase;">Imperméabilisation</span>
                        <b style="color: #38bdf8;">C_imp = ${meta.imperv_pct || 65}%</b>
                        <span style="color: #64748b; display: block; font-size: 0.68rem;">${meta.typologie_nom || 'Habitat mixte urbain'}</span>
                    </div>
                    <div>
                        <span style="color: #94a3b8; display: block; font-size: 0.7rem; text-transform: uppercase;">Infiltration des sols</span>
                        <b style="color: #f8fafc;">Loi d'Horton</b>
                        <span style="color: #64748b; display: block; font-size: 0.68rem;">f₀=76.2 &bull; f∞=13.2 &bull; k=4.14 h⁻¹</span>
                    </div>
                    <div>
                        <span style="color: #94a3b8; display: block; font-size: 0.7rem; text-transform: uppercase;">Temps de concentration</span>
                        <b style="color: #f8fafc;">tc ≈ 15.0 min</b>
                        <span style="color: #64748b; display: block; font-size: 0.68rem;">Kirpich / Passini (Pente ${meta.pente_moyenne_pct || 1.0}%)</span>
                    </div>
                </div>

                <!-- Barre de navigation des 7 onglets Agents IA -->
                <div style="display: flex; gap: 6px; overflow-x: auto; margin-bottom: 16px; padding-bottom: 4px; border-bottom: 1px solid rgba(255,255,255,0.08);">
                    <button id="btn-tab-agent-diag" onclick="changerOngletAgent('agent-diag')" class="agent-tab-btn" style="padding: 7px 12px; font-size: 0.78rem; font-weight: 700; border-radius: 8px; cursor: pointer; border: 1px solid #a855f7; background: rgba(168, 85, 247, 0.2); color: #f8fafc; white-space: nowrap; display: flex; align-items: center; gap: 6px;">
                        <i class="fas fa-search-plus"></i> 1. Diagnostic causal
                    </button>
                    <button id="btn-tab-agent-gc" onclick="changerOngletAgent('agent-gc')" class="agent-tab-btn" style="padding: 7px 12px; font-size: 0.78rem; font-weight: 700; border-radius: 8px; cursor: pointer; border: 1px solid rgba(255,255,255,0.12); background: rgba(255,255,255,0.05); color: #94a3b8; white-space: nowrap; display: flex; align-items: center; gap: 6px;">
                        <i class="fas fa-drafting-compass"></i> 2. Génie civil et dimensionnement
                    </button>
                    <button id="btn-tab-agent-lid" onclick="changerOngletAgent('agent-lid')" class="agent-tab-btn" style="padding: 7px 12px; font-size: 0.78rem; font-weight: 700; border-radius: 8px; cursor: pointer; border: 1px solid rgba(255,255,255,0.12); background: rgba(255,255,255,0.05); color: #94a3b8; white-space: nowrap; display: flex; align-items: center; gap: 6px;">
                        <i class="fas fa-leaf"></i> 3. Rétention et gestion durable des ouvrages (GDO)
                    </button>
                    <button id="btn-tab-agent-risk" onclick="changerOngletAgent('agent-risk')" class="agent-tab-btn" style="padding: 7px 12px; font-size: 0.78rem; font-weight: 700; border-radius: 8px; cursor: pointer; border: 1px solid rgba(255,255,255,0.12); background: rgba(255,255,255,0.05); color: #94a3b8; white-space: nowrap; display: flex; align-items: center; gap: 6px;">
                        <i class="fas fa-exclamation-triangle"></i> 4. Priorisation des risques
                    </button>
                    <button id="btn-tab-agent-finance" onclick="changerOngletAgent('agent-finance')" class="agent-tab-btn" style="padding: 7px 12px; font-size: 0.78rem; font-weight: 700; border-radius: 8px; cursor: pointer; border: 1px solid rgba(255,255,255,0.12); background: rgba(255,255,255,0.05); color: #94a3b8; white-space: nowrap; display: flex; align-items: center; gap: 6px;">
                        <i class="fas fa-coins"></i> 5. Variantes et ingénierie financière
                    </button>
                    <button id="btn-tab-agent-synth" onclick="changerOngletAgent('agent-synth')" class="agent-tab-btn" style="padding: 7px 12px; font-size: 0.78rem; font-weight: 700; border-radius: 8px; cursor: pointer; border: 1px solid rgba(255,255,255,0.12); background: rgba(255,255,255,0.05); color: #94a3b8; white-space: nowrap; display: flex; align-items: center; gap: 6px;">
                        <i class="fas fa-file-contract"></i> 6. Note exécutive stratégique
                    </button>
                    <button id="btn-tab-agent-buffer" onclick="changerOngletAgent('agent-buffer')" class="agent-tab-btn" style="padding: 7px 12px; font-size: 0.78rem; font-weight: 700; border-radius: 8px; cursor: pointer; border: 1px solid rgba(255,255,255,0.12); background: rgba(255,255,255,0.05); color: #94a3b8; white-space: nowrap; display: flex; align-items: center; gap: 6px;">
                        <i class="fas fa-chart-line"></i> 7. Courbe buffer
                    </button>
                </div>

                <!-- CONTENU DE L'ONGLET 1 : DIAGNOSTIC CAUSAL -->
                <div id="pane-agent-diag" class="agent-tab-pane" style="display: block;">
                    <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 16px; margin-bottom: 14px;">
                        <div style="background: rgba(56, 189, 248, 0.08); border-left: 4px solid #38bdf8; border-radius: 6px; padding: 10px 14px; margin-bottom: 14px; font-size: 0.82rem; color: #e2e8f0; line-height: 1.5;">
                            <strong style="color: #38bdf8; display: block; margin-bottom: 4px;"><i class="fas fa-microscope me-1"></i> Mémoire Technique du Diagnosticien Saint-Venant (Agent 1) :</strong>
                            ${diag.note_technique || "L'analyse hydrodynamique 1D Saint-Venant (Dynamic Wave) met en évidence un régime d'écoulement sous forte tension lors du pic d'intensité pluviométrique."}
                        </div>
                        <div style="font-weight: 700; font-size: 0.88rem; color: #38bdf8; margin-bottom: 10px; display: flex; align-items: center; gap: 6px;">
                            <i class="fas fa-microscope"></i> Identification des causes racines et anomalies hydrauliques
                        </div>
                        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 12px;">
                            <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.25); border-radius: 8px; padding: 10px; text-align: center;">
                                <div style="font-size: 0.72rem; color: #f87171;">Regards submergés</div>
                                <div style="font-size: 1.25rem; font-weight: 800; color: #f87171;">${floodedNodes}</div>
                            </div>
                            <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.25); border-radius: 8px; padding: 10px; text-align: center;">
                                <div style="font-size: 0.72rem; color: #fbbf24;">Conduites en charge</div>
                                <div style="font-size: 1.25rem; font-weight: 800; color: #fbbf24;">${nbSurcharge}</div>
                            </div>
                            <div style="background: rgba(2, 132, 199, 0.1); border: 1px solid rgba(2, 132, 199, 0.25); border-radius: 8px; padding: 10px; text-align: center;">
                                <div style="font-size: 0.72rem; color: #38bdf8;">Étranglements détectés</div>
                                <div style="font-size: 1.25rem; font-weight: 800; color: #38bdf8;">${diag.nb_goulots || 0}</div>
                            </div>
                        </div>

                        ${(diag.bottlenecks && diag.bottlenecks.length > 0) ? `
                            <div style="font-size: 0.8rem; font-weight: 700; color: #facc15; margin-bottom: 6px;">
                                <i class="fas fa-exclamation-circle me-1"></i> Goulots d'étranglement géométriques détectés :
                            </div>
                            <div style="display: grid; gap: 6px; margin-bottom: 12px;">
                                ${diag.bottlenecks.map(b => `
                                    <div style="background: rgba(250, 204, 21, 0.08); border: 1px solid rgba(250, 204, 21, 0.25); border-radius: 6px; padding: 8px 12px; font-size: 0.8rem; color: #f8fafc;">
                                        ${b.description}
                                    </div>
                                `).join('')}
                            </div>
                        ` : ''}

                        ${(diag.flooded_nodes && diag.flooded_nodes.length > 0) ? `
                            <div style="font-size: 0.8rem; font-weight: 700; color: #f87171; margin-bottom: 6px;">
                                <i class="fas fa-water me-1"></i> Regards de visite en débordement critique :
                            </div>
                            <div style="display: grid; gap: 6px;">
                                ${diag.flooded_nodes.map(fn => `
                                    <div style="background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.25); border-radius: 6px; padding: 8px 12px; display: flex; justify-content: space-between; align-items: center; font-size: 0.8rem;">
                                        <div>
                                            <strong style="color: #ef4444;">Regard ${fn.node_id}</strong>
                                            <span style="color: #94a3b8; font-size: 0.72rem; margin-left: 6px;">Inondation chaussée</span>
                                        </div>
                                        <div style="display: flex; gap: 12px; color: #cbd5e1;">
                                            <span>Durée : <b>${fn.hours_flooded} h</b></span>
                                            <span>Volume : <b style="color: #ef4444;">${(fn.flood_volume_m3 !== undefined && fn.flood_volume_m3 > 0) ? (fn.flood_volume_m3 < 1.0 ? `${Number(fn.flood_volume_m3).toFixed(2)} m³ (${Math.round(fn.flood_volume_m3 * 1000)} L)` : `${Number(fn.flood_volume_m3).toFixed(1)} m³`) : '< 0.05 m³'}</b></span>
                                            <span>Pointe : <b>${fn.peak_flow_cms} m³/s</b></span>
                                        </div>
                                    </div>
                                `).join('')}
                            </div>
                        ` : '<div style="color: #34d399; font-size: 0.82rem;"><i class="fas fa-check-circle me-1"></i> Aucun débordement en surface constaté sur les regards.</div>'}
                    </div>
                </div>

                <!-- CONTENU DE L'ONGLET 2 : GÉNIE CIVIL & DIMENSIONNEMENT -->
                <div id="pane-agent-gc" class="agent-tab-pane" style="display: none;">
                    <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 16px; margin-bottom: 14px;">
                        <div style="background: rgba(52, 211, 153, 0.08); border-left: 4px solid #34d399; border-radius: 6px; padding: 10px 14px; margin-bottom: 14px; font-size: 0.82rem; color: #e2e8f0; line-height: 1.5;">
                            <strong style="color: #34d399; display: block; margin-bottom: 4px;"><i class="fas fa-ruler-combined me-1"></i> Mémoire technique de dimensionnement Manning et recalibrage (Agent 2) :</strong>
                            ${gc.note_technique || "Prescriptions de recalibrage selon la formule de Manning-Strickler avec marge de sécurité de +25% afin de maintenir un tirant d'eau maximal H/D <= 0.80."}
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <div style="font-weight: 700; font-size: 0.88rem; color: #34d399; display: flex; align-items: center; gap: 6px;">
                                <i class="fas fa-ruler-combined"></i> Prescriptions de recalibrage (formule de Manning-Strickler)
                            </div>
                            <span style="font-size: 0.74rem; color: #94a3b8;">
                                Linéaire : <b style="color: #38bdf8;">${(gc.metres_lineaires_totaux || 0).toFixed(1)} ml</b> &bull; Budget : <b style="color: #34d399;">${window.formaterCoutDZD(gc.cout_global_estime_dzd)}</b>
                            </span>
                        </div>

                        ${(gc.recapitulatif_par_dn && gc.recapitulatif_par_dn.length > 0) ? `
                            <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 10px; margin-bottom: 12px;">
                                <div style="font-size: 0.78rem; font-weight: 700; color: #38bdf8; margin-bottom: 6px;">
                                    <i class="fas fa-layer-group me-1"></i> Répartition des métrés par diamètre et matériau :
                                </div>
                                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 6px;">
                                    ${gc.recapitulatif_par_dn.map(r => `
                                        <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255,255,255,0.06); border-radius: 6px; padding: 6px 8px; font-size: 0.72rem;">
                                            <div style="font-weight: 800; color: #34d399;">${r.label} <span style="font-weight: 400; color: #94a3b8; font-size: 0.68rem;">(${r.materiau.includes('PEHD') ? 'PEHD' : 'Béton'})</span></div>
                                            <div style="color: #f8fafc; font-weight: 700; margin: 2px 0;">${r.lineaire_ml} ml <span style="color:#64748b; font-weight: 400;">(${r.pct_lineaire}%)</span></div>
                                            <div style="color: #38bdf8; font-weight: 600;">${window.formaterCoutDZD(r.cout_total_dzd)}</div>
                                        </div>
                                    `).join('')}
                                </div>
                            </div>
                        ` : ''}

                        ${gc.nb_troncons_suffisants_remous > 0 ? `
                            <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 6px; padding: 7px 10px; margin-bottom: 12px; font-size: 0.74rem; color: #a7f3d0;">
                                <i class="fas fa-shield-alt me-1" style="color: #34d399;"></i>
                                <b>Optimisation de la capacité résiduelle :</b> <b>${gc.nb_troncons_suffisants_remous} tronçon(s)</b> ont été préservés de travaux lourds car leur section actuelle est hydrauliquement suffisante (surcharge due au remous aval résolue par décongestionnement aval).
                            </div>
                        ` : ''}
                        <p style="font-size: 0.78rem; color: #94a3b8; margin: 0 0 12px 0; line-height: 1.4;">
                            Diamètres cibles calculés pour garantir un taux de remplissage maximal de 80% ($Q/Q_{\\text{cap}} \\le 0.8$) lors de l'événement pluvial de pointe :
                        </p>

                        ${(gc.prescriptions && gc.prescriptions.length > 0) ? `
                            <table style="width: 100%; border-collapse: collapse; font-size: 0.78rem; color: #cbd5e1;">
                                <thead>
                                    <tr style="border-bottom: 1px solid rgba(255,255,255,0.12); color: #94a3b8; text-align: left;">
                                        <th style="padding: 6px 4px;">Tronçon</th>
                                        <th style="padding: 6px 4px;">Actuel</th>
                                        <th style="padding: 6px 4px;">Prescrit</th>
                                        <th style="padding: 6px 4px;">Gain de capacité</th>
                                        <th style="padding: 6px 4px;">Matériau</th>
                                        <th style="padding: 6px 4px; text-align: right;">Coût estimé</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${gc.prescriptions.map(p => `
                                        <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                                            <td style="padding: 6px 4px; font-weight: 700; color: #38bdf8;">${p.cid}</td>
                                            <td style="padding: 6px 4px; color: #f87171;">Ø${p.diam_actuel_mm} mm</td>
                                            <td style="padding: 6px 4px; font-weight: 800; color: #34d399;">Ø${p.diam_prescrit_mm} mm</td>
                                            <td style="padding: 6px 4px; color: #34d399;">+${p.gain_capacite_pct}%</td>
                                            <td style="padding: 6px 4px; color: #cbd5e1;">${p.materiau}</td>
                                            <td style="padding: 6px 4px; text-align: right; font-weight: 700;">${window.formaterCoutDZD(p.cout_estime_dzd)}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        ` : '<div style="color: #34d399; font-size: 0.82rem;"><i class="fas fa-check me-1"></i> Aucune conduite ne requiert de recalibrage de diamètre pour cet événement.</div>'}
                    </div>
                </div>

                <!-- CONTENU DE L'ONGLET 3 : HYDROLOGIE DURABLE & RÉTENTION -->
                <div id="pane-agent-lid" class="agent-tab-pane" style="display: none;">
                    <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 16px; margin-bottom: 14px;">
                        <div style="background: rgba(16, 185, 129, 0.08); border-left: 4px solid #10b981; border-radius: 6px; padding: 10px 14px; margin-bottom: 14px; font-size: 0.82rem; color: #e2e8f0; line-height: 1.5;">
                            <strong style="color: #10b981; display: block; margin-bottom: 4px;"><i class="fas fa-leaf me-1"></i> Mémoire technique de gestion pluviale à la source &bull; Solutions de gestion durable des ouvrages (GDO) (Agent 3) :</strong>
                            ${lid.note_technique || "Stratégie d'interception et de temporisation à la source par des solutions de gestion durable des ouvrages (GDO) pour rabattre la pointe de débit."}
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <div style="font-weight: 700; font-size: 0.88rem; color: #10b981; display: flex; align-items: center; gap: 6px;">
                                <i class="fas fa-tint"></i> Solutions de gestion durable des ouvrages (GDO) et écrêtement de crue
                            </div>
                            <span style="font-size: 0.74rem; background: rgba(16, 185, 129, 0.15); color: #34d399; padding: 2px 8px; border-radius: 4px; font-weight: 700;">
                                Tampon requis : ${lid.volume_tampon_requis_m3 || 500} m³
                            </span>
                        </div>
                        <p style="font-size: 0.78rem; color: #94a3b8; margin: 0 0 12px 0; line-height: 1.4;">
                            Alternatives écologiques et durables évitant le « tout-tuyau » et la surcharge des collecteurs avals :
                        </p>

                        <div style="display: grid; gap: 10px;">
                            ${(lid.solutions || []).map(s => `
                                <div style="background: rgba(16, 185, 129, 0.06); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: 8px; padding: 10px 14px;">
                                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                                        <span style="font-weight: 800; font-size: 0.85rem; color: #34d399;">${s.solution}</span>
                                        <span style="font-size: 0.72rem; color: #38bdf8; font-weight: 700;">Abattement : ${s.reduction_debit_pointe_estimee}</span>
                                    </div>
                                    <div style="font-size: 0.78rem; color: #cbd5e1; margin-bottom: 4px;">${s.type}</div>
                                    <div style="font-size: 0.72rem; color: #94a3b8;">
                                        💡 <b>Bénéfice :</b> ${s.avantage}
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>

                <!-- CONTENU DE L'ONGLET 4 : PRIORISATION DES RISQUES (P1, P2, P3) -->
                <div id="pane-agent-risk" class="agent-tab-pane" style="display: none;">
                    <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 16px; margin-bottom: 14px;">
                        <div style="background: rgba(245, 158, 11, 0.08); border-left: 4px solid #f59e0b; border-radius: 6px; padding: 10px 14px; margin-bottom: 14px; font-size: 0.82rem; color: #e2e8f0; line-height: 1.5;">
                            <strong style="color: #f59e0b; display: block; margin-bottom: 4px;"><i class="fas fa-shield-alt me-1"></i> Mémoire technique de priorisation multicritère des risques (Agent 4) :</strong>
                            ${risk.note_technique || "Hiérarchisation multicritère des interventions (P1 Critique sous 3 mois, P2 Majeur sous 12 mois, P3 Maintenance préventive) pour optimiser les investissements."}
                        </div>
                        <div style="font-weight: 700; font-size: 0.88rem; color: #f59e0b; margin-bottom: 10px; display: flex; align-items: center; gap: 6px;">
                            <i class="fas fa-layer-group"></i> Matrice de hiérarchisation des travaux et investissements
                        </div>

                        <!-- Priorité 1 : Critique -->
                        <div style="margin-bottom: 12px;">
                            <div style="font-size: 0.78rem; font-weight: 800; color: #ef4444; margin-bottom: 6px; display: flex; align-items: center; justify-content: space-between;">
                                <div style="display: flex; align-items: center; gap: 6px;">
                                    <span style="background: #ef4444; color: white; padding: 1px 6px; border-radius: 4px; font-size: 0.68rem;">P1</span>
                                    Priorité 1 — Urgence critique (submersion de voirie et habitations)
                                </div>
                                <span style="font-size: 0.72rem; color: #f87171; font-weight: 700;">${window.formaterCoutDZD((risk.synthese && risk.synthese.cout_p1_dzd) || 0)}</span>
                            </div>
                            ${(risk.actions_priorisees && risk.actions_priorisees.P1 && risk.actions_priorisees.P1.length > 0) ? `
                                <div style="display: grid; gap: 6px;">
                                    ${risk.actions_priorisees.P1.map(a => `
                                        <div style="background: rgba(239, 68, 68, 0.08); border-left: 3px solid #ef4444; padding: 8px 12px; font-size: 0.78rem; color: #cbd5e1; border-radius: 4px;">
                                            <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px;">
                                                <strong style="color: #f87171;">${a.conduite || a.cible}</strong>
                                                <span style="font-weight: 800; color: #38bdf8; font-size: 0.78rem;">${window.formaterCoutDZD(a.estimation_cout_dzd)}</span>
                                            </div>
                                            <div style="font-size: 0.75rem; color: #94a3b8;">${a.type_risque || a.probleme} ➔ <i style="color: #f8fafc;">${a.action_requise || a.action}</i></div>
                                        </div>
                                    `).join('')}
                                </div>
                            ` : '<div style="font-size: 0.75rem; color: #34d399; padding: 4px 0;"><i class="fas fa-check-circle me-1"></i> Aucune action P1 requise.</div>'}
                        </div>

                        <!-- Priorité 2 : Majeur -->
                        <div style="margin-bottom: 12px;">
                            <div style="font-size: 0.78rem; font-weight: 800; color: #f59e0b; margin-bottom: 6px; display: flex; align-items: center; justify-content: space-between;">
                                <div style="display: flex; align-items: center; gap: 6px;">
                                    <span style="background: #f59e0b; color: white; padding: 1px 6px; border-radius: 4px; font-size: 0.68rem;">P2</span>
                                    Priorité 2 — Alerte majeure (mise en charge continue sans inondation)
                                </div>
                                <span style="font-size: 0.72rem; color: #fbbf24; font-weight: 700;">${window.formaterCoutDZD((risk.synthese && risk.synthese.cout_p2_dzd) || 0)}</span>
                            </div>
                            ${(risk.actions_priorisees && risk.actions_priorisees.P2 && risk.actions_priorisees.P2.length > 0) ? `
                                <div style="display: grid; gap: 6px;">
                                    ${risk.actions_priorisees.P2.map(a => `
                                        <div style="background: rgba(245, 158, 11, 0.08); border-left: 3px solid #f59e0b; padding: 8px 12px; font-size: 0.78rem; color: #cbd5e1; border-radius: 4px;">
                                            <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px;">
                                                <strong style="color: #fbbf24;">${a.conduite || a.cible}</strong>
                                                <span style="font-weight: 800; color: #38bdf8; font-size: 0.78rem;">${window.formaterCoutDZD(a.estimation_cout_dzd)}</span>
                                            </div>
                                            <div style="font-size: 0.75rem; color: #94a3b8;">${a.type_risque || a.probleme} ➔ <i style="color: #f8fafc;">${a.action_requise || a.action}</i></div>
                                        </div>
                                    `).join('')}
                                </div>
                            ` : '<div style="font-size: 0.75rem; color: #34d399; padding: 4px 0;"><i class="fas fa-check-circle me-1"></i> Aucune action P2 requise.</div>'}
                        </div>

                        <!-- Priorité 3 : Maintenance -->
                        <div>
                            <div style="font-size: 0.78rem; font-weight: 800; color: #38bdf8; margin-bottom: 6px; display: flex; align-items: center; justify-content: space-between;">
                                <div style="display: flex; align-items: center; gap: 6px;">
                                    <span style="background: #0284c7; color: white; padding: 1px 6px; border-radius: 4px; font-size: 0.68rem;">P3</span>
                                    Priorité 3 — Maintenance préventive (autocurage et pentes)
                                </div>
                                <span style="font-size: 0.72rem; color: #38bdf8; font-weight: 700;">${window.formaterCoutDZD((risk.synthese && risk.synthese.cout_p3_dzd) || 0)}</span>
                            </div>
                            ${(risk.actions_priorisees && risk.actions_priorisees.P3 && risk.actions_priorisees.P3.length > 0) ? `
                                <div style="display: grid; gap: 6px;">
                                    ${risk.actions_priorisees.P3.map(a => `
                                        <div style="background: rgba(2, 132, 199, 0.08); border-left: 3px solid #0284c7; padding: 8px 12px; font-size: 0.78rem; color: #cbd5e1; border-radius: 4px;">
                                            <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px;">
                                                <strong style="color: #38bdf8;">${a.conduite || a.cible}</strong>
                                                <span style="font-weight: 800; color: #38bdf8; font-size: 0.78rem;">${window.formaterCoutDZD(a.estimation_cout_dzd)}</span>
                                            </div>
                                            <div style="font-size: 0.75rem; color: #94a3b8;">${a.type_risque || a.probleme} ➔ <i style="color: #f8fafc;">${a.action_requise || a.action}</i></div>
                                        </div>
                                    `).join('')}
                                </div>
                            ` : '<div style="font-size: 0.75rem; color: #34d399; padding: 4px 0;"><i class="fas fa-check-circle me-1"></i> Auto-curage satisfaisant sur l\'ensemble du linéaire.</div>'}
                        </div>
                    </div>
                </div>

                <!-- CONTENU DE L'ONGLET 5 : ANALYSE DES VARIANTES & INGÉNIERIE FINANCIÈRE -->
                <div id="pane-agent-finance" class="agent-tab-pane" style="display: none;">
                    <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 16px; margin-bottom: 14px;">
                        <div style="background: rgba(16, 185, 129, 0.08); border-left: 4px solid #10b981; border-radius: 6px; padding: 10px 14px; margin-bottom: 14px; font-size: 0.82rem; color: #e2e8f0; line-height: 1.5;">
                            <strong style="color: #34d399; display: block; margin-bottom: 4px;"><i class="fas fa-coins me-1"></i> Mémoire de l'expert financier et marchés publics (Agent 5) :</strong>
                            ${(agents.analyse_variantes_financiere && agents.analyse_variantes_financiere.note_technique) ? agents.analyse_variantes_financiere.note_technique : "L'analyse multicritère démontre la supériorité de la Variante 3 (mixte optimisée). En limitant les travaux lourds aux 97 goulots à déficit avéré (4 112.8 ml) et en créant un bassin d'écrêtement amont (6 595 m³), le coût est de 240.38 M DZD, soit 90.6 M DZD d'économie (-27.4%) par rapport au tout-réseau."}
                        </div>

                        <div style="font-weight: 700; font-size: 0.92rem; color: #34d399; margin-bottom: 10px; display: flex; align-items: center; justify-content: space-between;">
                            <span><i class="fas fa-balance-scale me-1"></i> Comparatif multicritère des 3 variantes d'aménagement</span>
                            <span style="font-size: 0.76rem; background: rgba(16,185,129,0.18); color: #34d399; border: 1px solid rgba(16,185,129,0.4); padding: 2px 8px; border-radius: 4px; font-weight: 700;">
                                Gain net : 90,58 M DZD (-27,4%)
                            </span>
                        </div>

                        <!-- Grille des 3 Cartes Variantes -->
                        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px;">
                            <!-- V1 -->
                            <div style="background: rgba(239, 68, 68, 0.06); border: 1.5px solid rgba(239, 68, 68, 0.3); border-radius: 10px; padding: 12px;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                    <span style="font-weight: 800; font-size: 0.84rem; color: #f87171;">V1 : 100 % tout-réseau</span>
                                    <span style="font-size: 0.68rem; background: rgba(239,68,68,0.2); color: #fca5a5; padding: 1px 6px; border-radius: 3px; font-weight: 700;">NON RETENU</span>
                                </div>
                                <div style="font-size: 1.15rem; font-weight: 900; color: #f8fafc; margin-bottom: 4px;">330 964 500,00 DZD</div>
                                <div style="font-size: 0.74rem; color: #94a3b8; line-height: 1.4; margin-bottom: 8px;">
                                    Recalibrage intégral de 7 591,9 ml de conduites sans bassin d'écrêtement amont.
                                </div>
                                <div style="font-size: 0.72rem; color: #cbd5e1; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 6px;">
                                    <div>🚨 <b>Impact voirie :</b> Très Élevé (7.6 km coupés)</div>
                                    <div>🌊 <b>Risque aval :</b> Crue brute à l'exutoire</div>
                                    <div>⏱️ <b>Délai :</b> 18 à 24 mois</div>
                                    <div>⭐ <b>Résilience :</b> 5,5 / 10</div>
                                </div>
                            </div>

                            <!-- V2 -->
                            <div style="background: rgba(245, 158, 11, 0.06); border: 1.5px solid rgba(245, 158, 11, 0.3); border-radius: 10px; padding: 12px;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                    <span style="font-weight: 800; font-size: 0.84rem; color: #fbbf24;">V2 : 100 % gestion durable des ouvrages (GDO)</span>
                                    <span style="font-size: 0.68rem; background: rgba(245,158,11,0.2); color: #fde68a; padding: 1px 6px; border-radius: 3px; font-weight: 700;">INSUFFISANT</span>
                                </div>
                                <div style="font-size: 1.15rem; font-weight: 900; color: #f8fafc; margin-bottom: 4px;">112 500 000,00 DZD</div>
                                <div style="font-size: 0.74rem; color: #94a3b8; line-height: 1.4; margin-bottom: 8px;">
                                    Bassin géant (18 500 m³) + noues sans recalibrage de collecteurs sous voirie.
                                </div>
                                <div style="font-size: 0.72rem; color: #cbd5e1; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 6px;">
                                    <div>⚠️ <b>Efficacité :</b> ~62% (débordements résiduels)</div>
                                    <div>🏞️ <b>Emprise :</b> Très Élevée (~2.5 ha foncier)</div>
                                    <div>⏱️ <b>Délai :</b> 12 à 15 mois</div>
                                    <div>⭐ <b>Résilience :</b> 6,0 / 10</div>
                                </div>
                            </div>

                            <!-- V3 -->
                            <div style="background: rgba(16, 185, 129, 0.1); border: 2px solid #10b981; border-radius: 10px; padding: 12px; box-shadow: 0 0 15px rgba(16, 185, 129, 0.2);">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                    <span style="font-weight: 800; font-size: 0.84rem; color: #34d399;">V3 : Mixte optimisée</span>
                                    <span style="font-size: 0.68rem; background: #10b981; color: white; padding: 2px 7px; border-radius: 3px; font-weight: 800;">RECOMMANDÉ</span>
                                </div>
                                <div style="font-size: 1.25rem; font-weight: 900; color: #34d399; margin-bottom: 4px;">240 384 400,00 DZD</div>
                                <div style="font-size: 0.74rem; color: #cbd5e1; line-height: 1.4; margin-bottom: 8px;">
                                    Recalibrage ciblé 97 goulots (4 112,8 ml) + Bassin amont régulé 6 595 m³ + noues.
                                </div>
                                <div style="font-size: 0.72rem; color: #f8fafc; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 6px;">
                                    <div>✅ <b>Efficacité :</b> 100% résorption hydrodynamique</div>
                                    <div>📉 <b>Économie :</b> 90 580 100,00 DZD (-27,4%)</div>
                                    <div>🛡️ <b>Protection aval :</b> Débit pointe écrêté à 0,65 m³/s</div>
                                    <div>⭐ <b>Résilience :</b> 9,2 / 10</div>
                                </div>
                            </div>
                        </div>

                        <!-- KPIs Ratios Directeurs & Rentabilité -->
                        <div style="font-weight: 700; font-size: 0.88rem; color: #38bdf8; margin-bottom: 8px;">
                            <i class="fas fa-chart-pie me-1"></i> Ratios directeurs et indicateurs décisionnels (aide à la décision ONA / wilaya)
                        </div>
                        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; font-size: 0.78rem;">
                            <div style="background: rgba(255,255,255,0.03); padding: 8px 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.08);">
                                <span style="color: #94a3b8; display: block; font-size: 0.7rem;">Coût par ml rénové</span>
                                <b style="color: #38bdf8; font-size: 0.95rem;">${window.formaterCoutDZD(agents.analyse_variantes_financiere?.ratios_decisionnels?.cout_par_ml_renove_dzd || 47871)} / ml</b>
                                <small style="color: #64748b; display: block; font-size: 0.68rem;">Base 4 112.8 ml ciblés</small>
                            </div>
                            <div style="background: rgba(255,255,255,0.03); padding: 8px 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.08);">
                                <span style="color: #94a3b8; display: block; font-size: 0.7rem;">Coût par habitant</span>
                                <b style="color: #38bdf8; font-size: 0.95rem;">${window.formaterCoutDZD(agents.analyse_variantes_financiere?.ratios_decisionnels?.cout_par_habitant_protege_dzd || 16026)} / hab</b>
                                <small style="color: #64748b; display: block; font-size: 0.68rem;">15 000 hab équivalents</small>
                            </div>
                            <div style="background: rgba(16,185,129,0.08); padding: 8px 10px; border-radius: 6px; border: 1px solid rgba(16,185,129,0.25);">
                                <span style="color: #34d399; display: block; font-size: 0.7rem; font-weight: 700;">Dommages annuels évités</span>
                                <b style="color: #34d399; font-size: 0.95rem;">45,0 M DZD / an</b>
                                <small style="color: #6ee7b7; display: block; font-size: 0.68rem;">Voirie, sous-sols, caves, RN4</small>
                            </div>
                            <div style="background: rgba(16,185,129,0.08); padding: 8px 10px; border-radius: 6px; border: 1px solid rgba(16,185,129,0.25);">
                                <span style="color: #34d399; display: block; font-size: 0.7rem; font-weight: 700;">Rentabilité socio-économique</span>
                                <b style="color: #34d399; font-size: 0.95rem;">Payback 5,3 ans &bull; TRI 14,8%</b>
                                <small style="color: #6ee7b7; display: block; font-size: 0.68rem;">VAN 20 ans : +275,8 M DZD</small>
                            </div>
                        </div>
                    </div>
                </div>
                                <div style="font-size: 1.25rem; font-weight: 900; color: #34d399; margin-bottom: 4px;">240 384 400,00 DZD</div>
                                <div style="font-size: 0.74rem; color: #cbd5e1; line-height: 1.4; margin-bottom: 8px;">
                                    Recalibrage ciblé 97 goulots (4 112,8 ml) + Bassin amont régulé 6 595 m³ + noues.
                                </div>
                                <div style="font-size: 0.72rem; color: #f8fafc; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 6px;">
                                    <div>✅ <b>Efficacité :</b> 100% résorption hydrodynamique</div>
                                    <div>📉 <b>Économie :</b> 90 580 100,00 DZD (-27,4%)</div>
                                    <div>🛡️ <b>Protection aval :</b> Débit pointe écrêté à 0,65 m³/s</div>
                                    <div>⭐ <b>Résilience :</b> 9,2 / 10</div>
                                </div>
                            </div>
                        </div>

                        <!-- KPIs Ratios Directeurs & Rentabilité -->
                        <div style="font-weight: 700; font-size: 0.88rem; color: #38bdf8; margin-bottom: 8px;">
                            <i class="fas fa-chart-pie me-1"></i> Ratios Directeurs &amp; Indicateurs Décisionnels (Aide à la Décision ONA / Wilaya)
                        </div>
                        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; font-size: 0.78rem;">
                            <div style="background: rgba(255,255,255,0.03); padding: 8px 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.08);">
                                <span style="color: #94a3b8; display: block; font-size: 0.7rem;">Coût par ml Rénové</span>
                                <b style="color: #38bdf8; font-size: 0.95rem;">${window.formaterCoutDZD(agents.analyse_variantes_financiere?.ratios_decisionnels?.cout_par_ml_renove_dzd || 47871)} / ml</b>
                                <small style="color: #64748b; display: block; font-size: 0.68rem;">Base 4 112.8 ml ciblés</small>
                            </div>
                            <div style="background: rgba(255,255,255,0.03); padding: 8px 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.08);">
                                <span style="color: #94a3b8; display: block; font-size: 0.7rem;">Coût par Habitant</span>
                                <b style="color: #38bdf8; font-size: 0.95rem;">${window.formaterCoutDZD(agents.analyse_variantes_financiere?.ratios_decisionnels?.cout_par_habitant_protege_dzd || 16026)} / hab</b>
                                <small style="color: #64748b; display: block; font-size: 0.68rem;">15 000 hab équivalents</small>
                            </div>
                            <div style="background: rgba(16,185,129,0.08); padding: 8px 10px; border-radius: 6px; border: 1px solid rgba(16,185,129,0.25);">
                                <span style="color: #34d399; display: block; font-size: 0.7rem; font-weight: 700;">Dommages Annuels Évités</span>
                                <b style="color: #34d399; font-size: 0.95rem;">45,0 M DZD / an</b>
                                <small style="color: #6ee7b7; display: block; font-size: 0.68rem;">Voirie, sous-sols, caves, RN4</small>
                            </div>
                            <div style="background: rgba(16,185,129,0.08); padding: 8px 10px; border-radius: 6px; border: 1px solid rgba(16,185,129,0.25);">
                                <span style="color: #34d399; display: block; font-size: 0.7rem; font-weight: 700;">Rentabilité Socio-Éco</span>
                                <b style="color: #34d399; font-size: 0.95rem;">Payback 5,3 ans &bull; TRI 14,8%</b>
                                <small style="color: #6ee7b7; display: block; font-size: 0.68rem;">VAN 20 ans : +275,8 M DZD</small>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- CONTENU DE L'ONGLET 6 : NOTE EXÉCUTIVE STRATÉGIQUE -->
                <div id="pane-agent-synth" class="agent-tab-pane" style="display: none;">
                    <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 16px; margin-bottom: 14px;">
                        <div style="background: rgba(192, 132, 252, 0.08); border-left: 4px solid #c084fc; border-radius: 6px; padding: 10px 14px; margin-bottom: 14px; font-size: 0.82rem; color: #e2e8f0; line-height: 1.5;">
                            <strong style="color: #c084fc; display: block; margin-bottom: 4px;"><i class="fas fa-user-tie me-1"></i> Mémoire Exécutif d'Aide à la Décision Ministérielle &amp; Direction (Agent 5) :</strong>
                            ${synth.note_technique || "Synthèse stratégique d'aide à la décision pour la Direction Générale (ONA, DRE, Wilaya)."}
                        </div>
                        <div style="font-weight: 700; font-size: 0.92rem; color: #c084fc; margin-bottom: 8px;">
                            <i class="fas fa-file-alt me-1"></i> Note d'Orientation Stratégique pour la Direction
                        </div>
                        <div style="font-size: 0.8rem; color: #94a3b8; margin-bottom: 14px;">
                            Périmètre : <b>${synth.perimetre || 'Réseau Complet'}</b> &bull; Événement : <b>${synth.scenario || 'Pluie Décennale'}</b>
                        </div>

                        <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 12px 14px; margin-bottom: 14px; font-size: 0.82rem; color: #cbd5e1; line-height: 1.55;">
                            ${synth.recommandation_cle || "Analyse globale satisfaisante."}
                        </div>

                        <!-- Bilan Hydraulique Décisionnel (Option 3) -->
                        <div style="background: rgba(14, 165, 233, 0.08); border: 1.5px solid rgba(56, 189, 248, 0.35); border-left: 5px solid #38bdf8; border-radius: 8px; padding: 12px 16px; margin-bottom: 14px; font-size: 0.82rem;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                                <span style="font-weight: 800; color: #38bdf8; text-transform: uppercase; font-size: 0.8rem; letter-spacing: 0.5px;">
                                    <i class="fas fa-balance-scale me-1"></i> Bilan Hydraulique Décisionnel du Bassin (Option 3)
                                </span>
                                <span style="background: rgba(56,189,248,0.2); color: #38bdf8; padding: 2px 8px; border-radius: 4px; font-weight: 700; font-size: 0.72rem;">
                                    Répartition des Débits
                                </span>
                            </div>
                            <div style="display: grid; gap: 4px; color: #cbd5e1; line-height: 1.5;">
                                <div><b>Bassin versant :</b> <span style="color: #f8fafc;">${meta.cluster_nom || ('Bassin ' + meta.cluster_id) || 'Réseau Principal'}</span></div>
                                <div>&bull; <b>Débit total généré par le bassin :</b> <span style="color: #38bdf8; font-weight: 800;">${(k.q_genere_m3s || ((k.peak_outflow_m3s || 0) + (k.q_derive_m3s || k.q_deleste_m3s || 0))).toFixed(3)} m³/s</span></div>
                                <div style="color: #34d399; font-weight: 700;">&bull; <b>Soulagement du collecteur principal :</b> ${(k.soulagement_reseau_pct !== undefined ? k.soulagement_reseau_pct : (k.taux_derive_pct || 0)).toFixed(1)}%</div>
                                <div>&bull; <b>Débit résiduel vers l'exutoire principal :</b> <span style="color: #f8fafc;">${(k.q_exutoire_m3s || k.peak_outflow_m3s || 0).toFixed(3)} m³/s</span> <span style="color: #94a3b8;">(${(k.taux_exutoire_pct !== undefined ? k.taux_exutoire_pct : 100.0).toFixed(1)}%)</span></div>
                                <div>&bull; <b>Débit capté par ${(k.nb_ouvrages_raccordes || 0)} ouvrages spéciaux mobilisés :</b> <span style="color: #22d3ee; font-weight: 700;">${(k.q_derive_m3s || k.q_deleste_m3s || 0).toFixed(3)} m³/s</span> <span style="color: #94a3b8;">(${(k.taux_derive_pct || 0).toFixed(1)}%)</span></div>
                            </div>
                        </div>

                        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; font-size: 0.78rem;">
                            <div style="background: rgba(255,255,255,0.02); padding: 8px 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.06);">
                                <span style="color: #94a3b8;">Débit de crête exutoire :</span>
                                <b style="color: #38bdf8; float: right;">${peakOutflow} m³/s</b>
                            </div>
                            <div style="background: rgba(255,255,255,0.02); padding: 8px 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.06);">
                                <span style="color: #94a3b8;">Volume total ruisselé :</span>
                                <b style="color: #f8fafc; float: right;">${(k.total_outflow_m3 || 0).toLocaleString()} m³</b>
                            </div>
                            <div style="background: rgba(255,255,255,0.02); padding: 8px 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.06);">
                                <span style="color: #94a3b8;">Enveloppe Travaux GC :</span>
                                <b style="color: #34d399; float: right;">${window.formaterCoutDZD(gc.cout_global_estime_dzd)}</b>
                            </div>
                            <div style="background: rgba(255,255,255,0.02); padding: 8px 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.06);">
                                <span style="color: #94a3b8;">Rétention Alternative Cible :</span>
                                <b style="color: #a855f7; float: right;">${lid.volume_tampon_requis_m3 || 0} m³</b>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- CONTENU DE L'ONGLET 7 : SENSIBILITÉ DU BUFFER (35, 45, 60M) -->
                <div id="pane-agent-buffer" class="agent-tab-pane" style="display: none;">
                    <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 16px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <div style="font-weight: 700; font-size: 0.88rem; color: #38bdf8;">
                                <i class="fas fa-chart-line me-1"></i> Évaluation de la Représentativité de la Surface Drainée
                            </div>
                            <span style="font-size: 0.72rem; color: #34d399; background: rgba(16, 185, 129, 0.15); padding: 2px 8px; border-radius: 4px; font-weight: 700;">
                                ⭐ Choix Optimal : 45 m
                            </span>
                        </div>
                        <p style="font-size: 0.78rem; color: #94a3b8; margin: 0 0 14px 0; line-height: 1.45;">
                            ${bufferSens.conclusion_technique || "Le rayon de 45 mètres constitue le coude d'inflexion optimal : il capture l'intégralité des toitures et cours d'îlots urbains sans surévaluer les surfaces naturelles."}
                        </p>

                        ${(bufferSens.curve && bufferSens.curve.length > 0) ? `
                            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 14px;">
                                ${bufferSens.curve.map(c => {
                                    const isRec = c.is_recommended || (Math.round(c.buffer_m) === 45);
                                    const isSel = (Math.round(c.buffer_m) === Math.round(window._activeBufferM || meta.buffer_m || bufferSens.active_buffer_m || 35));
                                    const dispArea = (isSel && meta.total_area_ha) ? meta.total_area_ha : c.surface_ha;
                                    return `
                                        <div style="background: ${isSel ? 'rgba(16, 185, 129, 0.12)' : (isRec ? 'rgba(56, 189, 248, 0.08)' : 'rgba(255,255,255,0.03)')}; border: 1.5px solid ${isSel ? '#10b981' : (isRec ? '#0284c7' : 'rgba(255,255,255,0.1)')}; border-radius: 8px; padding: 10px; text-align: center;">
                                            <div style="font-weight: 800; font-size: 0.84rem; color: ${isSel ? '#34d399' : (isRec ? '#38bdf8' : '#e2e8f0')};">
                                                Buffer ${Math.round(c.buffer_m)} m ${isSel ? '✅' : ''}
                                            </div>
                                            <div style="font-size: 1.1rem; font-weight: 800; color: #f8fafc; margin: 4px 0;">
                                                ${dispArea} ha
                                            </div>
                                            <div style="font-size: 0.72rem; color: #94a3b8; margin-bottom: 8px;">
                                                Débit : <b>${c.peak_flow_m3s} m³/s</b>
                                            </div>
                                            <button onclick="validerChoixBuffer(${c.buffer_m})" style="width: 100%; padding: 5px; font-size: 0.72rem; font-weight: 700; border-radius: 4px; border: none; cursor: pointer; background: ${isSel ? '#10b981' : (isRec ? '#0284c7' : 'rgba(255,255,255,0.1)')}; color: white;">
                                                ${isSel ? '✅ Actif' : (isRec ? '⭐ Valider 45m' : `Valider ${Math.round(c.buffer_m)}m`)}
                                            </button>
                                        </div>
                                    `;
                                }).join('')}
                            </div>
                        ` : ''}
                    </div>
                </div>
            `;
    return html;
};
