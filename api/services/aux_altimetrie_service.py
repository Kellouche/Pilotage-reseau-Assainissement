# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-27
Objet : Façade de compatibilité du service altimétrie — le code est réparti
        dans aux_altimetrie_grille / _regards / _apercu / _ecoulement /
        _raccordements (règle modularité ≤600 lignes). Tous les imports
        historiques `from api.services import aux_altimetrie_service`
        restent valides.
================================================================================
"""

from api.services.aux_altimetrie_grille import *  # noqa: F401,F403
from api.services.aux_altimetrie_grille import (  # noqa: F401
    RESOLUTION_CIBLE_M, K_VOISINS_IDW, PUISSANCE_IDW, DIST_MAX_TOPO_M,
    TAILLE_MAX_CELLULES, _CACHE_LOCK, _COLONNE_Z_REGEX, _zone_utm,
    _crs_metric, _COLONNE_COORD_REGEX, _detecter_colonne_z_par_valeurs,
    _extraire_xyz, pd_to_float, _charger_grille, _confiance,
)
from api.services.aux_altimetrie_regards import *  # noqa: F401,F403
from api.services.aux_altimetrie_regards import (  # noqa: F401
    _normaliser_code_regard, _lire_regards_projet, _echantillonner_grille_bilin,
)
from api.services.aux_altimetrie_apercu import *  # noqa: F401,F403
from api.services.aux_altimetrie_apercu import (  # noqa: F401
    SEUIL_COUVERTURE_INP, _PROFONDEURS_CONVERTIES, _mediane,
    _sanitiser_profondeur_m,
)
from api.services.aux_altimetrie_ecoulement import *  # noqa: F401,F403
from api.services.aux_altimetrie_ecoulement import (  # noqa: F401
    PENTE_INVERSION_FORT_PCT, PENTE_INVERSION_MOYEN_PCT,
    PENTE_LOCALE_MIN_AZIMUT_PCT, ECART_AZIMUT_OPPOSE_DEG,
    SEUIL_CONFIANCE_AZIMUT, _longueur_conduite_m, _cap_conduite_deg,
    _ecart_angulaire, _pire_confiance, _charger_contexte_altimetrie,
)
from api.services.aux_altimetrie_raccordements import *  # noqa: F401,F403
from api.services.aux_altimetrie_raccordements import (  # noqa: F401
    RACCORDEMENT_RAYON_DEFAUT_M, RACCORDEMENT_TOP_K, RACCORDEMENT_MAX_ORPHELINS,
    _coordonnees_regards_m, _azimut_vers, _score_raccordement,
)
