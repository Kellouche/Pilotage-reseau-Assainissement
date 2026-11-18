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
            window.dialogueAlerte("Lancer une simulation pour avoir un profil en long", 'info');
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
        _retirerAnomaliesProfil();
    } else {
        // Si le panneau est fermé, l'ouvrir s'il y a déjà des données
        if (panel && panel.style.display === 'none' && state.lastData) {
            panel.style.display = 'flex';
            _centrerPanelProfil();
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

    const state = window.profilLongState;
    const map = _getCarte();
    if (map && state.highlightLayer) {
        map.removeLayer(state.highlightLayer);
        state.highlightLayer = null;
    }

    // Couche d'anomalies sur la carte : zoom flagrant sur le
    // tracé du profil, symbologie par type d'anomalie, disparaît au premier
    // déplacement/zoom. Menu clic-droit : enregistrer / copier / quitter.
    const _d = state.lastData;
    if (_d && _d.segments && _d.segments.some(s => s.anomalies && s.anomalies.length)) {
        _afficherAnomaliesSurCarte(_d);
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
        window.dialogueAlerte("Veuillez saisir ou sélectionner un regard amont et un regard aval.", 'info');
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
    const overlay = document.getElementById('profil-loading-overlay');
    if (overlay) overlay.style.display = 'flex';

    const url = `/api/v1/simulations/profil-en-long?node_amont=${encodeURIComponent(nodeAmont)}&node_aval=${encodeURIComponent(nodeAval)}`;

    fetch(url)
        .then(response => {
            if (!response.ok) {
                return response.json().catch(() => null).then(err => {
                    throw new Error((err && err.detail) || `Erreur serveur (${response.status})`);
                });
            }
            return response.json();
        })
        .then(data => {
            if (overlay) overlay.style.display = 'none';
            window.profilLongState.lastData = data;
            if (panel) panel.style.display = 'flex';
            // Initialiser le déplacement du panneau (draggable)
            if (typeof _initProfilLongDraggable === 'function') {
                _initProfilLongDraggable();
            }
            afficherProfilLong(data);
            // Centrer une fois la hauteur finale connue (graduations Y)
            _centrerPanelProfil();
        })
        .catch(err => {
            if (overlay) overlay.style.display = 'none';
            console.error("Erreur profil en long:", err);
            if (panel) panel.style.display = 'none';
            const msg = (err && err.message) ? err.message : '';
            if (msg.includes("Simulation non trouvée") || msg.includes("non trouvée") || msg.includes("404")) {
                window.dialogueAlerte("Lancer une simulation pour avoir un profil en long", 'info');
            } else {
                window.dialogueAlerte(`Impossible de générer le profil en long :\n${msg}`, 'erreur');
            }
            annulerSelectionProfil();
        });
}

/** Libellés courts des types d'anomalie (état, sans diagnostic détaillé). */
const _TYPE_ANOMALIE_LABELS = {
    contre_pente: 'Contre-pente',
    pente_forte: 'Pente forte',
    autocurage_insuffisant: 'Autocurage insuffisant',
    autocurage_excessif: 'Vitesse excessive',
    hydraulique: 'Hydraulique (surcharge/inondation)',
    terrain_remonte: 'Terrain remonté'
};
const _SEV_ANOMALIE_LABELS = { fort: 'Critique', moyen: 'Modéré', faible: 'Faible', info: 'Info' };
const _COULEUR_SEV = { fort: '#ef4444', moyen: '#f59e0b', faible: '#fb923c', info: '#38bdf8' };
const _ICONE_TYPE_ANOMALIE = {
    contre_pente: 'fa-arrow-up',
    pente_forte: 'fa-chart-line',
    autocurage_insuffisant: 'fa-hourglass-half',
    autocurage_excessif: 'fa-tachometer-alt',
    hydraulique: 'fa-water',
    terrain_remonte: 'fa-mountain'
};

function _libelleTypeAnomalie(t) {
    return _TYPE_ANOMALIE_LABELS[t] || String(t || 'anomalie').replace(/_/g, ' ');
}
/** État court d'une anomalie : « Fort — Contre-pente » (sans message). */
function _etatAnomalie(a) {
    const sev = (a && a.severite) || 'info';
    return `${_SEV_ANOMALIE_LABELS[sev] || sev} — ${_libelleTypeAnomalie(a && a.type)}`;
}
function _couleurSeverite(sev) {
    return _COULEUR_SEV[sev] || _COULEUR_SEV.info;
}
function _rangSeverite(sev) {
    return { fort: 4, moyen: 3, faible: 2, info: 1 }[sev] || 0;
}

/**
 * Rendu graphique Chart.js et mise à jour de l'interface
 */
function afficherProfilLong(data) {
    if (!data || !data.segments || data.segments.length === 0) return;

    // Un nouveau profil remplace toute couche d'anomalies
    _retirerAnomaliesProfil();

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
        bSurcharges.textContent = `${data.conduites_en_charge} conduite${data.conduites_en_charge > 1 ? 's' : ''} en charge`;
        bSurcharges.style.display = data.conduites_en_charge > 0 ? 'inline-block' : 'none';
    }

    // 1a. Badge de provenance altimétrique : le profil déclare si les cotes
    // radier proviennent du SIG réel, du terrain interpolé (IDW) ou d'un
    // modèle synthétique — critique pour interpréter les écarts radier/terrain.
    const bAlt = document.getElementById('badge-profil-altimetrie');
    if (bAlt) {
        const alt = data.altimetrie || null;
        if (alt && alt.mode && alt.mode !== 'indisponible') {
            const _conf = {
                sig_reel:     { bg: 'rgba(52,211,153,0.18)',  color: '#34d399', icone: 'fa-check-double' },
                terrain_idw:  { bg: 'rgba(251,191,36,0.18)',  color: '#fbbf24', icone: 'fa-mountain' },
                synthetique:  { bg: 'rgba(248,113,113,0.20)', color: '#f87171', icone: 'fa-exclamation-triangle' },
            }[alt.mode] || { bg: 'rgba(148,163,184,0.18)', color: '#94a3b8', icone: 'fa-info-circle' };
            let _txt = alt.label || 'Altimétrie';
            if (alt.ecart_radier_terrain_med_m != null && alt.mode === 'synthetique') {
                _txt += ` — écart ~${alt.ecart_radier_terrain_med_m} m`;
            }
            bAlt.innerHTML = `<i class="fas ${_conf.icone}"></i> ${_txt}`;
            bAlt.style.display = 'inline-block';
            bAlt.style.background = _conf.bg;
            bAlt.style.color = _conf.color;
            bAlt.style.border = `1px solid ${_conf.color}`;
            bAlt.title = (alt.avertissement || '') +
                (alt.source ? `\nSource : ${alt.source}` : '') +
                (alt.ecart_radier_terrain_max_m != null
                    ? `\nÉcart radier↔terrain : médiane ${alt.ecart_radier_terrain_med_m} m, max ${alt.ecart_radier_terrain_max_m} m`
                    : '');
        } else {
            bAlt.style.display = 'none';
        }
    }

    // 1b. Bandeau fiabilité du modèle sous-jacent (garde-fou hydraulicien)
    const _fiabBanner = document.getElementById('profil-fiabilite-banner');
    const _fiabTexte = document.getElementById('profil-fiabilite-texte');
    if (_fiabBanner && _fiabTexte) {
        const _verdict = data.fiabilite_modele;
        const _anomalies = data.modelisation_anomalies || [];
        const _meta = {
            'A_VERIFIER': { icon: 'fas fa-shield-alt', label: 'à vérifier', color: '#fbbf24', bg: 'rgba(251,191,36,0.12)' },
            'DEGRADE':    { icon: 'fas fa-shield-alt', label: 'dégradé',    color: '#f87171', bg: 'rgba(248,113,113,0.12)' },
        }[_verdict];
        if (_meta) {
            _fiabBanner.style.display = 'flex';
            _fiabBanner.style.color = _meta.color;
            _fiabBanner.style.background = _meta.bg;
            _fiabBanner.innerHTML = `<i class="${_meta.icon}"></i><span>Profil basé sur un modèle à fiabilité ${_meta.label} — ${_anomalies.length} anomalie(s) détectée(s) par le garde-fou hydraulicien</span>`;
            _fiabBanner.title = _anomalies.map(a => `• ${a.message || a.code || ''}`).join('\n');
        } else {
            _fiabBanner.style.display = 'none';
        }
    }

    // 1c. Synthèse des anomalies hydrauliques du profil — distincte de la
    // fiabilité du modèle : un modèle SAIN peut avoir des contre-pentes,
    // débordements ou dépôts. Rend l'anomalie impossible à manquer.
    const _resAnom = document.getElementById('profil-anomalies-resume');
    const _txtAnom = document.getElementById('profil-anomalies-texte');
    if (_resAnom && _txtAnom) {
        const _sa = data.synthese_anomalies || null;
        const _nf = (_sa && _sa.forts) || 0;
        const _nm = (_sa && _sa.moyens) || 0;
        const _nt = (_sa && _sa.total) || 0;
        if (_nt > 0) {
            const _types = Object.entries((_sa && _sa.types_majeurs) || {})
                .map(([t, c]) => `${_libelleTypeAnomalie(t)} ×${c}`)
                .join(', ');
            _txtAnom.textContent = `${_nf} anomalie(s) critique(s) — avérée(s) par les données/SWMM, ` +
                `${_nm} modérée(s) — risque(s) à surveiller` +
                (_types ? ` — ${_types}` : '') +
                `. Survolez les jalons ◆ sur le graphique.`;
            _resAnom.style.display = 'flex';
            const _alerte = _nf > 0;
            _resAnom.style.color = _alerte ? '#f87171' : '#fbbf24';
            _resAnom.style.background = _alerte ? 'rgba(248,113,113,0.12)' : 'rgba(251,191,36,0.12)';
            _resAnom.title = ((_sa && _sa.messages_forts) || []).join('\n');
        } else {
            _resAnom.style.display = 'none';
        }
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
    // Étiquettes X sur deux lignes : ligne 1 = n° regard, ligne 2 = distance cumulée
    const labels = data.segments.map(s => `${s.node_id}\n${Math.round(s.distance_m)} m`);
    const aTerrain = data.segments.some(s => s.z_terrain != null);
    // P3 — terrain interpolé satellite (IDW topo) : affichage seul,
    // distinct du terrain vérifié (z_terrain) pour ne jamais être
    // confondu avec une cote altimétrique réelle.
    const aTerrainInterp = data.segments.some(s => s.z_terrain_interp != null);
    const aSommet = data.segments.some(s => s.z_sommet_regard != null);
    const terrainData = data.segments.map(s => ({ x: s.distance_m, y: s.z_terrain }));
    const terrainInterpData = data.segments.map(s => ({ x: s.distance_m, y: s.z_terrain_interp }));
    const sommetData = data.segments.map(s => ({ x: s.distance_m, y: s.z_sommet_regard }));
    const genSupData = data.segments.map(s => ({ x: s.distance_m, y: s.z_gen_superieure }));
    const radierData = data.segments.map(s => ({ x: s.distance_m, y: s.z_radier }));
    const eauConduiteData = data.segments.map(s => ({ x: s.distance_m, y: s.z_eau_conduite !== undefined && s.z_eau_conduite !== null ? s.z_eau_conduite : s.z_radier }));
    const hglData = data.segments.map(s => ({ x: s.distance_m, y: s.z_hgl }));

    const _estDebordement = s => s.hgl_regime === 'debordement'
        || (s.node_status === 'flooded' && data.hgl_base !== 'instant');
    const _estSurcharge = s => s.hgl_regime === 'surcharge'
        || (s.hgl_regime !== 'debordement' && s.z_hgl != null && s.z_gen_superieure != null && s.z_hgl > s.z_gen_superieure);

    // Classification couleur et taille des points HGL (🟢 Libre / 🟡 Surcharge / 🔴 Débordement)
    const hglPointColors = data.segments.map(s => {
        if (_estDebordement(s)) {
            return '#dc2626';
        } else if (_estSurcharge(s)) {
            return '#f97316';
        }
        return '#10b981';
    });

    const hglPointRadius = data.segments.map(s => {
        if (_estDebordement(s)) return 7;
        if (_estSurcharge(s)) return 5.5;
        return 4;
    });

    const ctx = document.getElementById('canvas-profil-long');
    if (!ctx) return;

    // ── Axe des cotes : pas rond fixe adaptatif à l'amplitude ──────────
    // Graduations entières et constantes par profil (ex. 100, 102, 104 m)
    // pour une lecture fiable : le pas est le plus petit palier rond
    // donnant au plus ~10 intervalles.
    const _toutesCotes = [];
    for (const _d of [terrainData, terrainInterpData, sommetData, genSupData, radierData, eauConduiteData, hglData]) {
        for (const _p of _d) {
            if (_p && _p.y != null && isFinite(_p.y)) _toutesCotes.push(_p.y);
        }
    }
    let _yMin = Infinity, _yMax = -Infinity;
    for (const _y of _toutesCotes) {
        if (_y < _yMin) _yMin = _y;
        if (_y > _yMax) _yMax = _y;
    }
    if (!isFinite(_yMin) || !isFinite(_yMax) || _yMax <= _yMin) {
        _yMin = 0; _yMax = 1;
    }
    const _amplitude = _yMax - _yMin;
    const _pasCandidats = [0.1, 0.2, 0.25, 0.5, 1, 2, 5, 10, 20, 50];
    let _pasCote = _pasCandidats[_pasCandidats.length - 1];
    for (const _p of _pasCandidats) {
        if (_amplitude / _p <= 10) { _pasCote = _p; break; }
    }
    const _nbGraduations = Math.ceil(_amplitude / _pasCote) + 1;
    // Hauteur du graphique dimensionnée sur le nombre de graduations
    // (~24 px par palier + marge pour les étiquettes X), bornée
    // pour ne pas masquer la carte.
    const _hauteurChart = Math.min(540, Math.max(260, _nbGraduations * 24 + 40));
    const _panelProfil = document.getElementById('panel-profil-long');
    if (_panelProfil) {
        _panelProfil.style.height = `${Math.min(700, _hauteurChart + 110)}px`;
    }

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
                ...(aTerrain ? [{
                    label: 'Terrain naturel (MNT)',
                    data: terrainData,
                    borderColor: '#10b981',
                    backgroundColor: 'transparent',
                    borderWidth: 2.2,
                    pointRadius: 4.5,
                    pointBackgroundColor: '#10b981',
                    fill: false,
                    tension: 0.1
                }] : []),
                ...(aTerrainInterp ? [{
                    label: 'Terrain interpolé IDW (topo — approximatif, ≠ fond de regard)',
                    data: terrainInterpData,
                    borderColor: '#38bdf8',
                    backgroundColor: 'transparent',
                    borderWidth: 1.8,
                    borderDash: [6, 4],
                    pointRadius: 0,
                    fill: false,
                    tension: 0.1
                }] : []),
                ...(aSommet ? [{
                    label: 'Plan de surverse (seuil de débordement SWMM)',
                    data: sommetData,
                    borderColor: '#0d9488',
                    backgroundColor: 'transparent',
                    borderWidth: 1.8,
                    borderDash: [2, 3],
                    pointRadius: 0,
                    fill: false,
                    tension: 0
                }] : []),
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
                },
                {
                    label: 'Alerte : débordement confirmé (SWMM)',
                    // Points objets systématiques (jamais null) : Chart.js
                    // rejette les entrées null mélangées en mode objet.
                    // Visibilité pilotée par pointRadius.
                    data: data.segments.map(s => ({
                        x: s.distance_m,
                        y: (s.z_hgl != null ? s.z_hgl : (s.z_sommet_regard != null ? s.z_sommet_regard : s.z_radier))
                    })),
                    showLine: false,
                    pointStyle: 'triangle',
                    pointRadius: data.segments.map(s => _estDebordement(s) ? 9 : 0),
                    pointHoverRadius: 12,
                    pointBackgroundColor: '#ef4444',
                    pointBorderColor: '#ffffff',
                    pointBorderWidth: 2
                },
                {
                    label: 'Anomalies du profil (jalons)',
                    // Jalons ◆ par nœud : une anomalie est accrochée au
                    // nœud aval du tronçon concerné (voir backend
                    // `anomalies` / `resume_anomalies`). Couleur = pire
                    // sévérité du nœud ; rayon 0 quand aucune anomalie.
                    data: data.segments.map((s, idx) => ({
                        x: labels[idx],
                        y: (s.z_radier != null ? s.z_radier : (s.z_hgl != null ? s.z_hgl : (s.z_terrain_interp != null ? s.z_terrain_interp : s.z_terrain)))
                    })),
                    showLine: false,
                    pointStyle: 'rectRot',
                    pointRadius: data.segments.map(s => (s.anomalies && s.anomalies.length) ? 9 : 0),
                    pointHoverRadius: 13,
                    pointBackgroundColor: data.segments.map(s => {
                        const an = s.anomalies || [];
                        if (!an.length) return 'transparent';
                        const sev = an.some(a => a.severite === 'fort') ? 'fort'
                            : an.some(a => a.severite === 'moyen') ? 'moyen'
                            : an.some(a => a.severite === 'faible') ? 'faible' : 'info';
                        return { fort: '#ef4444', moyen: '#f59e0b', faible: '#fb923c', info: '#38bdf8' }[sev];
                    }),
                    pointBorderColor: '#ffffff',
                    pointBorderWidth: 2
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
                    displayColors: false,
                    // N'afficher l'infobulle que sur les points des regards (dataset HGL)
                    filter: function(tooltipItem) {
                        const lbl = tooltipItem.dataset && tooltipItem.dataset.label;
                        return lbl === 'Ligne de charge HGL (zone de surpression hachuree)'
                            || lbl === 'Ligne de charge HGL (zone de surpression hachurée)'
                            || lbl === 'Anomalies du profil (jalons)';
                    },
                    callbacks: {
                        title: function(items) {
                            if (!items.length) return '';
                            const idx = items[0].dataIndex;
                            const s = data.segments[idx];
                            return `Regard : ${s.node_id} (Distance : ${s.distance_m} m)`;
                        },
                        label: function(item) {
                            const s = data.segments[item.dataIndex];
                            if (!s) return '';
                            const _lblDs = item.dataset && item.dataset.label;
                            if (_lblDs === 'Anomalies du profil (jalons)') {
                                const an = s.anomalies || [];
                                if (!an.length) return '';
                                // État seul (sévérité + type) — les messages
                                // complets restent dans le volet alertes et
                                // le rapport exporté, pas dans l'infobulle.
                                return '⚠ ' + an.map(a => _etatAnomalie(a)).join('  •  ');
                            }
                            if (_estDebordement(s)) {
                                return `🔴 État : Débordement confirmé par SWMM (eau déversée en surface)`;
                            } else if (s.hgl_regime === 'inondation') {
                                return `🟠 État : Niveau ≥ terrain naturel (sans débordement mesuré)`;
                            } else if (_estSurcharge(s)) {
                                return `🟠 État : Conduite en surcharge`;
                            } else if (s.hgl_regime === 'inconnu' || s.z_hgl == null) {
                                return `⚪ État : Donnée hydraulique indisponible`;
                            }
                            return `🟢 État : Écoulement libre`;
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
                        font: { size: 9, family: 'JetBrains Mono' },
                        // Étiquettes horizontales sur deux lignes
                        // (n° regard / distance cumulée) ; autoSkip
                        // masque les labels qui se chevaucheraient.
                        autoSkip: true,
                        maxRotation: 0,
                        minRotation: 0,
                        padding: 2
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
                    min: Math.floor(_yMin / _pasCote) * _pasCote,
                    max: Math.ceil(_yMax / _pasCote) * _pasCote,
                    ticks: {
                        color: '#94a3b8',
                        font: { size: 10, family: 'JetBrains Mono' },
                        stepSize: _pasCote,
                        autoSkip: false
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

    // Récupérer les coordonnées géographiques des regards : d'abord celles
    // fournies par l'API par segment (fiables), repli sur les couches.
    const latlngs = [];
    segments.forEach(s => {
        const ll = (s.lat != null && s.lng != null)
            ? L.latLng(s.lat, s.lng)
            : _trouverCoordonneesRegard(s.node_id);
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

        // Zoomer pour cadrer le profil — agrandissement maximal (tuiles
        // natives jusqu'à z19) tout en gardant tout le tronçon visible.
        map.fitBounds(state.highlightLayer.getBounds(), { padding: [40, 40], maxZoom: 19 });
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
        window.dialogueAlerte("Aucun profil actif à exporter.", 'info');
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
 * Centre le panneau du profil en long au milieu du workspace.
 * Ne s'applique qu'une fois : dès que l'utilisateur le déplace
 * manuellement (_userPositionned), sa position est conservée.
 */
function _centrerPanelProfil() {
    const panel = document.getElementById('panel-profil-long');
    if (!panel || panel._userPositionned) return;
    const parent = panel.offsetParent || document.body;
    const pRect = parent.getBoundingClientRect();
    if (!pRect.width || !pRect.height) return;

    const w = Math.max(320, Math.min(1240, pRect.width - 40));
    // La hauteur est fixée par le rendu (graduations Y) ; on la
    // borne à l'espace disponible pour ne jamais déborder.
    let h = panel.offsetHeight || 420;
    const hMax = pRect.height - 16;
    if (h > hMax) {
        h = hMax;
        panel.style.height = `${h}px`;
    }
    panel.style.width = `${w}px`;
    panel.style.left = `${Math.max(8, (pRect.width - w) / 2)}px`;
    panel.style.top = `${Math.max(8, (pRect.height - h) / 2)}px`;
    panel.style.right = 'auto';
    panel.style.bottom = 'auto';
}

/**
 * Initialise le déplacement à la souris (Draggable) du panneau Profil en long
 */
function _initProfilLongDraggable() {
    const panel = document.getElementById('panel-profil-long');
    const handle = document.getElementById('profil-long-drag-handle');
    if (!panel || !handle || panel._draggableInitDone) return;

    panel._draggableInitDone = true;
    let startX, startY, origX, origY, origW;

    handle.addEventListener('mousedown', (e) => {
        if (e.target.closest('button') || e.target.closest('input') || e.target.closest('.btn-close-profil')) return;
        e.preventDefault();
        // Position VISUELLE réelle + largeur figée : le panneau est
        // ancré left+right (largeur = dock) ; sans width explicite,
        // right:auto provoquait un shrink-to-fit après le 1er drag.
        const parent = panel.offsetParent || document.body;
        const pRect = parent.getBoundingClientRect();
        const rect = panel.getBoundingClientRect();
        startX = e.clientX;
        startY = e.clientY;
        origX = rect.left - pRect.left + (parent.scrollLeft || 0);
        origY = rect.top - pRect.top + (parent.scrollTop || 0);
        origW = panel.offsetWidth;
        panel.style.width = `${origW}px`;

        // Bornage : le panneau ne doit jamais sortir du workspace
        // (overflow:hidden rognait le bouton fermer hors limites).
        const maxX = pRect.width - rect.width;
        const maxY = pRect.height - rect.height;
        const clampX = (v) => Math.min(Math.max(v, Math.min(0, maxX)), Math.max(0, maxX));
        const clampY = (v) => Math.min(Math.max(v, Math.min(0, maxY)), Math.max(0, maxY));

        const onMouseMove = (ev) => {
            panel._userPositionned = true;
            const dx = ev.clientX - startX;
            const dy = ev.clientY - startY;
            panel.style.left = `${clampX(origX + dx)}px`;
            panel.style.top = `${clampY(origY + dy)}px`;
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

// ============================================================
// COUCHE D'ANOMALIES SUR LA CARTE (à la sortie du profil)
// Affiche le tracé + marqueurs par type d'anomalie, zoom flagrant.
// Persiste au pan/zoom ; retirée sur « Quitter » (clic droit) ou
// création d'un nouveau profil. Menu clic-droit
// (enregistrer / presse-papier / quitter).
// ============================================================

/**
 * Construit l'icône Leaflet d'un marqueur d'anomalie : forme/couleur par
 * type, teinte par sévérité.
 */
function _iconeNoeudAnomaliesProfil(liste, taille) {
    // Badges empilés en colonne, superposés, ancrés en bas sur le regard.
    // La taille suit le zoom (recalcul au zoomend) : les badges grossissent
    // et rétrécissent avec la carte comme les autres ouvrages.
    const t = taille || 18;
    const pas = Math.round(t * 0.66); // chevauchement vertical des badges
    const badges = liste.map((a, i) => {
        const couleur = _couleurSeverite(a.severite);
        const icone = _ICONE_TYPE_ANOMALIE[a.type] || 'fa-exclamation';
        const marge = i === 0 ? '0' : `-${Math.round(t * 0.34)}px`;
        return `<div style="width:${t}px;height:${t}px;border-radius:50%;background:rgba(15,23,42,0.92);border:${Math.max(1, Math.round(t / 12))}px solid ${couleur};display:flex;align-items:center;justify-content:center;box-shadow:0 0 6px ${couleur}77;margin-top:${marge};"><i class="fas ${icone}" style="color:${couleur};font-size:${Math.round(t / 2)}px;"></i></div>`;
    }).join('');
    const h = t + Math.max(0, liste.length - 1) * pas + 2;
    const w = t + 8;
    return L.divIcon({
        className: 'anomalie-profil-marker',
        html: `<div style="display:flex;flex-direction:column;align-items:center;">${badges}</div>`,
        iconSize: [w, h],
        iconAnchor: [Math.round(w / 2), h]
    });
}

/** Taille des badges d'anomalie selon le zoom courant (12→30 px). */
function _tailleBadgeAnomalie(zoom) {
    return Math.min(30, Math.max(12, Math.round(18 * Math.pow(2, (zoom - 15) / 4))));
}
/** Rayon des points de regard selon le zoom (4→9 px). */
function _rayonPointAnomalie(zoom) {
    return Math.min(9, Math.max(4, Math.round(2 + zoom * 0.28)));
}
/** Ré-applique tailles et rayons après un changement de zoom. */
function _adapterBadgesAnomaliesProfil(map, group) {
    const z = map.getZoom();
    const t = _tailleBadgeAnomalie(z);
    const r = _rayonPointAnomalie(z);
    group.eachLayer(function (l) {
        if (l._anomaliesListe) l.setIcon(_iconeNoeudAnomaliesProfil(l._anomaliesListe, t));
        if (l._noeudAnomalie) l.setRadius(r);
    });
}

/**
 * Affiche sur la carte le tracé du profil et ses anomalies (couche persistante).
 */
function _afficherAnomaliesSurCarte(data) {
    const map = _getCarte();
    if (!map || !data || !data.segments) return;
    _retirerAnomaliesProfil();

    // Pane dédié au premier plan (au-dessus des résultats de simulation)
    if (!map.getPane('anomaliesProfilPane')) {
        const p = map.createPane('anomaliesProfilPane');
        p.style.zIndex = 800;
    }

    const group = L.layerGroup();
    const latlngs = [];
    const noeuds = [];
    const anomalies = [];

    data.segments.forEach(s => {
        // Coordonnées fournies par l'API (fiables, indépendantes de l'état
        // des couches physiques) ; repli sur la recherche dans les couches.
        const ll = (s.lat != null && s.lng != null)
            ? L.latLng(s.lat, s.lng)
            : _trouverCoordonneesRegard(s.node_id);
        if (!ll) return;
        latlngs.push(ll);
        const an = s.anomalies || [];
        let sevMax = null;
        an.forEach(a => {
            if (_rangSeverite(a.severite) > _rangSeverite(sevMax)) sevMax = a.severite;
        });
        noeuds.push({ ll: ll, id: s.node_id, sev: sevMax });
        if (an.length) {
            // Un marqueur par nœud : ses anomalies sont empilées en colonne
            // (superposées) dans l'icône — pas de décalage géographique.
            anomalies.push({ ll: ll, node: s.node_id, anList: an });
        }
    });

    if (!latlngs.length) return;

    // Tronçons du profil (trait fin pointillé)
    if (latlngs.length >= 2) {
        L.polyline(latlngs, {
            color: '#f59e0b', weight: 4, opacity: 0.7,
            dashArray: '6, 6', pane: 'anomaliesProfilPane'
        }).addTo(group);
    }

    // Regards du profil (point coloré par la pire anomalie du nœud)
    const _rInit = _rayonPointAnomalie(map.getZoom());
    noeuds.forEach(n => {
        const cm = L.circleMarker(n.ll, {
            radius: _rInit, color: '#0f172a', weight: 2,
            fillColor: n.sev ? _couleurSeverite(n.sev) : '#94a3b8',
            fillOpacity: 0.95, pane: 'anomaliesProfilPane'
        }).bindTooltip(`<b>Regard ${n.id}</b>`, { direction: 'top' });
        cm._noeudAnomalie = true;
        cm.addTo(group);
    });

    // Marqueurs d'anomalies : un marqueur par nœud, badges empilés en
    // colonne superposée (type + sévérité), ancrés sur le regard. La taille
    // suit le zoom ; l'infobulle ne liste que les types d'anomalies.
    const _tInit = _tailleBadgeAnomalie(map.getZoom());
    anomalies.forEach(an => {
        const mk = L.marker(an.ll, {
            icon: _iconeNoeudAnomaliesProfil(an.anList, _tInit),
            pane: 'anomaliesProfilPane'
        }).bindTooltip(
            `<b>Regard ${an.node}</b><br>` + an.anList.map(a => _libelleTypeAnomalie(a.type)).join('<br>'),
            { direction: 'top' }
        );
        mk._anomaliesListe = an.anList;
        mk.addTo(group);
    });

    group.addTo(map);

    // Zoom flagrant sur l'ensemble du profil — agrandissement maximal
    // (tuiles natives z19) tout en gardant tout le tronçon visible.
    const bounds = L.latLngBounds(latlngs);
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 19 });

    // Badges et points réactifs au zoom (taille recalculée à chaque zoomend)
    const _onZoom = function () { _adapterBadgesAnomaliesProfil(map, group); };
    map.on('zoomend', _onZoom);

    // --- Persistance : la couche reste affichée au pan/zoom ---
    // Elle ne disparaît que sur action explicite : « Quitter » du menu
    // contextuel ou création d'un nouveau profil.

    // --- Menu contextuel clic-droit ---
    const _onCtx = function (e) {
        const st = window._anomaliesProfil;
        if (!st) return;
        if (e && e.originalEvent) e.originalEvent.preventDefault();
        _afficherMenuAnomaliesProfil(e && e.originalEvent);
    };
    map.on('contextmenu', _onCtx);

    // Clic gauche : referme juste le menu (la couche reste)
    const _onClick = function () { _menuAnomaliesProfilHide(); };
    map.on('click', _onClick);

    window._anomaliesProfil = {
        layer: group, data: data, onCtx: _onCtx, onClick: _onClick, onZoom: _onZoom
    };
}

/**
 * Retire la couche d'anomalies et tous ses écouteurs.
 */
function _retirerAnomaliesProfil() {
    const st = window._anomaliesProfil;
    const map = _getCarte();
    if (!st) return;
    if (map) {
        if (st.layer) map.removeLayer(st.layer);
        if (st.onCtx) map.off('contextmenu', st.onCtx);
        if (st.onClick) map.off('click', st.onClick);
        if (st.onZoom) map.off('zoomend', st.onZoom);
    }
    _menuAnomaliesProfilHide();
    window._anomaliesProfil = null;
}

/**
 * Menu contextuel (clic droit) : enregistrer / presse-papier / quitter.
 */
function _afficherMenuAnomaliesProfil(domEvent) {
    _menuAnomaliesProfilHide();
    if (!domEvent) return;
    const x = domEvent.clientX, y = domEvent.clientY;

    const menu = document.createElement('div');
    menu.className = 'menu-anomalies-profil';
    menu.style.cssText = 'position:fixed;z-index:9999;background:rgba(15,23,42,0.97);'
        + 'border:1px solid rgba(56,189,248,0.45);border-radius:10px;padding:5px;'
        + 'min-width:190px;box-shadow:0 10px 30px rgba(0,0,0,0.55);'
        + 'font-family:"Plus Jakarta Sans",sans-serif;';

    const _btn = (act, label) => {
        const b = document.createElement('button');
        b.type = 'button';
        b.dataset.act = act;
        b.textContent = label;
        b.style.cssText = 'display:block;width:100%;text-align:left;background:none;border:none;'
            + 'color:#e2e8f0;padding:7px 10px;border-radius:6px;cursor:pointer;font-size:0.8rem;';
        b.onmouseenter = () => { b.style.background = 'rgba(56,189,248,0.15)'; };
        b.onmouseleave = () => { b.style.background = 'none'; };
        b.onclick = (ev) => { ev.stopPropagation(); _actionMenuAnomalies(act, b); };
        return b;
    };

    // Case à cocher « Infobulles » quand une simulation est affichée :
    // même bascule que le menu contextuel de la carte.
    if (window._simCtxActif && window._ajouterItemInfobullesSim) {
        window._ajouterItemInfobullesSim(menu);
        const sep = document.createElement('div');
        sep.style.cssText = 'height:1px;background:rgba(148,163,184,0.25);margin:4px 6px;';
        menu.appendChild(sep);
    }

    menu.appendChild(_btn('enregistrer', '💾 Enregistrer (.txt)'));
    menu.appendChild(_btn('copier', '📋 Copier (presse-papier)'));
    menu.appendChild(_btn('quitter', '✖ Quitter'));

    // Position calée dans le viewport
    menu.style.left = Math.max(4, Math.min(x + 6, window.innerWidth - 200)) + 'px';
    menu.style.top = Math.max(4, Math.min(y + 6, window.innerHeight - 140)) + 'px';
    document.body.appendChild(menu);

    if (window._anomaliesProfil) window._anomaliesProfil.menu = menu;

    // Fermeture au clic hors menu / Échap
    setTimeout(() => {
        const _hide = (ev) => {
            if (menu.contains(ev.target)) return;
            _menuAnomaliesProfilHide();
            document.removeEventListener('click', _hide, true);
        };
        document.addEventListener('click', _hide, true);
        const _esc = (ev) => { if (ev.key === 'Escape') _menuAnomaliesProfilHide(); };
        document.addEventListener('keydown', _esc);
        menu._escHandler = _esc;
    }, 0);
}

function _menuAnomaliesProfilHide() {
    const st = window._anomaliesProfil;
    if (st && st.menu) {
        if (st.menu._escHandler) document.removeEventListener('keydown', st.menu._escHandler);
        st.menu.remove();
        st.menu = null;
    } else {
        document.querySelectorAll('.menu-anomalies-profil').forEach(m => m.remove());
    }
}

/**
 * Actions du menu contextuel.
 */
function _actionMenuAnomalies(act, btn) {
    const st = window._anomaliesProfil;
    if (!st || !st.data) { _menuAnomaliesProfilHide(); return; }

    if (act === 'quitter') {
        _retirerAnomaliesProfil();
        return;
    }

    const txt = _rapportAnomaliesTexte(st.data);

    if (act === 'enregistrer') {
        const blob = new Blob([txt], { type: 'text/plain;charset=utf-8' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `anomalies_profil_${st.data.node_amont || 'amont'}_${st.data.node_aval || 'aval'}.txt`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 5000);
        _menuAnomaliesProfilHide();
        return;
    }

    if (act === 'copier') {
        const _ok = () => {
            if (btn) {
                btn.textContent = '✓ Copié !';
                setTimeout(() => { btn.textContent = '📋 Copier (presse-papier)'; }, 1500);
            }
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(txt).then(_ok).catch(() => _copierFallback(txt, _ok));
        } else {
            _copierFallback(txt, _ok);
        }
    }
}

function _copierFallback(texte, cb) {
    try {
        const ta = document.createElement('textarea');
        ta.value = texte;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        ta.remove();
        if (cb) cb();
    } catch (e) { /* presse-papier indisponible */ }
}

/**
 * Rapport texte des anomalies du profil (export .txt / presse-papier).
 */
function _rapportAnomaliesTexte(data) {
    const lignes = [];
    lignes.push('PROFIL EN LONG — ANOMALIES DÉTECTÉES');
    lignes.push('================================');
    lignes.push(`Profil      : ${data.node_amont || '?'} → ${data.node_aval || '?'}`);
    lignes.push(`Tronçons    : ${data.nb_troncons || '?'} | Longueur : ${data.longueur_totale_m || '?'} m`);
    const alt = data.altimetrie || {};
    lignes.push(`Altimétrie  : ${alt.label || 'non tracée'}${alt.source ? ` (${alt.source})` : ''}`);
    const sa = data.synthese_anomalies || {};
    lignes.push(`Anomalies   : ${sa.total || 0} (dont ${sa.forts || 0} forte(s), ${sa.moyens || 0} moyenne(s))`);
    lignes.push(`Date        : ${new Date().toLocaleString('fr-FR')}`);
    lignes.push('');

    const parNoeud = {};
    (data.segments || []).forEach(s => {
        (s.anomalies || []).forEach(a => {
            (parNoeud[s.node_id] = parNoeud[s.node_id] || []).push(a);
        });
    });

    const distParNoeud = {};
    (data.segments || []).forEach(s => { distParNoeud[String(s.node_id)] = s.distance_m || 0; });
    const noeuds = Object.keys(parNoeud).sort((a, b) => (distParNoeud[a] || 0) - (distParNoeud[b] || 0));

    noeuds.forEach(nid => {
        lignes.push(`■ Regard ${nid} (${Math.round(distParNoeud[nid] || 0)} m)`);
        parNoeud[nid].forEach(a => {
            const val = a.valeur_m != null ? ` (${a.valeur_m} m)` : (a.valeur_ms != null ? ` (${a.valeur_ms} m/s)` : '');
            lignes.push(`   [${_SEV_ANOMALIE_LABELS[a.severite] || a.severite}] ${_libelleTypeAnomalie(a.type)}${val}`);
            if (a.message) lignes.push(`      ${a.message}`);
        });
        lignes.push('');
    });

    return lignes.join('\n');
}
