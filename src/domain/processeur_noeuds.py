#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : Pilotage Réseau d'Assainissement
Numéro version : 1.0.0
Date de création : 02-04-2026
Date de modification : 02-04-2026
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

                    # Standardiser l'ID avec graphe_reseau
                    candidats_id = (
                        ligne.get('id'), ligne.get('id_noeud'), ligne.get('Code'),
                        ligne.get('CODE'), ligne.get('CODEPRR'),
                        ligne.get('IDNAOPAD'), idx
                    )
                    noeud_id = str(next(
                        (value for value in candidats_id if pd.notna(value) and str(value).strip()),
                        idx
                    ))

                    self.tous_noeuds.append({
                        'swmm_id': noeud_id,
                        'x': ligne.geometry.x,
                        'y': ligne.geometry.y,
                        'node_type': type_noeud,
                        'original_gdf': type_original,
                        'nom': ligne.get('NOM', ligne.get('NOMPRR', ligne.get('Nom'))),
                        'nom_voie': ligne.get('NOMVOIE', ligne.get('NOM_VOIE', ligne.get('NOM-VOIE'))),
                        'commune': ligne.get('COMMUNE'),
                        'adresse': ligne.get('ADRESSE'),
                        'elevation': elevation,
                        'type_ouvrage': ligne.get('TYPEOUVR', ligne.get('TYPE_OUVR', ligne.get('type_ouvrage'))),
                        'h_seuil': ligne.get('H_de_Seuil', ligne.get('H_DE_SEUIL', ligne.get('h_seuil'))),
                        'milieu_rec': ligne.get('MILIEUREC', ligne.get('MILIEU_REC', ligne.get('milieu_rec'))),
                        'zone_collecte': ligne.get('ZONECOLLE', ligne.get('ZONE_COLLE', ligne.get('zone_collecte'))),
                    })
        except Exception as e:
            logger.error(
                f"Erreur traitement couche {prefixe}: {e}"
            )
