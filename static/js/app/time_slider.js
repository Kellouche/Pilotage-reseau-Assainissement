/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-09
 * Objet : Animation temporelle de l'onde de crue (Time Slider - Phase 6.B)
 * ================================================================================
 */

window.timeSliderState = {
    active: false,
    playing: false,
    currentStep: 0,
    speedMultiplier: 1,
    baseIntervalMs: 800,
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
 * Bascule l'affichage du contrôleur Time Slider
 */
function toggleTimeSlider(forceState) {
    const state = window.timeSliderState;
    const panel = document.getElementById('panel-time-slider');
    const btn = document.getElementById('btn-time-slider');
    const newState = (forceState !== undefined) ? forceState : !state.active;

    if (!newState) {
        // Arrêter et fermer
        timeSliderPause();
        state.active = false;
        if (panel) panel.style.display = 'none';
        if (btn) btn.classList.remove('active');

        // Nettoyer les marqueurs de débordement radar
        _nettoyerRadarDebordement();

        // Rétablir la coloration standard SWMM de la simulation
        if (window._dernierResultatSimulation && typeof afficherResultatsSimulation === 'function') {
            afficherResultatsSimulation(window._dernierResultatSimulation);
        }
        return;
    }

    // VÉRIFICATION : Une simulation doit avoir été effectuée
    const hasSim = !!(window._dernierResultatSimulation &&
                      window._dernierResultatSimulation.conduit_results &&
                      Object.keys(window._dernierResultatSimulation.conduit_results).length > 0);

    if (!hasSim) {
        alert("Lancer une simulation pour activer l'animation temporelle de l'onde de crue.");
        return;
    }

    // Charger les séries temporelles
    chargerDonneesTimeSlider().then(success => {
        if (!success) return;

        state.active = true;
        if (panel) panel.style.display = 'flex';
        if (btn) btn.classList.add('active');

        // Initialiser ou réinitialiser le contrôleur
        _initTimeSliderUI();
        timeSliderSeek(0);
    });
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
        return true;
    }

    // 2. Appel de l'endpoint dédié
    const badge = document.getElementById('badge-time-status');
    if (badge) {
        badge.textContent = "Chargement...";
        badge.className = "badge-ts badge-info";
    }

    try {
        const resp = await fetch('/api/v1/simulations/timeseries');
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `Erreur serveur (${resp.status})`);
        }
        const data = await resp.json();
        if (!data || !data.steps || data.steps.length === 0) {
            throw new Error("Aucun pas temporel disponible dans la simulation.");
        }
        state.data = data;
        if (window._dernierResultatSimulation) {
            window._dernierResultatSimulation.timeseries = data;
        }
        return true;
    } catch (err) {
        console.error("Erreur chargement séries temporelles:", err);
        alert(`Impossible d'initialiser l'animation temporelle :\n${err.message}`);
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

/**
 * Applique la coloration dynamique instantanée aux conduites de la carte
 */
function _appliquerCouleursConduites(activeLinks) {
    if (!window.couches || !window.couches.res_conduites) return;
    activeLinks = activeLinks || {};

    window.couches.res_conduites.eachLayer(layer => {
        if (!layer.feature || !layer.feature.properties) return;
        const p = layer.feature.properties;
        const u = String(p.ID_AMONT || p.id_amont || '').replace(/\.0$/, '').trim();
        const d = String(p.ID_AVAL || p.id_aval || '').replace(/\.0$/, '').trim();

        // Récupérer le link_id ou chercher par extrémités
        let linkRatio = 0.0;
        if (activeLinks[p.cid]) {
            linkRatio = activeLinks[p.cid];
        } else {
            // Chercher par clé de conduite
            for (const [k, ratio] of Object.entries(activeLinks)) {
                if (k.includes(`${u}`) && k.includes(`${d}`)) {
                    linkRatio = ratio;
                    break;
                }
            }
        }

        // Palette hydraulique selon le taux de charge Q/Qmax à cet instant
        let col = '#10b981'; // < 50% Sain (Vert/Cyan)
        let weight = 4.0;

        if (linkRatio >= 1.0) {
            col = '#8b5cf6'; // Violet : Surpression / saturation complète
            weight = 6.5;
        } else if (linkRatio >= 0.8) {
            col = '#ef4444'; // Rouge vif : En charge (> 80%)
            weight = 5.5;
        } else if (linkRatio >= 0.5) {
            col = '#f59e0b'; // Orange : Modéré (50% - 80%)
            weight = 4.5;
        }

        layer.setStyle({
            color: col,
            weight: weight,
            opacity: 0.95
        });
    });
}

/**
 * Marque les regards débordants à l'instant t avec pulsation radar
 */
function _appliquerRegardsDebordants(floodedNodeIds) {
    const map = _getCarteTS();
    if (!map) return;

    _nettoyerRadarDebordement();

    if (!floodedNodeIds || floodedNodeIds.length === 0) return;

    window.timeSliderState.radarGroup = L.layerGroup().addTo(map);
    const floodedSet = new Set(floodedNodeIds.map(String));

    // Chercher les coordonnées des regards débordants dans _rawNetworkData
    if (window._rawNetworkData && window._rawNetworkData.couches && window._rawNetworkData.couches.regards) {
        const geo = window._rawNetworkData.couches.regards;
        const features = geo.features || [];

        features.forEach(f => {
            const p = f.properties || {};
            const rawCode = p.Code !== undefined ? p.Code : (p.code !== undefined ? p.code : (p.CODE || p.id || ''));
            const nid = String(rawCode).replace(/\.0$/, '').trim();

            if (floodedSet.has(nid) && f.geometry && f.geometry.coordinates) {
                const coords = f.geometry.coordinates;
                const latlng = L.latLng(coords[1], coords[0]);

                const marker = L.circleMarker(latlng, {
                    radius: 9,
                    className: 'debordement-radar-marker',
                    color: '#ffffff',
                    fillColor: '#ef4444',
                    fillOpacity: 0.95,
                    weight: 2
                }).bindTooltip(`⚠️ <b>Regard ${nid}</b> en débordement actif`, { direction: 'top' });

                window.timeSliderState.radarGroup.addLayer(marker);
            }
        });
    }
}

/**
 * Nettoie le groupe Leaflet des marqueurs radar
 */
function _nettoyerRadarDebordement() {
    const state = window.timeSliderState;
    if (state.radarGroup) {
        state.radarGroup.clearLayers();
        const map = _getCarteTS();
        if (map && map.hasLayer(state.radarGroup)) {
            map.removeLayer(state.radarGroup);
        }
        state.radarGroup = null;
    }
}

/**
 * Démarre ou suspend la lecture continue
 */
function timeSliderTogglePlay() {
    const state = window.timeSliderState;
    if (state.playing) {
        timeSliderPause();
    } else {
        timeSliderPlay();
    }
}

/**
 * Lance la lecture
 */
function timeSliderPlay() {
    const state = window.timeSliderState;
    if (state.playing || !state.data || !state.data.steps) return;

    state.playing = true;

    // Mise à jour de l'icône et badge
    const icon = document.getElementById('ts-icon-play');
    if (icon) {
        icon.className = 'fas fa-pause';
    }
    const badge = document.getElementById('badge-time-status');
    if (badge) {
        badge.textContent = "Lecture ▶";
        badge.className = "badge-ts badge-play";
    }

    const interval = Math.max(150, Math.round(state.baseIntervalMs / state.speedMultiplier));

    state.intervalId = setInterval(() => {
        let nextIdx = state.currentStep + 1;
        if (nextIdx >= state.data.steps.length) {
            // Boucle ou pause à la fin
            nextIdx = 0;
        }
        timeSliderSeek(nextIdx);
    }, interval);
}

/**
 * Suspend la lecture
 */
function timeSliderPause() {
    const state = window.timeSliderState;
    state.playing = false;

    if (state.intervalId) {
        clearInterval(state.intervalId);
        state.intervalId = null;
    }

    const icon = document.getElementById('ts-icon-play');
    if (icon) {
        icon.className = 'fas fa-play';
    }
    const badge = document.getElementById('badge-time-status');
    if (badge) {
        badge.textContent = "Pause ⏸";
        badge.className = "badge-ts badge-info";
    }
}

/**
 * Avance ou recule d'un pas
 */
function timeSliderStep(delta) {
    timeSliderPause();
    const state = window.timeSliderState;
    if (!state.data || !state.data.steps) return;

    let target = state.currentStep + delta;
    if (target < 0) target = 0;
    if (target >= state.data.steps.length) target = state.data.steps.length - 1;

    timeSliderSeek(target);
}

/**
 * Règle la vitesse de lecture
 */
function timeSliderSetSpeed(multiplier) {
    const state = window.timeSliderState;
    state.speedMultiplier = parseFloat(multiplier) || 1;

    // Mise à jour des boutons vitesse
    document.querySelectorAll('.ts-btn-speed').forEach(b => {
        const s = parseFloat(b.getAttribute('data-speed'));
        if (s === state.speedMultiplier) {
            b.classList.add('active');
        } else {
            b.classList.remove('active');
        }
    });

    // Si en cours de lecture, relancer avec le nouvel intervalle
    if (state.playing) {
        timeSliderPause();
        timeSliderPlay();
    }
}

// Raccourci clavier : Barre d'espace pour Play/Pause
document.addEventListener('keydown', (e) => {
    if (window.timeSliderState && window.timeSliderState.active) {
        if (e.code === 'Space' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
            e.preventDefault();
            timeSliderTogglePlay();
        } else if (e.code === 'ArrowRight') {
            e.preventDefault();
            timeSliderStep(1);
        } else if (e.code === 'ArrowLeft') {
            e.preventDefault();
            timeSliderStep(-1);
        }
    }
});
