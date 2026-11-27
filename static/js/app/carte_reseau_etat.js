/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-27
 * Date de modification : 2026-11-27
 * Objet : Etat bureau (sauvegarde/restauration par reseau) et desactivation boutons hydro (extrait de static/js/app/carte_reseau.js)
 * ================================================================================
 */

/**
 * Désactive les boutons d'animation et d'analyse hydrologique
 * si aucune simulation n'est disponible pour le réseau courant
 */
function _desactiverBoutonsHydro() {
    const btnTimeSlider = document.getElementById('btn-time-slider');
    const btnHyetoHydro = document.getElementById('btn-hyeto-hydro');

    // Vérifier si une simulation est disponible
    const hasSim = !!(window._dernierResultatSimulation &&
                      window._dernierResultatSimulation.conduit_results &&
                      Object.keys(window._dernierResultatSimulation.conduit_results).length > 0);

    // Désactiver visuellement et fonctionnellement
    if (btnTimeSlider) {
        btnTimeSlider.disabled = !hasSim;
        btnTimeSlider.style.opacity = hasSim ? '1' : '0.4';
        btnTimeSlider.style.cursor = hasSim ? 'pointer' : 'not-allowed';
        btnTimeSlider.title = hasSim ? 'Animation onde de crue (Time Slider)' : 'Aucune simulation disponible';
    }

    if (btnHyetoHydro) {
        btnHyetoHydro.disabled = !hasSim;
        btnHyetoHydro.style.opacity = hasSim ? '1' : '0.4';
        btnHyetoHydro.style.cursor = hasSim ? 'pointer' : 'not-allowed';
        btnHyetoHydro.title = hasSim ? 'Analyse pluie ↔ débit (hyétogramme et hydrogramme)' : 'Aucune simulation disponible';
    }
}

// Initialisation dès que le DOM est prêt
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDraggableToolbar);
} else {
    initDraggableToolbar();
}

// ==========================================
// GESTION DE L'ÉTAT DU BUREAU PAR RÉSEAU
// Sauvegarde/restauration des positions de panneaux,
// état de la toolbar, légende et badges.
// ==========================================

window.etatBureau = window.etatBureau || {};

/**
 * Sauvegarde l'état complet du bureau (positions, visibilité, toolbar, légende)
 * pour un réseau donné, avant nettoyage/changement.
 */
window.sauvegarderEtatBureau = function(reseauId) {
    if (!reseauId) return;

    const etat = {
        timestamp: Date.now(),
        panels: {},
        floatingLegend: null,
        toolbar: null
    };

    // Panneau hyéto-hydro
    const hyetoPanel = document.getElementById('panel-hyeto-hydro');
    if (hyetoPanel) {
        const r = hyetoPanel.getBoundingClientRect();
        etat.panels.hyetoHydro = {
            visible: hyetoPanel.style.display !== 'none',
            x: r.left, y: r.top, w: r.width, h: r.height
        };
    }

    // Panneau time slider
    const tsPanel = document.getElementById('panel-time-slider');
    if (tsPanel) {
        const r = tsPanel.getBoundingClientRect();
        etat.panels.timeSlider = {
            visible: tsPanel.style.display !== 'none',
            x: r.left, y: r.top, w: r.width, h: r.height
        };
    }

    // Panneau profil en long
    const plPanel = document.querySelector('.profil-long-container');
    if (plPanel) {
        const r = plPanel.getBoundingClientRect();
        etat.panels.profilLong = {
            visible: plPanel.style.display !== 'none',
            x: r.left, y: r.top, w: r.width, h: r.height
        };
    }

    // Toolbar d'édition
    const toolbar = document.getElementById('main-edit-toolbar');
    if (toolbar) {
        etat.toolbar = {
            visible: toolbar.style.display !== 'none',
            collapsed: toolbar.classList.contains('collapsed')
        };
    }

    // Légende flottante
    const leg = document.getElementById('sim-floating-legend');
    if (leg) {
        etat.floatingLegend = {
            visible: leg.classList.contains('active-legend') && leg.style.display !== 'none'
        };
    }

    window.etatBureau[reseauId] = etat;
};

/**
 * Restaure l'état du bureau (positions, visibilité, toolbar, légende)
 * pour un réseau donné.
 */
window.restaurerEtatBureau = function(reseauId) {
    if (!reseauId || !window.etatBureau[reseauId]) return;

    const etat = window.etatBureau[reseauId];

    // Restaurer hyéto-hydro
    if (etat.panels && etat.panels.hyetoHydro) {
        const panel = document.getElementById('panel-hyeto-hydro');
        if (panel) {
            panel.style.display = etat.panels.hyetoHydro.visible ? 'flex' : 'none';
            if (etat.panels.hyetoHydro.x !== undefined) {
                panel.style.left = etat.panels.hyetoHydro.x + 'px';
                panel.style.top = etat.panels.hyetoHydro.y + 'px';
                panel.style.right = 'auto';
                panel.style.bottom = 'auto';
            }
        }
    }

    // Restaurer time slider
    if (etat.panels && etat.panels.timeSlider) {
        const panel = document.getElementById('panel-time-slider');
        if (panel) {
            panel.style.display = etat.panels.timeSlider.visible ? 'flex' : 'none';
            if (etat.panels.timeSlider.x !== undefined) {
                panel.style.left = etat.panels.timeSlider.x + 'px';
                panel.style.top = etat.panels.timeSlider.y + 'px';
                panel.style.right = 'auto';
                panel.style.bottom = 'auto';
            }
        }
    }

    // Restaurer profil en long
    if (etat.panels && etat.panels.profilLong) {
        const panel = document.querySelector('.profil-long-container');
        if (panel) {
            panel.style.display = etat.panels.profilLong.visible ? 'flex' : 'none';
            if (etat.panels.profilLong.x !== undefined) {
                panel.style.left = etat.panels.profilLong.x + 'px';
                panel.style.top = etat.panels.profilLong.y + 'px';
                panel.style.right = 'auto';
                panel.style.bottom = 'auto';
            }
        }
    }

    // Restaurer toolbar (ancrée dans Leaflet en haut à droite)
    if (etat.toolbar) {
        const toolbar = document.getElementById('main-edit-toolbar');
        if (toolbar) {
            toolbar.style.display = etat.toolbar.visible !== false ? 'flex' : 'none';
            if (etat.toolbar.collapsed) toolbar.classList.add('collapsed');
            else toolbar.classList.remove('collapsed');
            const icon = document.getElementById('icon-collapse-toolbar');
            if (icon) icon.className = etat.toolbar.collapsed ? 'fas fa-chevron-down' : 'fas fa-chevron-up';
            window._positionAutoToolbar(toolbar);
        }
    }

    // Restaurer légende flottante
    if (etat.floatingLegend !== null) {
        const leg = document.getElementById('sim-floating-legend');
        if (leg) {
            if (etat.floatingLegend.visible) {
                leg.style.display = 'block';
                leg.classList.add('active-legend');
            } else {
                leg.style.display = 'none';
                leg.classList.remove('active-legend');
            }
        }
    }
};

/**
 * Nettoie l'état du réseau avant chargement d'un nouveau réseau.
 * Sauvegarde l'état courant, détruit les graphiques, vide les caches,
 * masque toutes les couches de résultats.
 */
window.nettoyerEtatReseau = function(reseauId) {
    // Sauvegarder l'état courant avant nettoyage
    if (reseauId) window.sauvegarderEtatBureau(reseauId);

    // Masquer immédiatement les couches de résultats SWMM
    if (typeof reinitialiserAffichageSimulation === 'function') {
        reinitialiserAffichageSimulation();
    }

    // Vider les caches de simulation et de données
    window._dernierResultatSimulation = null;
    window._clustersData = null;
    window._bassinNoms = {};
    window._bassinBounds = {};
    window._selectedClusterId = null;
    window._simulationsCache = {};

    // Détruire les graphiques Chart.js pour libérer la mémoire et éviter les courbes fantômes
    if (window.hyetoHydroState && window.hyetoHydroState.chartInstance) {
        try { window.hyetoHydroState.chartInstance.destroy(); } catch(e) {}
        window.hyetoHydroState.chartInstance = null;
    }
    if (window.timeSliderState && window.timeSliderState.chartInstance) {
        try { window.timeSliderState.chartInstance.destroy(); } catch(e) {}
        window.timeSliderState.chartInstance = null;
    }

    // Nettoyer marqueurs de débordement radar
    if (typeof _nettoyerRadarDebordement === 'function') {
        _nettoyerRadarDebordement();
    }

    // Masquer les badges d'interface
    const badgeInstant = document.getElementById('badge-instant-state');
    if (badgeInstant) badgeInstant.classList.add('hidden');

    // Réinitialiser la toolbar (déplier et réancrer en haut à droite)
    const toolbar = document.getElementById('main-edit-toolbar');
    if (toolbar) {
        toolbar.classList.remove('collapsed');
        window._positionAutoToolbar(toolbar);
    }
    const icon = document.getElementById('icon-collapse-toolbar');
    if (icon) icon.className = 'fas fa-chevron-up';

    // Masquer la légende flottante
    const leg = document.getElementById('sim-floating-legend');
    if (leg) {
        leg.style.display = 'none';
        leg.classList.remove('active-legend');
    }

    // Vider toutes les couches Leaflet de résultats et physiques
    if (typeof clusterCouche !== 'undefined' && clusterCouche) clusterCouche.clearLayers();
    if (typeof _activeClusterLayer !== 'undefined' && _activeClusterLayer) _activeClusterLayer.clearLayers();
    if (typeof couches !== 'undefined') {
        Object.values(couches).forEach(l => l.clearLayers());
    }

    // Vider les raccordements orphelins
    if (window._coucheRaccordementsOrphelins) {
        try { window._coucheRaccordementsOrphelins.clearLayers(); } catch(e) {}
    }

    // Désactiver les boutons d'actions de simulation
    if (typeof activerActionsSimulation === 'function') {
        activerActionsSimulation(false);
    }
};
