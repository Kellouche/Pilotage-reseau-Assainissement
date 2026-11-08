"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Wrapper de compatibilité pour le module d'agents d'expertise IA et gestion durable des ouvrages (GDO)
================================================================================
"""

from src.domain.agents_expertise import (
    formater_cout_dzd,
    formater_montant_dzd,
    formater_nombre_fr,
    AgentDiagnosticCausal,
    AgentGenieCivil,
    AgentHydrologieDurable,
    AgentGestionRisques,
    AgentFinancierEtVariantes,
    AgentSyntheseExecutive,
    orchestrer_equipe_agents,
)

__all__ = [
    "formater_cout_dzd",
    "formater_montant_dzd",
    "formater_nombre_fr",
    "AgentDiagnosticCausal",
    "AgentGenieCivil",
    "AgentHydrologieDurable",
    "AgentGestionRisques",
    "AgentFinancierEtVariantes",
    "AgentSyntheseExecutive",
    "orchestrer_equipe_agents",
]
