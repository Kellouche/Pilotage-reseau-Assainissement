/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Couche de base et configuration du canevas cartographique
 * ================================================================================
 */

(() => {
    const state = window.mapState;
    state.carte = L.map('map').setView([36.15, 1.33], 13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap'
    }).addTo(state.carte);

    state.couches = {
        conduites: L.layerGroup().addTo(state.carte),
        regards: L.layerGroup(),
        stations: L.layerGroup().addTo(state.carte),
        step: L.layerGroup().addTo(state.carte),
        ouvrages: L.layerGroup().addTo(state.carte),
        bassins: L.layerGroup(),
        incidents: L.layerGroup().addTo(state.carte)
    };

    state.clusterCouche = L.layerGroup().addTo(state.carte);
})();
