// Variables globales pour les anomalies
let conduiteAnomaliesMap = {}; // fid -> { severite, types: [] }
let anomalousRegards = new Set();
let anomaliesData = {};
let anomaliesLayers = {};
let currentTab = 'connexions';
        anomalies.forEach(anomalie => {
            let regardIds = [];
            switch (anomalie.type) {
                case 'incoherence_profondeur':
                    if (anomalie.point_connexion) regardIds.push(anomalie.point_connexion);
                    break;
                case 'conduite_sans_regard':
                    if (anomalie.id_amont_manquant) regardIds.push(anomalie.id_amont_manquant);
                    if (anomalie.id_aval_manquant) regardIds.push(anomalie.id_aval_manquant);
                    break;
                case 'champs_manquants_regard':
                    if (anomalie.code) regardIds.push(anomalie.code);
                    break;
                default:
                    break;
            }
            regardIds.forEach(id => {
                if (id) anomalousRegards.add(id.toString());
            });
        });
    }
    console.log(`Total anomalous regards: ${anomalousRegards.size}`);
}

function buildAnomaliesMaps(data) {
    anomaliesData = data;
    anomalousRegards = new Set();
    conduiteAnomaliesMap = {};
    
    if (!data) return;

    for (const [category, anomalies] of Object.entries(data)) {
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
                    if (severities[anom.severite] > severities[conduiteAnomaliesMap[fid].severite]) {
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
    if (conduitesLayer) {
        conduitesLayer.setStyle(feature => getConduiteStyle(feature));
    }

    // 2. Mettre à jour les marqueurs ponctuels pour les anomalies non-conduites
    // (On garde les cercles pour les regards ou points spécifiques)
    try {
        for (const [typeAnomalie, anomalies] of Object.entries(anomaliesData)) {
            const markers = [];
            anomalies.forEach(anomalie => {
                if (!shouldShowAnomalie(anomalie)) return;

                // Si c'est une anomalie de conduite, on la montre déjà via le style de la ligne
                // sauf si c'est une connexion manquante (où on veut voir le point)
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
            if (markers.length > 0 && tabMappings[currentTab].includes(typeAnomalie)) {
                map.addLayer(anomaliesLayers[typeAnomalie]);
            }
        }
    } catch (e) { console.error('Error updating layers:', e); }
}

function findRegardCoords(regardId) {
    let result = null;
    if (!regardsLayer) return null;
    regardsLayer.eachLayer(layer => {
        if (layer.feature && layer.feature.properties) {
            const props = layer.feature.properties;
            const strId = regardId.toString();
            if ((props.id && props.id.toString() === strId) ||
                (props.fid && props.fid.toString() === strId) ||
                (props.code && props.code.toString() === strId)) {
                const ll = layer.getLatLng();
                result = [ll.lat, ll.lng];
            }
        }
    });
    return result;
}

function findConduiteCoords(conduiteId) {
    let result = null;
    if (!conduitesLayer) return null;
    conduitesLayer.eachLayer(layer => {
        if (layer.feature && layer.feature.properties) {
            const props = layer.feature.properties;
            const strId = conduiteId.toString();
            if ((props.id && props.id.toString() === strId) ||
                (props.fid && props.fid.toString() === strId)) {
                if (layer.getBounds) {
                    const center = layer.getBounds().getCenter();
                    result = [center.lat, center.lng];
                }
            }
        }
    });
    return result;
}

function findAnomalieCoords(anomalie) {
    if (anomalie.latitude !== undefined && anomalie.latitude !== null &&
        anomalie.longitude !== undefined && anomalie.longitude !== null) {
        return [anomalie.latitude, anomalie.longitude];
    }
    if (anomalie.type === 'incoherence_profondeur') {
        if (anomalie.point_connexion) {
            var coords = findRegardCoords(anomalie.point_connexion);
            if (coords) return coords;
        }
    }
    if (anomalie.id_conduite) return findConduiteCoords(anomalie.id_conduite);
    if (anomalie.id_regard) return findRegardCoords(anomalie.id_regard);
    if (anomalie.point_connexion) return findRegardCoords(anomalie.point_connexion);
    if (anomalie.fid) return findConduiteCoords(anomalie.fid);
    if (anomalie.code) return findRegardCoords(anomalie.code);
    return null;
}

function shouldShowAnomalie(anomalie) {
    const anyTypeChecked = ['type-conduites_sans_regards', 'type-troncons_orphelins', 'type-champs_manquants', 'type-pentes_suspectes', 'type-geometries_invalides', 'type-incoherences_amont_aval'].some(id => document.getElementById(id)?.checked);
    if (anyTypeChecked) {
        const group = getAnomalieGroup(anomalie.type);
        if (!document.getElementById(`type-${group}`)?.checked) return false;
    }

    const anySeveriteChecked = ['anomalies-critiques', 'anomalies-majeures', 'anomalies-mineures'].some(id => document.getElementById(id)?.checked);
    if (anySeveriteChecked) {
        if (!document.getElementById(`anomalies-${anomalie.severite}s`)?.checked) return false;
    }
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

function getAnomalieColor(severite) {
    const colors = { 'critique': '#f44336', 'majeure': '#ff9800', 'mineure': '#4caf50' };
    return colors[severite] || '#666';
}

function calculateTabStats(tabName) {
    if (!anomaliesData) return;
    const activeTypes = tabMappings[tabName] || [];
    let total = 0, critiques = 0, majeures = 0, mineures = 0;

    activeTypes.forEach(type => {
        const anomalies = anomaliesData[type] || [];
        anomalies.forEach(anomalie => {
            total++;
            if (anomalie.severite === 'critique') critiques++;
            else if (anomalie.severite === 'majeure') majeures++;
            else if (anomalie.severite === 'mineure') mineures++;
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
    Object.values(anomaliesLayers).forEach(layer => { if (map.hasLayer(layer)) map.removeLayer(layer); });
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