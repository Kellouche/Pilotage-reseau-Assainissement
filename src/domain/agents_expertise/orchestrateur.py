"""
Auteur : Hakim / Équipe DrainPilot
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Orchestrateur central de l'équipe multi-agents d'expertise hydraulique et d'aide à la décision.
"""

from typing import Dict, Any, Optional
import geopandas as gpd

from .agent1_diagnostic import AgentDiagnosticCausal
from .agent2_geniecivil import AgentGenieCivil
from .agent3_gdo import AgentHydrologieDurable
from .agent4_risques import AgentGestionRisques
from .agent5_finance import AgentFinancierEtVariantes
from .agent6_synthese import AgentSyntheseExecutive

def orchestrer_equipe_agents(
    sim_result: Dict[str, Any],
    canalisations_gdf: Optional[gpd.GeoDataFrame] = None
) -> Dict[str, Any]:
    """
    Exécute la chaîne complète des 6 agents d'expertise et retourne le diagnostic
    interconnecté et structuré.
    """
    kpis = sim_result.get("kpis", {})
    conduit_results = sim_result.get("conduit_results", {})
    node_results = sim_result.get("node_results", {})
    meta = sim_result.get("meta", {})

    # 1. Agent Diagnosticien
    agent_diag = AgentDiagnosticCausal()
    diag = agent_diag.analyser(kpis, conduit_results, node_results, meta, canalisations_gdf)

    # 2. Agent Génie Civil
    pente_calage = meta.get("pente_moyenne_pct") or 1.0
    agent_gc = AgentGenieCivil()
    gc = agent_gc.prescrire(diag, pente_moyenne_pct=pente_calage)

    # 3. Agent Hydrologie Durable (LID / GDO)
    agent_lid = AgentHydrologieDurable()
    lid = agent_lid.proposer_solutions(diag, kpis, meta)

    # 4. Agent Gestion des Risques
    agent_risk = AgentGestionRisques()
    risk = agent_risk.prioriser(diag, gc, lid)

    # 5. Agent Ingénierie Financière & Variantes
    agent_finance = AgentFinancierEtVariantes()
    finance = agent_finance.analyser_variantes(kpis, gc, lid, meta)

    # 6. Agent Synthèse Exécutive
    agent_exec = AgentSyntheseExecutive()
    synthese = agent_exec.generer_note(kpis, meta, diag, gc, lid, risk, finance)

    return {
        "status": "success",
        "diagnostic_causal": diag,
        "prescriptions_genie_civil": gc,
        "solutions_hydrologie_durable": lid,
        "matrice_risques": risk,
        "analyse_variantes_financiere": finance,
        "synthese_executive": synthese
    }
