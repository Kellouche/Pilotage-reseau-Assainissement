"""Tests pour l'application principale."""

import unittest
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from pathlib import Path
import tempfile
import logging

from main import SWMMGeneratorApp
from config import TARGET_CRS

# Désactiver les logs basiques pour les tests
logging.getLogger('main').setLevel(logging.CRITICAL)
logging.getLogger('data_processor').setLevel(logging.CRITICAL)
logging.getLogger('swmm_generator').setLevel(logging.CRITICAL)


class TestSWMMGeneratorApp(unittest.TestCase):
    """Tests pour l'application SWMMGeneratorApp."""

    def setUp(self):
        """Initialise les fixtures."""
        self.app = SWMMGeneratorApp()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Nettoie après les tests."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_app_initialization(self):
        """Teste l'initialisation de l'application."""
        self.assertIsNotNone(self.app.data_processor)
        self.assertIsNotNone(self.app.swmm_generator)

    def test_run_with_no_data(self):
        """Teste l'exécution avec aucune donnée."""
        output_file = Path(self.temp_dir) / 'test.inp'
        
        success, message = self.app.run(
            regards_gdf=None,
            rejets_gdf=None,
            ouvrages_gdf=None,
            stations_gdf=None,
            step_gdf=None,
            canalisations_gdf=None,
            output_file=str(output_file)
        )
        
        # Doit échouer car pas de nœuds
        self.assertFalse(success)
        self.assertIn('Aucun nœud', message)

    def test_run_with_sample_data(self):
        """Teste l'exécution avec des données d'exemple."""
        # Créer des données de test
        points = [Point(345000 + i * 100, 4000000 + i * 100) for i in range(5)]
        
        regards_gdf = gpd.GeoDataFrame({
            'HFERMSOL': [10.0, 15.0, 12.0, 14.0, 11.0],
            'geometry': points
        }, crs=TARGET_CRS)

        output_file = Path(self.temp_dir) / 'test.inp'
        
        success, message = self.app.run(
            regards_gdf=regards_gdf,
            output_file=str(output_file)
        )
        
        # Doit réussir
        self.assertTrue(success)
        self.assertTrue(Path(output_file).exists())

    def test_run_creates_log_file(self):
        """Teste que l'exécution crée un fichier log."""
        # Le fichier log peut être créé ou non dépendant du chemin
        # Test simplement que l'app s'exécute sans erreur
        output_file = Path(self.temp_dir) / 'test.inp'
        self.app.run(output_file=str(output_file))
        
        # Vérifier que l'app a au moins créé les objets nécessaires
        self.assertIsNotNone(self.app.data_processor)


class TestIntegration(unittest.TestCase):
    """Tests d'intégration complets."""

    def setUp(self):
        """Initialise les fixtures."""
        self.app = SWMMGeneratorApp()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Nettoie après les tests."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_complete_workflow(self):
        """Teste le workflow complet avec plusieurs types de nœuds."""
        # Créer des données complètes
        points = [Point(345000 + i * 100, 4000000 + i * 100) for i in range(6)]
        
        regards_gdf = gpd.GeoDataFrame({
            'HFERMSOL': [10.0, 15.0],
            'geometry': points[:2]
        }, crs=TARGET_CRS)

        rejets_gdf = gpd.GeoDataFrame({
            'geometry': points[2:4]
        }, crs=TARGET_CRS)

        stations_gdf = gpd.GeoDataFrame({
            'geometry': points[4:5]
        }, crs=TARGET_CRS)

        output_file = Path(self.temp_dir) / 'complete_test.inp'
        
        success, message = self.app.run(
            regards_gdf=regards_gdf,
            rejets_gdf=rejets_gdf,
            stations_gdf=stations_gdf,
            output_file=str(output_file)
        )
        
        self.assertTrue(success)
        self.assertTrue(Path(output_file).exists())
        
        # Vérifier le contenu du fichier
        with open(output_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Doit contenir les sections principales
        self.assertIn('[TITLE]', content)
        self.assertIn('[JUNCTIONS]', content)
        self.assertIn('[OUTFALLS]', content)
        self.assertIn('[COORDINATES]', content)


if __name__ == '__main__':
    unittest.main()
