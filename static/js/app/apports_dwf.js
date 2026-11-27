/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-27
 * Date de modification : 2026-11-27
 * Objet : LOT P1.5.2 — Interface de gestion des apports de temps sec (DWF)
 *
 * Consomme les contrats réels :
 *   GET    /api/v1/apports?project_id=&node_id=&actif_seulement=
 *   GET    /api/v1/apports/profils          → 3 profils, facteurs_168
 *   GET    /api/v1/apports/noeuds           → {noeuds[], count}
 *   GET    /api/v1/apports/a-reconcilier    → {apports, incompatibles[], reseau_courant}
 *   POST   /api/v1/apports                  → 201 ApportDwfResponse
 *   PUT    /api/v1/apports/{id}             → mise à jour partielle
 *   POST   /api/v1/apports/{id}/revalider   → ré-estampillage explicite
 *   DELETE /api/v1/apports/{id}             → 204
 *   GET    /api/v1/network/datasets         → active_project {id, name}
 *   GET    /api/v1/auth/me                  → rôle (owner/admin/engineer/viewer)
 *
 * Aucune réconciliation automatique : la seule voie est POST /revalider.
 * ================================================================================
 */

// ---------------------------------------------------------------------------
// État interne du module
// ---------------------------------------------------------------------------
window.DWF = {
    projectId: null,
    projectName: null,
    role: null,               // owner, admin, engineer, viewer…
    peutEcrire: false,
    apports: [],              // ApportDwfResponse[]
    incompatibles: [],        // details[] du contrat /a-reconcilier
    reseauCourant: null,      // {disponible, gpkg_version_id, gpkg_sha256, …}
    erreurReseau: null,
    profils: [],              // ProfilDwfInfo[]
    noeuds: [],               // string[]
    filtre: 'tous',
    recherche: '',
    editingId: null,
    mode: 'debit',
    chart: null,
    chargement: false,
};

const DWF_LABELS = {
    nature: {
        domestique: 'Domestique', industriel: 'Industriel',
        infiltration: 'Infiltration', autre: 'Autre',
    },
    mode: { debit: 'Débit mesuré', eh: 'Équivalent-habitant' },
    profil: {},   // rempli depuis /profils (key → nom)
};

// ---------------------------------------------------------------------------
// Helpers HTTP
// ---------------------------------------------------------------------------
function dwfToken() {
    return localStorage.getItem('swmm_access_token');
}

function dwfHeaders(json = false) {
    const h = {};
    const t = dwfToken();
    if (t) h['Authorization'] = `Bearer ${t}`;
    if (json) h['Content-Type'] = 'application/json';
    return h;
}

/** fetch JSON avec gestion 401/403/404/422 et détail API (string ou objet). */
async function dwfFetch(url, options = {}) {
    const resp = await fetch(url, Object.assign(
        { headers: dwfHeaders(!!options.body), credentials: 'include' },
        options));
    let data = null;
    try { data = await resp.json(); } catch (e) { /* pas de JSON */ }
    if (!resp.ok) {
        const err = new Error(dwfExtraireDetail(data, resp.status));
        err.status = resp.status;
        err.data = data;
        throw err;
    }
    return data;
}

function dwfExtraireDetail(data, status) {
    if (data && data.detail) {
        if (typeof data.detail === 'string') return data.detail;
        if (data.detail.message) return data.detail.message;
        try { return JSON.stringify(data.detail); } catch (e) { /* noop */ }
    }
    return `Erreur HTTP ${status}`;
}

function dwfFmt(n, dec = 3) {
    if (n === null || n === undefined || isNaN(Number(n))) return '—';
    return Number(n).toLocaleString('fr-FR', {
        minimumFractionDigits: dec, maximumFractionDigits: dec });
}

function dwfEchapper(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ---------------------------------------------------------------------------
// Ouverture / fermeture
// ---------------------------------------------------------------------------
window.ouvrirModalApportsDwf = async function() {
    const el = document.getElementById('modal-apports-dwf');
    if (!el) return;
    el.style.display = 'flex';
    DWF.editingId = null;
    DWF.recherche = '';
    const inp = document.getElementById('dwf-recherche');
    if (inp) inp.value = '';
    const wrapB = document.getElementById('dwf-wrap-bassin-seul');
    const chkB = document.getElementById('dwf-chk-bassin-seul');
    const lblB = document.getElementById('dwf-label-bassin-seul');
    const activeCid = window._selectedClusterId
        || (window._dernierResultatSimulation && window._dernierResultatSimulation.meta ? window._dernierResultatSimulation.meta.cluster_id : null);
    if (wrapB && chkB) {
        if (activeCid && String(activeCid).trim().toLowerCase() !== 'tous') {
            wrapB.style.display = 'inline-flex';
            chkB.checked = true;
            const nomB = (window._bassinNoms && window._bassinNoms[String(activeCid)]) || `Bassin ${activeCid}`;
            if (lblB) lblB.textContent = `Bassin : ${nomB}`;
        } else {
            wrapB.style.display = 'none';
            chkB.checked = false;
        }
    }
    definirFiltreDwf('courant');
    montrerVueDwf('liste');
    await initialiserDwf();
};

window.fermerModalApportsDwf = function() {
    const el = document.getElementById('modal-apports-dwf');
    if (el) el.style.setProperty('display', 'none', 'important');
    detruireChartDwf();

    // Restaurer les modales parentes suspendues lors du pick sur carte (ex: modal-simulation)
    if (window._dwfSuspendedModals && window._dwfSuspendedModals.length > 0) {
        window._dwfSuspendedModals.forEach(item => {
            if (item.id !== 'modal-apports-dwf') {
                const parentEl = document.getElementById(item.id);
                if (parentEl) {
                    parentEl.style.setProperty('display', item.prevDisplay || 'flex', 'important');
                }
            }
        });
        window._dwfSuspendedModals = [];
    }
};

// ---------------------------------------------------------------------------
// Initialisation : projet actif + rôle + données
// ---------------------------------------------------------------------------
async function initialiserDwf() {
    DWF.statut('Chargement du contexte projet…', 'info');
    try {
        // Projet actif (autorité : /network/datasets → active_project)
        const ds = await dwfFetch('/api/v1/network/datasets?_t=' + Date.now());
        const ap = ds && ds.active_project;
        if (!ap || !ap.id) {
            DWF.statut('Aucun projet actif : chargez d\'abord un réseau (modale Projet).', 'warn');
            rendreCompteursDwf();
            rendreListeDwf();
            return;
        }
        DWF.projectId = ap.id;
        DWF.projectName = ap.name || 'Projet actif';
        const nomEl = document.getElementById('dwf-projet-nom');
        if (nomEl) nomEl.textContent = DWF.projectName;

        // Rôle (pour masquer les écritures — l'autorité reste le backend)
        await chargerRoleDwf();

        // Chargements parallèles
        await Promise.all([
            chargerApportsDwf(),
            chargerIncompatiblesDwf(),
            chargerProfilsDwf(),
        ]);
        rendreCompteursDwf();
        rendreZoneReconciliationDwf();
        rendreListeDwf();
        DWF.statut(`${DWF.apports.length} apport(s) — ${DWF.incompatibles.length} incompatibilité(s) détectée(s).`, 'ok');
    } catch (e) {
        console.error('DWF init:', e);
        if (e.status === 401 || e.status === 403) {
            DWF.statut('Session expirée ou accès refusé — reconnectez-vous.', 'err');
        } else {
            DWF.statut('Erreur de chargement : ' + e.message, 'err');
        }
        rendreCompteursDwf();
        rendreListeDwf();
    }
}

async function chargerRoleDwf() {
    try {
        const me = await dwfFetch('/api/v1/auth/me');
        const role = me && me.user && me.user.is_superadmin
            ? 'superadmin'
            : (me && me.active_organization && me.active_organization.role) || null;
        DWF.role = role;
        // require_role("engineer") côté API : owner/admin/engineer écrivent.
        DWF.peutEcrire = !!role && ['owner', 'admin', 'engineer', 'superadmin'].includes(role);
    } catch (e) {
        // En cas de doute : lecture seule côté affichage (le backend tranche).
        DWF.role = null;
        DWF.peutEcrire = false;
    }
    appliquerPermissionsDwf();
}

function appliquerPermissionsDwf() {
    const btn = document.getElementById('btn-dwf-nouveau');
    if (btn) btn.style.display = DWF.peutEcrire ? '' : 'none';
    const note = document.getElementById('dwf-note-lecture-seule');
    if (note) note.style.display = DWF.peutEcrire ? 'none' : 'block';
}

// ---------------------------------------------------------------------------
// Chargement des données
// ---------------------------------------------------------------------------
function _dwfClusterActif() {
    const chk = document.getElementById('dwf-chk-bassin-seul');
    if (chk && !chk.checked) return null;
    const cid = window._selectedClusterId
        || (window._dernierResultatSimulation && window._dernierResultatSimulation.meta ? window._dernierResultatSimulation.meta.cluster_id : null);
    if (!cid || String(cid).trim().toLowerCase() === 'tous') return null;
    return String(cid).trim();
}

window.onToggleDwfBassinSeul = async function() {
    await Promise.all([chargerApportsDwf(), chargerIncompatiblesDwf()]);
    rendreCompteursDwf();
    rendreZoneReconciliationDwf();
    rendreListeDwf();
};

async function chargerApportsDwf() {
    const cid = _dwfClusterActif();
    const params = [];
    if (DWF.projectId) params.push(`project_id=${encodeURIComponent(DWF.projectId)}`);
    if (cid) params.push(`cluster_id=${encodeURIComponent(cid)}`);
    const qs = params.length ? `?${params.join('&')}` : '';
    var _urlApports = `/api/v1/apports${qs}`;
    if (typeof window._urlAvecSnapshot === 'function') _urlApports = window._urlAvecSnapshot(_urlApports);
    DWF.apports = await dwfFetch(_urlApports);
    if (!Array.isArray(DWF.apports)) DWF.apports = [];
}

async function chargerIncompatiblesDwf() {
    const cid = _dwfClusterActif();
    const params = [];
    if (DWF.projectId) params.push(`project_id=${encodeURIComponent(DWF.projectId)}`);
    if (cid) params.push(`cluster_id=${encodeURIComponent(cid)}`);
    const qs = params.length ? `?${params.join('&')}` : '';
    const res = await dwfFetch(`/api/v1/apports/a-reconcilier${qs}`);
    DWF.incompatibles = (res && Array.isArray(res.incompatibles)) ? res.incompatibles : [];
    DWF.reseauCourant = (res && res.reseau_courant) || null;
    DWF.erreurReseau = (res && res.erreur) || null;
}

async function chargerProfilsDwf() {
    DWF.profils = await dwfFetch('/api/v1/apports/profils');
    if (!Array.isArray(DWF.profils)) DWF.profils = [];
    DWF_LABELS.profil = {};
    DWF.profils.forEach(p => { DWF_LABELS.profil[p.key] = p.nom || p.key; });
    remplirSelectProfilsDwf();
}

async function chargerNoeudsDwf() {
    const pid = DWF.projectId ? `project_id=${encodeURIComponent(DWF.projectId)}` : '';
    // Détection intelligente du cluster/bassin actif
    const activeCluster = window._selectedClusterId
        || (window._dernierResultatSimulation && window._dernierResultatSimulation.meta ? window._dernierResultatSimulation.meta.cluster_id : null);
    
    let urlNoeuds = `/api/v1/apports/noeuds?${pid}&connectes_seulement=true`;
    if (activeCluster) {
        urlNoeuds += `&cluster_id=${encodeURIComponent(activeCluster)}`;
    }
    if (typeof window._urlAvecSnapshot === 'function') urlNoeuds = window._urlAvecSnapshot(urlNoeuds);
    
    const res = await dwfFetch(urlNoeuds);
    DWF.noeuds = (res && Array.isArray(res.noeuds)) ? res.noeuds : [];
    DWF.noeudsMeta = res || {};
    
    const dl = document.getElementById('dwf-liste-noeuds');
    if (dl) dl.innerHTML = DWF.noeuds.map(n => `<option value="${dwfEchapper(n)}">`).join('');
    
    const aide = document.getElementById('dwf-f-node-aide');
    if (aide) {
        if (activeCluster && res && res.cluster_id) {
            aide.innerHTML = `<span style="color:#34d399;"><i class="fas fa-check-circle me-1"></i><b>${DWF.noeuds.length} regards connectés</b> au bassin actif (${dwfEchapper(activeCluster)})</span>`;
        } else if (res && res.nb_connectes) {
            aide.innerHTML = `<span style="color:#38bdf8;"><i class="fas fa-network-wired me-1"></i><b>${DWF.noeuds.length} regards connectés</b> au réseau hydraulique</span>`;
        } else {
            aide.innerHTML = `<span style="color:#94a3b8;"><i class="fas fa-info-circle me-1"></i>${DWF.noeuds.length} regards disponibles</span>`;
        }
    }
}

window.actualiserDwf = async function() {
    if (!DWF.projectId) return;
    DWF.statut('Actualisation…', 'info');
    await Promise.all([chargerApportsDwf(), chargerIncompatiblesDwf()]);
    rendreCompteursDwf();
    rendreZoneReconciliationDwf();
    rendreListeDwf();
    if (typeof window.chargerInfosDwfSimulation === 'function') {
        window.chargerInfosDwfSimulation();
    }
    DWF.statut('Données actualisées.', 'ok');
};

// ---------------------------------------------------------------------------
// Rendu — compteurs, statut, réconciliation, liste
// ---------------------------------------------------------------------------
DWF.statut = function(msg, type) {
    const el = document.getElementById('dwf-statut');
    if (!el) return;
    const colors = { info: '#94a3b8', ok: '#34d399', warn: '#fbbf24', err: '#f87171' };
    el.style.color = colors[type] || colors.info;
    el.textContent = msg;
};

function incompatParApport() {
    const m = {};
    DWF.incompatibles.forEach(d => { if (d.apport_id) m[d.apport_id] = d; });
    return m;
}

function rendreCompteursDwf() {
    const actifs = DWF.apports.filter(a => a.actif).length;
    const c1 = document.getElementById('dwf-cpt-actifs');
    if (c1) c1.innerHTML = `<i class="fas fa-check-circle me-1"></i>${actifs} actif(s)`;
    const c2 = document.getElementById('dwf-cpt-incompat');
    if (c2) {
        const n = DWF.incompatibles.length;
        c2.style.display = n > 0 ? '' : 'none';
        c2.innerHTML = `<i class="fas fa-exclamation-triangle me-1"></i>${n} à réconcilier`;
    }
}

function rendreZoneReconciliationDwf() {
    const zone = document.getElementById('dwf-zone-reconcil');
    const liste = document.getElementById('dwf-liste-incompat');
    const alerte = document.getElementById('dwf-alerte-reseau');
    if (!zone || !liste) return;

    // Alerte réseau indisponible : explicite, jamais assimilée à "rien à faire"
    if (DWF.reseauCourant && DWF.reseauCourant.disponible === false) {
        zone.style.display = 'block';
        if (alerte) {
            alerte.style.display = 'block';
            alerte.innerHTML = `<i class="fas fa-exclamation-circle me-2"></i><strong>Réseau GPKG courant indisponible.</strong> ${dwfEchapper(DWF.erreurReseau || 'La version du GeoPackage ne peut pas être résolue.')}`;
        }
        liste.innerHTML = DWF.incompatibles.map(d => carteIncompatibiliteDwf(d)).join('');
        return;
    }
    if (alerte) alerte.style.display = 'none';

    if (!DWF.incompatibles.length) {
        zone.style.display = 'none';
        liste.innerHTML = '';
        return;
    }
    zone.style.display = 'block';

    const orphelins = DWF.incompatibles.filter(d => d.noeud_present === false);
    const peut = DWF.peutEcrire;
    let purgeBanner = '';
    if (orphelins.length > 0 && peut) {
        purgeBanner = `
        <div style="background: rgba(239,68,68,0.12); border: 1.5px solid rgba(239,68,68,0.5); border-radius: 10px; padding: 12px 16px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap;">
            <div>
                <div style="font-weight: 800; color: #fca5a5; font-size: 0.86rem; display: flex; align-items: center; gap: 7px;">
                    <i class="fas fa-broom" style="color: #f87171;"></i> ${orphelins.length} apport(s) d'un réseau antérieur détecté(s)
                </div>
                <div style="font-size: 0.74rem; color: #cbd5e1; margin-top: 3px; line-height: 1.4;">
                    Ces apports proviennent d'une configuration antérieure et ciblent des regards inexistants dans le réseau actif. Vous pouvez les purger immédiatement en 1 clic.
                </div>
            </div>
            <button onclick="purgerApportsOrphelinsDwf()" style="background: #dc2626; color: white; border: none; font-weight: 700; padding: 8px 16px; border-radius: 8px; cursor: pointer; font-size: 0.78rem; display: flex; align-items: center; gap: 6px; box-shadow: 0 4px 12px rgba(220,38,38,0.45); white-space: nowrap;">
                <i class="fas fa-trash"></i> Purger les ${orphelins.length} apport(s) orphelin(s)
            </button>
        </div>`;
    }

    liste.innerHTML = purgeBanner + DWF.incompatibles.map(d => carteIncompatibiliteDwf(d)).join('');
}

function carteIncompatibiliteDwf(d) {
    const peut = DWF.peutEcrire;
    const estOrphelin = (d.noeud_present === false);
    return `
    <div style="background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.4); border-radius: 10px; padding: 12px 14px;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; flex-wrap: wrap;">
            <div style="flex: 1; min-width: 260px;">
                <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 5px;">
                    <span style="font-weight: 800; color: #fca5a5; font-size: 0.9rem;"><i class="fas fa-map-marker-alt me-1"></i>${dwfEchapper(d.node_id || '—')}</span>
                    <span style="font-size: 0.68rem; background: rgba(239,68,68,0.2); color: #fca5a5; border: 1px solid rgba(239,68,68,0.4); padding: 2px 8px; border-radius: 4px; font-weight: 800;">${dwfEchapper(d.code || 'incompatible')}</span>
                    ${estOrphelin ? `<span style="font-size: 0.68rem; background: rgba(239,68,68,0.3); color: #fca5a5; border: 1px solid rgba(239,68,68,0.6); padding: 2px 8px; border-radius: 4px; font-weight: 800;"><i class="fas fa-unlink me-1"></i>Regard absent du réseau</span>` : ''}
                </div>
                <div style="font-size: 0.78rem; color: #cbd5e1; line-height: 1.45;">${dwfEchapper(d.motif || '')}</div>
                <div style="font-size: 0.72rem; color: #94a3b8; margin-top: 5px;">
                    <i class="fas fa-stamp me-1"></i>Apport : ${d.apport_gpkg_sha256 ? dwfEchapper(String(d.apport_gpkg_sha256).slice(0, 12)) + '…' : 'non estampillé'}${d.apport_gpkg_version_id ? ' · v ' + dwfEchapper(String(d.apport_gpkg_version_id).slice(0, 8)) : ''}
                    &nbsp;→&nbsp;Réseau : ${d.simulation_gpkg_sha256 ? dwfEchapper(String(d.simulation_gpkg_sha256).slice(0, 12)) + '…' : '—'}${d.simulation_gpkg_version_id ? ' · v ' + dwfEchapper(String(d.simulation_gpkg_version_id).slice(0, 8)) : ' · legacy'}
                </div>
                <div style="font-size: 0.76rem; color: #fbbf24; margin-top: 4px;"><i class="fas fa-wrench me-1"></i>${dwfEchapper(d.action_attendue || '')}</div>
            </div>
            ${peut ? (estOrphelin ? `
                <button onclick="supprimerApportDwf('${dwfEchapper(d.apport_id)}', '${dwfEchapper(d.node_id)}')" class="btn btn-sm" style="background: rgba(239,68,68,0.22); color: #fca5a5; border: 1px solid rgba(239,68,68,0.5); font-weight: 700; padding: 7px 12px; border-radius: 7px; cursor: pointer; font-size: 0.76rem; white-space: nowrap;">
                    <i class="fas fa-trash me-1"></i>Supprimer l'apport obsolète</button>
            ` : `
                <button onclick="revaliderApportDwf('${dwfEchapper(d.apport_id)}')" class="btn btn-sm" style="background: #dc2626; color: white; border: none; font-weight: 700; padding: 7px 12px; border-radius: 7px; cursor: pointer; font-size: 0.76rem; white-space: nowrap;">
                    <i class="fas fa-link me-1"></i>Revalider</button>
            `) : ''}
        </div>
    </div>`;
}

window.purgerApportsOrphelinsDwf = async function() {
    if (!DWF.peutEcrire) return;
    if (!confirm('Supprimer définitivement tous les apports obsolètes dont le regard n\'existe pas dans le réseau actuel ?')) return;
    try {
        DWF.statut('Purge des apports obsolètes en cours…', 'info');
        const pid = DWF.projectId ? `?project_id=${encodeURIComponent(DWF.projectId)}` : '';
        const res = await dwfFetch(`/api/v1/apports/purger-orphelins${pid}`, { method: 'POST' });
        await actualiserDwf();
        DWF.statut(`${res && res.supprimes_count != null ? res.supprimes_count : 'Les'} apport(s) obsolète(s) ont été purgé(s) avec succès.`, 'ok');
    } catch (e) {
        DWF.statut('Erreur purge : ' + e.message, 'err');
    }
};

function statutApportDwf(a, incMap) {
    if (incMap[a.id]) {
        const estOrph = incMap[a.id].noeud_present === false;
        return {
            label: estOrph ? 'Réseau antérieur' : 'Incompatible',
            color: '#f87171',
            bg: 'rgba(239,68,68,0.18)',
            code: estOrph ? 'noeud_absent' : incMap[a.id].code
        };
    }
    if (!a.actif) return { label: 'Inactif', color: '#94a3b8', bg: 'rgba(148,163,184,0.12)' };
    if (!a.gpkg_sha256 && !a.gpkg_version_id) return { label: 'À réconcilier', color: '#fbbf24', bg: 'rgba(245,158,11,0.15)' };
    return { label: 'Actif', color: '#34d399', bg: 'rgba(16,185,129,0.15)' };
}
