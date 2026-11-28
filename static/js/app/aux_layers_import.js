/**
 * ==============================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de creation : 2026-11-08
 * Date de modification : 2026-11-08
 * Objet : Import pilote des couches SIG satellite et gestion des suspects
 * ================================================================================
 */

// Module d'import et de qualification des couches SIG « satellite ».
// Extrait verbatim de aux_layers.js (regle 600 lignes) : meme IIFE, etat et
// helpers partages via window._auxInt expose par aux_layers.js.
(function () {
    'use strict';

    const {
        AUX, _baseSansExt, _rendreItemsAux, authHeaders, carte,
        chargerListeCouches, desactiverSonde, fetchJSON,
        majCouchesVisibles, resoudreProjectId
    } = window._auxInt;

    /**
     * Collecte récursive des fichiers d'un FileSystemDirectoryHandle
     * (File System Access API) en objets File exploitables par auxScanDossier.
     */
    async function _lireDossierFS(dirHandle, prefix, out) {
        for await (const h of dirHandle.values()) {
            if (h.kind === 'file') {
                try {
                    const f = await h.getFile();
                    // Chemin relatif synthétique : 1er segment = nom du dossier
                    // choisi (utilisé pour l'affichage « 📂 dossier »).
                    // Best effort : si le File est non extensible, on garde
                    // quand même le fichier (nomDossier retombera sur f.name).
                    try {
                        Object.defineProperty(f, 'webkitRelativePath',
                            { value: `${prefix}/${h.name}`, configurable: true });
                    } catch (e2) { /* non bloquant */ }
                    out.push(f);
                } catch (e) { /* fichier illisible : ignoré */ }
            } else if (h.kind === 'directory') {
                await _lireDossierFS(h, `${prefix}/${h.name}`, out);
            }
        }
    }

    /**
     * Sélection du dossier de couches SIG.
     * File System Access API (Chrome/Edge) : sélecteur de dossier natif,
     * SANS le dialogue « importer N fichiers » imposé par webkitdirectory.
     * Fallback : input webkitdirectory (dialogue navigateur inévitable).
     */
    window.choisirDossierSIG = async function () {
        if (window.showDirectoryPicker) {
            try {
                const dir = await showDirectoryPicker({ mode: 'read' });
                const fichiers = [];
                await _lireDossierFS(dir, dir.name, fichiers);
                if (fichiers.length) {
                    auxScanDossier(fichiers);
                }
                return;
            } catch (e) {
                // Annulation utilisateur ou API indisponible → fallback
                if (e && e.name === 'AbortError') return;
            }
        }
        const inp = document.getElementById('aux-file');
        if (inp) inp.click();
    };

    /**
     * Appelée dès que l'utilisateur a choisi un dossier.
     * Indexe tous les fichiers SIG, exclut ceux déjà importés, puis affiche
     * la liste à cocher (multisélection).
     */
    window.auxScanDossier = async function (fileList) {
        _auxDossierIndex = {};
        _auxEntrees = [];
        _auxSelectionnes = new Set();

        const allFiles = Array.from(fileList);
        if (!allFiles.length) return;

        // S'assurer que la liste des couches importées est à jour — sinon
        // les fichiers déjà présents ne pourraient pas être exclus.
        if (AUX.projectId && !AUX._listeChargee) {
            try { await chargerListeCouches(); } catch (e) { /* best effort */ }
        }

        // Libellé dossier
        const premierChemin = allFiles[0].webkitRelativePath || allFiles[0].name;
        nomDossierGlobal = premierChemin.split('/')[0] || '(dossier)';
        const lbl = document.getElementById('aux-folder-label');
        // NB : le compteur affiché après _rendreItemsAux() = nb de couches
        // (un shapefile + ses sidecars = 1 seule couche).

        // Index par nom de base (sans extension, insensible à la casse)
        allFiles.forEach(f => {
            const nomComplet = f.name;
            const ext = nomComplet.slice(nomComplet.lastIndexOf('.')).toLowerCase();
            const base = nomComplet.slice(0, nomComplet.lastIndexOf('.')).toLowerCase();

            if (!_auxDossierIndex[base]) {
                _auxDossierIndex[base] = { shp: null, sidecars: [], autres: [] };
            }
            if (ext === '.shp') {
                _auxDossierIndex[base].shp = f;
            } else if (['.shx', '.dbf', '.prj', '.cpg', '.sbn', '.sbx', '.qpj'].includes(ext)) {
                _auxDossierIndex[base].sidecars.push(f);
            } else {
                _auxDossierIndex[base].autres.push(f);
            }
        });

        // Couches directes (gpkg, geojson, zip) sans shp
        const directes = allFiles.filter(f => {
            const ext = f.name.slice(f.name.lastIndexOf('.')).toLowerCase();
            return ['.gpkg', '.geojson', '.json', '.zip'].includes(ext);
        });

        // Shapefiles détectés
        const shapefiles = Object.values(_auxDossierIndex).filter(e => e.shp !== null);

        // Construit les entrées affichables (déjà importé = exclu du rendu)
        shapefiles.forEach(entry => {
            const f = entry.shp;
            const base = f.name.slice(0, f.name.lastIndexOf('.')).toLowerCase();
            const manquants = ['.shx', '.dbf'].filter(scn =>
                !entry.sidecars.some(sc => sc.name.toLowerCase().endsWith(scn))
            );
            _auxEntrees.push({
                cle: 'shp:' + base,
                cleComp: base,
                genre: 'shp',
                ok: manquants.length === 0,
                deja: AUX.nomsImportes.has(base),
                nom: f.name,
                taille: f.size,
                nbSidecars: entry.sidecars.length,
                entry: entry
            });
        });

        directes.forEach(f => {
            const baseComp = _baseSansExt(f.name);
            const ext = f.name.slice(f.name.lastIndexOf('.')).toLowerCase();
            _auxEntrees.push({
                cle: 'direct:' + f.name,
                cleComp: baseComp,
                genre: 'direct',
                ok: true,
                deja: AUX.nomsImportes.has(baseComp),
                nom: f.name,
                taille: f.size,
                ext: ext,
                fichier: f
            });
        });

        _rendreItemsAux();
    };

    window.envoyerCoucheAux = async function () {
        const statutEl = document.getElementById('aux-upload-statut');
        const btn      = document.getElementById('btn-aux-upload');

        const afficherErreur = msg => {
            statutEl.style.display = 'block';
            statutEl.style.whiteSpace = 'pre-line';
            statutEl.style.background = 'rgba(248,113,113,0.12)';
            statutEl.style.color = '#fca5a5';
            statutEl.textContent = msg;
        };
        const afficherInfo = (msg, ok) => {
            statutEl.style.display = 'block';
            statutEl.style.whiteSpace = 'pre-line';
            statutEl.style.background = ok ? 'rgba(52,211,153,0.12)' : 'rgba(56,189,248,0.12)';
            statutEl.style.color = ok ? '#6ee7b7' : '#7dd3fc';
            statutEl.textContent = msg;
        };

        const selection = _auxEntrees.filter(e => _auxSelectionnes.has(e.cle) && !e.deja && e.ok);
        if (!selection.length) {
            afficherErreur("Cochez d'abord au moins une couche à importer dans la liste.");
            return;
        }

        const pid = await resoudreProjectId();
        if (!pid) { afficherErreur("Aucun projet actif : chargez d'abord un réseau."); return; }

        const type    = document.getElementById('aux-type').value;
        const nomBase = (document.getElementById('aux-nom').value || '').trim();
        const cz      = (document.getElementById('aux-colonne-z').value || '').trim();
        let   crsSaisi = '';
        const multi   = selection.length > 1;

        btn.disabled = true;
        btn.style.opacity = '0.6';
        btn.style.cursor  = 'not-allowed';
        btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Import en cours…';

        const resultats = [];
        for (let i = 0; i < selection.length; i++) {
            const e = selection[i];
            afficherInfo(`Import ${i + 1}/${selection.length} — « ${e.nom} »…`, false);

            const fd = new FormData();
            if (e.genre === 'direct') {
                fd.append('files', e.fichier);
            } else {
                fd.append('files', e.entry.shp);
                e.entry.sidecars.forEach(sc => fd.append('files', sc));
            }
            fd.append('type', type);
            const nomEnvoye = multi ? (nomBase ? `${nomBase} — ${e.nom}` : '') : nomBase;
            if (nomEnvoye) fd.append('nom', nomEnvoye);
            if (cz) fd.append('colonne_z', cz);
            if (crsSaisi) fd.append('crs', crsSaisi);

            try {
                let r = await fetch(`/api/v1/projets/${encodeURIComponent(pid)}/aux-layers`, {
                    method: 'POST',
                    credentials: 'include',
                    headers: authHeaders(),
                    body: fd
                });
                let j = await r.json().catch(() => ({}));
                // Projection absente → redemander une fois (jamais de repli
                // silencieux : des mesures faussées valent pire qu'un blocage).
                if (!r.ok && r.status === 400 && !crsSaisi &&
                    /crs|projection/i.test(j.detail || '')) {
                    const saisie = window.prompt(
                        `« ${e.nom} » ne déclare pas de projection (CRS).\n` +
                        'Saisissez le code EPSG de la projection source\n' +
                        '(ex. EPSG:32631 pour l\'UTM 31N Algérie) :',
                        'EPSG:32631');
                    if (saisie && saisie.trim()) {
                        crsSaisi = saisie.trim();
                        fd.set('crs', crsSaisi);
                        r = await fetch(`/api/v1/projets/${encodeURIComponent(pid)}/aux-layers`, {
                            method: 'POST',
                            credentials: 'include',
                            headers: authHeaders(),
                            body: fd
                        });
                        j = await r.json().catch(() => ({}));
                    }
                }
                if (!r.ok) throw new Error(j.detail || r.statusText);
                resultats.push({ cle: e.cle, ok: true, nom: (j.couche && j.couche.nom) || e.nom, avert: j.avertissement || null });
            } catch (err) {
                resultats.push({ cle: e.cle, ok: false, nom: e.nom, err: err.message });
            }
        }

        const nbOk = resultats.filter(r => r.ok).length;
        const lignes = resultats.map(r => r.ok ? `✔ ${r.nom}` : `✖ ${r.nom} — ${r.err}`);
        const avert = resultats.map(r => r.avert).filter(Boolean);
        afficherInfo(
            `${nbOk}/${selection.length} couche${selection.length > 1 ? 's' : ''} importée${nbOk > 1 ? 's' : ''}\n` +
            lignes.join('\n') +
            (avert.length ? `\n⚠ ${avert.join(' | ')}` : ''),
            nbOk === selection.length
        );

        // Réinitialisation + rafraîchissement : les fichiers importés
        // disparaissent de la liste à la prochaine ouverture/actualisation.
        _auxSelectionnes.clear();
        document.getElementById('aux-nom').value       = '';
        document.getElementById('aux-colonne-z').value = '';
        try { await chargerListeCouches(); } catch (e) {}
        _auxEntrees.forEach(e => { e.deja = AUX.nomsImportes.has(e.cleComp); });
        _rendreItemsAux();

        btn.disabled = false;
        btn.style.opacity = '1';
        btn.style.cursor  = 'pointer';
        btn.innerHTML = '<i class="fas fa-upload me-1"></i> Importer';

        // Succès complet → clôturer la modale : l'import est terminé, pas de
        // « re-confirmation » (Annuler/Importer) à retaper. En cas d'erreur
        // partielle, la modale reste ouverte avec le récapitulatif.
        if (nbOk === selection.length) {
            if (typeof window.dialogueNotifier === 'function') {
                window.dialogueNotifier({
                    message: `${nbOk} couche${nbOk > 1 ? 's' : ''} importée${nbOk > 1 ? 's' : ''} avec succès.`,
                    type: 'succes'
                });
            }
            window.fermerModalAuxLayer();
        }
    };

    // Compat ascendante : plus utilisé par la liste (cases à cocher),
    // conservé au cas où un autre appel existerait.
    window.auxSelectionnerShp = function () { /* remplacé par les écouteurs directs */ };



    // ------------------------------------------------------------------
    // File de revue P1 : suspects de sens d'écoulement (lecture seule)
    // ------------------------------------------------------------------
    const COULEURS_SEV = { fort: '#ef4444', moyen: '#f59e0b', faible: '#38bdf8' };
    const COULEURS_CONF = { haute: '#34d399', moyenne: '#fbbf24', faible: '#f87171', aucune: '#94a3b8' };

    function _suspectsFiltres() {
        return {
            sev: (document.getElementById('suspects-filtre-sev') || {}).value || '',
            conf: (document.getElementById('suspects-filtre-conf') || {}).value || '',
            txt: ((document.getElementById('suspects-filtre-texte') || {}).value || '').toLowerCase(),
        };
    }

    function _suspectsFiltresAppliquer(liste) {
        const f = _suspectsFiltres();
        return (liste || []).filter(s => {
            if (f.sev && s.severite !== f.sev) return false;
            if (f.conf && s.confiance !== f.conf) return false;
            if (f.txt && !(String(s.amont).includes(f.txt) || String(s.aval).includes(f.txt))) return false;
            return true;
        });
    }

    window.ouvrirModalSuspects = async function (layerId) {
        const m = document.getElementById('modal-suspects');
        if (!m || !AUX.projectId) return;
        AUX.suspectsLayerId = layerId;
        m.style.display = 'flex';
        const corps = document.getElementById('suspects-corps');
        const stats = document.getElementById('suspects-stats');
        if (corps) corps.innerHTML = '<div style="color:#94a3b8;font-size:0.85rem;">Analyse en cours…</div>';
        if (stats) stats.innerHTML = '<span style="color:#94a3b8;">Chargement…</span>';
        try {
            const d = await fetchJSON(
                `/api/v1/projets/${encodeURIComponent(AUX.projectId)}/aux-layers/${layerId}/suspects-ecoulement`
            );
            AUX.suspectsData = d;
            _rendreStatsSuspects(d);
            _rendreAvertSuspects(d);
            rendreTableSuspects();
        } catch (e) {
            if (corps) corps.innerHTML = `<div style="color:#f87171;font-size:0.85rem;">Analyse impossible : ${e.message}</div>`;
        }
    };

    window.fermerModalSuspects = function () {
        const m = document.getElementById('modal-suspects');
        if (m) m.style.display = 'none';
        _effacerSuspectsCarte();
    };

    function _rendreStatsSuspects(d) {
        const stats = document.getElementById('suspects-stats');
        const sous = document.getElementById('suspects-sous-titre');
        if (!stats) return;
        if (sous && d.layer_nom) sous.textContent = `${d.layer_nom} — analyse terrain IDW, file de revue`;
        if (d.statut !== 'ok') {
            stats.innerHTML = `<span style="color:#fbbf24;">${d.statut === 'perime' ? 'Artefact périmé — recalcul requis' : (d.raison || d.statut)}</span>`;
            return;
        }
        const ps = d.par_severite || {};
        stats.innerHTML = `
            <span><b style="color:#e2e8f0;">${d.nb_conduites_analysées}</b> <span style="color:#94a3b8;">conduites analysées</span></span>
            <span><b style="color:#f87171;">${ps.fort || 0}</b> <span style="color:#94a3b8;">forts</span></span>
            <span><b style="color:#fbbf24;">${ps.moyen || 0}</b> <span style="color:#94a3b8;">moyens</span></span>
            <span><b style="color:#7dd3fc;">${ps.faible || 0}</b> <span style="color:#94a3b8;">faibles</span></span>
            <span style="color:#64748b;">(suspects affichés : ${Math.min((d.suspects || []).length, 300)})</span>`;
    }

    function _rendreAvertSuspects(d) {
        const el = document.getElementById('suspects-avert');
        if (el && d.avertissement) el.textContent = d.avertissement;
    }

    window.rendreTableSuspects = function () {
        const corps = document.getElementById('suspects-corps');
        if (!corps) return;
        const d = AUX.suspectsData;
        if (!d || d.statut !== 'ok') return;
        const liste = _suspectsFiltresAppliquer(d.suspects || []);
        const MAX = 150;
        const shown = liste.slice(0, MAX);
        if (!shown.length) {
            corps.innerHTML = '<div style="color:#94a3b8;font-size:0.85rem;padding:12px 0;">Aucun suspect pour ces filtres.</div>';
            return;
        }
        let html = `<table style="width:100%; border-collapse:collapse; font-size:0.74rem;">
            <thead><tr style="color:#64748b; text-align:left; border-bottom:1px solid rgba(255,255,255,0.1);">
                <th style="padding:5px 6px;">Sévérité</th><th style="padding:5px 6px;">Conduite</th>
                <th style="padding:5px 6px; text-align:right;">Long.</th>
                <th style="padding:5px 6px; text-align:right;">Δ terrain</th>
                <th style="padding:5px 6px; text-align:right;">Pente contr.</th>
                <th style="padding:5px 6px; text-align:right;">Δ radier</th>
                <th style="padding:5px 6px;">Confiance</th><th style="padding:5px 6px;">Motifs</th>
                <th style="padding:5px 6px;"></th>
            </tr></thead><tbody>`;
        shown.forEach((s, i) => {
            const cc = COULEURS_CONF[s.confiance] || '#94a3b8';
            const sc = COULEURS_SEV[s.severite] || '#94a3b8';
            html += `<tr style="border-bottom:1px solid rgba(255,255,255,0.05); cursor:pointer;" 
                onmouseover="this.style.background='rgba(56,189,248,0.06)'" onmouseout="this.style.background='transparent'"
                onclick="centrerSuspect(${i})">
                <td style="padding:5px 6px;"><span style="color:${sc}; font-weight:700;">●</span> ${s.severite}</td>
                <td style="padding:5px 6px; font-family:monospace;">${s.amont} → ${s.aval}</td>
                <td style="padding:5px 6px; text-align:right;">${s.longueur_m} m</td>
                <td style="padding:5px 6px; text-align:right; color:#f87171;">+${s.ecart_terrain_m} m</td>
                <td style="padding:5px 6px; text-align:right;">${s.pente_contre_pct} %</td>
                <td style="padding:5px 6px; text-align:right;">${s.ecart_radier_m != null ? '+' + s.ecart_radier_m + ' m' : '—'}</td>
                <td style="padding:5px 6px;"><span style="color:${cc};">${s.confiance}</span></td>
                <td style="padding:5px 6px; color:#94a3b8; max-width:340px;">${(s.motifs || []).join(' ; ')}</td>
                <td style="padding:5px 6px;"><button onclick="event.stopPropagation(); centrerSuspect(${i})" style="background:transparent;border:1px solid rgba(56,189,248,0.4);color:#7dd3fc;border-radius:5px;padding:1px 8px;font-size:0.68rem;cursor:pointer;">⌖</button></td>
            </tr>`;
        });
        html += `</tbody></table>`;
        if (liste.length > MAX) {
            html += `<div style="color:#64748b;font-size:0.72rem;padding:8px 0;">… et ${liste.length - MAX} autres (affinez les filtres ou zoomez sur la carte).</div>`;
        }
        corps.innerHTML = html;
        AUX._suspectsFiltresCourants = liste;
    };

    window.centrerSuspect = function (idx) {
        const liste = AUX._suspectsFiltresCourants || [];
        const s = liste[idx];
        const m = carte();
        if (!s || !m) return;
        // Milieu approximatif entre amont et aval
        const lat = (s.lat_amont != null && s.lat_aval != null)
            ? (s.lat_amont + s.lat_aval) / 2 : s.lat_amont;
        const lng = (s.lng_amont != null && s.lng_aval != null)
            ? (s.lng_amont + s.lng_aval) / 2 : s.lng_amont;
        if (lat == null || lng == null) return;
        m.setView([lat, lng], 17);
        L.popup({ closeButton: true })
            .setLatLng([lat, lng])
            .setContent(`<div style="font-size:0.8rem;line-height:1.5;">
                <b>Suspect ${s.severite}</b> — ${s.amont} → ${s.aval}<br>
                Terrain : ${s.z_terrain_amont} → ${s.z_terrain_aval} m<br>
                Δ = +${s.ecart_terrain_m} m (${s.pente_contre_pct} %)<br>
                <span style="color:#64748b;">${(s.motifs || []).join(' ; ')}</span><br>
                <span style="color:#b45309;">File de revue — aucune correction auto.</span>
            </div>`).openOn(m);
    };

    window.afficherSuspectsCarte = function () {
        const m = carte();
        if (!m) return;
        _effacerSuspectsCarte();
        const liste = _suspectsFiltresAppliquer(AUX.suspectsData && AUX.suspectsData.suspects || []);
        const CAP = 500;
        AUX._suspectsGroupe = L.layerGroup();
        liste.slice(0, CAP).forEach(s => {
            const lat = (s.lat_amont != null && s.lat_aval != null) ? (s.lat_amont + s.lat_aval) / 2 : s.lat_amont;
            const lng = (s.lng_amont != null && s.lng_aval != null) ? (s.lng_amont + s.lng_aval) / 2 : s.lng_amont;
            if (lat == null || lng == null) return;
            const col = COULEURS_SEV[s.severite] || '#94a3b8';
            L.circleMarker([lat, lng], {
                radius: s.severite === 'fort' ? 7 : 5,
                color: '#0f172a', weight: 1,
                fillColor: col, fillOpacity: 0.75,
            }).bindTooltip(`${s.severite.toUpperCase()} — ${s.amont} → ${s.aval}<br>Δ terrain +${s.ecart_terrain_m} m`,
                { sticky: true })
              .addTo(AUX._suspectsGroupe);
        });
        AUX._suspectsGroupe.addTo(m);
        if (typeof window.dialogueNotifier === 'function') {
            window.dialogueNotifier({
                message: `${Math.min(liste.length, CAP)} suspects affichés sur la carte (filtrés).`,
                type: 'info'
            });
        }
    };

    function _effacerSuspectsCarte() {
        const m = carte();
        if (m && AUX._suspectsGroupe) {
            m.removeLayer(AUX._suspectsGroupe);
            AUX._suspectsGroupe = null;
        }
    }

    /**
     * Réinitialise le contexte projet des couches satellites : retire les
     * couches affichées de l'ancien projet, invalide le projectId caché et
     * recharge la liste. Appelé à chaque chargement d'un réseau/projet —
     * garantit qu'une couche importée dans un projet n'apparaît jamais
     * dans un autre.
     */
    window.auxReinitialiserProjet = async function () {
        const m = carte();
        Object.values(AUX.couches).forEach(c => {
            try { if (m && m.hasLayer(c.groupe)) m.removeLayer(c.groupe); } catch (e) {}
        });
        desactiverSonde();
        AUX.couches = {};
        AUX.projectId = null;
        AUX._listeChargee = false;
        AUX.nomsImportes = new Set();
        const cont = document.getElementById('aux-layers-list');
        if (cont) cont.innerHTML = '';
        const vide = document.getElementById('aux-layers-vide');
        if (vide) vide.style.display = 'block';
        await chargerListeCouches();
    };

    // ------------------------------------------------------------------
    // Initialisation
    // ------------------------------------------------------------------
    function initialiser() {
        window.auxMajChampZ && window.auxMajChampZ();
        chargerListeCouches();
        const m = carte();
        if (m && !AUX._moveendBind) {
            AUX._moveendBind = true;
            let t = null;
            m.on('moveend', () => {
                clearTimeout(t);
                t = setTimeout(() => {
                    // Pendant un positionnement de recherche d'ouvrage, conserver
                    // les couches auxiliaires déjà chargées : évite le rechargement
                    // massif de la couche altimétrique (gel) et le clignotement.
                    if (window._rechercheCentrageJusqua && Date.now() < window._rechercheCentrageJusqua) return;
                    majCouchesVisibles();
                }, 400);
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialiser);
    } else {
        initialiser();
    }
    // Le projet peut se charger après le DOM : on retente la résolution du projectId
    setTimeout(() => { if (!AUX.projectId) chargerListeCouches(); }, 8000);

    window.AUX_LAYERS = AUX;
})();
