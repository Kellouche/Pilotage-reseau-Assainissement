/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-27
 * Objet : Noyau d'initialisation cartographique, projections et tuiles
 * ================================================================================
 */

// Configuration
const API_BASE_URL = '';
let map = null;
let dataGlobal = null;
let layers = {};
let selectedAnomalie = null;

// Couches Leaflet
let regardsLayer = null;
let conduitesLayer = null;
let rejetsLayer = null;
let stationsLayer = null;
let ouvragesLayer = null;

let conduitesCoordsMap = {};
// Maps de lookup O(1) : id → coordonnées / layer (construites une fois au chargement)
let regardsCoordsMap = {};     // regard_id → [lat, lng]
let conduitesCoordsLookup = {}; // conduit_id → [lat, lng]
let regardsLayerMap = {};      // regard_id → layer Leaflet
let conduitesLayerMap = {};    // conduit_id → layer Leaflet

// Onglets et mappings
let currentTab = 'connexions';
const tabMappings = {
    'connexions': ['conduites_sans_regards', 'incoherences_amont_aval'],
    'geometrie': ['pentes_suspectes', 'geometries_invalides', 'capacite_debit', 'sauts_pente'],
    'donnees': ['champs_manquants'],
    'topologie': ['troncons_orphelins', 'incoherence_profondeur_topologie', 'chevauchement_geometrique', 'doublon_regards'],
    'orphelins': ['orphelins_regards', 'orphelins_troncons']
};

// Initialisation
document.addEventListener('DOMContentLoaded', function () {
    console.log('Carte opérationnelle initialisée');
    initMap();
    chargerDonnees().then(() => {
        if (typeof switchTab === 'function') switchTab('connexions', true);
        
        // Initialisation de la recherche
        const searchInput = document.getElementById('search-input');
        const searchButton = document.getElementById('search-button');
        
        if (searchInput && searchButton) {
            searchButton.addEventListener('click', () => {
                const terme = searchInput.value;
                rechercherReseau(terme);
            });
            
            searchInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    const terme = searchInput.value;
                    rechercherReseau(terme);
                }
            });
        }
    });
});

function initMap() {
    map = L.map('map', {
        preferCanvas: true
    }).setView([36.13, 1.32], 13);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19
    }).addTo(map);

    map.on('click', function (e) {
        if (typeof deselectAnomalie === 'function') deselectAnomalie();
    });

    map.on('zoomend', function () {
        const zoom = map.getZoom();
        const indicator = document.getElementById('zoom-indicator');
        if (indicator) indicator.textContent = 'Zoom: ' + zoom;
        if (typeof updateLegendForZoom === 'function') updateLegendForZoom();
        if (typeof updateSymbolSizes === 'function') updateSymbolSizes();
    });
}

async function chargerDonnees() {
    showLoading(true);
    try {
        console.log('Fetching layers from API...');
        const response = await fetch(`${API_BASE_URL}/api/v1/layers`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

        const data = await response.json();
        dataGlobal = data;

        // 1. Charger d'abord les couches de base (rapide)
        await chargerCouchesGeoJSON(data.couches);

        showNotification('Carte prête !', 'success');
        if (typeof updateLegendForZoom === 'function') updateLegendForZoom();
        if (typeof centerOnData === 'function') centerOnData();
        showLoading(false);

        // Auto-lancer le diagnostic après chargement carte (Phase 0)
        if (typeof lancerDiagnostic === 'function') {
            setTimeout(() => lancerDiagnostic('connexions'), 500);
        }
    } catch (error) {
        console.error('❌ Erreur lors du chargement:', error);
        showError(`Impossible de charger les données: ${error.message}`);
        showLoading(false);
    }
}

let precomputedConduiteStyles = {};

function precomputeConduiteStyles() {
    precomputedConduiteStyles = {};
    if (!diagnosticsLoaded || !anomaliesData) return;

    const activeTypesInTab = tabMappings[currentTab] || [];

    // Cache checkbox states to avoid DOM queries inside the loop
    const activeGroupsChecked = {};
    activeTypesInTab.forEach(group => {
        const cb = document.getElementById(`type-${group}`);
        activeGroupsChecked[group] = cb ? cb.checked : false;
    });

    const severities = { 'critique': 3, 'majeure': 2, 'mineure': 1 };
    const conduitActiveAnoms = {};

    activeTypesInTab.forEach(group => {
        if (activeGroupsChecked[group]) {
            const groupAnoms = anomaliesData[group] || [];
            groupAnoms.forEach(a => {
                const aid = (a.id_conduite || a.fid || a.id_conduite1 || a.id_conduite2 || a.fid1 || a.fid2 || '').toString();
                if (aid) {
                    if (!conduitActiveAnoms[aid]) {
                        conduitActiveAnoms[aid] = [];
                    }
                    conduitActiveAnoms[aid].push(a);
                }
            });
        }
    });

    for (const [fid, anoms] of Object.entries(conduitActiveAnoms)) {
        if (anoms.length > 0) {
            let maxSev = 'mineure';
            anoms.forEach(a => {
                if (severities[a.severite] > severities[maxSev]) {
                    maxSev = a.severite;
                }
            });
            const color = typeof getAnomalieColor === 'function' ? getAnomalieColor(maxSev) : '#f44336';
            precomputedConduiteStyles[fid] = { color: color, weight: 6, opacity: 1 };
        }
    }
}

function getConduiteStyle(feature) {
    if (!diagnosticsLoaded) {
        return { color: '#bdc3c7', weight: 2, opacity: 0.6 };
    }

    const props = feature.properties || {};

    const idCandidates = [
        feature.id,
        props.fid, props.FID, props.id, props.ID,
        props.OBJECTID, props.code, props.CODE,
        props.ID_CANALIS, props.ID_CONDUIT
    ];

    for (let cand of idCandidates) {
        if (cand !== undefined && cand !== null && cand !== '') {
            const sCand = cand.toString();
            if (precomputedConduiteStyles[sCand]) {
                return precomputedConduiteStyles[sCand];
            }
        }
    }

    return { color: '#bdc3c7', weight: 2, opacity: 0.6 };
}

function createPopupContent(props, type) {
    let html = `<div class="popup-content"><div class="popup-title">${type.toUpperCase()}</div>`;
    for (const [k, v] of Object.entries(props)) {
        if (v !== null && v !== undefined) html += `<div class="popup-info"><strong>${k}:</strong> ${v}</div>`;
    }
    html += '</div>';
    return html;
}

async function chargerCouchesGeoJSON(couches) {
    if (!couches) return;

    // Conduites
    if (couches.conduites && couches.conduites.features) {
        conduitesLayer = L.geoJSON(couches.conduites, {
            style: feature => getConduiteStyle(feature),
            onEachFeature: function (feature, layer) {
                layer.bindPopup(createPopupContent(feature.properties, 'conduite'));
                layer.on('click', () => selectFeature(feature.properties, 'conduite'));
            }
        });
    }

    // Regards
    if (couches.regards && couches.regards.features) {
        regardsLayer = L.geoJSON(couches.regards, {
            pointToLayer: function (feature, latlng) {
                return L.circleMarker(latlng, {
                    color: '#bdc3c7',
                    fillColor: '#bdc3c7',
                    fillOpacity: 0.6,
                    radius: 2, // Réduit encore la taille
                    weight: 1
                });
            },
            onEachFeature: function (feature, layer) {
                layer.bindPopup(createPopupContent(feature.properties, 'regard'));
                layer.on('click', () => selectFeature(feature.properties, 'regard'));
            }
        });
    }

    // Autres couches ponctuelles
    ['stations', 'rejets', 'ouvrages', 'step'].forEach(type => {
        if (couches[type] && couches[type].features) {
            let color = '#666';
            if (type === 'stations') color = '#ff5722'; // Orange pour relevage
            if (type === 'step') color = '#9c27b0';     // Violet pour STEP
            if (type === 'rejets') color = '#00bcd4';   // Cyan pour rejets

            console.log(`Couche ${type}Layer créée avec ${couches[type].features.length} entités.`);
            layers[type + 'Layer'] = L.geoJSON(couches[type], {
                pointToLayer: (feature, latlng) => L.circleMarker(latlng, {
                    radius: 6,
                    color: '#fff',
                    fillColor: color,
                    fillOpacity: 1,
                    weight: 2
                }),
                onEachFeature: function (feature, layer) {
                    layer.bindPopup(createPopupContent(feature.properties, type));
                }
            });
        } else {
            console.warn(`Couche ${type} absente ou vide dans les données reçues.`);
        }
    });

    // Enregistrer les couches principales dans l'objet global pour la visibilité
    layers['conduitesLayer'] = conduitesLayer;
    layers['regardsLayer'] = regardsLayer;

    // Construire les maps de lookup O(1) pour les coordonnées et les layers
    // (évite d'itérer sur 10 000+ entités pour chaque anomalie)
    if (regardsLayer) {
        regardsLayer.eachLayer(layer => {
            const p = layer.feature.properties;
            const ids = [p.code, p.id, p.fid].filter(v => v !== undefined && v !== null);
            const ll = layer.getLatLng();
            const coords = [ll.lat, ll.lng];
            ids.forEach(id => {
                const key = id.toString();
                regardsCoordsMap[key] = coords;
                regardsLayerMap[key] = layer;
            });
        });
        console.log(`[Lookup] regardsCoordsMap: ${Object.keys(regardsCoordsMap).length} entrées`);
    }

    if (conduitesLayer) {
        conduitesLayer.eachLayer(layer => {
            const p = layer.feature.properties;
            const ids = [p.fid, p.id, p.ID, p.ID_AMONT, p.ID_AVAL, p.CODE, p.code]
                .filter(v => v !== undefined && v !== null);
            if (layer.getBounds) {
                const c = layer.getBounds().getCenter();
                const coords = [c.lat, c.lng];
                ids.forEach(id => {
                    const key = id.toString();
                    conduitesCoordsLookup[key] = coords;
                    conduitesLayerMap[key] = layer;
                });
            }
        });
        console.log(`[Lookup] conduitesCoordsLookup: ${Object.keys(conduitesCoordsLookup).length} entrées`);
    }
}

function updateLegendForZoom() {
    if (!map) return;
    const zoom = map.getZoom();
    const analysisMode = document.getElementById('analysis-mode')?.checked ?? false;

    const layerMappings = {
        'conduitesLayer': { id: 'layer-conduites', minZoom: 15 },
        'regardsLayer': { id: 'layer-regards', minZoom: 16 },
        'stationsLayer': { id: 'layer-stations', minZoom: 13 },
        'stepLayer': { id: 'layer-step', minZoom: 13 },
        'ouvragesLayer': { id: 'layer-ouvrages', minZoom: 14 }
    };

    Object.entries(layerMappings).forEach(([layerKey, config]) => {
        const layer = layers[layerKey];
        const checkbox = document.getElementById(config.id);

        if (!layer) {
            console.warn(`Layer ${layerKey} non trouvé dans l'objet layers.`);
            return;
        }

        const isChecked = checkbox?.checked ?? true;
        const shouldShow = isChecked && (zoom >= config.minZoom || analysisMode);

        console.log(`Layer ${layerKey}: isChecked=${isChecked}, shouldShow=${shouldShow}`);

        if (shouldShow) {
            if (!map.hasLayer(layer)) {
                map.addLayer(layer);
                console.log(`Layer ${layerKey} ajouté à la carte`);
            }
        } else {
            if (map.hasLayer(layer)) {
                map.removeLayer(layer);
                console.log(`Layer ${layerKey} retiré de la carte`);
            }
        }
    });
}

function centerOnData() {
    console.log('Centrage sur les données...');
    if (conduitesLayer && map.hasLayer(conduitesLayer)) {
        try {
            const bounds = conduitesLayer.getBounds();
            if (bounds.isValid()) {
                map.fitBounds(bounds, { padding: [30, 30] });
            }
        } catch (e) { console.warn('Erreur centrage conduites:', e); }
    } else if (regardsLayer && map.hasLayer(regardsLayer)) {
        try {
            const bounds = regardsLayer.getBounds();
            if (bounds.isValid()) {
                map.fitBounds(bounds, { padding: [30, 30] });
            }
        } catch (e) { console.warn('Erreur centrage regards:', e); }
    }
}

function showLoading(show) {
    const el = document.getElementById('loading');
    if (el) el.style.display = show ? 'flex' : 'none';
}

function showError(msg) {
    const el = document.getElementById('error');
    const msgEl = document.getElementById('error-message');
    if (el && msgEl) {
        el.style.display = 'block';
        msgEl.textContent = msg;
    }
}
