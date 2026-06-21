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
