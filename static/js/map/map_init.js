(() => {
    function initMap() {
        initLayerFilters();
        initManualBasins();
        initClusterDetection();
        initEditAttributes();
        initNotifications();

        chargerDonneesInitiales().then(() => {
            initQuality();
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initMap);
    } else {
        initMap();
    }
})();
