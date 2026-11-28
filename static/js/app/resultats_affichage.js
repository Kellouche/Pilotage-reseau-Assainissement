/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Affichage des résultats hydrauliques SWMM, coloration des conduites et surcharges
 * ================================================================================
 */

// ==========================================
// INFOBULLES RÉSULTATS SWMM — BASCULE PAR MENU CONTEXTUEL
// Par défaut les infobulles de survol sont masquées. Un clic droit
// n'importe où sur la carte en mode simulation affiche un menu
// contextuel avec la case à cocher « Infobulles » pour les réactiver.
// ==========================================
window._simInfobullesActives = false;
window._simTipLayers = [];
window._simCtxActif = false;

// Enregistre une infobulle de résultat : elle n'est liée à la couche
// (et donc visible au survol) que si la bascule est cochée.
window._enregistrerInfobulleSim = function (layer, html, opts) {
    if (!layer) return;
    window._simTipLayers.push({ layer: layer, html: html, opts: opts || {} });
    window._appliquerInfobullesSim();
};

window._appliquerInfobullesSim = function () {
    const actif = !!window._simInfobullesActives;
    (window._simTipLayers || []).forEach(function (entry) {
        try {
            if (actif) {
                entry.layer.bindTooltip(entry.html, entry.opts);
            } else if (typeof entry.layer.unbindTooltip === 'function') {
                entry.layer.unbindTooltip();
            }
        } catch (_) {}
    });
};

window._basculerInfobullesSim = function () {
    window._simInfobullesActives = !window._simInfobullesActives;
    window._appliquerInfobullesSim();
    return window._simInfobullesActives;
};

// Construit l'élément « case à cocher Infobulles » réutilisable dans
// n'importe quel menu contextuel (menu simulation ou menu anomalies).
window._ajouterItemInfobullesSim = function (menu) {
    const item = document.createElement('button');
    item.type = 'button';
    item.style.cssText = 'display:flex;align-items:center;gap:8px;width:100%;text-align:left;'
        + 'background:none;border:none;color:#e2e8f0;padding:7px 10px;border-radius:6px;'
        + 'cursor:pointer;font-size:0.8rem;';
    const _rendu = function () {
        item.innerHTML = '<span style="width:14px;text-align:center;flex:none;">'
            + (window._simInfobullesActives ? '☑' : '☐') + '</span> Infobulles au survol';
    };
    _rendu();
    item.onmouseenter = function () { item.style.background = 'rgba(56,189,248,0.15)'; };
    item.onmouseleave = function () { item.style.background = 'none'; };
    item.onclick = function (ev) {
        ev.stopPropagation();
        window._basculerInfobullesSim();
        _rendu();
        // Fermer le menu après bascule : l'état (☑/☐) est relu à la
        // prochaine ouverture — évite un menu qui reste affiché.
        if (typeof _masquerMenuInfobullesSim === 'function') _masquerMenuInfobullesSim();
        if (typeof _menuAnomaliesProfilHide === 'function') _menuAnomaliesProfilHide();
    };
    menu.appendChild(item);
    return item;
};

// Menu contextuel « Infobulles » — affiché au clic droit sur la carte
// lorsque des résultats de simulation sont affichés (hors menu anomalies).
function _afficherMenuInfobullesSim(domEvent) {
    _masquerMenuInfobullesSim();
    if (!domEvent) return;
    const x = domEvent.clientX, y = domEvent.clientY;

    const menu = document.createElement('div');
    menu.className = 'menu-infobulles-sim';
    menu.style.cssText = 'position:fixed;z-index:9999;background:rgba(15,23,42,0.97);'
        + 'border:1px solid rgba(56,189,248,0.45);border-radius:10px;padding:5px;'
        + 'min-width:190px;box-shadow:0 10px 30px rgba(0,0,0,0.55);'
        + 'font-family:"Plus Jakarta Sans",sans-serif;';

    window._ajouterItemInfobullesSim(menu);

    menu.style.left = Math.max(4, Math.min(x + 6, window.innerWidth - 200)) + 'px';
    menu.style.top = Math.max(4, Math.min(y + 6, window.innerHeight - 90)) + 'px';
    document.body.appendChild(menu);
    window._menuInfobullesSim = menu;

    setTimeout(function () {
        const _hide = function (ev) {
            if (menu.contains(ev.target)) return;
            _masquerMenuInfobullesSim();
        };
        menu._hideHandler = _hide;
        document.addEventListener('click', _hide, true);
        const _esc = function (ev) { if (ev.key === 'Escape') _masquerMenuInfobullesSim(); };
        document.addEventListener('keydown', _esc);
        menu._escHandler = _esc;
    }, 0);
}

function _masquerMenuInfobullesSim() {
    if (window._menuInfobullesSim) {
        if (window._menuInfobullesSim._escHandler) {
            document.removeEventListener('keydown', window._menuInfobullesSim._escHandler);
        }
        if (window._menuInfobullesSim._hideHandler) {
            document.removeEventListener('click', window._menuInfobullesSim._hideHandler, true);
        }
        window._menuInfobullesSim.remove();
        window._menuInfobullesSim = null;
    }
}

// ==========================================
// LOT P1.5.3 / P1.5.4 — LÉGENDE INTERACTIVE DWF
// ==========================================
window.actualiserLegendeDwf = function(data) {
    const _dwfLeg = document.getElementById('sim-legend-dwf-info');
    const _dwfMarkerRow = document.getElementById('sim-legend-dwf-marker-row');
    if (!_dwfLeg && !_dwfMarkerRow) return;

    if (!data) {
        if (_dwfLeg) { _dwfLeg.style.display = 'none'; _dwfLeg.innerHTML = ''; }
        if (_dwfMarkerRow) { _dwfMarkerRow.style.display = 'none'; }
        return;
    }

    let _dwfExtrait = null;
    if (typeof window.dwfExtraireProvenance === 'function') {
        _dwfExtrait = window.dwfExtraireProvenance(data);
    }
    let _dwfProv = (_dwfExtrait && _dwfExtrait.source !== 'absente')
        ? { injectes: _dwfExtrait.injectes, ignores: _dwfExtrait.ignores }
        : ((data && data.provenance && data.provenance.apports_dwf)
            || (data && data.kpis && data.kpis.provenance
                ? data.kpis.provenance.apports_dwf : null));

    if (!_dwfProv && data && data.meta && (Array.isArray(data.meta.apports_dwf) || Array.isArray(data.meta.apports_dwf_ignores))) {
        _dwfProv = {
            injectes: Array.isArray(data.meta.apports_dwf) ? data.meta.apports_dwf : [],
            ignores: Array.isArray(data.meta.apports_dwf_ignores) ? data.meta.apports_dwf_ignores : []
        };
    }

    if (_dwfProv) {
        const _injList = Array.isArray(_dwfProv.injectes)
            ? _dwfProv.injectes
            : (Array.isArray(_dwfProv) ? _dwfProv : []);
        const _ignList = Array.isArray(_dwfProv.ignores) ? _dwfProv.ignores : [];
        const nInj = _injList.length;
        const nIgn = _ignList.length;

        if (_dwfMarkerRow) {
            _dwfMarkerRow.style.display = (nInj > 0) ? 'flex' : 'none';
        }

        if (_dwfLeg) {
            _dwfLeg.style.display = 'block';
            if (nInj > 0) {
                let qCumulM3s = 0;
                _injList.forEach(a => {
                    const q = parseFloat((a && (a.debit_moyen_m3s !== undefined ? a.debit_moyen_m3s : a.q_base_m3s)) || 0);
                    if (isFinite(q)) qCumulM3s += q;
                });
                const qLs = (qCumulM3s * 1000).toLocaleString('fr-FR', { minimumFractionDigits: 1, maximumFractionDigits: 2 });
                _dwfLeg.innerHTML = `
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 2px;">
                        <span style="color: #38bdf8; font-weight: 700;"><i class="fas fa-faucet-drip me-1"></i> Apports DWF :</span>
                        <span style="font-weight: 800; color: #38bdf8; background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.35); padding: 1px 6px; border-radius: 4px; font-size: 10px;"><b>${nInj} injecté${nInj > 1 ? 's' : ''}</b></span>
                    </div>
                    <div style="font-size: 10px; color: #cbd5e1; display: flex; justify-content: space-between; align-items: center;">
                        <span>Débit moyen cumulé :</span>
                        <b style="color: #6ee7b7;">${qLs} L/s</b>
                    </div>
                    ${nIgn > 0 ? `<div style="font-size: 9.5px; color: #fbbf24; margin-top: 2px;"><i class="fas fa-exclamation-circle me-1"></i> ${nIgn} ignoré(s)</div>` : ''}
                `;
            } else {
                _dwfLeg.innerHTML = `<i class="fas fa-faucet-drip me-1"></i> Apports DWF : <b>aucun injecté</b>${nIgn > 0 ? ` — ${nIgn} ignoré(s)` : ''}`;
            }
        }
    } else {
        if (_dwfMarkerRow) _dwfMarkerRow.style.display = 'none';
        if (_dwfLeg) {
            _dwfLeg.style.display = 'none';
            _dwfLeg.innerHTML = '';
        }
    }
};

// ==========================================
// POINTS 2 & 3 : COUCHES RÉSULTATS SWMM 5.2
// ==========================================
window._afficherResultatsSimulationNu = function(data, force = false) {
            // Garde anti-récursion : l'affichage chaîne highlightCluster →
            // gererAffichageSimulationPourBassin → ré-affiche les résultats,
            // ce qui bouclait indéfiniment (« Maximum call stack size
            // exceeded ») dès qu'un bassin avec simulation en cache était
            // sélectionné pendant le rendu. Le drapeau est levé le temps de
            // l'exécution synchrone puis relâché au tick suivant.
            if (window._affichageSimEnCours) return;
            if (!data || !data.conduit_results || !data.node_results) return;

            // Garde anti-doublon : ne pas recalculer ni re-rendre si exactement la même simulation est déjà affichée
            // (contournable avec force=true, notamment à la fermeture du time slider pour rétablir les maximums)
            if (!force && window._dernierResultatSimulation === data &&
                window.couches && window.couches.res_conduites &&
                window.carte && window.carte.hasLayer(window.couches.res_conduites) &&
                window.couches.res_conduites.getLayers().length > 0) {
                if (typeof window.actualiserLegendeDwf === 'function') {
                    window.actualiserLegendeDwf(data);
                }
                return;
            }

            window._affichageSimEnCours = true;
            setTimeout(function () { window._affichageSimEnCours = false; }, 150);
            window._dernierResultatSimulation = data;

            // Contexte « infobulles » : réinitialise le registre et active
            // le menu contextuel carte (case à cocher Infobulles au clic droit).
            window._simTipLayers = [];
            window._simCtxActif = true;
            if (typeof _masquerMenuInfobullesSim === 'function') _masquerMenuInfobullesSim();
            if (typeof _menuAnomaliesProfilHide === 'function') _menuAnomaliesProfilHide();
            if (!window._simCtxBound) {
                window._simCtxBound = true;
                const _mapCtx = window.carte || window.map;
                if (_mapCtx && typeof _mapCtx.on === 'function') {
                    _mapCtx.on('contextmenu', function (e) {
                        if (!window._simCtxActif) return;
                        // Le menu des anomalies profil (s'il est actif) intègre
                        // déjà la case à cocher Infobulles — pas de doublon.
                        if (window._anomaliesProfil) return;
                        if (e && e.originalEvent) {
                            try { e.originalEvent.preventDefault(); } catch (_) {}
                        }
                        _afficherMenuInfobullesSim(e && e.originalEvent);
                    });
                }
            }

            // LOT P1.5.3 — traçabilité DWF dans la légende : réutilise la
            // provenance existante (provenance.apports_dwf du résultat),
            // jamais de mécanisme parallèle.
            if (typeof window.actualiserLegendeDwf === 'function') {
                window.actualiserLegendeDwf(data);
            }

            // P0 — couleur dérivée du STATUT sémantique et des ratios physiques SWMM :
            // palette normal (<50% cyan éclatant) → modéré (50-80% vert) → critique (80-100% ambre) → surcharge (≥100% rouge).
            const _couleurConduite = function(r) {
                if (!r) return '#06b6d4';
                const qRatio = (r.flow_ratio !== undefined && r.flow_ratio !== null) ? Number(r.flow_ratio) : null;
                const dRatio = (r.depth_ratio !== undefined && r.depth_ratio !== null) ? Number(r.depth_ratio) : null;
                const maxRatio = Math.max(qRatio || 0, dRatio || 0);

                if (r.status === 'surcharge' || maxRatio >= 1.0) return '#ef4444';
                if (r.status === 'critique' || maxRatio >= 0.80) return '#f59e0b';
                if (r.status === 'moderee' || maxRatio >= 0.50) return '#10b981';
                return '#06b6d4';
            };

            // Réactiver les boutons d'animation et d'analyse hydrologique si une simulation est disponible
            if (typeof _desactiverBoutonsHydro === 'function') {
                _desactiverBoutonsHydro();
            }

            // Assurer l'existence de panes z-index dédiés pour que les résultats SWMM soient toujours visibles au-dessus des sous-bassins et clusters
            if (!carte.getPane('swmmResultsPane')) {
                const p = carte.createPane('swmmResultsPane');
                p.style.zIndex = 620;
            } else {
                carte.getPane('swmmResultsPane').style.zIndex = 620;
            }
            if (!carte.getPane('swmmNodesPane')) {
                const p = carte.createPane('swmmNodesPane');
                p.style.zIndex = 650;
            } else {
                carte.getPane('swmmNodesPane').style.zIndex = 650;
            }
            if (carte.getPane('tooltipPane')) {
                carte.getPane('tooltipPane').style.zIndex = 1000;
            }
            if (carte.getPane('popupPane')) {
                carte.getPane('popupPane').style.zIndex = 1100;
            }

            // Afficher la légende interactive sur la carte uniquement suite à la simulation
            const leg = document.getElementById('sim-floating-legend');
            if (leg) {
                leg.classList.add('active-legend');
                leg.style.display = 'block';
            }

            // Pour ne pas alourdir l'affichage (éviter des milliers d'éléments SVG superflus),
            // désactiver TOUTES les couches physiques et ne laisser que les couches thématiques.
            if (!window._etatCouchesAvantSimulation) {
                window._etatCouchesAvantSimulation = {};
                const _ids = ['conduites', 'regards', 'rejets', 'stations', 'step', 'ouvrages', 'bassins', 'orphelins', 'subcatchments', 'sens-ecoulement'];
                _ids.forEach(id => {
                    const el = document.getElementById('f-' + id);
                    if (el) window._etatCouchesAvantSimulation[id] = el.checked;
                });
            }

            const _couchesPhysiques = [
                'conduites', 'regards', 'rejets', 'stations', 'step',
                'ouvrages', 'bassins', 'orphelins', 'subcatchments', 'sens_ecoulement'
            ];
            _couchesPhysiques.forEach(type => {
                if (couches && couches[type] && carte.hasLayer(couches[type])) {
                    carte.removeLayer(couches[type]);
                }
            });

            if (typeof clusterCouche !== 'undefined' && clusterCouche && carte.hasLayer(clusterCouche)) {
                carte.removeLayer(clusterCouche);
            }
            if (window._coucheRaccordementsOrphelins && carte.hasLayer(window._coucheRaccordementsOrphelins)) {
                carte.removeLayer(window._coucheRaccordementsOrphelins);
                window._coucheRaccordementsOrphelins.clearLayers();
            }

            // Décocher les cases correspondantes dans le panneau latéral pour un affichage limpide et cohérent
            const _chkIds = [
                'f-conduites', 'f-regards', 'f-rejets', 'f-stations', 'f-step',
                'f-ouvrages', 'f-bassins', 'f-orphelins', 'f-subcatchments', 'f-sens-ecoulement'
            ];
            _chkIds.forEach(id => {
                const el = document.getElementById(id);
                if (el) el.checked = false;
            });

            if (!carte.hasLayer(couches.res_conduites)) couches.res_conduites.addTo(carte);
            if (!carte.hasLayer(couches.res_regards)) couches.res_regards.addTo(carte);

            // Nettoyer les couches de résultats existantes
            couches.res_conduites.clearLayers();
            couches.res_regards.clearLayers();

            const cRes = data.conduit_results;
            const nRes = data.node_results;

            // Indexer les conduites par extrémités (u_node, d_node) et par link_id pour un appariement direct infaillible
            const conduitByNodes = {};
            const conduitByLinkId = {};
            Object.values(cRes).forEach(r => {
                const u = String(r.u_node || '').replace(/\.0$/, '').trim();
                const d = String(r.d_node || '').replace(/\.0$/, '').trim();
                if (u && d) {
                    conduitByNodes[`${u}->${d}`] = r;
                    conduitByNodes[`${d}->${u}`] = r;
                }
                if (r.link_id) {
                    conduitByLinkId[String(r.link_id).trim().toLowerCase()] = r;
                }
            });

            const _trouverResultatConduite = function(p) {
                if (!p) return null;
                const u = String(p.ID_AMONT || p.id_amont || p.AMONT || p.amont || p.NODE1 || p.node1 || '').replace(/\.0$/, '').trim();
                const d = String(p.ID_AVAL || p.id_aval || p.AVAL || p.aval || p.NODE2 || p.node2 || '').replace(/\.0$/, '').trim();
                if (u && d && (conduitByNodes[`${u}->${d}`] || conduitByNodes[`${d}->${u}`])) {
                    return conduitByNodes[`${u}->${d}`] || conduitByNodes[`${d}->${u}`];
                }
                const lid = String(p.link_id || p.LINK_ID || p.id || p.ID || p.code || p.CODE || '').trim().toLowerCase();
                if (lid && conduitByLinkId[lid]) {
                    return conduitByLinkId[lid];
                }
                return null;
            };

            // Réseau sous pression : conduites de refoulement/pompage issues du
            // modèle .inp (meta.conduit_endpoints["fonction"] et meta.refoulements_traites)
            const _endpointsMeta = (data.meta && data.meta.conduit_endpoints) || {};
            const _refoulementsMeta = Array.isArray(data.meta && data.meta.refoulements_traites)
                ? data.meta.refoulements_traites : [];
            const refoulementCids = new Set();
            const pompeParCid = {};
            Object.keys(_endpointsMeta).forEach(cid => {
                const ep = _endpointsMeta[cid] || {};
                if (String(ep.fonction || '').toLowerCase() === 'refoulement') {
                    refoulementCids.add(String(cid));
                    if (ep.pompe) pompeParCid[String(cid)] = ep.pompe;
                }
            });
            _refoulementsMeta.forEach(rf => {
                if (rf && rf.cid) refoulementCids.add(String(rf.cid));
                if (rf && rf.cid && rf.pompe) pompeParCid[String(rf.cid)] = rf.pompe;
            });
            const _estRefoulementResultat = function(r) {
                return !!(r && refoulementCids.has(String(r.link_id || '')));
            };

            window._rendreCouchesResultatsSimulation({
                data: data,
                nRes: nRes,
                _couleurConduite: _couleurConduite,
                _trouverResultatConduite: _trouverResultatConduite,
                pompeParCid: pompeParCid,
                _estRefoulementResultat: _estRefoulementResultat
            });

            // Assurer que les couches de résultats sont bien au premier plan
            try {
                if (couches.res_conduites && couches.res_conduites.bringToFront) couches.res_conduites.bringToFront();
                if (couches.res_regards && couches.res_regards.bringToFront) couches.res_regards.bringToFront();
            } catch(e) {}

            // Cadrage automatique et centrage optimal sur le sous-bassin / réseau simulé
            try {
                let boundsToFit = null;
                if (couches.res_conduites && couches.res_conduites.getLayers().length > 0) {
                    boundsToFit = couches.res_conduites.getBounds();
                } else if (window._activeClusterLayer && window._activeClusterLayer.getBounds && window._activeClusterLayer.getBounds().isValid()) {
                    boundsToFit = window._activeClusterLayer.getBounds();
                }
                // Ne pas détourner le zoom si l'utilisateur vient de positionner
                // la carte via la recherche d'ouvrage (ré-affichage asynchrone tardif).
                const _zoomBloqueRecherche = window._rechercheCentrageJusqua && Date.now() < window._rechercheCentrageJusqua;
                if (!_zoomBloqueRecherche && boundsToFit && boundsToFit.isValid()) {
                    carte.fitBounds(boundsToFit, { padding: [35, 35], maxZoom: 19 });
                }
            } catch(e) {
                console.warn("Erreur cadrage zoom simulation:", e);
            }

            if (typeof window.mettreAJourIndicateursEtKpisSimulation === 'function') {
                window.mettreAJourIndicateursEtKpisSimulation(data);
            }
            // LOT P1.5.4 — bloc « Apports de temps sec (DWF) » dans la carte
            // des résultats, alimenté par la provenance de CETTE simulation.
            if (typeof window.afficherBlocResultatsDwf === 'function') {
                window.afficherBlocResultatsDwf(data);
            }

            // Indication visible Cockpit / Topbar pour la simulation courante
            // Remarque : Le pill DWF autonome est désormais masqué au profit du menu
            // déroulant hiérarchique sous le nom du bassin (topbar-bassin-dropdown).
            try {
                const dwfPill = document.getElementById('topbar-dwf-pill');
                const dwfLabel = document.getElementById('topbar-dwf-label');
                const provDwf = (data && data.provenance && data.provenance.apports_dwf)
                    || (data && data.kpis && data.kpis.provenance ? data.kpis.provenance.apports_dwf : null);
                if (dwfPill && dwfLabel) {
                    dwfPill.style.display = 'none';
                    if (provDwf) {
                        const nInj = Array.isArray(provDwf.injectes) ? provDwf.injectes.length : 0;
                        const nIgn = Array.isArray(provDwf.ignores) ? provDwf.ignores.length : 0;
                        let qTot = 0;
                        if (Array.isArray(provDwf.injectes)) {
                            provDwf.injectes.forEach(a => {
                                const q = parseFloat(a.debit_moyen_m3s || 0);
                                if (isFinite(q)) qTot += q;
                            });
                        }
                        const qLs = (qTot * 1000).toFixed(1);
                        if (nInj > 0) {
                            dwfLabel.innerHTML = `💧 DWF : <b>${nInj} injecté${nInj > 1 ? 's' : ''} (${qLs} L/s)</b>${nIgn > 0 ? ` <span style="color:#fbbf24; font-weight:800;">· ⚠️ ${nIgn} exclu${nIgn > 1 ? 's' : ''}</span>` : ''}`;
                        } else {
                            dwfLabel.innerHTML = `💧 DWF : Aucun injecté${nIgn > 0 ? ` <span style="color:#fbbf24; font-weight:800;">· ⚠️ ${nIgn} exclu${nIgn > 1 ? 's' : ''}</span>` : ''}`;
                        }
                    }
                }
            } catch (_) {}

            window._dernierResultatSimulation = data;
            if (typeof window.mettreAJourIndicateurBassin === 'function' && window._selectedClusterId) {
                window.mettreAJourIndicateurBassin(window._selectedClusterId, data);
            }
            if (typeof window.actualiserDropdownBassin === 'function') {
                window.actualiserDropdownBassin();
            }
            if (typeof activerActionsSimulation === 'function') {
                activerActionsSimulation(true);
            }
        };


/**
 * Point d'entrée public des résultats de simulation.
 * Quand le module contexte_spatial.js est chargé (cockpit), la vue est
 * synchronisée sur le snapshot producteur AVANT tout rendu (INV-1/INV-2).
 * Sinon (tests unitaires JS, pages autonomes), alias direct du rendu.
 */
if (typeof window._syncContexteAvecResultat === 'function') {
    window.afficherResultatsSimulation = function (data, force = false) {
        if (!data) return;
        window._syncContexteAvecResultat(data).then(function (res) {
            if (res && res.ok === false) {
                if (typeof window._notifierMismatchSnapshot === 'function') {
                    window._notifierMismatchSnapshot();
                }
                return;
            }
            if (typeof window._afficherResultatsSimulationNu === 'function') {
                window._afficherResultatsSimulationNu(data, force);
            }
        }).catch(function (e) {
            console.warn('[contexte-spatial] sync résultat impossible :', e);
            if (typeof window._afficherResultatsSimulationNu === 'function') {
                window._afficherResultatsSimulationNu(data, force);
            }
        });
    };
} else {
    window.afficherResultatsSimulation = function (data, force = false) {
        if (typeof window._afficherResultatsSimulationNu === 'function') {
            window._afficherResultatsSimulationNu(data, force);
        }
    };
}
