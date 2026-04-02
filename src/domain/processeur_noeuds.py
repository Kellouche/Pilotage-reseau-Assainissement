#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : Pilotage Réseau d'Assainissement
Numéro version : 1.0.0
Date de création : 2026-04-02
Date de modification : 2026-04-02
Objectif : Traitement des nœuds du réseau d'assainissement.
Regroupe les regards, rejets, ouvrages spéciaux, stations
de relevage et STEP en un GeoDataFrame unique prêt pour
la génération SWMM.
"""

import logging
from typing import Optional, Tuple

import geopandas as gpd
import pandas as pd

from src.infrastructure.config import TARGET_CRS
from src.domain.aides import obtenir_type_original

logger = logging.getLogger(__name__)


class ProcesseurNoeuds:
    """Traite les nœuds du réseau."""

    def __init__(self):
        """Initialise le processeur de nœuds."""
        self.tous_noeuds = []

    def traiter(
        self,
        regards_gdf: Optional[gpd.GeoDataFrame] = None,
        rejets_gdf: Optional[gpd.GeoDataFrame] = None,
        ouvrages_gdf: Optional[gpd.GeoDataFrame] = None,
        stations_gdf: Optional[gpd.GeoDataFrame] = None,
        step_gdf: Optional[gpd.GeoDataFrame] = None,
    ) -> Tuple[gpd.GeoDataFrame, int]:
        """Traite tous les types de nœuds."""
        self.tous_noeuds = []

        self._traiter_couche(regards_gdf, 'R', 'JUNCTION', 'HFERMSOL')
        self._traiter_couche(rejets_gdf, 'OUT', 'OUTFALL')
        self._traiter_couche(ouvrages_gdf, 'OS', 'JUNCTION')
        self._traiter_couche(stations_gdf, 'SR', 'JUNCTION')
        self._traiter_couche(step_gdf, 'STEP', 'OUTFALL')

        if not self.tous_noeuds:
            logger.warning("Aucun nœud trouvé!")
            return gpd.GeoDataFrame(), 0

        noeuds_gdf = gpd.GeoDataFrame(
            self.tous_noeuds,
            geometry=gpd.points_from_xy(
                [d['x'] for d in self.tous_noeuds],
                [d['y'] for d in self.tous_noeuds]
            ),
            crs=TARGET_CRS
        )

        logger.info(f"Total: {len(noeuds_gdf)} nœuds collectés")
        return noeuds_gdf, len(noeuds_gdf)

    def _traiter_couche(
        self,
        gdf: Optional[gpd.GeoDataFrame],
        prefixe: str,
        type_noeud: str,
        champ_elevation: Optional[str] = None
    ) -> None:
        """Traite une couche individuelle."""
        if gdf is None or gdf.empty:
            return

        try:
            gdf_proj = gdf.to_crs(TARGET_CRS)
            type_original = obtenir_type_original(prefixe)

            for idx, ligne in gdf_proj.iterrows():
                if (ligne.geometry
                        and ligne.geometry.geom_type == 'Point'):
                    elevation = 0.0
                    if (champ_elevation
                            and pd.notna(ligne.get(champ_elevation))):
                        elevation = float(ligne[champ_elevation])

                    self.tous_noeuds.append({
                        'swmm_id': f"{prefixe}_{idx}",
                        'x': ligne.geometry.x,
                        'y': ligne.geometry.y,
                        'node_type': type_noeud,
                        'original_gdf': type_original,
                        'elevation': elevation
                    })
        except Exception as e:
            logger.error(
                f"Erreur traitement couche {prefixe}: {e}"
            )
