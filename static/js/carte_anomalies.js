
// Variables globales pour les anomalies
let conduiteAnomaliesMap = {}; // fid -> { severite, types: [] }
let anomalousRegards = new Set();
let anomaliesData = {};
let anomaliesLayers = {};

function buildAnomaliesMaps(data) {
    if (!data) return;
    const anomsByType = data.anomalies || data; // Handle both full response and sub-object
    
    anomaliesData = anomsByType;
    anomalousRegards = new Set();
    conduiteAnomaliesMap = {};
    
    for (const [category, anomalies] of Object.entries(anomsByType)) {
        if (!Array.isArray(anomalies)) continue; // Skip non-array fields like date_analyse
        
        anomalies.forEach(anom => {
            // Mapping des regards
            const regardId = anom.id_regard || anom.code || anom.point_connexion || anom.id_amont_manquant || anom.id_aval_manquant;
            if (regardId) anomalousRegards.add(regardId.toString());

            // Mapping des conduites
            const conduiteId = anom.id_conduite || anom.fid;
            if (conduiteId) {
                const fid = conduiteId.toString();
                if (!conduiteAnomaliesMap[fid]) {
                    conduiteAnomaliesMap[fid] = { severite: anom.severite, types: [anom.type] };
                } else {
                    conduiteAnomaliesMap[fid].types.push(anom.type);
                    // Priorité à la sévérité la plus haute
                    const severities = { 'critique': 3, 'majeure': 2, 'mineure': 1 };
                    const currentSev = severities[anom.severite] || 0;
                    const storedSev = severities[conduiteAnomaliesMap[fid].severite] || 0;
                    if (currentSev > storedSev) {
                        conduiteAnomaliesMap[fid].severite = anom.severite;
                    }
                }
            }
        });
    }
    console.log("Anomalies maps built:", { regards: anomalousRegards.size, conduites: Object.keys(conduiteAnomaliesMap).length });
}

function updateAnomaliesLayers() {
    if (!anomaliesData) return;

    // 1. Mettre à jour le style des conduites
    if (typeof conduitesLayer !== 'undefined' && conduitesLayer) {
        conduitesLayer.setStyle(feature => getConduiteStyle(feature));
    }

    // 2. Mettre à jour les marqueurs ponctuels
    try {
        for (const [typeAnomalie, anomalies] of Object.entries(anomaliesData)) {
            const markers = [];
            anomalies.forEach(anomalie => {
                if (!shouldShowAnomalie(anomalie)) return;

                // Ne pas mettre de marqueur si c'est déjà colorié sur la conduite
                const isConduiteAnom = ['pente_negative', 'pente_trop_forte', 'champs_manquants_conduite'].includes(anomalie.type);
                if (isConduiteAnom) return;

                let coords = findAnomalieCoords(anomalie);
                if (coords) {
                    const color = getAnomalieColor(anomalie.severite);
                    const marker = L.circleMarker(coords, {
                        color: color, fillColor: color, fillOpacity: 0.8, radius: 8, weight: 2
                    });
                    marker.bindPopup(createAnomaliePopup(anomalie));
                    markers.push(marker);
                }
            });

            if (anomaliesLayers[typeAnomalie] && map.hasLayer(anomaliesLayers[typeAnomalie])) {
                map.removeLayer(anomaliesLayers[typeAnomalie]);
            }
            anomaliesLayers[typeAnomalie] = L.layerGroup(markers);
            
            // Afficher si c'est l'onglet courant
            if (typeof tabMappings !== 'undefined' && typeof currentTab !== 'undefined' && 
                tabMappings[currentTab] && tabMappings[currentTab].includes(typeAnomalie)) {
                map.addLayer(anomaliesLayers[typeAnomalie]);
            }
        }
    } catch (e) { console.error('Error updating layers:', e); }
}

function findRegardCoords(regardId) {
    if (!regardsLayer) return null;
    let coords = null;
    regardsLayer.eachLayer(layer => {
        const p = layer.feature.properties;
        if (p.code == regardId || p.id == regardId || p.fid == regardId) {
            const ll = layer.getLatLng();
            coords = [ll.lat, ll.lng];
        }
    });
    return coords;
}

function findConduiteCoords(conduiteId) {
    if (!conduitesLayer) return null;
    let coords = null;
    conduitesLayer.eachLayer(layer => {
        const p = layer.feature.properties;
        if (p.fid == conduiteId || p.id == conduiteId) {
            if (layer.getBounds) {
                const c = layer.getBounds().getCenter();
                coords = [c.lat, c.lng];
            }
        }
    });
    return coords;
}

function findAnomalieCoords(anomalie) {
    if (anomalie.latitude && anomalie.longitude) return [anomalie.latitude, anomalie.longitude];
    const id = anomalie.id_regard || anomalie.code || anomalie.point_connexion || anomalie.id_amont_manquant || anomalie.id_aval_manquant;
    if (id) return findRegardCoords(id);
    const cid = anomalie.id_conduite || anomalie.fid;
    if (cid) return findConduiteCoords(cid);
    return null;
}

function shouldShowAnomalie(anomalie) {
    // Vérification des types
    const group = getAnomalieGroup(anomalie.type);
    const typeEl = document.getElementById(`type-${group}`);
    if (typeEl && !typeEl.checked) return false;

    // Sévérités : On affiche tout automatiquement comme demandé
    return true;
}

function getAnomalieGroup(type) {
    switch (type) {
        case 'conduite_sans_regard': return 'conduites_sans_regards';
        case 'troncon_orphelin': return 'troncons_orphelins';
        case 'champs_manquants_conduite':
        case 'champs_manquants_regard': return 'champs_manquants';
        case 'geometrie_invalide': return 'geometries_invalides';
        case 'pente_negative':
        case 'pente_trop_forte': return 'pentes_suspectes';
        case 'incoherence_profondeur': return 'incoherences_amont_aval';
        default: return type;
    }
}

function getAnomalieColor(severite) {
    const colors = { 'critique': '#f44336', 'majeure': '#ff9800', 'mineure': '#4caf50' };
    return colors[severite] || '#666';
}

function getAnomalieTitre(anomalie) {
    const titres = {
        'conduite_sans_regard': 'Connexion manquante',
        'troncon_orphelin': 'Tronçon isolé',
        'champs_manquants_conduite': 'Données incomplètes (conduite)',
        'champs_manquants_regard': 'Données incomplètes (regard)',
        'geometrie_invalide': 'Position invalide',
        'pente_negative': 'Pente négative',
        'pente_trop_forte': 'Pente excessive',
        'incoherence_profondeur': 'Connexion incohérente'
    };
    return titres[anomalie.type] || anomalie.type;
}

function getAnomalieDescription(anomalie) {
    if (anomalie.champs_manquants) return `Champs manquants: ${anomalie.champs_manquants.join(", ")}`;
    if (anomalie.pente_pourcent !== undefined) return `Pente: ${anomalie.pente_pourcent.toFixed(1)}%`;
    if (anomalie.difference) return `Ecart: ${anomalie.difference.toFixed(2)}m`;
    return 'Anomalie détectée';
}

function calculateTabStats(tabName) {
    if (!anomaliesData) return;
    const activeTypes = tabMappings[tabName] || [];
    let total = 0, critiques = 0, majeures = 0, mineures = 0;

    activeTypes.forEach(type => {
        const anomalies = anomaliesData[type] || [];
        anomalies.forEach(anom => {
            total++;
            if (anom.severite === 'critique') critiques++;
            else if (anom.severite === 'majeure') majeures++;
            else if (anom.severite === 'mineure') mineures++;
        });
    });

    const el = document.getElementById(`stats-${tabName}`);
    if (el) {
        el.innerHTML = `
            <div class="diagnostic-stats">
                <div><strong>Total:</strong> ${total} anomalies</div>
                <div style="color: #f44336;"><strong>Critiques:</strong> ${critiques}</div>
                <div style="color: #ff9800;"><strong>Majeures:</strong> ${majeures}</div>
                <div style="color: #4caf50;"><strong>Mineures:</strong> ${mineures}</div>
            </div>
        `;
    }
}

function updateStats() {
    fetch(`${API_BASE_URL}/api/v1/qualite/scores`)
        .then(res => res.json())
        .then(data => {
            const scoreEl = document.getElementById('global-score');
            const totalEl = document.getElementById('total-anomalies');
            if (scoreEl) scoreEl.textContent = `${data.global.score_qualite}%`;
            if (totalEl) totalEl.textContent = data.global.total_anomalies;
        })
        .catch(e => console.error('Erreur stats:', e));
}

function updateTabDisplay() {
    // Retirer toutes les couches d'anomalies actuelles
    Object.values(anomaliesLayers).forEach(layer => {
        if (map.hasLayer(layer)) map.removeLayer(layer);
    });
    
    // Ajouter celles de l'onglet courant
    const activeTypes = tabMappings[currentTab] || [];
    activeTypes.forEach(type => {
        if (anomaliesLayers[type]) map.addLayer(anomaliesLayers[type]);
    });
}

function zoomToVisibleAnomalies() {
    const bounds = [];
    Object.values(anomaliesLayers).forEach(layer => {
        if (map.hasLayer(layer)) {
            layer.eachLayer(m => bounds.push(m.getLatLng()));
        }
    });
    if (bounds.length > 0) map.fitBounds(L.latLngBounds(bounds), { padding: [20, 20] });
}