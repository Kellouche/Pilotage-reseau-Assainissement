/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Analyse de sensibilité du buffer, modale multi-agents et restitution décisionnelle
 * ================================================================================
 */

// ==========================================
        // VALIDATION DU BUFFER VORONOÏ (35, 45, 60M)
        // ==========================================
        window.validerChoixBuffer = function(bufferM) {
            const token = localStorage.getItem('swmm_access_token');
            const headers = { 'Content-Type': 'application/json' };
            if (token) headers['Authorization'] = `Bearer ${token}`;

            fetch('/api/v1/simulations/validate-buffer', {
                method: 'POST',
                headers: headers,
                credentials: 'include',
                body: JSON.stringify({ buffer_m: parseFloat(bufferM) })
            })
            .then(r => r.json())
            .then(res => {
                window._activeBufferM = parseFloat(bufferM);
                if (window._dernierResultatSimulation && window._dernierResultatSimulation.buffer_sensitivity) {
                    afficherAnalyseSensibiliteBuffer(window._dernierResultatSimulation.buffer_sensitivity, window._activeBufferM);
                }
                const bEl = document.getElementById('buffer-badge-recommande');
                if (bEl) {
                    bEl.innerHTML = `✅ Choix Actif Validé : ${bufferM} m`;
                    bEl.style.background = 'rgba(16, 185, 129, 0.25)';
                    bEl.style.color = '#34d399';
                }
                alert(`✅ Choix validé avec succès !\nLe buffer de ${bufferM} mètres est maintenant enregistré comme configuration de référence pour ce projet.`);
            })
            .catch(e => {
                console.error("Erreur validation buffer:", e);
                window._activeBufferM = parseFloat(bufferM);
                if (window._dernierResultatSimulation && window._dernierResultatSimulation.buffer_sensitivity) {
                    afficherAnalyseSensibiliteBuffer(window._dernierResultatSimulation.buffer_sensitivity, window._activeBufferM);
                }
            });
        };

        window.afficherAnalyseSensibiliteBuffer = function(bufferSens, validatedVal) {
            const grid = document.getElementById('sim-buffer-tiles-grid');
            if (!grid) return;
            if (!bufferSens || !bufferSens.curve || bufferSens.curve.length === 0) {
                grid.innerHTML = '<div style="grid-column: 1/-1; color: #94a3b8; font-size: 0.8rem; text-align: center; padding: 10px;">Calcul de sensibilité automatique actif lors de la simulation.</div>';
                return;
            }

            const currentVal = validatedVal || bufferSens.active_buffer_m || window._activeBufferM || 35.0;
            const curve = bufferSens.curve;

            let html = '';
            curve.forEach(c => {
                const isRec = c.is_recommended || (Math.round(c.buffer_m) === 45);
                const isSelected = (Math.round(c.buffer_m) === Math.round(currentVal));
                const borderColor = isSelected ? '#10b981' : (isRec ? 'rgba(56, 189, 248, 0.5)' : 'rgba(255,255,255,0.1)');
                const bg = isSelected ? 'rgba(16, 185, 129, 0.12)' : (isRec ? 'rgba(56, 189, 248, 0.08)' : 'rgba(255,255,255,0.03)');

                html += `
                    <div style="background: ${bg}; border: 1.5px solid ${borderColor}; border-radius: 10px; padding: 10px 12px; display: flex; flex-direction: column; justify-content: space-between; position: relative; transition: all 0.2s;">
                        ${isRec ? `<span style="position: absolute; top: -8px; right: 8px; font-size: 0.65rem; background: #0284c7; color: white; padding: 1px 7px; border-radius: 4px; font-weight: 700; box-shadow: 0 2px 6px rgba(0,0,0,0.3);">POINT INFLEXION</span>` : ''}
                        <div>
                            <div style="font-size: 0.84rem; font-weight: 800; color: ${isSelected ? '#34d399' : (isRec ? '#38bdf8' : '#e2e8f0')}; margin-bottom: 2px;">
                                Buffer ${Math.round(c.buffer_m)} m ${isSelected ? '✅' : ''}
                            </div>
                            <div style="font-size: 0.72rem; color: #94a3b8; margin-bottom: 6px;">
                                ${c.buffer_m === 35 ? 'Voirie stricte' : (c.buffer_m === 45 ? 'Îlots comblés (Optimal)' : 'Périphérie élargie')}
                            </div>
                            <div style="font-size: 1.05rem; font-weight: 800; color: #f8fafc; margin-bottom: 2px;">
                                ${c.surface_ha} ha
                                ${c.gain_pct > 0 ? `<small style="font-size: 0.72rem; color: #34d399; font-weight: 700; margin-left: 4px;">+${c.gain_pct}%</small>` : ''}
                            </div>
                            <div style="font-size: 0.74rem; color: #cbd5e1;">
                                Pointe : <b style="color: ${isRec ? '#38bdf8' : '#f8fafc'};">${c.peak_flow_m3s} m³/s</b>
                            </div>
                        </div>
                        <button onclick="validerChoixBuffer(${c.buffer_m})" style="width: 100%; margin-top: 10px; padding: 7px; font-size: 0.75rem; font-weight: 700; border-radius: 6px; cursor: pointer; border: none; background: ${isSelected ? '#10b981' : (isRec ? 'linear-gradient(135deg, #0284c7, #0369a1)' : 'rgba(255,255,255,0.08)')}; color: white; display: flex; align-items: center; justify-content: center; gap: 4px;">
                            ${isSelected ? '<i class="fas fa-check"></i> Choix Actif' : (isRec ? '⭐ Valider 45m' : `Valider ${Math.round(c.buffer_m)}m`)}
                        </button>
                    </div>
                `;
            });

            grid.innerHTML = html;

            // Ajustement dynamique de la barre relative
            if (curve.length >= 3) {
                const s35 = curve[0].surface_ha || 1;
                const s45 = curve[1].surface_ha || 1;
                const s60 = curve[2].surface_ha || 1;
                const b35 = document.getElementById('bar-buffer-35');
                const b45 = document.getElementById('bar-buffer-45');
                const b60 = document.getElementById('bar-buffer-60');
                if (b35 && b45 && b60) {
                    b35.style.width = Math.min(Math.round((s35 / s60) * 100), 55) + '%';
                    b45.style.width = Math.max(Math.round(((s45 - s35) / s60) * 100), 20) + '%';
                    b60.style.width = Math.max(Math.round(((s60 - s45) / s60) * 100), 15) + '%';
                }
            }
        };

        // ==========================================
        // GESTION DES ONGLETS DU COCKPIT MULTI-AGENTS
        // ==========================================
        window.changerOngletAgent = function(ongletId) {
            document.querySelectorAll('.agent-tab-pane').forEach(el => el.style.display = 'none');
            document.querySelectorAll('.agent-tab-btn').forEach(btn => {
                btn.style.background = 'rgba(255,255,255,0.05)';
                btn.style.borderColor = 'rgba(255,255,255,0.12)';
                btn.style.color = '#94a3b8';
            });
            const pane = document.getElementById('pane-' + ongletId);
            if (pane) pane.style.display = 'block';
            const activeBtn = document.getElementById('btn-tab-' + ongletId);
            if (activeBtn) {
                activeBtn.style.background = 'rgba(168, 85, 247, 0.2)';
                activeBtn.style.borderColor = '#a855f7';
                activeBtn.style.color = '#f8fafc';
            }
        };

        // ==========================================
        // INTERPRÉTATION EXPERTE & MULTI-AGENTS IA
        // ==========================================
        window.genererRapportInterpretation = function(simData) {
            const container = document.getElementById('interpretation-modal-body');
            if (!container || !simData) return;

            const k = simData.kpis || {};
            const cRes = simData.conduit_results || {};
            const nRes = simData.node_results || {};
            const meta = simData.meta || {};
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

            const contError = Math.abs(k.routing_continuity_error_pct || 0);
            const surchargedNodes = k.surcharged_nodes_count || 0;
            const floodedNodes = k.flooded_nodes_count || 0;
            const peakOutflow = (k.peak_outflow_m3s || 0).toFixed(3);

            let nbConduites = Object.keys(cRes).length;
            let nbNormal = 0;
            let nbVigilance = 0;
            let nbSurcharge = 0;
            for (const [cid, c] of Object.entries(cRes)) {
                const ratio = c.flow_ratio || 0;
                if (ratio > 1.0) nbSurcharge++;
                else if (ratio >= 0.75) nbVigilance++;
                else nbNormal++;
            }

            const verdict = synth.verdict || (floodedNodes > 0 ? "VULNÉRABILITÉ ÉLEVÉE — DÉBORDEMENTS DÉTECTÉS" : (surchargedNodes > 0 ? "MISE EN CHARGE HYDRAULIQUE" : "RÉSEAU CONFORME & ÉCOULEMENT FLUIDE"));
            const verdictCouleur = synth.couleur || (floodedNodes > 0 ? "#ef4444" : (surchargedNodes > 0 ? "#f59e0b" : "#10b981"));


            let html = window._construireHtmlCorpsInterpretation(simData, k, cRes, nRes, meta, agents, bufferSens, diag, gc, lid, risk, finance, synth, variantes, ratios, contError, surchargedNodes, floodedNodes, peakOutflow, nbConduites, nbNormal, nbVigilance, nbSurcharge, verdict, verdictCouleur);
            container.innerHTML = html;
        };

        window.addEventListener('click', function(e) {
            const btnActions = document.getElementById('btn-actions-menu');
            const dActions = document.getElementById('actions-dropdown');
            if (dActions && btnActions && !btnActions.contains(e.target) && !dActions.contains(e.target)) {
                dActions.style.display = 'none';
            }

            const btnProfile = document.getElementById('btn-user-profile-menu');
            const dProfile = document.getElementById('user-profile-dropdown');
            if (dProfile && btnProfile && !btnProfile.contains(e.target) && !dProfile.contains(e.target)) {
                dProfile.style.display = 'none';
            }

            const btnRes = document.getElementById('btn-resources-menu');
            const dRes = document.getElementById('resources-dropdown');
            if (dRes && btnRes && !btnRes.contains(e.target) && !dRes.contains(e.target)) {
                dRes.style.display = 'none';
            }
        });
