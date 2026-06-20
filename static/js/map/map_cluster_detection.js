(() => {
    const state = window.mapState;

    const typeColors = {
        step: { color: '#c0392b', fill: '#e74c3c' },
        station: { color: '#1a6fa0', fill: '#3498db' },
        ouvrage: { color: '#7d3c98', fill: '#9b59b6' },
        rejet: { color: '#d35400', fill: '#e67e22' },
        manuel: { color: '#27ae60', fill: '#2ecc71' },
        inconnu: { color: '#607d8b', fill: '#90a4ae' }
    };

    const exutoireColors = {
        step: '#e74c3c',
        station: '#3498db',
        ouvrage: '#9b59b6',
        rejet: '#e67e22',
        manuel: '#27ae60',
        inconnu: '#607d8b'
    };

    window.highlightCluster = function(clusterId, geojsonLayer) {
        highlightCluster(clusterId, geojsonLayer);
    };

    const exutoireLabels = {
        step: '🔴 STEP',
        station: '🔵 Station',
        ouvrage: '🟣 Ouvrage',
        rejet: '🟠 Rejet',
        manuel: '⚪ Manuel',
        inconnu: '⚪ Exutoire'
    };

    function initClusterDetection() {
        document.getElementById('detect-cluster-btn').addEventListener('click', detecterBassins);
    }

    async function detecterBassins() {
        const btn = document.getElementById('detect-cluster-btn');
        const statusDiv = document.getElementById('cluster-status');
        const progress = getProgressElements();

        btn.disabled = true;
        btn.textContent = 'Détection en cours...';
        resetDetectionState();
        setProgress(progress, 'Connexion au service...', 5);
        setStatus(statusDiv, 'Recherche des bassins hydrauliques...');

        try {
            const response = await fetch('/api/v1/clusters/recalculate-all?persist=false', { method: 'POST' });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            setProgress(progress, 'Réception des résultats...', 35);
            const clusterData = await response.json();
            const resultats = clusterData.resultats || [];
            const features = extractFeatures(resultats);

            if (features.length === 0) {
                setProgress(progress, 'Aucun résultat', 100);
                setStatus(statusDiv, 'Aucun cluster détecté');
                return;
            }

            setProgress(progress, 'Préparation de la carte...', 50);
            const clusterLayer = buildClusterLayer(features);
            attachClusterLayer(clusterLayer);

            setProgress(progress, 'Mise à jour de la sélection...', 75);
            const nbBassins = clusterData.clusters_crees || resultats.filter(r => r.cluster || (r.exutoire && r.exutoire.type !== 'inconnu')).length;
            const nbTroncons = features.filter(f => f.geometry && f.geometry.type === 'LineString').length;
            const nbOrphelins = clusterData.troncons_orphelins || 0;

            setStatus(statusDiv, `Détection terminée !<br><b>${nbBassins}</b> bassins identifiés<br><b>${nbTroncons}</b> tronçons connectés<br><span style="color: #e74c3c;"><b>${nbOrphelins}</b> tronçons orphelins</span>`);

            peuplerDropdownBassins(clusterData, clusterLayer);
            highlightCluster(null, clusterLayer);

            const chkBassins = document.getElementById('f-bassins');
            const lblBassins = document.getElementById('label-bassins');
            if (chkBassins) {
                chkBassins.disabled = false;
                chkBassins.checked = true;
            }
            if (lblBassins) {
                lblBassins.style.color = 'inherit';
                lblBassins.style.fontWeight = 'bold';
            }

            setProgress(progress, 'Terminé', 100);
            if (clusterLayer.getBounds().isValid()) {
                state.carte.fitBounds(clusterLayer.getBounds(), { padding: [50, 50] });
            }
        } catch (error) {
            console.error('Erreur:', error);
            setProgress(progress, 'Erreur', 100, true);
            setStatus(statusDiv, `Erreur lors de la détection : ${escapeHtml(error.message)}`);
        } finally {
            btn.disabled = false;
            btn.textContent = 'Détecter les bassins urbains';
        }
    }

    function resetDetectionState() {
        state.clusterCouche.clearLayers();
        state.couches.bassins.clearLayers();
        state.activeClusterLayer = null;
        state.bassinBounds = {};

        const select = document.getElementById('bassin-select');
        const info = document.getElementById('bassin-info');
        const section = document.getElementById('bassin-section');
        const deleteBtn = document.getElementById('btn-delete-bassin');

        if (select) select.innerHTML = '';
        if (info) info.innerHTML = '';
        if (section) section.style.display = 'none';
        if (deleteBtn) {
            deleteBtn.disabled = true;
            deleteBtn.style.color = '';
        }
    }

    function extractFeatures(resultats) {
        const features = [];
        resultats.forEach(result => {
            if (result.geojson && Array.isArray(result.geojson.features)) {
                features.push(...result.geojson.features);
            }
        });
        return features;
    }

    function buildClusterLayer(features) {
        return L.geoJSON({ type: 'FeatureCollection', features }, {
            style: styleClusterFeature,
            pointToLayer: pointToClusterLayer,
            onEachFeature: (feature, layer) => bindClusterFeature(feature, layer)
        });
    }

    function styleClusterFeature(feature) {
        if (feature.properties.type === 'bassin_urbain') {
            const tc = typeColors[feature.properties.exutoire_type] || typeColors.inconnu;
            return {
                color: tc.color,
                fillColor: tc.fill,
                fillOpacity: 0.25,
                weight: 2,
                dashArray: '6, 4'
            };
        }

        return {
            color: feature.properties.couleur || '#3498db',
            weight: 2.5,
            opacity: 0.75
        };
    }

    function pointToClusterLayer(feature, latlng) {
        if (feature.properties.type === 'exutoire') {
            const color = exutoireColors[feature.properties.exutoire_type] || exutoireColors.inconnu;
            return L.circleMarker(latlng, {
                radius: 10,
                fillColor: color,
                color: '#fff',
                weight: 3,
                opacity: 1,
                fillOpacity: 1
            });
        }
        return L.marker(latlng);
    }

    function bindClusterFeature(feature, layer) {
        if (feature.properties.type === 'bassin_urbain') {
            const typLabel = exutoireLabels[feature.properties.exutoire_type] || exutoireLabels.inconnu;
            layer.bindTooltip(`<b>${feature.properties.nom || 'Bassin Urbain'}</b><br>${typLabel}`, { sticky: true });

            layer.on('click', function(e) {
                L.DomEvent.stopPropagation(e);
                const cid = feature.properties.cluster_id;
                highlightCluster(cid, state.activeClusterLayer);
                const sel = document.getElementById('bassin-select');
                if (sel) {
                    sel.value = String(cid);
                    afficherInfoBassin(cid);
                }
            });

            layer.on('mouseover', function() {
                this.setStyle({ fillOpacity: 0.5, weight: 3 });
            });
            layer.on('mouseout', function() {
                this.setStyle({ fillOpacity: 0.25, weight: 2 });
            });
        } else if (feature.properties.type === 'exutoire') {
            const typLabel = exutoireLabels[feature.properties.exutoire_type] || exutoireLabels.inconnu;
            layer.bindTooltip(`<b>Exutoire: ${feature.properties.nom}</b><br>${typLabel}`, { sticky: true });
        } else if (feature.geometry && feature.geometry.type === 'LineString') {
            const p = feature.properties;
            layer.bindTooltip(
                `<b>Conduite ${p.conduit_id || ''}</b><br>` +
                `📏 ${p.longueur ? p.longueur.toFixed(1) + ' m' : 'N/A'} &nbsp;|&nbsp; ` +
                `⌀ ${p.diametre || 'N/A'} mm<br>` +
                `Matériau: ${p.materiau || 'N/A'}<br>` +
                `Bassin n° ${p.cluster_id || '?'}`,
                { sticky: true }
            );
        }
    }

    function attachClusterLayer(clusterLayer) {
        clusterLayer.eachLayer(layer => {
            if (layer.feature.properties.type === 'bassin_urbain') {
                layer.addTo(state.couches.bassins);
            } else {
                layer.addTo(state.clusterCouche);
            }
        });

        state.activeClusterLayer = clusterLayer;
    }

    function highlightCluster(clusterId, geojsonLayer) {
        const sel = document.getElementById('bassin-select');
        if (clusterId !== null && clusterId !== undefined && sel && sel.value !== String(clusterId)) {
            sel.value = String(clusterId);
            afficherInfoBassin(clusterId);
        }

        const clusterIdString = clusterId === null || clusterId === undefined ? null : String(clusterId);

        geojsonLayer.eachLayer(layer => {
            const feature = layer.feature;
            if (!feature) return;

            if (feature.geometry && feature.geometry.type === 'LineString') {
                const featureClusterId = feature.properties ? String(feature.properties.cluster_id) : '';
                if (clusterIdString === null || featureClusterId === clusterIdString) {
                    layer.setStyle({ color: '#f1c40f', weight: 8, opacity: 1 });
                    layer.bringToFront();
                } else {
                    layer.setStyle({ color: feature.properties.couleur || '#e74c3c', weight: 3, opacity: 0.4 });
                }
            } else if (feature.properties && feature.properties.type === 'bassin_urbain') {
                const featureClusterId = feature.properties ? String(feature.properties.cluster_id) : '';
                if (clusterIdString === null || featureClusterId === clusterIdString) {
                    layer.setStyle({ fillOpacity: 0.45, weight: 3, color: '#f39c12' });
                } else {
                    layer.setStyle({ fillOpacity: 0.15, weight: 1, color: '#27ae60' });
                }
            }
        });
    }

    function peuplerDropdownBassins(geojsonData, clusterLayer) {
        const sel = document.getElementById('bassin-select');
        if (!sel) return;

        sel.innerHTML = '<option value="">-- Choisir un bassin --</option>';
        state.bassinBounds = {};

        const resultats = geojsonData.resultats || [];
        const features = geojsonData.features || [];
        const allFeatures = resultats.length
            ? resultats.flatMap(result => (result.geojson && result.geojson.features) ? result.geojson.features : [])
            : features;

        const bassins = allFeatures.filter(feature => feature.properties && feature.properties.type === 'bassin_urbain');
        bassins.sort((a, b) => String(a.properties.cluster_id).localeCompare(String(b.properties.cluster_id), undefined, { numeric: true }));

        bassins.forEach(f => {
            const cid = f.properties.cluster_id;
            const nom = f.properties.nom || `Bassin ${cid}`;
            const opt = document.createElement('option');
            opt.value = cid;
            opt.textContent = nom;
            sel.appendChild(opt);
        });

        clusterLayer.eachLayer(layer => {
            const feature = layer.feature;
            if (!feature || feature.properties.type !== 'bassin_urbain') return;
            const cid = feature.properties.cluster_id;
            try { state.bassinBounds[cid] = layer.getBounds(); } catch (e) {}
        });

        const section = document.getElementById('bassin-section');
        if (section) section.style.display = 'block';

        sel.onchange = function() {
            const cid = this.value;
            const btnDelete = document.getElementById('btn-delete-bassin');
            if (btnDelete) {
                if (cid && String(cid).startsWith('M_')) {
                    btnDelete.disabled = false;
                    btnDelete.style.color = '#e74c3c';
                } else {
                    btnDelete.disabled = true;
                    btnDelete.style.color = '';
                }
            }

            if (!cid) {
                highlightCluster(null, clusterLayer);
                afficherInfoBassin(null);
                return;
            }

            const finalCid = String(cid).startsWith('M_') ? cid : parseInt(cid, 10);
            highlightCluster(finalCid, clusterLayer);
            afficherInfoBassin(finalCid);
            if (state.bassinBounds[cid]) {
                state.carte.fitBounds(state.bassinBounds[cid], { padding: [60, 60] });
            }
        };
    }

    function afficherInfoBassin(clusterId) {
        const infoDiv = document.getElementById('bassin-info');
        if (!infoDiv || !state.activeClusterLayer || clusterId === null || clusterId === undefined || clusterId === '') {
            if (infoDiv) infoDiv.innerHTML = '';
            return;
        }

        const clusterIdString = String(clusterId);
        let nb = 0;

        state.activeClusterLayer.eachLayer(layer => {
            const f = layer.feature;
            const featureClusterId = f && f.properties ? f.properties.cluster_id : undefined;
            if (f && f.geometry && f.geometry.type === 'LineString' && String(featureClusterId) === clusterIdString) nb++;
        });

        infoDiv.innerHTML = `📍 ${nb} tronçon(s) dans ce bassin`;
    }

    function getProgressElements() {
        let bar = document.getElementById('cluster-progress-bar');
        let label = document.getElementById('cluster-progress-label');

        if (!bar) {
            const statusDiv = document.getElementById('cluster-status');
            if (!statusDiv) return { bar: null, label: null };

            bar = document.createElement('div');
            bar.id = 'cluster-progress-bar';
            bar.style.cssText = 'width:100%;height:8px;background:#263;overflow:hidden;margin:8px 0;border-radius:4px;';

            const fill = document.createElement('div');
            fill.id = 'cluster-progress-fill';
            fill.style.cssText = 'height:100%;width:0%;background:linear-gradient(90deg,#3498db,#2ecc71);transition:width .25s;';
            bar.appendChild(fill);

            label = document.createElement('div');
            label.id = 'cluster-progress-label';
            label.style.cssText = 'font-size:11px;color:#aab;margin-top:4px;';

            statusDiv.appendChild(bar);
            statusDiv.appendChild(label);
        }

        return { bar, label };
    }

    function setProgress(progress, text, percent, isError = false) {
        if (!progress.bar || !progress.label) return;
        const fill = document.getElementById('cluster-progress-fill');
        if (fill) {
            fill.style.width = Math.max(0, Math.min(100, percent)) + '%';
            if (isError) {
                fill.style.background = '#e74c3c';
            } else if (percent === 100) {
                fill.style.background = '#2ecc71';
            }
        }
        progress.label.textContent = `${text} (${percent}%)`;
    }

    function setStatus(element, html) {
        if (element) element.innerHTML = html;
    }

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, '&')
            .replace(/</g, '<')
            .replace(/>/g, '>')
            .replace(/"/g, '"')
            .replace(/'/g, '&#039;');
    }

    window.initClusterDetection = initClusterDetection;
    window.detecterBassins = detecterBassins;
    window.highlightCluster = highlightCluster;
    window.peuplerDropdownBassins = peuplerDropdownBassins;
    window.afficherInfoBassin = afficherInfoBassin;
})();
