# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-27
Objet : Façade de compatibilité du détecteur de clusters — code réparti dans
        detecteur_exutoires / _nommage / _bassins (règle modularité ≤600 lignes).
================================================================================
"""

from src.domain.detecteur_exutoires import *  # noqa: F401,F403
from src.domain.detecteur_exutoires import PRIORITE_EXUTOIRES_DEFAUT  # noqa: F401
from src.domain.detecteur_nommage import *  # noqa: F401,F403
from src.domain.detecteur_bassins import *  # noqa: F401,F403
