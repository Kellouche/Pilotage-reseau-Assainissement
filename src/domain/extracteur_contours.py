"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Algorithmes de vectorisation géométrique et enveloppes concaves
================================================================================
"""

from typing import List, Tuple, Optional
import networkx as nx
from shapely.geometry import Point, LineString, Polygon, MultiPolygon, box
from shapely.ops import unary_union
import shapely
import geopandas as gpd
import rasterio
from rasterio.enums import Resampling
import numpy as np
from skimage import measure


class ExtracteurContoursBassin:
    """
    Remplace l'ancien générateur d'enveloppes convexes par une union de corridors
    de drainage et concave hull sans chevauchement.
    """

    def __init__(self, largeur_bande_m: float = 20.0):
        self.largeur_bande_m = largeur_bande_m

    def extraire_contour_bassin(
        self,
        G: nx.DiGraph,
        edges_cluster: List[Tuple],
        noeuds_cluster: List[str]
    ) -> Optional[Polygon]:
        """
        Remplace l'ancienne méthode 'calculer_bassin_polygon' ou 'extraire_contour'.
        """
        tampons = []

        # 1. Tampon sur les canalisations réelles
        for edge in edges_cluster:
            if isinstance(edge[-1], dict):
                data = edge[-1]
            elif G.is_multigraph():
                data = G.edges[edge[0], edge[1], edge[2]]
            else:
                data = G.edges[edge[0], edge[1]]
            geom = data.get('geometry')
            if geom and isinstance(geom, LineString) and not geom.is_empty:
                tampons.append(geom.buffer(self.largeur_bande_m, cap_style=1, join_style=1))

        # 2. Tampon sur les regards / nœuds
        points = []
        for n in noeuds_cluster:
            nd = G.nodes[n]
            geom = nd.get('geometry')
            x = nd.get('x', nd.get('coord_x'))
            y = nd.get('y', nd.get('coord_y'))

            if isinstance(geom, Point):
                points.append((geom.x, geom.y))
                tampons.append(geom.buffer(self.largeur_bande_m * 0.8))
            elif x is not None and y is not None:
                points.append((float(x), float(y)))
                tampons.append(Point(float(x), float(y)).buffer(self.largeur_bande_m * 0.8))

        if not tampons and not points:
            return None

        # Fusion des corridors (sans chevauchement)
        if tampons:
            union_poly = unary_union(tampons)
            lisse = union_poly.buffer(3.0).buffer(-3.0)
            if isinstance(lisse, MultiPolygon):
                lisse = max(lisse.geoms, key=lambda p: p.area)
            return lisse

        # Repli si aucun tronçon géométrique : Concave Hull au lieu de Convex Hull
        if len(points) >= 3 and hasattr(shapely, 'concave_hull'):
            return shapely.concave_hull(shapely.MultiPoint(points), ratio=0.25).buffer(self.largeur_bande_m)

        return None


def extract_contours_from_dem(
    dem_path: str,
    contour_interval: float = 10.0,
    output_format: str = 'geojson'
) -> gpd.GeoDataFrame:
    """
    Extrait les courbes de niveau depuis un fichier DEM (MNT).
    
    Args:
        dem_path: Chemin vers le fichier DEM TIFF
        contour_interval: Intervalle des courbes de niveau en mètres
        output_format: Format de sortie ('geojson' ou 'gdf')
    
    Returns:
        GeoDataFrame avec les courbes de niveau
    """
    with rasterio.open(dem_path) as src:
        dem_data = src.read(
            1,
            out_shape=(src.height, src.width),
            resampling=Resampling.bilinear
        )
        transform = src.transform
        crs = src.crs
    
    # Calculer les niveaux de contour
    min_elev = np.nanmin(dem_data)
    max_elev = np.nanmax(dem_data)
    levels = np.arange(
        np.floor(min_elev / contour_interval) * contour_interval,
        np.ceil(max_elev / contour_interval) * contour_interval + contour_interval,
        contour_interval
    )
    
    # Extraire les contours avec skimage
    contours_list = []
    for level in levels:
        contours = measure.find_contours(dem_data, level)
        for contour in contours:
            # Convertir les coordonnées pixel en coordonnées géographiques
            coords = []
            for point in contour:
                row, col = point
                x, y = transform * (col, row)
                coords.append((x, y))
            
            if len(coords) >= 3:
                line = LineString(coords)
                if line.length > 0:
                    contours_list.append({
                        'geometry': line,
                        'level': float(level)
                    })
    
    if not contours_list:
        return gpd.GeoDataFrame(columns=['level', 'geometry'], crs=crs)
    
    gdf = gpd.GeoDataFrame(contours_list, crs=crs)
    
    if output_format == 'geojson':
        return gdf.__geo_interface__
    
    return gdf


def clipper_contours(
    contours_gdf: gpd.GeoDataFrame,
    aire_etude: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """
    Coupe les courbes de niveau à l'intérieur de l'aire d'étude.
    
    Args:
        contours_gdf: GeoDataFrame des courbes de niveau
        aire_etude: GeoDataFrame de l'aire d'étude (polygone)
    
    Returns:
        GeoDataFrame des courbes de niveau clippées
    """
    if contours_gdf.empty or aire_etude.empty:
        return gpd.GeoDataFrame(columns=contours_gdf.columns, crs=contours_gdf.crs)
    
    # S'assurer que les CRS sont identiques
    if contours_gdf.crs != aire_etude.crs:
        aire_etude = aire_etude.to_crs(contours_gdf.crs)
    
    # Union de l'aire d'étude
    mask = unary_union(aire_etude.geometry)
    
    # Clipper les contours
    clipped = contours_gdf.clip(mask)
    
    return clipped
