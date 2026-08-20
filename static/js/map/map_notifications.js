(() => {
    const state = window.mapState;

    function zoomToCoordinates(lat, lng) {
        const carte = state.carte;
        if (!carte) {
            console.error('❌ Carte non disponible');
            return;
        }
        if (isNaN(lat) || isNaN(lng)) {
            console.error('❌ Coordonnées invalides');
            return;
        }

        try {
            if (state.lastZoomMarker && carte.hasLayer && carte.hasLayer(state.lastZoomMarker)) {
                carte.removeLayer(state.lastZoomMarker);
            }

            carte.setView([lat, lng], 18);

            const marker = L.circleMarker([lat, lng], {
                radius: 8,
                fillColor: '#ff0000',
                color: '#ff0000',
                weight: 2,
                opacity: 0.8,
                fillOpacity: 0.6
            });

            marker.addTo(carte);
            marker.bindPopup(`
                <div style="font-family: Arial, sans-serif; font-size: 12px;">
                    <b>📍 Regard modifié</b><br>
                    <span style="color: #666;">Coordonnées:</span> ${lat.toFixed(2)}, ${lng.toFixed(2)}<br>
                    <small style="color: #999;">Marqueur temporaire (5s)</small>
                </div>
            `).openPopup();

            state.lastZoomMarker = marker;

            setTimeout(() => {
                if (carte.hasLayer && carte.hasLayer(marker)) {
                    carte.removeLayer(marker);
                }
            }, 5000);
        } catch (error) {
            console.error('❌ Erreur zoom:', error);
        }
    }

    function zoomToConduit(conduitId) {
        const carte = state.carte;
        if (!carte || !state.couches.conduites) {
            console.error('❌ Carte ou couche conduites non disponible');
            return;
        }

        let foundLayer = null;
        state.couches.conduites.eachLayer(layer => {
            if (layer.feature && layer.feature.properties && layer.feature.properties.conduit_id == conduitId) {
                foundLayer = layer;
            }
        });

        if (!foundLayer) {
            console.error('❌ Conduite non trouvée avec ID:', conduitId);
            return;
        }

        try {
            if (state.lastZoomMarker && carte.hasLayer && carte.hasLayer(state.lastZoomMarker)) {
                carte.removeLayer(state.lastZoomMarker);
            }

            const bounds = foundLayer.getBounds();
            if (!bounds.isValid()) {
                console.warn('⚠️ Bounds invalides pour la conduite');
                return;
            }

            carte.fitBounds(bounds, { padding: [50, 50], maxZoom: 18 });

            const center = bounds.getCenter();
            const marker = L.circleMarker([center.lat, center.lng], {
                radius: 8,
                fillColor: '#3498db',
                color: '#3498db',
                weight: 2,
                opacity: 0.8,
                fillOpacity: 0.6
            });

            marker.addTo(carte);
            marker.bindPopup(`
                <div style="font-family: Arial, sans-serif; font-size: 12px;">
                    <b>🛣️ Conduite modifiée</b><br>
                    <span style="color: #666;">ID:</span> ${conduitId}<br>
                    <small style="color: #999;">Marqueur temporaire (5s)</small>
                </div>
            `).openPopup();

            state.lastZoomMarker = marker;

            setTimeout(() => {
                if (carte.hasLayer && carte.hasLayer(marker)) {
                    carte.removeLayer(marker);
                }
            }, 5000);
        } catch (error) {
            console.error('❌ Erreur zoom conduite:', error);
        }
    }

    function initNotifications() {
        const syncIndicator = document.getElementById('sync-indicator');
        const ws = new WebSocket('ws://localhost:5002/ws/sync');

        ws.onmessage = (event) => {
            console.log('=== NOUVELLE NOTIFICATION ===');
            console.log('Notification reçue:', event.data);
            console.log('Type de message:', typeof event.data);

            const changesList = document.getElementById('changes-list');
            const messageDiv = document.createElement('div');
            messageDiv.style.cssText = 'padding: 4px 0; border-bottom: 1px solid rgba(0,0,0,0.1); font-family: monospace;';

            if (event.data.startsWith('Objet : Regard')) {
                const coordMatch = event.data.match(/\[([0-9.-]+),([0-9.-]+)\]/);
                messageDiv.style.cssText += 'background: rgba(39, 174, 96, 0.1); border-left: 3px solid #27ae60; padding-left: 8px; color: #000; cursor: pointer;';
                messageDiv.innerHTML = `<span style="color: #27ae60;">📍</span> ${event.data} <small style="color: #666; float: right;">clic pour zoomer</small>`;

                if (coordMatch) {
                    const lng = parseFloat(coordMatch[1]);
                    const lat = parseFloat(coordMatch[2]);
                    messageDiv.title = 'Cliquer pour zoomer sur ce regard';
                    messageDiv.onclick = () => zoomToCoordinates(lat, lng);
                    messageDiv.onmouseover = () => messageDiv.style.backgroundColor = 'rgba(39, 174, 96, 0.3)';
                    messageDiv.onmouseout = () => messageDiv.style.backgroundColor = 'rgba(39, 174, 96, 0.1)';
                }
            } else if (event.data.startsWith('Objet : Conduite')) {
                const coordMatch = event.data.match(/\[([0-9.-]+),([0-9.-]+)\]/);
                messageDiv.style.cssText += 'background: rgba(52, 152, 219, 0.1); border-left: 3px solid #3498db; padding-left: 8px; color: #000; cursor: pointer;';
                messageDiv.innerHTML = `<span style="color: #3498db;">🛣️</span> ${event.data} <small style="color: #666; float: right;">clic pour zoomer</small>`;

                if (coordMatch) {
                    const lng = parseFloat(coordMatch[1]);
                    const lat = parseFloat(coordMatch[2]);
                    messageDiv.title = 'Cliquer pour zoomer sur cette conduite';
                    messageDiv.onclick = () => zoomToConduit(conduitIdFromText(event.data));
                    messageDiv.onmouseover = () => messageDiv.style.backgroundColor = 'rgba(52, 152, 219, 0.3)';
                    messageDiv.onmouseout = () => messageDiv.style.backgroundColor = 'rgba(52, 152, 219, 0.1)';
                }
            } else if (event.data.startsWith('Incident signalé !')) {
                const coordMatch = event.data.match(/à \[([0-9.-]+),\s*([0-9.-]+)\]/);
                messageDiv.style.cssText += 'background: rgba(231, 76, 60, 0.1); border-left: 3px solid #e74c3c; padding-left: 8px; color: #000; cursor: pointer;';
                messageDiv.innerHTML = `<span style="color: #e74c3c;">⚠️</span> ${event.data} <small style="color: #666; float: right;">clic pour zoomer</small>`;

                if (coordMatch) {
                    const lng = parseFloat(coordMatch[1]);
                    const lat = parseFloat(coordMatch[2]);
                    messageDiv.title = 'Cliquer pour zoomer sur cet incident';
                    messageDiv.onclick = () => zoomToCoordinates(lat, lng);
                    messageDiv.onmouseover = () => messageDiv.style.backgroundColor = 'rgba(231, 76, 60, 0.3)';
                    messageDiv.onmouseout = () => messageDiv.style.backgroundColor = 'rgba(231, 76, 60, 0.1)';

                    // Add a persistent marker to the map
                    if (state.carte) {
                        const incidentMarker = L.marker([lat, lng], {
                            icon: L.divIcon({
                                className: 'incident-marker',
                                html: '<div style="background-color: #e74c3c; width: 20px; height: 20px; border-radius: 50%; border: 2px solid white; display: flex; align-items: center; justify-content: center; color: white; font-size: 12px; box-shadow: 0 0 5px rgba(0,0,0,0.5);">⚠️</div>',
                                iconSize: [20, 20],
                                iconAnchor: [10, 10]
                            })
                        }).addTo(state.carte);
                        
                        incidentMarker.bindPopup(`<b>🚨 Nouvel Incident</b><br>${event.data}`);
                    }
                }
            } else if (event.data.includes('Modifications synchronisées')) {
                messageDiv.style.cssText += 'background: rgba(52, 152, 219, 0.1); border-left: 3px solid #3498db; padding-left: 8px; font-weight: bold; color: #000;';
                messageDiv.innerHTML = `<span style="color: #3498db;">🔄</span> ${event.data}`;

                const match = event.data.match(/(\d+) acceptées/);
                if (match) {
                    state.totalModifications += parseInt(match[1]);
                    document.getElementById('modif-count').textContent = state.totalModifications;
                }
            } else {
                messageDiv.textContent = `${new Date().toLocaleTimeString()}: ${event.data}`;
                messageDiv.style.color = '#000';
            }

            changesList.appendChild(messageDiv);
            while (changesList.children.length > 8) {
                changesList.removeChild(changesList.firstChild);
            }

            syncIndicator.style.background = '#27ae60';
            setTimeout(() => {
                syncIndicator.style.background = '#ccc';
            }, 2000);

            changesList.scrollTop = changesList.scrollHeight;
        };

        ws.onopen = () => {
            console.log('WebSocket connecté');
            syncIndicator.style.background = '#3498db';
        };

        ws.onclose = () => {
            console.log('WebSocket déconnecté');
            syncIndicator.style.background = '#ccc';
        };

        ws.onerror = (error) => {
            console.error('Erreur WebSocket:', error);
            syncIndicator.style.background = '#e74c3c';
        };
    }

    function conduitIdFromText(text) {
        const match = text.match(/Conduite\s+([^\s\[]+)/i);
        return match ? match[1] : null;
    }

    window.zoomToCoordinates = zoomToCoordinates;
    window.zoomToConduit = zoomToConduit;
    window.initNotifications = initNotifications;
})();
