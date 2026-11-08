/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Initialisation du contexte cartographique et des écouteurs d'événements
 * ================================================================================
 */

(() => {
    function initMap() {
        initLayerFilters();
        initManualBasins();
        initClusterDetection();
        initEditAttributes();
        initNotifications();

        chargerDonneesInitiales();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initMap);
    } else {
        initMap();
    }
})();
