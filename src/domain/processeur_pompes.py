#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : Pilotage Réseau d'Assainissement
Numéro version : 1.0.0
Date de création : 2026-04-02
Date de modification : 2026-04-02
Objectif : Traitement des pompes de relevage du réseau.
Gère l'appariement des stations de relevage aux nœuds
et la création des objets pompe pour SWMM.
"""

import logging
from typing import List, Dict, Optional

import geopandas as gpd
from shapely.geometry import Point

from src.infrastructure.config import TARGET_CRS

logger = logging.getLogger(__name__)


class ProcesseurPompes:
    """Traite les pompes du réseau."""

    def __init__(self):
        """Initialise le processeur de pompes."""
        self.toutes_pompes = []

    def traiter(
        self,
        stations_gdf: Optional[gpd.GeoDataFrame],
        noeuds_gdf: gpd.GeoDataFrame
    ) -> List[Dict]:
        """Traite les pompes basées sur les stations."""
        self.toutes_pompes = []

        if stations_gdf is None or stations_gdf.empty:
            return self.toutes_pompes

        try:
            gdf_proj = stations_gdf.to_crs(TARGET_CRS)

            for idx, ligne in gdf_proj.iterrows():
                if (ligne.geometry
                        and ligne.geometry.geom_type == 'Point'):
                    id_pompe = f"P_{idx}"
                    id_noeud_source = f"SR_{idx}"

                    noeud_source = noeuds_gdf[
                        noeuds_gdf['swmm_id'] == id_noeud_source
                    ]

                    if noeud_source.empty:
                        logger.warning(
                            f"Nœud source {id_noeud_source} "
                            f"non trouvé pour pompe {id_pompe}"
                        )
                        continue

                    position_pompe = Point(
                        ligne.geometry.x, ligne.geometry.y
                    )
                    autres_noeuds = noeuds_gdf[
                        noeuds_gdf['swmm_id'] != id_noeud_source
                    ]

                    if autres_noeuds.empty:
                        logger.warning(
                            f"Aucun nœud destination "
                            f"pour pompe {id_pompe}"
                        )
                        continue

                    distances = autres_noeuds.geometry.apply(
                        lambda geom: position_pompe.distance(geom)
                    )
                    noeud_proche = autres_noeuds.loc[
                        distances.idxmin()
                    ]
                    id_noeud_arrivee = noeud_proche['swmm_id']

                    self.toutes_pompes.append({
                        'pump_id': id_pompe,
                        'from_node': id_noeud_source,
                        'to_node': id_noeud_arrivee,
                        'pump_curve': 'GENERIC_PUMP_CURVE'
                    })

            logger.info(f"{len(self.toutes_pompes)} pompes créées")
        except Exception as e:
            logger.error(f"Erreur traitement pompes: {e}")

        return self.toutes_pompes
