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
        let cidStr = String(clusterId || '').trim();
        if (!cidStr) {
            const res = (typeof _resoudreBassinPourSimulation === 'function') ? _resoudreBassinPourSimulation() : null;
            cidStr = (res && res.historyId) ? String(res.historyId).trim() : '';
        }
        if (!cidStr && window._selectedClusterId) {
            cidStr = String(window._selectedClusterId).trim();
        }
        if (!cidStr && window._dernierResultatSimulation && window._dernierResultatSimulation.meta) {
            const m = window._dernierResultatSimulation.meta;
            cidStr = String(m.cluster_id || m.exutoire_id || m.bassin_nom || '').trim();
        }

        const isGlobal = !cidStr;
        if (auto && window._bassinModalPour === (cidStr || '__global__')) return;
        window._bassinModalPour = cidStr || '__global__';

        const modal = document.getElementById('modal-simulations-bassin');
        const corps = document.getElementById('sim-hist-corps');
        const titre = document.getElementById('sim-hist-titre');
        const sousTitre = document.getElementById('sim-hist-sous-titre');
        if (!modal || !corps) return;

        let nomBassin = '';
        if (isGlobal) {
            const pName = (window._rawNetworkData && window._rawNetworkData.project_name) || 'Réseau actif';
            nomBassin = `Réseau complet (${pName})`;
        } else {
            nomBassin = (window._bassinNoms && window._bassinNoms[cidStr]) || null;
            if (!nomBassin && window._bassinProperties && window._bassinProperties[cidStr]) {
                nomBassin = window._bassinProperties[cidStr].nom;
            }
            if (!nomBassin && window._dernierResultatSimulation && window._dernierResultatSimulation.meta) {
                nomBassin = window._dernierResultatSimulation.meta.cluster_nom || window._dernierResultatSimulation.meta.bassin_nom;
            }
            if (!nomBassin) nomBassin = `Bassin ${cidStr}`;
        }

        if (titre) titre.textContent = `Simulations — ${nomBassin}`;
        if (sousTitre) sousTitre.textContent = isGlobal
            ? 'Historique global des calculs SWMM 5.2 — exécuter, modifier ou supprimer'
            : 'Historique des calculs SWMM 5.2 — exécuter, modifier ou supprimer';

        modal.style.display = 'flex';

        // Garde-fou d'ingénierie : un ouvrage isolé sans réseau collecteur amont n'a pas de simulations
        if (!isGlobal && window._bassinsIsoleIds && window._bassinsIsoleIds.has(cidStr)) {
            if (titre) titre.textContent = `Ouvrage isolé — ${nomBassin}`;
            if (sousTitre) sousTitre.textContent = 'Non simulable : absence de réseau collecteur amont';
            corps.innerHTML = `
                <div style="text-align: center; padding: 40px 20px; color: #94a3b8;">
                    <i class="fas fa-ban fa-3x" style="color: #f59e0b; margin-bottom: 14px;"></i>
                    <h4 style="color: #f8fafc; margin-bottom: 8px;">Aucune simulation possible</h4>
                    <p style="font-size: 13px; max-width: 440px; margin: 0 auto 16px auto; line-height: 1.5; color: #cbd5e1;">
                        Cet ouvrage est un exutoire ou regard ponctuel isolé sans réseau collecteur amont. Les simulations dynamiques SWMM 5.2 ne sont pas applicables à cet élément.
                    </p>
                    <button type="button" onclick="fermerModalSimulationsBassin();" style="padding: 8px 18px; background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.2); color: #fff; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 600;">
                        Fermer
                    </button>
                </div>
            `;
            return;
        }

        corps.innerHTML = '<div style="text-align:center;color:#94a3b8;padding:30px;"><i class="fas fa-spinner fa-spin fa-2x mb-3"></i><p>Chargement de l’historique…</p></div>';

        const token = localStorage.getItem('swmm_access_token');
        const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
        const urlHist = isGlobal
            ? '/api/v1/simulations/bassin/tous/historique'
            : `/api/v1/simulations/bassin/${encodeURIComponent(cidStr)}/historique`;
        fetch(urlHist, { headers, credentials: 'include' })
            .then(r => r.ok ? r.json() : Promise.reject(new Error(`Erreur ${r.status}`)))
            .then(d => {
                window._historiqueBassin = { clusterId: cidStr, isGlobal: isGlobal, sims: (d && d.simulations) || [] };
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
     * courant (sélectionné, sinon dernier bassin consulté / simulé),
     * ou l'historique global du projet si aucun bassin n'est sélectionné.
     */
    window.ouvrirModalSimulationsBassinDepuisToolbar = function () {
        let cidStr = '';
        const bSel = document.getElementById('bassin-select');
        if (bSel && bSel.value) cidStr = String(bSel.value);
        if (!cidStr && window._selectedClusterId) cidStr = String(window._selectedClusterId);
        if (!cidStr && window._dernierResultatSimulation && window._dernierResultatSimulation.meta) {
            const _m = window._dernierResultatSimulation.meta;
            cidStr = String(_m.cluster_id !== undefined && _m.cluster_id !== null ? _m.cluster_id : '');
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

            // Détection si c'est la simulation active actuellement visualisée
            const estActive = window._dernierResultatSimulation && (
                String(window._dernierResultatSimulation.id) === String(s.id) ||
                (window._dernierResultatSimulation.meta && String(window._dernierResultatSimulation.meta.simulation_id) === String(s.id))
            );
            const activeBadge = estActive
                ? `<span style="font-size:0.68rem;background:rgba(52,211,153,0.2);color:#34d399;border:1px solid #34d399;padding:1px 8px;border-radius:9999px;font-weight:800;"><i class="fas fa-check-circle me-1"></i>Active</span>`
                : '';

            // Analyse et badge DWF de la simulation
            const provDwf = rs.provenance?.apports_dwf || (s.summary_kpis && s.summary_kpis.provenance && s.summary_kpis.provenance.apports_dwf);
            let dwfBadge = '';
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
                    dwfBadge = `<span title="${nInj} apport(s) DWF injecté(s) (${qLs} L/s)" style="font-size:0.68rem;background:rgba(6,182,212,0.18);color:#38bdf8;border:1px solid rgba(6,182,212,0.45);padding:1px 7px;border-radius:9999px;font-weight:700;"><i class="fas fa-faucet-drip me-1"></i>DWF ${qLs} L/s (${nInj})</span>`;
                } else if (nIgn > 0) {
                    dwfBadge = `<span title="${nIgn} apport(s) exclu(s) hors réseau" style="font-size:0.68rem;background:rgba(245,158,11,0.18);color:#fbbf24;border:1px solid rgba(245,158,11,0.45);padding:1px 7px;border-radius:9999px;font-weight:700;">⚠️ DWF exclu (${nIgn})</span>`;
                }
            } else if (params.dwf_actif) {
                dwfBadge = `<span style="font-size:0.68rem;background:rgba(6,182,212,0.15);color:#06b6d4;border:1px solid rgba(6,182,212,0.4);padding:1px 7px;border-radius:9999px;font-weight:700;"><i class="fas fa-faucet-drip me-1"></i>DWF actif</span>`;
            } else {
                dwfBadge = `<span style="font-size:0.68rem;background:rgba(148,163,184,0.1);color:#94a3b8;border:1px solid rgba(148,163,184,0.25);padding:1px 7px;border-radius:9999px;">Sans DWF</span>`;
            }

            const statutBadge = s.status === 'completed'
                ? '<span style="font-size:0.68rem;background:rgba(52,211,153,0.15);color:#34d399;border:1px solid rgba(52,211,153,0.4);padding:1px 7px;border-radius:9999px;font-weight:700;">terminée</span>'
                : `<span style="font-size:0.68rem;background:rgba(148,163,184,0.15);color:#94a3b8;border:1px solid rgba(148,163,184,0.4);padding:1px 7px;border-radius:9999px;font-weight:700;">${_esc(s.status)}</span>`;

            // Badge État du Réseau (Colmatage & Vieillissement)
            const etatMeta = (rs.metadata && rs.metadata.etat_reseau) || params.etat_reseau || null;
            let etatBadge = '';
            if (etatMeta && !etatMeta.est_nominal && (etatMeta.colmatage_pct > 0 || (etatMeta.facteur_vieillissement && etatMeta.facteur_vieillissement > 1.0) || etatMeta.appliquer_depots_sig)) {
                const parts = [];
                if (etatMeta.colmatage_pct > 0) parts.push(`${etatMeta.colmatage_pct}% dépôt${etatMeta.cible_colmatage === 'faibles_pentes' ? ' (<' + (etatMeta.seuil_pente_pct || 0.5) + '%)' : ''}`);
                if (etatMeta.facteur_vieillissement > 1.0) parts.push(`n ×${Number(etatMeta.facteur_vieillissement).toFixed(2)}`);
                if (etatMeta.appliquer_depots_sig) parts.push('+SIG');
                const txtEtat = parts.join(' • ') || _esc(etatMeta.scenario_nom || 'Dégradé');
                etatBadge = `<span title="Scénario d'état du réseau appliqué (${_esc(etatMeta.scenario_nom || 'personnalisé')})" style="font-size:0.68rem;background:rgba(245,158,11,0.18);color:#fbbf24;border:1px solid rgba(245,158,11,0.45);padding:1px 7px;border-radius:9999px;font-weight:700;"><i class="fas fa-water me-1"></i>${txtEtat}</span>`;
            } else {
                etatBadge = `<span title="État nominal du réseau (curé, 0% colmatage)" style="font-size:0.68rem;background:rgba(16,185,129,0.12);color:#34d399;border:1px solid rgba(16,185,129,0.3);padding:1px 7px;border-radius:9999px;">État Nominal</span>`;
            }
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

            const borderStyle = estActive ? 'border: 1px solid rgba(52,211,153,0.5); box-shadow: 0 0 10px rgba(52,211,153,0.15);' : 'border: 1px solid rgba(255,255,255,0.08);';

            return `
            <div style="background:rgba(15,23,42,0.6);${borderStyle}border-radius:10px;padding:12px 14px;margin-bottom:10px;">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;flex-wrap:wrap;">
                    <div style="min-width:0;">
                        <div style="font-weight:700;font-size:0.86rem;color:#f1f5f9;display:flex;align-items:center;gap:8px;">
                            <span style="color:#64748b;font-size:0.75rem;">#${sims.length - i}</span>
                            <span>${_esc(s.name || `Simulation ${i + 1}`)}</span>
                        </div>
                        <div style="font-size:0.74rem;color:#94a3b8;margin-top:4px;display:flex;gap:12px;flex-wrap:wrap;">
                            <span><i class="fas fa-cloud-rain me-1" style="color:#38bdf8;"></i>${_esc(_scenarioLabel(s))}</span>
                            <span><i class="fas fa-clock me-1" style="color:#38bdf8;"></i>${s.duree_heures != null ? `${s.duree_heures} h` : '—'}</span>
                            <span><i class="fas fa-calendar me-1" style="color:#38bdf8;"></i>${dateStr}</span>
                            <span><i class="fas fa-water me-1" style="color:#38bdf8;"></i>Pic : ${pic}</span>
                            <span><i class="fas fa-exclamation-triangle me-1" style="color:#f59e0b;"></i>${inondes}</span>
                            ${identiteBassin ? `<span title="Identité stable du bassin (exutoire)" style="color:#64748b;"><i class="fas fa-map-marker-alt me-1"></i>${_esc(identiteBassin)}</span>` : ''}
                        </div>
                    </div>
                    <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
                        ${activeBadge}${etatBadge}${dwfBadge}${fiabBadge}${statutBadge}
                    </div>
                </div>
                ${actions ? `<div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap;">${actions}</div>` : ''}
            </div>`;
        }).join('');
    }

    window._rendreListeSimulations = _rendreListeSimulations;

    // Pont inter-fichiers : simulations_bassin_actions.js partage
    // l'etat et les helpers du module historique.
    window._simBassinInt = {
        _SCENARIO_LABELS: _SCENARIO_LABELS, _FIAB: _FIAB,
        _esc: _esc, _scenarioLabel: _scenarioLabel, _fiabiliteDe: _fiabiliteDe,
        _paramsDe: _paramsDe, _resoudreBassinPourSimulation: _resoudreBassinPourSimulation,
        _preselectionnerBassinPourModal: _preselectionnerBassinPourModal,
        _trouverOptionBassin: _trouverOptionBassin,
        _rendreListeSimulations: _rendreListeSimulations
    };
})();
