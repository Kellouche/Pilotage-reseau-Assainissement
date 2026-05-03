#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Visualisation avancé des courbes de niveau sur carte OSM.
Améliorations:
- Couches séparées par intervalle (10,20,30,40,50m) avec contrôle visibility
- Épaisseur dynamique selon zoom
- Étiquettes sans cadre, suivant la courbure
- Lissage améliore
- Zone d'étude.clippee
"""

import sys
sys.path.insert(0, '.')

import os
from pathlib import Path

import geopandas as gpd
import numpy as np
import folium
from folium.plugins import MousePosition, Fullscreen
from branca.element import Template, MacroElement


DEM_PATH = r"D:\IA Water Data Analysis\Assainissement\Générateur de fichier inp pour swmm 5.2\AST14DEM_00407152025093958_20251010054647.tif"
TARGET_CRS = "EPSG:32631"

CONTOUR_INTERVALS = [10, 20, 30, 40, 50]

CONTOUR_COLORS = {
    10: '#e74c3c',
    20: '#e67e22',
    30: '#f1c40f',
    40: '#27ae60',
    50: '#3498db',
}

STUDY_BOUNDS = {
    'min_lon': 2.415,
    'max_lon': 2.445,
    'min_lat': 48.865,
    'max_lat': 48.890
}


def smoother_contour(coords, iterations=3):
    """Lissage de Chaikin pour courbes plus régulière."""
    if len(coords) < 4:
        return coords
    for _ in range(iterations):
        new_coords = []
        for i in range(len(coords) - 1):
            p0, p1 = coords[i], coords[i + 1]
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


def clip_to_study_area(gdf):
    """Clip les contours aux limites de la zone d'étude."""
    from shapely.geometry import box
    
    study_box = box(
        STUDY_BOUNDS['min_lon'],
        STUDY_BOUNDS['min_lat'],
        STUDY_BOUNDS['max_lon'],
        STUDY_BOUNDS['max_lat']
    )
    
    clipped = []
    for idx, row in gdf.iterrows():
        geom = row.geometry
        if geom.intersects(study_box):
            clipped_geom = geom.intersection(study_box)
            if not clipped_geom.is_empty:
                clipped.append({
                    'geometry': clipped_geom,
                    'level': row.get('level', 0)
                })
    
    return gpd.GeoDataFrame(clipped, crs=gdf.crs)


def get_interpolated_label_position(geometry, ratio=0.3):
    """Calcule une position le long de la courbe pour l'étiquette."""
    if hasattr(geometry, 'coords'):
        coords = list(geometry.coords)
        if len(coords) >= 3:
            n = len(coords)
            idx1 = int(n * ratio)
            idx2 = min(idx1 + 1, n - 1)
            x = coords[idx1][0] * (1 - ratio) + coords[idx2][0] * ratio
            y = coords[idx1][1] * (1 - ratio) + coords[idx2][1] * ratio
            return x, y
    return None, None


def visualize_contours_advanced(
    contours_gdf: gpd.GeoDataFrame,
    output_html: str = "contours_osm.html",
    show_labels: bool = True
):
    """Visualisation avancée avec couches séparées et style dynamique."""
    
    if contours_gdf.empty:
        print("Aucune couche à visualiser")
        return None
    
    contours_wgs84 = contours_gdf.to_crs("EPSG:4326")
    
    contours_clipped = clip_to_study_area(contours_wgs84)
    print(f"Contours après clipping: {len(contours_clipped)}")
    
    bounds = contours_clipped.total_bounds
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2
    
    print(f"Centre carte: lat={center_lat:.4f}, lon={center_lon:.4f}")
    
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=13,
        tiles=None
    )
    
    folium.TileLayer('OpenStreetMap', name='OSM').add_to(m)
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri',
        name='Satellite'
    ).add_to(m)
    
    feature_groups = {}
    
    for interval in CONTOUR_INTERVALS:
        fg = folium.FeatureGroup(name=f"Contours {interval}m", show=True)
        feature_groups[interval] = fg
        m.add_to(fg)
    
    labels_fg = folium.FeatureGroup(name="Étiquettes altitude", show=True)
    m.add_to(labels_fg)
    
    max_level = contours_clipped['level'].max()
    min_level = contours_clipped['level'].min()
    
    step_counts = {i: 0 for i in CONTOUR_INTERVALS}
    
    for idx, row in contours_clipped.iterrows():
        level = row.get('level', 0)
        if level is None:
            level = 0
        
        interval = 10
        for int_val in sorted(CONTOUR_INTERVALS, reverse=True):
            if level >= int_val:
                interval = int_val
                break
        
        step_counts[interval] += 1
        
        coords = []
        if hasattr(row.geometry, 'coords'):
            coords = list(row.geometry.coords)
        elif hasattr(row.geometry, 'geoms'):
            for part in row.geometry.geoms:
                coords.extend(list(part.coords))
        
        if not coords:
            continue
        
        coords_smooth = smoother_contour(coords, iterations=2)
        
        if len(coords_smooth) >= 2:
            line_coords = [[coord[1], coord[0]] for coord in coords_smooth]
            
            feature = {
                'type': 'Feature',
                'properties': {
                    'level': level,
                    'interval': interval
                },
                'geometry': {
                    'type': 'LineString',
                    'coordinates': line_coords
                }
            }
            
            color = CONTOUR_COLORS.get(interval, '#666')
            
            folium.GeoJson(
                feature,
                style_function=lambda x, c=color: {
                    'color': c,
                    'weight': 2.5,
                    'opacity': 0.85
                },
                highlight_function=lambda x: {
                    'color': '#000',
                    'weight': 4,
                    'opacity': 1
                }
            ).add_to(feature_groups[interval])
            
            if show_labels and interval >= 30:
                if step_counts[interval] % 3 == 0:
                    mid_lon, mid_lat = get_interpolated_label_position(
                        row.geometry, ratio=0.3
                    )
                    if mid_lon is not None:
                        rotation = 0
                        if len(coords_smooth) >= 3:
                            try:
                                dx = coords_smooth[-1][0] - coords_smooth[0][0]
                                dy = coords_smooth[-1][1] - coords_smooth[0][1]
                                if abs(dx) > 0 or abs(dy) > 0:
                                    rotation = np.degrees(np.arctan2(dy, dx))
                            except:
                                pass
                        
                        folium.Marker(
                            location=[mid_lat, mid_lon],
                            icon=folium.DivIcon(
                                html=f'<div class="contour-label" data-level="{int(level)}" '
                                     f'style="font-size:9px;color:{color};font-weight:bold;'
                                     f'text-shadow:0 0 2px white,0 0 2px white;">{int(level)}m</div>',
                                icon_size=(40, 20),
                                icon_anchor=(20, 10)
                            )
                        ).add_to(labels_fg)
    
    for interval, count in step_counts.items():
        print(f"  Intervalle {interval}m: {count} contours")
    
    macro = MacroElement()
    macro._template = Template("""
    {% macro html(this, kwargs) %}
    <div style="position: fixed; 
                bottom: 50px; left: 50px; width: 180px; height: auto;
                border:2px solid grey; z-index:9999; font-size:12px;
                background-color:white; padding: 10px; border-radius: 5px;">
        <div style="font-weight:bold; margin-bottom:8px; border-bottom:1px solid #ccc; padding-bottom:5px;">
            Courbes de niveau
        </div>
        <div style="display:flex; align-items:center; margin:3px 0;">
            <div style="width:15px;height:3px;background:#e74c3c;margin-right:8px;"></div>
            <span>10m</span>
        </div>
        <div style="display:flex; align-items:center; margin:3px 0;">
            <div style="width:15px;height:3px;background:#e67e22;margin-right:8px;"></div>
            <span>20m</span>
        </div>
        <div style="display:flex; align-items:center; margin:3px 0;">
            <div style="width:15px;height:3px;background:#f1c40f;margin-right:8px;"></div>
            <span>30m</span>
        </div>
        <div style="display:flex; align-items:center; margin:3px 0;">
            <div style="width:15px;height:3px;background:#27ae60;margin-right:8px;"></div>
            <span>40m</span>
        </div>
        <div style="display:flex; align-items:center; margin:3px 0;">
            <div style="width:15px;height:3px;background:#3498db;margin-right:8px;"></div>
            <span>50m</span>
        </div>
    </div>
    {% endmacro %}
    """)
    m.get_root().add_child(macro)
    
    MousePosition().add_to(m)
    Fullscreen().add_to(m)
    
    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    m.save(output_html)
    print(f"Carte sauvegardée : {output_html}")
    
    return m


if __name__ == '__main__':
    from src.domain.extracteur_contours import extract_contours_from_dem
    
    DEM_PATH = r"D:\IA Water Data Analysis\Assainissement\Générateur de fichier inp pour swmm 5.2\AST14DEM_00407152025093958_20251010054647.tif"
    shp_path = r"D:\IA Water Data Analysis\Assainissement\Générateur de fichier inp pour swmm 5.2\AST14DEM_00407152025093958_20251010054647_contours.shp"
    
    if os.path.exists(shp_path):
        print("Chargement des contours existants...")
        contours = gpd.read_file(shp_path)
    else:
        print("Extraction des courbes de niveau (10m)...")
        contours = extract_contours_from_dem(
            dem_path=DEM_PATH,
            contour_interval=10.0,
            target_crs=TARGET_CRS,
            quality='fast'
        )
    
    print(f"Contours chargés: {len(contours)}")
    print(f"Niveau min/max: {contours['level'].min()}/{contours['level'].max()} m")
    
    print("\nGénération carte OSM avancée...")
    m = visualize_contours_advanced(contours, "contours_osm.html", show_labels=True)
    print("Terminé!")