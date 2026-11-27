/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-27
 * Date de modification : 2026-11-27
 * Objet : Bandeau garde-fou hydraulicien (fiabilité modèle) des recommandations multi-agents
 * ================================================================================
 */

window._multiAgentsGardeFouBanner = function(agents) {
    const gf = agents.controle_modele_hydraulique || {};
    const gfFiabilite = gf.fiabilite_modele || "SAIN";
    const gfAnomalies = gf.anomalies || [];
    const gfCouleur = gfFiabilite === "DEGRADE" ? "#ef4444" : (gfFiabilite === "A_VERIFIER" ? "#f59e0b" : "#10b981");
    const gfLibelle = gfFiabilite === "DEGRADE" ? "MODÈLE DÉGRADÉ — résultats non fiables" : (gfFiabilite === "A_VERIFIER" ? "MODÈLE À VÉRIFIER" : "Modèle hydraulique conforme");
    let gfBanner = "";
    if (gfFiabilite !== "SAIN" && gfAnomalies.length) {
        const gfItems = gfAnomalies.map(a =>
            `<div style="display:flex;gap:8px;align-items:flex-start;font-size:0.78rem;color:#e2e8f0;line-height:1.45;">
                <span style="color:${a.severite==='critique'?'#ef4444':(a.severite==='majeure'?'#f59e0b':'#94a3b8')};font-weight:800;white-space:nowrap;">[${(a.severite||'').toUpperCase()}]</span>
                <span><b style="color:#f8fafc;">${a.code||''}</b> — ${a.message||''}</span>
            </div>`).join("");
        gfBanner = `
                <div style="background: rgba(239, 68, 68, 0.07); border: 1px solid ${gfCouleur}66; border-left: 6px solid ${gfCouleur}; border-radius: 12px; padding: 12px 16px; margin-bottom: 12px;">
                    <div style="font-size: 0.85rem; font-weight: 800; color: ${gfCouleur}; margin-bottom: 8px; display:flex; align-items:center; gap:8px;">
                        <i class="fas fa-shield-alt"></i> Garde-fou hydraulicien — ${gfLibelle}
                    </div>
                    ${gfItems}
                    ${(gf.recommandations||[]).length ? `<div style="margin-top:8px;font-size:0.76rem;color:#fbbf24;"><i class="fas fa-lightbulb me-1"></i>${gf.recommandations[0]}</div>` : ""}
                </div>`;
    }
    return gfBanner;
};
