/**
 * Projet : DrainPilot 5.2 — Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-27 | Date de modification : 2026-11-27
 * Objet : Liste des apports DWF, filtres, actions et formulaire (extrait de static/js/app/apports_dwf.js)
 */

function rendreListeDwf() {
    const cont = document.getElementById('dwf-liste');
    const vide = document.getElementById('dwf-liste-vide');
    if (!cont) return;
    const incMap = incompatParApport();
    const q = (DWF.recherche || '').trim().toLowerCase();

    let liste = DWF.apports.filter(a => {
        const st = statutApportDwf(a, incMap);
        if (DWF.filtre === 'courant') {
            if (st.code === 'noeud_absent') return false;
            if (st.label === 'Incompatible') return false;
            if (DWF.reseauCourant && DWF.reseauCourant.gpkg_version_id && a.gpkg_version_id && a.gpkg_version_id !== DWF.reseauCourant.gpkg_version_id) return false;
        }
        if (DWF.filtre === 'actifs' && !a.actif) return false;
        if (DWF.filtre === 'inactifs' && a.actif) return false;
        if (DWF.filtre === 'reconcilier' && st.label !== 'Incompatible' && st.label !== 'À réconcilier' && st.label !== 'Réseau antérieur') return false;
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
                ${(st.label === 'Incompatible' && st.code !== 'noeud_absent') ? `<button onclick="revaliderApportDwf('${dwfEchapper(a.id)}')" class="btn btn-sm" style="background: rgba(239,68,68,0.15); color: #fca5a5; border: 1px solid rgba(239,68,68,0.4); padding: 6px 10px; border-radius: 7px; cursor: pointer; font-size: 0.74rem; font-weight: 700;">
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
    const _ok = window.dialogueConfirmer
        ? await window.dialogueConfirmer({
            titre: 'Suppression de l’apport DWF',
            message: `Supprimer définitivement l'apport DWF du nœud « ${nodeId} » ?\nCette action est irréversible.`,
            type: 'danger',
            libelleValider: 'Supprimer',
            libelleIgnorer: 'Annuler',
        })
        : confirm(`Supprimer définitivement l'apport DWF du nœud « ${nodeId} » ?\nCette action est irréversible.`);
    if (!_ok) return;
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
