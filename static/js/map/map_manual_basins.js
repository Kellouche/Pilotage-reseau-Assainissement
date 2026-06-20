(() => {
    const state = window.mapState;

    function isPointInPolygon(point, vs) {
        const x = point.lat;
        const y = point.lng;
        let inside = false;

        for (let i = 0, j = vs.length - 1; i < vs.length; j = i++) {
            const xi = vs[i].lat;
            const yi = vs[i].lng;
            const xj = vs[j].lat;
            const yj = vs[j].lng;
            const intersect = ((yi > y) !== (yj > y)) && (x < ((xj - xi) * (y - yi)) / (yj - yi) + xi);
            if (intersect) inside = !inside;
        }

        return inside;
    }

    function initManualBasins() {
        const carte = state.carte;

        document.getElementById('btn-create-bassin').onclick = function() {
            if (state.editor.active && state.editor.mode === 'create') {
                desactiverModeEdition();
            } else {
                activerModeEdition('create');
            }
        };

        document.getElementById('btn-save-edit').onclick = function() {
            if (state.editor.selectedConduits.size === 0) return;

            const data = {
                conduits: Array.from(state.editor.selectedConduits),
                exutoire: state.editor.foundOutfall || null,
                nom: prompt('Nom du bassin :', state.editor.foundOutfall ? 'Bassin ' + state.editor.foundOutfall.nom : 'Bassin Manuel')
            };

            if (!data.nom) return;

            fetch('/api/v1/manual-basin', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            })
            .then(r => r.json())
            .then(() => {
                alert('Bassin manuel enregistré avec succès !');
                desactiverModeEdition();
                document.getElementById('detect-cluster-btn').click();
            })
            .catch(err => {
                console.error(err);
                alert('Erreur lors de la sauvegarde.');
            });
        };

        document.getElementById('btn-delete-bassin').onclick = function() {
            const sel = document.getElementById('bassin-select');
            const cid = sel.value;
            if (!cid || !cid.startsWith('M_')) {
                alert('Veuillez sélectionner un bassin manuel (marqué [MANUEL]) pour le supprimer.');
                return;
            }

            if (!confirm('Voulez-vous vraiment supprimer ce bassin manuel ?')) return;

            fetch(`/api/v1/manual-basin/${cid}`, { method: 'DELETE' })
                .then(r => r.json())
                .then(() => {
                    alert('Bassin supprimé.');
                    document.getElementById('detect-cluster-btn').click();
                });
        };

        carte.on('click', (e) => {
            if (!state.editor.active || state.editor.mode !== 'create') return;

            const latlng = e.latlng;
            if (state.editor.points.length >= 2) {
                const firstPoint = state.editor.points[0];
                const dist = carte.latLngToContainerPoint(latlng).distanceTo(carte.latLngToContainerPoint(firstPoint));

                if (dist < 25) {
                    finaliserPolygone();
                    return;
                }
            }

            ajouterPointPolygone(latlng);
        });

        carte.on('contextmenu', (e) => {
            if (state.editor.active && state.editor.mode === 'create') {
                L.DomEvent.preventDefault(e);
                if (state.editor.points.length > 2) {
                    finaliserPolygone();
                } else {
                    alert('Tracez au moins 3 points avant de terminer.');
                }
            }
        });

        window.choisirExutoireManuel = function(idx) {
            const ex = state.editor.tempExutoires[idx];
            state.editor.foundOutfall = ex;
            document.getElementById('cluster-status').innerHTML = `<b>${state.editor.selectedConduits.size}</b> tronçons sélectionnés.<br>✅ Exutoire : <b>${ex.nom}</b><br><br>👉 Cliquez sur 💾 pour enregistrer.`;
            document.getElementById('btn-save-edit').disabled = false;
        };

        window.activerPickExutoire = function() {
            state.editor.mode = 'pick_exutoire';
            carte.getContainer().style.cursor = 'crosshair';

            carte.once('click', (e) => {
                state.editor.foundOutfall = {
                    id: 'custom_' + Date.now(),
                    nom: 'Point désigné',
                    type: 'manuel',
                    latlng: e.latlng
                };
                document.getElementById('cluster-status').innerHTML = `<b>${state.editor.selectedConduits.size}</b> tronçons sélectionnés.<br>🎯 Exutoire fixé.<br><br>👉 Cliquez sur 💾 pour enregistrer.`;
                state.editor.mode = 'create';
                carte.getContainer().style.cursor = '';
                document.getElementById('btn-save-edit').disabled = false;
            });
        };
    }

    function activerModeEdition(mode) {
        const carte = state.carte;
        const editor = state.editor;
        editor.active = true;
        editor.mode = mode;
        editor.selectedConduits.clear();
        editor.points = [];

        const btn = document.getElementById('btn-create-bassin');
        btn.classList.add('active');
        btn.innerHTML = '<i class="fas fa-times"></i>';
        btn.setAttribute('data-tip', 'Annuler la création');

        carte.dragging.disable();
        carte.getContainer().style.cursor = 'crosshair';
        document.getElementById('cluster-status').innerHTML = '<b>Mode Édition</b><br>Tracez votre polygone point par point...';
    }

    function desactiverModeEdition() {
        const carte = state.carte;
        const editor = state.editor;
        editor.active = false;
        editor.mode = null;

        const btn = document.getElementById('btn-create-bassin');
        btn.classList.remove('active');
        btn.innerHTML = '<i class="fas fa-draw-polygon"></i>';
        btn.setAttribute('data-tip', 'Nouveau Bassin (Polygone)');

        if (editor.tempPolyline) carte.removeLayer(editor.tempPolyline);
        if (editor.tempPolygon) carte.removeLayer(editor.tempPolygon);
        editor.markers.forEach(m => carte.removeLayer(m));

        editor.points = [];
        editor.markers = [];
        editor.tempPolyline = null;
        editor.tempPolygon = null;

        carte.dragging.enable();
        carte.getContainer().style.cursor = '';
        document.getElementById('btn-save-edit').disabled = true;
        nettoyerSurlignageSelection();
    }

    function nettoyerSurlignageSelection() {
        const state = window.mapState;
        if (state.activeClusterLayer) {
            (window.highlightCluster || function() {})(document.getElementById('bassin-select').value || null, state.activeClusterLayer);
        } else if (state.couches.conduites) {
            state.couches.conduites.setStyle({ color: '#3498db', weight: 3, opacity: 1 });
        }
    }

    function ajouterPointPolygone(latlng) {
        const carte = state.carte;
        const editor = state.editor;
        editor.points.push(latlng);

        const marker = L.circleMarker(latlng, {
            radius: 6,
            color: '#e94560',
            fillColor: '#fff',
            fillOpacity: 1,
            weight: 2,
            pane: 'markerPane',
            interactive: true
        }).addTo(carte);
        editor.markers.push(marker);

        if (editor.points.length === 1) {
            marker.setStyle({ radius: 10, color: '#f1c40f', weight: 4 });
            marker.bindTooltip('CLIQUEZ ICI pour fermer', { permanent: true, direction: 'top', className: 'close-tooltip' });
            marker.on('click', (ev) => {
                L.DomEvent.stopPropagation(ev);
                if (editor.points.length > 2) finaliserPolygone();
            });
        }

        if (editor.tempPolyline) carte.removeLayer(editor.tempPolyline);
        editor.tempPolyline = L.polyline(editor.points, { color: '#e94560', weight: 3, dashArray: '5, 5' }).addTo(carte);
    }

    function finaliserPolygone() {
        const carte = state.carte;
        const editor = state.editor;
        if (editor.tempPolyline) carte.removeLayer(editor.tempPolyline);

        editor.tempPolygon = L.polygon(editor.points, {
            color: '#e94560',
            weight: 2,
            fillOpacity: 0.15,
            dashArray: null
        }).addTo(carte);

        editor.markers.forEach(m => carte.removeLayer(m));
        editor.markers = [];

        const pts = [...editor.points];
        editor.points = [];
        capturerTronconsDansZone(pts);
    }

    function capturerTronconsDansZone(polyPoints) {
        const state = window.mapState;
        const editor = state.editor;
        let count = 0;
        const exutoiresTrouves = [];
        editor.selectedConduits.clear();

        const targets = [];
        if (state.activeClusterLayer) targets.push(state.activeClusterLayer);
        if (state.couches.conduites) targets.push(state.couches.conduites);

        targets.forEach(parentLayer => {
            parentLayer.eachLayer(layer => {
                if (layer.feature && layer.feature.geometry && layer.feature.geometry.type === 'LineString') {
                    const coords = layer.getLatLngs();
                    const isInside = coords.some(pt => isPointInPolygon(pt, polyPoints));
                    if (isInside) {
                        const props = layer.feature.properties;
                        const id = props.conduit_id || props.fid || props.ID;
                        if (id && !editor.selectedConduits.has(id)) {
                            editor.selectedConduits.add(id);
                            layer.setStyle({ color: '#f1c40f', weight: 8, opacity: 1 });
                            count++;
                        }
                    }
                }
            });
        });

        ['stations', 'step', 'ouvrages'].forEach(type => {
            if (state.couches[type]) {
                state.couches[type].eachLayer(layer => {
                    if (isPointInPolygon(layer.getLatLng(), polyPoints)) {
                        exutoiresTrouves.push({
                            id: layer.feature.properties.fid || layer.feature.properties.ID,
                            nom: layer.feature.properties.nom || layer.feature.properties.NOM || type,
                            type,
                            latlng: layer.getLatLng()
                        });
                    }
                });
            }
        });

        gererResultatCapture(count, exutoiresTrouves);
    }

    function gererResultatCapture(count, exutoires) {
        const statusDiv = document.getElementById('cluster-status');
        const editor = window.mapState.editor;

        if (count === 0) {
            statusDiv.innerHTML = '⚠️ Aucun tronçon capturé.<br>Cliquez sur le <b>X</b> pour recommencer.';
            return;
        }

        let msg = `<b>${count}</b> tronçons sélectionnés.<br>`;

        if (exutoires.length === 1) {
            msg += `✅ Exutoire : <b>${exutoires[0].nom}</b><br><br>👉 Cliquez sur 💾 pour enregistrer.`;
            editor.foundOutfall = exutoires[0];
            document.getElementById('btn-save-edit').disabled = false;
        } else if (exutoires.length > 1) {
            msg += '❓ Plusieurs exutoires trouvés. Cliquez sur le bon :<br>';
            exutoires.forEach((ex, idx) => {
                msg += `<button class="cluster-button" style="margin-top:5px;" onclick="choisirExutoireManuel(${idx})">${ex.nom}</button>`;
            });
            editor.tempExutoires = exutoires;
        } else {
            msg += '⚠️ Aucun exutoire détecté.<br><b>Désignez le point de sortie sur la carte...</b>';
            window.activerPickExutoire();
        }

        statusDiv.innerHTML = msg;
    }

    window.initManualBasins = initManualBasins;
    window.highlightCluster = highlightCluster;
})();
