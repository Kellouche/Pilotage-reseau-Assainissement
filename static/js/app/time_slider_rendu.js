/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-27
 * Date de modification : 2026-11-27
 * Objet : Rendu temporel : couleurs conduites/regards, radar debordement, controles play/pause/step/vitesse (extrait de static/js/app/time_slider.js)
 * ================================================================================
 */

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
 * Colorie nettement les regards selon leur état instantané à l'instant t :
 * - Rouge brique fixe si le regard déborde en surface (au sol)
 * - Bleu normal si le regard est sous contrôle
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
 * Rétablit le style d'origine des regards de simulation à la fermeture
 */
function _nettoyerRadarDebordement() {
    if (window._dernierResultatSimulation && typeof afficherResultatsSimulation === 'function') {
        afficherResultatsSimulation(window._dernierResultatSimulation);
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

    const interval = Math.max(40, Math.round(state.baseIntervalMs / (state.speedMultiplier || 1)));

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

// Export global sur window
window.toggleTimeSlider = toggleTimeSlider;
window.timeSliderTogglePlay = timeSliderTogglePlay;
window.timeSliderPlay = timeSliderPlay;
window.timeSliderPause = timeSliderPause;
window.timeSliderSeek = timeSliderSeek;
window.timeSliderStep = timeSliderStep;
window.timeSliderSetSpeed = timeSliderSetSpeed;

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

/**
 * Initialise le déplacement à la souris (Draggable) du panneau Time Slider
 */
function _initTimeSliderDraggable() {
    const panel = document.getElementById('panel-time-slider');
    const handle = document.getElementById('time-slider-drag-handle');
    if (!panel || !handle || panel._draggableInitDone) return;

    panel._draggableInitDone = true;
    let startX, startY, origX, origY;

    handle.addEventListener('mousedown', (e) => {
        if (e.target.closest('button') || e.target.closest('.badge-pill')) return;
        e.preventDefault();
        // L'utilisateur prend la main : on fige la position automatique
        panel.dataset.userMoved = '1';
        // Position VISUELLE réelle (le panneau est centré via
        // left:50% + transform:translateX(-50%) : offsetLeft ne
        // tient pas compte du transform et provoquait un saut).
        const parent = panel.offsetParent || document.body;
        const pRect = parent.getBoundingClientRect();
        const rect = panel.getBoundingClientRect();
        startX = e.clientX;
        startY = e.clientY;
        origX = rect.left - pRect.left + (parent.scrollLeft || 0);
        origY = rect.top - pRect.top + (parent.scrollTop || 0);
        panel.classList.add('is-dragging');

        // Bornage : le panneau reste entièrement visible dans le workspace.
        const maxX = pRect.width - rect.width;
        const maxY = pRect.height - rect.height;
        const clampX = (v) => Math.min(Math.max(v, Math.min(0, maxX)), Math.max(0, maxX));
        const clampY = (v) => Math.min(Math.max(v, Math.min(0, maxY)), Math.max(0, maxY));

        const onMouseMove = (ev) => {
            const dx = ev.clientX - startX;
            const dy = ev.clientY - startY;
            panel.style.left = `${clampX(origX + dx)}px`;
            panel.style.top = `${clampY(origY + dy)}px`;
            panel.style.right = 'auto';
            panel.style.bottom = 'auto';
            panel.style.transform = 'none';
        };

        const onMouseUp = () => {
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
            panel.classList.remove('is-dragging');
        };

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    });
}
