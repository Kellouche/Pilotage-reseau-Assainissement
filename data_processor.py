"""Processeur de données géospatiales pour SWMM."""

import logging
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from typing import List, Dict, Tuple, Optional
from config import TARGET_CRS, BUFFER_DISTANCE, SHAPE_MAP

logger = logging.getLogger(__name__)


class DataProcessor:
    """Traite les données géospatiales pour SWMM."""

    def __init__(self):
        """Initialise le processeur."""
        self.all_nodes = []
        self.all_pumps = []
        self.all_conduits = []

    def process_nodes(
        self,
        regards_gdf: Optional[gpd.GeoDataFrame] = None,
        rejets_gdf: Optional[gpd.GeoDataFrame] = None,
        ouvrages_gdf: Optional[gpd.GeoDataFrame] = None,
        stations_gdf: Optional[gpd.GeoDataFrame] = None,
        step_gdf: Optional[gpd.GeoDataFrame] = None,
    ) -> Tuple[gpd.GeoDataFrame, int]:
        """
        Traite tous les types de nœuds.

        Args:
            regards_gdf: GeoDataFrame des regards
            rejets_gdf: GeoDataFrame des rejets
            ouvrages_gdf: GeoDataFrame des ouvrages spéciaux
            stations_gdf: GeoDataFrame des stations de relevage
            step_gdf: GeoDataFrame des STEP

        Returns:
            Tuple(GeoDataFrame avec tous les nœuds, nombre de nœuds)
        """
        self.all_nodes = []

        # Traiter regards
        self._process_layer(regards_gdf, 'R', 'JUNCTION', 'HFERMSOL')
        logger.info(f"Regards traités: {len([n for n in self.all_nodes if n['original_gdf'] == 'regards'])}")

        # Traiter rejets
        self._process_layer(rejets_gdf, 'OUT', 'OUTFALL')
        logger.info(f"Rejets traités: {len([n for n in self.all_nodes if n['original_gdf'] == 'rejets'])}")

        # Traiter ouvrages spéciaux
        self._process_layer(ouvrages_gdf, 'OS', 'JUNCTION')
        logger.info(f"Ouvrages traités: {len([n for n in self.all_nodes if n['original_gdf'] == 'ouvrages_speciaux'])}")

        # Traiter stations de relevage
        self._process_layer(stations_gdf, 'SR', 'JUNCTION')
        logger.info(f"Stations traités: {len([n for n in self.all_nodes if n['original_gdf'] == 'station_relevage'])}")

        # Traiter STEP
        self._process_layer(step_gdf, 'STEP', 'OUTFALL')
        logger.info(f"STEP traités: {len([n for n in self.all_nodes if n['original_gdf'] == 'step'])}")

        # Créer GeoDataFrame
        if not self.all_nodes:
            logger.warning("Aucun nœud trouvé!")
            return gpd.GeoDataFrame(), 0

        nodes_gdf = gpd.GeoDataFrame(
            self.all_nodes,
            geometry=gpd.points_from_xy(
                [d['x'] for d in self.all_nodes],
                [d['y'] for d in self.all_nodes]
            ),
            crs=TARGET_CRS
        )

        logger.info(f"Total: {len(nodes_gdf)} nœuds collectés")
        return nodes_gdf, len(nodes_gdf)

    def _process_layer(
        self,
        gdf: Optional[gpd.GeoDataFrame],
        prefix: str,
        node_type: str,
        elevation_field: Optional[str] = None
    ) -> None:
        """Traite un type de couche."""
        if gdf is None or gdf.empty:
            return

        try:
            gdf_proj = gdf.to_crs(TARGET_CRS)
            
            original_type = self._get_original_type(prefix)
            
            for idx, row in gdf_proj.iterrows():
                if row.geometry and row.geometry.geom_type == 'Point':
                    elevation = 0.0
                    if elevation_field and pd.notna(row.get(elevation_field)):
                        elevation = float(row[elevation_field])

                    self.all_nodes.append({
                        'swmm_id': f"{prefix}_{idx}",
                        'x': row.geometry.x,
                        'y': row.geometry.y,
                        'node_type': node_type,
                        'original_gdf': original_type,
                        'elevation': elevation
                    })
        except Exception as e:
            logger.error(f"Erreur lors du traitement de la couche {prefix}: {e}")

    @staticmethod
    def _get_original_type(prefix: str) -> str:
        """Récupère le type original de la source."""
        mapping = {
            'R': 'regards',
            'OUT': 'rejets',
            'OS': 'ouvrages_speciaux',
            'SR': 'station_relevage',
            'STEP': 'step'
        }
        return mapping.get(prefix, 'unknown')

    def process_pumps(
        self,
        stations_gdf: Optional[gpd.GeoDataFrame],
        nodes_gdf: gpd.GeoDataFrame
    ) -> List[Dict]:
        """
        Traite les pompes basées sur les stations de relevage.

        Args:
            stations_gdf: GeoDataFrame des stations
            nodes_gdf: GeoDataFrame avec tous les nœuds

        Returns:
            Liste des données de pompe
        """
        self.all_pumps = []

        if stations_gdf is None or stations_gdf.empty:
            return self.all_pumps

        try:
            gdf_proj = stations_gdf.to_crs(TARGET_CRS)

            for idx, row in gdf_proj.iterrows():
                if row.geometry and row.geometry.geom_type == 'Point':
                    pump_id = f"P_{idx}"
                    from_node_id = f"SR_{idx}"
                    
                    # Chercher le nœud 'from'
                    from_node = nodes_gdf[nodes_gdf['swmm_id'] == from_node_id]
                    
                    if from_node.empty:
                        logger.warning(f"Nœud source {from_node_id} non trouvé pour pompe {pump_id}")
                        continue

                    # Trouver le nœud de destination le plus proche
                    pump_location = Point(row.geometry.x, row.geometry.y)
                    other_nodes = nodes_gdf[nodes_gdf['swmm_id'] != from_node_id]

                    if other_nodes.empty:
                        logger.warning(f"Aucun nœud de destination pour pompe {pump_id}")
                        continue

                    distances = other_nodes.geometry.apply(lambda geom: pump_location.distance(geom))
                    closest_node = other_nodes.loc[distances.idxmin()]
                    to_node_id = closest_node['swmm_id']

                    self.all_pumps.append({
                        'pump_id': pump_id,
                        'from_node': from_node_id,
                        'to_node': to_node_id,
                        'pump_curve': 'GENERIC_PUMP_CURVE'
                    })

            logger.info(f"{len(self.all_pumps)} pompes créées")
        except Exception as e:
            logger.error(f"Erreur lors du traitement des pompes: {e}")

        return self.all_pumps

    def process_conduits(
        self,
        canalisations_gdf: Optional[gpd.GeoDataFrame],
        nodes_gdf: gpd.GeoDataFrame
    ) -> List[Dict]:
        """
        Traite les conduites/canalisations.

        Args:
            canalisations_gdf: GeoDataFrame des canalisations
            nodes_gdf: GeoDataFrame avec tous les nœuds

        Returns:
            Liste des données de conduite
        """
        self.all_conduits = []

        if canalisations_gdf is None or canalisations_gdf.empty:
            return self.all_conduits

        try:
            gdf_proj = canalisations_gdf.to_crs(TARGET_CRS)

            conduit_id_counter = 0
            skipped_count = 0

            for idx, row in gdf_proj.iterrows():
                geoms_to_process = []

                if row.geometry:
                    if row.geometry.geom_type == 'LineString':
                        geoms_to_process = [row.geometry]
                    elif row.geometry.geom_type == 'MultiLineString':
                        geoms_to_process = list(row.geometry.geoms)

                for geom in geoms_to_process:
                    if geom.geom_type != 'LineString':
                        continue

                    # Créer ID conduite
                    conduit_id = f"C_{conduit_id_counter}"
                    conduit_id_counter += 1

                    # Trouver nœud de départ
                    start_point = geom.coords[0]
                    start_node_id = self._find_closest_node(Point(start_point), nodes_gdf)

                    # Trouver nœud d'arrivée
                    end_point = geom.coords[-1]
                    end_node_id = self._find_closest_node(Point(end_point), nodes_gdf)

                    if not start_node_id or not end_node_id:
                        skipped_count += 1
                        continue

                    # Extraire paramètres
                    length = max(
                        float(row.get('LINEAIRE', geom.length)) or geom.length,
                        0.1
                    )
                    
                    shape_type = str(row.get('FORMESECT', 'CIRCULAIRE')).upper()
                    swmm_shape = SHAPE_MAP.get(shape_type, 'CIRCULAR')

                    geom1 = float(row.get('DIAMETRE', 0.5)) or 0.5
                    geom2 = float(row.get('GDEBASE', 0.0)) or 0.0
                    geom3 = float(row.get('HAUTEUR', 0.0)) or 0.0

                    self.all_conduits.append({
                        'conduit_id': conduit_id,
                        'from_node': start_node_id,
                        'to_node': end_node_id,
                        'length': length,
                        'roughness': 0.013,
                        'in_offset': 0.0,
                        'out_offset': 0.0,
                        'init_flow': 0.0,
                        'max_flow': 0.0,
                        'shape': swmm_shape,
                        'geom1': geom1,
                        'geom2': geom2,
                        'geom3': geom3,
                        'geom4': 0.0,
                        'barrels': 1
                    })

            logger.info(f"{len(self.all_conduits)} conduites créées, {skipped_count} ignorées")
        except Exception as e:
            logger.error(f"Erreur lors du traitement des conduites: {e}")

        return self.all_conduits

    @staticmethod
    def _find_closest_node(point: Point, nodes_gdf: gpd.GeoDataFrame) -> Optional[str]:
        """Trouve le nœud le plus proche d'un point."""
        possible_nodes = nodes_gdf.cx[
            point.x - BUFFER_DISTANCE:point.x + BUFFER_DISTANCE,
            point.y - BUFFER_DISTANCE:point.y + BUFFER_DISTANCE
        ]

        if possible_nodes.empty:
            return None

        distances = possible_nodes.geometry.distance(point)
        closest = possible_nodes.loc[distances.idxmin()]
        return closest['swmm_id']
