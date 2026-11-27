# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-27
Objet : Façade de compatibilité des modèles ORM — le code est réparti dans
        models_core / models_network / models_simulation / models_domaine
        (règle modularité ≤600 lignes). Tous les imports
        `from api.models import X` restent valides.
================================================================================
"""

from api.database import Base  # noqa: F401
from api.models_core import *  # noqa: F401,F403
from api.models_core import _gen_uuid, _utc_now  # noqa: F401
from api.models_network import *  # noqa: F401,F403
from api.models_simulation import *  # noqa: F401,F403
from api.models_domaine import *  # noqa: F401,F403
