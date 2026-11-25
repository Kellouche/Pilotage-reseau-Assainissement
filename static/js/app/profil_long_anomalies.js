/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-24
 * Date de modification : 2026-11-24
 * Objet : Anomalies sur carte : marqueurs, badges zoom, menu contextuel, export et panneau draggable — extrait de profil_long.js (découpage 600 lignes)
 * ================================================================================
 */

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
