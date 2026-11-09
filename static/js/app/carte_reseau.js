/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Initialisation des calques réseau, styles graphiques et infobulles des ouvrages
 * ================================================================================
 */

function chargerDonneesInitiales() {
            // Montrer l'overlay de chargement
            montrerChargement(true);

            // Réinitialiser systématiquement l'affichage et les caches de données du modèle précédent
            if (typeof reinitialiserAffichageSimulation === 'function') {
                reinitialiserAffichageSimulation();
            }
            window._dernierResultatSimulation = null;
            window._clustersData = null;
            window._bassinNoms = {};
            window._bassinBounds = {};
            _selectedClusterId = null;
            if (typeof clusterCouche !== 'undefined' && clusterCouche) clusterCouche.clearLayers();
            if (typeof _activeClusterLayer !== 'undefined' && _activeClusterLayer) _activeClusterLayer.clearLayers();
            
            const bSel = document.getElementById('bassin-select');
            if (bSel) bSel.innerHTML = '<option value="">-- Réseau complet ou choisir un bassin --</option>';
            const bInfo = document.getElementById('bassin-info');
            if (bInfo) bInfo.innerHTML = '';
            const simBSel = document.getElementById('sim-select-bassin');
            if (simBSel) simBSel.innerHTML = '<option value="" disabled selected>-- Sélectionnez un bassin versant sectorisé --</option>';
            const badgeSb = document.getElementById('badge-subcatchments-count');
            if (badgeSb) { badgeSb.innerHTML = '-- SB'; badgeSb.style.background = ''; }
            
            fetch('/api/v1/layers')
                .then(r => r.json())
                .then(d => {
                    console.log('Données:', d.compteurs);
                    window._rawNetworkData = d;
                    if (d.project_name) {
                        const lbl = document.getElementById('topbar-project-label');
                        if (lbl) lbl.textContent = d.project_name;
                    }

                    // Vider les couches précédentes
                    Object.values(couches).forEach(l => l.clearLayers());

                    const totalObj = d.compteurs ? Object.values(d.compteurs).reduce((a, b) => a + b, 0) : 0;
                    if (d.is_empty || totalObj === 0) {
                        montrerChargement(false);
                        document.getElementById('stat-total').textContent = '0';
                        document.getElementById('mini-stats').innerHTML = '<span style="color: #f59e0b;"><i class="fas fa-info-circle me-1"></i> Projet vierge (aucun réseau)</span>';
                        document.getElementById('modal-project-status').textContent = 'Aucun réseau chargé — Espace de travail vierge';
                        const resetSec = document.getElementById('section-reset-project');
                        if (resetSec) resetSec.style.display = 'none';
                        montrerModalProjet(true);
                        return;
                    } else {
                        const resetSec = document.getElementById('section-reset-project');
                        if (resetSec) resetSec.style.display = 'block';
                        document.getElementById('modal-project-status').textContent = `Réseau actif : ${d.project_name || 'Chargé'} (${totalObj} éléments)`;
                    }
                    document.getElementById('stat-total').textContent = d.compteurs.conduites || 0;
                    const pName = d.project_name || 'Réseau Actif';
                    document.getElementById('mini-stats').innerHTML =
                        `<span style="color: #38bdf8; font-weight: 700;">Zone : ${pName}</span> | ` +
                        'Conduites: <b>' + (d.compteurs.conduites || 0) + '</b>' +
                        ' | Regards: <b>' + (d.compteurs.regards || 0) + '</b>';

                    window.conduitProperties = [];
                    // Conduites (lignes)
                    L.geoJSON(d.couches.conduites, {
                        pane: 'pipesPane',
                        style: { color: '#3498db', weight: 3 },
                        onEachFeature: (feature, layer) => {
                            const index = window.conduitProperties.length;
                            window.conduitProperties.push(feature.properties);
                            layer.bindPopup(conduitPopup(feature, index));

                            // Interception si le mode Profil en Long est actif pour faciliter le clic
                            layer.on('click', (e) => {
                                if (window.profilLongState && window.profilLongState.active) {
                                    L.DomEvent.stop(e);
                                    const cMap = window.carte || window.map;
                                    if (cMap) cMap.closePopup();
                                    if (layer.closePopup) layer.closePopup();
                                    const p = feature.properties || {};
                                    const targetNode = (window.profilLongState.step === 'amont')
                                        ? (p.ID_AMONT || p.id_amont || p.ID1 || p.Node1)
                                        : (p.ID_AVAL || p.id_aval || p.ID2 || p.Node2);
                                    if (targetNode && window.handleRegardClickForProfil) {
                                        window.handleRegardClickForProfil(targetNode, e.latlng);
                                    }
                                    return false;
                                }
                            });
                        }
                    }).addTo(couches.conduites);

                    // Styles typologiques pour les ouvrages spéciaux
                    function getOuvrageStyle(feature) {
                        const props = feature.properties || {};
                        const to = (props.TYPEOUVR || props.type_ouvrage || props.type_detaille || props.Type || '').toLowerCase();
                        if (to.includes('déversoir') || to.includes('deversoir') || to.includes('dvo')) {
                            return { radius: 7, color: '#0891b2', fillColor: '#06b6d4', fillOpacity: 0.9, weight: 2 };
                        } else if (to.includes('trop plein') || to.includes('trop-plein')) {
                            return { radius: 7, color: '#9333ea', fillColor: '#a855f7', fillOpacity: 0.9, weight: 2 };
                        } else if (to.includes('rétention') || to.includes('retention')) {
                            return { radius: 8, color: '#059669', fillColor: '#10b981', fillOpacity: 0.9, weight: 2 };
                        } else if (to.includes('régulation') || to.includes('regulation')) {
                            return { radius: 7, color: '#4f46e5', fillColor: '#6366f1', fillOpacity: 0.9, weight: 2 };
                        } else if (to.includes('réception') || to.includes('reception')) {
                            return { radius: 6, color: '#d97706', fillColor: '#f59e0b', fillOpacity: 0.9, weight: 2 };
                        }
                        return { radius: 7, color: '#0891b2', fillColor: '#06b6d4', fillOpacity: 0.9, weight: 2 };
                    }

                    // Popup enrichie pour les ouvrages spéciaux
                    function ouvragePopup(feature) {
                        const p = feature.properties || {};
                        const to = p.TYPEOUVR || p.type_ouvrage || p.libelle_type || 'Ouvrage spécial';
                        const seuilVal = p.H_de_Seuil !== undefined && p.H_de_Seuil !== null && p.H_de_Seuil !== '' && !isNaN(p.H_de_Seuil) ? parseFloat(p.H_de_Seuil).toFixed(2) : null;
                        const voie = p.NOMVOIE || p.nom_voie || p.ADRESSE || '--';
                        const zc = p.ZONECOLLE || p.zone_collecte || '--';
                        const code = p.Code || p.CODE || p.id || '--';
                        return `<div style="font-family: inherit; font-size: 12.5px; min-width: 215px; color: #1e293b;">
                            <div style="font-weight: 800; color: #0891b2; font-size: 13.5px; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; margin-bottom: 6px;">
                                <i class="fas fa-water me-1"></i> ${to}
                            </div>
                            <div style="margin-bottom: 3px;"><b>Adresse / Voie :</b> <span style="color: #0f172a; font-weight: 600;">${voie}</span></div>
                            <div style="margin-bottom: 3px;"><b>Zone collecte :</b> ${zc}</div>
                            ${seuilVal ? `<div style="margin-bottom: 3px;"><b>Seuil de crête ($H_s$) :</b> <span style="color: #d97706; font-weight: 800;">${seuilVal} m</span></div>` : ''}
                            <div style="font-size: 11px; color: #64748b; margin-top: 4px;">N° Ouvrage / Code : ${code}</div>
                        </div>`;
                    }

                    // Popup et infobulle enrichies pour les stations de relevage / pompage
                    function stationPopup(feature) {
                        const p = feature.properties || {};
                        const code = p.CODEPRR || p.Code || p.code || p.id || '--';
                        const nom = p.NOMPRR || p.Nom || p.nom || p.NOMVOIE || 'Station de relevage';
                        const etat = p.ETATFONCT || p.etat || 'En service';
                        const effluent = p.TYPE_EFFL || p.type_effluent || 'Eaux usées';
                        const mode = p.FONCTIOP6 || p.mode || 'Refoulement';
                        const pompe = p.CONSTPOMP || p.pompe || '';
                        const commande = p.ASSERV || p.commande || '';
                        const isMarche = String(etat).toLowerCase().includes('marche') || String(etat).toLowerCase().includes('service');
                        const isArret = String(etat).toLowerCase().includes('arrêt') || String(etat).toLowerCase().includes('arret');
                        const etatColor = isMarche ? '#16a34a' : (isArret ? '#ef4444' : '#f59e0b');

                        return `<div style="font-family: inherit; font-size: 12.5px; min-width: 220px; color: #1e293b;">
                            <div style="font-weight: 800; color: #ea580c; font-size: 13.5px; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; margin-bottom: 6px;">
                                <i class="fas fa-charging-station me-1"></i> Station : ${nom}
                            </div>
                            <div style="margin-bottom: 3px;"><b>Code station :</b> <span style="font-weight: 700; color: #0f172a;">${code}</span></div>
                            <div style="margin-bottom: 3px;"><b>État fonctionnement :</b> <span style="font-weight: 700; color: ${etatColor};">${etat}</span></div>
                            <div style="margin-bottom: 3px;"><b>Type effluent :</b> ${effluent}</div>
                            <div style="margin-bottom: 3px;"><b>Mode :</b> ${mode}</div>
                            ${pompe ? `<div style="margin-bottom: 3px;"><b>Pompe :</b> ${pompe}</div>` : ''}
                            ${commande ? `<div style="margin-bottom: 3px;"><b>Asservissement :</b> ${commande}</div>` : ''}
                        </div>`;
                    }

                    // Popup et infobulle enrichies pour la STEP
                    function stepPopup(feature) {
                        const p = feature.properties || {};
                        const code = p.CODE || p.code || p.id || 'STEP-01';
                        const nom = p.NOM || p.nom || "Station d'Épuration (STEP)";
                        return `<div style="font-family: inherit; font-size: 12.5px; min-width: 215px; color: #1e293b;">
                            <div style="font-weight: 800; color: #16a34a; font-size: 13.5px; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; margin-bottom: 6px;">
                                <i class="fas fa-recycle me-1"></i> ${nom}
                            </div>
                            <div style="margin-bottom: 3px;"><b>Référence SIG :</b> <span style="font-weight: 700; color: #0f172a;">${code}</span></div>
                            <div style="margin-bottom: 3px;"><b>Fonction :</b> Traitement et épuration des eaux usées</div>
                            <div style="margin-bottom: 3px;"><b>Statut opérationnel :</b> <span style="color: #16a34a; font-weight: 700;">En exploitation</span></div>
                        </div>`;
                    }

                    // Popup enrichie pour les rejets et exutoires
                    function rejetPopup(feature) {
                        const p = feature.properties || {};
                        const milieu = p.MILIEUREC || p.milieu_rec || 'Milieu naturel';
                        const nom = p.NOM || p.nom || p.NOM_VOIE || p.id || 'Exutoire';
                        const code = p.CODE || p.code || '--';
                        const tn = p.COTETN || p.cote_tampon || '--';
                        return `<div style="font-family: inherit; font-size: 12.5px; min-width: 215px; color: #1e293b;">
                            <div style="font-weight: 800; color: #ef4444; font-size: 13.5px; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; margin-bottom: 6px;">
                                <i class="fas fa-sign-out-alt me-1"></i> Exutoire / Rejet direct
                            </div>
                            <div style="margin-bottom: 3px;"><b>Milieu récepteur :</b> <span style="color: #0284c7; font-weight: 700;">${milieu}</span></div>
                            <div style="margin-bottom: 3px;"><b>Nom / Emplacement :</b> ${nom}</div>
                            <div style="margin-bottom: 3px;"><b>Cote TN :</b> ${tn} m</div>
                            <div style="font-size: 11px; color: #64748b; margin-top: 4px;">Code SIG : ${code}</div>
                        </div>`;
                    }

                    // Points (regards, rejets, stations, step, ouvrages)
                    const styles = {
                        regards: { radius: 4, color: '#2c3e50', fillColor: '#2c3e50', fillOpacity: 0.8 },
                        rejets: { radius: 7, color: '#ef4444', fillColor: '#ef4444', fillOpacity: 0.9, weight: 2 },
                        stations: { radius: 7, color: '#f97316', fillColor: '#f97316', fillOpacity: 0.85, weight: 2 },
                        step: { radius: 8, color: '#22c55e', fillColor: '#22c55e', fillOpacity: 0.9, weight: 2 },
                        ouvrages: { radius: 7, color: '#06b6d4', fillColor: '#06b6d4', fillOpacity: 0.9, weight: 2 }
                    };
                    window.regardProperties = [];
                    ['regards', 'rejets', 'stations', 'step', 'ouvrages'].forEach(type => {
                        if (!d.couches[type] || !d.couches[type].features) return;
                        L.geoJSON(d.couches[type], {
                            pane: 'nodesPane',
                            pointToLayer: (feature, latlng) => {
                                const st = (type === 'ouvrages') ? getOuvrageStyle(feature) : styles[type];
                                return L.circleMarker(latlng, Object.assign({ pane: 'nodesPane' }, st));
                            },
                            onEachFeature: (feature, layer) => {
                                if (type === 'stations') {
                                    const html = stationPopup(feature);
                                    layer.bindPopup(html);
                                    layer.bindTooltip(html, { sticky: true, opacity: 0.98 });
                                } else if (type === 'step') {
                                    const html = stepPopup(feature);
                                    layer.bindPopup(html);
                                    layer.bindTooltip(html, { sticky: true, opacity: 0.98 });
                                } else if (type === 'ouvrages') {
                                    const html = ouvragePopup(feature);
                                    layer.bindPopup(html);
                                    layer.bindTooltip(html, { sticky: true, opacity: 0.98 });
                                } else if (type === 'rejets') {
                                    const html = rejetPopup(feature);
                                    layer.bindPopup(html);
                                    layer.bindTooltip(html, { sticky: true, opacity: 0.98 });
                                } else if (type === 'regards') {
                                    const index = window.regardProperties.length;
                                    window.regardProperties.push(feature.properties);
                                    layer.bindPopup(regardPopup(feature, index));
                                }

                                // Interception pour le Profil en Long hydraulique (Phase 6.A)
                                // Si l'icône est active : tracé du profil sans ouvrir la fenêtre de modification
                                // Si l'icône n'est pas active : la fenêtre de modification s'ouvre normalement
                                layer.on('click', (e) => {
                                    if (window.profilLongState && window.profilLongState.active) {
                                        L.DomEvent.stop(e);
                                        const cMap = window.carte || window.map;
                                        if (cMap) cMap.closePopup();
                                        if (layer.closePopup) layer.closePopup();
                                        setTimeout(() => {
                                            if (cMap) cMap.closePopup();
                                            if (layer.closePopup) layer.closePopup();
                                        }, 10);

                                        const p = feature.properties || {};
                                        const code = p.Code || p.code || p.CODE || p.id || p.ID || p.Id || p.nom || p.NOM || p.Nom || p.CODEPRR || p.NUMERO || feature.id;
                                        if (code && window.handleRegardClickForProfil) {
                                            window.handleRegardClickForProfil(code, e.latlng);
                                        }
                                        return false;
                                    }
                                });

                                layer.on('popupopen', () => {
                                    if (window.profilLongState && window.profilLongState.active) {
                                        const cMap = window.carte || window.map;
                                        if (cMap) cMap.closePopup();
                                        if (layer.closePopup) layer.closePopup();
                                    }
                                });
                            }
                        }).addTo(couches[type]);
                    });

                    // Fetch incidents
                    fetch('/api/v1/terrain/incidents')
                        .then(r => r.json())
                        .then(incidents => {
                            if (Array.isArray(incidents)) {
                                incidents.forEach(inc => {
                                    const marker = L.circleMarker([inc.latitude, inc.longitude], {
                                        radius: 8,
                                        color: '#e74c3c',
                                        fillColor: '#c0392b',
                                        fillOpacity: 0.8,
                                        weight: 2
                                    });
                                    
                                    const popupContent = `<div style="font-family: Arial, sans-serif; font-size: 12px;">
                                        <b>🚨 Incident ${inc.id}</b><br>
                                        <b>Type:</b> ${inc.type_incident}<br>
                                        <b>Gravité:</b> ${inc.gravite}<br>
                                        <b>Statut:</b> ${inc.statut}<br>
                                        <b>Date:</b> ${new Date(inc.date_creation).toLocaleString()}<br>
                                        ${inc.description ? `<b>Desc:</b> ${inc.description}` : ''}
                                    </div>`;
                                    
                                    marker.bindPopup(popupContent);
                                    marker.addTo(couches.incidents);
                                });
                            }
                        })
                        .catch(err => console.error('Erreur chargement incidents:', err));

                    // Ajuster la vue avec cadrage optimal sur le réseau
                    const bounds = L.latLngBounds([]);
                    ['conduites', 'regards', 'rejets', 'stations', 'step', 'ouvrages'].forEach(type => {
                        if (couches[type]) {
                            couches[type].getLayers().forEach(layer => {
                                if (layer.getBounds) {
                                    bounds.extend(layer.getBounds());
                                } else if (layer.getLatLng) {
                                    bounds.extend(layer.getLatLng());
                                }
                            });
                        }
                    });
                    if (bounds.isValid()) {
                        carte.fitBounds(bounds, { padding: [40, 40], maxZoom: 17 });
                    }
                    
                    // 1. Charger immédiatement la sectorisation Voronoï
                    if (typeof chargerEtAfficherSousBassins === 'function') {
                        chargerEtAfficherSousBassins();
                    }

                    // 2. Partitionnement et tracé automatique immédiat des bassins versants (Exutoires)
                    if (typeof window.lancerPartitionnementBassins === 'function') {
                        window.lancerPartitionnementBassins(function(clusterData) {
                            // 3. Charger et restituer la dernière simulation une fois les bassins tracés
                            if (typeof chargerDerniereSimulation === 'function') {
                                chargerDerniereSimulation();
                            }
                            montrerChargement(false);
                        }, null, false, false);
                    } else {
                        if (typeof chargerDerniereSimulation === 'function') {
                            chargerDerniereSimulation();
                        }
                        montrerChargement(false);
                    }
                })
                .catch(e => {
                    console.error('Erreur:', e);
                    document.getElementById('mini-stats').textContent = 'Erreur chargement';
                    montrerChargement(false); // Masquer l'overlay même en cas d'erreur
                });
        }

        // Préchargement automatique des bassins versants sectorisés
        window.prechargerBassinsVersantsSilencieux = function() {
            if (typeof window.lancerPartitionnementBassins === 'function') {
                return window.lancerPartitionnementBassins(null, null, false, false);
            }
        };

/**
 * ================================================================================
 * BARRE D'OUTILS FLOTTANTE, DÉPLAÇABLE (DRAGGABLE) ET PLIABLE
 * ================================================================================
 */
function toggleToolbarCollapse(e) {
    if (e) e.stopPropagation();
    const toolbar = document.getElementById('main-edit-toolbar');
    const icon = document.getElementById('icon-collapse-toolbar');
    if (!toolbar) return;

    toolbar.classList.toggle('collapsed');
    const isCollapsed = toolbar.classList.contains('collapsed');

    if (icon) {
        icon.className = isCollapsed ? 'fas fa-chevron-right' : 'fas fa-chevron-left';
    }
    localStorage.setItem('drainpilot_toolbar_collapsed', isCollapsed ? '1' : '0');
}

function initDraggableToolbar() {
    const toolbar = document.getElementById('main-edit-toolbar');
    const handle = document.getElementById('toolbar-drag-handle');
    if (!toolbar || !handle) return;

    // Restaurer l'état réduit si mémorisé
    if (localStorage.getItem('drainpilot_toolbar_collapsed') === '1') {
        toolbar.classList.add('collapsed');
        const icon = document.getElementById('icon-collapse-toolbar');
        if (icon) icon.className = 'fas fa-chevron-right';
    }

    // Restaurer la position si mémorisée
    const savedPos = localStorage.getItem('drainpilot_toolbar_pos');
    if (savedPos) {
        try {
            const pos = JSON.parse(savedPos);
            if (pos.top && pos.left) {
                toolbar.style.top = `${pos.top}px`;
                toolbar.style.left = `${pos.left}px`;
                toolbar.style.right = 'auto';
            }
        } catch (err) {}
    }

    let isDragging = false;
    let startX = 0, startY = 0;
    let initialLeft = 0, initialTop = 0;

    handle.addEventListener('mousedown', (e) => {
        // Ne pas déclencher le drag si on clique sur le bouton collapse
        if (e.target.closest('#btn-collapse-toolbar')) return;

        isDragging = true;
        toolbar.classList.add('is-dragging');
        startX = e.clientX;
        startY = e.clientY;

        const rect = toolbar.getBoundingClientRect();
        initialLeft = rect.left;
        initialTop = rect.top;

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
        e.preventDefault();
    });

    function onMouseMove(e) {
        if (!isDragging) return;
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;

        let newLeft = initialLeft + dx;
        let newTop = initialTop + dy;

        // Limites écran
        const maxLeft = window.innerWidth - toolbar.offsetWidth - 10;
        const maxTop = window.innerHeight - toolbar.offsetHeight - 10;

        newLeft = Math.max(10, Math.min(newLeft, maxLeft));
        newTop = Math.max(55, Math.min(newTop, maxTop));

        toolbar.style.left = `${newLeft}px`;
        toolbar.style.top = `${newTop}px`;
        toolbar.style.right = 'auto';
    }

    function onMouseUp() {
        if (!isDragging) return;
        isDragging = false;
        toolbar.classList.remove('is-dragging');
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);

        // Mémoriser la position
        const rect = toolbar.getBoundingClientRect();
        localStorage.setItem('drainpilot_toolbar_pos', JSON.stringify({
            top: Math.round(rect.top),
            left: Math.round(rect.left)
        }));
    }
}

window.toggleToolbarCollapse = toggleToolbarCollapse;
window.initDraggableToolbar = initDraggableToolbar;

// Initialisation dès que le DOM est prêt
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDraggableToolbar);
} else {
    initDraggableToolbar();
}
