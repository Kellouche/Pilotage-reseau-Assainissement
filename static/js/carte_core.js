
// Configuration
const API_BASE_URL = 'http://127.0.0.1:5001';
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

// Onglets et mappings
let currentTab = 'connexions';
const tabMappings = {
    'connexions': ['conduites_sans_regards', 'incoherences_amont_aval'],
    'geometrie': ['pentes_suspectes', 'geometries_invalides'],
    'donnees': ['champs_manquants'],
    'topologie': ['troncons_orphelins']
};

// Initialisation
document.addEventListener('DOMContentLoaded', function() {
    console.log('Carte opérationnelle initialisée');
    initMap();
    chargerDonnees().then(() => {
        if (typeof switchTab === 'function') switchTab('connexions');
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

    map.on('click', function(e) {
        if (typeof deselectAnomalie === 'function') deselectAnomalie();
    });

    map.on('zoomend', function() {
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
        
        // 2. Charger les anomalies et scores (en arrière-plan)
        try {
            console.log('Fetching anomalies in background...');
            const anomRes = await fetch(`${API_BASE_URL}/api/v1/qualite/analyse`);
            const anomData = await anomRes.json();
            
            if (typeof buildAnomaliesMaps === 'function') buildAnomaliesMaps(anomData);
            if (typeof updateAnomaliesLayers === 'function') updateAnomaliesLayers();
            if (typeof updateStats === 'function') updateStats();
            
        } catch (error) {
            console.warn('⚠️ Anomalies non disponibles:', error.message);
        }
        
        showNotification('Carte prête !', 'success');
        if (typeof updateLegendForZoom === 'function') updateLegendForZoom();
        if (typeof centerOnData === 'function') centerOnData();
        showLoading(false);
    } catch (error) {
        console.error('❌ Erreur lors du chargement:', error);
        showError(`Impossible de charger les données: ${error.message}`);
        showLoading(false);
    }
}

function getConduiteStyle(feature) {
    const props = feature.properties || {};
    const fid = (props.fid || props.id || '').toString();
    
    // Check for anomalies first
    if (typeof conduiteAnomaliesMap !== 'undefined' && conduiteAnomaliesMap[fid]) {
        const anom = conduiteAnomaliesMap[fid];
        const isVisible = anom.types.some(t => {
            const group = typeof getAnomalieGroup === 'function' ? getAnomalieGroup(t) : t;
            return document.getElementById(`type-${group}`)?.checked;
        });
        
        if (isVisible) {
            const color = typeof getAnomalieColor === 'function' ? getAnomalieColor(anom.severite) : '#f44336';
            return { color: color, weight: 6, opacity: 1 };
        }
    }
    
    // Default material style
    const materiau = props.materiau;
    let color = '#4caf50';
    switch(materiau) {
        case 'Béton': color = '#795548'; break;
        case 'PVC': color = '#2196f3'; break;
        case 'Fonte': color = '#9e9e9e'; break;
        case 'Acier': color = '#607d8b'; break;
        case 'PE': color = '#4caf50'; break;
        case 'Grès': color = '#ff9800'; break;
    }
    return { color: color, weight: 3, opacity: 0.8 };
}

async function chargerCouchesGeoJSON(couches) {
    if (!couches) return;
    
    // Conduites
    if (couches.conduites && couches.conduites.features) {
        conduitesLayer = L.geoJSON(couches.conduites, {
            style: feature => getConduiteStyle(feature),
            onEachFeature: function(feature, layer) {
                layer.bindPopup(createPopupContent(feature.properties, 'conduite'));
                layer.on('click', () => selectFeature(feature.properties, 'conduite'));
            }
        });
    }

    // Regards
    if (couches.regards && couches.regards.features) {
        regardsLayer = L.geoJSON(couches.regards, {
            pointToLayer: function(feature, latlng) {
                const props = feature.properties || {};
                const regardId = (props.code || props.id || '').toString();
                const isAnomalous = typeof anomalousRegards !== 'undefined' && anomalousRegards.has(regardId);
                const color = isAnomalous ? '#f44336' : '#2196f3';
                return L.circleMarker(latlng, {
                    color: color, fillColor: color, fillOpacity: 0.8, radius: 3, weight: 1
                });
            },
            onEachFeature: function(feature, layer) {
                layer.bindPopup(createPopupContent(feature.properties, 'regard'));
                layer.on('click', () => selectFeature(feature.properties, 'regard'));
            }
        });
    }
    
    ['stations', 'rejets', 'ouvrages'].forEach(type => {
        if (couches[type] && couches[type].features) {
            layers[type + 'Layer'] = L.geoJSON(couches[type], {
                pointToLayer: (feature, latlng) => L.circleMarker(latlng, { radius: 5, color: '#666' })
            });
        }
    });
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

function showNotification(msg, type = 'info') {
    console.log(`[${type.toUpperCase()}] ${msg}`);
}