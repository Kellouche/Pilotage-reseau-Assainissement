(() => {
    const state = window.mapState;

    function montrerChargement(afficher) {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            overlay.style.display = afficher ? 'flex' : 'none';
        }
    }

    function initLayerFilters() {
        ['conduites', 'regards', 'stations', 'step', 'ouvrages', 'bassins'].forEach(type => {
            const input = document.getElementById('f-' + type);
            if (!input) return;

            input.onchange = (e) => {
                if (e.target.checked) state.couches[type].addTo(state.carte);
                else state.carte.removeLayer(state.couches[type]);
            };
        });
    }

    function initZoomVisibility() {
        const carte = state.carte;

        carte.on('zoomend', function() {
            const zoom = carte.getZoom();
            const zoomIndicator = document.getElementById('zoom-indicator');
            if (zoomIndicator) zoomIndicator.textContent = 'Zoom: ' + zoom;

            setLayerVisibility('conduites', zoom >= 15);
            setLayerVisibility('regards', zoom >= 16);
            ['stations', 'step', 'ouvrages'].forEach(type => setLayerVisibility(type, zoom >= 11));

            if (zoom >= 11) {
                if (!carte.hasLayer(state.couches.bassins) && state.couches.bassins.getLayers().length > 0) {
                    state.couches.bassins.addTo(carte);
                }
            } else if (carte.hasLayer(state.couches.bassins)) {
                carte.removeLayer(state.couches.bassins);
            }
        });

        carte.fire('zoomend');
        if (document.getElementById('zoom-indicator')) {
            document.getElementById('zoom-indicator').textContent = 'Zoom: ' + carte.getZoom();
        }
    }

    function setLayerVisibility(type, visible) {
        const carte = state.carte;
        const layer = state.couches[type];
        if (!layer) return;

        if (visible) {
            if (!carte.hasLayer(layer)) layer.addTo(carte);
        } else if (carte.hasLayer(layer)) {
            carte.removeLayer(layer);
        }
    }

    async function chargerDonneesInitiales() {
        montrerChargement(true);

        try {
            const response = await fetch('/api/v1/layers');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const d = await response.json();

            console.log('Données:', d.compteurs);
            const statTotal = document.getElementById('stat-total');
            const miniStats = document.getElementById('mini-stats');

            if (statTotal) statTotal.textContent = d.compteurs.conduites || 0;
            if (miniStats) {
                miniStats.innerHTML =
                    'Conduites: ' + (d.compteurs.conduites || 0) +
                    ' | Regards: ' + (d.compteurs.regards || 0) +
                    ' | Stations: ' + (d.compteurs.stations || 0) +
                    ' | STEP: ' + (d.compteurs.step || 0) +
                    ' | Ouvrages: ' + (d.compteurs.ouvrages || 0);
            }

            state.conduitProperties = [];
            state.regardProperties = [];
            L.geoJSON(d.couches.conduites, {
                style: { color: '#3498db', weight: 8 },
                onEachFeature: (feature, layer) => {
                    const index = state.conduitProperties.length;
                    state.conduitProperties.push(feature.properties);
                    layer.bindPopup(conduitPopup(feature, index));
                }
            }).addTo(state.couches.conduites);

            const styles = {
                regards: { radius: 4, color: '#2c3e50', fillColor: '#2c3e50' },
                stations: { radius: 6, color: '#e67e22', fillColor: '#e67e22' },
                step: { radius: 7, color: '#27ae60', fillColor: '#27ae60' },
                ouvrages: { radius: 6, color: '#9b59b6', fillColor: '#9b59b6' }
            };

            ['regards', 'stations', 'step', 'ouvrages'].forEach(type => {
                L.geoJSON(d.couches[type], {
                    pointToLayer: (feature, latlng) => L.circleMarker(latlng, styles[type]),
                    onEachFeature: (feature, layer) => {
                        if (type === 'regards') {
                            const index = state.regardProperties.length;
                            state.regardProperties.push(feature.properties);
                            layer.bindPopup(regardPopup(feature, index));
                        }
                    }
                }).addTo(state.couches[type]);
            });

            const bounds = L.latLngBounds([]);
            Object.values(state.couches).forEach(l => l.getLayers().forEach(layer => {
                bounds.extend(layer.getBounds ? layer.getBounds() : layer.getLatLng());
            }));

            if (bounds.isValid()) state.carte.fitBounds(bounds, { padding: [50, 50] });

            initZoomVisibility();
            montrerChargement(false);
        } catch (e) {
            console.error('Erreur:', e);
            const miniStats = document.getElementById('mini-stats');
            if (miniStats) miniStats.textContent = 'Erreur chargement';
            montrerChargement(false);
        }
    }

    function conduitPopup(feature, index) {
        return `<div style="font-family: Arial, sans-serif; font-size: 12px;">
            <b>Conduite ${feature.properties.conduit_id || feature.properties.fid}</b><br>
            Longueur: ${feature.properties.longueur || 'N/A'} m<br>
            Diamètre: ${feature.properties.diametre || 'N/A'} mm<br>
            <button onclick="editConduit(${index})" style="margin-top: 5px; padding: 5px 10px; background: #3498db; color: white; border: none; border-radius: 3px; cursor: pointer;">Modifier</button>
        </div>`;
    }

    function regardPopup(feature, index) {
        return `<div style="font-family: Arial, sans-serif; font-size: 12px;">
            <b>Regard ${feature.properties.code || feature.properties.fid || 'N/A'}</b><br>
            Type: ${feature.properties.type_regard || 'N/A'}<br>
            Profondeur: ${feature.properties.profondeur || 'N/A'} m<br>
            <button onclick="editRegard(${index})" style="margin-top: 5px; padding: 5px 10px; background: #3498db; color: white; border: none; border-radius: 3px; cursor: pointer;">Modifier</button>
        </div>`;
    }

    function zoomToLayer(layerName) {
        const layer = state.couches[layerName];
        if (layer && layer.getBounds && layer.getBounds().isValid()) {
            state.carte.fitBounds(layer.getBounds(), { padding: [50, 50] });
        } else {
            console.log(`Aucune donnée pour la couche ${layerName}`);
        }
    }

    window.mostrerChargement = montrerChargement;
    window.chargerDonneesInitiales = chargerDonneesInitiales;
    window.initLayerFilters = initLayerFilters;
    window.zoomToLayer = zoomToLayer;
})();
