/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-27
 * Date de modification : 2026-11-27
 * Objet : Menu deroulant hierarchique bassin dans la topbar (extrait de static/js/app/bassins_selection.js)
 * ================================================================================
 */

        // ==========================================
        // GESTION DU MENU DÉROULANT HIÉRARCHIQUE BASSIN (TOPBAR)
        // ==========================================

        window.basculerMenuBassin = function(e) {
            if (e) {
                if (e.target && e.target.closest('#topbar-bassin-reset-btn')) return;
                e.stopPropagation();
            }
            const d = document.getElementById('topbar-bassin-dropdown');
            if (!d) return;
            const isVisible = d.style.display === 'block';
            if (typeof window.fermerTousLesMenusTopbar === 'function') {
                window.fermerTousLesMenusTopbar(isVisible ? null : 'bassin');
            }
            if (!isVisible) {
                if (typeof window.actualiserDropdownBassin === 'function') {
                    window.actualiserDropdownBassin();
                }
                d.style.display = 'block';
                const chev = document.getElementById('topbar-bassin-chevron');
                if (chev) chev.style.transform = 'rotate(180deg)';
            } else {
                window.fermerMenuBassin();
            }
        };

        window.fermerMenuBassin = function() {
            const d = document.getElementById('topbar-bassin-dropdown');
            if (d) d.style.display = 'none';
            const chev = document.getElementById('topbar-bassin-chevron');
            if (chev) chev.style.transform = 'rotate(0deg)';
        };

        window.actualiserDropdownBassin = function() {
            const dropdown = document.getElementById('topbar-bassin-dropdown');
            if (!dropdown) return;

            const _esc = function(s) {
                return (typeof window.dwfEchapperHtml === 'function')
                    ? window.dwfEchapperHtml(s)
                    : String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            };

            const cidStr = (window._selectedClusterId !== null && window._selectedClusterId !== undefined && window._selectedClusterId !== '')
                ? String(window._selectedClusterId) : null;
            const totalBassins = (window._clustersData && window._clustersData.clusters_crees)
                || (window._bassinNoms ? Object.keys(window._bassinNoms).length : '--') || '--';

            // 1. Vue globale (aucun bassin sélectionné)
            if (!cidStr) {
                const projNom = (window._rawNetworkData && (window._rawNetworkData.project_name || window._rawNetworkData.project_id)) || 'Réseau urbain';
                dropdown.innerHTML = `
                    <div style="padding: 12px 16px; border-bottom: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.03);">
                        <div style="font-weight: 800; font-size: 13px; color: #38bdf8; display: flex; align-items: center; gap: 8px;">
                            <i class="fas fa-network-wired"></i> Vue globale du réseau
                        </div>
                        <div style="font-size: 11px; color: #94a3b8; margin-top: 3px;">
                            ${_esc(projNom)} · <b>${totalBassins} bassins versants</b>
                        </div>
                    </div>
                    <div style="padding: 12px 16px; font-size: 12px; color: #cbd5e1; line-height: 1.5;">
                        <p style="margin: 0 0 12px 0; color: #94a3b8; font-size: 11px;">
                            Sélectionnez un bassin versant sur la carte pour inspecter ses résultats détaillés, ou configurez et lancez une simulation.
                        </p>
                        <button type="button" onclick="fermerMenuBassin(); if (typeof ouvrirModalSimulation === 'function') ouvrirModalSimulation(true);" style="width: 100%; padding: 8px 12px; background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.4); color: #38bdf8; border-radius: 6px; font-size: 11px; font-weight: 700; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 7px;">
                            <i class="fas fa-play"></i> Configurer et lancer une simulation
                        </button>
                    </div>
                `;
                return;
            }

            // 1bis. Vue Ouvrage/Exutoire isolé sans réseau collecteur amont (non simulable)
            if (cidStr && window._bassinsIsoleIds && window._bassinsIsoleIds.has(cidStr)) {
                const nomIsole = (window._bassinNoms && window._bassinNoms[cidStr]) || `Ouvrage ${cidStr}`;
                const bpIsole = (window._bassinProperties && window._bassinProperties[cidStr]) || {};
                const typOuv = bpIsole.exutoire_type ? String(bpIsole.exutoire_type).toUpperCase() : 'EXUTOIRE';
                dropdown.innerHTML = `
                    <div style="padding: 12px 14px; border-bottom: 1px solid rgba(255,255,255,0.1); background: rgba(245, 158, 11, 0.05);">
                        <div style="font-weight: 800; font-size: 13px; color: #fbbf24; display: flex; align-items: center; gap: 7px;">
                            <i class="fas fa-map-pin"></i> ${_esc(nomIsole)}
                        </div>
                        <div style="font-size: 11px; color: #94a3b8; margin-top: 3px;">
                            Ouvrage ponctuel isolé (${typOuv}) · Aucun réseau collecteur amont
                        </div>
                    </div>
                    <div style="padding: 12px 14px;">
                        <div style="margin: 4px 0 14px 0; padding: 10px 12px; background: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 6px; font-size: 11px; color: #fbbf24; line-height: 1.45;">
                            <div style="font-weight: 800; display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
                                <i class="fas fa-ban"></i> Non simulable sous SWMM 5.2
                            </div>
                            Cet élément est un exutoire ou regard ponctuel isolé ne disposant d'aucune canalisation collectrice connectée. Les calculs hydrauliques 1D (Saint-Venant) ne peuvent pas lui être appliqués.
                        </div>
                        <div style="display: flex; gap: 6px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.08);">
                            <button type="button" disabled title="Simulation impossible sur un ouvrage isolé" style="flex: 1.2; padding: 6px 10px; background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.1); color: #64748b; border-radius: 6px; font-size: 11px; font-weight: 700; cursor: not-allowed; display: flex; align-items: center; justify-content: center; gap: 5px;">
                                <i class="fas fa-ban"></i> Non simulable
                            </button>
                            <button type="button" onclick="fermerMenuBassin(); reinitialiserSelectionBassin();" title="Revenir à la vue globale du réseau" style="flex: 0.8; padding: 6px 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.15); color: #cbd5e1; border-radius: 6px; font-size: 11px; font-weight: 600; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 5px;">
                                <i class="fas fa-globe"></i> Réseau
                            </button>
                        </div>
                    </div>
                `;
                return;
            }

            // 2. Recherche de la simulation associée à ce bassin
            let simActive = null;
            const lastSim = window._dernierResultatSimulation;
            if (lastSim && lastSim.meta && typeof _simCorrespondAuBassin === 'function' && _simCorrespondAuBassin(lastSim, cidStr)) {
                simActive = lastSim;
            }
            if (!simActive && window._simulationsCache) {
                for (const _k of Object.keys(window._simulationsCache)) {
                    const _cand = window._simulationsCache[_k];
                    if (_cand && _cand.status !== 'failed' && typeof _simCorrespondAuBassin === 'function' && _simCorrespondAuBassin(_cand, cidStr)) {
                        simActive = _cand;
                        break;
                    }
                }
            }

            const m = (simActive && simActive.meta) ? simActive.meta : {};
            const kp = (simActive && simActive.kpis) ? simActive.kpis : (simActive || {});
            const nom = (typeof _nomMetierBassin === 'function') ? _nomMetierBassin(cidStr, m) : `Bassin ${cidStr}`;

            // Propriétés du bassin
            const bp = (window._bassinProperties && window._bassinProperties[cidStr]) || {};
            const nbRegards = m.junctions_count || bp.nb_regards || bp.nodes_count || '--';
            const nbTroncons = m.conduits_count || bp.nb_canalisations || bp.pipes_count || '--';
            const surfaceHa = m.total_area_ha ? Number(m.total_area_ha).toFixed(1) : (bp.surface_ha ? Number(bp.surface_ha).toFixed(1) : '--');

            // --- ÉLÉMENT 1 : Simulation (Scénario / Période de retour) ---
            let simBlock = '';
            if (simActive) {
                const tRetour = kp.pluvio_periode_retour || m.pluvio_periode_retour || 'T = 2 ans (Biennale)';
                const scenNom = kp.pluvio_scenario_nom || m.pluvio_scenario_nom || m.scenario || 'Pluie de projet';
                const duree = m.duree_heures || kp.duree_heures || 2;

                const etatMeta = m.etat_reseau || (simActive.parameters && simActive.parameters.etat_reseau) || null;
                let etatLineHtml = '';
                const estDegrade = etatMeta && !etatMeta.est_nominal && (
                    (etatMeta.colmatage_pct && etatMeta.colmatage_pct > 0)
                    || (etatMeta.facteur_vieillissement && etatMeta.facteur_vieillissement > 1.0)
                    || etatMeta.appliquer_depots_sig
                );
                if (estDegrade) {
                    const ep = [];
                    ep.push(`${etatMeta.colmatage_pct || 0}% dépôt${etatMeta.cible_colmatage === 'faibles_pentes' ? ' (<' + (etatMeta.seuil_pente_pct || 0.5) + '%)' : ''}`);
                    if (etatMeta.facteur_vieillissement > 1.0) ep.push(`n ×${Number(etatMeta.facteur_vieillissement).toFixed(2)}`);
                    if (etatMeta.appliquer_depots_sig) ep.push(`+SIG`);
                    const sevCol = (etatMeta.colmatage_pct >= 20 || etatMeta.facteur_vieillissement >= 1.4) ? '#fca5a5' : '#fbbf24';
                    const nomE = etatMeta.scenario_nom && etatMeta.scenario_nom !== 'nominal' ? etatMeta.scenario_nom : 'personnalisé';
                    etatLineHtml = `
                        <div style="font-size: 11px; color: ${sevCol}; margin-top: 4px; padding-left: 18px; font-weight: 700; display: flex; align-items: center; gap: 5px;">
                            <i class="fas fa-water" style="font-size: 10px;"></i>
                            <span>État ${_esc(nomE)} : ${_esc(ep.join(' • '))}</span>
                        </div>`;
                } else {
                    etatLineHtml = `
                        <div style="font-size: 11px; color: #34d399; margin-top: 4px; padding-left: 18px; display: flex; align-items: center; gap: 5px;">
                            <i class="fas fa-check-circle" style="font-size: 10px;"></i>
                            <span>État : Nominal (Curé)</span>
                        </div>`;
                }

                simBlock = `
                    <div style="margin-bottom: 8px;">
                        <div style="font-size: 12px; font-weight: 700; color: #38bdf8; display: flex; align-items: center; gap: 7px;">
                            <i class="fas fa-cloud-showers-heavy" style="font-size: 11px;"></i> Simulation : ${_esc(tRetour)}
                        </div>
                        <div style="font-size: 11px; color: #94a3b8; margin-top: 2px; padding-left: 18px;">
                            ${_esc(scenNom)} (${duree} h)
                        </div>
                        ${etatLineHtml}
                    </div>
                `;
            } else {
                simBlock = `
                    <div style="margin-bottom: 8px;">
                        <div style="font-size: 12px; font-weight: 600; color: #94a3b8; display: flex; align-items: center; gap: 7px;">
                            <i class="fas fa-info-circle" style="font-size: 11px;"></i> Aucune simulation active
                        </div>
                        <div style="font-size: 11px; color: #64748b; margin-top: 2px; padding-left: 18px;">
                            Ce bassin n'a pas encore été calculé
                        </div>
                    </div>
                `;
            }

            // --- ÉLÉMENT 2 : Modèle sain / Diagnostic Garde-fou & DWF ---
            let diagBlock = '';
            const verdict = window._fiabiliteDepuisSimulation ? window._fiabiliteDepuisSimulation(simActive) : 'SAIN';
            const metaFiab = _FIABILITE_META[verdict] || _FIABILITE_META['SAIN'];

            // Analyse DWF
            let dwfTxt = 'DWF : Aucun injecté (0 L/s)';
            let dwfColor = '#94a3b8';
            let dwfSub = '';
            const provDwf = (simActive && simActive.provenance && simActive.provenance.apports_dwf)
                || (simActive && simActive.kpis && simActive.kpis.provenance ? simActive.kpis.provenance.apports_dwf : null)
                || (m && m.apports_dwf ? { injectes: m.apports_dwf, ignores: m.apports_dwf_ignores || [] } : null);

            if (provDwf) {
                const nInj = Array.isArray(provDwf.injectes) ? provDwf.injectes.length : 0;
                const nIgn = Array.isArray(provDwf.ignores) ? provDwf.ignores.length : 0;
                let qTot = 0;
                if (Array.isArray(provDwf.injectes)) {
                    provDwf.injectes.forEach(a => {
                        const q = parseFloat(a.debit_moyen_m3s || 0);
                        if (isFinite(q)) qTot += q;
                    });
                }
                const qLs = (qTot * 1000).toFixed(1);
                if (nInj > 0) {
                    dwfTxt = `DWF : <b>${nInj} injecté${nInj > 1 ? 's' : ''} (${qLs} L/s)</b>`;
                    dwfColor = '#06b6d4';
                    if (nIgn > 0) dwfSub = `<span style="color:#fbbf24; font-size:10px; display:block; margin-top:2px;">⚠️ ${nIgn} exclu(s) hors bassin</span>`;
                } else if (nIgn > 0) {
                    dwfTxt = `DWF : Aucun injecté`;
                    dwfColor = '#fbbf24';
                    dwfSub = `<span style="color:#fbbf24; font-size:10px; display:block; margin-top:2px;">⚠️ ${nIgn} exclu(s) (regard hors bassin)</span>`;
                }
            } else if (window._dwfSimulationInfo && window._dwfSimulationInfo.actifs > 0) {
                dwfTxt = `DWF : ${window._dwfSimulationInfo.actifs} configuré(s)`;
                dwfColor = '#6ee7b7';
            }

            diagBlock = `
                <div style="margin-bottom: 10px;">
                    <div style="font-size: 12px; font-weight: 700; color: ${metaFiab.color}; display: flex; align-items: center; gap: 7px;">
                        <span>${metaFiab.icon}</span> <span>${metaFiab.label}</span>
                    </div>
                    <!-- Sous-élément DWF indenté -->
                    <div style="margin-top: 5px; margin-left: 20px; padding-left: 8px; border-left: 2px solid rgba(6, 182, 212, 0.4);">
                        <div style="font-size: 11px; color: ${dwfColor}; display: flex; align-items: center; justify-content: space-between;">
                            <span><i class="fas fa-faucet-drip me-1" style="color: #06b6d4;"></i> ${dwfTxt}</span>
                            <button type="button" onclick="fermerMenuBassin(); ouvrirModalApportsDwf();" style="background: transparent; border: none; color: #38bdf8; font-size: 10px; text-decoration: underline; cursor: pointer; padding: 0 4px;">
                                Gérer
                            </button>
                        </div>
                        ${dwfSub}
                    </div>
                </div>
            `;

            // Résolution optimale de l'identifiant stable pour l'historique
            let idHistorique = cidStr;
            if (window._bassinProperties && window._bassinProperties[cidStr]) {
                const bp = window._bassinProperties[cidStr];
                idHistorique = bp.exutoire_id || bp.bassin_ref || bp.cluster_id || cidStr;
            }

            dropdown.innerHTML = `
                <div style="padding: 12px 14px; border-bottom: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.03);">
                    <div style="font-weight: 800; font-size: 13px; color: #34d399; display: flex; align-items: center; gap: 7px;">
                        <i class="fas fa-water"></i> ${_esc(nom)}
                    </div>
                    <div style="font-size: 11px; color: #94a3b8; margin-top: 3px;">
                        ${nbRegards} regards · ${nbTroncons} canalisations · ${surfaceHa} ha
                    </div>
                </div>

                <div style="padding: 12px 14px;">
                    <div style="font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; color: #64748b; margin-bottom: 8px;">
                        État d'analyse du bassin
                    </div>
                    ${simBlock}
                    ${diagBlock}

                    <div style="display: flex; gap: 6px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.08); margin-top: 8px;">
                        <button type="button" onclick="reSimulerBassin('${_esc(cidStr)}');" title="Configurer et relancer une simulation pour ce bassin" style="flex: 1.2; padding: 6px 10px; background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.35); color: #38bdf8; border-radius: 6px; font-size: 11px; font-weight: 700; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 5px;">
                            <i class="fas fa-play"></i> ${simActive ? 'Re-simuler' : 'Simuler'}
                        </button>
                        <button type="button" onclick="fermerMenuBassin(); if (typeof ouvrirModalSimulationsBassin === 'function') ouvrirModalSimulationsBassin('${_esc(idHistorique)}', false);" title="Consulter l'historique des calculs enregistrés pour ce bassin" style="flex: 1; padding: 6px 8px; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.15); color: #94a3b8; border-radius: 6px; font-size: 11px; font-weight: 600; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 5px;">
                            <i class="fas fa-history"></i> Historique
                        </button>
                        <button type="button" onclick="fermerMenuBassin(); reinitialiserSelectionBassin();" title="Revenir à la vue globale du réseau" style="flex: 0.8; padding: 6px 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.15); color: #cbd5e1; border-radius: 6px; font-size: 11px; font-weight: 600; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 5px;">
                            <i class="fas fa-globe"></i> Réseau
                        </button>
                    </div>
                </div>
            `;
        };

        /**
         * Re-simuler un bassin : ouvre directement la modale de configuration et
         * de lancement de simulation en pré-sélectionnant ce bassin, SANS détour
         * par l'historique des simulations.
         */
        window.reSimulerBassin = function(clusterId) {
            const cidStr = String(clusterId || '').trim();
            if (typeof window.fermerMenuBassin === 'function') window.fermerMenuBassin();
            if (cidStr && window._bassinsIsoleIds && window._bassinsIsoleIds.has(cidStr)) {
                if (typeof window.showToast === 'function') {
                    window.showToast("Cet ouvrage est un élément isolé sans réseau collecteur amont : simulation SWMM impossible.", "warning");
                }
                return;
            }
            if (cidStr) {
                const bSel = document.getElementById('bassin-select');
                if (bSel) bSel.value = cidStr;
                const simSel = document.getElementById('sim-select-bassin');
                if (simSel) {
                    simSel.value = cidStr;
                    try { simSel.dispatchEvent(new Event('change')); } catch (_) {}
                }
                try { window._selectedClusterId = cidStr; } catch (_) {}
            }
            if (typeof window.ouvrirModalSimulation === 'function') {
                window.ouvrirModalSimulation(true);
            }
        };

        // Fermeture automatique au clic extérieur
        document.addEventListener('click', (e) => {
            const d = document.getElementById('topbar-bassin-dropdown');
            const pill = document.getElementById('topbar-bassin-pill');
            if (d && d.style.display === 'block') {
                if (!d.contains(e.target) && (!pill || !pill.contains(e.target))) {
                    window.fermerMenuBassin();
                }
            }
        });
