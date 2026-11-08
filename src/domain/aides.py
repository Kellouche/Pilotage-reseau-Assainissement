#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Fiches d'aide interactive, documentation méthodologique et guides d'ingénierie
================================================================================
"""

from typing import Optional

import geopandas as gpd
from shapely.geometry import Point

from src.infrastructure.config import BUFFER_DISTANCE


def trouver_noeud_plus_proche(
    point: Point,
    noeuds_gdf: gpd.GeoDataFrame
) -> Optional[str]:
    """Trouve le nœud le plus proche d'un point donné."""
    noeuds_possibles = noeuds_gdf.cx[
        point.x - BUFFER_DISTANCE:point.x + BUFFER_DISTANCE,
        point.y - BUFFER_DISTANCE:point.y + BUFFER_DISTANCE
    ]

    if noeuds_possibles.empty:
        return None

    distances = noeuds_possibles.geometry.distance(point)
    plus_proche = noeuds_possibles.loc[distances.idxmin()]
    return plus_proche['swmm_id']


def obtenir_type_original(prefixe: str) -> str:
    """Récupère le nom du type original depuis le préfixe."""
    correspondance = {
        'R': 'regards',
        'OUT': 'rejets',
        'OS': 'ouvrages_speciaux',
        'SR': 'station_relevage',
        'STEP': 'step'
    }
    return correspondance.get(prefixe, 'inconnu')
