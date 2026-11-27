# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-27
Objet : Façade de compatibilité de l'analyseur .rpt SWMM — code réparti dans
        analyse_rapport_parseurs / _enrichissements / _impl (règle ≤600 lignes).
================================================================================
"""

from src.domain.moteur_swmm.analyse_rapport_parseurs import *  # noqa: F401,F403
from src.domain.moteur_swmm.analyse_rapport_parseurs import (  # noqa: F401
    _lire_node_depth_summary,
)
from src.domain.moteur_swmm.analyse_rapport_enrichissements import *  # noqa: F401,F403
from src.domain.moteur_swmm.analyse_rapport_impl import *  # noqa: F401,F403
