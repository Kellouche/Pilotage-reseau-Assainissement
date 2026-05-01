#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module de traitement des courbes de niveau pour le projet SWMM.

Auteur : Dr Abdelhakim Kellouche
Date : 05-04-2026
Objectif : Workflow complet pour extraire, clipper et visualiser
les courbes de niveau à partir d'un DEM géoréférencé.

Fonctionnalités :
1. Vérification et harmonisation du CRS
2. Détermination de l'aire d'étude depuis les couches réseau
3. Génération des contours avec intervalle configurable
4. Clipping des contours à l'aire d'étude
5. Export en format vectoriel (Shapefile/GeoJSON)
6. Visualisation cartographique avec étiquettes d'altitude
7. Export PDF/PNG
8. Options d'automatisation PyQGIS et GDAL/OGR
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional, Union

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import reproject, Resampling
from shapely.geometry import box, shape, LineString, MultiLineString
from shapely.ops import unary_union
import pyproj

logger = logging.getLogger(__name__)


def harmoniser_crs(
    dem_path: str,
    couches_reseau: list[str],
    crs_cible: Optional[str] = None
) -> dict[str, Any]:
    """
    Vérifie et harmonise le CRS du DEM et des couches réseau.
    
    Paramètres
    ----------
    dem_path : str
        Chemin vers le fichier DEM (TIFF).
    couches_reseau : list[str]
        Liste des chemins vers les fichiers vectoriels du réseau.
    crs_cible : str, optionnel
        CRS cible (par exemple 'EPSG:32631'). Si non fourni,
        utilise le CRS du DEM.
    
    Retourne
    -------
    dict
        Dictionnaire contenant les informations CRS :
        - dem_crs : CRS du DEM
        - reseau_crs : CRS des couches réseau (après harmonisation)
        - crs_utilise : CRS effectivement utilisé
        - besoins_reprojection : booléen indiquant si reprojection nécessaire
    """
    logger.info("=" * 60)
    logger.info("ÉTAPE 1: VÉRIFICATION ET HARMONISATION CRS")
    logger.info("=" * 60)
    
    resultat = {
        'dem_crs': None,
        'reseau_crs': None,
        'crs_utilise': None,
        'besoins_reprojection': False
    }
    
    with rasterio.open(dem_path) as src:
        dem_crs = src.crs
        resultat['dem_crs'] = str(dem_crs)
        logger.info(f"  CRS du DEM : {dem_crs}")
    
    reseau_crs_set = set()
    for chemin in couches_reseau:
        if os.path.exists(chemin):
            try:
                gdf = gpd.read_file(chemin)
                if gdf.crs:
                    reseau_crs_set.add(str(gdf.crs))
                    logger.info(f"  Couche {Path(chemin).name} : CRS = {gdf.crs}")
            except Exception as e:
                logger.warning(f"  Erreur lecture {chemin}: {e}")
    
    if not reseau_crs_set:
        raise ValueError("Aucune couche réseau avec CRS valide")
    
    reseau_crs = list(reseau_crs_set)[0]
    resultat['reseau_crs'] = reseau_crs
    
    if crs_cible:
        crs_final = crs_cible
    else:
        crs_final = dem_crs
    
    resultat['crs_utilise'] = crs_final
    
    if str(dem_crs) != crs_final or reseau_crs != crs_final:
        resultat['besoins_reprojection'] = True
        logger.info(f"  → Reprojection nécessaire vers : {crs_final}")
    else:
        logger.info(f"  → CRS harmonisés : {crs_final}")
    
    logger.info("  ✓ Vérification CRS terminée")
    return resultat


def determiner_aire_etude(
    couches_reseau: list[str],
    buffer_meters: float = 0.0,
    crs: Optional[str] = None
) -> gpd.GeoDataFrame:
    """
    Détermine l'aire d'étude en fusionnant les enveloppes des couches réseau.
    
    Paramètres
    ----------
    couches_reseau : list[str]
        Liste des chemins vers les fichiers vectoriels du réseau.
    buffer_meters : float, optionnel
        Zone tampon autour de l'enveloppe en mètres (par défaut 0).
    crs : str, optionnel
        CRS pour le calcul du buffer. Si None, utilise le CRS des géométries.
    
    Retourne
    -------
    gpd.GeoDataFrame
        GeoDataFrame avec un seul polygone représentant l'aire d'étude.
    """
    logger.info("=" * 60)
    logger.info("ÉTAPE 2: DÉTERMINATION AIRE D'ÉTUDE")
    logger.info("=" * 60)
    
    geometries = []
    crs_utilise = None
    
    for chemin in couches_reseau:
        if not os.path.exists(chemin):
            logger.warning(f"  Couche non trouvée : {chemin}")
            continue
            
        try:
            gdf = gpd.read_file(chemin)
            if crs_utilise is None and gdf.crs:
                crs_utilise = gdf.crs
            
            if gdf.crs and crs_utilise and gdf.crs != crs_utilise:
                gdf = gdf.to_crs(crs_utilise)
            
            bounds = gdf.total_bounds
            polygone = box(bounds[0], bounds[1], bounds[2], bounds[3])
            geometries.append(polygone)
            
            logger.info(f"  {Path(chemin).name}: bounds = {bounds}")
            
        except Exception as e:
            logger.warning(f"  Erreur traitement {chemin}: {e}")
    
    if not geometries:
        raise ValueError("Aucune géométrie valide trouvée dans les couches réseau")
    
    geometrie_fusionnee = unary_union(geometries)
    
    if buffer_meters > 0 and crs_utilise:
        try:
            projet = pyproj.CRS.from_user_input(crs_utilise)
            if projet.is_geographic:
                transforme = pyproj.Transformer.from_crs(
                    projet, projet.geodetic_crs, always_xy=True
                )
                if isinstance(geometrie_fusionnee, MultiLineString):
                    pass
                else:
                    geometrie_buffer = geometrie_fusionnee.buffer(
                        buffer_meters / 111320
                    )
            else:
                geometrie_buffer = geometrie_fusionnee.buffer(buffer_meters)
            geometrie_fusionnee = geometrie_buffer
            logger.info(f"  Applied buffer: {buffer_meters}m")
        except Exception as e:
            logger.warning(f"  Buffer failed: {e}")
    
    gdf_aire = gpd.GeoDataFrame(
        {'id': [1], 'geometry': [geometrie_fusionnee]},
        crs=crs_utilise
    )
    
    bounds = gdf_aire.total_bounds
    logger.info(f"  Aire d'étude : X=[{bounds[0]:.2f}, {bounds[2]:.2f}], Y=[{bounds[1]:.2f}, {bounds[3]:.2f}]")
    logger.info(f"  Surface : {(bounds[2]-bounds[0]) * (bounds[3]-bounds[1]):.2f} m²")
    logger.info("  ✓ Aire d'étude créée")
    
    return gdf_aire


def generer_contours(
    dem_path: str,
    aire_etude: gpd.GeoDataFrame,
    contour_interval: float = 10.0,
    output_crs: Optional[str] = None,
    quality: str = 'medium'
) -> gpd.GeoDataFrame:
    """
    Génère les courbes de niveau à partir du DEM sur l'aire d'étude.
    
    Paramètres
    ----------
    dem_path : str
        Chemin vers le fichier DEM (TIFF).
    aire_etude : gpd.GeoDataFrame
        Polygone de l'aire d'étude.
    contour_interval : float, optionnel
        Intervalle des contours en mètres (par défaut 10.0).
    output_crs : str, optionnel
        CRS de sortie. Si None, utilise le CRS du DEM.
    quality : str, optionnel
        Qualité : 'high', 'medium' (défaut), 'fast'.
    
    Retourne
    -------
    gpd.GeoDataFrame
        GeoDataFrame des contours avec attribut 'level' (altitude en mètres).
    """
    logger.info("=" * 60)
    logger.info("ÉTAPE 3: GÉNÉRATION DES COURBES DE NIVEAU")
    logger.info("=" * 60)
    
    with rasterio.open(dem_path) as src:
        dem_crs = src.crs
        transform = src.transform
        nodata = src.nodata
        bounds = src.bounds
        
        logger.info(f"  CRS DEM : {dem_crs}")
        logger.info(f"  Dimensions : {src.width} x {src.height}")
        logger.info(f"  Bounds : {bounds}")
        
        data = src.read(1)
    
    if nodata is not None:
        data = np.where(data == nodata, np.nan, data)
    else:
        data = np.where(np.isnan(data), np.nan, data)
    
    valid_data = data[~np.isnan(data)]
    valid_data = valid_data[valid_data > 0]
    
    if valid_data.size == 0:
        raise ValueError("Aucune donnée valide dans le DEM")
    
    min_alt = float(np.nanmin(valid_data))
    max_alt = float(np.nanmax(valid_data))
    logger.info(f"  Plage altitudes : {min_alt:.2f} - {max_alt:.2f} m")
    
    rows, cols = data.shape
    x_res = transform.a
    y_res = transform.e
    
    x_coords = transform.c + np.arange(cols) * x_res + x_res / 2
    y_coords = transform.f + np.arange(rows) * y_res + y_res / 2
    
    logger.info(f"  Intervalle demandé : {contour_interval} m")
    
    from skimage import measure
    
    alt_min = int(min_alt / contour_interval) * contour_interval
    alt_max = int(max_alt / contour_interval) * contour_interval + contour_interval
    niveaux = np.arange(alt_min, alt_max + contour_interval, contour_interval)
    logger.info(f"  Niveaux à extraire : {len(niveaux)}")
    
    contours = []
    smoothing_iters = {'high': 8, 'medium': 6, 'fast': 3}.get(quality, 6)
    
    def smooth_line(coords, iterations=6):
        if len(coords) < 4:
            return coords
        for _ in range(iterations):
            new_coords = []
            for i in range(len(coords) - 1):
                p0, p1 = coords[i], coords[i + 1]
                new_coords.append([0.75*p0[0] + 0.25*p1[0], 0.75*p0[1] + 0.25*p1[1]])
                new_coords.append([0.25*p0[0] + 0.75*p1[0], 0.25*p0[1] + 0.75*p1[1]])
            coords = np.array(new_coords)
        return coords
    
    for niveau in niveaux:
        try:
            contour_points = measure.find_contours(data, niveau)
            
            for contour in contour_points:
                if len(contour) < 3:
                    continue
                
                raw_coords = np.array([
                    [x_coords[int(p[1])], y_coords[int(p[0])]]
                    for p in contour
                    if 0 <= int(p[0]) < rows and 0 <= int(p[1]) < cols
                ])
                
                if len(raw_coords) >= 3:
                    smoothed = smooth_line(raw_coords, smoothing_iters)
                    line = LineString(smoothed)
                    if line.is_valid and not line.is_empty and line.length > 0:
                        contours.append({'geometry': line, 'level': round(niveau, 1)})
        except Exception as e:
            logger.debug(f"  Niveau {niveau}: {e}")
            continue
    
    if not contours:
        raise RuntimeError("Aucune courbe générée")
    
    gdf = gpd.GeoDataFrame(contours, crs=dem_crs)
    gdf = gdf[gdf.geometry.type.isin(['LineString', 'MultiLineString'])]
    gdf = gdf[gdf.geometry.is_valid]
    gdf = gdf[~gdf.geometry.is_empty]
    
    if output_crs and output_crs != str(dem_crs):
        gdf = gdf.to_crs(output_crs)
        logger.info(f"  Reprojection vers : {output_crs}")
    
    logger.info(f"  ✓ {len(gdf)} courbes générées")
    return gdf


def clipper_contours(
    contours: gpd.GeoDataFrame,
    aire_etude: gpd.GeoDataFrame,
    methode: str = 'intersection'
) -> gpd.GeoDataFrame:
    """
    Clippe les contours pour ne garder que ceux داخل l'aire d'étude.
    
    Paramètres
    ----------
    contours : gpd.GeoDataFrame
        GeoDataFrame des contours à clipper.
    aire_etude : gpd.GeoDataFrame
        Polygone de l'aire d'étude.
    methode : str, optionnel
        Méthode de clipping : 'intersection' (défaut), 'within', 'cover'.
    
    Retourne
    -------
    gpd.GeoDataFrame
        GeoDataFrame des contours clipés.
    """
    logger.info("=" * 60)
    logger.info("ÉTAPE 4: CLIPPING DES COURBES")
    logger.info("=" * 60)
    
    logger.info(f"  Méthode : {methode}")
    logger.info(f"  Contours initiaux : {len(contours)}")
    
    if contours.crs != aire_etude.crs:
        aire_etude = aire_etude.to_crs(contours.crs)
    
    polygone_etude = aire_etude.unary_union
    
    contours_clipped = []
    
    for idx, row in contours.iterrows():
        geom = row.geometry
        if methode == 'intersection':
            result = geom.intersection(polygone_etude)
        elif methode == 'within':
            result = geom if polygone_etude.contains(geom) else None
        else:
            result = geom.intersection(polygone_etude)
        
        if result and not result.is_empty:
            if result.geom_type == 'MultiLineString':
                for part in result.geoms:
                    if not part.is_empty:
                        contours_clipped.append({
                            'geometry': part,
                            'level': row.get('level', 0)
                        })
            elif result.geom_type == 'LineString':
                contours_clipped.append({
                    'geometry': result,
                    'level': row.get('level', 0)
                })
    
    gdf_clipped = gpd.GeoDataFrame(contours_clipped, crs=contours.crs)
    
    logger.info(f"  Contours après clipping : {len(gdf_clipped)}")
    logger.info(f"  Taux de rétention : {100*len(gdf_clipped)/len(contours):.1f}%")
    logger.info("  ✓ Clipping terminé")
    
    return gdf_clipped


def exporter_contours(
    contours: gpd.GeoDataFrame,
    output_path: str,
    format_export: str = 'shp'
) -> str:
    """
    Exporte les contours clipés en format vectoriel.
    
    Paramètres
    ----------
    contours : gpd.GeoDataFrame
        Contours à exporter.
    output_path : str
        Chemin de sortie.
    format_export : str, optionnel
        Format : 'shp' (défaut), 'geojson', 'gpkg'.
    
    Retourne
    -------
    str
        Chemin du fichier créé.
    """
    logger.info("=" * 60)
    logger.info("ÉTAPE 5: EXPORT VECTORIEL")
    logger.info("=" * 60)
    
    output_path = str(output_path)
    
    drivers = {
        'shp': 'ESRI Shapefile',
        'geojson': 'GeoJSON',
        'gpkg': 'GPKG'
    }
    
    driver = drivers.get(format_export.lower(), 'ESRI Shapefile')
    
    contours.to_file(output_path, driver=driver)
    
    logger.info(f"  Format : {format_export}")
    logger.info(f"  Fichier : {output_path}")
    logger.info(f"  Entités : {len(contours)}")
    logger.info("  ✓ Export terminé")
    
    return output_path


def visualiser_contours(
    contours: gpd.GeoDataFrame,
    output_html: str = "contours_carte.html",
    ajouter_etiquettes: bool = True,
    intervalle_etiquette: int = 5,
    style_ligne: Optional[dict] = None
) -> str:
    """
    Affiche les contours sur une carte interactive avec étiquettes.
    
    Paramètres
    ----------
    contours : gpd.GeoDataFrame
        Contours à visualiser.
    output_html : str, optionnel
        Chemin du fichier HTML de sortie.
    ajouter_etiquettes : bool, optionnel
        Ajouter les étiquettes d'altitude (défaut True).
    intervalle_etiquette : int, optionnel
        Afficher une étiquette toutes les N courbes (défaut 5).
    style_ligne : dict, optionnel
        Style des lignes (couleur, épaisseur, etc.).
    
    Retourne
    -------
    str
        Chemin du fichier HTML créé.
    """
    logger.info("=" * 60)
    logger.info("ÉTAPE 6: VISUALISATION CARTOGRAPHIQUE")
    logger.info("=" * 60)
    
    try:
        import folium
        from folium.plugins import MousePosition
    except ImportError:
        logger.error("Folium non installé. Installé: pip install folium")
        raise
    
    contours_wgs84 = contours.to_crs("EPSG:4326")
    bounds = contours_wgs84.total_bounds
    
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2
    
    logger.info(f"  Centre carte : [{center_lat:.4f}, {center_lon:.4f}]")
    
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=12,
        tiles='OpenStreetMap'
    )
    
    default_style = {
        'color': '#3388ff',
        'weight': 2,
        'opacity': 0.8
    }
    if style_ligne:
        default_style.update(style_ligne)
    
    niveaux_uniques = sorted(contours_wgs84['level'].unique())
    
    if not ajouter_etiquettes:
        for idx, row in contours_wgs84.iterrows():
            geojson = {
                'type': 'Feature',
                'properties': {'level': row.get('level', 0)},
                'geometry': row.geometry.__geo_interface__
            }
            
            def style_fn(feature):
                level = feature['properties']['level']
                color = _get_couleur_altitude(level, niveaux_uniques)
                return {'color': color, 'weight': 2, 'opacity': 0.8}
            
            folium.GeoJson(
                geojson,
                style_function=style_fn,
                tooltip=f"{int(row.get('level', 0))} m"
            ).add_to(m)
    else:
        n_etiquette = 0
        for idx, row in contours_wgs84.iterrows():
            level = row.get('level', 0)
            
            geojson = {
                'type': 'Feature',
                'properties': {'level': level},
                'geometry': row.geometry.__geo_interface__
            }
            
            color = _get_couleur_altitude(level, niveaux_uniques)
            style_fn = lambda f, c=color: {'color': c, 'weight': 2, 'opacity': 0.8}
            
            folium.GeoJson(
                geojson,
                style_function=style_fn
            ).add_to(m)
            
            n_etiquette += 1
            if n_etiquette % intervalle_etiquette == 0:
                try:
                    if hasattr(row.geometry, 'coords'):
                        coords = list(row.geometry.coords)
                        if len(coords) >= 2:
                            mid_idx = len(coords) // 2
                            mid_lon, mid_lat = coords[mid_idx]
                            
                            folium.Marker(
                                location=[mid_lat, mid_lon],
                                icon=folium.DivIcon(
                                    html=f'<div style="font-size:9pt;color:#000;font-weight:bold;'
                                        f'background:rgba(255,255,255,0.7);padding:1px 3px;'
                                        f'border-radius:2px;">{int(level)} m</div>',
                                    icon_size=(60, 20),
                                    icon_anchor=(30, 10)
                                )
                            ).add_to(m)
                except Exception:
                    pass
    
    MousePosition().add_to(m)
    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    m.save(output_html)
    
    logger.info(f"  Carte HTML : {output_html}")
    logger.info("  ✓ Visualisation terminée")
    
    return output_html


def _get_couleur_altitude(level: float, niveaux: list) -> str:
    """Retourne une couleur basée sur l'altitude."""
    n = len(niveaux)
    if n <= 1:
        return '#3388ff'
    
    idx = 0
    for i, nv in enumerate(niveaux):
        if level >= nv:
            idx = i
    
    hue = 240 - (idx / (n - 1)) * 240 if n > 1 else 240
    return f'hsl({hue}, 70%, 50%)'


def exporter_carte(
    contours: gpd.GeoDataFrame,
    aire_etude: gpd.GeoDataFrame,
    output_path: str,
    titre: str = "Courbes de niveau",
    format_export: str = 'png'
) -> str:
    """
    Exporte une carte statique (PNG/PDF).
    
    Paramètres
    ----------
    contours : gpd.GeoDataFrame
        Contours à afficher.
    aire_etude : gpd.GeoDataFrame
        Aire d'étude (pour le fond).
    output_path : str
        Chemin de sortie.
    titre : str, optionnel
        Titre de la carte.
    format_export : str, optionnel
        Format : 'png' (défaut), 'pdf'.
    
    Retourne
    -------
    str
        Chemin du fichier créé.
    """
    logger.info("=" * 60)
    logger.info("ÉTAPE 7: EXPORT CARTOGRAPHIQUE")
    logger.info("=" * 60)
    
    try:
        import matplotlib.pyplot as plt
        import contextily as ctx
    except ImportError:
        logger.warning("Matplotlib ou contextily non disponibles")
        logger.info("  Installéz: pip install matplotlib contextily")
        
        logger.info("  Création carte simplifiée avec matplotlib...")
    
    fig, ax = plt.subplots(1, 1, figsize=(12, 10))
    
    contours_wgs84 = contours.to_crs("EPSG:4326")
    
    niveaux = sorted(contours_wgs84['level'].unique())
    cmap = plt.cm.terrain
    
    for idx, row in contours_wgs84.iterrows():
        level = row.get('level', 0)
        color = cmap((level - min(niveaux)) / (max(niveaux) - min(niveaux) + 0.001))
        
        if hasattr(row.geometry, 'xy'):
            x, y = row.geometry.xy
            ax.plot(x, y, color=color, linewidth=0.8)
    
    try:
        aire_wgs84 = aire_etude.to_crs("EPSG:4326")
        for geom in aire_wgs84.geometry:
            x, y = geom.exterior.xy
            ax.plot(x, y, 'r--', linewidth=2, label='Aire étude')
    except Exception:
        pass
    
    ax.set_title(f"{titre}\nIntervalle: {contours['level'].diff().median():.0f} m")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    
    fig.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    logger.info(f"  Format : {format_export}")
    logger.info(f"  Fichier : {output_path}")
    logger.info("  ✓ Export cartographique terminé")
    
    return output_path


def documenter_parametres(
    parametres: dict,
    output_path: str = "contours_documentation.md"
) -> str:
    """
    Documente les paramètres utilisés.
    
    Paramètres
    ----------
    parametres : dict
        Dictionnaire des paramètres.
    output_path : str, optionnel
        Chemin du fichier de documentation.
    
    Retourne
    -------
    str
        Chemin du fichier créé.
    """
    logger.info("=" * 60)
    logger.info("RÉCAPITULATIF DES PARAMÈTRES")
    logger.info("=" * 60)
    
    doc = f"""# Documentation de génération des contours

## Paramètres utilisés

- **Intervalle de contour** : {parametres.get('intervalle', 'N/A')} m
- **CRS utilisé** : {parametres.get('crs', 'N/A')}
- **DEM source** : {parametres.get('dem_path', 'N/A')}
- **Couches réseau** : {', '.join(parametres.get('couches_reseau', []))}
- **Méthode de clipping** : {parametres.get('methode_clipping', 'intersection')}
- **Format export** : {parametres.get('format_export', 'shp')}
- **Qualité** : {parametres.get('quality', 'medium')}

## Méthode

1. **Vérification CRS** : Comparaison du CRS du DEM et des couches réseau
2. **Détermination aire** : Fusion des enveloppes des couches réseau
3. **Génération contours** : Extraction des isolignes via scikit-image
4. **Clipping** : Intersection des contours avec le polygone d'étude
5. **Export** : Sauvegarde en format vectoriel

## Fichiers générés

- Contours clipés : `{parametres.get('output_contours', 'contours_clipped.shp')}`
- Carte interactive : `{parametres.get('output_html', 'contours_carte.html')}`
- Export cartographique : `{parametres.get('output_carte', 'contours_carte.png')}`

"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(doc)
    
    logger.info(f"  Documentation : {output_path}")
    
    return output_path


def executer_workflow(
    dem_path: str,
    couches_reseau: list[str],
    output_dir: str = ".",
    contour_interval: float = 10.0,
    crs_cible: Optional[str] = None,
    buffer_meters: float = 0.0,
    quality: str = 'medium',
    format_export: str = 'geojson',
    export_carte: bool = True,
    creer_html: bool = True
) -> dict[str, Any]:
    """
    Exécute le workflow complet de traitement des contours.
    
    Paramètres
    ----------
    dem_path : str
        Chemin vers le fichier DEM (TIFF).
    couches_reseau : list[str]
        Liste des chemins vers les fichiers vectoriels du réseau.
    output_dir : str, optionnel
        Répertoire de sortie (par défaut répertoire courant).
    contour_interval : float, optionnel
        Intervalle des contours en mètres (par défaut 10.0).
    crs_cible : str, optionnel
        CRS cible (par exemple 'EPSG:32631').
    buffer_meters : float, optionnel
        Zone tampon autour de l'aire d'étude en mètres.
    quality : str, optionnel
        Qualité : 'high', 'medium' (défaut), 'fast'.
    format_export : str, optionnel
        Format d'export : 'shp', 'geojson' (défaut), 'gpkg'.
    export_carte : bool, optionnel
        Exporter la carte PNG/PDF (défaut True).
    creer_html : bool, optionnel
        Créer la carte interactive HTML (défaut True).
    
    Retourne
    -------
    dict
        Résultats du workflow avec les chemins des fichiers créés.
    """
    logger.info("\n" + "=" * 60)
    logger.info("DÉMARRAGE WORKFLOW GÉNÉRATION CONTOURS")
    logger.info("=" * 60)
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    resultats = {
        'parametres': {
            'intervalle': contour_interval,
            'crs': crs_cible,
            'dem_path': dem_path,
            'couches_reseau': [str(p) for p in couches_reseau],
            'quality': quality,
            'format_export': format_export
        },
        'fichiers_crees': {}
    }
    
    info_crs = harmoniser_crs(dem_path, couches_reseau, crs_cible)
    crs_utilise = info_crs['crs_utilise']
    
    aire_etude = determiner_aire_etude(couches_reseau, buffer_meters, crs_utilise)
    
    contours = generer_contours(
        dem_path,
        aire_etude,
        contour_interval,
        crs_utilise,
        quality
    )
    
    contours_clipped = clipper_contours(contours, aire_etude)
    
    base_name = Path(dem_path).stem
    ext = {'shp': '.shp', 'geojson': '.geojson', 'gpkg': '.gpkg'}[format_export]
    output_contours = output_dir / f"{base_name}_contours_clipped{ext}"
    
    exporter_contours(contours_clipped, str(output_contours), format_export)
    resultats['fichiers_crees']['contours'] = str(output_contours)
    
    if creer_html:
        output_html = output_dir / f"{base_name}_contours.html"
        visualiser_contours(
            contours_clipped,
            str(output_html),
            True,
            max(1, len(contours_clipped) // 20)
        )
        resultats['fichiers_crees']['html'] = str(output_html)
    
    if export_carte:
        output_carte = output_dir / f"{base_name}_contours.png"
        try:
            exporter_carte(
                contours_clipped,
                aire_etude,
                str(output_carte),
                format_export='png'
            )
            resultats['fichiers_crees']['carte'] = str(output_carte)
        except Exception as e:
            logger.warning(f"Export carte échoué: {e}")
    
    doc_path = output_dir / "contours_documentation.md"
    resultats['parametres']['methode_clipping'] = 'intersection'
    resultats['parametres']['output_contours'] = str(output_contours)
    resultats['parametres']['output_html'] = resultats['fichiers_crees'].get('html', '')
    resultats['parametres']['output_carte'] = resultats['fichiers_crees'].get('carte', '')
    
    documenter_parametres(resultats['parametres'], str(doc_path))
    resultats['fichiers_crees']['documentation'] = str(doc_path)
    
    logger.info("\n" + "=" * 60)
    logger.info("WORKFLOW TERMINÉ AVEC SUCCÈS")
    logger.info("=" * 60)
    logger.info(f"  Contours générés : {len(contours_clipped)}")
    logger.info(f"  Fichiers créés : {len(resultats['fichiers_crees'])}")
    
    return resultats


AUTOMATISATION_PYQGIS = """
# Option PyQGIS pour automatisation (script .py pour QGIS ouProcessing)

import os
from qgis.core import (
    Qgis,Qgisprocessing, edit, 
    feature, field, Geometry,
    vectorLayer, vectorFileWriter,
    project, NULL
)
from qgis.analysis import QgsNativeAlgorithms
from processing.core.Processing import Processing

Processing.initialize()
QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())

def generer_contours_pyqgis(dem_path,reseau_paths,output_path,
                            contour_interval=10,crs='EPSG:32631'):
    # Charger DEM
    dem_layer = processing.run("gdal:rasterize", {
        'INPUT': dem_path,
        'BAND': 1,
        'OUTPUT': output_path
    })['OUTPUT']
    
    # Créer aire d'étude depuis réseau
    layers = [QgsVectorLayer(p, os.path.basename(p), 'ogr') for p in reseau_paths]
    merged = processing.run("native:mergevectorlayers", {
        'LAYERS': layers,
        'OUTPUT': 'memory:'
    })['OUTPUT']
    
    aire = processing.run("native:boundingbox", {
        'INPUT': merged,
        'OUTPUT': 'memory:'
    })['OUTPUT']
    
    # Générer contours
    contours = processing.run("gdal:contour", {
        'INPUT': dem_layer,
        'BAND': 1,
        'INTERVAL': contour_interval,
        'OUTPUT': output_path
    })['OUTPUT']
    
    # Clipper avec aire
    clipped = processing.run("native:clip", {
        'INPUT': contours,
        'OVERLAY': aire,
        'OUTPUT': output_path
    })['OUTPUT']
    
    return clipped
"""

AUTOMATISATION_GDAL = """
# Option GDAL/OGR pour automation en ligne de commande

# Étape 1: Vérification CRS
gdalinfo dem.tif | grep -i "crs"

# Étape 2: Générer les contours (sans clipping)
gdal_contour -a elevation -i 10.0 dem.tif contours_all.shp

# Étape 3: Créer le polygone d'étude depuis les couches réseau
ogr2ogr -s_srs EPSG:32631 -t_srs EPSG:32631 -merge_bounds reseau.shp etude.shp

# Étape 4: Clipper les contours
ogr2ogr -clipsrc etude.shp contours_clipped.shp contours_all.shp

# Étape 5: Exporter en GeoJSON
ogr2ogr -f GeoJSON contours.geojson contours_clipped.shp

# Script Bash complet
#!/bin/bash
DEM="dem.tif"
RESEAU="reseau.shp"
INTERVALLE=10
CRS="EPSG:32631"

gdal_contour -a elevation -i $INTERVALLE -s_srs $CRS $DEM contours_all.shp
ogr2ogr -s_srs $CRS $CRS etude_bounds.shp $RESEAU
ogr2ogr -clipsrc etude_bounds.shp contours_clipped.shp contours_all.shp
ogr2ogr -f GeoJSON contours_clipped.geojson contours_clipped.shp
"""


if __name__ == '__main__':
    DEM_PATH = r"D:\IA Water Data Analysis\Assainissement\Générateur de fichier inp pour swmm 5.2\AST14DEM_00407152025093958_20251010054647.tif"
    RESEAU_PATHS = [
        r"D:\IA Water Data Analysis\Assainissement\Assainissement_Ville.gpkg"
    ]
    
    resultats = executer_workflow(
        dem_path=DEM_PATH,
        couches_reseau=RESEAU_PATHS,
        output_dir=".",
        contour_interval=10.0,
        crs_cible="EPSG:32631",
        buffer_meters=0.0,
        quality='medium',
        format_export='geojson'
    )
    
    print("\n=== RÉSULTATS ===")
    for cle, valeur in resultats.items():
        print(f"{cle}: {valeur}")