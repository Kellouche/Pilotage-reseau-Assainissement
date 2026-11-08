/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Système de notifications visuelles et alertes d'ingénierie
 * ================================================================================
 */

(() => {
    const state = window.mapState;

    function zoomToCoordinates(lat, lng, title = "Élément sélectionné", extraHtml = "") {
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
                    <b>📍 ${title}</b><br>
                    ${extraHtml ? extraHtml + '<br>' : ''}
                    <span style="color: #666;">Coordonnées:</span> ${lat.toFixed(4)}, ${lng.toFixed(4)}<br>
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
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/ws/sync`;
        const ws = new WebSocket(wsUrl);

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
                    messageDiv.title = 'Cliquer pour zoomer sur ce regard';
                    messageDiv.onclick = () => zoomToFeature('regards', regardIdFromText(event.data));
                    messageDiv.onmouseover = () => messageDiv.style.backgroundColor = 'rgba(39, 174, 96, 0.3)';
                    messageDiv.onmouseout = () => messageDiv.style.backgroundColor = 'rgba(39, 174, 96, 0.1)';
                }
            } else if (event.data.startsWith('Objet : Conduite')) {
                const coordMatch = event.data.match(/\[([0-9.-]+),([0-9.-]+)\]/);
                messageDiv.style.cssText += 'background: rgba(52, 152, 219, 0.1); border-left: 3px solid #3498db; padding-left: 8px; color: #000; cursor: pointer;';
                messageDiv.innerHTML = `<span style="color: #3498db;">🛣️</span> ${event.data} <small style="color: #666; float: right;">clic pour zoomer</small>`;

                if (coordMatch) {
                    const lng = parseFloat(coordMatch[1]);
                    messageDiv.title = 'Cliquer pour zoomer sur cette conduite';
                    messageDiv.onclick = () => zoomToFeature('conduites', conduitIdFromText(event.data));
                    messageDiv.onmouseover = () => messageDiv.style.backgroundColor = 'rgba(52, 152, 219, 0.3)';
                    messageDiv.onmouseout = () => messageDiv.style.backgroundColor = 'rgba(52, 152, 219, 0.1)';
                }
            } else if (event.data.startsWith('Incident signalé !')) {
                const coordMatch = event.data.match(/à \[([0-9.-]+),\s*([0-9.-]+)\]/);
                const incidentsList = document.getElementById('incidents-list');
                
                const incDiv = document.createElement('div');
                incDiv.style.cssText = 'padding: 4px 0; border-bottom: 1px solid rgba(0,0,0,0.1); font-family: monospace; background: rgba(231, 76, 60, 0.1); border-left: 3px solid #e74c3c; padding-left: 8px; color: #000; cursor: pointer;';
                
                const timeStr = new Date().toLocaleTimeString();
                incDiv.innerHTML = `<span style="color: #e74c3c;">⚠️</span> ${event.data} <small style="color: #666; float: right;">${timeStr}</small>`;

                if (coordMatch) {
                    const lng = parseFloat(coordMatch[1]);
                    const lat = parseFloat(coordMatch[2]);
                    const typeMatch = event.data.match(/Type:\s*([^\[]+)\s*\[Gravité:\s*([^\]]+)\]/);
                    let typeInc = "Inconnu", graviteInc = "Inconnue";
                    if (typeMatch) {
                        typeInc = typeMatch[1].trim();
                        graviteInc = typeMatch[2].trim();
                    }
                    const extraHtml = `<span style="color: #666;">Heure:</span> ${timeStr}<br><span style="color: #666;">Type:</span> ${typeInc}<br><span style="color: #666;">Gravité:</span> ${graviteInc}`;
                    
                    incDiv.title = 'Cliquer pour zoomer sur cet incident';
                    incDiv.onclick = () => zoomToCoordinates(lat, lng, "Incident signalé", extraHtml);
                    incDiv.onmouseover = () => incDiv.style.backgroundColor = 'rgba(231, 76, 60, 0.3)';
                    incDiv.onmouseout = () => incDiv.style.backgroundColor = 'rgba(231, 76, 60, 0.1)';

                    // Add a persistent marker to the map if not exists
                    if (state.carte && state.couches && state.couches.incidents) {
                        const incidentMarker = L.circleMarker([lat, lng], {
                            radius: 8,
                            color: '#e74c3c',
                            fillColor: '#c0392b',
                            fillOpacity: 0.8,
                            weight: 2
                        }).addTo(state.couches.incidents);
                        
                        incidentMarker.bindPopup(`
                            <div style="font-family: Arial, sans-serif; font-size: 12px;">
                                <b>🚨 Nouvel Incident</b><br>
                                ${event.data}
                            </div>
                        `);
                    }
                }
                
                if (incidentsList.children.length === 1 && incidentsList.children[0].textContent.includes('Aucun signalement')) {
                    incidentsList.innerHTML = '';
                }
                incidentsList.insertBefore(incDiv, incidentsList.firstChild);
                
                const countSpan = document.getElementById('incident-count');
                countSpan.textContent = parseInt(countSpan.textContent) + 1;
                
                syncIndicator.style.background = '#27ae60';
                setTimeout(() => {
                    syncIndicator.style.background = '#ccc';
                }, 2000);
                return; // Skip adding to changesList
            } else if (event.data.includes('Modifications synchronisées')) {
                const match = event.data.match(/(\d+) acceptées/);
                if (match) {
                    state.totalModifications += parseInt(match[1]);
                    document.getElementById('modif-count').textContent = state.totalModifications;
                }
                return; // Hide summary message
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

        function zoomToFeature(layerName, recordId) {
            if (!state.carte || !state.couches || !state.couches[layerName] || !recordId) return;
            
            let found = false;
            
            function checkLayer(layer) {
                if (found) return;
                
                if (layer.eachLayer) {
                    layer.eachLayer(checkLayer);
                }
                
                if (layer.feature) {
                    const props = layer.feature.properties || {};
                    if (props.id == recordId || 
                        props.code == recordId || 
                        props.fid == recordId || 
                        props.conduit_id == recordId || 
                        layer.feature.id == recordId) {
                        
                        found = true;
                        if (layer.getBounds) {
                            state.carte.fitBounds(layer.getBounds(), { padding: [50, 50], maxZoom: 18 });
                        } else if (layer.getLatLng) {
                            state.carte.setView(layer.getLatLng(), 18);
                        }
                        
                        // Visual effect
                        if (layer.setStyle) {
                            const originalColor = layer.options.color;
                            layer.setStyle({ color: '#ff0000', weight: 6 });
                            setTimeout(() => layer.setStyle({ color: originalColor, weight: 3 }), 3000);
                        }
                    }
                }
            }
            
            state.couches[layerName].eachLayer(checkLayer);
            
            if (!found) {
                console.warn('Object not found on map:', layerName, recordId);
            }
        }

        // Fetch recent modifications on page load
        fetch('/api/v1/audit/logs?limit=5')
            .then(res => res.json())
            .then(logs => {
                const changesList = document.getElementById('changes-list');
                if (logs && logs.length > 0) {
                    changesList.innerHTML = ''; // Clear 'En attente...'
                    
                    // Show them in chronological order
                    logs.reverse().forEach(log => {
                        if (log.table === 'incidents') return; // Skip incidents, they go to incidents-box
                        
                        const messageDiv = document.createElement('div');
                        messageDiv.style.cssText = 'padding: 4px 0; border-bottom: 1px solid rgba(0,0,0,0.1); font-family: monospace; font-size: 10px; color: #666; cursor: pointer;';
                        
                        const dateStr = new Date(log.timestamp).toLocaleTimeString();
                        let icon = '🔄';
                        let typeObj = log.table;
                        if (log.table === 'regards') { icon = '📍'; typeObj = 'Regard'; }
                        else if (log.table === 'conduites') { icon = '🛣️'; typeObj = 'Conduite'; }
                        
                        messageDiv.innerHTML = `<span>${icon}</span> ${typeObj} ID:${log.record_id} (${log.operation}) - <span style="color:#999">${dateStr}</span>`;
                        messageDiv.title = 'Cliquer pour localiser';
                        messageDiv.onclick = () => zoomToFeature(log.table, log.record_id);
                        messageDiv.onmouseover = () => messageDiv.style.backgroundColor = 'rgba(0,0,0,0.05)';
                        messageDiv.onmouseout = () => messageDiv.style.backgroundColor = 'transparent';
                        
                        changesList.appendChild(messageDiv);
                    });
                }
            })
            .catch(err => console.error('Erreur lors du chargement de l\'historique', err));

        // Fetch recent incidents of the day on page load
        fetch('/api/v1/terrain/incidents')
            .then(res => res.json())
            .then(incidents => {
                const incidentsList = document.getElementById('incidents-list');
                const countSpan = document.getElementById('incident-count');
                
                const todayStr = new Date().toISOString().split('T')[0];
                const todaysIncidents = incidents.filter(inc => inc.date_creation && inc.date_creation.startsWith(todayStr));
                
                if (todaysIncidents.length > 0) {
                    incidentsList.innerHTML = '';
                    countSpan.textContent = todaysIncidents.length;
                    
                    todaysIncidents.reverse().forEach(inc => {
                        const messageDiv = document.createElement('div');
                        messageDiv.style.cssText = 'padding: 4px 0; border-bottom: 1px solid rgba(0,0,0,0.1); font-family: monospace; background: rgba(231, 76, 60, 0.1); border-left: 3px solid #e74c3c; padding-left: 8px; color: #000; cursor: pointer; font-size: 11px;';
                        
                        const timeStr = new Date(inc.date_creation).toLocaleTimeString();
                        messageDiv.innerHTML = `<span style="color: #e74c3c;">⚠️</span> Incident signalé ! Type: ${inc.type_incident} [Gravité: ${inc.gravite}] à [${inc.longitude}, ${inc.latitude}] <small style="color: #666; float: right;">${timeStr}</small>`;
                        
                        const typeInc = inc.type_incident || "Inconnu";
                        const graviteInc = inc.gravite || "Inconnue";
                        const extraHtml = `<span style="color: #666;">Heure:</span> ${timeStr}<br><span style="color: #666;">Type:</span> ${typeInc}<br><span style="color: #666;">Gravité:</span> ${graviteInc}`;
                        
                        messageDiv.title = 'Cliquer pour zoomer sur cet incident';
                        messageDiv.onclick = () => zoomToCoordinates(inc.latitude, inc.longitude, "Incident signalé", extraHtml);
                        messageDiv.onmouseover = () => messageDiv.style.backgroundColor = 'rgba(231, 76, 60, 0.3)';
                        messageDiv.onmouseout = () => messageDiv.style.backgroundColor = 'rgba(231, 76, 60, 0.1)';
                        
                        incidentsList.appendChild(messageDiv);
                    });
                }
            })
            .catch(err => console.error('Erreur lors du chargement des incidents', err));
    }

    function conduitIdFromText(text) {
        const match = text.match(/Conduite\s+([^\s\[]+)/i);
        return match ? match[1] : null;
    }

    function regardIdFromText(text) {
        const match = text.match(/Regard\s+([^\s\[]+)/i);
        return match ? match[1] : null;
    }

    window.zoomToCoordinates = zoomToCoordinates;
    window.zoomToConduit = zoomToConduit;
    window.initNotifications = initNotifications;
})();
