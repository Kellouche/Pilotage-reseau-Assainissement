
// Configuration
const API_BASE_URL = 'http://127.0.0.1:5001';
let map = null;
let dataGlobal = null;
let layers = {};
let anomaliesData = {};
let selectedAnomalie = null;

// Couches Leaflet
let regardsLayer = null;
let conduitesLayer = null;
let rejetsLayer = null;
let stationsLayer = null;
let ouvragesLayer = null;
let anomaliesLayers = {};

// Cache des coordonnées
let regardsCoordsMap = {};
let conduitesCoordsMap = {};

// Regards avec anomalies
let anomalousRegards = new Set();

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
        const response = await fetch(`${API_BASE_URL}/api/v1/layers`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        dataGlobal = data;
        
        if (typeof updateStats === 'function') updateStats();
        await chargerCouchesGeoJSON(data.couches);
        
        showNotification('Chargement des anomalies...', 'info');
        try {
            await chargerAnomalies();
        } catch (error) {
            console.warn('⚠️ Anomalies non disponibles:', error.message);
        }
        
        showNotification('Carte prête !', 'success');
        if (typeof updateLegendForZoom === 'function') updateLegendForZoom();
        if (typeof centerOnData === 'function') centerOnData();
        if (typeof updateSymbolSizes === 'function') updateSymbolSizes();
        showLoading(false);
    } catch (error) {
        console.error('❌ Erreur lors du chargement:', error);
        showError(`Impossible de charger les données: ${error.message}`);
        showLoading(false);
    }
}

async function chargerCouchesGeoJSON(couches) {
    console.log('🔄 Chargement des couches GeoJSON...');
    if (!couches) return;

    // Conduites
    if (couches.conduites && couches.conduites.features) {
        conduitesLayer = L.geoJSON(couches.conduites, {
            style: function(feature) {
                const materiau = feature.properties.materiau;
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
            },
            onEachFeature: function(feature, layer) {
                layer.bindPopup(createPopupContent(feature.properties, 'conduite'));
                layer.on('click', () => selectFeature(feature.properties, 'conduite'));
            }
        });
        
        // Optimized cache building: only if really necessary, or do it lazily
        // For now, let's just use the layers directly when needed.
    }

    // Regards
    if (couches.regards && couches.regards.features) {
        regardsLayer = L.geoJSON(couches.regards, {
            pointToLayer: function(feature, latlng) {
                const props = feature.properties || {};
                const regardId = (props.code || props.id || '').toString();
                const isAnomalous = anomalousRegards.has(regardId);
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

    // Stations, Ouvrages, Rejets (Simplified for brevity but complete)
    if (couches.stations) {
        stationsLayer = L.geoJSON(couches.stations, {
            pointToLayer: (f, l) => L.circleMarker(l, { color: '#9c27b0', fillColor: '#9c27b0', radius: 8 }),
            onEachFeature: (f, l) => l.bindPopup(createPopupContent(f.properties, 'station'))
        });
    }
    if (couches.ouvrages) {
        ouvragesLayer = L.geoJSON(couches.ouvrages, {
            pointToLayer: (f, l) => L.circleMarker(l, { color: '#ff9800', fillColor: '#ff9800', radius: 7 }),
            onEachFeature: (f, l) => l.bindPopup(createPopupContent(f.properties, 'ouvrage'))
        });
    }
    if (couches.step) {
        rejetsLayer = L.geoJSON(couches.step, {
            pointToLayer: (f, l) => L.marker(l, { icon: L.divIcon({ html: '🚰', iconSize: [24, 24] }) }),
            onEachFeature: (f, l) => l.bindPopup(createPopupContent(f.properties, 'rejet'))
        });
    }
}

async function chargerAnomalies() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/v1/qualite/analyse`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        anomaliesData = data.anomalies;
        buildAnomalousRegards(anomaliesData);
        updateAnomaliesLayers();
        Object.keys(tabMappings).forEach(tab => calculateTabStats(tab));
        updateTabDisplay();
    } catch (error) {
        console.error('Erreur chargement anomalies:', error);
    }
}

function showLoading(show) {
    const el = document.getElementById('loading');
    if (el) el.style.display = show ? 'block' : 'none';
}

function showError(message) {
    const errorDiv = document.getElementById('error');
    const msgSpan = document.getElementById('error-message');
    if (errorDiv && msgSpan) {
        msgSpan.textContent = message;
        errorDiv.style.display = 'block';
        setTimeout(() => errorDiv.style.display = 'none', 5000);
    }
}

function showNotification(message, type = 'info') {
    const container = document.body;
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    container.appendChild(notification);
    setTimeout(() => { notification.style.opacity = '1'; }, 10);
    setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}