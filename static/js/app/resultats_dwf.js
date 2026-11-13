/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-13
 * Objet : LOT P1.5.4 — Restitution détaillée et traçable des apports DWF
 *         (provenance.apports_dwf) dans les résultats de simulation.
 *
 * Règles impératives :
 *  - source prioritaire : provenance.apports_dwf (secours : meta.apports_dwf
 *    uniquement si la provenance est absente) ;
 *  - jamais de volume, de débit instantané ni de débit total calculé ;
 *  - la somme affichée porte exclusivement sur debit_moyen_m3s des apports
 *    injectés — q_base_m3s (valeur technique du slot SWMM) n'y entre jamais ;
 *  - DWF = composante de temps sec, distincte du ruissellement et du débit
 *    de pointe à l'exutoire.
 * ================================================================================
 */

// Échappement HTML minimal pour tous les champs textuels persistés.
window.dwfEchapperHtml = function(s) {
    if (s === null || s === undefined) return '';
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
};

// Extraction de la provenance DWF de la simulation consultée.
// Retourne { source, injectes, ignores, anomalie } où source vaut
// 'provenance' | 'meta' | 'absente'. Aucune fusion des deux sources.
window.dwfExtraireProvenance = function(data) {
    const prov = (data && data.provenance && data.provenance.apports_dwf)
        || (data && data.kpis && data.kpis.provenance
            ? data.kpis.provenance.apports_dwf : null);
    const metaInj = (data && data.meta && Array.isArray(data.meta.apports_dwf))
        ? data.meta.apports_dwf : null;
    const metaIgn = (data && data.meta && Array.isArray(data.meta.apports_dwf_ignores))
        ? data.meta.apports_dwf_ignores : null;

    if (prov) {
        const injectes = Array.isArray(prov.injectes) ? prov.injectes : [];
        const ignores = Array.isArray(prov.ignores) ? prov.ignores : [];
        const metaPeuple = (metaInj && metaInj.length > 0)
            || (metaIgn && metaIgn.length > 0);
        const contradictoire = metaPeuple
            && ((metaInj ? metaInj.length : 0) !== injectes.length
                || (metaIgn ? metaIgn.length : 0) !== ignores.length);
        if (contradictoire) {
            console.warn('[DWF] Incohérence provenance/meta pour cette simulation — provenance prioritaire.');
        }
        return { source: 'provenance', injectes: injectes, ignores: ignores, anomalie: contradictoire };
    }
    // Repli historique : meta.apports_dwf / meta.apports_dwf_ignores,
    // uniquement si la provenance principale est absente.
    if ((metaInj && metaInj.length > 0) || (metaIgn && metaIgn.length > 0)) {
        return {
            source: 'meta',
            injectes: metaInj || [],
            ignores: metaIgn || [],
            anomalie: false
        };
    }
    return { source: 'absente', injectes: [], ignores: [], anomalie: false };
};

// Synthèse d'affichage : comptages + somme des débits moyens journaliers
// DÉCLARÉS des seuls apports injectés. q_base_m3s n'est jamais utilisé.
window.dwfCalculerSynthese = function(injectes) {
    const liste = Array.isArray(injectes) ? injectes : [];
    let debitCumule = 0;
    let nbDebitsValides = 0;
    const profils = new Set();
    liste.forEach(function(a) {
        const q = parseFloat(a && a.debit_moyen_m3s);
        if (isFinite(q)) {
            debitCumule += q;
            nbDebitsValides += 1;
        }
        profils.add(a && a.profile_key ? String(a.profile_key) : 'inconnu');
    });
    return {
        nb_injectes: liste.length,
        debit_cumule_m3s: debitCumule,
        nb_debits_valides: nbDebitsValides,
        profil: profils.size === 1 ? Array.from(profils)[0] : 'multiple'
    };
};

// Construit le HTML du bloc « Apports de temps sec (DWF) ».
// Fonction pure (aucun accès DOM) — testable en environnement Node.
window.dwfConstruireHtmlBloc = function(data) {
    const esc = window.dwfEchapperHtml;
    const fmtQ = function(v) {
        const n = parseFloat(v);
        return isFinite(n) ? n.toLocaleString('fr-FR', { maximumFractionDigits: 6 }) : '—';
    };
    const court = function(s, n) {
        s = String(s == null ? '' : s);
        return s.length > (n || 12) ? s.slice(0, n || 12) + '…' : s;
    };

    const res = window.dwfExtraireProvenance(data);
    const nIgn = res.ignores.length;
    const entete = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <span style="font-size:0.82rem; font-weight:800; color:#34d399; display:flex; align-items:center; gap:7px;">
                <i class="fas fa-faucet-drip"></i> Apports de temps sec (DWF)
            </span>
            <button type="button" onclick="ouvrirModalApportsDwf()" style="background:rgba(52,211,153,0.12); border:1px solid rgba(52,211,153,0.4); color:#6ee7b7; border-radius:6px; padding:3px 10px; font-size:0.72rem; font-weight:700; cursor:pointer;">
                <i class="fas fa-tools me-1"></i> Gérer les apports DWF
            </button>
        </div>`;

    const anomalieHtml = res.anomalie
        ? `
        <div style="font-size:0.7rem; color:#f87171; margin-top:6px;">
            <i class="fas fa-exclamation-triangle me-1"></i> Anomalie de cohérence détectée entre provenance et métadonnées — provenance affichée prioritairement.
        </div>` : '';

    if (res.source === 'absente') {
        return entete + `
            <div style="font-size:0.78rem; color:#94a3b8; line-height:1.45;">
                <i class="fas fa-info-circle me-1"></i> DWF non tracé — simulation antérieure ou état non documenté.
            </div>`;
    }

    const synth = window.dwfCalculerSynthese(res.injectes);

    if (synth.nb_injectes === 0 && nIgn === 0) {
        return entete + `
            <div style="font-size:0.78rem; color:#94a3b8; line-height:1.45;">
                <i class="fas fa-info-circle me-1"></i> Aucun apport DWF injecté ou enregistré pour cette simulation.
            </div>` + anomalieHtml;
    }

    const profilTxt = synth.nb_injectes === 0
        ? '—'
        : (synth.profil === 'multiple' ? 'Profils multiples' : esc(synth.profil));

    let html = entete + `
        <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap:8px; font-size:0.78rem; background:rgba(0,0,0,0.25); border-radius:6px; padding:8px 10px;">
            <div><span style="color:#94a3b8; display:block; font-size:0.7rem;">Apports injectés</span>
                <b style="color:#34d399; font-size:0.95rem;">${synth.nb_injectes}</b></div>
            <div><span style="color:#94a3b8; display:block; font-size:0.7rem;">Apports ignorés</span>
                <b style="color:#fbbf24; font-size:0.95rem;">${nIgn}</b></div>
            <div><span style="color:#94a3b8; display:block; font-size:0.7rem;">Débit moyen journalier déclaré cumulé</span>
                <b style="color:#38bdf8; font-size:0.95rem;">${fmtQ(synth.debit_cumule_m3s)} m³/s</b></div>
        </div>
        <div style="font-size:0.72rem; color:#94a3b8; margin-top:6px;">
            Profil temporel : <b style="color:#cbd5e1;">${profilTxt}</b>
            ${synth.nb_injectes > 0 ? ' — composante de temps sec, distincte du ruissellement et du débit de pointe.' : ''}
        </div>`;

    if (synth.nb_injectes > 0) {
        html += `
        <details style="margin-top:8px;">
            <summary style="cursor:pointer; font-size:0.76rem; font-weight:700; color:#6ee7b7; user-select:none;">
                <i class="fas fa-list me-1"></i> Détail des apports DWF injectés (${synth.nb_injectes})
            </summary>
            <div style="margin-top:6px; font-size:0.74rem; line-height:1.5; max-height:220px; overflow-y:auto;">`;
        res.injectes.forEach(function(a) {
            const qBase = (a && a.q_base_m3s !== undefined && a.q_base_m3s !== null)
                ? ` · <span style="color:#94a3b8;">q_base slot SWMM (technique) : ${esc(fmtQ(a.q_base_m3s))} m³/s</span>` : '';
            html += `
            <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(52,211,153,0.18); border-radius:6px; padding:7px 9px; margin-bottom:6px;">
                <div style="display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap;">
                    <span style="font-weight:800; color:#f8fafc; font-family:monospace; font-size:0.72rem;">${esc(court(a && a.apport_id, 13))}</span>
                    <span style="color:#34d399; font-weight:700;">nœud ${esc(a && a.node_id != null ? a.node_id : '—')} · ${esc(fmtQ(a && a.debit_moyen_m3s))} m³/s</span>
                </div>
                <div style="color:#94a3b8; margin-top:3px;">
                    ${esc(a && a.nature || '—')} · mode ${esc(a && a.mode_determination || '—')}
                    ${a && a.eh !== undefined && a.eh !== null ? ` · EH ${esc(a.eh)}` : ''}
                    ${a && a.debit_specifique_l_hab_j !== undefined && a.debit_specifique_l_hab_j !== null ? ` · ${esc(a.debit_specifique_l_hab_j)} L/hab/j` : ''}
                </div>
                <div style="color:#94a3b8; margin-top:2px;">
                    profil <b style="color:#cbd5e1;">${esc(a && a.profile_key || '—')}</b>
                    · méthode <b style="color:#cbd5e1;">${esc(a && a.methode_injection || '—')}</b>
                    ${a && a.pattern ? ` · pattern ${esc(a.pattern)}` : ''}
                </div>
                <div style="color:#64748b; margin-top:2px; font-size:0.7rem;">
                    GPKG v ${esc(court(a && a.gpkg_version_id, 8))} · sha ${esc(court(a && a.gpkg_sha256, 12))}${qBase}
                </div>
            </div>`;
        });
        html += `</div></details>`;
    }

    if (nIgn > 0) {
        html += `
        <details style="margin-top:6px;">
            <summary style="cursor:pointer; font-size:0.76rem; font-weight:700; color:#fbbf24; user-select:none;">
                <i class="fas fa-ban me-1"></i> Apports ignorés (${nIgn})
            </summary>
            <div style="margin-top:6px; font-size:0.74rem; line-height:1.5; max-height:160px; overflow-y:auto;">`;
        res.ignores.forEach(function(a) {
            html += `
            <div style="background:rgba(251,191,36,0.06); border:1px solid rgba(251,191,36,0.2); border-radius:6px; padding:6px 9px; margin-bottom:5px; display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap;">
                <span style="font-family:monospace; color:#fcd34d; font-size:0.72rem;">${esc(court(a && a.apport_id, 13))} · nœud ${esc(a && a.node_id != null ? a.node_id : '—')}</span>
                <span style="color:#fbbf24; font-weight:700;">${esc(a && a.motif || 'motif non renseigné')}</span>
            </div>`;
        });
        html += `</div></details>`;
    }

    return html + anomalieHtml;
};

// Point d'entrée UI : injecte le bloc dans la carte des résultats.
// Lié à l'objet `data` de la simulation consultée — aucun état global.
window.afficherBlocResultatsDwf = function(data) {
    const box = document.getElementById('sim-dwf-resultats-box');
    if (!box) return;
    box.innerHTML = window.dwfConstruireHtmlBloc(data);
    box.style.display = 'block';
};
