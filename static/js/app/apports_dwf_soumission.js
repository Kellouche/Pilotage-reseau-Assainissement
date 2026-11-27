/**
 * Projet : DrainPilot 5.2 — Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-27 | Date de modification : 2026-11-27
 * Objet : Soumission du formulaire DWF et selection de noeud sur la carte (extrait de static/js/app/apports_dwf.js)
 */

window.soumettreFormulaireDwf = async function() {
    if (!DWF.peutEcrire || DWF.chargement) return;
    const btn = document.getElementById('btn-dwf-soumettre');

    const node = (document.getElementById('dwf-f-node').value || '').trim();
    const nature = document.getElementById('dwf-f-nature').value;
    const profile_key = document.getElementById('dwf-f-profil').value;
    const source = (document.getElementById('dwf-f-source').value || '').trim() || null;
    const observations = (document.getElementById('dwf-f-observations').value || '').trim() || null;
    const actif = document.getElementById('dwf-f-actif').checked;

    // Validation côté client alignée sur ApportDwfCreate (l'API reste l'autorité)
    if (!node) { afficherMessageFormDwf('Le regard (node_id) est obligatoire.', false); return; }

    const body = { node_id: node, nature, profile_key, actif, source, observations };
    if (DWF.projectId) body.project_id = DWF.projectId;

    if (DWF.mode === 'debit') {
        const v = parseFloat(document.getElementById('dwf-f-debit').value);
        if (isNaN(v) || v <= 0 || v > 100) {
            afficherMessageFormDwf('Débit moyen invalide : valeur strictement positive, ≤ 100 m³/s.', false); return;
        }
        body.mode_determination = 'debit';
        body.debit_moyen_m3s = v;
    } else {
        const eh = parseFloat(document.getElementById('dwf-f-eh').value);
        const ds = parseFloat(document.getElementById('dwf-f-debitspec').value);
        if (isNaN(eh) || eh <= 0) { afficherMessageFormDwf('Équivalent-habitant invalide (strictement positif).', false); return; }
        if (isNaN(ds) || ds <= 0 || ds > 5000) { afficherMessageFormDwf('Débit spécifique invalide : (0, 5000] L/EH/j.', false); return; }
        body.mode_determination = 'eh';
        body.eh = eh;
        body.debit_specifique_l_hab_j = ds;
    }

    DWF.chargement = true;
    if (btn) { btn.disabled = true; btn.style.opacity = '0.6'; }
    masquerMessageFormDwf();
    try {
        if (DWF.editingId) {
            await dwfFetch(`/api/v1/apports/${encodeURIComponent(DWF.editingId)}`, {
                method: 'PUT', body: JSON.stringify(body) });
        } else {
            await dwfFetch('/api/v1/apports', {
                method: 'POST', body: JSON.stringify(body) });
        }
        DWF.chargement = false;
        if (btn) { btn.disabled = false; btn.style.opacity = '1'; }
        retourListeDwf();
        await actualiserDwf();
        DWF.statut(DWF.editingId ? 'Apport modifié.' : 'Apport créé.', 'ok');
    } catch (e) {
        DWF.chargement = false;
        if (btn) { btn.disabled = false; btn.style.opacity = '1'; }
        let msg = e.message || 'Erreur inconnue';
        if (e.status === 422) msg = 'Données refusées par le serveur : ' + msg;
        else if (e.status === 403) msg = 'Action réservée aux ingénieurs.';
        else if (e.status === 404) msg = 'Projet ou apport introuvable — rechargez la page.';
        afficherMessageFormDwf(msg, false);
        DWF.statut(msg, 'err');
    }
};

// Empêche la double soumission au clavier (Entrée dans un champ)
document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('dwf-vue-form');
    if (form) {
        form.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && e.target.tagName !== 'TEXTAREA') {
                e.preventDefault();
                soumettreFormulaireDwf();
            }
        });
    }
});

// ---------------------------------------------------------------------------
// Sélection interactive de regard sur la carte
// ---------------------------------------------------------------------------

window._dwfPickModeActive = false;
window._dwfSuspendedModals = [];
let _dwfMapClickListener = null;
let _dwfPopupOpenListener = null;
let _dwfEscKeyListener = null;

function _creerOuAfficherBanniereDwf() {
    let banner = document.getElementById('dwf-selection-banner');
    if (!banner) {
        banner = document.createElement('div');
        banner.id = 'dwf-selection-banner';
        banner.style.cssText = `
            position: fixed;
            top: 68px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 3500;
            background: rgba(15, 23, 42, 0.95);
            backdrop-filter: blur(14px);
            border: 2px solid #38bdf8;
            border-radius: 9999px;
            padding: 9px 20px;
            color: #f8fafc;
            display: flex;
            align-items: center;
            gap: 14px;
            box-shadow: 0 16px 40px rgba(0, 0, 0, 0.7);
            font-size: 0.84rem;
            animation: fadeInScale 0.2s ease-out;
            user-select: none;
        `;
        banner.innerHTML = `
            <div style="width: 26px; height: 26px; border-radius: 50%; background: rgba(56, 189, 248, 0.2); border: 1px solid #38bdf8; display: flex; align-items: center; justify-content: center; color: #38bdf8;">
                <i class="fas fa-crosshairs fa-spin" style="font-size: 13px;"></i>
            </div>
            <span style="font-weight: 700;">Cliquez sur un regard sur la carte (directement ou à proximité)</span>
            <button onclick="dwfAnnulerSelectionCarte()" style="background: rgba(239, 68, 68, 0.2); border: 1px solid #ef4444; color: #fca5a5; padding: 4px 12px; border-radius: 20px; font-size: 0.76rem; font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 5px; transition: all 0.15s;" onmouseover="this.style.background='rgba(239,68,68,0.35)'" onmouseout="this.style.background='rgba(239,68,68,0.2)'">
                <i class="fas fa-times"></i> Annuler
            </button>
        `;
        document.body.appendChild(banner);
    } else {
        banner.style.display = 'flex';
    }
}

function _masquerBanniereDwf() {
    const banner = document.getElementById('dwf-selection-banner');
    if (banner) {
        banner.style.display = 'none';
    }
}

function _nettoyerEcouteursSelectionDwf() {
    const cMap = window.carte || window.map;
    if (cMap && _dwfMapClickListener) {
        cMap.off('click', _dwfMapClickListener);
        _dwfMapClickListener = null;
    }
    if (cMap && _dwfPopupOpenListener) {
        cMap.off('popupopen', _dwfPopupOpenListener);
        _dwfPopupOpenListener = null;
    }
    if (_dwfEscKeyListener) {
        window.removeEventListener('keydown', _dwfEscKeyListener);
        _dwfEscKeyListener = null;
    }
}

function _trouverRegardLePlusProche(latlng, distanceMaxMetres) {
    const maxM = distanceMaxMetres || 100;
    const cMap = window.carte || window.map;
    if (!cMap || !latlng) return null;

    let meilleurNoeud = null;
    let distanceMin = maxM;

    const rawData = window._rawNetworkData;
    if (rawData && rawData.couches) {
        const types = ['regards', 'rejets', 'ouvrages', 'stations'];
        types.forEach(t => {
            const couche = rawData.couches[t];
            if (!couche || !couche.features) return;
            for (const f of couche.features) {
                if (!f.geometry || !f.geometry.coordinates) continue;
                const coords = f.geometry.coordinates;
                const fLatLng = L.latLng(coords[1], coords[0]);
                const dist = cMap.distance(latlng, fLatLng);
                if (dist < distanceMin) {
                    distanceMin = dist;
                    const p = f.properties || {};
                    const code = p.Code || p.code || p.CODE || p.id || p.ID || p.Id || p.nom || p.NOM || p.Nom || p.CODEPRR || p.NUMERO || f.id;
                    meilleurNoeud = { code: code, latlng: fLatLng, distance: dist };
                }
            }
        });
    }

    return meilleurNoeud;
}

window.dwfActiverSelectionCarte = function() {
    const modalEl = document.getElementById('modal-apports-dwf');
    const mapEl = document.getElementById('map');
    const cMap = window.carte || window.map;

    window._dwfPickModeActive = true;

    // Fermer immédiatement toute infobulle ouverte sur la carte
    if (cMap) cMap.closePopup();

    // 1. Fermer tous les menus déroulants de topbar
    ['actions-dropdown', 'topbar-bassin-dropdown', 'resources-dropdown', 'user-profile-dropdown'].forEach(id => {
        const d = document.getElementById(id);
        if (d) d.style.display = 'none';
    });

    // 2. Mémoriser et masquer TOUTES les modales actuellement visibles (y compris modal-simulation, modal-simulations-bassin, etc.)
    window._dwfSuspendedModals = [];
    document.querySelectorAll('div[id^="modal-"]').forEach(m => {
        const comp = window.getComputedStyle(m);
        if (comp.display !== 'none' && comp.visibility !== 'hidden' && comp.opacity !== '0') {
            window._dwfSuspendedModals.push({
                id: m.id,
                prevDisplay: m.style.display || comp.display
            });
            m.style.setProperty('display', 'none', 'important');
        }
    });

    // S'assurer que modal-apports-dwf est masqué pour supprimer l'effet flou et libérer l'accès à la carte
    if (modalEl) {
        modalEl.style.setProperty('display', 'none', 'important');
        modalEl.style.opacity = '1';
        modalEl.style.pointerEvents = 'auto';
    }

    // 3. Afficher la bannière flottante de sélection
    _creerOuAfficherBanniereDwf();

    // 4. Curseur crosshair
    if (mapEl) {
        mapEl.style.cursor = 'crosshair';
    }

    // 5. Intercepteur global de popup Leaflet pour empêcher toute ouverture d'infobulle (débordement, etc.)
    if (cMap && !_dwfPopupOpenListener) {
        _dwfPopupOpenListener = function(e) {
            if (window._dwfPickModeActive) {
                try { cMap.closePopup(); } catch(_) {}
                if (e && e.popup && e.popup._source && typeof e.popup._source.closePopup === 'function') {
                    try { e.popup._source.closePopup(); } catch(_) {}
                }
            }
        };
        cMap.on('popupopen', _dwfPopupOpenListener);
    }

    // 6. Écouteur de clic sur le fond de carte (recherche de proximité)
    if (cMap && !_dwfMapClickListener) {
        _dwfMapClickListener = function(e) {
            if (!window._dwfPickModeActive) return;
            const nearest = _trouverRegardLePlusProche(e.latlng, 100);
            if (nearest && nearest.code) {
                window.dwfAppliquerNoeudSelectionne(nearest.code, nearest.latlng);
            } else {
                if (typeof window.afficherNotification === 'function') {
                    window.afficherNotification("Aucun regard à proximité immédiate de ce clic. Cliquez plus près d'un nœud.", "warning");
                }
            }
        };
        cMap.on('click', _dwfMapClickListener);
    }

    // 7. Touche Échap pour annuler
    if (!_dwfEscKeyListener) {
        _dwfEscKeyListener = function(ev) {
            if (ev.key === 'Escape' && window._dwfPickModeActive) {
                window.dwfAnnulerSelectionCarte();
            }
        };
        window.addEventListener('keydown', _dwfEscKeyListener);
    }

    if (typeof window.afficherNotification === 'function') {
        window.afficherNotification('Mode sélection DWF actif : cliquez sur un regard sur la carte.', 'info');
    }
};

window.dwfAnnulerSelectionCarte = function() {
    window._dwfPickModeActive = false;
    _nettoyerEcouteursSelectionDwf();
    _masquerBanniereDwf();

    const mapEl = document.getElementById('map');
    if (mapEl) mapEl.style.cursor = '';

    const cMap = window.carte || window.map;
    if (cMap) cMap.closePopup();

    const modalEl = document.getElementById('modal-apports-dwf');
    if (modalEl) {
        modalEl.style.setProperty('display', 'flex', 'important');
        modalEl.style.opacity = '1';
        modalEl.style.pointerEvents = 'auto';
    }
};

window.dwfAppliquerNoeudSelectionne = function(nodeId, latlng) {
    window._dwfPickModeActive = false;
    _nettoyerEcouteursSelectionDwf();
    _masquerBanniereDwf();

    const mapEl = document.getElementById('map');
    if (mapEl) mapEl.style.cursor = '';

    const cMap = window.carte || window.map;
    if (cMap) cMap.closePopup();

    const modalEl = document.getElementById('modal-apports-dwf');
    const inputNode = document.getElementById('dwf-f-node');

    if (modalEl) {
        modalEl.style.setProperty('display', 'flex', 'important');
        modalEl.style.opacity = '1';
        modalEl.style.pointerEvents = 'auto';
    }

    if (inputNode && nodeId) {
        inputNode.value = String(nodeId).trim();
        inputNode.dispatchEvent(new Event('input', { bubbles: true }));
        inputNode.focus();

        // Accentuation visuelle verte pour confirmer la prise en compte
        inputNode.style.borderColor = '#10b981';
        inputNode.style.boxShadow = '0 0 0 3px rgba(16, 185, 129, 0.35)';
        setTimeout(() => {
            inputNode.style.borderColor = 'rgba(255,255,255,0.15)';
            inputNode.style.boxShadow = 'none';
        }, 1800);
    }

    if (typeof window.afficherNotification === 'function') {
        window.afficherNotification(`Regard N° ${nodeId} sélectionné pour l'apport DWF.`, 'success');
    }
};

window.ouvrirAjoutDwfPourNoeud = function(nodeId) {
    if (typeof window.ouvrirModalApportsDwf === 'function') {
        window.ouvrirModalApportsDwf();
    }
    setTimeout(() => {
        if (typeof window.basculerFormulaireDwf === 'function') {
            window.basculerFormulaireDwf(true);
        }
        const inputNode = document.getElementById('dwf-f-node');
        if (inputNode && nodeId) {
            inputNode.value = String(nodeId).trim();
            inputNode.dispatchEvent(new Event('input', { bubbles: true }));
        }
        const inputDebit = document.getElementById('dwf-f-debit');
        if (inputDebit) inputDebit.focus();
    }, 200);
};
