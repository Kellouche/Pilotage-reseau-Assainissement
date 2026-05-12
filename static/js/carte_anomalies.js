
// Variables globales pour les anomalies
let conduiteAnomaliesMap = {}; // fid -> { severite, types: [] }
let anomalousRegards = new Set();
let anomaliesData = {};
let anomaliesLayers = {};

function applyFilters() {
    console.log('Applying filters manually...');
    if (typeof updateLayersVisibility === 'function') updateLayersVisibility();
    if (typeof updateAnomaliesLayers === 'function') updateAnomaliesLayers();
}

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
    
    for (const [category, anomalies] of Object.entries(anomsByType)) {
        if (!Array.isArray(anomalies)) continue;
        
        const markers = [];
        anomalies.forEach(anom => {
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

            // CRÉATION PRÉALABLE DES MARQUEURS (Pour la rapidité)
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
                    // Identifier le type d'objet parent pour le filtrage global
                    marker._pointType = 'regard'; // Par défaut
                    if (anom.type && anom.type.includes('station')) marker._pointType = 'station';
                    if (anom.type && anom.type.includes('step')) marker._pointType = 'step';
                    if (anom.type && anom.type.includes('ouvrage')) marker._pointType = 'ouvrage';
                    
                    markers.push(marker);
                }
            }
        });

        if (markers.length > 0) {
            anomaliesLayers[category] = L.layerGroup(markers);
        }
    }
    console.log("Anomalies maps and layers built:", { 
        regards: anomalousRegards.size, 
        conduites: Object.keys(conduiteAnomaliesMap).length,
        layers: Object.keys(anomaliesLayers).length
    });
    
    // Remplir les listes déroulantes pour la navigation rapide
    populateAnomaliesLists(anomsByType);
    
    // Ajouter la légende si elle n'existe pas encore sur la carte
    if (typeof addDiagnosticLegend === 'function') {
        addDiagnosticLegend();
    }
}

function updateAnomaliesLayers() {
    if (!anomaliesData) return;

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

function addDiagnosticLegend() {
    const legend = L.control({ position: 'bottomright' });
    legend.onAdd = function() {
        const div = L.DomUtil.create('div', 'info legend');
        div.style.backgroundColor = 'white';
        div.style.padding = '10px';
        div.style.borderRadius = '5px';
        div.style.boxShadow = '0 0 15px rgba(0,0,0,0.2)';
        div.style.fontSize = '12px';
        div.style.lineHeight = '18px';
        div.style.color = '#333';

        div.innerHTML = `
            <b style="display:block;margin-bottom:5px;border-bottom:1px solid #eee;">Sévérité Anomalies</b>
            <i style="background:#e74c3c;width:12px;height:12px;display:inline-block;margin-right:5px;border-radius:2px;"></i> Critique<br>
            <i style="background:#e67e22;width:12px;height:12px;display:inline-block;margin-right:5px;border-radius:2px;"></i> Majeure<br>
            <i style="background:#2ecc71;width:12px;height:12px;display:inline-block;margin-right:5px;border-radius:2px;"></i> Mineure<br>
            <i style="background:#bdc3c7;width:12px;height:12px;display:inline-block;margin-right:5px;border-radius:2px;"></i> Sain / Non concerné
        `;
        return div;
    };
    legend.addTo(map);
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

function populateAnomaliesLists(data) {
    console.log('Populating anomalies lists with data:', Object.keys(data));
    const tabMappings = {
        'connexions': ['conduites_sans_regards', 'incoherences_amont_aval', 'troncons_orphelins'],
        'geometrie': ['geometries_invalides', 'pentes_suspectes'],
        'donnees': ['champs_manquants']
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
            if (Array.isArray(anoms)) {
                console.log(`Tab ${tab}: found ${anoms.length} anomalies of type ${type}`);
                anoms.forEach(anom => {
                    const coords = findAnomalieCoords(anom);
                    if (coords) {
                        count++;
                        const id = anom.fid || anom.code || anom.identifiant || anom.id_conduite || 'Inconnu';
                        const option = document.createElement('option');
                        option.value = `${coords[0]},${coords[1]}`;
                        
                        let label = `[${(anom.severite || 'info').toUpperCase()}] ${getAnomalieTitre(anom)} - ID: ${id}`;
                        if (anom.type === 'incoherence_profondeur') {
                            label = `[Saut] FID ${anom.fid1} / ${anom.fid2}`;
                        }
                        
                        option.textContent = label;
                        select.appendChild(option);
                    } else {
                        // console.warn(`Could not find coords for anomalie ${anom.type} / ${anom.fid || anom.code}`);
                    }
                });
            }
        });

        console.log(`Tab ${tab}: total anomalies with coords = ${count}`);
        // Afficher le conteneur seulement s'il y a des anomalies
        container.style.display = count > 0 ? 'block' : 'none';
    });
}

function zoomToAnomalie(coordsStr) {
    if (!coordsStr) return;
    const [lat, lng] = coordsStr.split(',').map(Number);
    
    console.log(`Zooming to anomalie at ${lat}, ${lng}`);
    map.setView([lat, lng], 18);
    
    // Attendre un peu que le zoom se termine pour ouvrir le popup
    setTimeout(() => {
        Object.values(anomaliesLayers).forEach(layer => {
            if (typeof layer.eachLayer === 'function') {
                layer.eachLayer(marker => {
                    if (typeof marker.getLatLng === 'function') {
                        const ll = marker.getLatLng();
                        if (Math.abs(ll.lat - lat) < 0.0001 && Math.abs(ll.lng - lng) < 0.0001) {
                            marker.openPopup();
                        }
                    }
                });
            }
        });
    }, 500);
}