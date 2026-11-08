/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Gestion centralisée de l'état applicatif et des sélections du réseau
 * ================================================================================
 */

(() => {
    const state = {
        carte: null,
        couches: null,
        clusterCouche: null,
        activeClusterLayer: null,
        bassinBounds: {},
        bassinNoms: {},
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
