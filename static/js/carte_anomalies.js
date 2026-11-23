/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Gestion de l'affichage et du traitement cartographique des anomalies
 * ================================================================================
 */

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
            // On veut afficher une icône visuelle pour TOUTES les anomalies,
            // y compris celles sur les conduites (au centre géométrique).
            let coords = findAnomalieCoords(anom);
            if (coords) {
                const icones = {
                    incoherence_profondeur_topologie: '⚠️',
                    incoherence_profondeur: '⚠️',
                    incoherences_amont_aval: '⚠️',
                    chevauchement_geometrique: '🔀',
                    doublon_regards: '🔄',
                    pente_negative: '📉',
                    pente_trop_forte: '🎢',
                    pentes_suspectes: '🎢',
                    pente_trop_faible: '📉',
                    saut_pente: '⛰️',
                    conduite_sans_regard: '❓',
                    conduites_sans_regards: '❓',
                    troncon_orphelin: '❓',
                    troncons_orphelins: '❓',
                    regard_orphelin: '🕳️',
                    orphelins_regards: '🕳️',
                    orphelins_troncons: '❓',
                    geometrie_invalide: '❌',
                    geometries_invalides: '❌',
                    champs_manquants_conduite: '📝',
                    champs_manquants_regard: '📝',
                    champs_manquants: '📝',
                    capacite_debit: '💧'
                };
                
                const icone = icones[anom.type] || icones[group] || '🚨';
                const color = getAnomalieColor(anom.severite);
                
                const divIcon = L.divIcon({
                    html: `<div style="font-size:16px;background:white;border-radius:50%;width:24px;height:24px;display:flex;align-items:center;justify-content:center;box-shadow:0 0 5px rgba(0,0,0,0.5);border:2px solid ${color};">${icone}</div>`,
                    className: '',
                    iconSize: [24, 24],
                    iconAnchor: [12, 12]
                });

                const marker = L.marker(coords, { icon: divIcon });
                marker.bindPopup(createAnomaliePopup(anom));
                marker._isPointAnom = !!(anom.id_regard || anom.code || anom.point_connexion || anom.id_regard1 || anom.type === 'champs_manquants_regard' || anom.type === 'incoherence_profondeur');
                marker._pointType = 'regard';
                if (anom.type && anom.type.includes('station')) marker._pointType = 'station';
                if (anom.type && anom.type.includes('step')) marker._pointType = 'step';
                if (anom.type && anom.type.includes('ouvrage')) marker._pointType = 'ouvrage';

                if (!allMarkersByCategory[group]) allMarkersByCategory[group] = [];
                allMarkersByCategory[group].push(marker);
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
    const showConduitesGlobal = document.getElementById('layer-conduites')?.checked ?? true;
    if (typeof conduitesLayer !== 'undefined' && conduitesLayer) {
        if (showConduitesGlobal === false) {
            // Style neutre forcé
            conduitesLayer.setStyle({ color: '#bdc3c7', weight: 2, opacity: 0.6 });
        } else {
            conduitesLayer.setStyle(feature => getConduiteStyle(feature));
        }
    }

    // 2. Gérer la visibilité des couches de marqueurs pré-calculées
    const showRegardsGlobal = document.getElementById('layer-regards')?.checked ?? true;
    const showStationsGlobal = document.getElementById('layer-stations')?.checked ?? true;
    const showStepGlobal = document.getElementById('layer-step')?.checked ?? true;
    const showOuvragesGlobal = document.getElementById('layer-ouvrages')?.checked ?? true;

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
    const id = anomalie.id_regard || anomalie.code || anomalie.point_connexion || anomalie.id_amont_manquant || anomalie.id_aval_manquant || anomalie.id_regard1;
    if (id) {
        const coords = findRegardCoords(id);
        if (coords) return coords;
    }
    const cid = anomalie.id_conduite || anomalie.fid || anomalie.fid1 || anomalie.fid2 || anomalie.id_conduite1 || anomalie.id_conduite2;
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
        const showRegards = document.getElementById('layer-regards')?.checked ?? true;
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
        'regard_orphelin': 'Nœud isolé (orphelin)',
        'champs_manquants_conduite': 'Données incomplètes (conduite)',
        'champs_manquants_regard': 'Données incomplètes (regard)',
        'geometrie_invalide': 'Position invalide',
        'pente_negative': 'Pente négative',
        'pente_trop_forte': 'Pente excessive',
        'incoherence_profondeur': 'Connexion incohérente',
        // Phase 1 - Fondations topologiques
        'incoherence_profondeur_topologie': 'Dénivellation excessive',
        'chevauchement_geometrique': 'Chevauchement géométrique',
        'doublon_regards': 'Doublons regards'
    };
    return titres[anomalie.type] || anomalie.type;
}

function getAnomalieDescription(anomalie) {
    if (anomalie.description) return anomalie.description;
    // Phase 1 descriptions
    if (anomalie.type === 'incoherence_profondeur_topologie') {
        return `Écart: ${anomalie.difference || (anomalie.details && anomalie.details.difference) || 0}m`;
    }
    if (anomalie.type === 'chevauchement_geometrique') {
        return `Distance: ${anomalie.distance_min || 0}m`;
    }
    if (anomalie.type === 'doublon_regards') {
        return `Distance: ${anomalie.distance || 0}m`;
    }
    
    if (anomalie.champs_manquants) return `Champs manquants: ${anomalie.champs_manquants.join(", ")}`;
    if (anomalie.pente_pourcent !== undefined) return `Pente: ${anomalie.pente_pourcent.toFixed(1)}%`;
    if (anomalie.difference) return `Écart: ${anomalie.difference.toFixed(2)}m`;
    return 'Anomalie détectée';
}


function updateVisibleCount() {
    const activeTypes = tabMappings[currentTab] || [];
    activeTypes.forEach(type => {
        const layer = anomaliesLayers[type];
        const countEl = document.getElementById(`count-${type}`);
        if (!countEl) return;
        let visibleCount = 0;
        if (layer && typeof map !== 'undefined' && map.hasLayer(layer)) {
            layer.eachLayer(marker => {
                let visible = true;
                if (marker._isPointAnom) {
                    if (marker._pointType === 'station' && !(document.getElementById('layer-stations')?.checked)) visible = false;
                    else if (marker._pointType === 'step' && !(document.getElementById('layer-step')?.checked)) visible = false;
                    else if (marker._pointType === 'ouvrage' && !(document.getElementById('layer-ouvrages')?.checked)) visible = false;
                    else if (!(document.getElementById('layer-regards')?.checked)) visible = false;
                }
                if (visible) visibleCount++;
            });
        }
        countEl.textContent = `(${visibleCount})`;
        countEl.style.color = visibleCount > 0 ? '#16213e' : '#ccc';
    });
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
            if (scoreEl && data.global) {
                let score = data.global.score_qualite;
                if (typeof score === 'string') score = score.replace(',', '.');
                const scoreFmt = Number(score || 0).toFixed(1);
                scoreEl.textContent = `${scoreFmt}%`;
            }
            if (totalEl && data.global) totalEl.textContent = data.global.total_anomalies;
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

let suggestableFidsFetched = false;

async function fetchSuggestableFids() {
    if (suggestableFidsFetched) return;
    try {
        const res = await fetch('/api/v1/corrections/hybride/suggestable_fids');
        if (res.ok) {
            const data = await res.json();
            const fids = data.suggestable_fids || [];
            fids.forEach(fid => {
                _suggestionCache[fid] = true;
            });
            suggestableFidsFetched = true;
            
            // Mettre à jour l'UI uniquement pour les options qui ont une suggestion fiable disponible
            document.querySelectorAll('select[id^="select-anomalies-"] option').forEach(opt => {
                if (!opt.value) return;
                const fid = opt.value.split('|')[0];
                if (_suggestionCache[fid] && !opt.textContent.includes('⭐')) {
                    opt.textContent = opt.textContent + ' ⭐';
                }
            });
        }
    } catch (e) {
        console.error("Erreur lors de la récupération des FIDs suggestibles:", e);
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
        'geometrie': ['geometries_invalides', 'pentes_suspectes', 'capacite_debit', 'sauts_pente'],
        'donnees': ['champs_manquants'],
        'topologie': ['troncons_orphelins', 'incoherence_profondeur_topologie', 'chevauchement_geometrique', 'doublon_regards']
        // 'orphelins' est exclu : cet onglet possède son propre listing
        // cliquable (rendreListeOrphelins / localiserOrphelin).
    };

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
                option.dataset.anomalieType = anom.type;
                option.dataset.anomalieSeverite = anom.severite;
                select.appendChild(option);
                count++;
            });
        });

        console.log(`Tab ${tab}: total anomalies with coords = ${count}`);
        container.style.display = count > 0 ? 'block' : 'none';
    });

    // Lancer la récupération globale de toutes les étoiles (1 seule requête rapide !)
    fetchSuggestableFids();
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
                    // Récupérer le type d'anomalie depuis l'option sélectionnée
                    const sel = document.getElementById(`select-anomalies-${currentTab}`);
                    const optSelected = sel?.options?.[sel.selectedIndex];
                    const anomType = optSelected?.dataset?.anomalieType || 'conduite';
                    openCorrectionModal(targetId, anomType);
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

// ============================================================================
// Éléments orphelins (regards/nœuds isolés + tronçons hors graphe ou sans
// exutoire) — endpoint GET /api/v1/network/orphelins, listing cliquable.
// ============================================================================

// Fusionne la réponse /network/orphelins dans le rapport qualité : les
// éléments orphelins deviennent des catégories d'anomalies natives
// (marqueurs, compteurs, listes déroulantes et onglet dédiés).
function fusionnerOrphelins(anomData, orphelins) {
    if (!anomData || !orphelins) return;
    if (!anomData.anomalies || typeof anomData.anomalies !== 'object') {
        anomData.anomalies = {};
    }
    const anomalies = anomData.anomalies;

    anomalies.orphelins_regards = (orphelins.noeuds_orphelins || []).map(n => {
        const typeLbl = (n.type_noeud || 'noeud').toLowerCase();
        const details = [n.nom, n.nom_voie, n.commune].filter(v => v && String(v).trim() && String(v).trim().toLowerCase() !== 'nan');
        return {
            type: 'regard_orphelin',
            severite: 'majeure',
            id_regard: n.id,
            code: n.id,
            latitude: n.lat,
            longitude: n.lng,
            description: `Nœud ${typeLbl} « ${n.id} » isolé : aucune conduite amont ni aval ne s'y rattache${details.length ? ' — ' + details.join(' · ') : ''}`,
            _orphelin: {
                genre: 'regard',
                id: n.id,
                type_noeud: n.type_noeud,
                nom: n.nom,
                nom_voie: n.nom_voie,
                commune: n.commune,
                lat: n.lat,
                lng: n.lng
            }
        };
    });

    anomalies.orphelins_troncons = (orphelins.troncons_orphelins || []).map(t => {
        const libelle = (t.amont && t.aval) ? `${t.amont} → ${t.aval}` : (t.id || 'tronçon');
        const horsGraphe = t.motif === 'hors_graphe';
        return {
            type: 'troncon_orphelin',
            severite: horsGraphe ? 'majeure' : 'mineure',
            id_conduite: t.id,
            fid: t.id,
            id_amont: t.amont,
            id_aval: t.aval,
            latitude: t.lat,
            longitude: t.lng,
            description: `${t.detail || 'Tronçon orphelin'}${t.type_conduite ? ' · ' + t.type_conduite : ''}${t.longueur_m ? ' · ' + Math.round(t.longueur_m) + ' m' : ''}`,
            _orphelin: {
                genre: 'troncon',
                id: t.id,
                libelle: libelle,
                amont: t.amont,
                aval: t.aval,
                motif: t.motif,
                detail: t.detail,
                type_conduite: t.type_conduite,
                longueur_m: t.longueur_m,
                diametre_mm: t.diametre_mm,
                lat: t.lat,
                lng: t.lng
            }
        };
    });
}

// ---------------------------------------------------------------------------
// Listing cliquable des orphelins
// ---------------------------------------------------------------------------
let _orphelinsItems = [];

function _escHtml(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function _texteRechercheOrphelin(it) {
    const o = it._orphelin || {};
    return [
        o.id, o.libelle, o.amont, o.aval, o.type_noeud, o.nom, o.nom_voie,
        o.commune, o.type_conduite, o.detail
    ].filter(Boolean).join(' ').toLowerCase();
}

function rendreListeOrphelins() {
    const listEl = document.getElementById('orphelins-list');
    const searchWrap = document.getElementById('orphelins-search-container');
    const statsEl = document.getElementById('stats-orphelins');
    if (!listEl) return;

    _orphelinsItems = [];
    const regards = anomaliesData && anomaliesData.orphelins_regards ? anomaliesData.orphelins_regards : [];
    const troncons = anomaliesData && anomaliesData.orphelins_troncons ? anomaliesData.orphelins_troncons : [];

    regards.forEach(a => _orphelinsItems.push(a));
    troncons.forEach(a => _orphelinsItems.push(a));

    const nR = regards.length, nT = troncons.length;
    if (statsEl) {
        statsEl.innerHTML = `
            <div class="diagnostic-stats">
                <div><strong>Total:</strong> ${nR + nT} éléments orphelins</div>
                <div style="color:#e74c3c;"><strong>Nœuds isolés:</strong> ${nR}</div>
                <div style="color:#3498db;"><strong>Tronçons:</strong> ${nT}</div>
            </div>`;
    }

    if (!_orphelinsItems.length) {
        listEl.style.display = 'block';
        listEl.innerHTML = '<div class="orphelins-empty">Aucun élément orphelin détecté — le réseau est entièrement connecté.</div>';
        if (searchWrap) searchWrap.style.display = 'none';
        return;
    }

    if (searchWrap) searchWrap.style.display = 'block';
    const q = (document.getElementById('orphelins-search') || {}).value || '';
    filtrerListeOrphelins(q);
}

function filtrerListeOrphelins(val) {
    const listEl = document.getElementById('orphelins-list');
    if (!listEl) return;
    const q = (typeof val === 'string' ? val : ((document.getElementById('orphelins-search') || {}).value || '')).trim().toLowerCase();

    const visibles = _orphelinsItems.filter(it => !q || _texteRechercheOrphelin(it).includes(q));
    if (!visibles.length) {
        listEl.innerHTML = '<div class="orphelins-empty">Aucun résultat pour ce filtre.</div>';
        return;
    }

    listEl.innerHTML = visibles.map(a => {
        const o = a._orphelin || {};
        const estRegard = o.genre === 'regard';
        const cls = estRegard ? 'orphelin-regard' : (o.motif === 'hors_graphe' ? 'orphelin-hors-graphe' : 'orphelin-troncon');
        const ico = estRegard ? '🕳️' : '❓';
        let titre, sous;
        if (estRegard) {
            titre = `${o.type_noeud === 'regard' || !o.type_noeud ? 'Regard' : o.type_noeud} ${o.id}`;
            sous = [o.nom, o.nom_voie, o.commune].filter(v => v && String(v).trim() && String(v).trim().toLowerCase() !== 'nan').join(' · ') || 'aucune connexion';
        } else {
            titre = o.libelle || `Tronçon ${o.id}`;
            const motifTxt = o.motif === 'hors_graphe' ? 'hors graphe (extrémité non résolue)' : 'composante sans exutoire';
            const tech = [o.type_conduite, o.longueur_m ? Math.round(o.longueur_m) + ' m' : null, o.diametre_mm ? 'Ø' + o.diametre_mm : null].filter(Boolean).join(' · ');
            sous = [motifTxt, tech].filter(Boolean).join(' — ');
        }
        return `<div class="orphelin-item ${cls}" data-idx="${_orphelinsItems.indexOf(a)}" title="${_escHtml(a.description || titre)}">
            <span class="orphelin-ico">${ico}</span>
            <span class="orphelin-main">
                <span class="orphelin-titre">${_escHtml(titre)}</span><br>
                <span class="orphelin-sous">${_escHtml(sous)}</span>
            </span>
            <span class="orphelin-zoom"><i class="fas fa-map-marker-alt"></i></span>
        </div>`;
    }).join('');

    listEl.querySelectorAll('.orphelin-item').forEach(el => {
        el.addEventListener('click', () => {
            const it = _orphelinsItems[parseInt(el.dataset.idx, 10)];
            if (it) localiserOrphelin(it);
        });
    });
}

// ---------------------------------------------------------------------------
// Localisation sur la carte active — fonctionne sur n'importe quelle carte
// Leaflet exposée (window.carte du cockpit, window.map ou `map` global).
// ---------------------------------------------------------------------------
let _orphelinPulse = null;
let _orphelinHighlight = null;

function _estCarteLeaflet(c) {
    return !!(c && typeof c.setView === 'function' && typeof c.getCenter === 'function'
        && typeof c.addLayer === 'function');
}

function _carteActiveOrphelins() {
    const candidats = [];
    if (typeof window !== 'undefined') {
        candidats.push(window.carte, window.map, window.leafletMap);
    }
    try { candidats.push(map); } catch (e) { /* noop */ }
    try { candidats.push(carte); } catch (e) { /* noop */ }
    return candidats.find(_estCarteLeaflet) || null;
}

function _pulseOrphelin(carte, lat, lng, label) {
    if (typeof L === 'undefined') return;
    if (_orphelinPulse) {
        try { carte.removeLayer(_orphelinPulse); } catch (e) { /* noop */ }
        _orphelinPulse = null;
    }
    const icon = L.divIcon({
        className: 'pulse-regard-icon',
        html: '<div class="pulse-regard-wrap"><div class="pulse-regard-ring"></div><div class="pulse-regard-core"></div></div>',
        iconSize: [34, 34],
        iconAnchor: [17, 17]
    });
    if (!carte.getPane('searchPulsePane')) {
        try {
            const p = carte.createPane('searchPulsePane');
            p.style.zIndex = 900;
        } catch (e) { /* noop */ }
    }
    _orphelinPulse = L.marker([lat, lng], { icon: icon, zIndexOffset: 1000, pane: 'searchPulsePane' }).addTo(carte);
    if (label) {
        _orphelinPulse.bindTooltip(String(label), {
            permanent: true, direction: 'top', offset: [0, -20], className: 'pulse-regard-label'
        });
    }
    setTimeout(() => {
        if (_orphelinPulse) {
            const el = _orphelinPulse.getElement && _orphelinPulse.getElement();
            if (el) el.classList.add('fade-out');
            setTimeout(() => {
                try { if (_orphelinPulse) carte.removeLayer(_orphelinPulse); } catch (e) { /* noop */ }
                _orphelinPulse = null;
            }, 700);
        }
    }, 8000);
}

function localiserOrphelin(anomalie) {
    const o = (anomalie && anomalie._orphelin) || {};
    const lat = anomalie && anomalie.latitude != null ? anomalie.latitude : o.lat;
    const lng = anomalie && anomalie.longitude != null ? anomalie.longitude : o.lng;
    const carte = _carteActiveOrphelins();
    if (!carte || lat == null || lng == null || !isFinite(lat) || !isFinite(lng)) {
        if (typeof showNotification === 'function') showNotification('Position indisponible pour cet élément.', 'warning');
        return;
    }

    const estRegard = o.genre === 'regard';
    const titre = estRegard ? `Regard ${o.id}` : (o.libelle || `Tronçon ${o.id}`);

    // Centrage — même garde-fou que la recherche : pendant ~8 s aucun
    // rendu asynchrone ne doit détourner la vue.
    try { window._rechercheCentrageJusqua = Date.now() + 8000; } catch (e) { /* noop */ }
    try { carte.setView([lat, lng], 18); } catch (e) { /* noop */ }
    _pulseOrphelin(carte, lat, lng, titre);

    // Surlignage de la géométrie si la couche est chargée (carte /carte)
    let carteMap = null;
    try { carteMap = (typeof map !== 'undefined' && _estCarteLeaflet(map)) ? map : null; } catch (e) { carteMap = null; }
    if (carteMap && carteMap === carte) {
        if (_orphelinHighlight && carteMap.hasLayer(_orphelinHighlight)) {
            try { carteMap.removeLayer(_orphelinHighlight); } catch (e) { /* noop */ }
            _orphelinHighlight = null;
        }
        const cibleId = o.id || anomalie.id_regard || anomalie.id_conduite || anomalie.fid;
        if (cibleId && typeof findLayerById === 'function') {
            const layer = findLayerById(estRegard ? regardsLayer : conduitesLayer, cibleId)
                || findLayerById(conduitesLayer, cibleId)
                || findLayerById(regardsLayer, cibleId);
            if (layer) {
                try {
                    if (layer.getLatLngs) {
                        _orphelinHighlight = L.polyline(layer.getLatLngs(), { color: '#e74c3c', weight: 10, opacity: 0.85, dashArray: '8,10' }).addTo(carteMap);
                    } else if (layer.getLatLng) {
                        _orphelinHighlight = L.circleMarker(layer.getLatLng(), { radius: 18, color: '#e74c3c', weight: 5, opacity: 0.9, fillColor: 'transparent' }).addTo(carteMap);
                    }
                    setTimeout(() => {
                        if (_orphelinHighlight && carteMap.hasLayer(_orphelinHighlight)) {
                            try { carteMap.removeLayer(_orphelinHighlight); } catch (e) { /* noop */ }
                            _orphelinHighlight = null;
                        }
                    }, 12000);
                } catch (e) { /* noop */ }
            }
        }
    }

    // Ouvre la popup d'anomalie si un marqueur correspond (carte /carte)
    setTimeout(() => {
        try {
            const cibleLat = lat, cibleLng = lng;
            Object.values(anomaliesLayers || {}).forEach(layer => {
                if (typeof layer.eachLayer === 'function') {
                    layer.eachLayer(marker => {
                        if (typeof marker.getLatLng === 'function') {
                            const ll = marker.getLatLng();
                            if (Math.abs(ll.lat - cibleLat) < 0.0001 && Math.abs(ll.lng - cibleLng) < 0.0001) {
                                marker.openPopup();
                            }
                        }
                    });
                }
            });
        } catch (e) { /* noop */ }
    }, 450);
}
window.localiserOrphelin = localiserOrphelin;
