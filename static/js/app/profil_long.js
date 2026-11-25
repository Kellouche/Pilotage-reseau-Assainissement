/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-24
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
 * Si des cotes suspectes non validées sont présentes sur le chemin, suspend le tracé
 * et affiche l'écran de certification/validation pour l'hydraulicien.
 */
function chargerProfilLong(nodeAmont, nodeAval, forcerBrut = false) {
    const panel = document.getElementById('panel-profil-long');
    const overlay = document.getElementById('profil-loading-overlay');
    if (overlay) overlay.style.display = 'flex';

    let url = `/api/v1/simulations/profil-en-long?node_amont=${encodeURIComponent(nodeAmont)}&node_aval=${encodeURIComponent(nodeAval)}`;
    if (forcerBrut) {
        url += '&forcer_brut=true';
    }

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

            // Contrôle Human-in-the-Loop : cotes suspectes nécessitant validation
            if (data.status === 'cotes_suspectes_a_valider') {
                if (panel) panel.style.display = 'flex';
                if (typeof _initProfilLongDraggable === 'function') {
                    _initProfilLongDraggable();
                }
                afficherEcranValidationCotesProfil(data);
                _centrerPanelProfil();
                return;
            }

            // Réactiver la vue graphique
            const valView = document.getElementById('profil-validation-cotes-view');
            const chartWrapper = document.getElementById('profil-chart-wrapper');
            if (valView) valView.style.display = 'none';
            if (chartWrapper) chartWrapper.style.display = 'block';

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
 * Affiche l'écran de validation interactive des cotes suspectes (Human-in-the-Loop)
 */
function afficherEcranValidationCotesProfil(data) {
    window.profilLongState._pendingValidationData = data;
    const valView = document.getElementById('profil-validation-cotes-view');
    const chartWrapper = document.getElementById('profil-chart-wrapper');
    const alertesContainer = document.getElementById('profil-alertes-container');
    const msgElem = document.getElementById('profil-validation-cotes-msg');
    const tbody = document.getElementById('profil-validation-cotes-tbody');

    if (chartWrapper) chartWrapper.style.display = 'none';
    if (alertesContainer) alertesContainer.style.display = 'none';
    if (valView) valView.style.display = 'block';

    const panel = document.getElementById('panel-profil-long');
    if (panel) {
        panel.style.height = 'auto';
        panel.style.maxHeight = '85vh';
    }

    if (msgElem && data.message) {
        msgElem.textContent = data.message;
    }

    if (tbody) {
        tbody.innerHTML = '';
        const suspectes = data.cotes_suspectes || [];
        suspectes.forEach((cs, idx) => {
            const tr = document.createElement('tr');
            tr.style.cssText = 'border-bottom: 1px solid rgba(255, 255, 255, 0.05); background: ' + (idx % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'transparent');
            tr.innerHTML = `
                <td style="padding: 10px 12px; font-weight: 700; color: #f8fafc;">
                    <span style="background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.4); color: #38bdf8; border-radius: 6px; padding: 2px 8px; font-size: 0.8rem;">
                        Regard ${cs.node_id}
                    </span>
                </td>
                <td style="padding: 10px 12px; color: #ef4444; font-weight: 700; font-family: monospace;">
                    ${cs.valeur_brute} m
                </td>
                <td style="padding: 10px 12px; color: #cbd5e1; font-size: 0.82rem;">
                    ${cs.motif_suspicion || 'Profondeur excessive'}
                </td>
                <td style="padding: 10px 12px;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <input type="number" step="0.01" class="input-cote-validee-val" data-node="${cs.node_id}" data-champ="${cs.champ || 'profondeur'}" value="${cs.valeur_suggeree !== null ? cs.valeur_suggeree : cs.valeur_brute}" style="width: 90px; background: rgba(15, 23, 42, 0.9); border: 1.5px solid #0284c7; color: #38bdf8; font-weight: 700; font-family: monospace; border-radius: 6px; padding: 4px 8px; font-size: 0.85rem; text-align: right;">
                        <span style="color: #64748b; font-size: 0.8rem;">m</span>
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        });
    }
}

/**
 * Valide les cotes suspectes saisies et déclenche le tracé certifié du profil
 */
function soumettreValidationCotesProfil() {
    const data = window.profilLongState._pendingValidationData;
    if (!data) return;

    const inputs = document.querySelectorAll('.input-cote-validee-val');
    const validations = [];
    inputs.forEach(inp => {
        const node_id = inp.getAttribute('data-node');
        const champ = inp.getAttribute('data-champ') || 'profondeur';
        const val = parseFloat(inp.value);
        if (node_id && !isNaN(val)) {
            validations.push({
                node_id: node_id,
                champ: champ,
                action: 'valider',
                valeur_validee: val,
                commentaire: `Validé par l'hydraulicien lors du tracé profil (${val} m)`
            });
        }
    });

    if (validations.length === 0) return;

    const overlay = document.getElementById('profil-loading-overlay');
    if (overlay) overlay.style.display = 'flex';

    fetch('/api/v1/simulations/cotes-suspectes/valider', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ validations: validations })
    })
    .then(r => {
        if (!r.ok) throw new Error(`Erreur validation (${r.status})`);
        return r.json();
    })
    .then(res => {
        if (typeof window.dialogueAlerte === 'function') {
            window.dialogueAlerte(`${validations.length} cote(s) validée(s) et certifiée(s). Élaboration du profil...`, 'succes');
        }
        chargerProfilLong(data.node_amont, data.node_aval, false);
    })
    .catch(err => {
        if (overlay) overlay.style.display = 'none';
        console.error("Erreur validation cotes:", err);
        if (typeof window.dialogueAlerte === 'function') {
            window.dialogueAlerte(`Échec de la validation : ${err.message}`, 'erreur');
        }
    });
}

/**
 * Force le tracé du profil avec les cotes brutes non validées
 */
function forcerTraceProfilBrut() {
    const data = window.profilLongState._pendingValidationData;
    if (!data) return;
    chargerProfilLong(data.node_amont, data.node_aval, true);
}
