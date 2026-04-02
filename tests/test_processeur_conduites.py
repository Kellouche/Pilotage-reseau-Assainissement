#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : Pilotage Réseau d'Assainissement
Numéro version : 1.0.0
Date de création : 2026-04-02
Date de modification : 2026-04-02
Objectif : Tests unitaires pour le processeur de conduites.
Vérifie le traitement des canalisations et la création
des objets conduite.
"""

import unittest
import logging

from src.domain.processeur_conduites import ProcesseurConduites

logging.getLogger('src.domain.processeur_conduites').setLevel(
    logging.CRITICAL
)


class TestProcesseurConduites(unittest.TestCase):
    """Tests pour la classe ProcesseurConduites."""

    def setUp(self):
        """Initialise les fixtures."""
        self.processeur = ProcesseurConduites()

    def test_traiter_vide(self):
        """Teste le traitement sans données."""
        import geopandas as gpd
        noeuds_gdf = gpd.GeoDataFrame()
        conduites = self.processeur.traiter(None, noeuds_gdf)
        self.assertEqual(len(conduites), 0)


if __name__ == '__main__':
    unittest.main()
