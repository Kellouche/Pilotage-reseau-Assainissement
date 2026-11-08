# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Module wrapper de compatibilité pour le moteur de simulation SWMM 5.2
================================================================================
"""

from src.domain.moteur_swmm import (
    MoteurSWMM,
    _clean_node_id,
    _resoudre_altimetrie_noeuds,
    _assainir_topologie_swmm,
    SCENARIOS_PLUIE,
    TYPOLOGIES_OCCUPATION_SOL,
    _EXUTOIRES_MAP_CACHE,
    assembler_modele_inp_impl,
    analyser_rapport_swmm_impl,
    calculer_sensibilite_buffers_impl,
    executer_solver_swmm,
)

__all__ = [
    "MoteurSWMM",
    "_clean_node_id",
    "_resoudre_altimetrie_noeuds",
    "_assainir_topologie_swmm",
    "SCENARIOS_PLUIE",
    "TYPOLOGIES_OCCUPATION_SOL",
    "_EXUTOIRES_MAP_CACHE",
    "assembler_modele_inp_impl",
    "analyser_rapport_swmm_impl",
    "calculer_sensibilite_buffers_impl",
    "executer_solver_swmm",
]
