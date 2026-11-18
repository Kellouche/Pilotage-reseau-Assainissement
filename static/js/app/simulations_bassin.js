/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Objet : Modale d'historique des simulations d'un bassin versant
 *        (exécuter à l'identique / modifier / supprimer)
 * ================================================================================
 */
(function () {
    'use strict';

    window._historiqueBassin = { clusterId: null, sims: [] };

    const _SCENARIO_LABELS = {
        'pluie_biennale': 'Pluie biennale (T = 2 ans)',
        'pluie_decennale': 'Pluie décennale (T = 10 ans)',
        'pluie_cinquantennale': 'Pluie cinquantennale (T = 50 ans)',
        'pluie_centennale': 'Pluie centennale (T = 100 ans)',
        'pluie_orage_2h': 'Orage d’été 2 h',
        'bms_onm': 'Scénario BMS ONM',
    };

    const _FIAB = {
        'SAIN':       { icon: '🟢', label: 'Modèle sain',     color: '#34d399', bg: 'rgba(52,211,153,0.15)',  border: 'rgba(52,211,153,0.45)' },
        'A_VERIFIER': { icon: '🟠', label: 'À vérifier',     color: '#fbbf24', bg: 'rgba(251,191,36,0.15)',  border: 'rgba(251,191,36,0.45)' },
        'DEGRADE':    { icon: '🔴', label: 'Modèle dégradé', color: '#f87171', bg: 'rgba(248,113,113,0.15)', border: 'rgba(248,113,113,0.45)' },
    };

    function _esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function _scenarioLabel(sim) {
        const sk = (sim.result_summary && sim.result_summary.parameters && sim.result_summary.parameters.scenario_key)
            || sim.scenario_pluie || '';
        return _SCENARIO_LABELS[sk] || (sk ? sk.replace(/_/g, ' ') : 'Simulation');
    }

    function _fiabiliteDe(sim) {
        if (window._fiabiliteDepuisSimulation) return window._fiabiliteDepuisSimulation(sim);
        const rs = sim.result_summary || {};
        return rs.fiabilite_modele || null;
    }

    function _paramsDe(sim) {
        return (sim.result_summary && sim.result_summary.parameters) || {};
    }

    /**
     * Ouvre la modale et charge l'historique des simulations du bassin.
     * `auto` : n'ouvre qu'une fois par bassin (évite la réouverture en boucle).
     */
    window.ouvrirModalSimulationsBassin = function (clusterId, auto = false) {
        const cidStr = String(clusterId || '').trim();
        if (!cidStr) return;
        if (auto && window._bassinModalPour === cidStr) return;
        window._bassinModalPour = cidStr;

        const modal = document.getElementById('modal-simulations-bassin');
        const corps = document.getElementById('sim-hist-corps');
        const titre = document.getElementById('sim-hist-titre');
        const sousTitre = document.getElementById('sim-hist-sous-titre');
        if (!modal || !corps) return;

        const nomBassin = (window._bassinNoms && window._bassinNoms[cidStr]) || `Bassin ${cidStr}`;
        if (titre) titre.textContent = `Simulations — ${nomBassin}`;
        if (sousTitre) sousTitre.textContent = 'Historique des calculs SWMM 5.2 — exécuter, modifier ou supprimer';

        modal.style.display = 'flex';
        corps.innerHTML = '<div style="text-align:center;color:#94a3b8;padding:30px;"><i class="fas fa-spinner fa-spin fa-2x mb-3"></i><p>Chargement de l’historique…</p></div>';

        const token = localStorage.getItem('swmm_access_token');
        const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
        fetch(`/api/v1/simulations/bassin/${encodeURIComponent(cidStr)}/historique`, { headers, credentials: 'include' })
            .then(r => r.ok ? r.json() : Promise.reject(new Error(`Erreur ${r.status}`)))
            .then(d => {
                window._historiqueBassin = { clusterId: cidStr, sims: (d && d.simulations) || [] };
                _rendreListeSimulations();
            })
            .catch(err => {
                corps.innerHTML = `<div style="text-align:center;color:#f87171;padding:30px;"><i class="fas fa-exclamation-triangle fa-2x mb-3"></i><p>Impossible de charger l’historique : ${_esc(err.message)}</p></div>`;
            });
    };

    window.fermerModalSimulationsBassin = function () {
        const modal = document.getElementById('modal-simulations-bassin');
        if (modal) modal.style.display = 'none';
    };

    /**
     * Action « Simuler » du menu Actions : si le bassin choisi possède déjà
     * des simulations, on ouvre d'abord l'historique (affichage instantané
     * des résultats) ; sinon on ouvre directement la modale de simulation.
     * Sans bassin sélectionné, comportement historique inchangé.
     */
    /**
     * Résout le bassin « courant » pour l'action Simuler :
     *  1. #bassin-select (sélection explicite)
     *  2. _selectedClusterId (dernier clic sur la carte)
     *  3. _dernierResultatSimulation.meta (dernier bassin affiché —
     *     survit au rechargement de page via /simulations/latest)
     * Retourne { historyId, optionValue } : historyId pour l'endpoint
     * (accepte cluster_id dropdown OU exutoire), optionValue = valeur
     * de l'option #bassin-select correspondante (null si introuvable).
     */
    function _resoudreBassinPourSimulation() {
        const bSel = document.getElementById('bassin-select');
        if (bSel && bSel.value) {
            return { historyId: String(bSel.value), optionValue: String(bSel.value) };
        }
        try {
            if (typeof _selectedClusterId !== 'undefined' && _selectedClusterId !== null && _selectedClusterId !== '') {
                return { historyId: String(_selectedClusterId), optionValue: String(_selectedClusterId) };
            }
        } catch (_) {}

        const meta = window._dernierResultatSimulation && window._dernierResultatSimulation.meta;
        if (meta) {
            const cidMeta = String(meta.cluster_id !== undefined && meta.cluster_id !== null ? meta.cluster_id : '').trim();
            const cidMetaBas = cidMeta.toLowerCase();
            const nomMeta = String(meta.cluster_nom || meta.bassin_nom || '').trim().toLowerCase();
            if (bSel && cidMeta) {
                let trouve = null;
                for (const opt of bSel.options) {
                    if (!opt.value) continue;
                    if (String(opt.value) === cidMeta) { trouve = opt.value; break; }
                    const exId = String(opt.dataset.exutoireId || '').trim().toLowerCase();
                    const bref = String(opt.dataset.bassinRef || '').trim().toLowerCase();
                    if ((exId && exId === cidMetaBas) || (bref && bref === ('exutoire:' + cidMetaBas))) {
                        trouve = opt.value; break;
                    }
                }
                if (!trouve && nomMeta) {
                    // Repli par nom toléré UNIQUEMENT si un seul bassin
                    // porte ce nom — les homonymes (« Chorfa ») rendraient
                    // la correspondance ambiguë et potentiellement fausse.
                    const _homonymes = [];
                    for (const opt of bSel.options) {
                        const txt = String(opt.textContent || '').trim().toLowerCase();
                        if (txt === nomMeta || txt.startsWith(nomMeta + ' ') || txt.startsWith(nomMeta + '(')) {
                            _homonymes.push(opt.value);
                        }
                    }
                    if (_homonymes.length === 1) trouve = _homonymes[0];
                }
                if (trouve) return { historyId: trouve, optionValue: trouve };
            }
            if (cidMeta) return { historyId: cidMeta, optionValue: null };
        }
        return { historyId: '', optionValue: null };
    }

    window.ouvrirSimulationOuHistorique = function () {
        const res = _resoudreBassinPourSimulation();
        const cidStr = res.historyId;
        if (!cidStr) {
            if (typeof window.ouvrirModalSimulation === 'function') window.ouvrirModalSimulation();
            return;
        }
        const token = localStorage.getItem('swmm_access_token');
        const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
        fetch(`/api/v1/simulations/bassin/${encodeURIComponent(cidStr)}/historique`, { headers, credentials: 'include' })
            .then(r => r.ok ? r.json() : Promise.reject(new Error(`Erreur ${r.status}`)))
            .then(d => {
                const sims = (d && d.simulations) || [];
                if (sims.length > 0) {
                    // Afficher le titre avec le nom du bassin résolu
                    window.ouvrirModalSimulationsBassin(res.optionValue || cidStr, false);
                } else {
                    _preselectionnerBassinPourModal(res.optionValue);
                    if (typeof window.ouvrirModalSimulation === 'function') {
                        window.ouvrirModalSimulation();
                    }
                }
            })
            .catch(() => {
                _preselectionnerBassinPourModal(res.optionValue);
                if (typeof window.ouvrirModalSimulation === 'function') window.ouvrirModalSimulation();
            });
    };

    /**
     * Pré-sélectionne le bassin dans #bassin-select / _selectedClusterId
     * avant d'ouvrir la modale de simulation (évite le 1er bassin de la
     * liste quand aucune sélection n'a été faite après un rechargement).
     */
    function _preselectionnerBassinPourModal(optionValue) {
        if (!optionValue) return;
        const bSel = document.getElementById('bassin-select');
        if (bSel) {
            for (const opt of bSel.options) {
                if (String(opt.value) === String(optionValue)) { bSel.value = optionValue; break; }
            }
        }
        try { if (typeof _selectedClusterId !== 'undefined') _selectedClusterId = optionValue; } catch (_) {}
        window._selectedClusterId = optionValue;
    }

    /**
     * Bouton « Nouvelle simulation » de la modale historique : ferme
     * l'historique et ouvre la modale de simulation avec le bassin
     * pré-sélectionné. Le backend déduplique : des paramètres identiques
     * à une simulation existante restituent ses résultats sans recalcul.
     */
    /**
     * Retrouve la valeur d'option #bassin-select correspondant à un id
     * (espace dropdown, exutoire_id, bassin_ref ou nom du bassin).
     */
    function _trouverOptionBassin(cidStr) {
        const bSel = document.getElementById('bassin-select');
        if (!bSel || !cidStr) return null;
        const cidBas = String(cidStr).trim().toLowerCase();
        const nomCherche = String((window._bassinNoms && window._bassinNoms[cidStr]) || '').trim().toLowerCase();
        for (const opt of bSel.options) {
            if (!opt.value) continue;
            if (String(opt.value) === String(cidStr)) return opt.value;
            const exId = String(opt.dataset.exutoireId || '').trim().toLowerCase();
            const bref = String(opt.dataset.bassinRef || '').trim().toLowerCase();
            if ((exId && exId === cidBas) || (bref && bref === ('exutoire:' + cidBas))) return opt.value;
        }
        if (nomCherche) {
            for (const opt of bSel.options) {
                const txt = String(opt.textContent || '').trim().toLowerCase();
                if (txt === nomCherche || txt.startsWith(nomCherche + ' ') || txt.startsWith(nomCherche + '(')) return opt.value;
            }
        }
        return null;
    }

    window.nouvelleSimulationDepuisHistorique = function () {
        const cidStr = String(window._historiqueBassin.clusterId || '');
        window.fermerModalSimulationsBassin();
        const optionValue = _trouverOptionBassin(cidStr);
        if (optionValue) {
            const bSel = document.getElementById('bassin-select');
            if (bSel) bSel.value = optionValue;
            try { if (typeof _selectedClusterId !== 'undefined') _selectedClusterId = optionValue; } catch (_) {}
            window._selectedClusterId = optionValue;
        }
        if (typeof window.ouvrirModalSimulation === 'function') {
            window.ouvrirModalSimulation(true);
        }
    };

    /**
     * Bouton toolbar : rouvre l'historique des simulations pour le bassin
     * courant (sélectionné, sinon dernier bassin consulté / simulé).
     */
    window.ouvrirModalSimulationsBassinDepuisToolbar = function () {
        let cidStr = '';
        const bSel = document.getElementById('bassin-select');
        if (bSel && bSel.value) cidStr = String(bSel.value);
        if (!cidStr && window._dernierResultatSimulation && window._dernierResultatSimulation.meta) {
            const _m = window._dernierResultatSimulation.meta;
            cidStr = String(_m.cluster_id !== undefined && _m.cluster_id !== null ? _m.cluster_id : '');
        }
        if (!cidStr) cidStr = String(window._bassinModalPour || '');
        if (!cidStr) {
            if (window.dialogueAlerte) window.dialogueAlerte('Sélectionnez d’abord un bassin versant sur la carte ou dans la liste.');
            else alert('Sélectionnez d’abord un bassin versant sur la carte ou dans la liste.');
            return;
        }
        window.ouvrirModalSimulationsBassin(cidStr, false);
    };

    function _rendreListeSimulations() {
        const corps = document.getElementById('sim-hist-corps');
        const pied = document.getElementById('sim-hist-pied');
        const { clusterId, sims } = window._historiqueBassin;
        if (!corps) return;

        if (!sims.length) {
            corps.innerHTML = `<div style="text-align:center;color:#94a3b8;padding:34px;">
                <i class="fas fa-flask fa-2x mb-3" style="color:#38bdf8;"></i>
                <p>Aucune simulation enregistrée pour ce bassin.<br><small>Lancez un calcul depuis la modale Simulation.</small></p>
                <p style="margin-top:10px;font-size:0.74rem;color:#64748b;">Plusieurs bassins peuvent porter le même nom — vérifiez la surface et le nombre de regards dans la liste pour viser le bon exutoire.</p>
            </div>`;
            if (pied) pied.textContent = '';
            return;
        }
        if (pied) pied.textContent = `${sims.length} simulation(s) — plus récentes d'abord`;

        corps.innerHTML = sims.map((s, i) => {
            const rs = s.result_summary || {};
            const params = rs.parameters || {};
            const verdict = _fiabiliteDe(s);
            const fiab = verdict ? _FIAB[verdict] : null;
            const dt = s.completed_at || s.created_at || '';
            const dateStr = dt ? new Date(dt).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
            const pic = rs.peak_outflow_m3s != null ? `${Number(rs.peak_outflow_m3s).toFixed(3)} m³/s` : '—';
            const inondes = rs.flooded_nodes_count != null ? `${rs.flooded_nodes_count} regard(s)` : '—';
            // Identité stable du bassin portée par la simulation : permet de
            // vérifier visuellement qu'une ligne appartient bien au bassin
            // affiché (ex. exutoire:8_rejets_346731 = « Rempois chorfa »).
            const identiteBassin = s.exutoire_noeud || s.bassin_ref || '';
            const statutBadge = s.status === 'completed'
                ? '<span style="font-size:0.68rem;background:rgba(52,211,153,0.15);color:#34d399;border:1px solid rgba(52,211,153,0.4);padding:1px 7px;border-radius:9999px;font-weight:700;">terminée</span>'
                : `<span style="font-size:0.68rem;background:rgba(148,163,184,0.15);color:#94a3b8;border:1px solid rgba(148,163,184,0.4);padding:1px 7px;border-radius:9999px;font-weight:700;">${_esc(s.status)}</span>`;
            const fiabBadge = fiab
                ? `<span title="Fiabilité du modèle : ${_esc(verdict)}" style="font-size:0.68rem;background:${fiab.bg};color:${fiab.color};border:1px solid ${fiab.border};padding:1px 7px;border-radius:9999px;font-weight:700;">${fiab.icon} ${fiab.label}</span>`
                : '';
            const actions = s.status === 'completed' ? `
                <button onclick="executerSimulationHistorique('${_esc(s.id)}')" title="Afficher les résultats sauvegardés (instantané, sans recalcul)" style="padding:5px 10px;background:linear-gradient(135deg,#0284c7,#0369a1);border:none;color:#fff;border-radius:7px;font-size:0.76rem;font-weight:700;cursor:pointer;">
                    <i class="fas fa-eye"></i> Afficher
                </button>
                <button onclick="modifierSimulationHistorique('${_esc(s.id)}')" title="Ouvrir la modale de simulation pré-remplie" style="padding:5px 10px;background:rgba(56,189,248,0.12);border:1px solid rgba(56,189,248,0.4);color:#38bdf8;border-radius:7px;font-size:0.76rem;font-weight:700;cursor:pointer;">
                    <i class="fas fa-pen"></i> Modifier
                </button>
                <button onclick="supprimerSimulationHistorique('${_esc(s.id)}')" title="Supprimer définitivement cette simulation" style="padding:5px 10px;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.4);color:#f87171;border-radius:7px;font-size:0.76rem;font-weight:700;cursor:pointer;">
                    <i class="fas fa-trash"></i> Supprimer
                </button>` : '';

            return `
            <div style="background:rgba(15,23,42,0.6);border:1px solid rgba(255,255,255,0.08);border-radius:10px;padding:12px 14px;margin-bottom:10px;">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;flex-wrap:wrap;">
                    <div style="min-width:0;">
                        <div style="font-weight:700;font-size:0.86rem;color:#f1f5f9;">${_esc(s.name || `Simulation ${i + 1}`)}</div>
                        <div style="font-size:0.74rem;color:#94a3b8;margin-top:3px;display:flex;gap:12px;flex-wrap:wrap;">
                            <span><i class="fas fa-cloud-rain me-1" style="color:#38bdf8;"></i>${_esc(_scenarioLabel(s))}</span>
                            <span><i class="fas fa-clock me-1" style="color:#38bdf8;"></i>${s.duree_heures != null ? `${s.duree_heures} h` : '—'}</span>
                            <span><i class="fas fa-calendar me-1" style="color:#38bdf8;"></i>${dateStr}</span>
                            <span><i class="fas fa-water me-1" style="color:#38bdf8;"></i>Pic : ${pic}</span>
                            <span><i class="fas fa-exclamation-triangle me-1" style="color:#f59e0b;"></i>${inondes}</span>
                            ${identiteBassin ? `<span title="Identité stable du bassin (exutoire)" style="color:#64748b;"><i class="fas fa-map-marker-alt me-1"></i>${_esc(identiteBassin)}</span>` : ''}
                        </div>
                    </div>
                    <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
                        ${fiabBadge}${statutBadge}
                    </div>
                </div>
                ${actions ? `<div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap;">${actions}</div>` : ''}
            </div>`;
        }).join('');
    }

    window._rendreListeSimulations = _rendreListeSimulations;

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
        const cidStr = window._historiqueBassin.clusterId;
        if (!sim || !cidStr) return;
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
                const _cid = (d.meta && d.meta.cluster_id) || cidStr;
                window._simulationsCache[String(_cid)] = d;
                if (d.meta && d.meta.bassin_nom) window._simulationsCache[String(d.meta.bassin_nom)] = d;
                if (d.meta && d.meta.cluster_nom) window._simulationsCache[String(d.meta.cluster_nom)] = d;
                window._dernierResultatSimulation = d;
                if (window._fiabiliteParBassin) {
                    window._fiabiliteParBassin[String(_cid)] = d;
                    if (typeof window._decorerOptionsFiabilite === 'function') window._decorerOptionsFiabilite();
                }
                if (typeof afficherResultatsSimulation === 'function') afficherResultatsSimulation(d);
                if (typeof window.mettreAJourIndicateurBassin === 'function') {
                    window.mettreAJourIndicateurBassin(cidStr, d);
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
            if (el && v !== undefined && v !== null && v !== '') el.value = String(v);
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
