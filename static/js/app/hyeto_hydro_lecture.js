/**
 * ==============================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de creation : 2026-11-09
 * Date de modification : 2026-11-28
 * Objet : Hydrologique SWMM - lecture animee, coloration des cernes et export
 *         (extrait verbatim de hyeto_hydro.js, regle 600 lignes)
 * ==============================================================================
 */

// Lecture animee du jeu de resultats, synchronisation Time Slider,
// coloration dynamique des cernes et export d'image du graphique.
// L'etat partage reste window.hyetoHydroState (hyeto_hydro.js).
(function() {
    'use strict';

    /**
     * Rapprochement avec le contrôleur Time Slider pour synchroniser la ligne de repère
     */
    const _originalTimeSliderSeek = window.timeSliderSeek;
    if (typeof _originalTimeSliderSeek === 'function') {
        window.timeSliderSeek = function(stepIndex) {
            // La synchro du dataset (hyetoHydroState.data fait foi tant que
            // le panneau est ouvert) est assurée dans timeSliderSeek
            // lui-même — couvre aussi les appels internes du time slider.
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

            // Palette hydraulique identique à l'enveloppe de criticité statique :
            // bleu → vert → jaune → rouge selon la charge instantanée.
            let col = '#3b82f6'; // < 50% Normal (Bleu)
            let weight = 3.5;

            if (linkRatio >= 1.0) {
                col = '#ef4444'; // Rouge : Surcharge / mise en charge (≥ 100%)
                weight = 6.0;
            } else if (linkRatio >= 0.8) {
                col = '#eab308'; // Jaune : Critique (80% - 100%)
                weight = 5.0;
            } else if (linkRatio >= 0.5) {
                col = '#22c55e'; // Vert : Modéré (50% - 80%)
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
                // Regard sous contrôle (Bleu identique à la vue statique)
                layer.setStyle({
                    radius: 4.5,
                    fillColor: '#0284c7',
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

        const interval = Math.max(40, Math.round(state.baseIntervalMs / (state.speedMultiplier || 1)));

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
     * Règle la vitesse de lecture (1x, 2x, 5x)
     */
    window.hyetoHydroSetSpeed = function(multiplier) {
        const state = window.hyetoHydroState;
        state.speedMultiplier = parseFloat(multiplier) || 1;

        document.querySelectorAll('#panel-hyeto-hydro .ts-btn-speed').forEach(b => {
            const s = parseFloat(b.getAttribute('data-speed'));
            b.classList.toggle('active', s === state.speedMultiplier);
        });

        // Si l'animation tourne, relancer avec le nouvel intervalle
        if (state.playing) {
            _hyetoPause();
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

    // Pont vers le module principal : le panneau appelle ces deux
    // helpers a la fermeture / a l'ouverture (ex-closure privee).
    window._hyetoPause = _hyetoPause;
    window._initHyetoHydroDraggable = _initHyetoHydroDraggable;
})();
