/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Objet : Paramétrage du garde-fou hydraulicien (Agent 0) par projet.
 *
 * Consomme les contrats réels :
 *   GET  /api/v1/network/datasets                 → active_project {id, name}
 *   GET  /api/v1/auth/me                          → rôle
 *   GET  /api/v1/projets/{id}/garde-fou            → config + catalogue
 *   PUT  /api/v1/projets/{id}/garde-fou            → enregistre la config
 *   POST /api/v1/projets/{id}/garde-fou/reaudit    → ré-évalue l'historique
 * ================================================================================
 */

window.GF = {
    projectId: null,
    projectName: null,
    role: null,
    peutEcrire: false,
    catalogue: null,
    configBrute: {},
    preset: 'standard',
    profil: null,
    userSeuils: {},        // seuils modifiés manuellement {cle: valeur}
    checks: {},
    chargement: false,
};

// ---------------------------------------------------------------------------
// Helpers HTTP (même convention que apports_dwf.js)
// ---------------------------------------------------------------------------
function gfToken() { return localStorage.getItem('swmm_access_token'); }

function gfHeaders(json = false) {
    const h = {};
    const t = gfToken();
    if (t) h['Authorization'] = `Bearer ${t}`;
    if (json) h['Content-Type'] = 'application/json';
    return h;
}

async function gfFetch(url, options = {}) {
    const resp = await fetch(url, Object.assign(
        { headers: gfHeaders(!!options.body), credentials: 'include' },
        options));
    let data = null;
    try { data = await resp.json(); } catch (e) { /* pas de JSON */ }
    if (!resp.ok) {
        const err = new Error(gfExtraireDetail(data, resp.status));
        err.status = resp.status;
        err.data = data;
        throw err;
    }
    return data;
}

function gfExtraireDetail(data, status) {
    if (data && data.detail) {
        if (typeof data.detail === 'string') return data.detail;
        if (data.detail.message) return data.detail.message;
        try { return JSON.stringify(data.detail); } catch (e) { /* noop */ }
    }
    return `Erreur HTTP ${status}`;
}

function gfNotif(message, type) {
    if (window.dialogueNotifier) {
        window.dialogueNotifier({ message, type: type || 'info' });
    }
}

// ---------------------------------------------------------------------------
// Fusion des seuils (miroir de config_effective côté backend)
// ---------------------------------------------------------------------------
function gfValeursEffectives() {
    const cat = GF.catalogue || {};
    const seuilsCat = cat.seuils || {};
    const val = {};
    Object.keys(seuilsCat).forEach(k => { val[k] = Number(seuilsCat[k].defaut); });
    const preset = (cat.presets || {})[GF.preset];
    if (preset) Object.entries(preset.seuils || {}).forEach(([k, v]) => { val[k] = Number(v); });
    const profil = GF.profil ? (cat.profils_reseau || {})[GF.profil] : null;
    if (profil) Object.entries(profil.seuils || {}).forEach(([k, v]) => { val[k] = Number(v); });
    Object.entries(GF.userSeuils).forEach(([k, v]) => { val[k] = Number(v); });
    return val;
}

// ---------------------------------------------------------------------------
// Ouverture / chargement
// ---------------------------------------------------------------------------
async function ouvrirModalGardeFou() {
    const modal = document.getElementById('modal-garde-fou');
    if (!modal) return;
    modal.style.display = 'flex';
    gfStatut('Chargement du paramétrage…', 'info');
    try {
        const ds = await gfFetch('/api/v1/network/datasets?_t=' + Date.now());
        const ap = ds && ds.active_project;
        if (!ap || !ap.id) {
            gfStatut('Aucun projet actif : chargez d\'abord un réseau (modale Projet).', 'warn');
            return;
        }
        GF.projectId = ap.id;
        GF.projectName = ap.name || 'Projet actif';
        const nomEl = document.getElementById('gf-projet-nom');
        if (nomEl) nomEl.textContent = GF.projectName;

        const me = await gfFetch('/api/v1/auth/me').catch(() => null);
        GF.role = (me && (me.role || (me.user && me.user.role))) || null;
        GF.peutEcrire = !GF.role || ['owner', 'admin', 'engineer'].includes(GF.role);

        const res = await gfFetch(`/api/v1/projets/${encodeURIComponent(GF.projectId)}/garde-fou`);
        GF.catalogue = res.catalogue;
        GF.configBrute = res.config_brute || {};
        GF.preset = GF.configBrute.preset || 'standard';
        GF.profil = GF.configBrute.profil_reseau || null;
        GF.userSeuils = Object.assign({}, GF.configBrute.seuils || {});
        GF.checks = Object.assign({}, (res.catalogue.checks || {}).defauts || {});
        Object.assign(GF.checks, GF.configBrute.checks_actives || {});

        gfRendrePresets();
        gfRendreProfils();
        gfRendreChecks();
        gfRendreSeuils();
        gfAppliquerEtatEcriture();
        gfStatut('Paramétrage chargé — les seuils s\'appliquent aux prochaines simulations et au ré-audit de l\'historique.', 'ok');
    } catch (e) {
        gfStatut('Chargement impossible : ' + e.message, 'erreur');
    }
}

function fermerModalGardeFou() {
    const modal = document.getElementById('modal-garde-fou');
    if (modal) modal.style.display = 'none';
}

function gfStatut(msg, type) {
    const el = document.getElementById('gf-statut');
    if (!el) return;
    el.textContent = msg || '';
    el.style.color = type === 'erreur' ? '#f87171' : type === 'ok' ? '#34d399' : '#94a3b8';
}

// ---------------------------------------------------------------------------
// Rendu
// ---------------------------------------------------------------------------
function gfRendrePresets() {
    const cont = document.getElementById('gf-presets');
    if (!cont || !GF.catalogue) return;
    cont.innerHTML = '';
    Object.entries(GF.catalogue.presets || {}).forEach(([key, p]) => {
        const actif = GF.preset === key;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'gf-choix' + (actif ? ' actif' : '');
        btn.innerHTML = `<div class="gf-choix-titre">${p.label || key}</div>
                         <div class="gf-choix-desc">${p.description || ''}</div>`;
        btn.onclick = () => { GF.preset = key; GF.userSeuils = {}; gfRendrePresets(); gfRendreSeuils(); };
        cont.appendChild(btn);
    });
}

function gfRendreProfils() {
    const cont = document.getElementById('gf-profils');
    if (!cont || !GF.catalogue) return;
    cont.innerHTML = '';
    const btnAucun = document.createElement('button');
    btnAucun.type = 'button';
    btnAucun.className = 'gf-choix' + (!GF.profil ? ' actif' : '');
    btnAucun.innerHTML = `<div class="gf-choix-titre">Non précisé</div>
                          <div class="gf-choix-desc">Seuils pilotés par le préréglage seul.</div>`;
    btnAucun.onclick = () => { GF.profil = null; GF.userSeuils = {}; gfRendreProfils(); gfRendreSeuils(); };
    cont.appendChild(btnAucun);
    Object.entries(GF.catalogue.profils_reseau || {}).forEach(([key, p]) => {
        const actif = GF.profil === key;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'gf-choix' + (actif ? ' actif' : '');
        btn.innerHTML = `<div class="gf-choix-titre">${p.label || key}</div>
                         <div class="gf-choix-desc">${p.description || ''}</div>`;
        btn.onclick = () => {
            GF.profil = key; GF.userSeuils = {};
            const sugg = (GF.catalogue.profils_reseau[key] || {}).preset_suggere;
            if (sugg && GF.catalogue.presets && GF.catalogue.presets[sugg]) {
                GF.preset = sugg;
                gfRendrePresets();
            }
            gfRendreProfils(); gfRendreSeuils();
        };
        cont.appendChild(btn);
    });
}

function gfRendreChecks() {
    const cont = document.getElementById('gf-checks');
    if (!cont || !GF.catalogue) return;
    const codes = (GF.catalogue.checks || {}).codes || {};
    cont.innerHTML = '';
    Object.entries(codes).forEach(([code, label]) => {
        const actif = GF.checks[code] !== false;
        const div = document.createElement('label');
        div.className = 'gf-check';
        div.innerHTML = `<input type="checkbox" data-gf-check="${code}" ${actif ? 'checked' : ''}>
                         <span>${label}</span>`;
        cont.appendChild(div);
    });
}

function gfRendreSeuils() {
    const cont = document.getElementById('gf-seuils');
    if (!cont || !GF.catalogue) return;
    const val = gfValeursEffectives();
    cont.innerHTML = '';
    Object.entries(GF.catalogue.seuils || {}).forEach(([cle, meta]) => {
        const row = document.createElement('div');
        row.className = 'gf-seuil-row';
        const inputId = 'gf-seuil-' + cle;
        row.innerHTML = `
            <div class="gf-seuil-info">
                <label for="${inputId}" class="gf-seuil-label">${meta.label || cle}</label>
                <div class="gf-seuil-justif" title="${(meta.justification || '').replace(/"/g, '&quot;')}">${meta.unite || ''}</div>
            </div>
            <input type="number" step="any" id="${inputId}" class="gf-seuil-input"
                   value="${val[cle]}" data-gf-seuil="${cle}">
        `;
        cont.appendChild(row);
        const input = row.querySelector('input');
        input.addEventListener('change', () => {
            const v = parseFloat(input.value);
            if (isNaN(v)) return;
            GF.userSeuils[cle] = v;
            input.value = v;
        });
    });
}

function gfAppliquerEtatEcriture() {
    const grise = !GF.peutEcrire;
    ['gf-btn-enregistrer', 'gf-btn-reaudit'].forEach(id => {
        const b = document.getElementById(id);
        if (b) b.disabled = grise;
    });
    const note = document.getElementById('gf-note-lecture-seule');
    if (note) note.style.display = grise ? 'block' : 'none';
}

// ---------------------------------------------------------------------------
// Sauvegarde & ré-audit
// ---------------------------------------------------------------------------
async function enregistrerConfigGardeFou() {
    if (!GF.projectId || !GF.peutEcrire) return;
    gfStatut('Enregistrement…', 'info');
    try {
        const checks = {};
        document.querySelectorAll('[data-gf-check]').forEach(cb => {
            checks[cb.getAttribute('data-gf-check')] = cb.checked;
        });
        const payload = {
            preset: GF.preset,
            profil_reseau: GF.profil || null,
            seuils: GF.userSeuils,
            checks_actives: checks,
        };
        const res = await gfFetch(
            `/api/v1/projets/${encodeURIComponent(GF.projectId)}/garde-fou`,
            { method: 'PUT', body: JSON.stringify(payload) });
        GF.configBrute = res.config_brute || {};
        gfStatut('Paramétrage enregistré. Il s\'appliquera aux prochaines simulations.', 'ok');
        gfNotif('Paramétrage du contrôle qualité enregistré.', 'succes');
    } catch (e) {
        gfStatut('Enregistrement impossible : ' + e.message, 'erreur');
        gfNotif('Échec de l\'enregistrement : ' + e.message, 'erreur');
    }
}

async function reauditGardeFou() {
    if (!GF.projectId || !GF.peutEcrire) return;
    const ok = await (window.dialogueConfirmer ? window.dialogueConfirmer({
        titre: 'Ré-appliquer le contrôle qualité',
        message: 'Ré-évaluer toutes les simulations terminées de ce projet avec les seuils actuels ? Les verdicts de fiabilité seront mis à jour (résultats et historique).',
        type: 'confirmation',
        libelleValider: 'Ré-appliquer',
        libelleIgnorer: 'Annuler',
    }) : Promise.resolve(true));
    if (!ok) return;
    gfStatut('Ré-évaluation de l\'historique en cours…', 'info');
    try {
        const res = await gfFetch(
            `/api/v1/projets/${encodeURIComponent(GF.projectId)}/garde-fou/reaudit`,
            { method: 'POST', body: JSON.stringify({ appliquer: true }) });
        gfStatut(
            `Ré-audit terminé : ${res.charges}/${res.total} résultats analysés — ` +
            `${res.modifies} verdict(s) mis à jour, ${res.degrades} dégradation(s), ` +
            `${res.erreurs} erreur(s) de lecture.`, 'ok');
        gfNotif(
            `Contrôle qualité ré-appliqué : ${res.modifies} verdict(s) mis à jour, ` +
            `${res.degrades} simulation(s) dégradée(s).`,
            res.degrades > 0 ? 'erreur' : 'succes');
    } catch (e) {
        gfStatut('Ré-audit impossible : ' + e.message, 'erreur');
        gfNotif('Échec du ré-audit : ' + e.message, 'erreur');
    }
}
