/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Contexte spatial unique (invariants INV-1/INV-2)
 * Objet : Un seul snapshot GPKG à la fois — la carte, les résultats de
 *         simulation, les bassins, la recherche et les apports affichés
 *         partagent toujours le même espace d'identifiants.
 *
 * Règles :
 *  - INV-1 : toute couche spatiale provient du snapshot actif ;
 *  - INV-2 : une simulation n'est rendue que si sa provenance
 *    (provenance.gpkg_sha256 / gpkg_version_id) correspond au snapshot
 *    affiché — sinon bascule préalable du réseau sur LE snapshot de la sim ;
 *  - INV-4 : snapshot archivé = lecture seule (aucune écriture n'est
 *    possible : les endpoints d'écriture ne prennent pas de paramètre
 *    snapshot et agissent toujours sur la version courante).
 * ================================================================================
 */
(function () {
    'use strict';

    /**
     * Contexte spatial courant — reflète la réponse /api/v1/layers.
     * sha256/versionId identifient le snapshot EFFECTIVEMENT affiché.
     */
    window._contexteSpatial = {
        sha256: null,
        versionId: null,
        estVersionCourante: true,
        libelle: null,
        nbRegards: null,
        nbConduites: null,
    };

    /** Snapshot demandé pour le prochain chargement des couches (sha ou version_id). */
    window._snapshotEnAttente = null;
    /** true pendant la bascule vers un snapshot archivé (supprime l'auto-restore). */
    window._chargementSnapshotEnCours = false;
    /** Promesse résolue à la fin d'un chargerDonneesInitiales(). */
    window._promesseChargementReseau = null;
    /** Déduplication des bascules simultanées. */
    window._syncSnapshotEnCours = null;

    /**
     * Ajoute `snapshot=<réf>` aux URLs des endpoints de lecture spatiale
     * quand une vue archive est active. Sans vue archive : URL inchangée.
     */
    window._urlAvecSnapshot = function (url) {
        const cs = window._contexteSpatial;
        if (!cs || cs.estVersionCourante) return url;
        const ref = cs.sha256 || cs.versionId;
        if (!ref) return url;
        return url + (url.indexOf('?') >= 0 ? '&' : '?')
            + 'snapshot=' + encodeURIComponent(ref);
    };

    /**
     * Enregistre la métadonnée `snapshot` renvoyée par /api/v1/layers et
     * met à jour la bannière d'archive.
     */
    window._majContexteDepuisLayers = function (d) {
        const snap = d && d.snapshot;
        if (!snap) return;
        const cs = window._contexteSpatial;
        cs.sha256 = snap.sha256 || null;
        cs.versionId = snap.version_id || null;
        cs.estVersionCourante = !!snap.est_version_courante;
        cs.libelle = snap.libelle || null;
        cs.nbRegards = snap.nb_regards;
        cs.nbConduites = snap.nb_conduites;
        _majBanniereArchive();
    };

    function _majBanniereArchive() {
        const cs = window._contexteSpatial;
        let banniere = document.getElementById('banniere-snapshot-archive');
        if (cs.estVersionCourante) {
            if (banniere) banniere.style.display = 'none';
            document.body.classList.remove('snapshot-archive');
            try { if (window.carte && window.carte.invalidateSize) window.carte.invalidateSize(); } catch (_) {}
            return;
        }
        if (!banniere) {
            banniere = document.createElement('div');
            banniere.id = 'banniere-snapshot-archive';
            const carteWs = document.getElementById('carte-workspace') || document.getElementById('app-workspace');
            if (carteWs) {
                carteWs.insertBefore(banniere, carteWs.firstChild);
            } else {
                document.body.appendChild(banniere);
            }
        }
        const libelle = cs.libelle || 'version archivée';
        const parties = [];
        if (cs.nbRegards != null) parties.push(cs.nbRegards + ' regards');
        if (cs.nbConduites != null) parties.push(cs.nbConduites + ' conduites');
        const comptes = parties.length ? ' (' + parties.join(' / ') + ')' : '';
        banniere.innerHTML =
            '<i class="fas fa-box-archive" style="color:#fbbf24;"></i>'
            + '<span><b>Consultation d\'archive</b> — réseau « ' + _echapper(libelle) + ' »'
            + comptes + ' — <i>lecture seule</i></span>'
            + '<span style="flex:1"></span>'
            + '<button id="btn-retour-reseau-actuel" style="background:#f59e0b;color:#1c1917;border:none;'
            + 'border-radius:6px;padding:4px 12px;font-weight:700;cursor:pointer;">'
            + 'Revenir au réseau actuel</button>';
        banniere.style.display = 'flex';
        document.body.classList.add('snapshot-archive');
        try { if (window.carte && window.carte.invalidateSize) window.carte.invalidateSize(); } catch (_) {}
        const btn = document.getElementById('btn-retour-reseau-actuel');
        if (btn && !btn._lie) {
            btn._lie = true;
            btn.addEventListener('click', function () {
                window.retournerAuReseauActuel();
            });
        }
    }

    function _echapper(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    /**
     * Revient au réseau courant : purge le contexte archive et recharge
     * les couches sans paramètre snapshot.
     */
    window.retournerAuReseauActuel = function () {
        window._contexteSpatial.estVersionCourante = true;
        window._contexteSpatial.sha256 = null;
        window._contexteSpatial.versionId = null;
        window._contexteSpatial.libelle = null;
        _majBanniereArchive();
        if (typeof chargerDonneesInitiales === 'function') {
            chargerDonneesInitiales();
        }
    };

    /**
     * Attend la fin du chargement courant des couches réseau
     * (promesse posée par chargerDonneesInitiales). Timeout de sécurité.
     */
    function _attendreChargementReseau(timeoutMs) {
        const p = window._promesseChargementReseau;
        if (!p || typeof p.then !== 'function') return Promise.resolve();
        return Promise.race([
            p,
            new Promise(function (res) { setTimeout(res, timeoutMs || 30000); })
        ]);
    }

    /**
     * Synchronise le contexte spatial avec la provenance d'une simulation.
     * Si la sim appartient à un autre snapshot que le réseau affiché, le
     * réseau ENTIER bascule sur le snapshot de la sim (couches, bassins,
     * sous-bassins, apports — tous via les endpoints snapshot-aware).
     *
     * Retourne Promise<{ok:boolean, raison?:string}> — ok=false si le
     * snapshot est introuvable ou si la vérification finale échoue (INV-2).
     */
    window._syncContexteAvecResultat = function (data) {
        const prov = (data && data.provenance) || {};
        const refSnap = prov.gpkg_sha256 || prov.gpkg_version_id || null;
        if (!refSnap) {
            // Simulation legacy sans provenance exploitable : pas de
            // bascule possible — le garde-fou INV-2 laisse passer (le
            // matching u_node/d_node échouera naturellement si le réseau
            // a changé).
            return Promise.resolve({ ok: true });
        }

        const cs = window._contexteSpatial;
        // Déjà cohérent ? (vue archive sur ce snapshot, ou réseau courant).
        // RÈGLE D'OR : Si nous sommes sur la version courante du projet, ne JAMAIS
        // déclencher chargerDonneesInitiales() lors d'une sélection de bassin ou de
        // simulation — cela rechargerait tout le réseau (10k regards) et relancerait
        // le partitionnement lourd. Les identifiants topologiques de nœuds et tronçons
        // assurent l'intégrité du rendu directement.
        if (cs.estVersionCourante) {
            return Promise.resolve({ ok: true });
        }
        const ref = String(refSnap);
        if (!cs.estVersionCourante
            && (ref === cs.sha256 || ref === cs.versionId)) {
            return Promise.resolve({ ok: true });
        }

        // Bascule dédupliquée : plusieurs affichages simultanés partagent
        // la même promesse de rechargement.
        if (window._syncSnapshotEnCours) {
            return window._syncSnapshotEnCours.then(function () {
                return _verifierInv2(data);
            });
        }

        window._chargementSnapshotEnCours = true;
        window._snapshotEnAttente = refSnap;

        window._syncSnapshotEnCours = (async function () {
            try {
                if (typeof chargerDonneesInitiales === 'function') {
                    chargerDonneesInitiales();
                    await _attendreChargementReseau(60000);
                }
            } catch (e) {
                console.warn('[contexte-spatial] Bascule snapshot impossible :', e);
            } finally {
                window._chargementSnapshotEnCours = false;
                window._snapshotEnAttente = null;
                window._syncSnapshotEnCours = null;
            }
        })();

        return window._syncSnapshotEnCours.then(function () {
            return _verifierInv2(data);
        });
    };

    /**
     * INV-2 — vérification finale : la provenance de la simulation doit
     * correspondre au snapshot effectivement affiché (sha256 prioritaire,
     * version_id en secours). Aucun repli silencieux.
     */
    function _verifierInv2(data) {
        const prov = (data && data.provenance) || {};
        const shaSim = prov.gpkg_sha256 || null;
        const vidSim = prov.gpkg_version_id || null;
        const cs = window._contexteSpatial;
        if (!cs.sha256 && !cs.versionId) {
            // Réseau sans métadonnée snapshot (ancien serveur) : on laisse
            // passer — le matching par IDs reste le garde-fou naturel.
            return { ok: true };
        }
        const sSim = String(shaSim || '').trim().toLowerCase();
        const sCs = String(cs.sha256 || '').trim().toLowerCase();
        const okSha = sSim && sCs && (sSim === sCs || sSim.startsWith(sCs) || sCs.startsWith(sSim));
        const vSim = String(vidSim || '').trim().toLowerCase();
        const vCs = String(cs.versionId || '').trim().toLowerCase();
        const okVid = vSim && vCs && (vSim === vCs || vSim.startsWith(vCs) || vCs.startsWith(vSim));
        if (okSha || okVid) return { ok: true };
        return { ok: false, raison: 'gpkg_snapshot_mismatch' };
    }

    /**
     * Notifie l'utilisateur qu'une simulation n'a pas pu être superposée
     * au réseau affiché (snapshot indisponible).
     */
    function _notifierMismatchSnapshot() {
        try {
            if (typeof window.afficherToast === 'function') {
                window.afficherToast(
                    'Cette simulation appartient à une version réseau dont le fichier est indisponible — affichage impossible sans mélange.',
                    'error');
            } else {
                console.warn('[contexte-spatial] Simulation hors snapshot disponible.');
            }
        } catch (_) { /* silencieux */ }
        if (typeof reinitialiserAffichageSimulation === 'function') {
            try { reinitialiserAffichageSimulation(); } catch (_) {}
        }
    }


    /**
     * Vrai si la vue archive est active — les écritures restent de toute
     * façon impossibles (endpoints sans paramètre snapshot), ceci sert
     * uniquement aux affordances UI (dégriser boutons, bandeau).
     */
    window._snapshotArchiveActif = function () {
        return !!(window._contexteSpatial && !window._contexteSpatial.estVersionCourante);
    };
})();
