/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Utilitaires de formatage monétaire DZD, cockpit view, overlays et menus navbar
 * ================================================================================
 */

// ==============================================================================
        // FONCTIONS UTILITAIRES DE FORMATAGE HYDRAULIQUE & COMPTABLE (NORMES ONA / DRE)
        // ==============================================================================
        window.formaterNombre = function(val, decimales = 3) {
            if (val === null || val === undefined || isNaN(Number(val))) {
                return (0).toFixed(decimales).replace('.', ',');
            }
            const num = Number(val);
            return num.toLocaleString('fr-FR', {
                minimumFractionDigits: decimales,
                maximumFractionDigits: decimales
            });
        };

        window.formaterCoutDZD = function(val, avecDecimales = true) {
            if (val === null || val === undefined || isNaN(Number(val))) {
                return avecDecimales ? '0,00 DA' : '0 DA';
            }
            const num = Number(val);
            const s = num.toLocaleString('fr-FR', {
                minimumFractionDigits: avecDecimales ? 2 : 0,
                maximumFractionDigits: avecDecimales ? 2 : 0
            });
            return `${s} DA`;
        };

        // Montant numérique sans unité : l'unité doit figurer dans l'en-tête de colonne
        window.formaterMontant = function(val, decimales = 2) {
            const num = Number(val || 0);
            return num.toLocaleString('fr-FR', {
                minimumFractionDigits: decimales,
                maximumFractionDigits: decimales
            });
        };

        let carte = L.map('map', {
            maxZoom: 22,
            zoomSnap: 0.5,
            zoomDelta: 0.5
        }).setView([36.15, 1.33], 13);
        window.carte = carte;
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap',
            maxZoom: 22,
            maxNativeZoom: 19
        }).addTo(carte);

        // Hiérarchie cartographique des Panes Leaflet (z-index)
        // 1. Sous-bassins versants Voronoï (fond géométrique)
        if (!carte.getPane('voronoiPane')) {
            const p = carte.createPane('voronoiPane');
            p.style.zIndex = 410;
        }
        // 2. Bassins Versants (Prend le dessus sur les Voronoï)
        if (!carte.getPane('bassinsPane')) {
            const p = carte.createPane('bassinsPane');
            p.style.zIndex = 430;
        }
        // 3. Réseau physique brut : Conduites
        if (!carte.getPane('pipesPane')) {
            const p = carte.createPane('pipesPane');
            p.style.zIndex = 450;
        }
        // 4. Réseau physique brut : Regards et Ouvrages
        if (!carte.getPane('nodesPane')) {
            const p = carte.createPane('nodesPane');
            p.style.zIndex = 470;
        }
        // 5. Résultats SWMM 5.2 : Conduites simulées
        if (!carte.getPane('swmmResultsPane')) {
            const p = carte.createPane('swmmResultsPane');
            p.style.zIndex = 620;
        }
        // 6. Résultats SWMM 5.2 : Regards simulés (surcharges orange & débordements rouge)
        if (!carte.getPane('swmmNodesPane')) {
            const p = carte.createPane('swmmNodesPane');
            p.style.zIndex = 650;
        }
        // 7. Infobulles et survol interactif au 1er plan absolu
        if (carte.getPane('tooltipPane')) {
            carte.getPane('tooltipPane').style.zIndex = 1000;
        }
        if (carte.getPane('popupPane')) {
            carte.getPane('popupPane').style.zIndex = 1100;
        }

        let couches = {
            conduites: L.layerGroup().addTo(carte),
            regards: L.layerGroup().addTo(carte),
            rejets: L.layerGroup().addTo(carte),
            stations: L.layerGroup().addTo(carte),
            step: L.layerGroup().addTo(carte),
            ouvrages: L.layerGroup().addTo(carte),
            bassins: L.layerGroup().addTo(carte),
            orphelins: L.layerGroup(),
            incidents: L.layerGroup().addTo(carte),
            subcatchments: L.layerGroup().addTo(carte),
            res_conduites: L.featureGroup().addTo(carte),
            res_regards: L.featureGroup().addTo(carte),
            sens_ecoulement: L.layerGroup()
        };
        window.couches = couches;

        // Fonction certifiée de calcul du rayon des ouvrages spéciaux et orphelins proportionnel au niveau de zoom
        function calculerRayonOuvrageSpecial(zoom) {
            if (zoom <= 13) return 4.5;
            if (zoom <= 15) return 6.0;
            if (zoom <= 17) return 8.0;
            if (zoom <= 19) return 10.0;
            return 12.0;
        }
        window.calculerRayonOuvrageSpecial = calculerRayonOuvrageSpecial;

        // Écouteur de zoom pour ajuster dynamiquement la taille des ouvrages orphelins et connectés
        carte.on('zoomend', function() {
            const z = carte.getZoom();
            const r = calculerRayonOuvrageSpecial(z);
            carte.eachLayer(function(l) {
                if (l.options && l.options.className === 'orphan-zoom-marker' && typeof l.setRadius === 'function') {
                    l.setRadius(r);
                }
            });
        });

        // ============================================================
        // GESTIONNAIRE STRICT D'INFOBULLE UNIQUE (ANTI-CHEVAUCHEMENT LEAFLET SANS CASSE DU DOM)
        // ============================================================
        let _activeGlobalTooltip = null;

        carte.on('tooltipopen', function(e) {
            // S'il y a déjà une infobulle ouverte différente, on la ferme proprement via l'API Leaflet
            if (_activeGlobalTooltip && _activeGlobalTooltip !== e.tooltip) {
                try {
                    if (_activeGlobalTooltip._source && typeof _activeGlobalTooltip._source.closeTooltip === 'function') {
                        _activeGlobalTooltip._source.closeTooltip();
                    } else if (typeof _activeGlobalTooltip.close === 'function') {
                        _activeGlobalTooltip.close();
                    }
                } catch(_) {}
            }
            _activeGlobalTooltip = e.tooltip;

            // Garantir que le tooltip actif est bien visible sans style display parasite
            if (e.tooltip && e.tooltip._container) {
                e.tooltip._container.style.display = '';
            }
        });

        carte.on('tooltipclose', function(e) {
            if (_activeGlobalTooltip === e.tooltip) {
                _activeGlobalTooltip = null;
            }
        });

        // Fermer proprement toutes les infobulles lors des déplacements cartographiques ou clics via l'API Leaflet
        carte.on('zoomstart movestart dragstart click', function() {
            _activeGlobalTooltip = null;
            carte.eachLayer(function(l) {
                if (typeof l.closeTooltip === 'function') {
                    try { l.closeTooltip(); } catch(e) {}
                }
            });
        });

        function basculerCoucheBassins(checked) {
            if (checked) couches.bassins.addTo(carte);
            else carte.removeLayer(couches.bassins);
        }

        function basculerCoucheOrphelins(checked) {
            if (checked) couches.orphelins.addTo(carte);
            else carte.removeLayer(couches.orphelins);
        }

        // Couche pour les clusters détectés
        let clusterCouche = L.layerGroup().addTo(carte);
        
        // Référence globale vers le layer Leaflet des clusters (pour synchro dropdown)
        let _activeClusterLayer = null;
        let _selectedClusterId = null;
        // Map clusterId -> bounds du bassin
        let _bassinBounds = {};

        ['conduites', 'regards', 'rejets', 'stations', 'step', 'ouvrages', 'bassins', 'incidents'].forEach(type => {
            const el = document.getElementById('f-' + type);
            if (el) {
                el.onchange = (e) => {
                    if (e.target.checked) couches[type].addTo(carte);
                    else carte.removeLayer(couches[type]);
                };
            }
        });

        // ==========================================
        // LÉGENDE INTERACTIVE CARTE SWMM 5.2 (POINT 1)
        // ==========================================
        let simulationLegendControl = L.control({ position: 'bottomright' });

        simulationLegendControl.onAdd = function(map) {
            const div = L.DomUtil.create('div', 'sim-legend-container');
            div.id = 'sim-floating-legend';
            div.style.display = 'none'; // Masqué par défaut : n'apparaît que suite à une simulation
            div.innerHTML = `
                <div style="background: rgba(15, 23, 42, 0.92); backdrop-filter: blur(8px); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 10px; padding: 10px 14px; color: #f8fafc; font-family: inherit; font-size: 11px; width: 235px; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
                    <div style="display: flex; align-items: center; justify-content: space-between; font-weight: 800; font-size: 11.5px; color: #38bdf8; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 5px; margin-bottom: 8px;">
                        <span><i class="fas fa-layer-group me-1"></i> Légende SWMM 5.2</span>
                        <button onclick="basculerAffichageLegende(event)" id="btn-toggle-legend" style="background: transparent; border: none; color: #94a3b8; cursor: pointer; font-size: 12px; font-weight: bold; padding: 0 4px;" title="Réduire / Agrandir">—</button>
                    </div>
                    <div id="sim-legend-body">
                        <!-- Taux de charge conduites -->
                        <div style="font-weight: 700; color: #cbd5e1; margin-bottom: 4px;">Charge Conduites (Q / Qmax) :</div>
                        <div style="display: flex; align-items: center; gap: 7px; margin-bottom: 2px;"><span style="display:inline-block; width:14px; height:4px; background:#10b981; border-radius:2px;"></span> &lt; 50% (Sain / Libre)</div>
                        <div style="display: flex; align-items: center; gap: 7px; margin-bottom: 2px;"><span style="display:inline-block; width:14px; height:4px; background:#facc15; border-radius:2px;"></span> 50 - 80% (Modéré)</div>
                        <div style="display: flex; align-items: center; gap: 7px; margin-bottom: 2px;"><span style="display:inline-block; width:14px; height:4px; background:#f97316; border-radius:2px;"></span> 80 - 100% (Critique)</div>
                        <div style="display: flex; align-items: center; gap: 7px; margin-bottom: 8px;"><span style="display:inline-block; width:14px; height:4px; background:#ef4444; border-radius:2px;"></span> &gt; 100% (Sous pression)</div>

                        <!-- Comportement des Regards -->
                        <div style="font-weight: 700; color: #cbd5e1; margin-bottom: 4px;">Regards de Visite :</div>
                        <div style="display: flex; align-items: center; gap: 7px; margin-bottom: 3px;"><span style="display:inline-block; width:11px; height:11px; background:#f97316; border-radius:50%; border:2px solid #ffffff;"></span> Surcharge (dans cheminée)</div>
                        <div style="display: flex; align-items: center; gap: 7px; margin-bottom: 8px;"><span style="display:inline-block; width:11px; height:11px; background:#ef4444; border-radius:50%; border:2px solid #ffffff;"></span> Débordement (au sol)</div>

                        <!-- Ouvrages Spéciaux & Exutoires -->
                        <div style="font-weight: 700; color: #cbd5e1; margin-bottom: 4px;">Ouvrages &amp; Exutoires :</div>
                        <div style="display: flex; align-items: center; gap: 7px; margin-bottom: 2px;"><span style="display:inline-block; width:10px; height:10px; background:#06b6d4; border-radius:50%; border:1px solid #ffffff;"></span> Déversoir d'orage (DVO)</div>
                        <div style="display: flex; align-items: center; gap: 7px; margin-bottom: 2px;"><span style="display:inline-block; width:10px; height:10px; background:#a855f7; border-radius:50%; border:1px solid #ffffff;"></span> Trop-plein de réseau</div>
                        <div style="display: flex; align-items: center; gap: 7px; margin-bottom: 2px;"><span style="display:inline-block; width:10px; height:10px; background:#10b981; border-radius:50%; border:1px solid #ffffff;"></span> Bassin de rétention</div>
                        <div style="display: flex; align-items: center; gap: 7px; margin-bottom: 8px;"><span style="display:inline-block; width:10px; height:10px; background:#ef4444; border-radius:50%; border:1px solid #ffffff;"></span> Rejet direct (Oued)</div>

                        <!-- Hydrologie & Sens d'écoulement -->
                        <div style="font-weight: 700; color: #cbd5e1; margin-bottom: 4px;">Hydrologie &amp; Écoulement :</div>
                        <div style="display: flex; align-items: center; gap: 7px; margin-bottom: 2px;"><span style="display:inline-block; width:14px; height:10px; background:rgba(16,185,129,0.25); border:1px dashed #059669; border-radius:2px;"></span> Sous-Bassin Voronoï (ha)</div>
                        <div style="display: flex; align-items: center; gap: 7px;"><span style="color:#38bdf8; font-weight:bold; font-size:12px;">➤</span> Sens d'écoulement (Amont ➔ Aval)</div>
                    </div>
                </div>
            `;
            return div;
        };

        simulationLegendControl.addTo(carte);

        window.basculerAffichageLegende = function(e) {
            if (e) e.stopPropagation();
            const body = document.getElementById('sim-legend-body');
            const btn = document.getElementById('btn-toggle-legend');
            if (body && btn) {
                if (body.style.display === 'none') {
                    body.style.display = 'block';
                    btn.innerText = '—';
                } else {
                    body.style.display = 'none';
                    btn.innerText = '+';
                }
            }
        };

        setTimeout(() => {
            const legEl = document.getElementById('sim-floating-legend');
            if (legEl) L.DomEvent.disableClickPropagation(legEl);
        }, 500);

        // Fonction pour afficher/masquer l'overlay de chargement avec timeout de sécurité
        function montrerChargement(afficher, message = 'Chargement des données...') {
            const overlay = document.getElementById('loading-overlay');
            if (!overlay) return;
            const txtEl = document.getElementById('loading-overlay-text');
            if (txtEl && message) txtEl.textContent = message;
            if (afficher) {
                overlay.style.display = 'flex';
                if (window._loadingSafetyTimer) clearTimeout(window._loadingSafetyTimer);
                window._loadingSafetyTimer = setTimeout(() => {
                    if (overlay && overlay.style.display === 'flex') {
                        overlay.style.display = 'none';
                        console.warn('Timeout de sécurité : overlay de chargement masqué automatiquement.');
                    }
                }, 25000);
            } else {
                if (window._loadingSafetyTimer) clearTimeout(window._loadingSafetyTimer);
                overlay.style.display = 'none';
                if (window.carte) {
                    setTimeout(() => { try { window.carte.invalidateSize(); } catch(e) {} }, 50);
                }
            }
        }

        // Restauration instantanée depuis le cache mémoire du navigateur (bfcache) sans recharger
        window.addEventListener('pageshow', (event) => {
            if (event.persisted) {
                montrerChargement(false);
            }
        });

        // ============================================================
        // BASCULE DE VUES DU COCKPIT (CARTO <-> QUALITÉ SANS RECHARGEMENT)
        // ============================================================
        window.basculerVueCockpit = function(vue) {
            const tabCarto = document.getElementById('tab-nav-carto');
            const tabQualite = document.getElementById('tab-nav-qualite');
            const workspace = document.getElementById('app-workspace');
            const containerQ = document.getElementById('container-qualite-cockpit');
            const iframeQ = document.getElementById('iframe-qualite');

            if (vue === 'qualite') {
                if (tabCarto) {
                    tabCarto.style.color = '#cbd5e1';
                    tabCarto.style.background = 'transparent';
                    tabCarto.style.borderColor = 'transparent';
                }
                if (tabQualite) {
                    tabQualite.style.color = '#38bdf8';
                    tabQualite.style.background = 'rgba(56, 189, 248, 0.15)';
                    tabQualite.style.borderColor = 'rgba(56, 189, 248, 0.3)';
                }
                if (workspace) workspace.style.display = 'none';
                if (containerQ) {
                    containerQ.style.display = 'block';
                    if (iframeQ && (!iframeQ.src || iframeQ.src === 'about:blank' || !iframeQ.src.includes('/qualite'))) {
                        iframeQ.src = '/qualite';
                    }
                }
                if (window.history && window.history.pushState) {
                    window.history.pushState({ tab: 'qualite' }, '', '/map?tab=qualite');
                }
            } else {
                if (tabCarto) {
                    tabCarto.style.color = '#38bdf8';
                    tabCarto.style.background = 'rgba(56, 189, 248, 0.15)';
                    tabCarto.style.borderColor = 'rgba(56, 189, 248, 0.3)';
                }
                if (tabQualite) {
                    tabQualite.style.color = '#cbd5e1';
                    tabQualite.style.background = 'transparent';
                    tabQualite.style.borderColor = 'transparent';
                }
                if (containerQ) containerQ.style.display = 'none';
                if (workspace) {
                    workspace.style.display = 'flex';
                    if (typeof carte !== 'undefined' && carte) {
                        setTimeout(() => carte.invalidateSize(), 60);
                    }
                }
                if (window.history && window.history.pushState) {
                    window.history.pushState({ tab: 'carto' }, '', '/map');
                }
            }
        };

        window.addEventListener('popstate', (e) => {
            const params = new URLSearchParams(window.location.search);
            if (params.get('tab') === 'qualite') {
                basculerVueCockpit('qualite');
            } else {
                basculerVueCockpit('carto');
            }
        });

        if (window.location.search.includes('tab=qualite')) {
            setTimeout(() => basculerVueCockpit('qualite'), 100);
        }

        // Variables pour l'éditeur manuel
        let editorState = {
            active: false,
            mode: null,
            points: [],
            markers: [],
            tempPolyline: null,
            tempPolygon: null,
            selectedConduits: new Set(),
            foundOutfall: null
        };

        // Activer/Désactiver le mode édition
        document.getElementById('btn-create-bassin').onclick = function() {
            if (editorState.active && editorState.mode === 'create') {
                desactiverModeEdition();
            } else {
                activerModeEdition('create');
            }
        };

// ==========================================
// PANNEAU D'INGÉNIERIE PLIABLE (style tiroir)
// ==========================================
window.basculeSidebarIngenierie = function() {
    const ws = document.getElementById('app-workspace');
    if (!ws) return;
    const replie = ws.classList.toggle('sidebar-collapsed');
    try { localStorage.setItem('drainpilot_sidebar_plie', replie ? '1' : '0'); } catch (e) {}
    // Laisser la transition CSS se terminer avant de recalculer la carte
    setTimeout(() => {
        try { if (window.carte && window.carte.invalidateSize) window.carte.invalidateSize(true); } catch (e) {}
        try { document.dispatchEvent(new Event('resize')); } catch (e) {}
    }, 300);
};

function _initialiserSidebarIngenierie() {
    try {
        if (localStorage.getItem('drainpilot_sidebar_plie') === '1') {
            const ws = document.getElementById('app-workspace');
            if (ws) {
                ws.classList.add('sidebar-collapsed');
                // La carte doit se recalculer sur la largeur libérée
                setTimeout(() => {
                    try { if (window.carte && window.carte.invalidateSize) window.carte.invalidateSize(true); } catch (e) {}
                }, 350);
            }
        }
    } catch (e) {}
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initialiserSidebarIngenierie);
} else {
    _initialiserSidebarIngenierie();
}
