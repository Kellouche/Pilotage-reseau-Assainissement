# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Constantes hydrauliques, typologies de sol et scénarios pluviométriques SWMM
================================================================================
"""

import os
import re
import math
import logging
from typing import Dict, Any
import pandas as pd

# Stabilisation critique de la mémoire OpenBLAS / NumPy sous Windows
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

logger = logging.getLogger("swmm_platform.moteur_swmm.constants")
_EXUTOIRES_MAP_CACHE: Dict[str, Dict[str, Any]] = {}


def _clean_node_id(val: Any, fallback: str = "") -> str:
    """Normalise proprement un identifiant de nœud sans espaces ni caractères invalides pour SWMM."""
    if val is None or (isinstance(val, float) and (math.isnan(val) or pd.isna(val))):
        return fallback
    txt = str(val).strip()
    if txt.endswith(".0"):
        txt = txt[:-2]
    txt = re.sub(r'[\s;\'",]+', '_', txt).strip('_')
    if not txt or txt.lower() in ('nan', 'none', 'null'):
        return fallback
    return txt


_LEGACY_SCENARIOS = {
    "pluie_decennale": {
        "nom": "Station ANRH Mascara — Pluie Décennale (T = 10 ans) [Référence Validée]",
        "station": "Station ANRH Mascara-Ghriss (Bassin Macta - Réf. 040702)",
        "periode_retour": "T = 10 ans (Décennale réglementaire)",
        "intensite_max_defaut": 62.0,
        "duree_heures": 4.0,
        "formule_montana": "I(t) = 6.2 · t^(-0.58) (ANRH Macta, durée critique tc = 15-30 min)",
        "coefficients_montana": {"a": 6.2, "b": 0.58},
        "hauteur_p24_mm": 58.5,
        "hauteur_totale_mm": 36.5,
        "source": "ANRH Direction Régionale Ouest / Banque Hydro-Météo Mascara (Séries 1970-2020)",
        "description": "Pluie d'orage décennale réglementaire de référence selon les séries statistiques ANRH Mascara (P24 = 58.5 mm, formule Montana a=6.2, b=0.58, pic Chicago centré Imax = 62.0 mm/h).",
        "timeseries": [
            ("00:00", 0.0),
            ("00:15", 5.5),
            ("00:30", 15.0),
            ("00:45", 37.0),
            ("01:00", 62.0),
            ("01:15", 30.0),
            ("01:30", 13.5),
            ("01:45", 6.8),
            ("02:00", 2.0),
            ("03:00", 0.0),
            ("04:00", 0.0),
        ]
    },
    "pluie_cinquantennale": {
        "nom": "Station ANRH Mascara — Pluie Cinquantennale (T = 50 ans) [Crise Majeure]",
        "station": "Station ANRH Mascara-Ghriss (Bassin Macta - Réf. 040702)",
        "periode_retour": "T = 50 ans (Cinquantennale)",
        "intensite_max_defaut": 85.0,
        "duree_heures": 4.0,
        "formule_montana": "I(t) = 8.1 · t^(-0.56)",
        "coefficients_montana": {"a": 8.1, "b": 0.56},
        "hauteur_p24_mm": 82.0,
        "hauteur_totale_mm": 54.0,
        "source": "ANRH Direction Régionale Ouest / Loi de Gumbel Mascara",
        "description": "Événement pluvieux exceptionnel cinquantennal ANRH Mascara (P24 = 82.0 mm, pic Chicago Imax = 85.0 mm/h) simulant une crise d'inondation majeure.",
        "timeseries": [
            ("00:00", 0.0),
            ("00:15", 8.0),
            ("00:30", 22.0),
            ("00:45", 52.0),
            ("01:00", 85.0),
            ("01:15", 42.0),
            ("01:30", 19.0),
            ("01:45", 9.5),
            ("02:00", 3.0),
            ("03:00", 0.0),
            ("04:00", 0.0),
        ]
    },
    "pluie_centennale": {
        "nom": "Station ANRH Mascara — Pluie Centennale (T = 100 ans) [Crue Historique]",
        "station": "Station ANRH Mascara-Ghriss (Bassin Macta - Réf. 040702)",
        "periode_retour": "T = 100 ans (Centennale)",
        "intensite_max_defaut": 110.0,
        "duree_heures": 4.0,
        "formule_montana": "I(t) = 9.8 · t^(-0.55)",
        "coefficients_montana": {"a": 9.8, "b": 0.55},
        "hauteur_p24_mm": 102.0,
        "hauteur_totale_mm": 72.0,
        "source": "ANRH Direction Régionale Ouest / Extrêmes Gumbel Mascara",
        "description": "Averse centennale de submersion totale ANRH Mascara (P24 = 102.0 mm, pic Chicago Imax = 110.0 mm/h).",
        "timeseries": [
            ("00:00", 0.0),
            ("00:15", 11.0),
            ("00:30", 30.0),
            ("00:45", 68.0),
            ("01:00", 110.0),
            ("01:15", 55.0),
            ("01:30", 25.0),
            ("01:45", 12.0),
            ("02:00", 4.0),
            ("03:00", 0.0),
            ("04:00", 0.0),
        ]
    },
    "pluie_biennale": {
        "nom": "Station ANRH Mascara — Pluie Biennale (T = 2 ans) [Pluie Courante]",
        "station": "Station ANRH Mascara-Ghriss (Bassin Macta - Réf. 040702)",
        "periode_retour": "T = 2 ans (Biennale)",
        "intensite_max_defaut": 38.0,
        "duree_heures": 4.0,
        "formule_montana": "I(t) = 4.2 · t^(-0.60)",
        "coefficients_montana": {"a": 4.2, "b": 0.60},
        "hauteur_p24_mm": 35.0,
        "hauteur_totale_mm": 22.5,
        "source": "ANRH Direction Régionale Ouest / Fréquentiel Mascara",
        "description": "Pluie biennale d'exploitation normale ANRH Mascara (P24 = 35.0 mm, pic Chicago Imax = 38.0 mm/h).",
        "timeseries": [
            ("00:00", 0.0),
            ("00:15", 3.5),
            ("00:30", 9.0),
            ("00:45", 23.0),
            ("01:00", 38.0),
            ("01:15", 18.0),
            ("01:30", 8.0),
            ("01:45", 4.0),
            ("02:00", 1.0),
            ("03:00", 0.0),
            ("04:00", 0.0),
        ]
    },
    "pluie_orage_2h": {
        "nom": "Orage d'Été Brutal Méditerranéen (2h — Imax = 92 mm/h)",
        "station": "Station Synoptique Régionale Ouest",
        "periode_retour": "T = 20 ans (Orage Convectif)",
        "intensite_max_defaut": 92.0,
        "duree_heures": 2.0,
        "formule_montana": "Averse orageuse convective concentrée",
        "coefficients_montana": {"a": 7.5, "b": 0.50},
        "hauteur_p24_mm": 65.0,
        "hauteur_totale_mm": 45.0,
        "source": "Données régionales Ouest algérien (Orages convectifs estivaux)",
        "description": "Averse estivale brève et intense concentrée sur 60 minutes avec pic de crête à 92.0 mm/h.",
        "timeseries": [
            ("00:00", 0.0),
            ("00:10", 12.0),
            ("00:20", 38.0),
            ("00:30", 92.0),
            ("00:40", 55.0),
            ("00:50", 18.0),
            ("01:00", 4.0),
            ("02:00", 0.0),
        ]
    },
    "temps_sec_pur": {
        "nom": "Temps Sec Pur (Étiage / Eaux Usées sans pluie)",
        "station": "Régime d'Étiage Sans Précipitation",
        "periode_retour": "Régime Permanent DWF",
        "intensite_max_defaut": 0.0,
        "duree_heures": 24.0,
        "formule_montana": "I = 0 mm/h",
        "coefficients_montana": {"a": 0.0, "b": 0.0},
        "hauteur_p24_mm": 0.0,
        "hauteur_totale_mm": 0.0,
        "source": "Réseau d'assainissement par temps sec",
        "description": "Simulation d'étiage et de transit des eaux usées domestiques sans précipitation.",
        "timeseries": [
            ("00:00", 0.0),
            ("24:00", 0.0)
        ]
    },
    "personnalise": {
        "nom": "✏️ Saisie Manuelle Ingénieur (Intensité Personnalisée)",
        "station": "Profil Pluviométrique Personnalisé par l'Utilisateur",
        "periode_retour": "Saisie Manuelle",
        "intensite_max_defaut": 62.0,
        "duree_heures": 4.0,
        "formule_montana": "Hyétogramme Chicago proportionnel à l'intensité de pointe spécifiée",
        "coefficients_montana": {"a": 6.2, "b": 0.58},
        "hauteur_p24_mm": 58.5,
        "hauteur_totale_mm": 36.5,
        "source": "Saisie Directe Utilisateur",
        "description": "Pluie de projet personnalisée générée d'après la valeur d'intensité de pointe spécifiée par l'ingénieur.",
        "timeseries": [
            ("00:00", 0.0),
            ("00:15", 5.5),
            ("00:30", 15.0),
            ("00:45", 37.0),
            ("01:00", 62.0),
            ("01:15", 30.0),
            ("01:30", 13.5),
            ("01:45", 6.8),
            ("02:00", 2.0),
            ("03:00", 0.0),
            ("04:00", 0.0),
        ]
    }
}

SCENARIOS_PLUIE = {}
try:
    from src.domain.referentiel_pluvio import generer_scenarios_swmm_pour_station
    SCENARIOS_PLUIE = generer_scenarios_swmm_pour_station("chlef_anrh_siege")
except Exception as _e_scen:
    logger.warning("Erreur chargement scénarios pluviométriques Chlef : %s", _e_scen)

if not SCENARIOS_PLUIE:
    SCENARIOS_PLUIE = _LEGACY_SCENARIOS

TYPOLOGIES_OCCUPATION_SOL = {
    "centre_urbain_dense": {
        "nom": "Centre urbain dense / Commercial (85%)",
        "description": "Tissu urbain dense, toitures jointives, cours bétonnées, voirie asphaltée continue.",
        "imperv_pct": 85.0,
        "n_imperv": 0.013,
        "n_perv": 0.20,
        "d_store_imperv": 1.5,
        "d_store_perv": 4.0,
        "c_ruissellement_ref": 0.85
    },
    "habitat_collectif": {
        "nom": "Habitat collectif / Cités denses (75%)",
        "description": "Grands ensembles (Cités 500 Logts, etc.), parkings, cours goudronnées.",
        "imperv_pct": 75.0,
        "n_imperv": 0.014,
        "n_perv": 0.22,
        "d_store_imperv": 1.8,
        "d_store_perv": 4.5,
        "c_ruissellement_ref": 0.75
    },
    "habitat_mixte": {
        "nom": "Habitat mixte / Tissu intermédiaire (65%)",
        "description": "Mélange collectif et individuel, petites parcelles (Profil standard recommandé).",
        "imperv_pct": 65.0,
        "n_imperv": 0.015,
        "n_perv": 0.25,
        "d_store_imperv": 2.0,
        "d_store_perv": 5.0,
        "c_ruissellement_ref": 0.65
    },
    "habitat_individuel": {
        "nom": "Habitat individuel / Pavillonnaire (50%)",
        "description": "Villas, maisons individuelles avec cours, jardins et passages perméables.",
        "imperv_pct": 50.0,
        "n_imperv": 0.015,
        "n_perv": 0.25,
        "d_store_imperv": 2.5,
        "d_store_perv": 5.0,
        "c_ruissellement_ref": 0.50
    },
    "zone_activites_indus": {
        "nom": "Zone industrielle & Entrepôts (80%)",
        "description": "Grandes toitures métalliques, quais de chargement, voiries lourdes.",
        "imperv_pct": 80.0,
        "n_imperv": 0.013,
        "n_perv": 0.20,
        "d_store_imperv": 1.5,
        "d_store_perv": 4.0,
        "c_ruissellement_ref": 0.80
    },
    "periurbain_semi_rural": {
        "nom": "Périurbain / Semi-rural lâche (35%)",
        "description": "Bordure d'agglomération, parcelles agricoles intercalaires, pistes non bitumées.",
        "imperv_pct": 35.0,
        "n_imperv": 0.016,
        "n_perv": 0.28,
        "d_store_imperv": 3.0,
        "d_store_perv": 6.0,
        "c_ruissellement_ref": 0.35
    },
    "espaces_verts_friches": {
        "nom": "Parcs / Espaces naturels / Friches (15%)",
        "description": "Espaces verts communaux, lits d'oueds, terres naturelles perméables.",
        "imperv_pct": 15.0,
        "n_imperv": 0.018,
        "n_perv": 0.30,
        "d_store_imperv": 4.0,
        "d_store_perv": 7.0,
        "c_ruissellement_ref": 0.15
    }
}
