/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-27
 * Objet : Animation temporelle de l'onde de crue (Time Slider - Phase 6.B)
 * ================================================================================
 */

window.timeSliderState = {
    active: false,
    playing: false,
    currentStep: 0,
    speedMultiplier: 1,
    baseIntervalMs: 200,
    intervalId: null,
    data: null,
    chartInstance: null,
    radarGroup: null
};

/**
 * Récupère l'instance de carte Leaflet globale
 */
function _getCarteTS() {
    return window.carte || window.map || (typeof carte !== 'undefined' ? carte : null);
}

/**
 * Centre le panneau en haut de la zone carte disponible.
 * #app-workspace englobe toute la largeur (sidebar incluse) : left:50%
 * du CSS centrait le panneau sur le viewport entier, décalé de moitié
 * de la largeur de la sidebar. On se réfère donc au rect de #map,
 * qui exclut sidebar et toolbar.
 */
function _positionnerTimeSliderCentrer() {
    const panel = document.getElementById('panel-time-slider');
    const ws = document.getElementById('app-workspace');
    const map = document.getElementById('map');
    if (!panel || !ws) return;

    const ref = map || ws;
    const refRect = ref.getBoundingClientRect();
    const wsRect = ws.getBoundingClientRect();
    const w = panel.offsetWidth || 880;
    const h = panel.offsetHeight || 120;

    let left = (refRect.left - wsRect.left) + (refRect.width - w) / 2;
    let top = (refRect.top - wsRect.top) + 16;

    // Bornage : le panneau reste entièrement visible dans le workspace
    left = Math.max(8, Math.min(left, wsRect.width - w - 8));
    top = Math.max(8, Math.min(top, wsRect.height - h - 8));

    panel.style.left = `${Math.round(left)}px`;
    panel.style.top = `${Math.round(top)}px`;
    panel.style.right = 'auto';
    panel.style.bottom = 'auto';
    panel.style.transform = 'none';
}

/**
 * Recentrage automatique après pli/dépli de la sidebar.
 * Sans effet si l'utilisateur a déjà positionné le panneau à la main.
 */
window.recentrerTimeSliderSiNecessaire = function() {
    const panel = document.getElementById('panel-time-slider');
    if (!panel || panel.style.display === 'none') return;
    if (panel.dataset.userMoved === '1') return;
    _positionnerTimeSliderCentrer();
};

/**
 * Bascule l'affichage du contrôleur Time Slider
 */
function toggleTimeSlider(forceState) {
    const state = window.timeSliderState;
    const panel = document.getElementById('panel-time-slider');
    const btn = document.getElementById('btn-time-slider');

    // Vérifier si le bouton est désactivé (pas de simulation)
    if (btn && btn.disabled) {
        window.dialogueAlerte("Aucune simulation disponible pour ce réseau. Veuillez d'abord lancer une simulation SWMM 5.2.", 'info');
        return;
    }

    const newState = (forceState !== undefined) ? forceState : !state.active;

    if (!newState) {
        // Arrêter et fermer
        timeSliderPause();
        state.active = false;
        if (panel) panel.style.display = 'none';
        if (btn) btn.classList.remove('active');

        // Masquer le badge "État à l'instant T"
        const badgeInstant = document.getElementById('badge-instant-state');
        if (badgeInstant) {
            badgeInstant.classList.add('hidden');
        }

        // Déplier la toolbar d'édition si elle était repliée
        const toolbar = document.getElementById('main-edit-toolbar');
        if (toolbar && toolbar.classList.contains('collapsed')) {
            toolbar.classList.remove('collapsed');
        }
        const icon = document.getElementById('icon-collapse-toolbar');
        if (icon) icon.className = 'fas fa-chevron-up';

        // Vider les couches pour forcer le redessin net de l'enveloppe de criticité
        if (window.couches && window.couches.res_conduites) {
            window.couches.res_conduites.clearLayers();
        }
        if (window.couches && window.couches.res_regards) {
            window.couches.res_regards.clearLayers();
        }

        // Rétablir la coloration standard SWMM de la simulation (enveloppe des maximums observés)
        if (window._dernierResultatSimulation && typeof afficherResultatsSimulation === 'function') {
            afficherResultatsSimulation(window._dernierResultatSimulation, true);
        }
        return;
    }

    // VÉRIFICATION : Une simulation doit avoir été effectuée
    const hasSim = !!(window._dernierResultatSimulation &&
                      window._dernierResultatSimulation.conduit_results &&
                      Object.keys(window._dernierResultatSimulation.conduit_results).length > 0);

    if (!hasSim) {
        window.dialogueAlerte("Lancer une simulation pour activer l'animation temporelle de l'onde de crue.", 'info');
        return;
    }

    // Charger les séries temporelles
    chargerDonneesTimeSlider().then(success => {
        if (!success) return;

        state.active = true;
        if (panel) panel.style.display = 'flex';
        if (btn) btn.classList.add('active');

        // Position : centrée en haut de la zone carte, sauf si
        // l'utilisateur a déjà déplacé le panneau manuellement
        if (panel && panel.dataset.userMoved !== '1') {
            _positionnerTimeSliderCentrer();
        }

        // Initialiser le déplacement du panneau (comme hyeto-hydro)
        _initTimeSliderDraggable();

        // Replier la toolbar d'édition (forcer l'état collapsed)
        const toolbar = document.getElementById('main-edit-toolbar');
        if (toolbar && !toolbar.classList.contains('collapsed')) {
            toolbar.classList.add('collapsed');
        }
        const icon = document.getElementById('icon-collapse-toolbar');
        if (icon) icon.className = 'fas fa-chevron-down';

        // Afficher le badge "État hydraulique à l'instant T" dans l'en-tête du player
        const badgeInstant = document.getElementById('badge-instant-state');
        if (badgeInstant) {
            badgeInstant.classList.remove('hidden');
        }

        // S'assurer que les couches de résultats SWMM sont bien montées sur Leaflet
        if (window._dernierResultatSimulation && typeof afficherResultatsSimulation === 'function') {
            if (!window.couches || !window.couches.res_conduites || window.couches.res_conduites.getLayers().length === 0) {
                try {
                    afficherResultatsSimulation(window._dernierResultatSimulation);
                } catch (e_aff) {
                    console.warn("Affichage préalable simulation:", e_aff);
                }
            }
        }

        // Initialiser ou réinitialiser le contrôleur
        _initTimeSliderUI();
        timeSliderSeek(0);

        // Forcer le redessin du canvas chart après affichage du panneau (position en haut)
        setTimeout(() => {
            if (state.chartInstance) {
                state.chartInstance.resize();
                state.chartInstance.update();
            }
        }, 150);
    });
}

/**
 * Affiche le bandeau de fiabilité du modèle sous-jacent quand le
 * garde-fou hydraulicien a rendu un verdict autre que SAIN.
 */
function _appliquerBandeauFiabilite(data) {
    const banner = document.getElementById('ts-fiabilite-banner');
    const texte = document.getElementById('ts-fiabilite-texte');
    if (!banner || !texte) return;

    let verdict = data && data.fiabilite_modele;
    let anomalies = (data && data.modelisation_anomalies) || [];
    if (!verdict && window._dernierResultatSimulation) {
        const gf = ((window._dernierResultatSimulation.agents_expertise || {}).controle_modele_hydraulique) || {};
        verdict = gf.fiabilite_modele;
        anomalies = gf.anomalies || anomalies;
    }
    const meta = {
        'A_VERIFIER': { label: 'à vérifier', color: '#fbbf24', bg: 'rgba(251,191,36,0.12)' },
        'DEGRADE':    { label: 'dégradé',    color: '#f87171', bg: 'rgba(248,113,113,0.12)' },
    }[verdict];
    if (meta) {
        banner.style.display = 'flex';
        banner.style.color = meta.color;
        banner.style.background = meta.bg;
        texte.textContent = `Animation basée sur un modèle à fiabilité ${meta.label} — ${anomalies.length} anomalie(s) détectée(s) par le garde-fou hydraulicien`;
        banner.title = anomalies.map(a => `• ${a.message || a.code || ''}`).join('\n');
    } else {
        banner.style.display = 'none';
    }
}

/**
 * Récupère les données temporelles depuis l'API ou le cache mémoire
 */
async function chargerDonneesTimeSlider() {
    const state = window.timeSliderState;

    // 1. Déjà présent dans le résultat en cache
    if (window._dernierResultatSimulation &&
        window._dernierResultatSimulation.timeseries &&
        window._dernierResultatSimulation.timeseries.status === 'SUCCESS' &&
        window._dernierResultatSimulation.timeseries.steps &&
        window._dernierResultatSimulation.timeseries.steps.length > 0) {
        state.data = window._dernierResultatSimulation.timeseries;
        _appliquerBandeauFiabilite(state.data);
        return true;
    }

    // 2. Appel de l'endpoint dédié
    const badge = document.getElementById('badge-time-status');
    if (badge) {
        badge.textContent = "Chargement...";
        badge.className = "badge-ts badge-info";
    }

    try {
        // Filtrer par le bassin affiché : sans cluster_id, l'API renvoie
        // les séries de la dernière simulation du projet — dont les
        // link_id ne correspondent pas aux conduites affichées
        // (toute la carte resterait verte).
        const _bSel = document.getElementById('bassin-select');
        const _optBassin = (_bSel && _bSel.selectedOptions && _bSel.selectedOptions[0]) || null;
        const _cidBassin = (_bSel && _bSel.value) ? _bSel.value : '';
        // Identité métier stable portée par l'option (dataset) : l'API peut
        // alors résoudre la simulation sans dépendre du cache de
        // sectorisation (pont positionnel→exutoire).
        const _exutoire = _optBassin && _optBassin.dataset ? (_optBassin.dataset.exutoireId || '') : '';
        const _bassinRef = _optBassin && _optBassin.dataset ? (_optBassin.dataset.bassinRef || '') : '';
        const _qsParams = [];
        if (_cidBassin) _qsParams.push(`cluster_id=${encodeURIComponent(_cidBassin)}`);
        if (_exutoire) _qsParams.push(`exutoire_noeud=${encodeURIComponent(_exutoire)}`);
        if (_bassinRef) _qsParams.push(`bassin_ref=${encodeURIComponent(_bassinRef)}`);
        // simulation_id de la sim AFFICHÉE : le slider doit animer ces
        // séries, pas « la plus récente du contexte » (risque de servir
        // les link_id d'une sim d'un autre snapshot réseau).
        const _simAff = (window._dernierResultatSimulation && window._dernierResultatSimulation.simulation_id)
            || (window._dernierResultatSimulation && window._dernierResultatSimulation.meta && window._dernierResultatSimulation.meta.simulation_id)
            || '';
        if (_simAff) _qsParams.push(`simulation_id=${encodeURIComponent(_simAff)}`);
        const _qs = _qsParams.length ? `?${_qsParams.join('&')}` : '';
        const resp = await fetch('/api/v1/simulations/timeseries' + _qs);
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `Erreur serveur (${resp.status})`);
        }
        const data = await resp.json();
        if (!data || !data.steps || data.steps.length === 0) {
            throw new Error("Aucun pas temporel disponible dans la simulation.");
        }
        state.data = data;
        _appliquerBandeauFiabilite(data);
        if (window._dernierResultatSimulation) {
            window._dernierResultatSimulation.timeseries = data;
        }
        return true;
    } catch (err) {
        console.error("Erreur chargement séries temporelles:", err);
        window.dialogueAlerte(`Impossible d'initialiser l'animation temporelle :\n${err.message}`, 'erreur');
        return false;
    }
}

/**
 * Initialise les composants UI et le mini-hydrogramme Chart.js
 */
function _initTimeSliderUI() {
    const state = window.timeSliderState;
    if (!state.data || !state.data.steps) return;

    const steps = state.data.steps;
    const slider = document.getElementById('ts-range-slider');
    const lblStart = document.getElementById('ts-label-start');
    const lblEnd = document.getElementById('ts-label-end');

    if (slider) {
        slider.min = "0";
        slider.max = String(steps.length - 1);
        slider.value = "0";
    }

    if (lblStart) lblStart.textContent = steps[0].time_str || "00:00";
    if (lblEnd) lblEnd.textContent = steps[steps.length - 1].time_str || `${state.data.duration_hours || 4}h`;

    // Création ou mise à jour du mini-hydrogramme Canvas
    _initMiniHydrograph();
}

/**
 * Trace le mini-hydrogramme exutoire avec Chart.js
 */
function _initMiniHydrograph() {
    const state = window.timeSliderState;
    const canvas = document.getElementById('canvas-ts-hydrograph');
    if (!canvas || !state.data) return;

    if (state.chartInstance) {
        state.chartInstance.destroy();
    }

    const labels = state.data.time_labels || state.data.steps.map(s => s.time_str);
    const dataValues = state.data.outflow_series || state.data.steps.map(s => s.outflow_m3s);

    // Plugin personnalisé pour tracer la ligne verticale de progression
    const verticalLinePlugin = {
        id: 'timeSliderVerticalLine',
        afterDraw: (chart) => {
            const activeIdx = window.timeSliderState.currentStep;
            const meta = chart.getDatasetMeta(0);
            if (!meta || !meta.data || !meta.data[activeIdx]) return;

            const x = meta.data[activeIdx].x;
            const topY = chart.scales.y.top;
            const bottomY = chart.scales.y.bottom;
            const ctx = chart.ctx;

            ctx.save();
            ctx.beginPath();
            ctx.moveTo(x, topY);
            ctx.lineTo(x, bottomY);
            ctx.lineWidth = 2;
            ctx.strokeStyle = '#f59e0b';
            ctx.shadowColor = 'rgba(245, 158, 11, 0.8)';
            ctx.shadowBlur = 6;
            ctx.stroke();
            ctx.restore();
        }
    };

    state.chartInstance = new Chart(canvas, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                data: dataValues,
                borderColor: '#38bdf8',
                backgroundColor: 'rgba(56, 189, 248, 0.2)',
                borderWidth: 1.5,
                pointRadius: 0,
                fill: true,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            events: ['click'],
            animation: false,
            plugins: {
                legend: { display: false },
                tooltip: { enabled: false }
            },
            scales: {
                x: { display: false },
                y: { display: false }
            },
            onClick: (e, elements, chart) => {
                const canvasPosition = Chart.helpers.getRelativePosition(e, chart);
                const dataX = chart.scales.x.getValueForPixel(canvasPosition.x);
                if (dataX !== undefined) {
                    const stepIdx = Math.max(0, Math.min(Math.round(dataX), state.data.steps.length - 1));
                    timeSliderSeek(stepIdx);
                }
            }
        },
        plugins: [verticalLinePlugin]
    });
}

/**
 * Se déplace à un pas temporel précis (appelé par le slider ou le timer)
 */
function timeSliderSeek(stepIndex) {
    const state = window.timeSliderState;
    // Tant que le panneau hyétogramme-débit est ouvert, sa dataset fait
    // foi : l'animation et le scrub (slider, mini-hydrogramme, clic
    // graphique) doivent colorier la carte avec les MÊMES séries, sinon
    // state.data peut être périmé ou provenir d'une autre simulation.
    if (state && window.hyetoHydroState && window.hyetoHydroState.visible
        && window.hyetoHydroState.data && window.hyetoHydroState.data.steps) {
        state.data = window.hyetoHydroState.data;
    }
    if (!state.data || !state.data.steps) return;

    const idx = parseInt(stepIndex, 10);
    if (isNaN(idx) || idx < 0 || idx >= state.data.steps.length) return;

    state.currentStep = idx;
    const step = state.data.steps[idx];

    // 1. Mettre à jour l'input slider et le remplissage de la barre
    const slider = document.getElementById('ts-range-slider');
    if (slider) {
        slider.value = String(idx);
        const pct = (idx / (state.data.steps.length - 1)) * 100;
        slider.style.background = `linear-gradient(to right, #0284c7 ${pct}%, rgba(255, 255, 255, 0.1) ${pct}%)`;
    }

    // 2. Mettre à jour les indicateurs textuels et badges
    const lblCur = document.getElementById('ts-label-current');
    if (lblCur) {
        const hh = Math.floor(step.minute / 60);
        const mm = step.minute % 60;
        lblCur.textContent = `T = ${String(hh).padStart(2, '0')}h ${String(mm).padStart(2, '0')}m`;
    }

    const valOutflow = document.getElementById('ts-val-outflow');
    if (valOutflow) valOutflow.textContent = `${(step.outflow_m3s || 0).toFixed(3)} m³/s`;

    const valSurcharges = document.getElementById('ts-val-surcharges');
    if (valSurcharges) valSurcharges.textContent = `${step.surcharged_pipes_count || 0} tronçon${step.surcharged_pipes_count > 1 ? 's' : ''}`;

    const valDebord = document.getElementById('ts-val-debordements');
    if (valDebord) valDebord.textContent = `${step.flooded_nodes_count || 0} regard${step.flooded_nodes_count > 1 ? 's' : ''}`;

    // 3. Mettre à jour les couleurs des conduites sur la carte Leaflet
    _appliquerCouleursConduites(step.links);

    // 4. Mettre à jour les regards débordants avec effet radar
    _appliquerRegardsDebordants(step.flooded_nodes);

    // 5. Redessiner la ligne de repère sur le mini-hydrogramme
    if (state.chartInstance) {
        state.chartInstance.draw();
    }
}
