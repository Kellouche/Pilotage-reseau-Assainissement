
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
    'geometrie': ['pentes_suspectes', 'geometries_invalides'],
    'donnees': ['champs_manquants'],
    'topologie': ['troncons_orphelins']
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

let diagnosticsLoaded = false;
let abortController = null;
let diagnosticInterval = null;
let diagnosticStartTime = 0;

function lancerDiagnostic(targetTab) {
    console.log("Démarrage du diagnostic pour :", targetTab);

    // Afficher la modale bloquante
    const modal = document.getElementById('diagnostic-modal');
    if (modal) modal.style.display = 'flex';

    const progressBar = document.getElementById('diagnostic-progress-bar');
    const percentText = document.getElementById('diagnostic-percent');
    const chronoText = document.getElementById('diagnostic-chrono');
    const statusMsg = document.getElementById('diagnostic-status-msg');

    if (progressBar) progressBar.style.width = '0%';
    if (percentText) percentText.textContent = '0%';
    if (chronoText) chronoText.textContent = 'Temps écoulé : 0.0s';
    if (statusMsg) statusMsg.textContent = "Initialisation de l'analyse...";

    // Annuler tout diagnostic précédent
    if (diagnosticInterval) clearInterval(diagnosticInterval);
    if (abortController) abortController.abort();

    abortController = new AbortController();
    diagnosticStartTime = Date.now();

    // Lancer le timer pour animer la barre de progression et le chrono
    diagnosticInterval = setInterval(() => {
        const elapsedMs = Date.now() - diagnosticStartTime;
        const elapsedSec = (elapsedMs / 1000).toFixed(1);
        if (chronoText) chronoText.textContent = `Temps écoulé : ${elapsedSec}s`;

        // Progression simulée asymptotique (0% -> 95%)
        let progress = 0;
        if (elapsedMs < 2000) {
            progress = (elapsedMs / 2000) * 40; // 0% à 40% en 2s
        } else if (elapsedMs < 5000) {
            progress = 40 + ((elapsedMs - 2000) / 3000) * 35; // 40% à 75% en 3s
        } else {
            progress = 75 + (1 - Math.exp(-(elapsedMs - 5000) / 10000)) * 20; // asymptotique vers 95%
        }

        const progressInt = Math.min(95, Math.floor(progress));
        if (progressBar) progressBar.style.width = progressInt + '%';
        if (percentText) percentText.textContent = progressInt + '%';

        // Messages de statut dynamiques basés sur le temps écoulé
        let msg = "Initialisation de l'analyse...";
        if (elapsedMs > 12000) {
            msg = "Finalisation et calcul des scores...";
        } else if (elapsedMs > 8000) {
            msg = "Calcul de la topologie du graphe...";
        } else if (elapsedMs > 5000) {
            msg = "Vérification des anomalies de pente...";
        } else if (elapsedMs > 3000) {
            msg = "Analyse des connexions amont/aval...";
        } else if (elapsedMs > 1500) {
            msg = "Chargement du modèle de réseau...";
        }
        if (statusMsg) statusMsg.textContent = msg;
    }, 100);

    // Lancer la requête API réelle
    fetch(`${API_BASE_URL}/api/v1/qualite/analyse`, { signal: abortController.signal })
        .then(async (response) => {
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            return response.json();
        })
        .then((anomData) => {
            console.log("Diagnostic calculé avec succès", anomData);

            // Stopper le chrono
            clearInterval(diagnosticInterval);
            diagnosticInterval = null;

            // Afficher 100% de progression
            if (progressBar) progressBar.style.width = '100%';
            if (percentText) percentText.textContent = '100%';
            if (statusMsg) statusMsg.textContent = "Calcul terminé !";

            // Fermer la modale après un court délai pour que l'utilisateur voie les 100%
            setTimeout(() => {
                if (modal) modal.style.display = 'none';
            }, 500);
            showNotification('Diagnostic terminé !', 'success');

            // Traitement différé : laisser le navigateur respirer entre chaque étape
            // pour éviter de geler l'interface pendant le traitement de 3 Mo de données
            const steps = [];

            // Étape 1 : intégrer les anomalies dans la carte
            steps.push(() => {
                if (typeof buildAnomaliesMaps === 'function') buildAnomaliesMaps(anomData);
                if (typeof updateAnomaliesLayers === 'function') updateAnomaliesLayers();
            });

            // Étape 2 : peupler les listes d'anomalies (async pour pré-charger les suggestions)
            steps.push(async () => {
                try {
                    if (typeof populateAnomaliesLists === 'function') await populateAnomaliesLists(anomData.anomalies || anomData);
                } catch (e) {
                    console.warn('populateAnomaliesLists fallback failed', e);
                }
            });

            // Étape 3 : mettre à jour les compteurs de tous les onglets
            steps.push(() => {
                Object.keys(tabMappings).forEach(tab => {
                    if (typeof calculateTabStats === 'function') calculateTabStats(tab);
                });
            });

            // Étape 4 : mettre à jour les scores
            steps.push(() => {
                if (typeof updateStats === 'function') updateStats();
            });

            // Étape 5 : finaliser
            steps.push(() => {
                diagnosticsLoaded = true;
                document.querySelectorAll('.tab-btn').forEach(btn => {
                    btn.classList.remove('pending');
                });
                if (typeof switchTabReal === 'function') {
                    switchTabReal(targetTab);
                }
            });

            // Exécuter chaque étape en cédant la main au navigateur entre chaque
            // Gère aussi les étapes async (ex: populateAnomaliesLists avec pré-chargement suggestions)
            async function runStep(index) {
                if (index >= steps.length) return;
                // requestAnimationFrame garantit que le DOM est rendu avant de toucher les éléments
                requestAnimationFrame(async () => {
                    try {
                        await steps[index]();
                    } catch (e) {
                        console.error(`Erreur étape traitement ${index}:`, e);
                    }
                    runStep(index + 1);
                });
            }

            runStep(0);
        })
        .catch((error) => {
            if (error.name === 'AbortError') {
                console.log("Opération annulée par l'utilisateur.");
                return; // Géré par annulerDiagnostic()
            }
            console.error("Erreur lors de l'analyse :", error);

            clearInterval(diagnosticInterval);
            diagnosticInterval = null;

            if (modal) modal.style.display = 'none';
            showNotification(`Erreur d'analyse: ${error.message}`, 'error');
        });
}

function annulerDiagnostic() {
    console.log("Annulation du diagnostic...");

    if (abortController) {
        abortController.abort();
        abortController = null;
    }

    if (diagnosticInterval) {
        clearInterval(diagnosticInterval);
        diagnosticInterval = null;
    }

    const modal = document.getElementById('diagnostic-modal');
    if (modal) modal.style.display = 'none';

    showNotification("Opération annulée par l'utilisateur.", 'warning');
}

/**
 * Recherche dans les couches du réseau
 * @param {string} terme - Terme de recherche
 */
function rechercherReseau(terme) {
    terme = terme.trim().toLowerCase();
    if (terme.length < 2) {
        alert('Veuillez entrer au moins 2 caractères pour rechercher.');
        return;
    }

    const matches = [];
    const coucheTypes = [
        { name: 'conduites', layer: conduitesLayer },
        { name: 'regards', layer: regardsLayer },
        { name: 'stations', layer: layers?.stationsLayer },
        { name: 'rejets', layer: layers?.rejectsLayer },
        { name: 'ouvrages', layer: layers?.ouvragesLayer },
        { name: 'step', layer: layers?.stepLayer }
    ];

    for (const { name, layer } of coucheTypes) {
        if (!layer) continue;
        layer.eachLayer(l => {
            const props = l.feature.properties || {};
            let found = false;
            for (const key in props) {
                const val = props[key];
                if (val !== null && val !== undefined) {
                    const strVal = String(val).toLowerCase();
                    if (strVal.includes(terme)) {
                        found = true;
                        break;
                    }
                }
            }
            if (found) {
                matches.push({ type: name, props, layer: l });
            }
        });
    }

    if (matches.length === 0) {
        alert('Aucun résultat trouvé.');
        return;
    }

    // Prendre le premier résultat pour le zoom et le popup
    const firstMatch = matches[0];
    const layer = firstMatch.layer;
    const props = firstMatch.props;

    // Calculer les bounds pour le zoom
    let bounds;
    if (layer instanceof L.LatLng) {
        bounds = L.latLngBounds(layer, layer);
    } else if (layer.getLatLng) {
        bounds = L.latLngBounds(layer.getLatLng(), layer.getLatLng());
    } else if (layer.getBounds) {
        bounds = layer.getBounds();
    } else {
        // Fallback: utiliser la première coordonnée disponible
        const latlng = layer.getLatLng ? layer.getLatLng() : L.latLng(0, 0);
        bounds = L.latLngBounds(latlng, latlng);
    }

    if (bounds && bounds.isValid()) {
        map.fitBounds(bounds, { padding: [50, 50] });
    }

    // Créer un popup avec les propriétés
    let popupContent = `<div class="popup-content"><div class="popup-title">Résultat de recherche</div>`;
    for (const [k, v] of Object.entries(props)) {
        if (v !== null && v !== undefined) {
            popupContent += `<div class="popup-info"><strong>${k}:</strong> ${v}</div>`;
        }
    }
    popupContent += '</div>';

    // Lier le popup au layer et l'ouvrir
    layer.bindPopup(popupContent).openPopup();

    // Surligner temporairement le layer correspondant
    function highlightLayerTemporarily(l, delay = 2000) {
        let originalStyle;
        if (l instanceof L.Polyline) {
            originalStyle = l.options;
            l.setStyle({ color: '#ffff00', weight: 8, opacity: 0.8 });
        } else if (l instanceof L.CircleMarker) {
            originalStyle = {
                radius: l.options.radius,
                color: l.options.color,
                fillColor: l.options.fillColor,
                weight: l.options.weight
            };
            l.setStyle({ radius: 10, color: '#ffff00', fillColor: '#ffff00', weight: 2 });
        } else {
            // Pour les autres types de couches, on ne fait rien de spécial
            return;
        }
        setTimeout(() => {
            if (originalStyle) {
                l.setStyle(originalStyle);
            }
        }, delay);
    }

    highlightLayerTemporarily(layer, 3000);
}

function showNotification(msg, type = 'info') {
    console.log(`[${type.toUpperCase()}] ${msg}`);

    let toast = document.getElementById('toast-notification');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'toast-notification';
        toast.className = 'notification';
        document.body.appendChild(toast);
    }

    toast.className = `notification notification-${type}`;
    toast.innerHTML = msg;
    toast.style.display = 'block';

    setTimeout(() => {
        toast.style.opacity = '1';
    }, 10);

    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => {
            toast.style.display = 'none';
        }, 300);
    }, 3000);
}