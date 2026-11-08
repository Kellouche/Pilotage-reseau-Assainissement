/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Outils de dessin géométrique et sectorisation manuelle de bassins versants
 * ================================================================================
 */

// Plus besoin de disableClickPropagation car toolbar est hors de map

        function activerModeEdition(mode) {
            editorState.active = true;
            editorState.mode = mode;
            editorState.selectedConduits.clear();
            editorState.points = [];
            
            const btn = document.getElementById('btn-create-bassin');
            btn.classList.add('active');
            btn.innerHTML = '<i class="fas fa-times"></i>'; // Changer en "Annuler"
            btn.setAttribute('data-tip', 'Annuler la création');

            carte.dragging.disable(); 
            carte.getContainer().style.cursor = 'crosshair';
            document.getElementById('cluster-status').innerHTML = "<b>Mode Édition</b><br>Tracez votre polygone point par point...";
        }

        function desactiverModeEdition() {
            editorState.active = false;
            editorState.mode = null;
            
            const btn = document.getElementById('btn-create-bassin');
            btn.classList.remove('active');
            btn.innerHTML = '<i class="fas fa-draw-polygon"></i>';
            btn.setAttribute('data-tip', 'Nouveau Bassin (Polygone)');

            if (editorState.tempPolyline) carte.removeLayer(editorState.tempPolyline);
            if (editorState.tempPolygon) carte.removeLayer(editorState.tempPolygon);
            editorState.markers.forEach(m => carte.removeLayer(m));
            
            editorState.points = [];
            editorState.markers = [];
            editorState.tempPolyline = null;
            editorState.tempPolygon = null;

            carte.dragging.enable();
            carte.getContainer().style.cursor = '';
            document.getElementById('btn-save-edit').disabled = true;
            nettoyerSurlignageSelection();
        }

        function nettoyerSurlignageSelection() {
            // Rétablir le style original des tronçons
            if (_activeClusterLayer) {
                highlightCluster(document.getElementById('bassin-select').value || null, _activeClusterLayer);
            } else if (couches.conduites) {
                couches.conduites.setStyle({ color: '#3498db', weight: 3, opacity: 1 });
            }
        }

        // Événements souris pour le tracé du polygone
        carte.on('click', (e) => {
            if (!editorState.active || editorState.mode !== 'create') return;
            
            const latlng = e.latlng;
            console.log("[Editor] Clic à:", latlng);
            
            // Si on clique sur le premier point (ou proche), on ferme le polygone
            if (editorState.points.length >= 2) {
                const firstPoint = editorState.points[0];
                const dist = carte.latLngToContainerPoint(latlng).distanceTo(carte.latLngToContainerPoint(firstPoint));
                console.log("[Editor] Distance au départ:", dist.toFixed(1), "px");
                
                if (dist < 25) { // Seuil augmenté à 25px pour plus de souplesse
                    console.log("[Editor] Fermeture par proximité");
                    finaliserPolygone();
                    return;
                }
            }

            ajouterPointPolygone(latlng);
        });

        // Fermeture par CLIC DROIT (Standard SIG)
        carte.on('contextmenu', (e) => {
            if (editorState.active && editorState.mode === 'create') {
                L.DomEvent.preventDefault(e); // Empêcher le menu du navigateur
                if (editorState.points.length > 2) {
                    console.log("[Editor] Fermeture par clic droit");
                    finaliserPolygone();
                } else {
                    alert("Tracez au moins 3 points avant de terminer.");
                }
            }
        });

        function ajouterPointPolygone(latlng) {
            editorState.points.push(latlng);
            
            // Ajouter un marqueur visuel
            const marker = L.circleMarker(latlng, {
                radius: 6, color: '#e94560', fillColor: '#fff', fillOpacity: 1, weight: 2,
                pane: 'markerPane', interactive: true
            }).addTo(carte);
            editorState.markers.push(marker);

            if (editorState.points.length === 1) {
                marker.setStyle({ radius: 10, color: '#f1c40f', weight: 4 });
                marker.bindTooltip("CLIQUEZ ICI pour fermer", { permanent: true, direction: 'top', className: 'close-tooltip' });
                
                marker.on('click', (ev) => {
                    console.log("[Editor] Clic direct sur marqueur départ");
                    L.DomEvent.stopPropagation(ev);
                    if (editorState.points.length > 2) finaliserPolygone();
                });
            }

            if (editorState.tempPolyline) carte.removeLayer(editorState.tempPolyline);
            editorState.tempPolyline = L.polyline(editorState.points, { color: '#e94560', weight: 3, dashArray: '5, 5' }).addTo(carte);
        }

        function finaliserPolygone() {
            console.log("[Editor] Finalisation du polygone avec", editorState.points.length, "points");
            if (editorState.tempPolyline) carte.removeLayer(editorState.tempPolyline);
            
            // Créer le polygone final
            editorState.tempPolygon = L.polygon(editorState.points, {
                color: "#e94560", weight: 2, fillOpacity: 0.15, dashArray: null
            }).addTo(carte);

            // Nettoyer les marqueurs de construction
            editorState.markers.forEach(m => carte.removeLayer(m));
            editorState.markers = [];

            const pts = [...editorState.points];
            editorState.points = []; // On vide pour bloquer le tracé
            
            // Lancer la détection
            capturerTronconsDansZone(pts);
        }

        // Algorithme Point-in-Polygon (Ray Casting) optimisé
        function isPointInPolygon(point, vs) {
            var x = point.lat, y = point.lng;
            var inside = false;
            for (var i = 0, j = vs.length - 1; i < vs.length; j = i++) {
                var xi = vs[i].lat, yi = vs[i].lng;
                var xj = vs[j].lat, yj = vs[j].lng;
                var intersect = ((yi > y) != (yj > y))
                    && (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
                if (intersect) inside = !inside;
            }
            return inside;
        }

        function capturerTronconsDansZone(polyPoints) {
            console.log("[Editor] Analyse de la zone...");
            let count = 0;
            let exutoiresTrouves = [];
            editorState.selectedConduits.clear();
            
            // 1. Capturer les tronçons
            // On cherche dans la couche de clusters active ET dans la couche réseau brute
            const targets = [];
            if (_activeClusterLayer) targets.push(_activeClusterLayer);
            if (couches.conduites) targets.push(couches.conduites);

            targets.forEach(parentLayer => {
                parentLayer.eachLayer(layer => {
                    if (layer.feature && layer.feature.geometry.type === 'LineString') {
                        const coords = layer.getLatLngs();
                        // Un tronçon est capturé si l'un de ses points est dedans
                        const isInside = coords.some(pt => isPointInPolygon(pt, polyPoints));
                        if (isInside) {
                            const props = layer.feature.properties;
                            const id = props.conduit_id || props.fid || props.ID;
                            if (id && !editorState.selectedConduits.has(id)) {
                                editorState.selectedConduits.add(id);
                                layer.setStyle({ color: '#f1c40f', weight: 8, opacity: 1 });
                                count++;
                            }
                        }
                    }
                });
            });

            // 2. Chercher les exutoires
            ['stations', 'step', 'ouvrages'].forEach(type => {
                if (couches[type]) {
                    couches[type].eachLayer(layer => {
                        if (isPointInPolygon(layer.getLatLng(), polyPoints)) {
                            exutoiresTrouves.push({
                                id: layer.feature.properties.fid || layer.feature.properties.ID,
                                nom: layer.feature.properties.nom || layer.feature.properties.NOM || type,
                                type: type,
                                latlng: layer.getLatLng()
                            });
                        }
                    });
                }
            });

            console.log("[Editor] Résultat capture:", count, "tronçons,", exutoiresTrouves.length, "exutoires");
            gererResultatCapture(count, exutoiresTrouves);
        }

        function gererResultatCapture(count, exutoires) {
            const statusDiv = document.getElementById('cluster-status');
            if (count === 0) {
                statusDiv.innerHTML = "⚠️ Aucun tronçon capturé.<br>Cliquez sur le <b>X</b> pour recommencer.";
                return;
            }

            let msg = `<b>${count}</b> tronçons sélectionnés.<br>`;
            
            if (exutoires.length === 1) {
                msg += `✅ Exutoire : <b>${exutoires[0].nom}</b><br><br>👉 Cliquez sur 💾 pour enregistrer.`;
                editorState.foundOutfall = exutoires[0];
                document.getElementById('btn-save-edit').disabled = false;
            } else if (exutoires.length > 1) {
                msg += `❓ Plusieurs exutoires trouvés. Cliquez sur le bon :<br>`;
                exutoires.forEach((ex, idx) => {
                    msg += `<button class="cluster-button" style="margin-top:5px;" onclick="choisirExutoireManuel(${idx})">${ex.nom}</button>`;
                });
                editorState.tempExutoires = exutoires;
            } else {
                msg += `⚠️ Aucun exutoire détecté.<br><b>Désignez le point de sortie sur la carte...</b>`;
                activerPickExutoire(); // Passage automatique en mode cible
            }

            statusDiv.innerHTML = msg;
        }

        // Choix parmi une liste (si plusieurs détectés)
        window.choisirExutoireManuel = function(idx) {
            const ex = editorState.tempExutoires[idx];
            editorState.foundOutfall = ex;
            const statusDiv = document.getElementById('cluster-status');
            statusDiv.innerHTML = `<b>${editorState.selectedConduits.size}</b> tronçons sélectionnés.<br>✅ Exutoire : <b>${ex.nom}</b><br><br>👉 Cliquez sur 💾 pour enregistrer.`;
            document.getElementById('btn-save-edit').disabled = false;
        };

        // Mode "Pick" : l'utilisateur clique sur la carte pour désigner le rejet
        window.activerPickExutoire = function() {
            editorState.mode = 'pick_exutoire';
            carte.getContainer().style.cursor = 'crosshair';
            
            carte.once('click', (e) => {
                editorState.foundOutfall = {
                    id: 'custom_' + Date.now(),
                    nom: "Point désigné",
                    type: "manuel",
                    latlng: e.latlng
                };
                document.getElementById('cluster-status').innerHTML = `<b>${editorState.selectedConduits.size}</b> tronçons sélectionnés.<br>🎯 Exutoire fixé.<br><br>👉 Cliquez sur 💾 pour enregistrer.`;
                editorState.mode = 'create';
                carte.getContainer().style.cursor = '';
                document.getElementById('btn-save-edit').disabled = false;
            });
        };

        // Sauvegarder le bassin manuel
        document.getElementById('btn-save-edit').onclick = function() {
            if (editorState.selectedConduits.size === 0) return;
            
            const data = {
                conduits: Array.from(editorState.selectedConduits),
                exutoire: editorState.foundOutfall || null,
                nom: prompt("Nom du bassin :", editorState.foundOutfall ? "Bassin " + editorState.foundOutfall.nom : "Bassin Manuel")
            };

            if (!data.nom) return;

            fetch('/api/v1/manual-basin', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            })
            .then(r => r.json())
            .then(res => {
                alert("Bassin manuel enregistré avec succès !");
                desactiverModeEdition();
                // Recharger les données pour voir le nouveau bassin
                if (typeof window.lancerPartitionnementBassins === 'function') {
                    window.lancerPartitionnementBassins(null, null, true, true);
                }
            })
            .catch(err => {
                console.error(err);
                alert("Erreur lors de la sauvegarde.");
            });
        };

        // Supprimer un bassin manuel
        document.getElementById('btn-delete-bassin').onclick = function() {
            const sel = document.getElementById('bassin-select');
            const cid = sel.value;
            if (!cid || !cid.startsWith('M_')) {
                alert("Veuillez sélectionner un bassin manuel (marqué [MANUEL]) pour le supprimer.");
                return;
            }
            
            if (!confirm("Voulez-vous vraiment supprimer ce bassin manuel ?")) return;

            fetch(`/api/v1/manual-basin/${cid}`, { method: 'DELETE' })
                .then(r => r.json())
                .then(res => {
                    alert("Bassin supprimé.");
                    // Recharger les clusters
                    if (typeof window.lancerPartitionnementBassins === 'function') {
                        window.lancerPartitionnementBassins(null, null, true, true);
                    }
                });
        };
