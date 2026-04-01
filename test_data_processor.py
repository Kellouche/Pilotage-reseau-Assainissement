"""Tests pour le module data_processor."""

import unittest
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
import logging

from data_processor import DataProcessor
from config import TARGET_CRS

# Désactiver les logs basiques pour les tests
logging.getLogger('data_processor').setLevel(logging.CRITICAL)


class TestDataProcessor(unittest.TestCase):
    """Tests pour la classe DataProcessor."""

    def setUp(self):
        """Initialise les fixtures de test."""
        self.processor = DataProcessor()

        # Créer des GeoDataFrames fictifs
        points = [Point(345000 + i * 100, 4000000 + i * 100) for i in range(5)]
        
        self.sample_regards_gdf = gpd.GeoDataFrame({
            'HFERMSOL': [10.0, 15.0, 12.0, 14.0, 11.0],
            'geometry': points
        }, crs=TARGET_CRS)

        self.sample_rejets_gdf = gpd.GeoDataFrame({
            'geometry': points[:3]
        }, crs=TARGET_CRS)

    def test_process_nodes_empty(self):
        """Teste le traitement avec des données vides."""
        gdf, count = self.processor.process_nodes()
        self.assertEqual(count, 0)
        self.assertTrue(gdf.empty)

    def test_process_nodes_avec_regards(self):
        """Teste le traitement des regards."""
        gdf, count = self.processor.process_nodes(regards_gdf=self.sample_regards_gdf)
        
        self.assertEqual(count, 5)
        self.assertEqual(len(gdf), 5)
        
        # Vérifier les types de nœuds
        self.assertTrue(all(gdf['node_type'] == 'JUNCTION'))
        
        # Vérifier l'élévation
        self.assertEqual(gdf.iloc[0]['elevation'], 10.0)

    def test_process_nodes_mixture(self):
        """Teste le traitement avec plusieurs types de nœuds."""
        gdf, count = self.processor.process_nodes(
            regards_gdf=self.sample_regards_gdf,
            rejets_gdf=self.sample_rejets_gdf
        )
        
        self.assertEqual(count, 8)  # 5 regards + 3 rejets
        
        # Vérifier les types
        junctions = gdf[gdf['node_type'] == 'JUNCTION']
        outfalls = gdf[gdf['node_type'] == 'OUTFALL']
        
        self.assertEqual(len(junctions), 5)
        self.assertEqual(len(outfalls), 3)

    def test_process_pumps_empty(self):
        """Teste le traitement des pompes sans données."""
        nodes_gdf = gpd.GeoDataFrame()
        pumps = self.processor.process_pumps(None, nodes_gdf)
        self.assertEqual(len(pumps), 0)

    def test_process_conduits_empty(self):
        """Teste le traitement des conduites sans données."""
        nodes_gdf = gpd.GeoDataFrame()
        conduits = self.processor.process_conduits(None, nodes_gdf)
        self.assertEqual(len(conduits), 0)

    def test_find_closest_node(self):
        """Teste la recherche du nœud le plus proche."""
        gdf, _ = self.processor.process_nodes(regards_gdf=self.sample_regards_gdf)
        
        # Chercher le nœud le plus proche d'un point (très proche du premier nœud)
        test_point = Point(345000.1, 4000000.1)  # Très proche de R_0
        closest_id = DataProcessor._find_closest_node(test_point, gdf)
        
        # Doit être R_0 (le premier regard)
        self.assertIsNotNone(closest_id)
        self.assertTrue(closest_id.startswith('R_'))


class TestDataProcessorIntegration(unittest.TestCase):
    """Tests d'intégration pour DataProcessor."""

    def setUp(self):
        """Initialise les fixtures."""
        self.processor = DataProcessor()

    def test_full_pipeline_no_data(self):
        """Teste le pipeline complet sans données."""
        nodes_gdf, _ = self.processor.process_nodes()
        pumps = self.processor.process_pumps(None, nodes_gdf)
        conduits = self.processor.process_conduits(None, nodes_gdf)
        
        self.assertEqual(len(nodes_gdf), 0)
        self.assertEqual(len(pumps), 0)
        self.assertEqual(len(conduits), 0)


if __name__ == '__main__':
    unittest.main()
