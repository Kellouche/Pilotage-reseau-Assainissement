/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-09
 * Objet : Module interactif de calcul et tracé de profil en long hydraulique (Phase 6.A)
 * ================================================================================
 */

window.profilLongState = {
    active: false,
    step: 'amont',
    nodeAmont: null,
    nodeAval: null,
    chartInstance: null,
    highlightLayer: null,
    markersLayer: null,
    lastData: null
};

/**
 * Récupère l'instance Leaflet globale (carte ou map)
 */
function _getCarte() {
    return window.carte || window.map || (typeof carte !== 'undefined' ? carte : null);
}

/**
 * Active ou désactive le mode de sélection sur la carte
 */
function toggleProfilLongMode() {
    const state = window.profilLongState;
    const btn = document.getElementById('btn-profil-long');
    const panel = document.getElementById('panel-profil-long');
    const banner = document.getElementById('profil-selection-banner');
    const map = _getCarte();

    if (!state.active) {
        // VÉRIFICATION : Une simulation doit être active pour pouvoir générer le profil en long hydraulique (HGL)
        const hasSim = !!(window._dernierResultatSimulation && 
                          window._dernierResultatSimulation.conduit_results && 
                          Object.keys(window._dernierResultatSimulation.conduit_results).length > 0);

        if (!hasSim) {
            alert("Lancer une simulation pour avoir un profil en long");
            if (panel) panel.style.display = 'none';
            return;
        }

        state.active = true;
        state.step = 'amont';
        if (btn) btn.classList.add('active');

        // Fermer les popups de modification existantes
        if (map) {
            map.closePopup();
            const mapEl = document.getElementById('map');
            if (mapEl) mapEl.style.cursor = 'crosshair';
        }

        // Afficher la bannière d'aide
        if (banner) {
            banner.style.display = 'flex';
            document.getElementById('profil-selection-text').innerHTML =
                'Mode Profil en long actif : Cliquez sur le <b>regard amont</b> (vert) sur la carte...';
        }

        // Nettoyer les sélections précédentes si nouveau tracé
        _nettoyerMarqueursProfil();
    } else {
        // Si le panneau est fermé, l'ouvrir s'il y a déjà des données
        if (panel && panel.style.display === 'none' && state.lastData) {
            panel.style.display = 'flex';
            // Initialiser le déplacement du panneau (draggable)
            if (typeof _initProfilLongDraggable === 'function') {
                _initProfilLongDraggable();
            }
        } else {
            annulerSelectionProfil();
        }
    }
}

/**
 * Annule la sélection en cours
 */
function annulerSelectionProfil() {
    const state = window.profilLongState;
    state.active = false;
    state.step = 'amont';

    const btn = document.getElementById('btn-profil-long');
    if (btn) btn.classList.remove('active');

    const mapEl = document.getElementById('map');
    if (mapEl) mapEl.style.cursor = '';

    const banner = document.getElementById('profil-selection-banner');
    if (banner) banner.style.display = 'none';

    _nettoyerMarqueursProfil();
}

/**
 * Ferme le panneau du profil en long
 */
function fermerProfilLong() {
    const panel = document.getElementById('panel-profil-long');
    if (panel) panel.style.display = 'none';
    annulerSelectionProfil();

    const map = _getCarte();
    if (map && window.profilLongState.highlightLayer) {
        map.removeLayer(window.profilLongState.highlightLayer);
        window.profilLongState.highlightLayer = null;
    }
}

/**
 * Gère le clic sur un regard ou nœud physique sur la carte Leaflet
 */
window.handleRegardClickForProfil = function(code, latlng) {
    const state = window.profilLongState;
    if (!state.active || !code) return;

    const map = _getCarte();
    if (!map) return;

    if (!state.markersLayer) {
        state.markersLayer = L.layerGroup().addTo(map);
    }

    if (state.step === 'amont') {
        state.nodeAmont = String(code).trim();
        state.step = 'aval';

        const inpAmont = document.getElementById('input-profil-amont');
        if (inpAmont) inpAmont.value = state.nodeAmont;

        // Placer un marqueur vert pour l'amont
        if (latlng) {
            const m = L.circleMarker(latlng, {
                radius: 9,
                color: '#10b981',
                fillColor: '#34d399',
                fillOpacity: 0.95,
                weight: 3
            }).bindTooltip(`<b>Amont:</b> ${state.nodeAmont}`, { permanent: true, direction: 'top' });
            state.markersLayer.addLayer(m);
        }

        const banner = document.getElementById('profil-selection-banner');
        const text = document.getElementById('profil-selection-text');
        if (banner) banner.style.display = 'flex';
        if (text) {
            text.innerHTML = `Amont : <b>${state.nodeAmont}</b> ✅ — Cliquez maintenant sur le <b>regard aval</b>...`;
        }

    } else if (state.step === 'aval') {
        state.nodeAval = String(code).trim();
        state.active = false; // Sélection terminée

        const btn = document.getElementById('btn-profil-long');
        if (btn) btn.classList.remove('active');

        const mapEl = document.getElementById('map');
        if (mapEl) mapEl.style.cursor = '';

        const inpAval = document.getElementById('input-profil-aval');
        if (inpAval) inpAval.value = state.nodeAval;

        // Placer marqueur bleu pour l'aval
        if (latlng) {
            const m = L.circleMarker(latlng, {
                radius: 9,
                color: '#0284c7',
                fillColor: '#38bdf8',
                fillOpacity: 0.95,
                weight: 3
            }).bindTooltip(`<b>Aval:</b> ${state.nodeAval}`, { permanent: true, direction: 'bottom' });
            state.markersLayer.addLayer(m);
        }

        const banner = document.getElementById('profil-selection-banner');
        if (banner) banner.style.display = 'none';

        // Lancer la requête de profil
        chargerProfilLong(state.nodeAmont, state.nodeAval);
    }
};

/**
 * Crée un motif de hachures diagonales pour la zone de charge piézométrique (HGL > Plan d'eau)
 */
function _creerPatternHachures(couleurLigne, couleurFond, espacement) {
    const pCanvas = document.createElement('canvas');
    const size = espacement || 10;
    pCanvas.width = size;
    pCanvas.height = size;
    const pctx = pCanvas.getContext('2d');

    if (couleurFond) {
        pctx.fillStyle = couleurFond;
        pctx.fillRect(0, 0, size, size);
    }

    pctx.strokeStyle = couleurLigne || 'rgba(239, 68, 68, 0.45)';
    pctx.lineWidth = 1.8;
    pctx.beginPath();
    pctx.moveTo(0, size);
    pctx.lineTo(size, 0);
    pctx.stroke();

    pctx.beginPath();
    pctx.moveTo(-1, 1);
    pctx.lineTo(1, -1);
    pctx.stroke();

    pctx.beginPath();
    pctx.moveTo(size - 1, size + 1);
    pctx.lineTo(size + 1, size - 1);
    pctx.stroke();

    return pctx.createPattern(pCanvas, 'repeat');
}

/**
 * Synchronise la saisie manuelle dans le champ regard amont
 */
window.synchroniserInputProfilAmont = function(val) {
    if (val && val.trim()) {
        const v = val.trim();
        window.profilLongState.nodeAmont = v;
        window.profilLongState.nodeAval = null; // Reset aval si amont change
        window.profilLongState.step = 'amont'; // Réinitialiser la machine à états
        const inpB = document.getElementById('input-profil-aval');
        if (inpB) inpB.value = '';
        // Mettre à jour le marqueur carte pour l'amont
        _mettreAJourMarqueurRegard(v, 'amont');
    }
};

/**
 * Synchronise la saisie manuelle dans le champ regard aval
 */
window.synchroniserInputProfilAval = function(val) {
    if (val && val.trim()) {
        const v = val.trim();
        window.profilLongState.nodeAval = v;
        window.profilLongState.step = 'amont'; // Réinitialiser la machine à états
        // Mettre à jour le marqueur carte pour l'aval
        _mettreAJourMarqueurRegard(v, 'aval');
    }
};

/**
 * Met à jour le marqueur carte pour un regard donné (après saisie manuelle)
 */
function _mettreAJourMarqueurRegard(code, role) {
    const map = _getCarte();
    if (!map || !code) return;
    const ll = _trouverCoordonneesRegard(code);
    if (!ll) return;
    // Supprimer ancien marqueur de ce rôle
    const state = window.profilLongState;
    if (state.markersLayer) {
        // On ne peut pas cibler un seul marqueur facilement, on reconstruit
        // Les marqueurs seront recalculés au prochain chargement de profil
    }
    // Afficher un marqueur temporaire pour ce regard
    const color = role === 'amont' ? '#10b981' : '#0284c7';
    const fillColor = role === 'amont' ? '#34d399' : '#38bdf8';
    const label = role === 'amont' ? 'Amont' : 'Aval';
    if (state.markersLayer) {
        state.markersLayer.clearLayers();
        const m = L.circleMarker(ll, {
            radius: 9,
            color: color,
            fillColor: fillColor,
            fillOpacity: 0.95,
            weight: 3
        }).bindTooltip(`<b>${label}:</b> ${code}`, { permanent: true, direction: 'top' });
        state.markersLayer.addLayer(m);
    }
}

/**
 * Inverse les regards amont et aval
 */
function inverserRegardsProfil() {
    const inpA = document.getElementById('input-profil-amont');
    const inpB = document.getElementById('input-profil-aval');
    const a = inpA ? inpA.value.trim() : (window.profilLongState.nodeAmont || '');
    const b = inpB ? inpB.value.trim() : (window.profilLongState.nodeAval || '');
    if (!a && !b) return;

    window.profilLongState.nodeAmont = b;
    window.profilLongState.nodeAval = a;

    if (inpA) inpA.value = b;
    if (inpB) inpB.value = a;

    // Mettre à jour les marqueurs carte
    const state = window.profilLongState;
    if (state.markersLayer) state.markersLayer.clearLayers();
    if (a) _mettreAJourMarqueurRegard(b, 'amont');
    if (b) _mettreAJourMarqueurRegard(a, 'aval');

    if (a && b) {
        chargerProfilLong(b, a);
    }
}

/**
 * Rafraîchit le profil actuel (supporte la saisie manuelle directe au clavier)
 */
function rafraichirProfilLong() {
    const inpA = document.getElementById('input-profil-amont');
    const inpB = document.getElementById('input-profil-aval');
    const a = inpA ? inpA.value.trim() : (window.profilLongState.nodeAmont || '');
    const b = inpB ? inpB.value.trim() : (window.profilLongState.nodeAval || '');

    if (!a || !b) {
        alert("Veuillez saisir ou sélectionner un regard amont et un regard aval.");
        return;
    }

    window.profilLongState.nodeAmont = a;
    window.profilLongState.nodeAval = b;
    chargerProfilLong(a, b);
}

/**
 * Appelle l'API et affiche le profil en long
 */
function chargerProfilLong(nodeAmont, nodeAval) {
    const panel = document.getElementById('panel-profil-long');

    const url = `/api/v1/simulations/profil-en-long?node_amont=${encodeURIComponent(nodeAmont)}&node_aval=${encodeURIComponent(nodeAval)}`;

    fetch(url)
        .then(response => {
            if (!response.ok) {
                return response.json().then(err => {
                    throw new Error(err.detail || `Erreur serveur (${response.status})`);
                });
            }
            return response.json();
        })
        .then(data => {
            window.profilLongState.lastData = data;
            if (panel) panel.style.display = 'flex';
            // Initialiser le déplacement du panneau (draggable)
            if (typeof _initProfilLongDraggable === 'function') {
                _initProfilLongDraggable();
            }
            afficherProfilLong(data);
        })
        .catch(err => {
            console.error("Erreur profil en long:", err);
            if (panel) panel.style.display = 'none';
            const msg = (err && err.message) ? err.message : '';
            if (msg.includes("Simulation non trouvée") || msg.includes("non trouvée") || msg.includes("404")) {
                alert("Lancer une simulation pour avoir un profil en long");
            } else {
                alert(`Impossible de générer le profil en long :\n${msg}`);
            }
            annulerSelectionProfil();
        });
}

/**
 * Rendu graphique Chart.js et mise à jour de l'interface
 */
function afficherProfilLong(data) {
    if (!data || !data.segments || data.segments.length === 0) return;

    // 1. Badges d'en-tête
    const bTroncons = document.getElementById('badge-profil-troncons');
    const bLongueur = document.getElementById('badge-profil-longueur');
    const bSurcharges = document.getElementById('badge-profil-surcharges');

    if (bTroncons) {
        bTroncons.textContent = `${data.nb_troncons} tronçons`;
        bTroncons.style.display = 'inline-block';
    }
    if (bLongueur) {
        bLongueur.textContent = `${data.longueur_totale_m} m`;
        bLongueur.style.display = 'inline-block';
    }
    if (bSurcharges) {
        bSurcharges.textContent = `${data.conduites_en_charge} surcharge${data.conduites_en_charge > 1 ? 's' : ''}`;
        bSurcharges.style.display = data.conduites_en_charge > 0 ? 'inline-block' : 'none';
    }

    // 2. Alertes et recommandations
    const alertContainer = document.getElementById('profil-alertes-container');
    const alertList = document.getElementById('profil-alertes-list');
    if (alertContainer && alertList) {
        if (data.alertes && data.alertes.length > 0) {
            alertContainer.style.display = 'flex';
            alertList.innerHTML = data.alertes.map(a => `
                <div class="alerte-card ${a.type}">
                    <div class="alerte-msg">${a.message}</div>
                    ${a.observations ? `<div class="alerte-obs" style="font-size: 0.72rem; color: #cbd5e1; margin: 2px 0;">• ${a.observations}</div>` : ''}
                    <div class="alerte-reco">💡 ${a.recommandation}</div>
                </div>
            `).join('');
        } else {
            alertContainer.style.display = 'none';
        }
    }

    // 3. Tracé sur la carte Leaflet
    _surlignerCheminCarte(data.segments);

    // 4. Préparer les données pour Chart.js
    const labels = data.segments.map(s => `${s.node_id}\n(${s.distance_m}m)`);
    const terrainData = data.segments.map(s => ({ x: s.distance_m, y: s.z_terrain }));
    const genSupData = data.segments.map(s => ({ x: s.distance_m, y: s.z_gen_superieure }));
    const radierData = data.segments.map(s => ({ x: s.distance_m, y: s.z_radier }));
    const eauConduiteData = data.segments.map(s => ({ x: s.distance_m, y: s.z_eau_conduite !== undefined ? s.z_eau_conduite : s.z_radier }));
    const hglData = data.segments.map(s => ({ x: s.distance_m, y: s.z_hgl }));

    // Classification couleur et taille des points HGL (🟢 Libre / 🟡 Surcharge / 🔴 Débordement)
    const hglPointColors = data.segments.map(s => {
        if (s.hgl_regime === 'debordement' || (s.z_hgl && s.z_hgl >= s.z_terrain)) {
            return '#ef4444'; // 🔴 Débordement au sol
        } else if (s.hgl_regime === 'surcharge' || (s.z_hgl && s.z_hgl > s.z_gen_superieure)) {
            return '#f59e0b'; // 🟡 Surcharge en cheminée
        }
        return '#10b981'; // 🟢 Écoulement libre
    });

    const hglPointRadius = data.segments.map(s => {
        if (s.hgl_regime === 'debordement' || (s.z_hgl && s.z_hgl >= s.z_terrain)) return 7;
        if (s.hgl_regime === 'surcharge' || (s.z_hgl && s.z_hgl > s.z_gen_superieure)) return 5.5;
        return 4;
    });

    const ctx = document.getElementById('canvas-profil-long');
    if (!ctx) return;

    if (window.profilLongState.chartInstance) {
        window.profilLongState.chartInstance.destroy();
    }

    // Motif de hachures diagonales pour la colonne de charge piézométrique (HGL > Plan d'eau réel)
    const patternHachures = _creerPatternHachures('rgba(239, 68, 68, 0.45)', 'rgba(245, 158, 11, 0.08)', 10);

    // Création du graphique Chart.js avec Plan d'Eau Réel dans la Conduite et Zone de Charge Hachurée
    window.profilLongState.chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Terrain naturel (MNT)',
                    data: terrainData,
                    borderColor: '#10b981',
                    backgroundColor: 'transparent',
                    borderWidth: 2.2,
                    pointRadius: 4.5,
                    pointBackgroundColor: '#10b981',
                    fill: false,
                    tension: 0.1
                },
                {
                    label: 'Génératrice supérieure (haut de conduite)',
                    data: genSupData,
                    borderColor: '#64748b',
                    borderWidth: 1.5,
                    borderDash: [5, 4],
                    pointRadius: 2.5,
                    pointBackgroundColor: '#64748b',
                    fill: false,
                    tension: 0
                },
                {
                    label: "Fil d'eau (cote radier)",
                    data: radierData,
                    borderColor: '#475569',
                    backgroundColor: 'rgba(100, 116, 139, 0.10)',
                    borderWidth: 2.5,
                    pointRadius: 4.5,
                    pointBackgroundColor: data.segments.map(s => s.node_color || '#475569'),
                    fill: '-1', // Matérialise le vide physique intérieur de la conduite
                    tension: 0
                },
                {
                    label: "Plan d'eau réel dans la conduite (WSP / hauteur d'eau)",
                    data: eauConduiteData,
                    borderColor: '#0284c7',
                    backgroundColor: 'rgba(14, 165, 233, 0.45)', // Remplissage bleu eau translucide
                    borderWidth: 2.5,
                    pointRadius: 3.5,
                    pointBackgroundColor: '#0284c7',
                    fill: '-1', // Remplit vers le radier (Dataset 2)
                    tension: 0
                },
                {
                    label: 'Ligne de charge HGL (zone de surpression hachurée)',
                    data: hglData,
                    borderColor: '#f59e0b',
                    backgroundColor: patternHachures, // Hachures diagonales d'alerte entre WSP et HGL
                    borderWidth: 3.5,
                    pointRadius: hglPointRadius,
                    pointBackgroundColor: hglPointColors,
                    pointBorderColor: '#ffffff',
                    pointBorderWidth: 1.5,
                    fill: '-1', // Hachure la zone de mise en charge vers le Plan d'eau réel (Dataset 3)
                    tension: 0.15
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 350 },
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        color: '#cbd5e1',
                        font: { size: 11, family: 'Plus Jakarta Sans', weight: '600' },
                        boxWidth: 14,
                        padding: 10
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.96)',
                    titleColor: '#38bdf8',
                    bodyColor: '#e2e8f0',
                    borderColor: 'rgba(56, 189, 248, 0.4)',
                    borderWidth: 1.5,
                    padding: 12,
                    callbacks: {
                        title: function(items) {
                            const idx = items[0].dataIndex;
                            const s = data.segments[idx];
                            return `Regard : ${s.node_id} (Distance : ${s.distance_m} m)`;
                        },
                        beforeBody: function(items) {
                            const idx = items[0].dataIndex;
                            const s = data.segments[idx];
                            if (s.hgl_regime === 'debordement' || (s.z_hgl && s.z_hgl >= s.z_terrain)) {
                                return `🔴 ÉTAT : DÉBORDEMENT AU SOL (HGL ≥ Terrain)`;
                            } else if (s.hgl_regime === 'surcharge' || (s.z_hgl && s.z_hgl > s.z_gen_superieure)) {
                                return `🟡 ÉTAT : SURCHARGE EN CHARGE (HGL > Voûte)`;
                            }
                            return `🟢 ÉTAT : ÉCOULEMENT LIBRE SAIN (HGL < Voûte)`;
                        },
                        afterBody: function(items) {
                            const idx = items[0].dataIndex;
                            const s = data.segments[idx];
                            const zEau = s.z_eau_conduite !== undefined ? s.z_eau_conduite : s.z_radier;
                            const hEau = Math.max(0, zEau - s.z_radier);
                            const lines = [
                                `• Plan d'eau conduite (WSP) : ${zEau.toFixed(2)} m (Hauteur d'eau : ${hEau.toFixed(2)} m)`,
                                `• Profondeur regard : ${s.profondeur_m} m`
                            ];

                            if (s.pression_m && s.pression_m > 0) {
                                lines.push(`• Charge au-dessus voûte : +${s.pression_m} m (Pression)`);
                            }
                            if (s.revanche_m && s.revanche_m > 0) {
                                lines.push(`• Revanche avant tampon : ${s.revanche_m} m`);
                            } else if (s.hgl_regime === 'debordement' || (s.z_hgl && s.z_hgl >= s.z_terrain)) {
                                lines.push(`• Tampon atteint : Débordement actif sur voirie`);
                            }

                            if (s.conduit_sortant) {
                                const c = s.conduit_sortant;
                                lines.push(`• Conduite aval : ${c.cid} (Ø${c.diam_mm} mm, L=${c.length}m)`);
                                if (c.flow_ratio > 0) {
                                    lines.push(`• Taux de charge Q/Qmax : ${(c.flow_ratio * 100).toFixed(0)}% (${c.status})`);
                                }
                            }
                            return lines;
                        }
                    }
                }
            },
            scales: {
                x: {
                    type: 'category',
                    grid: { color: 'rgba(255, 255, 255, 0.06)' },
                    ticks: {
                        color: '#94a3b8',
                        font: { size: 10, family: 'JetBrains Mono' }
                    },
                    title: {
                        display: true,
                        text: "Distance cumulée depuis l'amont (mètres)",
                        color: '#64748b',
                        font: { size: 11 }
                    }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.08)' },
                    ticks: {
                        color: '#94a3b8',
                        font: { size: 10, family: 'JetBrains Mono' }
                    },
                    title: {
                        display: true,
                        text: 'Altitude (mètres)',
                        color: '#64748b',
                        font: { size: 11 }
                    }
                }
            }
        }
    });
}

/**
 * Récupère les coordonnées géographiques d'un regard depuis toutes les couches de points
 */
function _trouverCoordonneesRegard(code) {
    if (!code || !window.couches) return null;
    const codeTrim = String(code).trim();
    const types = ['regards', 'rejets', 'stations', 'step', 'ouvrages'];
    let found = null;
    for (const type of types) {
        const couche = window.couches[type];
        if (couche && typeof couche.eachLayer === 'function') {
            couche.eachLayer(l => {
                if (found) return;
                if (l.feature && l.feature.properties) {
                    const p = l.feature.properties;
                    const c = p.Code || p.code || p.CODE || p.id || p.ID || p.Id || p.nom || p.NOM || p.Nom || p.CODEPRR || p.NUMERO || (l.feature && l.feature.id);
                    if (c && String(c).trim() === codeTrim) {
                        found = l.getLatLng();
                    }
                }
            });
        }
        if (found) break;
    }
    return found;
}

/**
 * Surligne le tracé sur la carte Leaflet
 */
function _surlignerCheminCarte(segments) {
    const map = _getCarte();
    if (!map || !segments || segments.length === 0) return;

    const state = window.profilLongState;
    if (state.highlightLayer) {
        map.removeLayer(state.highlightLayer);
        state.highlightLayer = null;
    }

    // Récupérer les coordonnées géographiques des regards depuis TOUTES les couches de points
    const latlngs = [];
    segments.forEach(s => {
        const ll = _trouverCoordonneesRegard(s.node_id);
        if (ll) latlngs.push(ll);
    });

    if (latlngs.length >= 2) {
        state.highlightLayer = L.polyline(latlngs, {
            color: '#f59e0b',
            weight: 6,
            opacity: 0.9,
            dashArray: '8, 8',
            className: 'pulsing-profil-path'
        }).addTo(map);

        // Zoomer légèrement pour cadrer le profil
        map.fitBounds(state.highlightLayer.getBounds(), { padding: [60, 60], maxZoom: 17 });
    }
}

/**
 * Nettoie les marqueurs temporaires
 */
function _nettoyerMarqueursProfil() {
    const state = window.profilLongState;
    const map = _getCarte();
    if (state.markersLayer && map) {
        state.markersLayer.clearLayers();
    }
}

/**
 * Exporte l'image PNG du graphique
 */
function exporterProfilImage() {
    const chart = window.profilLongState.chartInstance;
    if (!chart) {
        alert("Aucun profil actif à exporter.");
        return;
    }
    const a = document.createElement('a');
    a.href = chart.toBase64Image('image/png', 1.0);
    const nodeA = window.profilLongState.nodeAmont || 'amont';
    const nodeB = window.profilLongState.nodeAval || 'aval';
    a.download = `profil_long_${nodeA}_vers_${nodeB}.png`;
    a.click();
}

/**
 * Initialise le déplacement à la souris (Draggable) du panneau Profil en long
 */
function _initProfilLongDraggable() {
    const panel = document.getElementById('panel-profil-long');
    const handle = document.getElementById('profil-long-drag-handle');
    if (!panel || !handle || panel._draggableInitDone) return;

    panel._draggableInitDone = true;
    let startX, startY, origX, origY;

    handle.addEventListener('mousedown', (e) => {
        if (e.target.closest('button') || e.target.closest('input') || e.target.closest('.btn-close-profil')) return;
        e.preventDefault();
        startX = e.clientX;
        startY = e.clientY;
        origX = panel.offsetLeft;
        origY = panel.offsetTop;

        const onMouseMove = (ev) => {
            const dx = ev.clientX - startX;
            const dy = ev.clientY - startY;
            panel.style.left = `${origX + dx}px`;
            panel.style.top = `${origY + dy}px`;
            panel.style.right = 'auto';
            panel.style.bottom = 'auto';
        };

        const onMouseUp = () => {
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
        };

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    });
}

// Exposer pour appel depuis d'autres modules si nécessaire
window.initProfilLongDraggable = _initProfilLongDraggable;
