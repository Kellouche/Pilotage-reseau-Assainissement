
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
            
            // Mettre à jour les compteurs (parenthèses) pour tous les onglets
            Object.keys(tabMappings).forEach(tab => {
                if (typeof calculateTabStats === 'function') calculateTabStats(tab);
            });
            
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
    const activeTypesInTab = tabMappings[currentTab] || [];
    
    // Recherche agressive d'un identifiant correspondant
    const idCandidates = [
        feature.id,
        props.fid, props.FID, props.id, props.ID, 
        props.OBJECTID, props.code, props.CODE,
        props.ID_CANALIS, props.ID_CONDUIT
    ];
    
    let matchedFid = null;
    for (let cand of idCandidates) {
        if (cand !== undefined && cand !== null && cand !== '') {
            let sCand = cand.toString();
            if (typeof conduiteAnomaliesMap !== 'undefined' && conduiteAnomaliesMap[sCand]) {
                matchedFid = sCand;
                break;
            }
        }
    }
    
    if (matchedFid) {
        console.log(`Debug: Analyse anomalie pour ${matchedFid}`);
        const anomInfo = conduiteAnomaliesMap[matchedFid];
        
        // On ne regarde QUE les anomalies qui appartiennent à l'onglet courant ET sont cochées
        const visibleAnoms = [];
        if (anomaliesData) {
            activeTypesInTab.forEach(group => {
                const cb = document.getElementById(`type-${group}`);
                if (cb && cb.checked) {
                    const groupAnoms = anomaliesData[group] || [];
                    // Chercher les anomalies de ce groupe pour cette conduite
                    groupAnoms.forEach(a => {
                        const aid = (a.id_conduite || a.fid || a.id_conduite1 || a.id_conduite2 || a.fid1 || a.fid2 || '').toString();
                        if (aid === matchedFid) visibleAnoms.push(a);
                    });
                }
            });
        }
        
        if (visibleAnoms.length > 0) {
            // Calculer la sévérité max parmi les anomalies VISIBLES uniquement
            let maxSev = 'mineure';
            const severities = { 'critique': 3, 'majeure': 2, 'mineure': 1 };
            visibleAnoms.forEach(a => {
                if (severities[a.severite] > severities[maxSev]) maxSev = a.severite;
            });
            
            const color = typeof getAnomalieColor === 'function' ? getAnomalieColor(maxSev) : '#f44336';
            return { color: color, weight: 6, opacity: 1 };
        }
    }
    
    // Style par défaut (Neutre pour ne pas confondre avec les anomalies)
    return { color: '#bdc3c7', weight: 2, opacity: 0.6 };
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
                return L.circleMarker(latlng, {
                    color: '#bdc3c7', 
                    fillColor: '#bdc3c7', 
                    fillOpacity: 0.6, 
                    radius: 2, // Réduit encore la taille
                    weight: 1
                });
            },
            onEachFeature: function(feature, layer) {
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
                onEachFeature: function(feature, layer) {
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
}

function updateLegendForZoom() {
    if (!map) return;
    const zoom = map.getZoom();
    const analysisMode = document.getElementById('analysis-mode')?.checked;

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

        const isChecked = checkbox?.checked;
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

function showNotification(msg, type = 'info') {
    console.log(`[${type.toUpperCase()}] ${msg}`);
}