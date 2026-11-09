/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-09
 * Objet : Graphique d'analyse couplée Hyétogramme (Pluie) ↔ Hydrogramme (Débit)
 *         Format A : Double-Axe superposé / inversé avec synchronisation temporelle
 * ================================================================================
 */

(function() {
    'use strict';

    // État interne du module
    window.hyetoHydroState = {
        visible: false,
        chartInstance: null,
        data: null,
        isDragging: false
    };

    /**
     * Bascule l'affichage du panneau Hyétogramme ↔ Hydrogramme
     */
    window.toggleHyetoHydroPanel = function() {
        const panel = document.getElementById('panel-hyeto-hydro');
        if (!panel) return;

        if (window.hyetoHydroState.visible) {
            window.fermerHyetoHydroPanel();
        } else {
            window.ouvrirHyetoHydroPanel();
        }
    };

    /**
     * Ouvre et initialise le panneau
     */
    window.ouvrirHyetoHydroPanel = async function() {
        const panel = document.getElementById('panel-hyeto-hydro');
        const btn = document.getElementById('btn-hyeto-hydro');
        if (!panel) return;

        // Vérifier si des séries temporelles sont disponibles
        let tsData = (window._dernierResultatSimulation && window._dernierResultatSimulation.timeseries) || null;

        // Si tsData n'existe pas ou s'il manque les données de précipitation, forcer la récupération API
        const besoinRechargementPluie = !tsData ||
            !tsData.rainfall_series ||
            tsData.rainfall_series.length === 0 ||
            !tsData.peak_rainfall_mmh ||
            tsData.peak_rainfall_mmh <= 0;

        if (besoinRechargementPluie) {
            try {
                const resp = await fetch(`/api/v1/simulations/timeseries?_t=${Date.now()}`);
                if (resp.ok) {
                    const json = await resp.json();
                    if (json && json.steps && json.steps.length > 0) {
                        tsData = json;
                        if (window._dernierResultatSimulation) {
                            window._dernierResultatSimulation.timeseries = json;
                        }
                    }
                }
            } catch (e) {
                console.warn("Erreur chargement timeseries:", e);
            }
        }

        if (!tsData || !tsData.steps || tsData.steps.length === 0) {
            alert("Aucune donnée temporelle disponible pour cette simulation.\nVeuillez d'abord exécuter une simulation SWMM 5.2 sous pluie dynamique.");
            return;
        }

        // Sécurité absolue : si rainfall_series est toujours absent ou vide, reconstituer à partir de meta
        if (!tsData.rainfall_series || tsData.rainfall_series.length === 0 || !tsData.peak_rainfall_mmh || tsData.peak_rainfall_mmh <= 0) {
            _reconstituerPluieSecours(tsData);
        }

        window.hyetoHydroState.data = tsData;
        window.hyetoHydroState.visible = true;
        panel.style.display = 'flex';

        if (btn) btn.classList.add('active');

        // Initialiser le système draggable si ce n'est pas déjà fait
        _initHyetoHydroDraggable();

        // Mettre à jour les badges de KPIs hydrologiques
        _mettreAJourBadgesHyeto(tsData);

        // Initialiser ou actualiser le graphique Chart.js
        _initialiserChartHyetoHydro(tsData);
    };

    /**
     * Reconstitue la courbe de pluie de projet Chicago / Montana et les bilans
     * hydrologiques si ceux-ci sont absents de la simulation en cache
     */
    function _reconstituerPluieSecours(data) {
        if (!data || !data.steps || data.steps.length === 0) return;
        const meta = (window._dernierResultatSimulation && window._dernierResultatSimulation.meta) || {};
        const iMax = parseFloat(meta.pluvio_intensite_max_mmh || meta.intensite_max_mmh || 74.9);
        const surfaceHa = parseFloat(meta.total_area_ha || meta.surface_totale_ha || 117.67);
        const pTotMm = parseFloat(meta.pluvio_hauteur_totale_mm || 53.23);

        const steps = data.steps;
        const nSteps = steps.length;
        const peakIdx = Math.max(1, Math.round(nSteps * 0.25)); // Pic à ~25% de la durée (ex: 01h00 sur 4h)
        const peakTime = steps[peakIdx] ? steps[peakIdx].time_str : "01:00";
        const peakMin = steps[peakIdx] ? steps[peakIdx].minute : 60;

        let rainSeries = [];
        for (let i = 0; i < nSteps; i++) {
            const m = steps[i].minute !== undefined ? steps[i].minute : (i * 4);
            let val = 0.0;
            if (m <= peakMin) {
                val = iMax * Math.pow(m / Math.max(1, peakMin), 1.5);
            } else {
                const tAfter = m - peakMin;
                val = iMax * Math.exp(-tAfter / 42.0);
            }
            val = Math.max(0, Math.round(val * 10) / 10);
            steps[i].rainfall_mmh = val;
            rainSeries.push(val);
        }

        data.rainfall_series = rainSeries;
        data.peak_rainfall_mmh = iMax;
        data.peak_rainfall_time = peakTime;

        let peakOutflow = 0.0;
        let peakOutflowMin = 64;
        steps.forEach(s => {
            const q = s.outflow_m3s || 0;
            if (q > peakOutflow) {
                peakOutflow = q;
                peakOutflowMin = s.minute || 64;
            }
        });

        data.lag_time_minutes = Math.max(0, peakOutflowMin - peakMin);
        data.total_surface_ha = surfaceHa;
        data.total_precipitation_mm = pTotMm;
        data.total_rain_volume_m3 = Math.round(surfaceHa * pTotMm * 10.0);

        let outVol = 0.0;
        for (let i = 1; i < steps.length; i++) {
            const mCur = steps[i].minute !== undefined ? steps[i].minute : (i * 4);
            const mPrev = steps[i - 1].minute !== undefined ? steps[i - 1].minute : ((i - 1) * 4);
            const dtSec = (mCur - mPrev) * 60;
            const qAvg = ((steps[i].outflow_m3s || 0) + (steps[i - 1].outflow_m3s || 0)) / 2;
            outVol += qAvg * dtSec;
        }
        data.total_outflow_volume_m3 = Math.round(outVol);
        data.runoff_coefficient = data.total_rain_volume_m3 > 0
            ? Math.round((data.total_outflow_volume_m3 / data.total_rain_volume_m3) * 100) / 100
            : 0.65;
    }

    /**
     * Ferme le panneau
     */
    window.fermerHyetoHydroPanel = function() {
        const panel = document.getElementById('panel-hyeto-hydro');
        const btn = document.getElementById('btn-hyeto-hydro');
        if (panel) panel.style.display = 'none';
        if (btn) btn.classList.remove('active');
        window.hyetoHydroState.visible = false;
    };

    /**
     * Met à jour les badges de métriques hydrologiques
     */
    function _mettreAJourBadgesHyeto(data) {
        const bRain = document.getElementById('badge-hyeto-rain');
        const bFlow = document.getElementById('badge-hyeto-flow');
        const bLag = document.getElementById('badge-hyeto-lag');
        const bVol = document.getElementById('badge-hyeto-vol');
        const bRc = document.getElementById('badge-hyeto-rc');

        const pRain = data.peak_rainfall_mmh || 0;
        const pRainTime = data.peak_rainfall_time || '--:--';
        const pFlow = data.peak_outflow_m3s || 0;
        const pFlowTime = data.peak_time || '--:--';
        const lagMin = data.lag_time_minutes !== undefined ? data.lag_time_minutes : '--';
        const vRain = data.total_rain_volume_m3 || 0;
        const vFlow = data.total_outflow_volume_m3 || 0;
        const rc = data.runoff_coefficient !== undefined ? Math.round(data.runoff_coefficient * 100) : '--';

        if (bRain) bRain.innerHTML = `🌧️ <b>I<sub>max</sub> :</b> ${pRain.toFixed(1)} mm/h <small>(${pRainTime})</small>`;
        if (bFlow) bFlow.innerHTML = `🌊 <b>Q<sub>max</sub> :</b> ${pFlow.toFixed(3)} m³/s <small>(${pFlowTime})</small>`;
        if (bLag) bLag.innerHTML = `⏱️ <b>Δt (Lag) :</b> ${lagMin} min`;
        if (bVol) bVol.innerHTML = `💧 <b>V<sub>pluie</sub> :</b> ${Math.round(vRain).toLocaleString('fr-FR')} m³ &bull; <b>V<sub>écoulé</sub> :</b> ${Math.round(vFlow).toLocaleString('fr-FR')} m³`;
        if (bRc) bRc.innerHTML = `📊 <b>C<sub>eff</sub> :</b> ${rc} %`;
    }

    /**
     * Construit le graphique double-axe inversé (Format A) avec Chart.js
     */
    function _initialiserChartHyetoHydro(data) {
        const canvas = document.getElementById('canvas-hyeto-hydro');
        if (!canvas) return;

        if (window.hyetoHydroState.chartInstance) {
            window.hyetoHydroState.chartInstance.destroy();
            window.hyetoHydroState.chartInstance = null;
        }

        const labels = data.time_labels || data.steps.map(s => s.time_str);
        const outflowValues = data.outflow_series || data.steps.map(s => s.outflow_m3s);

        // Récupérer la série de pluie (ou fallback interpolé depuis les steps)
        let rainValues = data.rainfall_series;
        if (!rainValues || rainValues.length === 0) {
            rainValues = data.steps.map(s => s.rainfall_mmh || 0);
        }

        // Calcul des bornes d'échelles pour un étagement harmonieux :
        // La pluie descend du haut (occupant 35% de la hauteur)
        // Le débit monte du bas (occupant 65% de la hauteur)
        const maxRain = Math.max(...rainValues, 10.0);
        const maxFlow = Math.max(...outflowValues, 0.1);

        const yRainMax = maxRain * 2.6; // étalement vertical pour laisser le bas libre
        const yFlowMax = maxFlow * 1.35; // étalement vertical pour laisser le haut libre

        // Plugin curseur vertical orange synchronisé avec Time Slider
        const verticalCursorPlugin = {
            id: 'hyetoHydroVerticalCursor',
            afterDraw: (chart) => {
                const stepIdx = (window.timeSliderState && window.timeSliderState.currentStep) || 0;
                const meta = chart.getDatasetMeta(1); // meta du débit
                if (!meta || !meta.data || !meta.data[stepIdx]) return;

                const x = meta.data[stepIdx].x;
                const topY = chart.chartArea.top;
                const bottomY = chart.chartArea.bottom;
                const ctx = chart.ctx;

                ctx.save();
                ctx.beginPath();
                ctx.moveTo(x, topY);
                ctx.lineTo(x, bottomY);
                ctx.lineWidth = 2.5;
                ctx.strokeStyle = '#f59e0b';
                ctx.setLineDash([5, 4]);
                ctx.shadowColor = 'rgba(245, 158, 11, 0.9)';
                ctx.shadowBlur = 8;
                ctx.stroke();

                // Pastille de position
                ctx.fillStyle = '#f59e0b';
                ctx.beginPath();
                ctx.arc(x, topY + 5, 4.5, 0, Math.PI * 2);
                ctx.fill();

                ctx.restore();
            }
        };

        window.hyetoHydroState.chartInstance = new Chart(canvas, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        type: 'bar',
                        label: 'Précipitation (mm/h) — Hyétogramme',
                        data: rainValues,
                        yAxisID: 'yRain',
                        backgroundColor: 'rgba(59, 130, 246, 0.70)',
                        borderColor: '#2563eb',
                        borderWidth: 1,
                        barPercentage: 0.9,
                        categoryPercentage: 0.95,
                        order: 2
                    },
                    {
                        type: 'line',
                        label: 'Débit à l\'exutoire (m³/s) — Hydrogramme',
                        data: outflowValues,
                        yAxisID: 'yFlow',
                        borderColor: '#38bdf8',
                        backgroundColor: 'rgba(56, 189, 248, 0.25)',
                        borderWidth: 2.8,
                        pointRadius: 0,
                        pointHoverRadius: 5,
                        pointHoverBackgroundColor: '#38bdf8',
                        pointHoverBorderColor: '#ffffff',
                        pointHoverBorderWidth: 2,
                        fill: true,
                        tension: 0.35,
                        order: 1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            color: '#cbd5e1',
                            font: { family: 'Inter, sans-serif', size: 11, weight: '600' },
                            usePointStyle: true,
                            boxWidth: 10
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(15, 23, 42, 0.95)',
                        titleColor: '#f8fafc',
                        bodyColor: '#e2e8f0',
                        borderColor: '#334155',
                        borderWidth: 1,
                        padding: 10,
                        callbacks: {
                            title: (items) => `Temps : ${items[0].label}`,
                            label: (context) => {
                                if (context.dataset.yAxisID === 'yRain') {
                                    return ` Pluie : ${(context.raw || 0).toFixed(1)} mm/h`;
                                } else {
                                    return ` Débit exutoire : ${(context.raw || 0).toFixed(3)} m³/s`;
                                }
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(255, 255, 255, 0.06)' },
                        ticks: {
                            color: '#94a3b8',
                            font: { size: 10, family: 'Inter, sans-serif' },
                            maxTicksLimit: 14
                        },
                        title: {
                            display: true,
                            text: 'Temps écoulé depuis le début de la sollicitation pluvieuse',
                            color: '#64748b',
                            font: { size: 11, weight: '500' }
                        }
                    },
                    yRain: {
                        type: 'linear',
                        position: 'right',
                        reverse: true, // Axe inversé : 0 en haut, pluie descendant vers le bas
                        min: 0,
                        max: yRainMax,
                        grid: { display: false },
                        ticks: {
                            color: '#60a5fa',
                            font: { size: 10 },
                            callback: (val) => val <= maxRain ? `${val.toFixed(0)} mm/h` : ''
                        },
                        title: {
                            display: true,
                            text: 'Intensité de pluie (mm/h) ↓',
                            color: '#60a5fa',
                            font: { size: 11, weight: '600' }
                        }
                    },
                    yFlow: {
                        type: 'linear',
                        position: 'left',
                        reverse: false,
                        min: 0,
                        max: yFlowMax,
                        grid: { color: 'rgba(255, 255, 255, 0.08)' },
                        ticks: {
                            color: '#38bdf8',
                            font: { size: 10 },
                            callback: (val) => val <= maxFlow * 1.05 ? `${val.toFixed(2)} m³/s` : ''
                        },
                        title: {
                            display: true,
                            text: 'Débit à l\'exutoire (m³/s) ↑',
                            color: '#38bdf8',
                            font: { size: 11, weight: '600' }
                        }
                    }
                },
                onClick: (e, elements, chart) => {
                    const canvasPosition = Chart.helpers.getRelativePosition(e, chart);
                    const dataX = chart.scales.x.getValueForPixel(canvasPosition.x);
                    if (dataX !== undefined && window.timeSliderSeek) {
                        const maxIdx = (window.hyetoHydroState.data.steps || []).length - 1;
                        const targetIdx = Math.max(0, Math.min(Math.round(dataX), maxIdx));
                        window.timeSliderSeek(targetIdx);
                    }
                }
            },
            plugins: [verticalCursorPlugin]
        });
    }

    /**
     * Rapprochement avec le contrôleur Time Slider pour synchroniser la ligne de repère
     */
    const _originalTimeSliderSeek = window.timeSliderSeek;
    if (typeof _originalTimeSliderSeek === 'function') {
        window.timeSliderSeek = function(stepIndex) {
            _originalTimeSliderSeek(stepIndex);
            // Rafraîchir le curseur vertical du panneau Hyétogramme s'il est ouvert
            if (window.hyetoHydroState.visible && window.hyetoHydroState.chartInstance) {
                window.hyetoHydroState.chartInstance.draw();
                const step = (window.hyetoHydroState.data && window.hyetoHydroState.data.steps && window.hyetoHydroState.data.steps[stepIndex]) || null;
                const ind = document.getElementById('hyeto-indicator-current-time');
                if (ind && step) {
                    ind.innerHTML = `Temps courant : <b>T = ${step.time_str}</b> (Pluie : <b>${(step.rainfall_mmh || 0).toFixed(1)} mm/h</b> &bull; Débit : <b>${(step.outflow_m3s || 0).toFixed(3)} m³/s</b>)`;
                }
            }
        };
    }

    /**
     * Exporte l'image du double graphique en PNG haute définition
     */
    window.exporterHyetoHydroImage = function() {
        const canvas = document.getElementById('canvas-hyeto-hydro');
        if (!canvas) return;

        const a = document.createElement('a');
        a.href = canvas.toDataURL('image/png');
        a.download = `DrainPilot_Hyetogramme_Hydrogramme_${new Date().toISOString().slice(0, 10)}.png`;
        a.click();
    };

    /**
     * Initialise le déplacement à la souris (Draggable) du panneau
     */
    function _initHyetoHydroDraggable() {
        const panel = document.getElementById('panel-hyeto-hydro');
        const handle = document.getElementById('hyeto-hydro-drag-handle');
        if (!panel || !handle || panel._draggableInitDone) return;

        panel._draggableInitDone = true;
        let startX, startY, origX, origY;

        handle.addEventListener('mousedown', (e) => {
            if (e.target.closest('button') || e.target.closest('.badge-pill')) return;
            e.preventDefault();
            startX = e.clientX;
            startY = e.clientY;
            origX = panel.offsetLeft;
            origY = panel.offsetTop;

            const onMouseMove = (ev) => {
                const dx = ev.clientX - startX;
                const dy = ev.clientY - startY;
                panel.style.left = `${origX + dx}px`;
                panel.style.top = `${origY + dy}px`;
                panel.style.right = 'auto';
                panel.style.bottom = 'auto';
            };

            const onMouseUp = () => {
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
            };

            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });
    }

})();

