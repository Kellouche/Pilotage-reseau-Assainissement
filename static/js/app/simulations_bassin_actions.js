/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Objet : Modale historique bassins - actions executer/modifier/supprimer
 *        (extrait verbatim de simulations_bassin.js, regle 600 lignes)
 * ================================================================================
 */

// Actions sur les simulations enregistrees : reexecution a l'identique,
// modification des parametres et suppression. Etat et helpers partages
// via window._simBassinInt / window._historiqueBassin.
(function () {
    'use strict';

    const {
        _SCENARIO_LABELS, _FIAB, _esc, _scenarioLabel, _fiabiliteDe,
        _paramsDe, _resoudreBassinPourSimulation, _preselectionnerBassinPourModal,
        _trouverOptionBassin, _rendreListeSimulations
    } = window._simBassinInt;


    function _trouverSimulation(simId) {
        return (window._historiqueBassin.sims || []).find(s => String(s.id) === String(simId));
    }

    /**
     * Affiche les résultats sauvegardés de la simulation (result.json
     * persisté) : instantané, sans recalcul SWMM et sans créer de
     * doublon dans l'historique.
     */
    window.executerSimulationHistorique = function (simId) {
        const sim = _trouverSimulation(simId);
        if (!sim) return;
        let cidStr = window._historiqueBassin ? window._historiqueBassin.clusterId : '';
        if (!cidStr && sim) {
            const sk = sim.summary_kpis || {};
            cidStr = sim.exutoire_noeud || sim.bassin_ref || sk.cluster_id || '';
        }
        const corps = document.getElementById('sim-hist-corps');

        if (corps) {
            corps.innerHTML = `<div style="text-align:center;color:#94a3b8;padding:40px;">
                <i class="fas fa-circle-notch fa-spin fa-2x mb-3" style="color:#38bdf8;"></i>
                <p><b>Chargement des résultats sauvegardés…</b><br><small>Affichage instantané — aucun recalcul</small></p>
            </div>`;
        }

        const token = localStorage.getItem('swmm_access_token');
        const headers = {};
        if (token) headers['Authorization'] = `Bearer ${token}`;

        fetch(`/api/v1/simulations/${encodeURIComponent(simId)}/resultat`, {
            headers, credentials: 'include',
        })
            .then(r => {
                if (r.status === 404) {
                    throw new Error('Résultat introuvable : cette simulation a peut-être été supprimée ou ses données ne sont plus disponibles.');
                }
                if (r.status === 401 || r.status === 403) {
                    throw new Error('Session expirée : reconnectez-vous pour afficher les résultats.');
                }
                return r.json().then(d => ({ ok: r.ok, d }));
            })
            .then(({ ok, d }) => {
                if (!ok || !d || d.status !== 'success') {
                    const msg = (d && (d.detail || d.message)) || 'Résultat indisponible';
                    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
                }
                // Appliquer le résultat comme un run standard
                if (!window._simulationsCache) window._simulationsCache = {};
                const _cid = (d.meta && (d.meta.cluster_id || d.meta.exutoire_noeud || d.meta.bassin_ref)) || cidStr;
                window._simulationsCache[String(_cid)] = d;
                if (d.meta && d.meta.bassin_nom) window._simulationsCache[String(d.meta.bassin_nom)] = d;
                if (d.meta && d.meta.cluster_nom) window._simulationsCache[String(d.meta.cluster_nom)] = d;
                window._dernierResultatSimulation = d;
                if (window._fiabiliteParBassin) {
                    window._fiabiliteParBassin[String(_cid)] = d;
                    if (typeof window._decorerOptionsFiabilite === 'function') window._decorerOptionsFiabilite();
                }

                // Synchroniser le sélecteur et le focus sur le bassin de la simulation
                const targetCid = _cid;
                const optionValue = (typeof window._optionBassinPourMetaSim === 'function' ? window._optionBassinPourMetaSim(d.meta) : null)
                    || (typeof _trouverOptionBassin === 'function' ? _trouverOptionBassin(targetCid) : null)
                    || targetCid;

                if (optionValue) {
                    const bSel = document.getElementById('bassin-select');
                    if (bSel) bSel.value = optionValue;
                    try { if (typeof _selectedClusterId !== 'undefined') _selectedClusterId = optionValue; } catch (_) {}
                    window._selectedClusterId = optionValue;
                    if (typeof highlightCluster === 'function') {
                        highlightCluster(optionValue, window._activeClusterLayer || (typeof couches !== 'undefined' ? couches.bassins : null));
                    }
                    if (typeof zoomerSurBassin === 'function') {
                        zoomerSurBassin(optionValue, window._activeClusterLayer || (typeof couches !== 'undefined' ? couches.bassins : null));
                    }
                }

                if (typeof afficherResultatsSimulation === 'function') afficherResultatsSimulation(d, true);
                if (typeof window.actualiserLegendeDwf === 'function') {
                    window.actualiserLegendeDwf(d);
                }
                if (typeof window.mettreAJourIndicateurBassin === 'function') {
                    window.mettreAJourIndicateurBassin(optionValue || targetCid, d);
                }
                window.fermerModalSimulationsBassin();
            })
            .catch(err => {
                if (corps) {
                    corps.innerHTML = `<div style="text-align:center;color:#f87171;padding:30px;">
                        <i class="fas fa-exclamation-triangle fa-2x mb-3"></i>
                        <p>Impossible d'afficher les résultats : ${_esc(err.message)}</p>
                        <button onclick="_rendreListeSimulations()" style="margin-top:10px;padding:6px 14px;background:rgba(56,189,248,0.15);border:1px solid rgba(56,189,248,0.4);color:#38bdf8;border-radius:8px;cursor:pointer;">Retour à la liste</button>
                    </div>`;
                }
            });
    };

    /**
     * Ouvre la modale de simulation pré-remplie avec les paramètres
     * de la simulation choisie.
     */
    window.modifierSimulationHistorique = function (simId) {
        const sim = _trouverSimulation(simId);
        if (!sim) return;
        const cidStr = window._historiqueBassin.clusterId;
        const p = _paramsDe(sim);

        const _set = (id, v) => {
            const el = document.getElementById(id);
            if (!el || v === undefined || v === null || v === '') return;
            // Selects : comparer numériquement — String(4.0) === "4" ne
            // correspond pas à <option value="4.0"> et laisserait le champ vide.
            if (el.tagName === 'SELECT') {
                const cible = String(v);
                let trouves = Array.from(el.options).filter(o => o.value === cible);
                if (!trouves.length) {
                    const nCible = parseFloat(String(v).replace(',', '.'));
                    if (!isNaN(nCible)) {
                        trouves = Array.from(el.options).filter(o => {
                            const n = parseFloat(o.value);
                            return !isNaN(n) && Math.abs(n - nCible) < 1e-6;
                        });
                    }
                }
                if (trouves.length) el.value = trouves[0].value;
                return;
            }
            el.value = String(v);
        };

        _set('sim-select-scenario', p.scenario_key || sim.scenario_pluie);
        _set('sim-select-duree', p.duree_heures != null ? p.duree_heures : sim.duree_heures);
        _set('sim-select-step', p.pas_routage_sec);
        _set('sim-pente-moyenne', p.pente_moyenne_pct);
        _set('sim-select-typologie-sol', p.typologie_sol);
        _set('sim-imperv-pct', p.imperv_pct);
        _set('sim-input-intensite-max', p.intensite_max_mmh);
        _set('sim-select-station', p.station_id);
        _set('sim-select-bassin', cidStr);

        // Paramètres BMS si le scénario d'origine était un BMS
        if (p.bms_mode) {
            _set('sim-select-scenario', 'bms_onm');
            _set('sim-bms-cumul-mm', p.bms_cumul_mm);
            _set('sim-bms-heure-debut', p.bms_heure_debut);
            _set('sim-bms-heure-fin', p.bms_heure_fin);
            _set('sim-bms-profil', p.bms_profil);
            const _vig = document.querySelector(`input[name="bms-vigilance"][value="${p.bms_vigilance || 'orange'}"]`);
            if (_vig) _vig.checked = true;
        }

        // DWF : refléter l'état persisté si disponible
        if (p.dwf_actif !== undefined) {
            const chk = document.getElementById('sim-chk-dwf-actif');
            if (chk) chk.checked = !!p.dwf_actif;
        }

        // Altimétrie terrain : refléter l'état persisté — sinon une
        // simulation modifiée perd silencieusement son mode altimétrique.
        if (p.altimetrie_terrain !== undefined) {
            const chkAlt = document.getElementById('sim-chk-altimetrie-terrain');
            if (chkAlt) chkAlt.checked = !!p.altimetrie_terrain;
        }

        // État physique du réseau (Colmatage & Vieillissement)
        const etatSim = p.etat_reseau || (sim.result_summary && sim.result_summary.metadata && sim.result_summary.metadata.etat_reseau) || null;
        if (etatSim && typeof window.selectionnerPresetEtatReseau === 'function') {
            const nomE = etatSim.scenario_nom || 'personnalise';
            if (nomE === 'nominal' || nomE === 'exploite' || nomE === 'critique') {
                window.selectionnerPresetEtatReseau(nomE);
            } else {
                window.selectionnerPresetEtatReseau('personnalise');
            }
            const rngCol = document.getElementById('sim-etat-colmatage-range');
            const rngVie = document.getElementById('sim-etat-vieillissement-range');
            const inpSeuil = document.getElementById('sim-etat-seuil-pente');
            const chkSig = document.getElementById('sim-chk-depots-sig');
            if (rngCol && etatSim.colmatage_pct !== undefined) rngCol.value = etatSim.colmatage_pct;
            if (rngVie && etatSim.facteur_vieillissement !== undefined) rngVie.value = etatSim.facteur_vieillissement;
            if (inpSeuil && etatSim.seuil_pente_pct !== undefined) inpSeuil.value = etatSim.seuil_pente_pct;
            if (chkSig && etatSim.appliquer_depots_sig !== undefined) chkSig.checked = !!etatSim.appliquer_depots_sig;
            if (etatSim.cible_colmatage) {
                document.querySelectorAll('input[name="sim-etat-cible"]').forEach(r => {
                    r.checked = (r.value === etatSim.cible_colmatage);
                });
            }
            if (typeof window.mettreAJourResumeEtatReseau === 'function') window.mettreAJourResumeEtatReseau();
        } else if (typeof window.selectionnerPresetEtatReseau === 'function') {
            window.selectionnerPresetEtatReseau('nominal');
        }

        window.fermerModalSimulationsBassin();
        if (typeof window.ouvrirModalSimulation === 'function') {
            window.ouvrirModalSimulation(true);
        }
    };

    /**
     * Supprime définitivement la simulation (ligne DB + artefacts).
     */
    window.supprimerSimulationHistorique = function (simId) {
        const sim = _trouverSimulation(simId);
        if (!sim) return;
        const label = sim.name || sim.id;
        const _confirmerPuisSupprimer = () => {
        const token = localStorage.getItem('swmm_access_token');
        const headers = {};
        if (token) headers['Authorization'] = `Bearer ${token}`;

        fetch(`/api/v1/simulations/${encodeURIComponent(simId)}`, {
            method: 'DELETE', headers, credentials: 'include',
        })
            .then(r => {
                if (!r.ok) return r.json().catch(() => ({})).then(d => {
                    throw new Error(d.detail || `Erreur ${r.status}`);
                });
                // Retirer de la liste et des caches
                window._historiqueBassin.sims = (window._historiqueBassin.sims || []).filter(s => String(s.id) !== String(simId));
                if (window._fiabiliteParBassin && window._historiqueBassin.clusterId) {
                    delete window._fiabiliteParBassin[String(window._historiqueBassin.clusterId)];
                    if (typeof window._decorerOptionsFiabilite === 'function') window._decorerOptionsFiabilite();
                }
                if (window._simulationsCache && sim.result_summary) {
                    // nettoie les alias connus
                }
                _rendreListeSimulations();
            })
            .catch(err => {
                if (window.dialogueAlerte) window.dialogueAlerte(`Suppression impossible : ${err.message}`, 'erreur');
                else alert(`Suppression impossible : ${err.message}`);
            });
        };

        if (window.dialogueConfirmer) {
            const _dt = sim.completed_at || sim.created_at || '';
            const _dateStr = _dt ? new Date(_dt).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
            window.dialogueConfirmer({
                titre: `Suppression — ${_scenarioLabel(sim)}`,
                message: `Supprimer définitivement cette simulation${_dateStr ? ` du ${_dateStr}` : ''} ?\n\nCette action retire les résultats calculés et les artefacts associés (modèle .inp, rapport .rpt). Elle est irréversible.`,
                type: 'danger',
                libelleValider: 'Supprimer',
                libelleIgnorer: 'Annuler',
            }).then(ok => { if (ok) _confirmerPuisSupprimer(); });
        } else if (confirm(`Supprimer définitivement « ${label} » ?\n\nCette action retire la simulation, ses résultats et ses artefacts (INP/RPT).`)) {
            _confirmerPuisSupprimer();
        }
    };

    /**
     * Épuration intelligente des simulations redondantes (mêmes paramètres/scénario).
     * Conserve toujours la plus récente de chaque configuration et préserve la simulation active.
     */
    window.epurerDoublonsHistorique = function () {
        const sims = (window._historiqueBassin && window._historiqueBassin.sims) || [];
        if (sims.length <= 1) {
            if (window.dialogueAlerte) window.dialogueAlerte("Aucun doublon à épurer pour ce bassin.", "info");
            else alert("Aucun doublon à épurer pour ce bassin.");
            return;
        }

        const vus = new Set();
        const aSupprimer = [];

        sims.forEach(s => {
            const p = _paramsDe(s);
            const provDwf = s.result_summary?.provenance?.apports_dwf || s.summary_kpis?.provenance?.apports_dwf;
            const nInj = (provDwf && Array.isArray(provDwf.injectes)) ? provDwf.injectes.length : 0;
            const sig = `${p.scenario_key || s.scenario_pluie}_${s.duree_heures}_${nInj}`;

            const estActive = window._dernierResultatSimulation && (
                String(window._dernierResultatSimulation.id) === String(s.id) ||
                (window._dernierResultatSimulation.meta && String(window._dernierResultatSimulation.meta.simulation_id) === String(s.id))
            );

            if (vus.has(sig)) {
                if (!estActive) {
                    aSupprimer.push(s);
                }
            } else {
                vus.add(sig);
            }
        });

        if (aSupprimer.length === 0) {
            const msg = "Toutes les simulations de la liste correspondent déjà à des configurations ou scénarios distincts.";
            if (window.dialogueAlerte) window.dialogueAlerte(msg, "info");
            else alert(msg);
            return;
        }

        const actionSuppr = () => {
            const token = localStorage.getItem('swmm_access_token');
            const headers = {};
            if (token) headers['Authorization'] = `Bearer ${token}`;

            Promise.all(aSupprimer.map(s => fetch(`/api/v1/simulations/${encodeURIComponent(s.id)}`, { method: 'DELETE', headers, credentials: 'include' })))
                .then(() => {
                    const cidStr = window._historiqueBassin.clusterId;
                    window.ouvrirModalSimulationsBassin(cidStr, false);
                })
                .catch(err => {
                    const errTxt = "Erreur lors de l'épuration : " + err.message;
                    if (window.dialogueAlerte) window.dialogueAlerte(errTxt, "erreur");
                    else alert(errTxt);
                });
        };

        if (window.dialogueConfirmer) {
            window.dialogueConfirmer({
                titre: "Épurer les doublons de simulation",
                message: `Supprimer ${aSupprimer.length} simulation(s) antérieure(s) redondante(s) et ne conserver que la plus récente pour chaque configuration ?`,
                type: "warning",
                libelleValider: "Épurer les doublons",
                libelleIgnorer: "Annuler"
            }).then(ok => { if (ok) actionSuppr(); });
        } else if (confirm(`Supprimer ${aSupprimer.length} simulation(s) redondante(s) et ne conserver que la plus récente pour chaque configuration ?`)) {
            actionSuppr();
        }
    };

    // Fermeture par clic sur le fond et touche Échap
    document.addEventListener('click', (e) => {
        const modal = document.getElementById('modal-simulations-bassin');
        if (modal && e.target === modal) window.fermerModalSimulationsBassin();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            const modal = document.getElementById('modal-simulations-bassin');
            if (modal && modal.style.display !== 'none') window.fermerModalSimulationsBassin();
        }
    });
})();
