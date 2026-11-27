/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-27
 * Date de modification : 2026-11-27
 * Objet : Mise a jour IHM et tooltip de la zone simulee (extrait de static/js/app/resultats_couches.js)
 * ================================================================================
 */

        const zoomerSurZoneSimulee = window.zoomerSurZoneSimulee;

        function mettreAJourIHMZoneSimulee(data) {
            if (!data) return;
            const meta = data.meta || {};
            const k = data.kpis || {};
            const isTargeted = !!meta.cluster_id;

            // 1. Panneau d'Ingénierie : Mini-stats de l'en-tête
            const miniStatsEl = document.getElementById('mini-stats');
            if (miniStatsEl) {
                if (isTargeted) {
                    // meta.bassin_nom peut contenir l'identifiant brut
                    // (« 459 ») : on ne retient qu'un vrai nom métier.
                    const _cidM = String(meta.cluster_id !== undefined && meta.cluster_id !== null ? meta.cluster_id : '');
                    const _nomMeta = [meta.cluster_nom, meta.bassin_nom]
                        .map(v => String(v || '').trim())
                        .find(v => v && !/^\d+$/.test(v) && !/^Bassin\s+\d+$/i.test(v) && v !== _cidM);
                    const _nomBassin = _nomMeta
                        || (window._bassinNoms && window._bassinNoms[_cidM])
                        || `Bassin ${_cidM}`;
                    miniStatsEl.innerHTML = `<span style="color: #38bdf8; font-weight: 700;">Bassin : ${_nomBassin}</span> | Conduites: <b>${meta.conduits_count}</b> | Regards: <b>${meta.junctions_count + 1}</b>`;
                    miniStatsEl.style.background = 'rgba(56, 189, 248, 0.15)';
                    miniStatsEl.style.border = '1px solid rgba(56, 189, 248, 0.3)';
                    miniStatsEl.style.color = '#f8fafc';
                } else {
                    miniStatsEl.innerHTML = `Réseau Complet | Conduites: <b>${meta.conduits_count}</b> | Exutoires: <b>${meta.outfalls_count || 1}</b>`;
                    miniStatsEl.style.background = 'rgba(255, 255, 255, 0.06)';
                    miniStatsEl.style.border = 'none';
                    miniStatsEl.style.color = '#94a3b8';
                }
            }

            // 2. Section 2 Hydrologie : Badge & Description
            const badgeSb = document.getElementById('badge-subcatchments-count');
            if (badgeSb) {
                if (isTargeted) {
                    badgeSb.innerHTML = `${meta.subcatchments_count} SB (${meta.total_area_ha} ha)`;
                    badgeSb.style.background = 'rgba(16, 185, 129, 0.2)';
                    badgeSb.style.color = '#34d399';
                } else {
                    badgeSb.innerHTML = `${meta.subcatchments_count} SB (${meta.total_area_ha} ha)`;
                    badgeSb.style.background = '';
                    badgeSb.style.color = '';
                }
            }

            // Réseau sous pression : pompes et tronçons de refoulement modélisés
            const _rfTraites = Array.isArray(meta.refoulements_traites) ? meta.refoulements_traites : [];
            const _nbPompes = _rfTraites.filter(x => x && x.tete_refoulement).length;
            const _rfTxt = _rfTraites.length > 0
                ? ` · ⛽ <b style="color:#fca5a5;">${_nbPompes} pompe(s)</b>, ${_rfTraites.length} tronçon(s) sous pression`
                : '';

            const subLeg = document.getElementById('subcatchments-legend');
            if (subLeg) {
                if (isTargeted) {
                    subLeg.innerHTML = `Périmètre simulé : <b style="color: #38bdf8;">${meta.cluster_nom || meta.bassin_nom || ('Bassin ' + meta.cluster_id)}</b> (${meta.total_area_ha} ha drainés vers l'exutoire ${meta.outfall_code || ''})${_rfTxt}.`;
                } else {
                    subLeg.innerHTML = `Surface drainée totale : <b>${meta.total_area_ha} ha</b> sur <b>${meta.subcatchments_count} sous-bassins</b>${_rfTxt}.`;
                }
            }

            // 3. Section Bassin Sélectionné dans la barre latérale
            const bSec = document.getElementById('bassin-section');
            if (bSec) bSec.style.display = 'block';

            const bSel = document.getElementById('bassin-select');
            let valeurBassin = null;
            if (bSel && isTargeted) {
                const cidMeta = String(meta.cluster_id);
                // meta.cluster_id est dans l'espace exutoire (ex. 234) alors
                // que le dropdown utilise le cluster_id positionnel (ex. 87).
                // Retrouver l'option du dropdown via data-exutoire-id /
                // data-bassin-ref / nom du bassin avant de créer un fantôme.
                const nomMeta = String(meta.cluster_nom || meta.bassin_nom || '').trim().toLowerCase();
                const cidMetaBas = cidMeta.toLowerCase();
                // Priorité 1 : nom du bassin — discriminant fiable car les
                // exutoire_id peuvent entrer en collision avec le
                // cluster_id d'un autre bassin (ex. exutoire 4 = Bensouna
                // alors que meta.cluster_id=4 = Rejet Lbatimat).
                if (nomMeta) {
                    for (let opt of bSel.options) {
                        const txt = String(opt.textContent || '').trim().toLowerCase();
                        // Frontière de mot : « rn 4 » ne doit pas matcher « rn 45 ».
                        if (txt === nomMeta || txt.startsWith(nomMeta + ' ')
                                || txt.startsWith(nomMeta + '(')) {
                            valeurBassin = opt.value; break;
                        }
                    }
                }
                // Priorité 2 : cluster_id exact, puis exutoire/bassin_ref.
                if (!valeurBassin) {
                    for (let opt of bSel.options) {
                        if (opt.value === cidMeta) { valeurBassin = opt.value; break; }
                        const exId = String(opt.dataset.exutoireId || '').trim().toLowerCase();
                        const bref = String(opt.dataset.bassinRef || '').trim().toLowerCase();
                        if ((exId && exId === cidMetaBas)
                                || (bref && bref === ('exutoire:' + cidMetaBas))) {
                            valeurBassin = opt.value; break;
                        }
                    }
                }
                if (!valeurBassin) {
                    const newOpt = document.createElement('option');
                    newOpt.value = cidMeta;
                    newOpt.textContent = `${meta.cluster_id}. ${meta.cluster_nom || 'Bassin ' + meta.cluster_id}`;
                    bSel.appendChild(newOpt);
                    valeurBassin = cidMeta;
                }
                bSel.value = valeurBassin;
            }

            // Conserver une barre latérale sobre : afficher la fiche standard du bassin sans le cartouche lourd de simulation
            if (isTargeted) {
                // Passer l'identité du dropdown (cluster_id positionnel) :
                // highlightCluster/afficherInfoBassin comparent aux
                // properties.cluster_id des couches cartographiques.
                const cidAffichage = valeurBassin || meta.cluster_id;
                afficherInfoBassin(cidAffichage);
                if (typeof highlightCluster === 'function') {
                    highlightCluster(cidAffichage, window._activeClusterLayer || (typeof couches !== 'undefined' ? couches.bassins : null));
                }
            }

            // 4. Mettre en valeur les sous-bassins Voronoï du périmètre simulé
            if (couches.subcatchments) {
                const nRes = data.node_results || {};
                const simNodes = new Set((meta.simulated_nodes || []).map(String));
                couches.subcatchments.eachLayer(layer => {
                    const p = (layer.feature && layer.feature.properties) ? layer.feature.properties : {};
                    const outlet = String(p.outlet || '');
                    if (isTargeted) {
                        const isSim = (simNodes.size > 0) ? simNodes.has(outlet) : (nRes[outlet] || (meta.outfall_code && outlet === String(meta.outfall_code)));
                        if (isSim) {
                            layer.setStyle({
                                color: '#10b981',
                                fillColor: '#10b981',
                                fillOpacity: 0.12,
                                weight: 1.2,
                                opacity: 0.8
                            });
                        } else {
                            layer.setStyle({
                                color: '#475569',
                                fillColor: '#334155',
                                fillOpacity: 0.02,
                                weight: 0.5,
                                opacity: 0.10
                            });
                        }
                    } else {
                        layer.setStyle({
                            color: '#059669',
                            fillColor: '#10b981',
                            fillOpacity: 0.18,
                            weight: 1.5,
                            opacity: 0.85
                        });
                    }
                });
            }

            // 5. Mettre à jour le titre de la légende flottante
            const legTitle = document.querySelector('#sim-floating-legend span');
            if (legTitle) {
                const _warnVersion = meta.gpkg_version_mismatch
                    ? ' <span style="color:#f59e0b; font-size:0.72rem; font-weight:700;" title="Cette simulation provient d\'une autre version du GeoPackage que le réseau actuellement affiché">⚠ autre version réseau</span>'
                    : '';
                if (isTargeted) {
                    const _rawLegNom = String(meta.cluster_nom || meta.bassin_nom || '').trim();
                    const _metierNom = (typeof window._nomMetierBassin === 'function')
                        ? String(window._nomMetierBassin(meta.cluster_id, meta) || '').trim()
                        : '';
                    const _selNom = String(window._selectedClusterNom || '').trim();
                    const _legNom = (_rawLegNom && !/^\d+$/.test(_rawLegNom))
                        ? _rawLegNom
                        : ((_metierNom && !/^\d+$/.test(_metierNom) && !/^Bassin\s+\d+$/i.test(_metierNom))
                            ? _metierNom
                            : ((_selNom && !/^\d+$/.test(_selNom)) ? _selNom : (_rawLegNom || ('Bassin ' + meta.cluster_id))));
                    legTitle.innerHTML = `<i class="fas fa-layer-group me-1"></i> SWMM 5.2 — ${_legNom}${_warnVersion}`;
                } else {
                    legTitle.innerHTML = `<i class="fas fa-layer-group me-1"></i> Légende SWMM 5.2${_warnVersion}`;
                }
            }

            // 6. Déplacer les détails de simulation sur la fenêtre de survol de la zone d'étude (bassin et sous-bassins)
            mettreAJourTooltipZoneSimulee(data);
        }

        function mettreAJourTooltipZoneSimulee(data) {
            if (!data || !data.meta) return;
            const meta = data.meta;
            const k = data.kpis || {};
            const isTargeted = !!meta.cluster_id;
            if (!isTargeted) return;

            const qExutoire = parseFloat(k.q_exutoire_m3s !== undefined ? k.q_exutoire_m3s : (k.peak_outflow_m3s || 0));
            const qDerive = parseFloat(k.q_derive_m3s !== undefined ? k.q_derive_m3s : (k.q_deleste_m3s || 0));
            const qGenere = parseFloat(k.q_genere_m3s !== undefined ? k.q_genere_m3s : (qExutoire + qDerive));
            const nbOuv = parseInt(k.nb_ouvrages_raccordes || 0, 10);
            const tauxDerive = k.taux_derive_pct !== undefined ? parseFloat(k.taux_derive_pct) : (qGenere > 0 ? ((qDerive / qGenere) * 100.0) : 0.0);
            const tauxExutoire = k.taux_exutoire_pct !== undefined ? parseFloat(k.taux_exutoire_pct) : Math.max(0, 100.0 - tauxDerive);

            const simCardHtml = `
                <div style="font-family: inherit; font-size: 12px; min-width: 220px; color: #f8fafc; padding: 2px;">
                    <div style="font-weight: 800; color: #38bdf8; font-size: 13px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.15); padding-bottom: 4px; margin-bottom: 6px;">
                        <span>${meta.cluster_nom || meta.bassin_nom || ('Bassin ' + meta.cluster_id)}</span>
                        <span style="font-size: 10px; background: rgba(56,189,248,0.25); color: #38bdf8; padding: 1px 6px; border-radius: 4px; font-weight: 800;">SIMULÉ</span>
                    </div>
                    <div style="color: #94a3b8; font-size: 11px; margin-bottom: 3px;">🏷️ Exutoire récepteur : <b>${meta.outfall_code || 'N/A'}</b></div>
                    <div style="color: #38bdf8; font-size: 11px; margin-bottom: 2px;">🌧️ Sollicitation : <b>${(Number(k.pluvio_intensite_max_mmh || meta.pluvio_intensite_max_mmh || 62.0)).toFixed(1)} mm/h</b> <small style="color:#94a3b8;">(${meta.pluvio_periode_retour || k.pluvio_periode_retour || 'T=10 ans'})</small></div>
                    <div style="margin-bottom: 2px;">📐 Surface drainée : <b>${meta.total_area_ha} ha</b> (${meta.subcatchments_count} sous-bassins)</div>
                    <div style="margin-bottom: 2px;">📍 Regards : <b>${meta.junctions_count + 1}</b> ${k.flooded_nodes_count > 0 ? `<span style="color:#ef4444; font-weight:700;">(${k.flooded_nodes_count} débordements)</span>` : ''}</div>
                    <div style="margin-bottom: 2px;">📏 Conduites : <b>${meta.conduits_count}</b></div>
                    <div style="border-top: 1px solid rgba(255,255,255,0.1); padding-top: 4px; margin-top: 4px;">
                        <div style="color: #38bdf8; font-weight: 700;">🌊 Débit généré : <b>${qGenere.toFixed(3)} m³/s</b></div>
                        <div style="color: #34d399; font-size: 11px; margin-left: 6px;">► Vers exutoire principal : <b>${qExutoire.toFixed(3)} m³/s</b> (${tauxExutoire.toFixed(1)}%)</div>
                        ${qDerive > 0 ? `<div style="color: #22d3ee; font-size: 11px; margin-left: 6px;"><i class="fas fa-random"></i> Dérivé (${nbOuv} ouv. spéc.) : <b>${qDerive.toFixed(3)} m³/s</b> (${tauxDerive.toFixed(1)}%)</div>` : ''}
                    </div>
                    <div style="color: #38bdf8; font-weight: 700; margin-top: 3px;">💧 Erreur continuité : <b>${(k.routing_continuity_error_pct || 0).toFixed(2)} %</b></div>
                </div>
            `;

            // 1. Mettre à jour les polygones de bassins versants dans couches.bassins et window._activeClusterLayer
            const updateBassinLayer = (layer) => {
                const f = layer.feature;
                if (!f || !f.properties) return;
                if (f.properties.type !== 'bassin_urbain') return;
                // meta.cluster_id est dans l'espace exutoire : le polygone
                // doit aussi matcher via exutoire_id / bassin_ref.
                const fp = f.properties;
                const cidMeta = String(meta.cluster_id).toLowerCase();
                const exF = String(fp.exutoire_id || '').trim().toLowerCase();
                const brefF = String(fp.bassin_ref || '').trim().toLowerCase();
                const matchBassin = String(fp.cluster_id) === String(meta.cluster_id)
                    || (exF && exF === cidMeta)
                    || (brefF && brefF === ('exutoire:' + cidMeta));
                if (matchBassin) {
                    if (!layer._originalTooltip) {
                        const curTip = layer.getTooltip();
                        layer._originalTooltip = curTip ? curTip.getContent() : null;
                    }
                    const fullSimTooltip = window.genererTooltipBassinVersantHtml ? window.genererTooltipBassinVersantHtml(f.properties, data) : simCardHtml;
                    layer.unbindTooltip();
                    window._enregistrerInfobulleSim(layer, fullSimTooltip, {
                        sticky: true,
                        direction: 'left',
                        offset: [-15, 0],
                        opacity: 0.98,
                        className: 'sim-bassin-tooltip'
                    });
                    layer._isSimulatedBassin = true;
                    // NB : les écouteurs namespacés Leaflet (« type.ns ») ne se
                    // déclenchent pas sur les événements DOM réels — handlers
                    // simples référencés pour permettre un retrait ciblé.
                    if (layer._simBassinHandlers) {
                        layer.off('mouseover', layer._simBassinHandlers.over);
                        layer.off('mouseout', layer._simBassinHandlers.out);
                    }
                    const _bassinOver = function() {
                        this.setStyle({
                            color: '#0284c7',
                            weight: 3.5,
                            fillColor: '#38bdf8',
                            fillOpacity: 0.32,
                            dashArray: '7, 4'
                        });
                    };
                    const _bassinOut = function() {
                        this.setStyle({
                            color: '#0284c7',
                            weight: 3.5,
                            fillColor: '#38bdf8',
                            fillOpacity: 0.20,
                            dashArray: '7, 4'
                        });
                    };
                    layer._simBassinHandlers = { over: _bassinOver, out: _bassinOut };
                    layer.on('mouseover', _bassinOver);
                    layer.on('mouseout', _bassinOut);
                    try { layer.unbindPopup(); } catch(_) {}
                    layer.options.pane = 'bassinsPane';
                    layer.setStyle({
                        color: '#0284c7',
                        weight: 3.5,
                        fillColor: '#38bdf8',
                        fillOpacity: 0.20,
                        dashArray: '7, 4'
                    });
                    try { layer.bringToFront(); } catch(e) {}
                }
            };

            if (couches.bassins) couches.bassins.eachLayer(updateBassinLayer);
            if (window._activeClusterLayer) window._activeClusterLayer.eachLayer(updateBassinLayer);

            // 2. Mettre à jour les sous-bassins versants Voronoï du périmètre simulé
            if (couches.subcatchments) {
                const nRes = data.node_results || {};
                const simNodes = new Set((meta.simulated_nodes || []).map(String));
                couches.subcatchments.eachLayer(sbLayer => {
                    const p = (sbLayer.feature && sbLayer.feature.properties) ? sbLayer.feature.properties : {};
                    const outlet = String(p.outlet || '');
                    const isSim = (simNodes.size > 0) ? simNodes.has(outlet) : (nRes[outlet] || (meta.outfall_code && outlet === String(meta.outfall_code)));
                    if (isSim) {
                        if (!sbLayer._originalTooltip) {
                            const curTip = sbLayer.getTooltip();
                            sbLayer._originalTooltip = curTip ? curTip.getContent() : null;
                        }
                        const sId = p.subcatchment_id || p.id || 'SB';
                        const aHa = (p.area_ha || 0).toFixed(2);
                        const sbTooltipHtml = `
                            <div style="font-family: inherit; font-size: 12px; min-width: 220px; color: #f8fafc; padding: 2px;">
                                <div style="font-weight: 800; color: #38bdf8; font-size: 13px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.15); padding-bottom: 4px; margin-bottom: 6px;">
                                    <span>${meta.cluster_nom || meta.bassin_nom || ('Bassin ' + meta.cluster_id)}</span>
                                    <span style="font-size: 10px; background: rgba(56,189,248,0.25); color: #38bdf8; padding: 1px 6px; border-radius: 4px; font-weight: 800;">SIMULÉ</span>
                                </div>
                                <div style="color: #94a3b8; font-size: 11px; margin-bottom: 3px;">🏷️ Exutoire récepteur : <b>${meta.outfall_code || 'N/A'}</b></div>
                                <div style="margin-bottom: 2px;">📐 Surface drainée : <b>${meta.total_area_ha} ha</b> (${meta.subcatchments_count} sous-bassins)</div>
                                <div style="margin-bottom: 2px;">📍 Regards : <b>${meta.junctions_count + 1}</b> ${k.flooded_nodes_count > 0 ? `<span style="color:#ef4444; font-weight:700;">(${k.flooded_nodes_count} débordements)</span>` : ''}</div>
                                <div style="margin-bottom: 2px;">📏 Conduites : <b>${meta.conduits_count}</b></div>
                                <div style="border-top: 1px solid rgba(255,255,255,0.1); padding-top: 4px; margin-top: 4px;">
                                    <div style="color: #38bdf8; font-weight: 700;">🌊 Débit généré : <b>${qGenere.toFixed(3)} m³/s</b></div>
                                    <div style="color: #34d399; font-size: 11px; margin-left: 6px;">► Vers exutoire principal : <b>${qExutoire.toFixed(3)} m³/s</b> (${tauxExutoire.toFixed(1)}%)</div>
                                    ${qDerive > 0 ? `<div style="color: #22d3ee; font-size: 11px; margin-left: 6px;"><i class="fas fa-random"></i> Dérivé (${nbOuv} ouv. spéc.) : <b>${qDerive.toFixed(3)} m³/s</b> (${tauxDerive.toFixed(1)}%)</div>` : ''}
                                </div>
                                <div style="color: #38bdf8; font-weight: 700; margin-bottom: 5px; margin-top: 3px;">💧 Erreur continuité : <b>${(k.routing_continuity_error_pct || 0).toFixed(2)} %</b></div>
                                <div style="border-top: 1px dashed rgba(255,255,255,0.15); padding-top: 4px; color: #94a3b8; font-size: 10.5px;">
                                    <i class="fas fa-draw-polygon me-1"></i> Sous-bassin local ${sId} &bull; Regard N° ${outlet} (${aHa} ha)
                                </div>
                            </div>
                        `;
                        sbLayer.unbindTooltip();
                        window._enregistrerInfobulleSim(sbLayer, sbTooltipHtml, {
                            sticky: true,
                            direction: 'left',
                            offset: [-15, 0],
                            opacity: 0.98,
                            className: 'sim-bassin-tooltip'
                        });
                    }
                });
            }

            // 7. Couverture exhaustive : toute infobulle de bassin/sous-bassin
            // non déjà enregistrée (polygones hors zone simulée ou appariement
            // impossible) est aussi soumise à la bascule « Infobulles au
            // survol » — sinon la fiche reste affichée et la case à cocher
            // semble sans effet sur elle.
            const _dejaEnregistree = function (layer) {
                return (window._simTipLayers || []).some(function (e) { return e.layer === layer; });
            };
            const _couvrirInfobulles = function (grp) {
                if (!grp || !grp.eachLayer) return;
                grp.eachLayer(function (l) {
                    if (_dejaEnregistree(l)) return;
                    if (!l.getTooltip || !l.getTooltip()) return;
                    const cur = l.getTooltip().getContent();
                    if (!cur) return;
                    if (!l._originalTooltip) l._originalTooltip = cur;
                    l.unbindTooltip();
                    window._enregistrerInfobulleSim(l, cur, {
                        sticky: true,
                        direction: 'left',
                        offset: [-15, 0],
                        opacity: 0.98,
                        className: 'sim-bassin-tooltip'
                    });
                });
            };
            _couvrirInfobulles(couches.bassins);
            _couvrirInfobulles(window._activeClusterLayer);
            _couvrirInfobulles(couches.subcatchments);
        }
