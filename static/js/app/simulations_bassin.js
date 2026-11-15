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

    function _rendreListeSimulations() {
        const corps = document.getElementById('sim-hist-corps');
        const pied = document.getElementById('sim-hist-pied');
        const { clusterId, sims } = window._historiqueBassin;
        if (!corps) return;

        if (!sims.length) {
            corps.innerHTML = `<div style="text-align:center;color:#94a3b8;padding:34px;">
                <i class="fas fa-flask fa-2x mb-3" style="color:#38bdf8;"></i>
                <p>Aucune simulation enregistrée pour ce bassin.<br><small>Lancez un calcul depuis la modale Simulation.</small></p>
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
            const statutBadge = s.status === 'completed'
                ? '<span style="font-size:0.68rem;background:rgba(52,211,153,0.15);color:#34d399;border:1px solid rgba(52,211,153,0.4);padding:1px 7px;border-radius:9999px;font-weight:700;">terminée</span>'
                : `<span style="font-size:0.68rem;background:rgba(148,163,184,0.15);color:#94a3b8;border:1px solid rgba(148,163,184,0.4);padding:1px 7px;border-radius:9999px;font-weight:700;">${_esc(s.status)}</span>`;
            const fiabBadge = fiab
                ? `<span title="Fiabilité du modèle : ${_esc(verdict)}" style="font-size:0.68rem;background:${fiab.bg};color:${fiab.color};border:1px solid ${fiab.border};padding:1px 7px;border-radius:9999px;font-weight:700;">${fiab.icon} ${fiab.label}</span>`
                : '';
            const actions = s.status === 'completed' ? `
                <button onclick="executerSimulationHistorique('${_esc(s.id)}')" title="Relancer à l'identique (mêmes paramètres)" style="padding:5px 10px;background:linear-gradient(135deg,#0284c7,#0369a1);border:none;color:#fff;border-radius:7px;font-size:0.76rem;font-weight:700;cursor:pointer;">
                    <i class="fas fa-play"></i> Exécuter
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
     * Exécute la simulation à l'identique : mêmes paramètres persistés,
     * force_recalculate pour obtenir un vrai recalcul SWMM.
     */
    window.executerSimulationHistorique = function (simId) {
        const sim = _trouverSimulation(simId);
        const cidStr = window._historiqueBassin.clusterId;
        if (!sim || !cidStr) return;
        const p = _paramsDe(sim);
        const corps = document.getElementById('sim-hist-corps');

        const payload = {
            scenario_key: p.scenario_key || sim.scenario_pluie || 'pluie_decennale',
            duree_heures: p.duree_heures != null ? p.duree_heures : (sim.duree_heures || null),
            pas_routage_sec: p.pas_routage_sec || 5,
            pente_moyenne_pct: p.pente_moyenne_pct != null ? p.pente_moyenne_pct : 1.0,
            buffer_m: p.buffer_m != null ? p.buffer_m : 35.0,
            valider_raccordement: p.valider_raccordement !== false,
            typologie_sol: p.typologie_sol || 'habitat_mixte',
            imperv_pct: p.imperv_pct != null ? p.imperv_pct : null,
            intensite_max_mmh: p.intensite_max_mmh != null ? p.intensite_max_mmh : null,
            station_id: p.station_id || 'chlef_anrh_siege',
            bms_mode: !!p.bms_mode,
            bms_vigilance: p.bms_vigilance || 'orange',
            bms_cumul_mm: p.bms_cumul_mm != null ? p.bms_cumul_mm : 30.0,
            bms_heure_debut: p.bms_heure_debut || '07:00',
            bms_heure_fin: p.bms_heure_fin || '21:00',
            bms_profil: p.bms_profil || 'cloche',
            dwf_actif: p.dwf_actif,
            cluster_id: cidStr,
            bassin_ref: p.bassin_ref || null,
            force_recalculate: true,
        };
        if (Array.isArray(p.raccordements_orphelins) && p.raccordements_orphelins.length) {
            payload.raccordements_orphelins = p.raccordements_orphelins.map(x =>
                typeof x === 'string' ? { id: x } : x);
        }

        if (corps) {
            corps.innerHTML = `<div style="text-align:center;color:#94a3b8;padding:40px;">
                <i class="fas fa-circle-notch fa-spin fa-2x mb-3" style="color:#38bdf8;"></i>
                <p><b>Exécution SWMM 5.2 en cours…</b><br><small>Résolution Saint-Venant à l'identique des paramètres d'origine</small></p>
            </div>`;
        }

        const token = localStorage.getItem('swmm_access_token');
        const headers = { 'Content-Type': 'application/json' };
        if (token) headers['Authorization'] = `Bearer ${token}`;

        fetch('/api/v1/simulations/run', {
            method: 'POST', headers, credentials: 'include',
            body: JSON.stringify(payload),
        })
            .then(r => r.json().then(d => ({ ok: r.ok, d })))
            .then(({ ok, d }) => {
                if (!ok || !d || d.status !== 'success') {
                    const msg = (d && (d.detail || d.message)) || 'Échec de la simulation';
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
                // Recharger l'historique au prochain accès
                window._historiqueBassin = { clusterId: null, sims: [] };
            })
            .catch(err => {
                if (corps) {
                    corps.innerHTML = `<div style="text-align:center;color:#f87171;padding:30px;">
                        <i class="fas fa-exclamation-triangle fa-2x mb-3"></i>
                        <p>Échec de l'exécution : ${_esc(err.message)}</p>
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
        if (!confirm(`Supprimer définitivement « ${label} » ?\n\nCette action retire la simulation, ses résultats et ses artefacts (INP/RPT).`)) return;

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
            .catch(err => alert(`Suppression impossible : ${err.message}`));
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
