#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : Pilotage Réseau d'Assainissement
Numéro version : 1.0.0
Date de création : 2026-04-02
Date de modification : 2026-04-02
Objectif : Tests unitaires pour le générateur SWMM.
Vérifie la création du fichier .inp et la structure
des sections générées.
"""

import unittest
import tempfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point

from src.controllers.generateur_swmm import GenerateurSWMM
from src.infrastructure.config import TARGET_CRS


class TestGenerateurSWMM(unittest.TestCase):
    """Tests pour la classe GenerateurSWMM."""

    def setUp(self):
        """Initialise les fixtures."""
        self.generateur = GenerateurSWMM()
        self.temp_dir = tempfile.mkdtemp()

        points = [
            Point(345000 + i * 100, 4000000 + i * 100)
            for i in range(3)
        ]

        self.sample_noeuds = gpd.GeoDataFrame({
            'swmm_id': ['R_0', 'R_1', 'OUT_0'],
            'x': [345000, 345100, 345200],
            'y': [4000000, 4000100, 4000200],
            'elevation': [10.0, 12.0, 5.0],
            'node_type': ['JUNCTION', 'JUNCTION', 'OUTFALL'],
            'original_gdf': ['regards', 'regards', 'rejets'],
            'geometry': points
        }, crs=TARGET_CRS)

        self.sample_conduites = [{
            'conduit_id': 'C_0',
            'from_node': 'R_0',
            'to_node': 'R_1',
            'length': 100.0,
            'roughness': 0.013,
            'in_offset': 0.0,
            'out_offset': 0.0,
            'init_flow': 0.0,
            'max_flow': 0.0,
            'shape': 'CIRCULAR',
            'geom1': 1.0,
            'geom2': 0.0,
            'geom3': 0.0,
            'geom4': 0.0,
            'barrels': 1
        }]

        self.sample_pompes = [{
            'pump_id': 'P_0',
            'from_node': 'R_0',
            'to_node': 'OUT_0',
            'pump_curve': 'GENERIC_PUMP_CURVE'
        }]

    def tearDown(self):
        """Nettoie après les tests."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_genere_fichier(self):
        """Teste que la génération crée un fichier."""
        chemin = Path(self.temp_dir) / 'test.inp'

        resultat = self.generateur.generer(
            noeuds_gdf=self.sample_noeuds,
            conduites=self.sample_conduites,
            pompes=self.sample_pompes,
            fichier_sortie=str(chemin)
        )

        self.assertTrue(Path(resultat).exists())

    def test_structure_fichier(self):
        """Teste la structure du fichier généré."""
        chemin = Path(self.temp_dir) / 'test.inp'

        self.generateur.generer(
            noeuds_gdf=self.sample_noeuds,
            conduites=self.sample_conduites,
            pompes=self.sample_pompes,
            fichier_sortie=str(chemin)
        )

        with open(chemin, 'r', encoding='utf-8') as f:
            contenu = f.read()

        sections_requises = [
            '[TITLE]', '[OPTIONS]', '[JUNCTIONS]',
            '[OUTFALLS]', '[CONDUITS]', '[PUMPS]',
            '[XSECTIONS]', '[COORDINATES]', '[MAP]'
        ]

        for section in sections_requises:
            self.assertIn(
                section, contenu,
                f"Section {section} manquante"
            )


if __name__ == '__main__':
    unittest.main()
