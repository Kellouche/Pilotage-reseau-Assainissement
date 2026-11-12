/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
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
    definirFiltreDwf('tous');
    montrerVueDwf('liste');
    await initialiserDwf();
};

window.fermerModalApportsDwf = function() {
    const el = document.getElementById('modal-apports-dwf');
    if (el) el.style.display = 'none';
    detruireChartDwf();
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
async function chargerApportsDwf() {
    const pid = DWF.projectId ? `?project_id=${encodeURIComponent(DWF.projectId)}` : '';
    DWF.apports = await dwfFetch(`/api/v1/apports${pid}`);
    if (!Array.isArray(DWF.apports)) DWF.apports = [];
}

async function chargerIncompatiblesDwf() {
    const pid = DWF.projectId ? `?project_id=${encodeURIComponent(DWF.projectId)}` : '';
    const res = await dwfFetch(`/api/v1/apports/a-reconcilier${pid}`);
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
    const pid = DWF.projectId ? `?project_id=${encodeURIComponent(DWF.projectId)}` : '';
    const res = await dwfFetch(`/api/v1/apports/noeuds${pid}`);
    DWF.noeuds = (res && Array.isArray(res.noeuds)) ? res.noeuds : [];
    const dl = document.getElementById('dwf-liste-noeuds');
    if (dl) dl.innerHTML = DWF.noeuds.map(n => `<option value="${dwfEchapper(n)}">`).join('');
}

window.actualiserDwf = async function() {
    if (!DWF.projectId) return;
    DWF.statut('Actualisation…', 'info');
    await Promise.all([chargerApportsDwf(), chargerIncompatiblesDwf()]);
    rendreCompteursDwf();
    rendreZoneReconciliationDwf();
    rendreListeDwf();
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
    liste.innerHTML = DWF.incompatibles.map(d => carteIncompatibiliteDwf(d)).join('');
}

function carteIncompatibiliteDwf(d) {
    const peut = DWF.peutEcrire;
    return `
    <div style="background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.4); border-radius: 10px; padding: 12px 14px;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; flex-wrap: wrap;">
            <div style="flex: 1; min-width: 260px;">
                <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 5px;">
                    <span style="font-weight: 800; color: #fca5a5; font-size: 0.9rem;"><i class="fas fa-map-marker-alt me-1"></i>${dwfEchapper(d.node_id || '—')}</span>
                    <span style="font-size: 0.68rem; background: rgba(239,68,68,0.2); color: #fca5a5; border: 1px solid rgba(239,68,68,0.4); padding: 2px 8px; border-radius: 4px; font-weight: 800;">${dwfEchapper(d.code || 'incompatible')}</span>
                </div>
                <div style="font-size: 0.78rem; color: #cbd5e1; line-height: 1.45;">${dwfEchapper(d.motif || '')}</div>
                <div style="font-size: 0.72rem; color: #94a3b8; margin-top: 5px;">
                    <i class="fas fa-stamp me-1"></i>Apport : ${d.apport_gpkg_sha256 ? dwfEchapper(String(d.apport_gpkg_sha256).slice(0, 12)) + '…' : 'non estampillé'}${d.apport_gpkg_version_id ? ' · v ' + dwfEchapper(String(d.apport_gpkg_version_id).slice(0, 8)) : ''}
                    &nbsp;→&nbsp;Réseau : ${d.simulation_gpkg_sha256 ? dwfEchapper(String(d.simulation_gpkg_sha256).slice(0, 12)) + '…' : '—'}${d.simulation_gpkg_version_id ? ' · v ' + dwfEchapper(String(d.simulation_gpkg_version_id).slice(0, 8)) : ' · legacy'}
                </div>
                <div style="font-size: 0.76rem; color: #fbbf24; margin-top: 4px;"><i class="fas fa-wrench me-1"></i>${dwfEchapper(d.action_attendue || '')}</div>
            </div>
            ${peut ? `<button onclick="revaliderApportDwf('${dwfEchapper(d.apport_id)}')" class="btn btn-sm" style="background: #dc2626; color: white; border: none; font-weight: 700; padding: 7px 12px; border-radius: 7px; cursor: pointer; font-size: 0.76rem; white-space: nowrap;">
                <i class="fas fa-link me-1"></i>Revalider</button>` : ''}
        </div>
    </div>`;
}

function statutApportDwf(a, incMap) {
    if (incMap[a.id]) return { label: 'Incompatible', color: '#f87171', bg: 'rgba(239,68,68,0.15)', code: incMap[a.id].code };
    if (!a.actif) return { label: 'Inactif', color: '#94a3b8', bg: 'rgba(148,163,184,0.12)' };
    if (!a.gpkg_sha256 && !a.gpkg_version_id) return { label: 'À réconcilier', color: '#fbbf24', bg: 'rgba(245,158,11,0.15)' };
    return { label: 'Actif', color: '#34d399', bg: 'rgba(16,185,129,0.15)' };
}

function rendreListeDwf() {
    const cont = document.getElementById('dwf-liste');
    const vide = document.getElementById('dwf-liste-vide');
    if (!cont) return;
    const incMap = incompatParApport();
    const q = (DWF.recherche || '').trim().toLowerCase();

    let liste = DWF.apports.filter(a => {
        const st = statutApportDwf(a, incMap);
        if (DWF.filtre === 'actifs' && !a.actif) return false;
        if (DWF.filtre === 'inactifs' && a.actif) return false;
        if (DWF.filtre === 'reconcilier' && st.label !== 'Incompatible' && st.label !== 'À réconcilier') return false;
        if (q && !String(a.node_id || '').toLowerCase().includes(q)) return false;
        return true;
    });

    if (!liste.length) {
        cont.innerHTML = '';
        if (vide) vide.style.display = DWF.apports.length ? 'none' : 'block';
        return;
    }
    if (vide) vide.style.display = 'none';

    cont.innerHTML = liste.map(a => carteApportDwf(a, incMap)).join('');
}

function carteApportDwf(a, incMap) {
    const st = statutApportDwf(a, incMap);
    const debitLs = (a.debit_moyen_ls !== null && a.debit_moyen_ls !== undefined)
        ? a.debit_moyen_ls : (a.debit_moyen_m3s != null ? a.debit_moyen_m3s * 1000 : null);
    const profilNom = DWF_LABELS.profil[a.profile_key] || a.profile_key;
    const peut = DWF.peutEcrire;

    const detailDebit = a.mode_determination === 'eh'
        ? `EH ${dwfFmt(a.eh, 0)} · ${dwfFmt(a.debit_specifique_l_hab_j, 0)} L/EH/j → ${dwfFmt(debitLs, 2)} L/s`
        : `${dwfFmt(debitLs, 2)} L/s (${dwfFmt(a.debit_moyen_m3s, 5)} m³/s)`;

    return `
    <div style="background: #0f172a; border: 1px solid ${st.label === 'Incompatible' ? 'rgba(239,68,68,0.45)' : 'rgba(255,255,255,0.08)'}; border-radius: 10px; padding: 12px 14px;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; flex-wrap: wrap;">
            <div style="flex: 1; min-width: 240px;">
                <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 5px;">
                    <span style="font-weight: 800; color: #f8fafc; font-size: 0.95rem;"><i class="fas fa-map-marker-alt me-1" style="color:#38bdf8;"></i>${dwfEchapper(a.node_id)}</span>
                    <span style="font-size: 0.68rem; background: ${st.bg}; color: ${st.color}; border: 1px solid ${st.color}55; padding: 2px 8px; border-radius: 4px; font-weight: 800;">${st.label}${st.code ? ' · ' + dwfEchapper(st.code) : ''}</span>
                </div>
                <div style="font-size: 0.78rem; color: #cbd5e1; line-height: 1.5;">
                    <span style="color:#94a3b8;">Nature :</span> ${dwfEchapper(DWF_LABELS.nature[a.nature] || a.nature)}
                    &nbsp;·&nbsp;<span style="color:#94a3b8;">Mode :</span> ${dwfEchapper(DWF_LABELS.mode[a.mode_determination] || a.mode_determination)}
                    &nbsp;·&nbsp;<span style="color:#94a3b8;">Profil :</span> ${dwfEchapper(profilNom)}
                </div>
                <div style="font-size: 0.82rem; color: #34d399; font-weight: 700; margin-top: 4px;">
                    <i class="fas fa-water me-1"></i>Q̄ = ${detailDebit}
                </div>
                ${a.source ? `<div style="font-size: 0.72rem; color: #64748b; margin-top: 3px;"><i class="fas fa-file-alt me-1"></i>Source : ${dwfEchapper(a.source)}</div>` : ''}
                ${a.observations ? `<div style="font-size: 0.72rem; color: #64748b; margin-top: 2px;"><i class="fas fa-sticky-note me-1"></i>${dwfEchapper(a.observations)}</div>` : ''}
            </div>
            ${peut ? `<div style="display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end;">
                <button onclick="basculerActifDwf('${dwfEchapper(a.id)}', ${a.actif ? 'false' : 'true'})" class="btn btn-sm" title="${a.actif ? 'Désactiver' : 'Activer'} l'apport"
                    style="background: ${a.actif ? 'rgba(148,163,184,0.15)' : 'rgba(16,185,129,0.15)'}; color: ${a.actif ? '#94a3b8' : '#34d399'}; border: 1px solid ${a.actif ? 'rgba(148,163,184,0.3)' : 'rgba(16,185,129,0.4)'}; padding: 6px 10px; border-radius: 7px; cursor: pointer; font-size: 0.74rem; font-weight: 700;">
                    <i class="fas ${a.actif ? 'fa-pause' : 'fa-play'} me-1"></i>${a.actif ? 'Désactiver' : 'Activer'}</button>
                <button onclick="ouvrirFormulaireDwf('${dwfEchapper(a.id)}')" class="btn btn-sm" style="background: rgba(56,189,248,0.12); color: #38bdf8; border: 1px solid rgba(56,189,248,0.35); padding: 6px 10px; border-radius: 7px; cursor: pointer; font-size: 0.74rem; font-weight: 700;">
                    <i class="fas fa-edit me-1"></i>Modifier</button>
                ${st.label === 'Incompatible' ? `<button onclick="revaliderApportDwf('${dwfEchapper(a.id)}')" class="btn btn-sm" style="background: rgba(239,68,68,0.15); color: #fca5a5; border: 1px solid rgba(239,68,68,0.4); padding: 6px 10px; border-radius: 7px; cursor: pointer; font-size: 0.74rem; font-weight: 700;">
                    <i class="fas fa-link me-1"></i>Revalider</button>` : ''}
                <button onclick="supprimerApportDwf('${dwfEchapper(a.id)}', '${dwfEchapper(a.node_id)}')" class="btn btn-sm" style="background: rgba(239,68,68,0.08); color: #f87171; border: 1px solid rgba(239,68,68,0.3); padding: 6px 10px; border-radius: 7px; cursor: pointer; font-size: 0.74rem; font-weight: 700;">
                    <i class="fas fa-trash me-1"></i></button>
            </div>` : `<div style="font-size: 0.72rem; color: #475569; align-self: center;"><i class="fas fa-eye me-1"></i>Lecture seule</div>`}
        </div>
    </div>`;
}

window.definirFiltreDwf = function(f) {
    DWF.filtre = f;
    document.querySelectorAll('.dwf-filtre-btn').forEach(b => {
        const actif = b.dataset.filtre === f;
        b.style.background = actif ? 'rgba(56,189,248,0.15)' : 'transparent';
        b.style.color = actif ? '#38bdf8' : '#94a3b8';
        b.style.borderColor = actif ? 'rgba(56,189,248,0.4)' : 'rgba(255,255,255,0.12)';
    });
    rendreListeDwf();
};

// ---------------------------------------------------------------------------
// Actions : activation, suppression, revalidation
// ---------------------------------------------------------------------------
window.basculerActifDwf = async function(id, actif) {
    if (!DWF.peutEcrire) return;
    try {
        DWF.statut('Mise à jour…', 'info');
        await dwfFetch(`/api/v1/apports/${encodeURIComponent(id)}`, {
            method: 'PUT',
            body: JSON.stringify({ actif: actif }),
        });
        await actualiserDwf();
        DWF.statut(actif ? 'Apport activé.' : 'Apport désactivé.', 'ok');
    } catch (e) {
        DWF.statut('Erreur : ' + e.message, 'err');
    }
};

window.supprimerApportDwf = async function(id, nodeId) {
    if (!DWF.peutEcrire) return;
    if (!confirm(`Supprimer définitivement l'apport DWF du nœud « ${nodeId} » ?\nCette action est irréversible.`)) return;
    try {
        DWF.statut('Suppression…', 'info');
        await dwfFetch(`/api/v1/apports/${encodeURIComponent(id)}`, { method: 'DELETE' });
        await actualiserDwf();
        DWF.statut('Apport supprimé.', 'ok');
    } catch (e) {
        if (e.status === 404) DWF.statut('Apport introuvable (déjà supprimé ?).', 'warn');
        else if (e.status === 403) DWF.statut('Action réservée aux ingénieurs.', 'err');
        else DWF.statut('Erreur : ' + e.message, 'err');
    }
};

window.revaliderApportDwf = async function(id) {
    if (!DWF.peutEcrire) return;
    try {
        DWF.statut('Revalidation de l\'apport sur le réseau courant…', 'info');
        await dwfFetch(`/api/v1/apports/${encodeURIComponent(id)}/revalider`, { method: 'POST' });
        await actualiserDwf();
        DWF.statut('Apport ré-estampillé sur la version courante du réseau.', 'ok');
    } catch (e) {
        if (e.status === 422) {
            DWF.statut('Revalidation refusée : ' + e.message, 'err');
        } else if (e.status === 404) {
            DWF.statut('Apport introuvable.', 'err');
        } else {
            DWF.statut('Erreur : ' + e.message, 'err');
        }
        // Rafraîchir quand même : l'état réel a pu changer
        try { await actualiserDwf(); } catch (_) {}
    }
};

// ---------------------------------------------------------------------------
// Formulaire création / modification
// ---------------------------------------------------------------------------
window.ouvrirFormulaireDwf = async function(id) {
    DWF.editingId = id || null;
    montrerVueDwf('form');
    const titre = document.getElementById('dwf-form-titre');
    if (titre) {
        titre.innerHTML = id
            ? '<i class="fas fa-edit me-1"></i> Modifier l\'apport DWF'
            : '<i class="fas fa-plus-circle me-1"></i> Nouvel apport DWF';
    }
    // Réinitialiser
    ['dwf-f-node','dwf-f-source','dwf-f-observations'].forEach(fid => {
        const el = document.getElementById(fid); if (el) el.value = '';
    });
    const deb = document.getElementById('dwf-f-debit'); if (deb) deb.value = '';
    const eh = document.getElementById('dwf-f-eh'); if (eh) eh.value = '';
    const ds = document.getElementById('dwf-f-debitspec'); if (ds) ds.value = '200';
    const act = document.getElementById('dwf-f-actif'); if (act) act.checked = true;
    document.getElementById('dwf-f-nature').value = 'domestique';
    masquerMessageFormDwf();
    definirModeDwf('debit');

    // Nœuds (lazy, à chaque ouverture pour rester à jour)
    try { await chargerNoeudsDwf(); }
    catch (e) { console.warn('Chargement nœuds DWF:', e); }

    if (id) {
        const a = DWF.apports.find(x => x.id === id);
        if (!a) { retourListeDwf(); return; }
        document.getElementById('dwf-f-node').value = a.node_id || '';
        document.getElementById('dwf-f-nature').value = a.nature || 'domestique';
        definirModeDwf(a.mode_determination === 'eh' ? 'eh' : 'debit');
        if (a.mode_determination === 'eh') {
            const e1 = document.getElementById('dwf-f-eh'); if (e1) e1.value = a.eh ?? '';
            const e2 = document.getElementById('dwf-f-debitspec'); if (e2) e2.value = a.debit_specifique_l_hab_j ?? '200';
        } else {
            const d = document.getElementById('dwf-f-debit'); if (d) d.value = a.debit_moyen_m3s ?? '';
        }
        if (a.profile_key) document.getElementById('dwf-f-profil').value = a.profile_key;
        const s = document.getElementById('dwf-f-source'); if (s) s.value = a.source || '';
        const o = document.getElementById('dwf-f-observations'); if (o) o.value = a.observations || '';
        const ac = document.getElementById('dwf-f-actif'); if (ac) ac.checked = !!a.actif;
    } else {
        // Profil par défaut : journalier type si disponible, sinon constant
        const sel = document.getElementById('dwf-f-profil');
        if (sel) sel.value = DWF.profils.some(p => p.key === 'journalier_type') ? 'journalier_type' : (DWF.profils[0] && DWF.profils[0].key) || '';
    }
    afficherApercuProfilDwf();
    mettreAJourAidesDwf();
}

window.retourListeDwf = function() {
    montrerVueDwf('liste');
    detruireChartDwf();
    masquerMessageFormDwf();
};

function montrerVueDwf(vue) {
    const l = document.getElementById('dwf-vue-liste');
    const f = document.getElementById('dwf-vue-form');
    if (l) l.style.display = vue === 'liste' ? '' : 'none';
    if (f) f.style.display = vue === 'form' ? '' : 'none';
}

window.definirModeDwf = function(mode) {
    DWF.mode = mode;
    const bd = document.getElementById('dwf-f-mode-debit-btn');
    const be = document.getElementById('dwf-f-mode-eh-btn');
    const blkD = document.getElementById('dwf-f-bloc-debit');
    const blkE = document.getElementById('dwf-f-bloc-eh');
    if (bd) { bd.style.background = mode === 'debit' ? 'rgba(56,189,248,0.15)' : 'transparent'; bd.style.color = mode === 'debit' ? '#38bdf8' : '#94a3b8'; bd.style.borderColor = mode === 'debit' ? 'rgba(56,189,248,0.5)' : 'rgba(255,255,255,0.12)'; }
    if (be) { be.style.background = mode === 'eh' ? 'rgba(56,189,248,0.15)' : 'transparent'; be.style.color = mode === 'eh' ? '#38bdf8' : '#94a3b8'; be.style.borderColor = mode === 'eh' ? 'rgba(56,189,248,0.5)' : 'rgba(255,255,255,0.12)'; }
    if (blkD) blkD.style.display = mode === 'debit' ? '' : 'none';
    if (blkE) blkE.style.display = mode === 'eh' ? '' : 'none';
    mettreAJourAidesDwf();
};

function mettreAJourAidesDwf() {
    // Équivalents L/s pour lisibilité
    const dEl = document.getElementById('dwf-f-debit');
    const lEl = document.getElementById('dwf-f-debit-ls');
    if (dEl && lEl) {
        const v = parseFloat(dEl.value);
        lEl.textContent = isNaN(v) ? '= — L/s'
            : `= ${dwfFmt(v * 1000, 2)} L/s (${dwfFmt(v, 6)} m³/s)`;
    }
    const ehEl = document.getElementById('dwf-f-eh');
    const dsEl = document.getElementById('dwf-f-debitspec');
    const rEl = document.getElementById('dwf-f-eh-resultat');
    if (ehEl && dsEl && rEl) {
        const eh = parseFloat(ehEl.value), ds = parseFloat(dsEl.value);
        if (!isNaN(eh) && !isNaN(ds) && eh > 0 && ds > 0) {
            const m3s = eh * ds / 1000 / 3600 / 24;   // L/EH/j → m³/s
            rEl.textContent = `Q̄ dérivé = ${dwfFmt(m3s, 6)} m³/s (${dwfFmt(m3s * 1000, 3)} L/s)`;
        } else {
            rEl.textContent = 'Q̄ dérivé = —';
        }
    }
}

// Liaison live des champs numériques → aides
['dwf-f-debit','dwf-f-eh','dwf-f-debitspec'].forEach(fid => {
    document.addEventListener('input', (e) => {
        if (e.target && e.target.id === fid) mettreAJourAidesDwf();
    });
});

function remplirSelectProfilsDwf() {
    const sel = document.getElementById('dwf-f-profil');
    if (!sel) return;
    sel.innerHTML = DWF.profils.map(p =>
        `<option value="${dwfEchapper(p.key)}">${dwfEchapper(p.nom)} — ${p.nb_facteurs} facteurs</option>`
    ).join('');
}

window.afficherApercuProfilDwf = function() {
    const sel = document.getElementById('dwf-f-profil');
    const p = DWF.profils.find(x => x.key === (sel && sel.value));
    const desc = document.getElementById('dwf-f-profil-desc');
    if (desc) desc.textContent = p ? (p.description || p.type_swmm || '') : '';
    detruireChartDwf();
    const canvas = document.getElementById('dwf-canvas-profil');
    const vide = document.getElementById('dwf-profil-vide');
    if (!p || !Array.isArray(p.facteurs_168) || !p.facteurs_168.length || typeof Chart === 'undefined') {
        if (vide) vide.style.display = 'block';
        return;
    }
    if (vide) vide.style.display = 'none';
    const moy = p.moyenne_facteurs;
    DWF.chart = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
            labels: p.facteurs_168.map((_, i) => i),
            datasets: [
                { label: `Facteur horaire — ${p.nom}`, data: p.facteurs_168,
                  borderColor: '#38bdf8', backgroundColor: 'rgba(56,189,248,0.12)',
                  borderWidth: 1.5, pointRadius: 0, tension: 0.25, fill: true },
                { label: `Moyenne (${dwfFmt(moy, 3)})`, data: p.facteurs_168.map(() => moy),
                  borderColor: '#fbbf24', borderWidth: 1, borderDash: [5, 4],
                  pointRadius: 0 },
            ],
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { labels: { color: '#cbd5e1', font: { size: 10 } } } },
            scales: {
                x: { ticks: { color: '#64748b', maxTicksLimit: 9, callback: v => v + 'h' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                y: { ticks: { color: '#64748b' }, grid: { color: 'rgba(255,255,255,0.05)' }, title: { display: true, text: 'Facteur', color: '#64748b', font: { size: 10 } } },
            },
        },
    });
};

function detruireChartDwf() {
    if (DWF.chart) { try { DWF.chart.destroy(); } catch (e) {} DWF.chart = null; }
}

function masquerMessageFormDwf() {
    const el = document.getElementById('dwf-message-form');
    if (el) { el.style.display = 'none'; el.innerHTML = ''; }
}

function afficherMessageFormDwf(msg, ok) {
    const el = document.getElementById('dwf-message-form');
    if (!el) return;
    el.style.display = 'block';
    el.style.background = ok ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)';
    el.style.border = `1px solid ${ok ? 'rgba(16,185,129,0.4)' : 'rgba(239,68,68,0.4)'}`;
    el.style.color = ok ? '#6ee7b7' : '#fca5a5';
    el.innerHTML = msg;
}

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
