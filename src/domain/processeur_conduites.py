#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : Pilotage Réseau d'Assainissement
Numéro version : 1.0.0
Date de création : 2026-04-02
Date de modification : 2026-04-02
Objectif : Traitement des conduites et canalisations du réseau.
Gère l'appariement des extrémités aux nœuds existants,
l'extraction des paramètres géométriques et la création
des objets conduite pour SWMM.
"""

import logging
from typing import List, Dict, Optional

import geopandas as gpd
from shapely.geometry import Point

from src.infrastructure.config import TARGET_CRS, SHAPE_MAP
from src.domain.aides import trouver_noeud_plus_proche

logger = logging.getLogger(__name__)


class ProcesseurConduites:
    """Traite les conduites du réseau."""

    def __init__(self):
        """Initialise le processeur de conduites."""
        self.toutes_conduites = []

    def traiter(
        self,
        canalisations_gdf: Optional[gpd.GeoDataFrame],
        noeuds_gdf: gpd.GeoDataFrame
    ) -> List[Dict]:
        """Traite les canalisations."""
        self.toutes_conduites = []

        if canalisations_gdf is None or canalisations_gdf.empty:
            return self.toutes_conduites

        try:
            gdf_proj = canalisations_gdf.to_crs(TARGET_CRS)
            compteur_id = 0
            nb_ignores = 0

            for idx, ligne in gdf_proj.iterrows():
                geoms_a_traiter = []

                if ligne.geometry:
                    if ligne.geometry.geom_type == 'LineString':
                        geoms_a_traiter = [ligne.geometry]
                    elif ligne.geometry.geom_type == 'MultiLineString':
                        geoms_a_traiter = list(ligne.geometry.geoms)

                for geom in geoms_a_traiter:
                    if geom.geom_type != 'LineString':
                        continue

                    id_conduite = f"C_{compteur_id}"
                    compteur_id += 1

                    point_depart = geom.coords[0]
                    id_noeud_dep = trouver_noeud_plus_proche(
                        Point(point_depart), noeuds_gdf
                    )

                    point_arrivee = geom.coords[-1]
                    id_noeud_arr = trouver_noeud_plus_proche(
                        Point(point_arrivee), noeuds_gdf
                    )

                    if not id_noeud_dep or not id_noeud_arr:
                        nb_ignores += 1
                        continue

                    longueur = max(
                        float(ligne.get('LINEAIRE', geom.length))
                        or geom.length,
                        0.1
                    )

                    forme = str(
                        ligne.get('FORMESECT', 'CIRCULAIRE')
                    ).upper()
                    forme_swmm = SHAPE_MAP.get(forme, 'CIRCULAR')

                    geom1 = float(ligne.get('DIAMETRE', 0.5)) or 0.5
                    geom2 = float(ligne.get('GDEBASE', 0.0)) or 0.0
                    geom3 = float(ligne.get('HAUTEUR', 0.0)) or 0.0

                    self.toutes_conduites.append({
                        'conduit_id': id_conduite,
                        'from_node': id_noeud_dep,
                        'to_node': id_noeud_arr,
                        'length': longueur,
                        'roughness': 0.013,
                        'in_offset': 0.0,
                        'out_offset': 0.0,
                        'init_flow': 0.0,
                        'max_flow': 0.0,
                        'shape': forme_swmm,
                        'geom1': geom1,
                        'geom2': geom2,
                        'geom3': geom3,
                        'geom4': 0.0,
                        'barrels': 1
                    })

            logger.info(
                f"{len(self.toutes_conduites)} conduites créées, "
                f"{nb_ignores} ignorées"
            )
        except Exception as e:
            logger.error(f"Erreur traitement conduites: {e}")

        return self.toutes_conduites
