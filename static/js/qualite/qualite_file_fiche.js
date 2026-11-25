/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-24
 * Date de modification : 2026-11-24
 * Objet : File de navigation, contexte réseau fin, fiche anomalie, zoom, changement de statut — extrait de templates/qualite.html (découpage 600 lignes)
 * ================================================================================
 */

function naviguerQueue(delta) {
    if (currentQueueList.length === 0) return;
    currentQueueIndex = Math.max(0, Math.min(currentQueueList.length - 1, currentQueueIndex + delta));
    afficherFicheAnomalie(currentQueueList[currentQueueIndex], true);
    mettreAJourCompteurQueue();
}

function mettreAJourCompteurQueue() {
    const el = document.getElementById('queue-counter');
    const btnPrev = document.getElementById('btn-prev');
    const btnNext = document.getElementById('btn-next');

    if (currentQueueList.length === 0) {
        el.textContent = '0 anomalie';
        btnPrev.disabled = true;
        btnNext.disabled = true;
    } else {
        el.textContent = `Anomalie ${currentQueueIndex + 1} sur ${currentQueueList.length}`;
        btnPrev.disabled = (currentQueueIndex === 0);
        btnNext.disabled = (currentQueueIndex === currentQueueList.length - 1);
    }
}

// 6bis. « Fine réseau » volatile — contexte local du tronçon suspect
// Rayon adapté à l'échelle : très resserré en zoom fort, plus large
// quand la carte est dézoomée pour garder un contexte lisible.
function rayonContexteReseau() {
    const z = map ? map.getZoom() : 16;
    if (z >= 17) return 20;
    if (z >= 15) return 40;
    return 80;
}

function effacerContexteReseau() {
    _fineReseauReq++;  // invalide tout fetch encore en vol
    if (fineNetworkGroup) fineNetworkGroup.clearLayers();
}

async function chargerContexteReseauFin(idConduite) {
    const reqId = ++_fineReseauReq;
    if (fineNetworkGroup) fineNetworkGroup.clearLayers();
    if (!idConduite) return;
    try {
        const token = localStorage.getItem('swmm_access_token');
        const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
        const rayon = rayonContexteReseau();
        const resp = await fetch(`${API_BASE}/conduites/${encodeURIComponent(idConduite)}/contexte-reseau?rayon_m=${rayon}`, { headers, credentials: 'include' });
        if (!resp.ok) return;
        const data = await resp.json();
        if (reqId !== _fineReseauReq) return; // une anomalie plus récente a pris le relais
        afficherContexteReseau(data);
    } catch (e) {
        // Couche volatile : un échec réseau ne doit jamais casser la fiche
    }
}

function afficherContexteReseau(data) {
    if (!fineNetworkGroup || !data || !Array.isArray(data.features)) return;
    const features = data.features;

    // 1. Périmètre de recherche (sous les conduites)
    features.filter(f => f.properties && f.properties.type_feature === 'zone_recherche').forEach(f => {
        L.geoJSON(f, {
            style: { color: '#94a3b8', weight: 1, dashArray: '4 4', fillOpacity: 0.04, opacity: 0.7 },
            interactive: false
        }).addTo(fineNetworkGroup);
    });

    // 2. Conduites : suspect en orange épais, voisines en gris
    features.filter(f => f.properties && f.properties.type_feature === 'conduite').forEach(f => {
        const p = f.properties;
        const suspect = !!p.suspect;
        const style = suspect
            ? { color: '#f97316', weight: 5, opacity: 1 }
            : { color: '#64748b', weight: 2, opacity: 0.7 };
        const layer = L.geoJSON(f, { style }).addTo(fineNetworkGroup);
        const info = suspect
            ? `<b>TRONÇON SUSPECT ${p.id_conduite}</b><br>Amont: ${p.id_amont || '?'} · Aval: ${p.id_aval || '?'}<br>Longueur: ${p.longueur_m != null ? p.longueur_m + ' m' : '?'}<br><i>Rayon: ${data.rayon_m} m</i>`
            : `Conduite ${p.id_conduite}<br>${p.id_amont || '?'} → ${p.id_aval || '?'}`;
        layer.eachLayer(l => { if (l.bindPopup) l.bindPopup(`<div style="font-size:12px;">${info}</div>`); });
    });

    // 3. Nœuds : regards bleus, rejets/exutoires verts
    features.filter(f => f.properties && f.properties.type_feature === 'noeud').forEach(f => {
        const p = f.properties;
        const coords = f.geometry && f.geometry.coordinates;
        if (!coords || coords.length < 2) return;
        const col = p.kind_noeud === 'rejet' ? '#22c55e' : '#3b82f6';
        const label = p.kind_noeud === 'rejet' ? 'Rejet / Exutoire' : 'Regard';
        L.circleMarker([coords[1], coords[0]], {
            radius: 5, fillColor: col, color: '#ffffff', weight: 1.2, fillOpacity: 0.95
        }).bindPopup(`<div style="font-size:12px;"><b>${label}</b> ${p.id_noeud || ''}</div>`)
          .addTo(fineNetworkGroup);
    });
}

// 7. Affichage détaillé de la fiche actionnable (Panneau de Résolution Unifié)
function afficherFicheAnomalie(item, centrerCarte = false) {
    if (!item) return;
    const p = item.properties;
    const container = document.getElementById('fiche-container');

    // « Fine réseau » : recharger le contexte local du tronçon
    // (volatile — disparaît dès que l'anomalie change ou n'a pas de
    // conduite associée).
    chargerContexteReseauFin(p.id_conduite || null);

    // Hint contextuel : l'action recommandée suit la catégorie de
    // l'anomalie affichée (le top global ne doit pas masquer les autres).
    const hintEl = document.getElementById('top-action-hint');
    if (hintEl) {
        const libAction = ACTION_PAR_CATEGORIE[p.categorie];
        hintEl.innerHTML = libAction
            ? `<strong>Action recommandée :</strong> ${libAction}`
            : (_topActionGlobalHtml || '');
    }

    // Métriques physiques
    let metricsHtml = '';
    if (p.ecart_terrain_m !== undefined && p.ecart_terrain_m !== null) {
        metricsHtml += `<li><span>Dénivelée terrain observée :</span> <strong>+${p.ecart_terrain_m} m</strong></li>`;
    }
    if (p.pente_contre_pct !== undefined && p.pente_contre_pct !== null) {
        metricsHtml += `<li><span>Contre-pente mesurée :</span> <strong style="color:var(--sev-critique); font-weight:700;">${p.pente_contre_pct} %</strong></li>`;
    }
    if (p.distance_m !== undefined && p.distance_m !== null) {
        metricsHtml += `<li><span>Longueur tronçon :</span> <strong>${p.distance_m} m</strong></li>`;
    }
    if (p.confiance) {
        metricsHtml += `<li><span>Fiabilité MNT altimétrique :</span> <strong style="color:var(--accent-purple);">${p.confiance.toUpperCase()}</strong></li>`;
    }

    const isContrePente = (p.categorie === 'inversions_sens_ecoulement' || p.categorie === 'sens_ecoulement' || (p.id_amont && p.id_aval && p.pente_contre_pct !== undefined));
    const isDeconnexion = (p.categorie === 'deconnexions_spatiales' || p.categorie === 'conduites_sans_regards' || p.categorie === 'troncons_orphelins');
    const isAttributsManquants = (p.categorie === 'champs_manquants');
    const isPenteOuAlti = (p.categorie === 'pentes_suspectes' || p.categorie === 'donnees_manquantes');
    const sevIcon = (p.severite === 'critique' || p.severite === 'majeure') ? 'fa-triangle-exclamation' : 'fa-circle-info';

    let titreResolution = 'Résolution & Actions';
    let actionsButtonsHtml = '';
    let derogationLabel = 'Dérogation terrain';

    if (isDeconnexion) {
        titreResolution = 'Raccordement Topologique (Nœuds Extrémités)';
        derogationLabel = 'Dérogation terrain (Rejet libre / Antenne)';
        actionsButtonsHtml = `
            <button class="btn-primary-action btn-connect" onclick="ouvrirModalRaccordementNoeuds('${p.id_conduite || ''}', '${p.cle_anomalie || ''}', '${p.id_amont || ''}', '${p.id_aval || ''}')">
                <i class="fa-solid fa-link"></i> Raccorder les nœuds (Amont / Aval)
            </button>
            <div class="action-help-text">Assigne les identifiants de regards amont/aval ou snappe sur les nœuds détectés les plus proches.</div>
        `;
    } else if (isContrePente) {
        titreResolution = 'Résolution Hydraulique (Sens d\'Écoulement)';
        derogationLabel = 'Dérogation terrain (Refoulement / Siphon)';
        actionsButtonsHtml = `
            <button class="btn-primary-action btn-reverse" onclick="inverserSensEcoulement('${p.id_conduite || ''}', '${p.cle_anomalie || ''}', '${p.id_amont || ''}', '${p.id_aval || ''}')">
                <i class="fa-solid fa-arrows-rotate"></i> Inverser le sens de pose (${p.id_aval || 'Aval'} ➔ ${p.id_amont || 'Amont'})
            </button>
            <div class="action-help-text">Rétablit l'écoulement gravitaire amont ➔ aval dans le GeoPackage et résout l'anomalie.</div>
            <button class="btn-secondary-action" onclick="ouvrirModalCotesAlti('${p.id_conduite || ''}', '${p.cle_anomalie || ''}', ${p.prof_fe_am || 'null'}, ${p.prof_fe_av || 'null'})" style="margin-top:4px;">
                <i class="fa-solid fa-ruler-vertical"></i> Corriger les profondeurs de fil d'eau (si sens physique correct)
            </button>
        `;
    } else if (isAttributsManquants) {
        titreResolution = 'Complétude des Attributs Physiques SWMM';
        derogationLabel = 'Dérogation terrain (Ouvrage particulier)';
        actionsButtonsHtml = `
            <button class="btn-primary-action btn-edit btn-edit-attr" onclick="ouvrirModalEditionAttributs('${p.id_conduite || ''}', '${p.cle_anomalie || ''}', ${p.diametre || 'null'}, '${p.materiau || ''}', ${p.distance_m || 'null'})">
                <i class="fa-solid fa-pen-to-square"></i> Renseigner les attributs de section (Diamètre, Matériau)
            </button>
            <div class="action-help-text">Définit la section hydraulique et la rugosité de Manning indispensables à SWMM.</div>
        `;
    } else if (isPenteOuAlti) {
        titreResolution = 'Rectification Altimétrique & Pente';
        derogationLabel = 'Dérogation terrain (Pente conforme au site)';
        actionsButtonsHtml = `
            <button class="btn-primary-action btn-edit-cotes" onclick="ouvrirModalCotesAlti('${p.id_conduite || ''}', '${p.cle_anomalie || ''}', ${p.prof_fe_am || 'null'}, ${p.prof_fe_av || 'null'})">
                <i class="fa-solid fa-ruler-vertical"></i> Ajuster les profondeurs de fil d'eau / cotes radier
            </button>
            <div class="action-help-text">Modifie les profondeurs d'enfouissement amont/aval pour recalculer la pente hydraulique.</div>
        `;
    } else {
        actionsButtonsHtml = `
            <button class="btn-primary-action btn-connect" onclick="ouvrirModalRaccordementNoeuds('${p.id_conduite || ''}', '${p.cle_anomalie || ''}', '${p.id_amont || ''}', '${p.id_aval || ''}')">
                <i class="fa-solid fa-link"></i> Vérifier le raccordement topologique
            </button>
            <button class="btn-secondary-action" onclick="ouvrirModalEditionAttributs('${p.id_conduite || ''}', '${p.cle_anomalie || ''}', ${p.diametre || 'null'}, '${p.materiau || ''}', ${p.distance_m || 'null'})" style="margin-top:6px;">
                <i class="fa-solid fa-pen-to-square"></i> Modifier les attributs physiques
            </button>
        `;
    }

    container.innerHTML = `
        <div class="anomalie-card-actionable">
            <div class="card-header-bar">
                <div style="display:flex; align-items:center; gap:8px;">
                    <span class="badge-sev badge-${p.severite}"><i class="fa-solid ${sevIcon}"></i> ${p.severite}</span>
                    <span style="font-size:11px; font-weight:700; color:var(--text-muted); text-transform:uppercase;">
                        ${libelleCategorie(p.categorie)}
                    </span>
                </div>
                <button class="btn-zoom-anom" onclick="zoomerSurAnomalieActive()" title="Centrer et zoomer la carte sur cette anomalie (Touche Z)">
                    <i class="fa-solid fa-crosshairs"></i> Centrer <span class="kbd-badge">Z</span>
                </button>
            </div>

            <div class="card-body">
                <!-- Identité hydraulique -->
                <div class="card-meta-grid">
                    <div>
                        <div class="meta-cell-label">Tronçon / Conduite</div>
                        <div class="meta-cell-val"><span class="monospace-tag">${p.id_conduite || 'N/A'}</span></div>
                    </div>
                    <div>
                        <div class="meta-cell-label">Sens de pose (Amont ➔ Aval)</div>
                        <div class="meta-cell-val" style="display:flex; align-items:center; gap:4px;">
                            <span class="monospace-tag">${p.id_amont || '?'}</span>
                            <i class="fa-solid fa-arrow-right-long" style="color:#64748b; font-size:12px;"></i>
                            <span class="monospace-tag">${p.id_aval || '?'}</span>
                        </div>
                    </div>
                </div>

                <!-- Diagnostic & Constat technique -->
                <div class="diagnostic-box">
                    <div class="diagnostic-title"><i class="fa-solid fa-circle-exclamation"></i> Constat Hydraulique</div>
                    <div class="diagnostic-desc">${p.description || 'Anomalie détectée sur ce tronçon.'}</div>
                    ${metricsHtml ? `
                    <div class="metrics-list">
                        <ul>${metricsHtml}</ul>
                    </div>` : ''}
                </div>

                <!-- Panneau de Résolution Unifié Métier -->
                <div class="resolution-panel">
                    <div class="resolution-header">
                        <i class="fa-solid fa-wrench"></i> ${titreResolution}
                    </div>

                    <div class="action-buttons-stack">
                        ${actionsButtonsHtml}
                    </div>

                    <!-- Validation comme dérogation terrain ou statut -->
                    <div class="derogation-bar">
                        <button class="btn-derogation ${p.statut === 'revu' ? 'active' : ''}" onclick="changerStatutAnomalie('${p.cle_anomalie}', 'revu')" title="Valider cet ouvrage tel quel si conforme sur site (dérogation terrain)">
                            <i class="fa-solid fa-clipboard-check"></i> ${derogationLabel}
                        </button>
                        <div>
                            ${p.statut === 'corrige' ? `
                                <span class="status-tag status-corrected"><i class="fa-solid fa-check"></i> Résolu / Corrigé</span>
                            ` : (p.statut === 'revu' ? `
                                <span class="status-tag" style="background:#eff6ff; color:#1d4ed8; border:1px solid #bfdbfe;"><i class="fa-solid fa-shield-halved"></i> Dérogation active</span>
                            ` : `
                                <span class="status-tag" style="background:#fef2f2; color:#b91c1c; border:1px solid #fecaca;"><i class="fa-solid fa-clock"></i> À traiter</span>
                            `)}
                        </div>
                    </div>
                </div>

                <!-- Trace d'intégrité discrète en pied de fiche -->
                <div class="card-footer-trace">
                    <span>Réf. intégrité SHA-1</span>
                    <code>${p.cle_anomalie || 'N/A'}</code>
                </div>

            </div>
        </div>
    `;

    // Mettre en surbrillance systématiquement sur la carte
    mettreEnSurbrillance(item);

    if (centrerCarte) {
        zoomerSurAnomalieActive();
    }
}

// Fonctions de Zoom et Surbrillance Cartographique
function zoomerVueGlobale() {
    if (globalBoundsReseau && globalBoundsReseau.isValid()) {
        map.fitBounds(globalBoundsReseau, { padding: [30, 30], maxZoom: 16 });
    }
}

function zoomerSurAnomalieActive() {
    if (currentQueueList.length === 0 || currentQueueIndex < 0) return;
    const item = currentQueueList[currentQueueIndex];
    if (!item) return;

    const coords = item.feature?.geometry?.coordinates;
    if (!coords || coords.length < 2) return;
    const latLng = L.latLng(coords[1], coords[0]);

    mettreEnSurbrillance(item);

    if (item.marker && clusterGroup) {
        clusterGroup.zoomToShowLayer(item.marker, () => {
            map.flyTo(latLng, Math.max(map.getZoom(), 18), { duration: 0.6 });
            item.marker.openPopup();
        });
    } else {
        map.flyTo(latLng, Math.max(map.getZoom(), 18), { duration: 0.6 });
    }
}

function mettreEnSurbrillance(item) {
    if (!item) return;
    const coords = item.feature?.geometry?.coordinates;
    if (!coords || coords.length < 2) return;
    const latLng = L.latLng(coords[1], coords[0]);

    if (highlightMarker) {
        map.removeLayer(highlightMarker);
        highlightMarker = null;
    }

    const pulseIcon = L.divIcon({
        className: 'anomalie-pulse-container',
        html: '<div class="anomalie-pulse-circle"></div>',
        iconSize: [26, 26],
        iconAnchor: [13, 13]
    });

    highlightMarker = L.marker(latLng, {
        icon: pulseIcon,
        zIndexOffset: 1200
    }).addTo(map);
}

// 8. Envoi de l'action de statut vers l'API
async function changerStatutAnomalie(cleAnomalie, nouveauStatut) {
    if (!cleAnomalie) return;

    const commentaire = document.getElementById('statut-comment')?.value || '';
    afficherLoading(true, 'Enregistrement du statut...');

    try {
        const token = localStorage.getItem('swmm_access_token');
        const headers = {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        };

        const resp = await fetch(`${API_BASE}/anomalies/${cleAnomalie}/statut`, {
            method: 'POST',
            headers: headers,
            credentials: 'include',
            body: JSON.stringify({
                statut: nouveauStatut,
                commentaire: commentaire
            })
        });

        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

        // Mise à jour locale dans le GeoJSON en mémoire
        const item = currentQueueList.find(x => x.properties.cle_anomalie === cleAnomalie);
        if (item) {
            item.properties.statut = nouveauStatut;
        }

        // Rafraîchir l'affichage
        afficherFicheAnomalie(currentQueueList[currentQueueIndex], false);
        remplirTableauRecapitulatif();

    } catch (err) {
        console.error('[QUALITE] Erreur statut:', err);
        alert(`Erreur lors du changement de statut: ${err.message}`);
    } finally {
        afficherLoading(false);
    }
}

// 9. Remplissage du tableau récapitulatif
