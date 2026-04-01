"""Tests pour le module swmm_generator."""

import unittest
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from pathlib import Path
import tempfile
import logging

from swmm_generator import SWMMGenerator
from config import TARGET_CRS

# Désactiver les logs basiques pour les tests
logging.getLogger('swmm_generator').setLevel(logging.CRITICAL)


class TestSWMMGenerator(unittest.TestCase):
    """Tests pour la classe SWMMGenerator."""

    def setUp(self):
        """Initialise les fixtures."""
        self.generator = SWMMGenerator()
        self.temp_dir = tempfile.mkdtemp()

        # Créer un GeoDataFrame de nœuds de test
        points = [Point(345000 + i * 100, 4000000 + i * 100) for i in range(3)]
        
        self.sample_nodes_gdf = gpd.GeoDataFrame({
            'swmm_id': ['R_0', 'R_1', 'OUT_0'],
            'x': [345000, 345100, 345200],
            'y': [4000000, 4000100, 4000200],
            'elevation': [10.0, 12.0, 5.0],
            'node_type': ['JUNCTION', 'JUNCTION', 'OUTFALL'],
            'original_gdf': ['regards', 'regards', 'rejets'],
            'geometry': points
        }, crs=TARGET_CRS)

        # Données de test pour les conduites
        self.sample_conduits = [
            {
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
            }
        ]

        # Données de test pour les pompes
        self.sample_pumps = [
            {
                'pump_id': 'P_0',
                'from_node': 'R_0',
                'to_node': 'OUT_0',
                'pump_curve': 'GENERIC_PUMP_CURVE'
            }
        ]

    def tearDown(self):
        """Nettoie après les tests."""
        # Supprimer les fichiers temporaires
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_generate_creates_file(self):
        """Teste que la génération crée un fichier."""
        output_path = Path(self.temp_dir) / 'test.inp'
        
        result = self.generator.generate(
            nodes_gdf=self.sample_nodes_gdf,
            conduits=self.sample_conduits,
            pumps=self.sample_pumps,
            output_file=str(output_path)
        )
        
        # Vérifier que le fichier existe
        self.assertTrue(Path(result).exists())

    def test_generate_file_content_structure(self):
        """Teste la structure du fichier généré."""
        output_path = Path(self.temp_dir) / 'test.inp'
        
        self.generator.generate(
            nodes_gdf=self.sample_nodes_gdf,
            conduits=self.sample_conduits,
            pumps=self.sample_pumps,
            output_file=str(output_path)
        )
        
        # Lire le fichier
        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Vérifier les sections requises
        required_sections = [
            '[TITLE]',
            '[OPTIONS]',
            '[JUNCTIONS]',
            '[OUTFALLS]',
            '[CONDUITS]',
            '[PUMPS]',
            '[XSECTIONS]',
            '[COORDINATES]',
            '[MAP]'
        ]

        for section in required_sections:
            self.assertIn(section, content, f"Section {section} manquante")

    def test_generate_junctions_section(self):
        """Teste la section JUNCTIONS."""
        output_path = Path(self.temp_dir) / 'test.inp'
        
        self.generator.generate(
            nodes_gdf=self.sample_nodes_gdf,
            conduits=self.sample_conduits,
            pumps=self.sample_pumps,
            output_file=str(output_path)
        )
        
        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Vérifier que les jonctions sont présentes
        self.assertIn('R_0', content)
        self.assertIn('R_1', content)
        self.assertIn('10.00', content)  # Élévation

    def test_generate_outfalls_section(self):
        """Teste la section OUTFALLS."""
        output_path = Path(self.temp_dir) / 'test.inp'
        
        self.generator.generate(
            nodes_gdf=self.sample_nodes_gdf,
            conduits=self.sample_conduits,
            pumps=self.sample_pumps,
            output_file=str(output_path)
        )
        
        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Vérifier les exutoires
        self.assertIn('OUT_0', content)
        self.assertIn('FREE', content)

    def test_generate_conduits_section(self):
        """Teste la section CONDUITS."""
        output_path = Path(self.temp_dir) / 'test.inp'
        
        self.generator.generate(
            nodes_gdf=self.sample_nodes_gdf,
            conduits=self.sample_conduits,
            pumps=self.sample_pumps,
            output_file=str(output_path)
        )
        
        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Vérifier les conduites
        self.assertIn('C_0', content)
        self.assertIn('R_0', content)
        self.assertIn('R_1', content)

    def test_generate_pumps_section(self):
        """Teste la section PUMPS."""
        output_path = Path(self.temp_dir) / 'test.inp'
        
        self.generator.generate(
            nodes_gdf=self.sample_nodes_gdf,
            conduits=self.sample_conduits,
            pumps=self.sample_pumps,
            output_file=str(output_path)
        )
        
        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Vérifier les pompes
        self.assertIn('P_0', content)
        self.assertIn('GENERIC_PUMP_CURVE', content)

    def test_generate_no_pumps(self):
        """Teste la génération sans pompes."""
        output_path = Path(self.temp_dir) / 'test.inp'
        
        self.generator.generate(
            nodes_gdf=self.sample_nodes_gdf,
            conduits=self.sample_conduits,
            pumps=[],
            output_file=str(output_path)
        )
        
        self.assertTrue(Path(output_path).exists())


if __name__ == '__main__':
    unittest.main()
