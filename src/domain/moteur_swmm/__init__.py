# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Point d'entrée et exports du package modulaire moteur_swmm
================================================================================
"""

from src.domain.moteur_swmm.constants import (
    _clean_node_id,
    SCENARIOS_PLUIE,
    TYPOLOGIES_OCCUPATION_SOL,
    _EXUTOIRES_MAP_CACHE,
)
from src.domain.moteur_swmm.assainissement_topologique import (
    _resoudre_altimetrie_noeuds,
    _assainir_topologie_swmm,
)
from src.domain.moteur_swmm.assemblage_inp import assembler_modele_inp_impl
from src.domain.moteur_swmm.analyse_rapport import analyser_rapport_swmm_impl
from src.domain.moteur_swmm.bilan_hydraulique import calculer_sensibilite_buffers_impl
from src.domain.moteur_swmm.execution_solver import executer_solver_swmm
from src.domain.moteur_swmm.moteur import MoteurSWMM

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

