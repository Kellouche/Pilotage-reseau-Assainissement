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
        isDragging: false,
        playing: false,
        currentStep: 0,
        intervalId: null,
        baseIntervalMs: 500
    };

    /**
     * Bascule l'affichage du panneau Hyétogramme ↔ Hydrogramme
     */
    window.toggleHyetoHydroPanel = function() {
        const panel = document.getElementById('panel-hyeto-hydro');
        if (!panel) return;

        const btn = document.getElementById('btn-hyeto-hydro');
        if (btn && btn.disabled) {
            alert("Aucune simulation disponible pour ce réseau. Veuillez d'abord lancer une simulation SWMM 5.2.");
            return;
        }

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
        window.hyetoHydroState.currentStep = 0;
        panel.style.display = 'flex';

        if (btn) btn.classList.add('active');

        // Mettre à jour le texte du bouton selon le type de simulation
        const meta = (window._dernierResultatSimulation && window._dernierResultatSimulation.meta) || {};
        const kpis = (window._dernierResultatSimulation && window._dernierResultatSimulation.kpis) || {};
        const bmsInfo = meta.bms_info || kpis.bms_info;
        const btnLabel = document.getElementById('label-hyeto-fiche');
        const btnFiche = document.getElementById('btn-hyeto-bms-mission');
        if (bmsInfo) {
            if (btnLabel) btnLabel.textContent = 'Ordre de mission';
            if (btnFiche) {
                btnFiche.title = 'Télécharger l\'ordre de mission terrain BMS (PDF)';
                btnFiche.style.background = 'rgba(239, 68, 68, 0.2)';
                btnFiche.style.borderColor = 'rgba(239, 68, 68, 0.6)';
                btnFiche.style.color = '#fca5a5';
            }
        } else {
            if (btnLabel) btnLabel.textContent = 'Fiche de synthèse';
            if (btnFiche) {
                btnFiche.title = 'Afficher la fiche de synthèse hydrologique';
                btnFiche.style.background = 'rgba(56, 189, 248, 0.2)';
                btnFiche.style.borderColor = 'rgba(56, 189, 248, 0.6)';
                btnFiche.style.color = '#38bdf8';
            }
        }

        // Initialiser le système draggable si ce n'est pas déjà fait
        _initHyetoHydroDraggable();

        // Mettre à jour les badges de KPIs hydrologiques
        _mettreAJourBadgesHyeto(tsData);

        // Initialiser ou actualiser le graphique Chart.js
        _initialiserChartHyetoHydro(tsData);

        // Initialiser l'indicateur de temps avec le premier pas
        const ind = document.getElementById('hyeto-indicator-current-time');
        if (ind && tsData.steps && tsData.steps[0]) {
            const step0 = tsData.steps[0];
            ind.innerHTML = `Temps courant : <b>T = ${step0.time_str}</b> (pluie : <b>${(step0.rainfall_mmh || 0).toFixed(1)} mm/h</b> &bull; débit : <b>${(step0.outflow_m3s || 0).toFixed(3)} m³/s</b>)`;
        }
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
     * Gère l'action du bouton "Fiche terrain" selon le type de simulation :
     * - BMS (Bulletin Météo Spécial) : télécharge l'ordre de mission terrain PDF
     * - Pluie réglementaire (Montana/Chicago) : affiche la fiche de synthèse hydrologique
     */
    window.gererActionFicheTerrain = function() {
        const meta = (window._dernierResultatSimulation && window._dernierResultatSimulation.meta) || {};
        const kpis = (window._dernierResultatSimulation && window._dernierResultatSimulation.kpis) || {};
        const bmsInfo = meta.bms_info || kpis.bms_info;

        if (bmsInfo) {
            // Cas BMS : télécharger l'ordre de mission terrain
            window.telechargerOrdreMissionTerrain();
        } else {
            // Cas pluie réglementaire : afficher la fiche de synthèse hydrologique
            _afficherFicheSyntheseHydrologique();
        }
    };

    /**
     * Affiche la fiche de synthèse hydrologique pour une simulation pluie réglementaire
     */
    function _afficherFicheSyntheseHydrologique() {
        const meta = (window._dernierResultatSimulation && window._dernierResultatSimulation.meta) || {};
        const kpis = (window._dernierResultatSimulation && window._dernierResultatSimulation.kpis) || {};
        const ts = (window._dernierResultatSimulation && window._dernierResultatSimulation.timeseries) || {};

        const surfaceHa = parseFloat(meta.total_area_ha || meta.surface_totale_ha || 0);
        const iMax = parseFloat(meta.pluvio_intensite_max_mmh || kpis.pluvio_intensite_max_mmh || ts.peak_rainfall_mmh || 0);
        const volumePluieMm = parseFloat(meta.pluvio_hauteur_totale_mm || kpis.pluvio_hauteur_totale_mm || ts.total_precipitation_mm || 0);
        const volumePluieM3 = Math.round(surfaceHa * volumePluieMm * 10.0) || ts.total_rain_volume_m3 || 0;
        const debitMax = parseFloat(kpis.peak_outflow_m3s || ts.peak_outflow_m3s || 0);
        const tempsReponse = parseInt(ts.lag_time_minutes || 0) || 0;
        const volumeEcoule = Math.round(ts.total_outflow_volume_m3 || 0);
        const ceff = ts.runoff_coefficient !== undefined ? Math.round(ts.runoff_coefficient * 100) : 0;

        let interpretation = "";
        if (ceff >= 60) {
            interpretation = "Bassin très réactif • Temps de concentration très court";
        } else if (ceff >= 30) {
            interpretation = "Bassin modérément réactif • Temps de concentration court";
        } else if (ceff >= 10) {
            interpretation = "Bassin faiblement réactif • Temps de concentration modéré";
        } else {
            interpretation = "Bassin peu réactif • Temps de concentration long";
        }

        const html = `
        <div style="background: rgba(15, 23, 42, 0.95); border: 1.5px solid #38bdf8; border-radius: 10px; padding: 16px; max-width: 500px; margin: 20px auto; color: #f8fafc; font-family: 'Inter', sans-serif;">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                <i class="fas fa-file-alt" style="color: #38bdf8; font-size: 1.2rem;"></i>
                <h2 style="margin: 0; font-size: 1.1rem; color: #f8fafc;">Fiche de synthèse hydrologique</h2>
            </div>
            <hr style="border: 0; border-top: 1px solid #334155; margin: 8px 0;">
            
            <div style="margin-bottom: 10px;">
                <div style="font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 3px;">SYNTHÈSE HYDROLOGIQUE</div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; font-size: 0.85rem;">
                    <div><b>Surface drainée :</b> ${surfaceHa.toLocaleString('fr-FR')} ha</div>
                    <div><b>Pluie :</b></div>
                    <div style="margin-left: 16px;">• Intensité max : ${iMax.toFixed(1)} mm/h</div>
                    <div style="margin-left: 16px;">• Volume : ${volumePluieM3.toLocaleString('fr-FR')} m³</div>
                    <div><b>Réponse :</b></div>
                    <div style="margin-left: 16px;">• Débit max : ${debitMax.toFixed(3)} m³/s</div>
                    <div style="margin-left: 16px;">• Temps de réponse : ${tempsReponse} min</div>
                    <div style="margin-left: 16px;">• Volume écoulé : ${volumeEcoule.toLocaleString('fr-FR')} m³</div>
                    <div><b>Interprétation :</b></div>
                    <div style="margin-left: 16px;">• Ceff = ${ceff} %</div>
                    <div style="margin-left: 16px;">• ${interpretation}</div>
                </div>
            </div>
            
            <div style="text-align: right; margin-top: 12px;">
                <button onclick="this.closest('.fiche-synthese-modal').remove()" style="background: #38bdf8; color: #0f172a; border: none; padding: 6px 16px; border-radius: 5px; font-weight: 700; cursor: pointer;">Fermer</button>
            </div>
        </div>
        `;

        const modal = document.createElement('div');
        modal.className = 'fiche-synthese-modal';
        modal.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 9999;';
        modal.innerHTML = html;
        document.body.appendChild(modal);

        // Fermer sur clic outside le contenu
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.remove();
        });
    };

    /**
     * Ferme le panneau
     */
    window.fermerHyetoHydroPanel = function() {
        const panel = document.getElementById('panel-hyeto-hydro');
        const btn = document.getElementById('btn-hyeto-hydro');
        if (panel) panel.style.display = 'none';
        if (btn) btn.classList.remove('active');
        window.hyetoHydroState.visible = false;

        // Arrêter l'animation locale
        _hyetoPause();

        // Restaurer la coloration standard SWMM de la simulation
        if (window._dernierResultatSimulation && typeof afficherResultatsSimulation === 'function') {
            afficherResultatsSimulation(window._dernierResultatSimulation);
        }
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

        // Prise en compte du contexte d'alerte météo BMS
        const meta = (window._dernierResultatSimulation && window._dernierResultatSimulation.meta) || {};
        const kpis = (window._dernierResultatSimulation && window._dernierResultatSimulation.kpis) || {};
        const bmsInfo = meta.bms_info || kpis.bms_info;
        const legendRainText = document.getElementById('hyeto-legend-rain-text');
        if (legendRainText) {
            if (bmsInfo) {
                const vig = (bmsInfo.vigilance || 'orange').toUpperCase();
                const sym = bmsInfo.symbole || (vig === 'ROUGE' ? '🔴' : (vig === 'JAUNE' ? '🟡' : '🟠'));
                legendRainText.innerHTML = `<b>Hyétogramme de pluie</b> (barres descendantes, mm/h) — ${sym} Sollicitation BMS ONM (${vig}, ${bmsInfo.cumul_mm || 30} mm sur ${bmsInfo.duree_heures || 14} h)`;
            } else {
                legendRainText.innerHTML = `<b>Hyétogramme de pluie</b> (barres descendantes, mm/h) — sollicitation Chicago / Montana`;
            }
        }
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

        // Plugin curseur vertical orange autonome
        const verticalCursorPlugin = {
            id: 'hyetoHydroVerticalCursor',
            afterDraw: (chart) => {
                const stepIdx = window.hyetoHydroState.currentStep || 0;
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
                        label: 'Précipitation (mm/h) — hyétogramme',
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
                        label: 'Débit à l\'exutoire (m³/s) — hydrogramme',
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
                window.hyetoHydroState.currentStep = stepIndex;
                window.hyetoHydroState.chartInstance.draw();
                const step = (window.hyetoHydroState.data && window.hyetoHydroState.data.steps && window.hyetoHydroState.data.steps[stepIndex]) || null;
                const ind = document.getElementById('hyeto-indicator-current-time');
                if (ind && step) {
                    ind.innerHTML = `Temps courant : <b>T = ${step.time_str}</b> (pluie : <b>${(step.rainfall_mmh || 0).toFixed(1)} mm/h</b> &bull; débit : <b>${(step.outflow_m3s || 0).toFixed(3)} m³/s</b>)`;
                }
            }
        };
    }

    /**
     * Parcourt récursivement toutes les entités Leaflet d'un groupe ou d'un L.GeoJSON
     */
    function _itererEntitesLeaflet(group, fn) {
        if (!group) return;
        if (typeof group.eachLayer !== 'function') return;

        group.eachLayer(layer => {
            if (layer.feature && layer.feature.properties) {
                fn(layer);
            } else if (typeof layer.eachLayer === 'function') {
                _itererEntitesLeaflet(layer, fn);
            }
        });
    }

    /**
     * Applique la coloration dynamique instantanée aux conduites de la carte
     */
    function _appliquerCouleursConduites(activeLinks) {
        if (!window.couches) return;
        activeLinks = activeLinks || {};

        // Indexation inverse des conduites u->d vers link_id (depuis la simulation SWMM)
        const cRes = (window._dernierResultatSimulation && window._dernierResultatSimulation.conduit_results) || {};
        const linkIdByNodes = {};
        Object.values(cRes).forEach(r => {
            const u = String(r.u_node || '').replace(/\.0$/, '').trim();
            const d = String(r.d_node || '').replace(/\.0$/, '').trim();
            if (u && d && r.link_id) {
                linkIdByNodes[`${u}->${d}`] = r.link_id;
                linkIdByNodes[`${d}->${u}`] = r.link_id;
            }
        });

        const traiterConduite = (layer) => {
            const p = layer.feature.properties;
            const u = String(p.ID_AMONT || p.id_amont || '').replace(/\.0$/, '').trim();
            const d = String(p.ID_AVAL || p.id_aval || '').replace(/\.0$/, '').trim();

            // Trouver le link_id SWMM correspondant
            const lid = linkIdByNodes[`${u}->${d}`] || p.cid;
            let linkRatio = 0.0;
            if (lid && activeLinks[lid] !== undefined) {
                linkRatio = activeLinks[lid];
            } else if (p.cid && activeLinks[p.cid] !== undefined) {
                linkRatio = activeLinks[p.cid];
            }

            // Palette hydraulique fixe et nette selon le taux de charge instantané
            let col = '#10b981'; // < 50% Sain (Vert/Cyan)
            let weight = 3.5;

            if (linkRatio >= 1.0) {
                col = '#dc2626'; // Rouge brique : Surcharge complète / sous pression
                weight = 6.0;
            } else if (linkRatio >= 0.8) {
                col = '#f97316'; // Orange vif : En charge (> 80%)
                weight = 5.0;
            } else if (linkRatio >= 0.5) {
                col = '#f59e0b'; // Jaune ambré : Modéré (50% - 80%)
                weight = 4.2;
            }

            if (typeof layer.setStyle === 'function') {
                layer.setStyle({
                    color: col,
                    weight: weight,
                    opacity: 0.95
                });
            }
        };

        // Parcourir à la fois la couche de résultat SWMM et la couche physique de base
        if (window.couches.res_conduites) {
            _itererEntitesLeaflet(window.couches.res_conduites, traiterConduite);
        }
        if (window.couches.conduites) {
            _itererEntitesLeaflet(window.couches.conduites, traiterConduite);
        }
    }

    /**
     * Colorie nettement les regards selon leur état instantané à l'instant t
     */
    function _appliquerRegardsDebordants(floodedNodeIds) {
        if (!window.couches) return;
        const floodedSet = new Set((floodedNodeIds || []).map(String));

        const traiterRegard = (layer) => {
            const p = layer.feature.properties;
            const rawCode = p.Code !== undefined ? p.Code : (p.code !== undefined ? p.code : (p.CODE || p.id || ''));
            const nid = String(rawCode).replace(/\.0$/, '').trim();

            if (typeof layer.setStyle !== 'function') return;

            if (floodedSet.has(nid)) {
                // Regard en débordement actif au sol à cet instant (Rouge brique net et fixe)
                layer.setStyle({
                    radius: 7.0,
                    fillColor: '#dc2626',
                    color: '#ffffff',
                    weight: 2.0,
                    fillOpacity: 1.0
                });
                if (layer.getTooltip && layer.getTooltip()) {
                    layer.setTooltipContent(`⚠️ <b>Regard ${nid}</b> : DÉBORDEMENT ACTIF AU SOL`);
                }
            } else {
                // Regard sous contrôle (Bleu cyan discret)
                layer.setStyle({
                    radius: 4.5,
                    fillColor: '#38bdf8',
                    color: '#0f172a',
                    weight: 1.0,
                    fillOpacity: 0.8
                });
                if (layer.getTooltip && layer.getTooltip()) {
                    layer.setTooltipContent(`Regard ${nid}`);
                }
            }
        };

        // Parcourir à la fois la couche de regards SWMM et la couche de base
        if (window.couches.res_regards) {
            _itererEntitesLeaflet(window.couches.res_regards, traiterRegard);
        }
        if (window.couches.regards) {
            _itererEntitesLeaflet(window.couches.regards, traiterRegard);
        }
    }

    /**
     * Synchronise l'icône et le label du bouton "Animer" avec l'état de lecture
     */
    function _syncHyetoPlayButton() {
        const state = window.hyetoHydroState;
        if (!state) return;

        const icon = document.getElementById('icon-hyeto-play');
        const label = document.getElementById('label-hyeto-play');
        if (!icon || !label) return;

        if (state.playing) {
            icon.className = 'fas fa-pause';
            label.textContent = 'Pause';
        } else {
            icon.className = 'fas fa-play';
            label.textContent = 'Animer';
        }
    }

    /**
     * Lance l'animation du panneau Hyétogramme (autonome)
     */
    function _hyetoPlay() {
        const state = window.hyetoHydroState;
        if (state.playing || !state.data || !state.data.steps) return;

        state.playing = true;
        _syncHyetoPlayButton();

        const interval = state.baseIntervalMs;

        state.intervalId = setInterval(() => {
            let nextIdx = state.currentStep + 1;
            if (nextIdx >= state.data.steps.length) {
                nextIdx = 0;
            }
            state.currentStep = nextIdx;

            const step = state.data.steps[nextIdx];

            // Mettre à jour la carte directement (sans time slider)
            if (step.links) {
                _appliquerCouleursConduites(step.links);
            }
            if (step.flooded_nodes) {
                _appliquerRegardsDebordants(step.flooded_nodes);
            }

            // Rafraîchir le curseur vertical et l'indicateur
            if (state.chartInstance) {
                state.chartInstance.draw();
                const ind = document.getElementById('hyeto-indicator-current-time');
                if (ind && step) {
                    ind.innerHTML = `Temps courant : <b>T = ${step.time_str}</b> (pluie : <b>${(step.rainfall_mmh || 0).toFixed(1)} mm/h</b> &bull; débit : <b>${(step.outflow_m3s || 0).toFixed(3)} m³/s</b>)`;
                }
            }
        }, interval);
    }

    /**
     * Suspend l'animation du panneau Hyétogramme
     */
    function _hyetoPause() {
        const state = window.hyetoHydroState;
        state.playing = false;

        if (state.intervalId) {
            clearInterval(state.intervalId);
            state.intervalId = null;
        }

        _syncHyetoPlayButton();
    }

    /**
     * Bascule lecture/pause du panneau Hyétogramme
     */
    window.hyetoTogglePlay = function() {
        const state = window.hyetoHydroState;
        if (state.playing) {
            _hyetoPause();
        } else {
            _hyetoPlay();
        }
    };

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

