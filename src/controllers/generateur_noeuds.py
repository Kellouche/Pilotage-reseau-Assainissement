#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : Pilotage Réseau d'Assainissement
Numéro version : 1.0.0
Date de création : 2026-04-02
Date de modification : 2026-04-02
Objectif : Génération des sections de nœuds d'un fichier SWMM.
Gère les sections TITLE, OPTIONS, JUNCTIONS, OUTFALLS,
STORAGE, COORDINATES et MAP.
"""

import geopandas as gpd

from src.infrastructure.config import SWMM_CONFIG


class GenerateurNoeuds:
    """Génère les sections liées aux nœuds SWMM."""

    def __init__(self, lignes):
        """Initialise avec la référence à la liste de lignes."""
        self.lignes = lignes

    def ajouter_titre(self) -> None:
        """Ajoute la section [TITLE]."""
        self.lignes.append('[TITLE]')
        self.lignes.append(
            ";; Projet du Réseau d'Assainissement"
        )
        self.lignes.append('')

    def ajouter_options(self) -> None:
        """Ajoute la section [OPTIONS]."""
        self.lignes.append('[OPTIONS]')
        self.lignes.append(';;Option             Valeur')

        for cle, valeur in SWMM_CONFIG.items():
            self.lignes.append(f'{cle:<19} {valeur}')

        self.lignes.append('')

    def ajouter_jonctions(
        self, noeuds_gdf: gpd.GeoDataFrame
    ) -> None:
        """Ajoute la section [JUNCTIONS]."""
        self.lignes.append('[JUNCTIONS]')
        self.lignes.append(
            ';;Nom             Altitude  ProfMax   '
            'ProfInit  ProfSeuil AireBassin'
        )

        jonctions = noeuds_gdf[
            noeuds_gdf['node_type'] == 'JUNCTION'
        ]

        for idx, ligne in jonctions.iterrows():
            ligne_txt = (
                f"{ligne['swmm_id']:<15} "
                f"{ligne['elevation']:>10.2f}   "
                f"{1.0:>8.2f}   {0.0:>8.2f}   "
                f"{0.0:>7.2f}   {0.0:>7.2f}"
            )
            self.lignes.append(ligne_txt)

        self.lignes.append('')

    def ajouter_exutoires(
        self, noeuds_gdf: gpd.GeoDataFrame
    ) -> None:
        """Ajoute la section [OUTFALLS]."""
        self.lignes.append('[OUTFALLS]')
        self.lignes.append(
            ';;Nom             Altitude  Type      '
            'DonneesSeuil Barrage'
        )

        exutoires = noeuds_gdf[
            noeuds_gdf['node_type'] == 'OUTFALL'
        ]

        for idx, ligne in exutoires.iterrows():
            ligne_txt = (
                f"{ligne['swmm_id']:<15} "
                f"{ligne['elevation']:>10.2f}     LIBRE       "
                f"{'0.0':>9}          NON"
            )
            self.lignes.append(ligne_txt)

        self.lignes.append('')

    def ajouter_stockage(self) -> None:
        """Ajoute la section [STORAGE] vide."""
        self.lignes.append('[STORAGE]')
        self.lignes.append(
            ';;Nom             Altitude  ProfMax   '
            'ProfInit  Forme     Courbe     AireBassin'
        )
        self.lignes.append('')

    def ajouter_coordonnees(
        self, noeuds_gdf: gpd.GeoDataFrame
    ) -> None:
        """Ajoute la section [COORDINATES]."""
        self.lignes.append('[COORDINATES]')
        self.lignes.append(
            ';;Noeud           X-Coord          Y-Coord'
        )

        for idx, ligne in noeuds_gdf.iterrows():
            ligne_txt = (
                f"{ligne['swmm_id']:<15} "
                f"{ligne['x']:>15.2f}   "
                f"{ligne['y']:>15.2f}"
            )
            self.lignes.append(ligne_txt)

        self.lignes.append('')

    def ajouter_carte(self) -> None:
        """Ajoute la section [MAP]."""
        self.lignes.append('[MAP]')
        self.lignes.append(
            'DIMENSIONS 345019.85 4006157.97 '
            '355571.83 3998866.65'
        )
        self.lignes.append('UNITS      METERS')
        self.lignes.append('')
