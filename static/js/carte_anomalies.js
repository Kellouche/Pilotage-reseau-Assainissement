
// Variables globales pour les anomalies
let conduiteAnomaliesMap = {}; // fid -> { severite, types: [] }
let anomalousRegards = new Set();
let anomaliesData = {};
let anomaliesLayers = {};

// Highlight used when zooming to a conduite/regard
let currentGeometryHighlight = null;

// Correction modal state
let currentCorrectionId = null;
let currentCorrectionType = null;

function applyFilters() {
    console.log('Applying filters manually...');
    if (typeof updateLayersVisibility === 'function') updateLayersVisibility();
    if (typeof updateAnomaliesLayers === 'function') updateAnomaliesLayers();
}

// Traite les anomalies par lots pour ne pas bloquer le thread principal
const CHUNK_SIZE = 500; // anomalies traitées par intervalle

function buildAnomaliesMaps(data) {
    if (!data) return;
    const anomsByType = data.anomalies || data;

    anomaliesData = anomsByType;
    anomalousRegards = new Set();
    conduiteAnomaliesMap = {};

    // Nettoyer les couches précédentes
    Object.values(anomaliesLayers).forEach(l => {
        if (map && map.hasLayer(l)) map.removeLayer(l);
    });
    anomaliesLayers = {};

    // Aplatir toutes les anomalies en un seul tableau avec leur catégorie
    const flatAnomalies = [];
    for (const [category, anomalies] of Object.entries(anomsByType)) {
        if (!Array.isArray(anomalies)) continue;
        anomalies.forEach(anom => flatAnomalies.push({ anom, category }));
    }

    let index = 0;
    const allMarkersByCategory = {};

    function processChunk() {
        const end = Math.min(index + CHUNK_SIZE, flatAnomalies.length);
        for (; index < end; index++) {
            const { anom, category } = flatAnomalies[index];
            const group = category;

            // Mapping des regards
            const regardId = anom.id_regard || anom.code || anom.point_connexion || anom.id_amont_manquant || anom.id_aval_manquant;
            if (regardId) anomalousRegards.add(regardId.toString());

            // Mapping des conduites (Multi-ID pour les incohérences)
            const ids = [
                anom.id_conduite, anom.fid, anom.code,
                anom.id_conduite1, anom.fid1,
                anom.id_conduite2, anom.fid2
            ].filter(v => v !== undefined && v !== null && v !== '');

            ids.forEach(cid => {
                const fid = cid.toString();
                if (!conduiteAnomaliesMap[fid]) {
                    conduiteAnomaliesMap[fid] = { severite: anom.severite, types: [group] };
                } else {
                    if (!conduiteAnomaliesMap[fid].types.includes(group)) {
                        conduiteAnomaliesMap[fid].types.push(group);
                    }
                    const severities = { 'critique': 3, 'majeure': 2, 'mineure': 1 };
                    if (severities[anom.severite] > severities[conduiteAnomaliesMap[fid].severite]) {
                        conduiteAnomaliesMap[fid].severite = anom.severite;
                    }
                }
            });

            // CRÉATION DES MARQUEURS (différée par lots)
            const isConduiteAnom = [
                'pente_negative',
                'pente_trop_forte',
                'champs_manquants_conduite',
                'troncon_orphelin',
                'conduite_sans_regard'
            ].includes(anom.type);

            if (!isConduiteAnom) {
                let coords = findAnomalieCoords(anom);
                if (coords) {
                    const color = getAnomalieColor(anom.severite);
                    const marker = L.circleMarker(coords, {
                        color: color, fillColor: color, fillOpacity: 0.8, radius: 8, weight: 2
                    });
                    marker.bindPopup(createAnomaliePopup(anom));
                    marker._isPointAnom = !!(anom.id_regard || anom.code || anom.point_connexion || anom.type === 'champs_manquants_regard' || anom.type === 'incoherence_profondeur');
                    marker._pointType = 'regard';
                    if (anom.type && anom.type.includes('station')) marker._pointType = 'station';
                    if (anom.type && anom.type.includes('step')) marker._pointType = 'step';
                    if (anom.type && anom.type.includes('ouvrage')) marker._pointType = 'ouvrage';

                    if (!allMarkersByCategory[group]) allMarkersByCategory[group] = [];
                    allMarkersByCategory[group].push(marker);
                }
            }
        }

        if (index < flatAnomalies.length) {
            // Céder la main au navigateur avant le prochain lot
            setTimeout(processChunk, 0);
        } else {
            // Tous les marqueurs créés : assembler les layerGroups
            for (const [category, markers] of Object.entries(allMarkersByCategory)) {
                if (markers.length > 0) {
                    anomaliesLayers[category] = L.layerGroup(markers);
                }
            }
            console.log("Anomalies maps and layers built:", {
                regards: anomalousRegards.size,
                conduites: Object.keys(conduiteAnomaliesMap).length,
                layers: Object.keys(anomaliesLayers).length
            });

        }
    }

    processChunk();
}

function updateAnomaliesLayers() {
    if (!anomaliesData) return;

    if (typeof precomputeConduiteStyles === 'function') {
        precomputeConduiteStyles();
    }

    // 1. Mettre à jour le style des conduites (Couleurs de diagnostic)
    // RÈGLE : Si la couche globale "Conduite" est décochée, on ne colorie rien
    const showConduitesGlobal = document.getElementById('layer-conduites')?.checked;
    if (typeof conduitesLayer !== 'undefined' && conduitesLayer) {
        if (showConduitesGlobal === false) {
            // Style neutre forcé
            conduitesLayer.setStyle({ color: '#bdc3c7', weight: 2, opacity: 0.6 });
        } else {
            conduitesLayer.setStyle(feature => getConduiteStyle(feature));
        }
    }

    // 2. Gérer la visibilité des couches de marqueurs pré-calculées
    const showRegardsGlobal = document.getElementById('layer-regards')?.checked;
    const showStationsGlobal = document.getElementById('layer-stations')?.checked;
    const showStepGlobal = document.getElementById('layer-step')?.checked;
    const showOuvragesGlobal = document.getElementById('layer-ouvrages')?.checked;

    try {
        Object.entries(anomaliesLayers).forEach(([group, layer]) => {
            const typeEl = document.getElementById(`type-${group}`);
            const isGroupChecked = typeEl && typeEl.checked;

            if (isGroupChecked) {
                if (!map.hasLayer(layer)) layer.addTo(map);

                layer.eachLayer(marker => {
                    let visible = true;
                    if (marker._isPointAnom) {
                        if (marker._pointType === 'station' && !showStationsGlobal) visible = false;
                        else if (marker._pointType === 'step' && !showStepGlobal) visible = false;
                        else if (marker._pointType === 'ouvrage' && !showOuvragesGlobal) visible = false;
                        else if (!showRegardsGlobal) visible = false;
                    }

                    if (visible) {
                        marker.setOpacity(1);
                        if (marker.getElement) marker.getElement().style.display = 'block';
                    } else {
                        marker.setOpacity(0);
                        if (marker.getElement) marker.getElement().style.display = 'none';
                    }
                });
            } else {
                if (map.hasLayer(layer)) map.removeLayer(layer);
            }
        });
    } catch (e) { console.error('Error updating anomaly layers:', e); }
}

// Lookup O(1) via les maps préconstruites (voir carte_core.js)
function findRegardCoords(regardId) {
    if (!regardId) return null;
    return regardsCoordsMap[regardId.toString()] || null;
}

function findConduiteCoords(conduiteId) {
    if (!conduiteId) return null;
    return conduitesCoordsLookup[conduiteId.toString()] || null;
}

function findAnomalieCoords(anomalie) {
    if (anomalie.latitude && anomalie.longitude) return [anomalie.latitude, anomalie.longitude];
    const id = anomalie.id_regard || anomalie.code || anomalie.point_connexion || anomalie.id_amont_manquant || anomalie.id_aval_manquant;
    if (id) {
        const coords = findRegardCoords(id);
        if (coords) return coords;
    }
    const cid = anomalie.id_conduite || anomalie.fid || anomalie.fid1 || anomalie.fid2;
    if (cid) {
        const coords = findConduiteCoords(cid);
        if (coords) return coords;
    }
    return null;
}

function shouldShowAnomalie(anomalie, group) {
    // 1. Filtre par type d'anomalie (cochage dans le panneau diagnostic)
    const typeEl = document.getElementById(`type-${group}`);
    if (typeEl && !typeEl.checked) return false;

    // 2. Filtre par couche globale (Options avancées)
    // Si c'est une anomalie liée à un regard, vérifier si la couche Regards est cochée
    const isRegardAnom = !!(anomalie.id_regard || anomalie.code || anomalie.point_connexion || anomalie.type === 'champs_manquants_regard');
    if (isRegardAnom) {
        const showRegards = document.getElementById('layer-regards')?.checked;
        if (showRegards === false) return false;
    }

    return true;
}

function getAnomalieColor(severite) {
    const colors = {
        'critique': '#e74c3c', // Rouge vif
        'majeure': '#e67e22',  // Orange
        'mineure': '#2ecc71'   // Vert
    };
    return colors[severite] || '#95a5a6';
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
        const count = anomalies.length;

        const countEl = document.getElementById(`count-${type}`);
        if (countEl) {
            countEl.textContent = `(${count})`;
            countEl.style.color = count > 0 ? '#16213e' : '#ccc';
            countEl.style.fontSize = '11px';
            countEl.style.marginLeft = '4px';
        }

        const cbEl = document.getElementById(`type-${type}`);
        if (cbEl) {
            cbEl.disabled = (count === 0);
            if (count === 0) {
                cbEl.checked = false;
                cbEl.parentElement.style.opacity = '0.5';
            } else {
                cbEl.parentElement.style.opacity = '1';
            }
        }

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
    Object.values(anomaliesLayers).forEach(layer => {
        if (map.hasLayer(layer)) map.removeLayer(layer);
    });

    const activeTypes = tabMappings[currentTab] || [];
    activeTypes.forEach(type => {
        if (anomaliesLayers[type]) map.addLayer(anomaliesLayers[type]);
    });
}

function zoomToVisibleAnomalies() {
    console.log('Zooming on visible anomalies for tab:', currentTab);
    const bounds = L.latLngBounds([]);
    let count = 0;

    // 1. Marqueurs ponctuels
    Object.values(anomaliesLayers).forEach(layer => {
        if (map.hasLayer(layer)) {
            layer.eachLayer(m => {
                if (m.getLatLng) {
                    bounds.extend(m.getLatLng());
                    count++;
                }
            });
        }
    });

    // 2. Conduites coloriées (fallback)
    if (count < 20 && conduitesLayer && map.hasLayer(conduitesLayer)) {
        const activeTypesInTab = tabMappings[currentTab] || [];
        conduitesLayer.eachLayer(layer => {
            const props = layer.feature.properties;
            // Utiliser la même logique que getConduiteStyle
            const idCandidates = [layer.feature.id, props.fid, props.FID, props.id, props.ID, props.OBJECTID, props.code, props.ID_CANALIS];
            let fid = null;
            for (let cand of idCandidates) {
                if (cand !== undefined && cand !== null && cand !== '' && conduiteAnomaliesMap[cand.toString()]) {
                    fid = cand.toString();
                    break;
                }
            }

            if (fid) {
                const anom = conduiteAnomaliesMap[fid];
                const isVisible = anom.types.some(t => activeTypesInTab.includes(t) && document.getElementById(`type-${t}`)?.checked);
                if (isVisible && layer.getBounds) {
                    bounds.extend(layer.getBounds());
                    count++;
                }
            }
        });
    }

    console.log(`Zoom logic found ${count} matching elements.`);

    if (count > 0 && bounds.isValid()) {
        map.fitBounds(bounds, { padding: [40, 40] });
    } else {
        console.warn('No visible anomalies found to zoom on.');
        if (typeof centerOnData === 'function') centerOnData();
    }
}

function findLayerById(layer, id) {
    if (!layer || id === undefined || id === null) return null;
    const key = id.toString();

    // Utiliser la map de lookup O(1) si c'est une couche connue
    if (layer === regardsLayer) return regardsLayerMap[key] || null;
    if (layer === conduitesLayer) return conduitesLayerMap[key] || null;

    // Fallback : itération (pour couches inconnues)
    let found = null;
    layer.eachLayer(l => {
        try {
            const props = (l.feature && l.feature.properties) || {};
            const candidates = [l.feature && l.feature.id, props.fid, props.FID, props.id, props.ID, props.ID_AMONT, props.ID_AVAL, props.code, props.CODE, props.LINEAIRE];
            for (let c of candidates) {
                if (c !== undefined && c !== null && c.toString() === id.toString()) {
                    found = l; break;
                }
            }
        } catch (e) { }
    });
    return found;
}

function getAnomalieConduiteIds(anom) {
    return [anom.id_conduite, anom.fid, anom.code, anom.id_conduite1, anom.fid1, anom.id_conduite2, anom.fid2, anom.ID_AMONT, anom.ID_AVAL].filter(v => v !== undefined && v !== null && v !== '');
}

function findConduiteByCoords(lat, lng) {
    if (!conduitesLayer) return null;
    let best = null; let bestDist = Infinity;
    const target = [lat, lng];
    conduitesLayer.eachLayer(l => {
        try {
            const bounds = l.getBounds && l.getBounds();
            if (bounds) {
                const c = bounds.getCenter();
                const dlat = c.lat - lat; const dlng = c.lng - lng; const d = Math.sqrt(dlat * dlat + dlng * dlng);
                if (d < bestDist) { bestDist = d; best = (l.feature && (l.feature.properties && (l.feature.properties.fid || l.feature.properties.FID || l.feature.properties.id))) || best; }
            }
        } catch (e) { }
    });
    return best;
}

const SEVERITY_ORDER = { 'critique': 0, 'majeure': 1, 'mineure': 2, 'info': 3 };

// Cache des suggestions de profil par fid (évite de re-appeler l'API pour chaque anomalie)
const _suggestionCache = {};

// Pré-charge les suggestions pour un ensemble de fids de conduite (appels parallèles limités)
async function prefetchSuggestions(fids) {
    const uniqueFids = [...new Set(fids.filter(f => f && !_suggestionCache[f]))];
    if (uniqueFids.length === 0) return;
    const CONCURRENCY = 5;
    for (let i = 0; i < uniqueFids.length; i += CONCURRENCY) {
        const batch = uniqueFids.slice(i, i + CONCURRENCY);
        await Promise.all(batch.map(async fid => {
            try {
                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), 8000);
                const res = await fetch(`/api/v1/corrections/hybride/suggest?fid=${encodeURIComponent(fid)}&anomalie_type=conduite`, { signal: controller.signal });
                clearTimeout(timer);
                if (res.ok) {
                    const data = await res.json();
                    _suggestionCache[fid] = (data.suggestion && data.suggestion.available) || false;
                } else {
                    _suggestionCache[fid] = false;
                }
            } catch {
                _suggestionCache[fid] = false;
            }
        }));
    }
}

// Vrai si l'anomalie concerne une conduite qui a une suggestion de profil
function hasProfileSuggestion(anom) {
    const fid = anom.fid || anom.id_conduite || anom.fid1 || anom.fid2;
    return !!fid && !!_suggestionCache[fid.toString()];
}

function sortAnomaliesBySeverityThenId(anoms) {
    return [...anoms].sort((a, b) => {
        const sa = SEVERITY_ORDER[a.severite || 'info'] ?? 9;
        const sb = SEVERITY_ORDER[b.severite || 'info'] ?? 9;
        if (sa !== sb) return sa - sb;
        // Même sévérité : tri par code objet (fid > id_conduite > id_regard > code)
        const aid = a.fid || a.id_conduite || a.id_regard || a.code || a.point_connexion || '';
        const bid = b.fid || b.id_conduite || b.id_regard || b.code || b.point_connexion || '';
        return String(aid).localeCompare(String(bid));
    });
}

async function populateAnomaliesLists(data) {
    console.log('Populating anomalies lists with data:', Object.keys(data || {}));
    const tabMappings = {
        'connexions': ['conduites_sans_regards', 'incoherences_amont_aval'],
        'geometrie': ['geometries_invalides', 'pentes_suspectes'],
        'donnees': ['champs_manquants'],
        'topologie': ['troncons_orphelins']
    };

    // 1. Pré-charger les suggestions de profil pour toutes les conduites concernées
    //    (appels parallèles, pas d'attente séquentielle)
    const allFids = [];
    Object.values(data || {}).forEach(anoms => {
        if (!Array.isArray(anoms)) return;
        anoms.forEach(anom => {
            const fid = anom.fid || anom.id_conduite || anom.fid1 || anom.fid2;
            if (fid) allFids.push(fid.toString());
        });
    });
    if (allFids.length > 0) {
        await prefetchSuggestions(allFids);
    }

    Object.entries(tabMappings).forEach(([tab, types]) => {
        const select = document.getElementById(`select-anomalies-${tab}`);
        const container = document.getElementById(`list-container-${tab}`);
        if (!select || !container) {
            console.warn(`Elements for tab ${tab} not found: select=${!!select}, container=${!!container}`);
            return;
        }

        // Vider la liste
        select.innerHTML = '<option value="">-- Sélectionner une anomalie --</option>';

        let count = 0;
        types.forEach(type => {
            const anoms = data[type];
            if (!Array.isArray(anoms)) return;

            // Trier par sévérité (critique → majeure → mineure) puis par code objet
            const sorted = sortAnomaliesBySeverityThenId(anoms);

            console.log(`Tab ${tab}: found ${sorted.length} anomalies of type ${type}`);
            sorted.forEach(anom => {
                // Try to find coords from anomaly, otherwise try to locate feature by id in layers
                let coords = findAnomalieCoords(anom);
                if (!coords) {
                    try {
                        const candidateIds = getAnomalieConduiteIds(anom);
                        for (const cid of candidateIds) {
                            const layerFound = (typeof findLayerById === 'function') ? (findLayerById(conduitesLayer, cid) || findLayerById(regardsLayer, cid)) : null;
                            if (layerFound) {
                                if (layerFound.getBounds) {
                                    const c = layerFound.getBounds().getCenter();
                                    coords = [c.lat, c.lng];
                                } else if (layerFound.getLatLng) {
                                    const ll = layerFound.getLatLng();
                                    coords = [ll.lat, ll.lng];
                                }
                                if (coords) break;
                            }
                        }
                    } catch (e) { /* ignore */ }
                }

                const id = (typeof normalizeId === 'function') ? (normalizeId(anom.fid || anom.code || anom.identifiant || anom.id_conduite || anom.fid1) || 'Inconnu') : (anom.fid || anom.code || anom.identifiant || anom.id_conduite || anom.fid1 || 'Inconnu');
                const option = document.createElement('option');
                if (coords) {
                    option.value = `${id}|${coords[0]},${coords[1]}`;
                } else {
                    option.value = `${id}`;
                }

                // ⭐ Étoile si la conduite a une suggestion de profil disponible
                const star = hasProfileSuggestion(anom) ? ' ⭐' : '';

                let label = `[${(anom.severite || 'info').toUpperCase()}] ${getAnomalieTitre(anom)} - ID: ${id}${star}`;
                if (anom.type === 'incoherence_profondeur') {
                    label = `[Saut] FID ${anom.fid1 || '?'} / ${anom.fid2 || '?'} `;
                }

                option.textContent = label;
                select.appendChild(option);
                count++;
            });
        });

        console.log(`Tab ${tab}: total anomalies with coords = ${count}`);
        container.style.display = count > 0 ? 'block' : 'none';
    });
}

function zoomToAnomalie(valueStr) {
    if (!valueStr) return;

    // value can be "id|lat,lng" or "lat,lng" or just an id
    let targetId = null;
    let lat = null, lng = null;

    if (valueStr.includes('|')) {
        const parts = valueStr.split('|');
        targetId = parts[0];
        const coords = parts[1].split(',').map(Number);
        if (coords.length === 2) { lat = coords[0]; lng = coords[1]; }
    } else if (valueStr.includes(',')) {
        const coords = valueStr.split(',').map(Number);
        if (coords.length === 2) { lat = coords[0]; lng = coords[1]; }
    } else {
        targetId = valueStr;
    }

    if (lat !== null && lng !== null) {
        map.setView([lat, lng], 18);
    }

    // Nettoyer ancien highlight
    if (currentGeometryHighlight && map.hasLayer(currentGeometryHighlight)) {
        map.removeLayer(currentGeometryHighlight);
        currentGeometryHighlight = null;
    }

    // Si on a un ID, tenter de trouver la géométrie et la surligner
    let foundLayer = null;
    if (targetId && typeof findLayerById === 'function') {
        // try exact find
        foundLayer = findLayerById(conduitesLayer, targetId) || findLayerById(regardsLayer, targetId);
        // fallback: try numeric comparisons or property-based match
        if (!foundLayer && conduitesLayer && conduitesLayer.eachLayer) {
            conduitesLayer.eachLayer(l => {
                try {
                    const p = l.feature && l.feature.properties || {};
                    const candidates = [p.fid, p.FID, p.id, p.ID, p.ID_AMONT, p.ID_AVAL, p.CODE, p.code, l.feature && l.feature.id];
                    for (let c of candidates) {
                        if (c !== undefined && c !== null && c.toString() === targetId.toString()) { foundLayer = l; break; }
                    }
                } catch (e) { }
            });
        }

        if (foundLayer) {
            if (foundLayer.getLatLngs) {
                currentGeometryHighlight = L.polyline(foundLayer.getLatLngs(), { color: '#ff0000', weight: 12, opacity: 0.8, dashArray: '10,15' }).addTo(map);
            } else if (foundLayer.getLatLng) {
                currentGeometryHighlight = L.circleMarker(foundLayer.getLatLng(), { radius: 20, color: '#ff0000', weight: 5, opacity: 0.9, fillColor: 'transparent' }).addTo(map);
            }
        }

        // Toujours tenter d'ouvrir la modal de correction (fallback si aucune géométrie trouvée)
        try {
            setTimeout(() => {
                if (typeof openCorrectionModal === 'function') {
                    openCorrectionModal(targetId, 'conduite');
                }
            }, 250);
        } catch (e) { console.warn('openCorrectionModal failed', e); }
    } else if (targetId) {
        // if we only have an id and not found, still try open modal
        try { setTimeout(() => { if (typeof openCorrectionModal === 'function') openCorrectionModal(targetId, 'conduite'); }, 250); } catch (e) { }
    }

    // Attendre un peu que le zoom se termine pour ouvrir le popup si un marqueur ponctuel existe
    setTimeout(() => {
        let popupOpened = false;
        if (lat !== null && lng !== null) {
            Object.values(anomaliesLayers).forEach(layer => {
                if (typeof layer.eachLayer === 'function') {
                    layer.eachLayer(marker => {
                        if (typeof marker.getLatLng === 'function') {
                            const ll = marker.getLatLng();
                            if (Math.abs(ll.lat - lat) < 0.0001 && Math.abs(ll.lng - lng) < 0.0001) {
                                marker.openPopup();
                                popupOpened = true;
                            }
                        }
                    });
                }
            });
        }

        // Si pas de popup mais surlignage existant, ouvrir une bulle temporaire
        if (!popupOpened && currentGeometryHighlight) {
            try { currentGeometryHighlight.bindPopup(`<b>Objet ciblé : ${targetId || 'Inconnu'}</b>`).openPopup(); } catch (e) { }
        }
    }, 500);
}