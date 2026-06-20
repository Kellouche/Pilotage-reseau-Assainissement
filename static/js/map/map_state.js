(() => {
    const state = {
        carte: null,
        couches: null,
        clusterCouche: null,
        activeClusterLayer: null,
        bassinBounds: {},
        lastSyncVersion: 0,
        lastZoomMarker: null,
        totalModifications: 0,
        conduitProperties: [],
        editor: {
            active: false,
            mode: null,
            points: [],
            markers: [],
            tempPolyline: null,
            tempPolygon: null,
            selectedConduits: new Set(),
            foundOutfall: null,
            tempExutoires: []
        }
    };

    window.mapState = state;
})();
