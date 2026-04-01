"""
Programme principal pour générer des fichiers SWMM .inp.

Architecture modulaire avec :
- data_processor : Traitement des données géospatiales
- swmm_generator : Génération des fichiers SWMM
- config : Configuration centralisée
"""

import sys
import logging
import geopandas as gpd
from pathlib import Path
from typing import Optional, Tuple

from data_processor import DataProcessor
from swmm_generator import SWMMGenerator

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('swmm_generator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class SWMMGeneratorApp:
    """Application principale pour générer les fichiers SWMM."""

    def __init__(self):
        """Initialise l'application."""
        self.data_processor = DataProcessor()
        self.swmm_generator = SWMMGenerator()
        self.nodes_gdf = None
        self.conduits = []
        self.pumps = []

    def run(
        self,
        regards_gdf: Optional[gpd.GeoDataFrame] = None,
        rejets_gdf: Optional[gpd.GeoDataFrame] = None,
        ouvrages_gdf: Optional[gpd.GeoDataFrame] = None,
        stations_gdf: Optional[gpd.GeoDataFrame] = None,
        step_gdf: Optional[gpd.GeoDataFrame] = None,
        canalisations_gdf: Optional[gpd.GeoDataFrame] = None,
        output_file: str = 'model.inp'
    ) -> Tuple[bool, str]:
        """
        Exécute le pipeline de génération.

        Args:
            regards_gdf: GeoDataFrame des regards
            rejets_gdf: GeoDataFrame des rejets
            ouvrages_gdf: GeoDataFrame des ouvrages spéciaux
            stations_gdf: GeoDataFrame des stations de relevage
            step_gdf: GeoDataFrame des STEP
            canalisations_gdf: GeoDataFrame des canalisations
            output_file: Nom du fichier de sortie

        Returns:
            Tuple(succès, message)
        """
        try:
            logger.info("Démarrage du pipeline de génération SWMM")

            # 1. Traiter les nœuds
            logger.info("Traitement des nœuds...")
            self.nodes_gdf, node_count = self.data_processor.process_nodes(
                regards_gdf=regards_gdf,
                rejets_gdf=rejets_gdf,
                ouvrages_gdf=ouvrages_gdf,
                stations_gdf=stations_gdf,
                step_gdf=step_gdf
            )

            if node_count == 0:
                msg = "Aucun nœud trouvé. Vérifiez les GeoDataFrames d'entrée."
                logger.error(msg)
                return False, msg

            logger.info(f"✓ {node_count} nœuds créés")

            # 2. Traiter les pompes
            logger.info("Traitement des pompes...")
            self.pumps = self.data_processor.process_pumps(stations_gdf, self.nodes_gdf)
            logger.info(f"✓ {len(self.pumps)} pompes créées")

            # 3. Traiter les conduites
            logger.info("Traitement des conduites...")
            self.conduits = self.data_processor.process_conduits(canalisations_gdf, self.nodes_gdf)
            
            if len(self.conduits) == 0:
                logger.warning("⚠ Aucune conduite créée. Le réseau peut être vide.")
            else:
                logger.info(f"✓ {len(self.conduits)} conduites créées")

            # 4. Générer le fichier SWMM
            logger.info("Génération du fichier SWMM...")
            output_path = self.swmm_generator.generate(
                nodes_gdf=self.nodes_gdf,
                conduits=self.conduits,
                pumps=self.pumps,
                output_file=output_file
            )

            logger.info(f"✓ Fichier généré: {output_path}")
            self._print_summary(output_path)

            return True, f"Succès: {output_path}"

        except Exception as e:
            msg = f"Erreur critique: {e}"
            logger.exception(msg)
            return False, msg

    def _print_summary(self, output_path: str) -> None:
        """Affiche un résumé de la génération."""
        print("\n" + "="*60)
        print("RÉSUMÉ DE GÉNÉRATION")
        print("="*60)
        print(f"Fichier généré: {output_path}")
        print(f"Nœuds: {len(self.nodes_gdf)}")
        print(f"  - Jonctions: {len(self.nodes_gdf[self.nodes_gdf['node_type'] == 'JUNCTION'])}")
        print(f"  - Exutoires: {len(self.nodes_gdf[self.nodes_gdf['node_type'] == 'OUTFALL'])}")
        print(f"Conduites: {len(self.conduits)}")
        print(f"Pompes: {len(self.pumps)}")
        print("="*60 + "\n")


def main():
    """Point d'entrée du programme."""
    logger.info("Application SWMM Generator démarrée")
    
    app = SWMMGeneratorApp()
    
    # Chercher le GeoPackage
    gpkg_path = Path(r'c:\Users\Hakim\Downloads\Assainissement_Ville.gpkg')
    
    if gpkg_path.exists():
        logger.info(f"GeoPackage trouvé: {gpkg_path}")
        
        try:
            # Charger les couches du GeoPackage
            regards_gdf = gpd.read_file(
                str(gpkg_path),
                layer='Regards_e3c22000_8bba_45a0_a575_d60bbd4b99d3'
            )
            rejets_gdf = gpd.read_file(
                str(gpkg_path),
                layer='Rejets_3cc8eef2_2241_47a0_ad80_fd59749ab068'
            )
            canalisations_gdf = gpd.read_file(
                str(gpkg_path),
                layer='Canalisations_860f298d_9fd9_40a5_bfa4_f913acc71f2e'
            )
            ouvrages_gdf = gpd.read_file(
                str(gpkg_path),
                layer='Ouvrages_Speciaux_4162132f_cd17_43bc_835d_2f7b46f2419f'
            )
            stations_gdf = gpd.read_file(
                str(gpkg_path),
                layer='Station_de_relevage_5c8a759c_c2c5_46cb_a2be_8993c368e0c2'
            )
            step_gdf = gpd.read_file(
                str(gpkg_path),
                layer='STEP_d9ded7b2_1693_4298_baf4_6691f781d403'
            )
            
            logger.info(f"GeoPackage chargé: {len(regards_gdf)} regards, {len(canalisations_gdf)} canalisations")
            
            success, message = app.run(
                regards_gdf=regards_gdf,
                rejets_gdf=rejets_gdf,
                ouvrages_gdf=ouvrages_gdf,
                stations_gdf=stations_gdf,
                step_gdf=step_gdf,
                canalisations_gdf=canalisations_gdf,
                output_file='Assainissement_Ville.inp'
            )
        except Exception as e:
            logger.error(f"Erreur lors du chargement du GeoPackage: {e}")
            success, message = False, f"Erreur: {e}"
    
    else:
        logger.info("GeoPackage non trouvé. Mode démonstration.")
        logger.info(f"Recherché: {gpkg_path}")
        
        success, message = app.run(
            regards_gdf=None,
            rejets_gdf=None,
            ouvrages_gdf=None,
            stations_gdf=None,
            step_gdf=None,
            canalisations_gdf=None,
            output_file='model.inp'
        )
    
    if success:
        logger.info(message)
        return 0
    else:
        return 1


if __name__ == '__main__':
    sys.exit(main())
