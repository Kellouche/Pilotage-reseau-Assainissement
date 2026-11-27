/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-27
 * Objet : Initialisation des calques réseau, styles graphiques et infobulles des ouvrages
 * ================================================================================
 */

function chargerDonneesInitiales() {
            // Promesse de fin de chargement : utilisée par le contexte
            // spatial pour attendre la bascule de snapshot avant de rendre
            // les résultats d'une simulation archivée.
            let _resolverChargement = null;
            window._promesseChargementReseau = new Promise(function(res) { _resolverChargement = res; });
            window._resolverChargementReseau = function() {
                if (_resolverChargement) { _resolverChargement(); _resolverChargement = null; }
            };

            // Montrer l'overlay de chargement bloquant : il reste affiché
            // jusqu'à la fin réelle de la sectorisation (failsafe 15 min).
            montrerChargement(true, 'Chargement du projet et du réseau…', 15 * 60 * 1000);

            // === NETTOYAGE : sauvegarder l'état du réseau courant et tout vider ===
            const reseauActuel = (window._rawNetworkData && window._rawNetworkData.project_name)
                ? window._rawNetworkData.project_name
                : (window._dernierResultatSimulation && window._dernierResultatSimulation.meta
                    ? (window._dernierResultatSimulation.meta.project_name || window._dernierResultatSimulation.meta.cluster_nom || window._dernierResultatSimulation.meta.cluster_id)
                    : null);
            if (reseauActuel) {
                window.nettoyerEtatReseau(reseauActuel);
            }

            const bSel = document.getElementById('bassin-select');
            if (bSel) bSel.innerHTML = '<option value="">-- Réseau complet ou choisir un bassin --</option>';
            const bInfo = document.getElementById('bassin-info');
            if (bInfo) bInfo.innerHTML = '';
            const simBSel = document.getElementById('sim-select-bassin');
            if (simBSel) simBSel.innerHTML = '<option value="" disabled selected>-- Sélectionnez un bassin versant sectorisé --</option>';
            const badgeSb = document.getElementById('badge-subcatchments-count');
            if (badgeSb) { badgeSb.innerHTML = '-- SB'; badgeSb.style.background = ''; }

            // Désactiver les boutons d'animation et d'analyse hydrologique au chargement d'un nouveau réseau
            _desactiverBoutonsHydro();

            var _urlLayers = '/api/v1/layers';
            if (window._snapshotEnAttente) {
                _urlLayers += (_urlLayers.indexOf('?') >= 0 ? '&' : '?')
                    + 'snapshot=' + encodeURIComponent(window._snapshotEnAttente);
            }
            const _tokenLayers = localStorage.getItem('swmm_access_token');
            fetch(_urlLayers, {
                credentials: 'include',
                headers: _tokenLayers ? { 'Authorization': 'Bearer ' + _tokenLayers } : {}
            })
                .then(r => {
                    if (!r.ok) {
                        // Snapshot archivé introuvable : ne jamais retomber
                        // silencieusement sur le réseau courant (INV-1).
                        throw new Error('Snapshot réseau indisponible (HTTP ' + r.status + ')');
                    }
                    return r.json();
                })
                .then(d => {
                    console.log('Données:', d.compteurs);
                    window._rawNetworkData = d;

                    // Recadrage instantané : dès réception de la bbox calculée par l'API, zoomer
                    // immédiatement sans attendre la boucle de création DOM des milliers d'objets.
                    if (d.bbox && Array.isArray(d.bbox) && d.bbox.length === 2) {
                        try {
                            carte.fitBounds(d.bbox, { padding: [40, 40], maxZoom: 17 });
                            localStorage.setItem('swmm_last_bbox', JSON.stringify(d.bbox));
                        } catch (_) {}
                    }
                    // Contexte spatial : le snapshot réellement servi fait
                    // foi pour toutes les vérifications INV-2 en aval.
                    if (typeof window._majContexteDepuisLayers === 'function') {
                        window._majContexteDepuisLayers(d);
                    }
                    // Couches SIG satellites : réinitialiser le contexte projet
                    // (sinon les couches de l'ancien projet restent visibles et
                    // le projectId caché interroge le mauvais projet).
                    if (typeof window.auxReinitialiserProjet === 'function') {
                        window.auxReinitialiserProjet();
                    }
                    if (d.project_name) {
                        const lbl = document.getElementById('topbar-project-label');
                        if (lbl) lbl.textContent = d.project_name;
                    }

                    // Restaurer l'état du bureau (positions panneaux, toolbar, légende) pour ce réseau
                    if (d.project_name) {
                        window.restaurerEtatBureau(d.project_name);
                    }

                    // Vider les couches précédentes
                    Object.values(couches).forEach(l => l.clearLayers());

                    const totalObj = d.compteurs ? Object.values(d.compteurs).reduce((a, b) => a + b, 0) : 0;
                    if (d.is_empty || totalObj === 0) {
                        montrerChargement(false);
                        if (window._resolverChargementReseau) window._resolverChargementReseau();
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
                        `<span style="color: #38bdf8; font-weight: 700;">Réseau : ${pName}</span> | ` +
                        'Conduites: <b>' + (d.compteurs.conduites || 0) + '</b>' +
                        ' | Regards: <b>' + (d.compteurs.regards || 0) + '</b>';

                    window.conduitProperties = [];
                    // Conduites (lignes) : gravitaires en bleu plein,
                    // refoulements/pompage en rouge pointillé (réseau sous pression)
                    const _estRefoulement = (props) => {
                        const f = String((props && (props.FONCTIONMT || props.fonctionmt || props.FonctionMT || props.FONCTION)) || '').toLowerCase();
                        return f.includes('refoul') || f.includes('pompage') || f.includes('refoulement');
                    };
                    L.geoJSON(d.couches.conduites, {
                        pane: 'pipesPane',
                        style: (feature) => {
                            if (_estRefoulement(feature.properties)) {
                                return { color: '#dc2626', weight: 4, dashArray: '7 4', opacity: 0.95 };
                            }
                            return { color: '#38bdf8', weight: 2.5 };
                        },
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
                            ${seuilVal ? `<div style="margin-bottom: 3px;"><b>Seuil de crête (H&#8347;) :</b> <span style="color: #d97706; font-weight: 800;">${seuilVal} m</span></div>` : ''}
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
                        regards: { radius: 2.5, color: '#2c3e50', fillColor: '#2c3e50', fillOpacity: 0.8 },
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
                                    // Interception si le mode Sélection Regard DWF est actif
                                    if (window._dwfPickModeActive) {
                                        L.DomEvent.stop(e);
                                        const cMap = window.carte || window.map;
                                        if (cMap) cMap.closePopup();
                                        if (layer.closePopup) layer.closePopup();
                                        const p = feature.properties || {};
                                        const code = p.Code || p.code || p.CODE || p.id || p.ID || p.Id || p.nom || p.NOM || p.Nom || p.CODEPRR || p.NUMERO || feature.id;
                                        if (code && typeof window.dwfAppliquerNoeudSelectionne === 'function') {
                                            window.dwfAppliquerNoeudSelectionne(code, e.latlng);
                                        }
                                        return false;
                                    }
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
                                    if (window._dwfPickModeActive || (window.profilLongState && window.profilLongState.active)) {
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
                        try {
                            localStorage.setItem('swmm_last_bbox', JSON.stringify([
                                [bounds.getSouth(), bounds.getWest()],
                                [bounds.getNorth(), bounds.getEast()]
                            ]));
                        } catch (_) {}
                    }
                    
                    // 1. Partitionnement et tracé automatique immédiat des bassins versants (Exutoires)
                    if (window.majMessageChargement) {
                        window.majMessageChargement('Analyse topologique et sectorisation des bassins versants…');
                    }
                    if (typeof window.lancerPartitionnementBassins === 'function') {
                        window.lancerPartitionnementBassins(function(clusterData) {
                            // Charger le maillage des sous-bassins Voronoï en arrière-plan sans bloquer
                            if (typeof chargerEtAfficherSousBassins === 'function') {
                                chargerEtAfficherSousBassins();
                            }
                            if (window._chargementSnapshotEnCours) {
                                // En cours de bascule de snapshot archivé : NE PAS écraser la simulation
                                // demandée par l'ancienne dernière simulation ni réinitialiser le bassin
                                montrerChargement(false);
                                if (window._resolverChargementReseau) window._resolverChargementReseau();
                                return;
                            }
                            // Rouvrir sur le dernier bassin consulté (par projet) s'il existe
                            let aRestaureBassin = false;
                            if (typeof window.restaurerDernierBassin === 'function') {
                                try {
                                    aRestaureBassin = !!window.restaurerDernierBassin();
                                } catch (_) {}
                            }

                            // 3. Charger et restituer la dernière simulation SEULEMENT si aucun bassin spécifique n'a été restauré
                            if (!aRestaureBassin) {
                                if (window.majMessageChargement) {
                                    window.majMessageChargement('Restauration de la dernière simulation…');
                                }
                                if (typeof chargerDerniereSimulation === 'function') {
                                    chargerDerniereSimulation();
                                }
                            }
                            // Met à jour le badge « N BV » avec le nombre
                            // réel de bassins sectorisés (fini le « -- »).
                            if (typeof window.mettreAJourIndicateurBassin === 'function') {
                                window.mettreAJourIndicateurBassin(null, {});
                            }
                            montrerChargement(false);
                            if (window._resolverChargementReseau) window._resolverChargementReseau();
                            // Vérifier si une simulation est restaurée et réactiver les boutons si nécessaire
                            if (typeof _desactiverBoutonsHydro === 'function') {
                                setTimeout(() => _desactiverBoutonsHydro(), 500);
                            }
                        }, null, false, false);
                    } else {
                        if (!window._chargementSnapshotEnCours && typeof chargerDerniereSimulation === 'function') {
                            chargerDerniereSimulation();
                        }
                        montrerChargement(false);
                        if (window._resolverChargementReseau) window._resolverChargementReseau();
                        // Vérifier si une simulation est restaurée et réactiver les boutons si nécessaire
                        if (typeof _desactiverBoutonsHydro === 'function') {
                            setTimeout(() => _desactiverBoutonsHydro(), 500);
                        }
                    }
                })
                .catch(e => {
                    console.error('Erreur:', e);
                    document.getElementById('mini-stats').textContent = 'Erreur chargement';
                    montrerChargement(false); // Masquer l'overlay même en cas d'erreur
                    if (window._resolverChargementReseau) window._resolverChargementReseau();
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
        icon.className = isCollapsed ? 'fas fa-chevron-down' : 'fas fa-chevron-up';
    }
    localStorage.setItem('drainpilot_toolbar_collapsed', isCollapsed ? '1' : '0');
}

/**
 * Maintient la toolbar dans les limites visibles de son conteneur (#carte-workspace)
 * et du viewport pour éviter qu'elle ne devienne invisible lors du redimensionnement.
 */
window._bornerToolbarViewport = function(toolbar) {
    if (!toolbar) return;
};

/**
 * Position « automatique » de la toolbar :
 * Inspiré de la légende Leaflet, la toolbar est ancrée dans le conteneur
 * Leaflet natif (.leaflet-top.leaflet-left). Aucun style inline de position
 * n'est requis : Leaflet et le flexbox CSS gèrent le calage naturellement.
 */
window._positionAutoToolbar = function(toolbar) {
    if (!toolbar) return;
    delete toolbar.dataset.positionManuelle;
    delete toolbar.dataset.fx;
    delete toolbar.dataset.fy;
    toolbar.style.position = '';
    toolbar.style.left = '';
    toolbar.style.top = '';
    toolbar.style.right = '';
};

/** Vrai si l'utilisateur a déplacé la toolbar manuellement. */
window._toolbarPositionPersonnalisee = function(toolbar) {
    return false;
};

/**
 * Position manuelle exprimée en FRACTIONS du conteneur #map :
 * le décalage est relatif et suit le redimensionnement de la carte.
 */
window._positionRelativeToolbar = function(toolbar) {
    window._positionAutoToolbar(toolbar);
};

function initDraggableToolbar() {
    const toolbar = document.getElementById('main-edit-toolbar');
    if (!toolbar) return;

    // Purge de toute ancienne position manuelle pour garantir l'ancrage Leaflet avec la légende
    localStorage.removeItem('drainpilot_toolbar_pos');
    window._positionAutoToolbar(toolbar);

    // Restaurer l'état réduit si mémorisé
    if (localStorage.getItem('drainpilot_toolbar_collapsed') === '1') {
        toolbar.classList.add('collapsed');
        const icon = document.getElementById('icon-collapse-toolbar');
        if (icon) icon.className = 'fas fa-chevron-down';
    } else {
        const icon = document.getElementById('icon-collapse-toolbar');
        if (icon) icon.className = 'fas fa-chevron-up';
    }
}

window.toggleToolbarCollapse = toggleToolbarCollapse;
window.initDraggableToolbar = initDraggableToolbar;
