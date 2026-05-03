#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module d'extraction de courbes de niveau à partir d'un MNT (DEM).

Auteur : Dr Abdelhakim Kellouche
Date : 02-04-2026
Objectif : Extraire des courbes de niveau géoréférencées à partir d'un
fichier DEM TIFF pour les utiliser comme couche dans le projet SWMM.
"""

import logging
import os
from pathlib import Path
from typing import Optional, Union

import numpy as np
import geopandas as gpd
import rasterio
from rasterio.warp import reproject, Resampling
from shapely.geometry import shape, LineString
import pyproj

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def extract_contours_from_dem(
    dem_path: str,
    contour_interval: float = 10.0,
    target_crs: Optional[Union[str, pyproj.CRS]] = None,
    output_path: Optional[str] = None,
    output_format: str = 'shp',
    quality: str = 'medium'
) -> gpd.GeoDataFrame:
    """
    Extrait les courbes de niveau d'un DEM géoréférencé.

    Paramètres
    ----------
    dem_path : str
        Chemin vers le fichier DEM (TIFF géoréférencé).
    contour_interval : float, optionnel
        Intervalle d'extraction des courbes en mètres (par défaut 10.0).
    target_crs : str ou pyproj.CRS, optionnel
        CRS cible pour la reprojection. Si None, conserve le CRS original.
    output_path : str, optionnel
        Chemin de sortie pour les contours. Si None, génère un nom par défaut.
    output_format : str, optionnel
        Format de sortie ('shp' ou 'geojson', par défaut 'shp').
    quality : str, optionnel
        Qualité d'extraction : 'high' (lent, tous les niveaux), 'medium' (défaut), 'fast' (rapide).

    Retourne
    -------
    gpd.GeoDataFrame
        GeoDataFrame contenant les contours avec leurs géométries et
        l'attribut 'level' représentant laltitude.

    Exceptions
    ----------
    FileNotFoundError
        Si le fichier DEM nexiste pas.
    ValueError
        Si le format de sortie nest pas supporté.
    RuntimeError
        Si lextraction des contours échoue.
    """
    logger.info(f"Chargement du DEM depuis : {dem_path}")

    dem_path_obj = Path(dem_path)
    if not dem_path_obj.exists():
        raise FileNotFoundError(f"Le fichier DEM nexiste pas : {dem_path}")

    with rasterio.open(dem_path) as src:
        dem_crs = src.crs
        transform = src.transform
        nodata = src.nodata
        bounds = src.bounds

        logger.info(f"CRS original du DEM : {dem_crs}")
        logger.info(f"Dimensions : {src.width} x {src.height}")
        logger.info(f"Nodata value : {nodata}")
        logger.info(f"Bounds : {bounds}")

        data = src.read(1)

    if nodata is not None:
        data = np.where(data == nodata, np.nan, data)
    else:
        data = np.where(np.isnan(data), np.nan, data)

    valid_data = data[~np.isnan(data)]
    valid_data = valid_data[valid_data > 0]
    if valid_data.size == 0:
        raise ValueError("Aucune donnée valide trouvée dans le DEM")

    min_level = np.nanmin(valid_data)
    max_level = np.nanmax(valid_data)
    logger.info(f"Plage altitudes valides : {min_level:.2f} - {max_level:.2f} m")

    if target_crs is not None:
        if isinstance(target_crs, str):
            target_crs = pyproj.CRS.from_user_input(target_crs)
        else:
            target_crs = pyproj.CRS.from_user_input(target_crs)

        logger.info(f"Reprojection vers le CRS cible : {target_crs}")

        data_proj, transform_proj, current_crs = _reproject_dem(
            data, transform, dem_crs, target_crs
        )
        current_transform = transform_proj
    else:
        current_crs = dem_crs
        current_transform = transform
        data_proj = data

    logger.info(f"Intervalle des contours : {contour_interval} m")

    contours_gdf = _extract_contours_isolines(
        data_proj, current_transform, current_crs, contour_interval, min_level, max_level, quality
    )

    if contours_gdf.empty:
        raise RuntimeError("Aucune courbe de niveau extraite")

    logger.info(f"Nombre de contours extraits : {len(contours_gdf)}")

    if output_path is None:
        output_path = _generate_default_output_path(dem_path_obj, output_format)

    _save_contours(contours_gdf, output_path, output_format)

    return contours_gdf


def _reproject_dem(
    data: np.ndarray,
    transform: rasterio.Affine,
    src_crs: pyproj.CRS,
    dst_crs: pyproj.CRS
) -> tuple:
    """
    Reprojette le DEM vers le CRS cible.

    Paramètres
    ----------
    data : np.ndarray
        Données raster du DEM.
    transform : rasterio.Affine
        Transformation géoréférencement du DEM source.
    src_crs : pyproj.CRS
        CRS source.
    dst_crs : pyproj.CRS
        CRS cible.

    Retourne
    -------
    tuple
        (données reprojetées, nouvelle transformation, nouveau CRS)
    """
    logger.info(f"Reprojection de {src_crs} vers {dst_crs}")

    transformer = pyproj.Transformer.from_crs(src_crs, dst_crs, always_xy=True)

    width = data.shape[1]
    height = data.shape[0]

    left = transform.c
    top = transform.f
    right = transform.c + width * transform.a
    bottom = transform.f + height * transform.e

    xs = np.array([left, right])
    ys = np.array([bottom, top])
    xs_proj, ys_proj = transformer.transform(xs, ys)

    dst_left, dst_right = min(xs_proj), max(xs_proj)
    dst_bottom, dst_top = min(ys_proj), max(ys_proj)

    dst_width = width
    dst_height = height

    dst_transform = rasterio.transform.from_bounds(
        dst_left, dst_bottom, dst_right, dst_top, dst_width, dst_height
    )

    data_proj = np.zeros((dst_height, dst_width), dtype=data.dtype)

    reproject(
        source=data,
        destination=data_proj,
        src_transform=transform,
        dst_transform=dst_transform,
        src_crs=src_crs,
        dst_crs=dst_crs,
        resampling=Resampling.bilinear
    )

    return data_proj, dst_transform, dst_crs


def _extract_contours_isolines(
    data: np.ndarray,
    transform: rasterio.Affine,
    crs: pyproj.CRS,
    contour_interval: float,
    min_level: float,
    max_level: float,
    quality: str = 'medium'
) -> gpd.GeoDataFrame:
    """
    Extrait les courbes de niveau (isolignes) comme des LineStrings.

    Paramètres
    ----------
    data : np.ndarray
        Données raster (déjà reprojetées si nécessaire).
    transform : rasterio.Affine
        Transformation géoréférencement.
    crs : pyproj.CRS
        CRS des géométries extraites.
    contour_interval : float
        Intervalle des contours.
    min_level : float
        Niveau minimum.
    max_level : float
        Niveau maximum.

    Retourne
    -------
    gpd.GeoDataFrame
        GeoDataFrame des courbes de niveau (lignes) avec attribut level.
    """
    logger.info("Génération des courbes de niveau (isolignes)")

    data_clean = np.where(np.isnan(data), np.nan, data)
    data_clean = np.where(data_clean < 0, np.nan, data_clean)

    valid_mask = ~np.isnan(data_clean)
    if not np.any(valid_mask):
        logger.warning("Aucune donnée valide trouvée")
        return gpd.GeoDataFrame(columns=['geometry', 'level'], crs=str(crs))

    valid_min = float(np.nanmin(data_clean))
    valid_max = float(np.nanmax(data_clean))

    logger.info(f"Plage valide : {valid_min:.2f} - {valid_max:.2f} m")

    rows, cols = data_clean.shape
    x_res = transform.a
    y_res = transform.e
    
    x_coords = transform.c + np.arange(cols) * x_res + x_res / 2
    y_coords = transform.f + np.arange(rows) * y_res + y_res / 2

    logger.info("Extraction des isolignes via skimage (marching squares)")

    from skimage import measure
    from scipy import signal

    levels = np.arange(valid_min, valid_max + contour_interval, contour_interval)
    logger.info(f"Niveaux à extraire : {len(levels)}")

    contours = []
    
    smoothing_iterations = 6
    
    def smooth_line(coords: np.ndarray, iterations: int = 6) -> np.ndarray:
        """Applique un lissage de Chaikin pour obtenir des courbes plus lisses."""
        for _ in range(iterations):
            if len(coords) < 4:
                break
            new_coords = []
            for i in range(len(coords) - 1):
                p0 = coords[i]
                p1 = coords[i + 1]
                new_coords.append([
                    0.75 * p0[0] + 0.25 * p1[0],
                    0.75 * p0[1] + 0.25 * p1[1]
                ])
                new_coords.append([
                    0.25 * p0[0] + 0.75 * p1[0],
                    0.25 * p0[1] + 0.75 * p1[1]
                ])
            coords = np.array(new_coords)
        return coords

    for level in levels:
        try:
            contour_points = measure.find_contours(data_clean, level)
            
            for contour in contour_points:
                if len(contour) < 3:
                    continue
                
                raw_coords = np.array([
                    [x_coords[int(p[1])], y_coords[int(p[0])]] 
                    for p in contour 
                    if 0 <= int(p[0]) < rows and 0 <= int(p[1]) < cols
                ])
                
                if len(raw_coords) >= 3:
                    smoothed_coords = smooth_line(raw_coords, smoothing_iterations)
                    
                    line = LineString(smoothed_coords)
                    if line.is_valid and not line.is_empty and line.length > 0:
                        contours.append({'geometry': line, 'level': level})
        except Exception as e:
            logger.debug(f"Erreur au niveau {level}: {e}")
            continue

    logger.info(f"Isolignes extraites : {len(contours)}")

    if not contours:
        logger.warning("Aucune isoligne générée")
        return gpd.GeoDataFrame(columns=['geometry', 'level'], crs=str(crs))

    gdf = gpd.GeoDataFrame(contours, crs=crs)

    if 'geometry' in gdf.columns:
        gdf = gdf[gdf.geometry.type.isin(['LineString', 'MultiLineString'])]
        gdf = gdf[gdf.geometry.is_valid]
        gdf = gdf[~gdf.geometry.is_empty]

    logger.info(f"Isolignes générées : {len(gdf)}")

    return gdf

    if not contours:
        logger.warning("Aucune isoligne générée")
        return gpd.GeoDataFrame(columns=['geometry', 'level'], crs=str(crs))

    gdf = gpd.GeoDataFrame(contours, crs=crs)

    if 'geometry' in gdf.columns:
        gdf = gdf[gdf.geometry.type.isin(['LineString', 'MultiLineString'])]
        gdf = gdf[gdf.geometry.is_valid]
        gdf = gdf[~gdf.geometry.is_empty]

    logger.info(f"Isolignes générées : {len(gdf)}")

    return gdf


def _generate_default_output_path(dem_path: Path, output_format: str) -> str:
    """
    Génère un chemin de sortie par défaut.

    Paramètres
    ----------
    dem_path : Path
        Chemin du fichier DEM.
    output_format : str
        Format de sortie.

    Retourne
    -------
    str
        Chemin de sortie généré.
    """
    extensions = {'shp': '.shp', 'geojson': '.geojson'}
    ext = extensions.get(output_format.lower(), '.shp')

    output_path = dem_path.with_name(dem_path.stem + '_contours' + ext)
    logger.info(f"Chemin de sortie par défaut : {output_path}")

    return str(output_path)


def _save_contours(gdf: gpd.GeoDataFrame, output_path: str, output_format: str) -> None:
    """
    Sauvegarde les contours dans un fichier.

    Paramètres
    ----------
    gdf : gpd.GeoDataFrame
        GeoDataFrame des contours.
    output_path : str
        Chemin de sortie.
    output_format : str
        Format de sortie (shp ou geojson).
    """
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)

    if output_format.lower() == 'geojson':
        gdf.to_file(output_path_obj, driver='GeoJSON')
    else:
        gdf.to_file(output_path_obj)

    logger.info(f"Contours sauvegardés : {output_path}")


def test_contours_crs_match(
    dem_path: str,
    target_crs: Optional[str] = None,
    contour_interval: float = 10.0,
    output_path: Optional[str] = None,
    quality: str = 'medium'
) -> gpd.GeoDataFrame:
    """
    Teste et valide l'extraction des contours.

    Paramètres
    ----------
    dem_path : str
        Chemin vers le fichier DEM.
    target_crs : str, optionnel
        CRS cible attendu. Si None, utilise le CRS du DEM.
    contour_interval : float, optionnel
        Intervalle des contours (par défaut 10.0).
    output_path : str, optionnel
        Chemin de sortie pour les contours.
    quality : str, optionnel
        Qualité : 'high', 'medium' (défaut), 'fast'.

    Retourne
    -------
    gpd.GeoDataFrame
        GeoDataFrame des contours extraits.

    Exceptions
    ----------
    AssertionError
        Si le CRS ne correspond pas ou si lextraction échoue.
    """
    logger.info("=" * 50)
    logger.info("DÉBUT DU TEST DE VALIDATION")
    logger.info("=" * 50)

    try:
        contours_gdf = extract_contours_from_dem(
            dem_path=dem_path,
            contour_interval=contour_interval,
            target_crs=target_crs,
            output_path=output_path,
            quality=quality
        )

        expected_crs = pyproj.CRS.from_user_input(target_crs) if target_crs else None
        if expected_crs is None:
            with rasterio.open(dem_path) as src:
                expected_crs = src.crs

        actual_crs = contours_gdf.crs
        logger.info(f"CRS attendu : {expected_crs}")
        logger.info(f"CRS obtenu : {actual_crs}")

        if expected_crs != actual_crs:
            raise AssertionError(
                f"Le CRS ne correspond pas ! Attendu: {expected_crs}, Obtenu: {actual_crs}"
            )

        logger.info("✓ Validation CRS : OK")

        num_contours = len(contours_gdf)
        if num_contours == 0:
            raise RuntimeError("Aucun contour extrait")

        logger.info(f"Nombre de courbes : {num_contours}")

        min_level = contours_gdf['level'].min()
        max_level = contours_gdf['level'].max()
        logger.info(f"Niveau min : {min_level:.2f} m")
        logger.info(f"Niveau max : {max_level:.2f} m")

        bounds = contours_gdf.total_bounds
        logger.info(f"Étendue : X=[{bounds[0]:.2f}, {bounds[2]:.2f}], Y=[{bounds[1]:.2f}, {bounds[3]:.2f}]")

        logger.info("=" * 50)
        logger.info("VALIDATION TERMINÉE AVEC SUCCÈS")
        logger.info("=" * 50)

        return contours_gdf

    except Exception as e:
        logger.error(f"Échec de la validation : {str(e)}")
        raise


if __name__ == '__main__':
    DEM_PATH = r"D:\IA Water Data Analysis\Assainissement\Générateur de fichier inp pour swmm 5.2\AST14DEM_00407152025093958_20251010054647.tif"

    TARGET_CRS = "EPSG:32631"

    RESULT = test_contours_crs_match(
        dem_path=DEM_PATH,
        target_crs=TARGET_CRS,
        contour_interval=10.0,
        output_path=None
    )
    print(f"\nRésultat: {len(RESULT)} contours extraits")