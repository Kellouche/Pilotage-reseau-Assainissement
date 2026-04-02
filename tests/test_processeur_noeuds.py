#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : Pilotage Réseau d'Assainissement
Numéro version : 1.0.0
Date de création : 2026-04-02
Date de modification : 2026-04-02
Objectif : Tests unitaires pour le processeur de nœuds.
Vérifie le traitement des regards, rejets et la création
du GeoDataFrame de nœuds.
"""

import unittest
import logging

import geopandas as gpd
from shapely.geometry import Point

from src.domain.processeur_noeuds import ProcesseurNoeuds
from src.infrastructure.config import TARGET_CRS

logging.getLogger('src.domain.processeur_noeuds').setLevel(
    logging.CRITICAL
)


class TestProcesseurNoeuds(unittest.TestCase):
    """Tests pour la classe ProcesseurNoeuds."""

    def setUp(self):
        """Initialise les fixtures de test."""
        self.processeur = ProcesseurNoeuds()

        points = [
            Point(345000 + i * 100, 4000000 + i * 100)
            for i in range(5)
        ]

        self.sample_regards_gdf = gpd.GeoDataFrame({
            'HFERMSOL': [10.0, 15.0, 12.0, 14.0, 11.0],
            'geometry': points
        }, crs=TARGET_CRS)

        self.sample_rejets_gdf = gpd.GeoDataFrame({
            'geometry': points[:3]
        }, crs=TARGET_CRS)

    def test_traiter_vide(self):
        """Teste le traitement avec des données vides."""
        gdf, compte = self.processeur.traiter()
        self.assertEqual(compte, 0)
        self.assertTrue(gdf.empty)

    def test_traiter_avec_regards(self):
        """Teste le traitement des regards."""
        gdf, compte = self.processeur.traiter(
            regards_gdf=self.sample_regards_gdf
        )
        self.assertEqual(compte, 5)
        self.assertEqual(len(gdf), 5)
        self.assertTrue(
            all(gdf['node_type'] == 'JUNCTION')
        )
        self.assertEqual(gdf.iloc[0]['elevation'], 10.0)

    def test_traiter_melange(self):
        """Teste le traitement avec plusieurs types."""
        gdf, compte = self.processeur.traiter(
            regards_gdf=self.sample_regards_gdf,
            rejets_gdf=self.sample_rejets_gdf
        )
        self.assertEqual(compte, 8)

        jonctions = gdf[gdf['node_type'] == 'JUNCTION']
        exutoires = gdf[gdf['node_type'] == 'OUTFALL']
        self.assertEqual(len(jonctions), 5)
        self.assertEqual(len(exutoires), 3)


if __name__ == '__main__':
    unittest.main()
