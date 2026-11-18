/**
 * Extraction par pochoir (SHP.md) — outil SIG thématique.
 *
 * Deux modes de définition de la zone :
 *  - 'bassin' : clic sur un polygone de bassin versant d'une couche SIG
 *    satellite importée (features GeoJSON chargées dans AUX.couches)
 *  - 'dessin' : tracé du polygone point par point (clic = sommet,
 *    double-clic ou clic proche du 1er point = fermeture)
 *
 * Après délimitation → modale nommage/sources → POST
 * /api/v1/projets/{pid}/extraction-pochoir → zip {nom}_*.shp + {nom}.gpkg
 * + manifeste.json, téléchargé via /api/v1/artifacts/download.
 */
(function () {
    'use strict';

    const P = {
        mode: null,          // 'bassin' | 'dessin' | null
        points: [],          // latlng[] du dessin en cours
        markers: [],
        polyline: null,
        stencilLayer: null,  // aperçu polygone pochoir
        stencilGeoJSON: null,// géométrie retenue (Polygon/MultiPolygon)
        handlers: {},        // refs pour off()
        statutTimeout: null,
    };

    function carte() { return window.carte || window.map || null; }
    function $id(x) { return document.getElementById(x); }

    async function resoudreProjectId() {
        const aux = window.AUX_LAYERS;
        if (aux && aux.projectId) return aux.projectId;
        try {
            const d = await (await fetch('/api/v1/network/datasets?_t=' + Date.now(),
                { credentials: 'include' })).json();
            return d && d.active_project && d.active_project.id || null;
        } catch (e) { return null; }
    }

    function authHeaders() {
        const t = localStorage.getItem('swmm_access_token');
        return t ? { 'Authorization': 'Bearer ' + t } : {};
    }

    // ------------------------------------------------------------------
    // Menu toolbar
    // ------------------------------------------------------------------
    window.basculerMenuPochoir = function (ev) {
        if (ev) ev.stopPropagation();
        const m = $id('menu-pochoir');
        if (!m) return;
        const ouvrir = m.style.display === 'none';
        m.style.display = ouvrir ? 'flex' : 'none';
        if (ouvrir && !P._docClose) {
            P._docClose = true;
            document.addEventListener('click', _fermerMenuDoc);
        }
    };

    function _fermerMenuDoc(e) {
        const menu = $id('menu-pochoir');
        const btn = $id('btn-pochoir');
        if (menu && menu.style.display !== 'none' &&
            !menu.contains(e.target) && !(btn && btn.contains(e.target))) {
            menu.style.display = 'none';
        }
    }

    // ------------------------------------------------------------------
    // Modes
    // ------------------------------------------------------------------
    window.choisirModePochoir = function (mode) {
        if (P.mode === mode) { quitterModePochoir(); return; }
        quitterModePochoir();
        const menu = $id('menu-pochoir');
        if (menu) menu.style.display = 'none';
        // Nouvelle zone : invalider tout stencil précédent
        if (P.stencilLayer && carte() && carte().hasLayer(P.stencilLayer)) {
            carte().removeLayer(P.stencilLayer);
        }
        P.stencilLayer = null;
        P.stencilGeoJSON = null;
        const m = carte();
        if (!m) return;
        P.mode = mode;
        const btn = $id('btn-pochoir');
        if (btn) btn.classList.add('active');

        if (mode === 'bassin') {
            _infoCarte('Mode pochoir — cliquez sur un bassin versant d\'une couche SIG affichée (Échap pour quitter).');
            P.handlers.click = e => _surClicBassin(e);
            m.on('click', P.handlers.click);
            m.getContainer().style.cursor = 'crosshair';
            if (m.dragging) m.dragging.disable();
        } else {
            _infoCarte('Mode pochoir — cliquez pour poser les sommets, double-clic (ou clic sur le 1er point) pour fermer (Échap pour annuler).');
            P.handlers.click = e => _surClicDessin(e);
            P.handlers.dblclick = e => { L.DomEvent.stop(e); _fermerDessin(); };
            m.on('click', P.handlers.click);
            m.on('dblclick', P.handlers.dblclick);
            m.getContainer().style.cursor = 'crosshair';
            if (m.dragging) m.dragging.disable();
        }
        // Échap : quitter le mode
        P.handlers.key = e => { if (e.key === 'Escape') quitterModePochoir(); };
        document.addEventListener('keydown', P.handlers.key);
    };

    function _infoCarte(msg) {
        const el = $id('cluster-status');
        if (el) el.innerHTML = `<b>Pochoir</b><br>${msg}`;
    }

    window.quitterModePochoir = function () {
        const m = carte();
        if (m) {
            if (P.handlers.click) m.off('click', P.handlers.click);
            if (P.handlers.dblclick) m.off('dblclick', P.handlers.dblclick);
            if (m.dragging) m.dragging.enable();
            m.getContainer().style.cursor = '';
        }
        if (P.handlers.key) document.removeEventListener('keydown', P.handlers.key);
        _effacerDessin();
        P.mode = null;
        const btn = $id('btn-pochoir');
        if (btn) btn.classList.remove('active');
        const el = $id('cluster-status');
        if (el && el.innerHTML.includes('Pochoir')) el.innerHTML = '';
    };

    // ------------------------------------------------------------------
    // Hit-test polygone (point dans polygone GeoJSON, coords [lon,lat])
    // ------------------------------------------------------------------
    function _anneauContient(ring, lng, lat) {
        let inside = false;
        for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
            const xi = ring[i][0], yi = ring[i][1];
            const xj = ring[j][0], yj = ring[j][1];
            if ((yi > lat) !== (yj > lat) &&
                lng < (xj - xi) * (lat - yi) / (yj - yi) + xi) {
                inside = !inside;
            }
        }
        return inside;
    }

    function _geomContient(geom, lng, lat) {
        if (!geom) return false;
        if (geom.type === 'Polygon') {
            const [ext, ...trous] = geom.coordinates;
            if (!_anneauContient(ext, lng, lat)) return false;
            return !trous.some(h => _anneauContient(h, lng, lat));
        }
        if (geom.type === 'MultiPolygon') {
            return geom.coordinates.some(poly =>
                _geomContient({ type: 'Polygon', coordinates: poly }, lng, lat));
        }
        return false;
    }

    /**
     * Traversée récursive des couches Leaflet : L.geoJSON ajoute un
     * FeatureGroup comme ENFANT unique du layerGroup — eachLayer seul
     * ne descend pas jusqu'aux features (d'où les « aucun bassin »).
     */
    function _parcourirFeatures(layer, cb) {
        if (!layer) return;
        if (layer.feature && layer.feature.geometry) { cb(layer); return; }
        if (layer.eachLayer) layer.eachLayer(enfant => _parcourirFeatures(enfant, cb));
    }

    /** Cherche la première feature polygone de couche auxiliaire sous le clic. */
    function _featureSousClic(latlng) {
        const aux = window.AUX_LAYERS;
        if (!aux || !aux.couches) return null;
        const lng = latlng.lng, lat = latlng.lat;
        for (const entree of Object.values(aux.couches)) {
            const groupe = entree && entree.groupe;
            if (!groupe || !groupe.eachLayer) continue;
            let trouve = null;
            _parcourirFeatures(groupe, l => {
                if (trouve) return;
                const f = l.feature;
                const g = f && f.geometry;
                if (g && (g.type === 'Polygon' || g.type === 'MultiPolygon') &&
                    _geomContient(g, lng, lat)) {
                    trouve = { feature: f, couche: entree.meta || entree };
                }
            });
            if (trouve) return trouve;
        }
        return null;
    }

    function _surClicBassin(e) {
        const hit = _featureSousClic(e.latlng);
        if (!hit) {
            if (typeof window.dialogueNotifier === 'function') {
                window.dialogueNotifier({
                    message: 'Aucun bassin versant de couche SIG sous ce point — affichez/zoomez la couche puis réessayez.',
                    type: 'info'
                });
            }
            return;
        }
        const g = hit.feature.geometry;
        P.stencilGeoJSON = { type: g.type, coordinates: g.coordinates };
        _dessinerApercuPochoir(P.stencilGeoJSON);
        quitterModePochoir();
        const props = hit.feature.properties || {};
        const nomSug = props.nom || props.NOM || props.name || props.libelle ||
            props.Nom || (hit.couche && hit.couche.nom) || '';
        _ouvrirModalPochoir(nomSug);
    }

    // ------------------------------------------------------------------
    // Dessin libre du polygone
    // ------------------------------------------------------------------
    function _surClicDessin(e) {
        // Clic proche du 1er point (≥3 pts) → fermeture
        if (P.points.length >= 3) {
            const first = P.points[0];
            if (e.latlng.distanceTo(first) < 15) { _fermerDessin(); return; }
        }
        P.points.push(e.latlng);
        const m = L.marker(e.latlng, { draggable: false, keyboard: false,
            icon: L.divIcon({ className: 'pochoir-pt', html: '●', iconSize: [10, 10], iconAnchor: [5, 5] }) })
            .addTo(carte());
        P.markers.push(m);
        if (P.points.length === 1) {
            P.polyline = L.polyline(P.points, { color: '#8b5cf6', weight: 2, dashArray: '6 4' }).addTo(carte());
        } else {
            P.polyline.setLatLngs(P.points);
        }
    }

    function _fermerDessin() {
        if (P.points.length < 3) {
            if (typeof window.dialogueNotifier === 'function') {
                window.dialogueNotifier({ message: 'Pochoir incomplet : au moins 3 points requis.', type: 'warning' });
            }
            return;
        }
        const coords = P.points.map(ll => [ll.lng, ll.lat]);
        if (coords[0][0] !== coords[coords.length - 1][0] ||
            coords[0][1] !== coords[coords.length - 1][1]) {
            coords.push(coords[0].slice());
        }
        P.stencilGeoJSON = { type: 'Polygon', coordinates: [coords] };
        _effacerDessin();
        _dessinerApercuPochoir(P.stencilGeoJSON);
        quitterModePochoir();
        _ouvrirModalPochoir('');
    }

    function _effacerDessin() {
        const m = carte();
        P.markers.forEach(mk => { try { m.removeLayer(mk); } catch (e) {} });
        P.markers = [];
        if (P.polyline && m) { try { m.removeLayer(P.polyline); } catch (e) {} }
        P.polyline = null;
        P.points = [];
    }

    function _dessinerApercuPochoir(geom) {
        const m = carte();
        if (!m || !geom) return;
        if (P.stencilLayer && m.hasLayer(P.stencilLayer)) m.removeLayer(P.stencilLayer);
        try {
            const gj = { type: 'Feature', properties: {}, geometry: geom };
            P.stencilLayer = L.geoJSON(gj, {
                style: { color: '#8b5cf6', weight: 2, fillColor: '#8b5cf6',
                         fillOpacity: 0.12, dashArray: '8 5' }
            }).addTo(m);
            const b = P.stencilLayer.getBounds();
            if (b.isValid()) m.fitBounds(b.pad(0.15));
        } catch (e) { /* aperçu best effort */ }
    }

    // ------------------------------------------------------------------
    // Modale : sources + nommage + lancement
    // ------------------------------------------------------------------
    function _ouvrirModalPochoir(nomSug) {
        const modal = $id('modal-pochoir');
        if (!modal) return;
        const input = $id('pochoir-nom');
        if (input) input.value = nomSug ? String(nomSug).replace(/[^\w\- ]/g, '_').slice(0, 60) : '';

        // Liste des couches satellites : cochées par défaut si visibles
        const cont = $id('pochoir-aux-list');
        const vide = $id('pochoir-aux-vide');
        if (cont) {
            cont.innerHTML = '';
            const aux = window.AUX_LAYERS;
            const entrees = aux && aux.couches ? Object.values(aux.couches) : [];
            entrees.forEach(entree => {
                const meta = entree.meta || entree;
                if (!meta || !meta.id) return;
                const visible = !!(entree.groupe && carte() && carte().hasLayer(entree.groupe));
                const lab = document.createElement('label');
                lab.style.cssText = 'display:flex;align-items:center;gap:10px;padding:7px 10px;background:#0f172a;border:1px solid rgba(255,255,255,0.08);border-radius:8px;cursor:pointer;';
                lab.innerHTML =
                    `<input type="checkbox" class="pochoir-aux-cb" data-id="${meta.id}" ${visible ? 'checked' : ''} style="accent-color:#8b5cf6;width:15px;height:15px;">` +
                    `<span style="font-size:0.8rem;color:#e2e8f0;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${meta.nom || meta.id}</span>` +
                    `<span style="font-size:0.65rem;color:#64748b;">${meta.nb_features != null ? meta.nb_features + ' objets' : ''}</span>`;
                cont.appendChild(lab);
            });
            const n = cont.children.length;
            if (vide) vide.style.display = n ? 'none' : 'block';
            if (cont.parentElement) cont.style.display = n ? 'grid' : 'none';
        }
        const statut = $id('pochoir-statut');
        if (statut) statut.style.display = 'none';
        modal.style.display = 'flex';
    }

    window.fermerModalPochoir = function () {
        const modal = $id('modal-pochoir');
        if (modal) modal.style.display = 'none';
        // L'aperçu du pochoir reste sur la carte pour référence visuelle.
    };

    window.lancerExtractionPochoir = async function () {
        if (!P.stencilGeoJSON) {
            _statutPochoir('Définissez d\'abord la zone du pochoir (icône toolbar).', false);
            return;
        }
        const nom = (($id('pochoir-nom') || {}).value || '').trim();
        if (!nom) { _statutPochoir('Donnez un nom de base aux fichiers.', false); return; }
        const inclureReseau = ($id('pochoir-reseau') || {}).checked !== false;
        const auxIds = Array.from(document.querySelectorAll('.pochoir-aux-cb:checked'))
            .map(cb => cb.dataset.id);
        if (!inclureReseau && !auxIds.length) {
            _statutPochoir('Sélectionnez au moins une source (réseau ou couches SIG).', false);
            return;
        }
        const pid = await resoudreProjectId();
        if (!pid) { _statutPochoir('Aucun projet actif.', false); return; }

        const btn = $id('btn-pochoir-run');
        if (btn) { btn.disabled = true; btn.style.opacity = '0.6'; }
        _statutPochoir('Extraction en cours…', true);

        try {
            const r = await fetch(`/api/v1/projets/${encodeURIComponent(pid)}/extraction-pochoir`, {
                method: 'POST',
                credentials: 'include',
                headers: Object.assign({ 'Content-Type': 'application/json' }, authHeaders()),
                body: JSON.stringify({
                    nom, geojson: P.stencilGeoJSON,
                    inclure_reseau: inclureReseau, aux_layer_ids: auxIds,
                })
            });
            const j = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(j.detail || r.statusText);
            const ex = j.extraction || {};
            _statutPochoir(
                `✔ ${ex.nom_zip || 'Archive'} prête — ${ex.nb_objets || 0} couche(s) thématique(s) extraite(s).`, true);
            // Téléchargement automatique du zip
            if (ex.url_download) _telechargerArtefact(ex.url_download, ex.nom_zip || `${nom}.zip`);
        } catch (err) {
            _statutPochoir('Échec : ' + err.message, false);
        } finally {
            if (btn) { btn.disabled = false; btn.style.opacity = '1'; }
        }
    };

    function _statutPochoir(msg, ok) {
        const el = $id('pochoir-statut');
        if (!el) return;
        el.style.display = 'block';
        el.style.whiteSpace = 'pre-line';
        el.style.background = ok ? 'rgba(52,211,153,0.12)' : 'rgba(248,113,113,0.12)';
        el.style.color = ok ? '#6ee7b7' : '#fca5a5';
        el.textContent = msg;
    }

    async function _telechargerArtefact(url, nomFichier) {
        try {
            const r = await fetch(url, { credentials: 'include', headers: authHeaders() });
            if (!r.ok) throw new Error('HTTP ' + r.status);
            const blob = await r.blob();
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = nomFichier;
            document.body.appendChild(a);
            a.click();
            setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 4000);
        } catch (e) {
            // Repli : ouverture directe (cookie de session)
            window.open(url, '_blank');
        }
    }

    // Si une couche satellite est (re)chargée pendant le mode « bassin »,
    // les nouveaux features restent cliquables via le hit-test global — rien
    // à faire : _featureSousClic parcourt les groupes à chaque clic.

    // Nettoyage si la carte est remplacée
    window.addEventListener('beforeunload', () => { try { quitterModePochoir(); } catch (e) {} });
})();
