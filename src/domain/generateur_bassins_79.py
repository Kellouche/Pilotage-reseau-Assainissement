"""
Module de sectorisation et génération des 79 bassins versants urbains
et intégration hiérarchique des sous-bassins Voronoï pour SWMM 5.2.
Fichier : src/domain/generateur_bassins_79.py
"""

import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import time
import math
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import colorsys

import numpy as np
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon, MultiPolygon, MultiPoint, mapping
from shapely.ops import voronoi_diagram, unary_union
from shapely import STRtree

from src.domain.graphe_reseau import construire_graphe
from src.domain.detecteur_clusters import trouver_exutoires_physiques


def generer_palette_couleurs(nb_couleurs: int) -> List[str]:
    """Génère une palette de couleurs HSL contrastées et réparties harmonieusement."""
    couleurs = []
    # Palette de base pour les premiers exutoires emblématiques
    base_palette = [
        "#e74c3c", "#3498db", "#2ecc71", "#9b59b6", "#f39c12",
        "#1abc9c", "#d35400", "#e84393", "#00cec9", "#6c5ce7",
        "#fdcb6e", "#0984e3", "#00b894", "#b2bec3", "#e17055",
        "#a29bfe", "#fd79a8", "#636e72", "#2d3436", "#55efc4"
    ]
    if nb_couleurs <= len(base_palette):
        return base_palette[:nb_couleurs]

    # Génération HSL équilibrée
    for i in range(nb_couleurs):
        hue = (i * 0.618033988749895) % 1.0  # Nombre d'or pour étaler les teintes
        saturation = 0.75 + (i % 3) * 0.10
        lightness = 0.48 + (i % 2) * 0.08
        r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
        hex_color = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
        couleurs.append(hex_color)
    return couleurs


def partitionner_79_bassins_versants(
    gpkg_path: str,
    buffer_voronoi_m: float = 35.0,
    sauvegarder_gpkg: bool = True
) -> Dict[str, Any]:
    """
    Construit les 79 macro-bassins versants urbains et intègre pour chacun
    ses sous-bassins élémentaires Voronoï.
    
    1. Attribue les nœuds connectés au premier exutoire aval rencontré dans le graphe.
    2. Rapproche géométriquement les regards et tronçons orphelins du bassin le plus proche.
    3. Isole les orphelins dans un fichier et une couche dédiée pour audit.
    4. Calcule les 10 538 polygones Voronoï élémentaires avec leurs attributs SWMM.
    5. Fusionne (unary_union) les Voronoï par exutoire pour former les 79 bassins continus.
    6. Persiste directement dans le GeoPackage (si demandé) et met en cache.
    """
    t0 = time.time()
    gpkg_p = Path(gpkg_path)
    if not gpkg_p.exists():
        raise FileNotFoundError(f"GeoPackage introuvable : {gpkg_path}")

    print(f"[bassins_79] Construction du graphe depuis {gpkg_p.name}...", flush=True)
    G = construire_graphe(str(gpkg_p))
    exutoires_physiques = trouver_exutoires_physiques(G)
    nb_exutoires = len(exutoires_physiques)
    print(f"[bassins_79] {nb_exutoires} exutoires physiques identifiés.", flush=True)

    # 1. Neutraliser les boucles / cycles pour un parcours amont strict
    try:
        while True:
            cycle = nx.find_cycle(G, orientation="original")
            G.remove_edge(cycle[-1][0], cycle[-1][1])
    except nx.NetworkXNoCycle:
        pass

    # 2. Attribution de chaque nœud au premier exutoire aval rencontré
    #    Chaque exutoire draine son réseau amont direct jusqu'aux exutoires amont voisins
    ex_set = set(exutoires_physiques.keys())
    node_to_exutoire: Dict[str, str] = {}

    # Tri par priorité hydraulique
    exutoires_tries = sorted(exutoires_physiques.items(), key=lambda x: x[1].get('priorite', 99))

    for ex_id, _ in exutoires_tries:
        node_to_exutoire[ex_id] = ex_id
        queue = [ex_id]
        while queue:
            curr = queue.pop(0)
            for pred in G.predecessors(curr):
                if pred not in ex_set and pred not in node_to_exutoire:
                    node_to_exutoire[pred] = ex_id
                    queue.append(pred)

    print(f"[bassins_79] {len(node_to_exutoire)} nœuds connectés directement aux {nb_exutoires} exutoires.", flush=True)

    # 3. Charger les couches Regards et Canalisations du GPKG
    layers = gpd.list_layers(str(gpkg_p))['name'].tolist()
    regard_layer = next((l for l in layers if 'regard' in l.lower()), None)
    pipe_layer = next((l for l in layers if any(k in l.lower() for k in ['canalisat', 'conduit', 'pipe', 'troncon']) and 'désaffect' not in l.lower() and 'desaffect' not in l.lower()), None)

    if not regard_layer:
        raise ValueError("Couche Regards introuvable dans le GeoPackage.")

    regards_gdf = gpd.read_file(str(gpkg_p), layer=regard_layer)
    pipes_gdf = gpd.read_file(str(gpkg_p), layer=pipe_layer) if pipe_layer else gpd.GeoDataFrame()
    crs_metrique = regards_gdf.crs or "EPSG:32631"

    # Index spatial des regards connectés pour le rattachement des orphelins
    connected_points = []
    connected_ex_ids = []
    for idx, row in regards_gdf.iterrows():
        c = str(row.get('Code', row.get('id', idx)))
        if c in node_to_exutoire:
            connected_points.append(row.geometry)
            connected_ex_ids.append(node_to_exutoire[c])

    if not connected_points:
        # Fallback si aucun regard n'est connecté par code : utiliser la position des exutoires
        for ex_id, ex_data in exutoires_physiques.items():
            if 'x' in ex_data and 'y' in ex_data:
                connected_points.append(Point(float(ex_data['x']), float(ex_data['y'])))
                connected_ex_ids.append(ex_id)

    conn_tree = STRtree(connected_points)

    # Palette de couleurs
    palette = generer_palette_couleurs(nb_exutoires)
    exutoire_id_list = list(exutoires_physiques.keys())
    ex_to_color = {ex_id: palette[i % len(palette)] for i, ex_id in enumerate(exutoire_id_list)}
    ex_to_num = {ex_id: i + 1 for i, ex_id in enumerate(exutoire_id_list)}

    # 4. Génération du diagramme de Voronoï sur tous les regards
    points_list = [g for g in regards_gdf.geometry if isinstance(g, Point)]
    multipoints = MultiPoint(points_list)
    diagramme = voronoi_diagram(multipoints)
    cellules = list(diagramme.geoms) if hasattr(diagramme, 'geoms') else [diagramme]

    # Index spatial des cellules Voronoï pour appariement 1-à-1 ultra-rapide
    cell_tree = STRtree(cellules)
    pt_indices, cell_indices = cell_tree.query(points_list, predicate='intersects')
    pt_to_cell: Dict[int, Polygon] = {}
    for p_idx, c_idx in zip(pt_indices, cell_indices):
        if p_idx not in pt_to_cell:
            pt_to_cell[p_idx] = cellules[c_idx]

    # 5. Découpage et enrichissement des sous-bassins Voronoï
    voronoi_records = []
    bassin_polygons_map: Dict[str, List[Polygon]] = {ex_id: [] for ex_id in exutoire_id_list}
    orphelins_regards_records = []

    for i, row in regards_gdf.iterrows():
        pt = row.geometry
        if not isinstance(pt, Point):
            continue

        raw_code = row.get('Code', row.get('id', i))
        str_code = str(raw_code).strip()
        if str_code.endswith('.0'):
            str_code = str_code[:-2]

        # Vérifier connexion topologique ou rattachement orphelin
        is_orphelin = False
        dist_snap = 0.0

        if str_code in node_to_exutoire:
            assigned_ex = node_to_exutoire[str_code]
        elif str(raw_code) in node_to_exutoire:
            assigned_ex = node_to_exutoire[str(raw_code)]
        else:
            # Orphelin -> Snapper au regard connecté le plus proche
            is_orphelin = True
            n_idx = conn_tree.nearest(pt)
            assigned_ex = connected_ex_ids[n_idx]
            dist_snap = round(float(pt.distance(connected_points[n_idx])), 2)
            orphelins_regards_records.append({
                "code_regard": str_code,
                "exutoire_rattache": assigned_ex,
                "nom_exutoire": exutoires_physiques.get(assigned_ex, {}).get('nom', str(assigned_ex)),
                "distance_rattachement_m": dist_snap,
                "commune": row.get('COMMUNE', ''),
                "nom_voie": row.get('NOMVOIE', ''),
                "geometry": pt
            })

        # Cellule de Voronoï bornée par le buffer de drainage urbain
        cell = pt_to_cell.get(i)
        if cell is not None and not cell.is_empty:
            clipped_cell = cell.intersection(pt.buffer(buffer_voronoi_m))
            if clipped_cell.is_empty:
                clipped_cell = pt.buffer(5.0)
        else:
            clipped_cell = pt.buffer(buffer_voronoi_m)

        area_m2 = round(float(clipped_cell.area), 2)
        area_ha = round(area_m2 / 10000.0, 4)
        width_m = round(max(math.sqrt(area_m2), 5.0), 2)

        ex_info = exutoires_physiques.get(assigned_ex, {})
        b_num = ex_to_num.get(assigned_ex, 1)
        b_color = ex_to_color.get(assigned_ex, "#3498db")

        voronoi_records.append({
            "subcatchment_id": f"SB_{str_code}",
            "outlet": str_code,
            "id_bassin": b_num,
            "exutoire_id": str(assigned_ex),
            "nom_bassin": ex_info.get('nom', f"Bassin_{b_num}"),
            "type_exutoire": ex_info.get('type', 'exutoire'),
            "area_ha": area_ha,
            "area_m2": area_m2,
            "imperv_pct": 70.0,
            "width_m": width_m,
            "slope_pct": 0.5,
            # Infiltration Horton
            "f0": 75.0,
            "fc": 10.0,
            "decay_k": 4.0,
            "is_orphelin": 1 if is_orphelin else 0,
            "dist_snap_m": dist_snap,
            "couleur": b_color,
            "geometry": clipped_cell
        })

        bassin_polygons_map[assigned_ex].append(clipped_cell)

    gdf_voronoi = gpd.GeoDataFrame(voronoi_records, crs=crs_metrique)
    print(f"[bassins_79] {len(gdf_voronoi)} sous-bassins Voronoï générés et typés.", flush=True)

    # 6. Fusion géométrique (unary_union) pour créer les 79 macro-bassins versants
    bassins_records = []
    print("[bassins_79] Fusion spatiale des 79 macro-bassins versants urbains...", flush=True)

    for ex_id, geoms in bassin_polygons_map.items():
        ex_info = exutoires_physiques.get(ex_id, {})
        b_num = ex_to_num.get(ex_id, 1)
        b_color = ex_to_color.get(ex_id, "#3498db")

        if geoms:
            geom_union = unary_union(geoms)
            area_m2 = round(float(geom_union.area), 2)
            area_ha = round(area_m2 / 10000.0, 2)
        else:
            # Si exutoire isolé sans cellule, créer un polygone tampon minimal
            ex_pt = Point(float(ex_info.get('x', 0)), float(ex_info.get('y', 0)))
            geom_union = ex_pt.buffer(buffer_voronoi_m)
            area_m2 = round(float(geom_union.area), 2)
            area_ha = round(area_m2 / 10000.0, 2)

        # Statistiques regards et conduites
        regards_in_bassin = [r for r in voronoi_records if r['exutoire_id'] == str(ex_id)]
        nb_regards_total = len(regards_in_bassin)
        nb_regards_orphelins = sum(1 for r in regards_in_bassin if r['is_orphelin'] == 1)

        bassins_records.append({
            "id_bassin": b_num,
            "exutoire_id": str(ex_id),
            "nom_exutoire": ex_info.get('nom', f"Exutoire_{b_num}"),
            "type_exutoire": ex_info.get('type', 'exutoire'),
            "surface_ha": area_ha,
            "surface_m2": area_m2,
            "nb_regards": nb_regards_total,
            "nb_regards_orphelins": nb_regards_orphelins,
            "couleur": b_color,
            "geometry": geom_union
        })

    # Trier par numéro de bassin 1..79
    bassins_records.sort(key=lambda x: x['id_bassin'])
    gdf_bassins_79 = gpd.GeoDataFrame(bassins_records, crs=crs_metrique)

    # 7. Identifier et colorier les canalisations par bassin versant
    pipes_by_exutoire: Dict[str, List[Dict[str, Any]]] = {ex_id: [] for ex_id in exutoire_id_list}
    if not pipes_gdf.empty:
        try:
            pipes_wgs84 = pipes_gdf.to_crs("EPSG:4326")
            for idx, row in pipes_wgs84.iterrows():
                geom = row.geometry
                if geom and not geom.is_empty:
                    pipe_id = str(row.get('id', row.get('ID', idx)))
                    u_val = str(row.get('noeud_amont', row.get('AMONT', row.get('amont', '')))).strip()
                    v_val = str(row.get('noeud_aval', row.get('AVAL', row.get('aval', '')))).strip()
                    if u_val.endswith('.0'): u_val = u_val[:-2]
                    if v_val.endswith('.0'): v_val = v_val[:-2]

                    assigned_pipe_ex = node_to_exutoire.get(u_val) or node_to_exutoire.get(v_val)
                    if not assigned_pipe_ex and not connected_points:
                        assigned_pipe_ex = exutoire_id_list[0]
                    elif not assigned_pipe_ex:
                        # Rapprochement spatial du centroïde de la conduite
                        centroid = geom.centroid
                        # Conversion rapide
                        nearest_p_idx = conn_tree.nearest(Point(row.geometry.centroid.x, row.geometry.centroid.y))
                        assigned_pipe_ex = connected_ex_ids[nearest_p_idx]

                    b_num = ex_to_num.get(assigned_pipe_ex, 1)
                    b_color = ex_to_color.get(assigned_pipe_ex, "#3498db")

                    feat_pipe = {
                        "type": "Feature",
                        "geometry": mapping(geom),
                        "properties": {
                            "conduit_id": pipe_id,
                            "cluster_id": b_num,
                            "couleur": b_color,
                            "diametre": row.get('DIAMETRE', row.get('diametre', None)),
                            "longueur": row.get('LONGUEUR', row.get('longueur', None)),
                            "materiau": row.get('MATERIAU', row.get('materiau', None))
                        }
                    }
                    if assigned_pipe_ex in pipes_by_exutoire:
                        pipes_by_exutoire[assigned_pipe_ex].append(feat_pipe)
        except Exception as e:
            print(f"[bassins_79] Erreur classification conduites: {e}", flush=True)

    gdf_orphelins_regards = gpd.GeoDataFrame(orphelins_regards_records, crs=crs_metrique) if orphelins_regards_records else gpd.GeoDataFrame()

    total_surface_ha = round(float(gdf_bassins_79['surface_ha'].sum()), 2)
    print(f"[bassins_79] {len(gdf_bassins_79)} bassins versants créés (Surface totale : {total_surface_ha} ha).", flush=True)
    print(f"[bassins_79] Regards orphelins isolés : {len(gdf_orphelins_regards)}.", flush=True)

    # 8. Persistance dans le GeoPackage (si demandé)
    if sauvegarder_gpkg:
        print(f"[bassins_79] Écriture des nouvelles couches dans {gpkg_p.name}...", flush=True)
        try:
            gdf_bassins_79.to_file(str(gpkg_p), layer="bassins_versants_79", driver="GPKG")
            print("[bassins_79] Couche 'bassins_versants_79' sauvegardée.", flush=True)
        except Exception as e:
            print(f"[bassins_79] Erreur sauvegarde bassins_versants_79: {e}", flush=True)

        try:
            gdf_voronoi.to_file(str(gpkg_p), layer="sous_bassins_voronoi", driver="GPKG")
            print("[bassins_79] Couche 'sous_bassins_voronoi' sauvegardée.", flush=True)
        except Exception as e:
            print(f"[bassins_79] Erreur sauvegarde sous_bassins_voronoi: {e}", flush=True)

        if not gdf_orphelins_regards.empty:
            try:
                gdf_orphelins_regards.to_file(str(gpkg_p), layer="elements_orphelins_regards", driver="GPKG")
                print("[bassins_79] Couche 'elements_orphelins_regards' sauvegardée.", flush=True)
            except Exception as e:
                print(f"[bassins_79] Erreur sauvegarde orphelins: {e}", flush=True)

    # 9. Export du fichier isolé des orphelins (GeoJSON) dans le dossier upload
    orphelins_geojson_path = gpkg_p.parent / "elements_orphelins.geojson"
    if not gdf_orphelins_regards.empty:
        try:
            gdf_orph_wgs84 = gdf_orphelins_regards.to_crs("EPSG:4326")
            gdf_orph_wgs84.to_file(str(orphelins_geojson_path), driver="GeoJSON")
            print(f"[bassins_79] Fichier d'isolation exporté : {orphelins_geojson_path.name}", flush=True)
        except Exception as e:
            print(f"[bassins_79] Erreur export orphelins.geojson: {e}", flush=True)

    # 10. Préparation des structures GeoJSON WGS84 pour l'API et le cache Web
    gdf_bassins_wgs84 = gdf_bassins_79.to_crs("EPSG:4326")
    bassins_geojson = json.loads(gdf_bassins_wgs84.to_json(na="drop"))

    gdf_voronoi_wgs84 = gdf_voronoi.to_crs("EPSG:4326")
    voronoi_geojson = json.loads(gdf_voronoi_wgs84.to_json(na="drop"))

    # Construction des 79 items de resultats pour le cockpit
    results_formatted = []
    total_troncons_assignes = 0

    for feat in bassins_geojson.get("features", []):
        props = feat.get("properties", {})
        b_id = props.get("id_bassin")
        ex_id_str = props.get("exutoire_id")
        b_nom = props.get("nom_exutoire")
        b_type = props.get("type_exutoire")
        b_color = props.get("couleur")

        feat["properties"]["type"] = "bassin_urbain"
        feat["properties"]["cluster_id"] = b_id
        feat["properties"]["nom"] = b_nom
        feat["properties"]["exutoire_type"] = b_type
        feat["properties"]["couleur"] = b_color

        cluster_features = [feat]

        # Ajouter l'exutoire ponctuel s'il a des coordonnées valides
        ex_info = exutoires_physiques.get(ex_id_str, {})
        if 'x' in ex_info and 'y' in ex_info:
            try:
                pt_ex = Point(float(ex_info['x']), float(ex_info['y']))
                gdf_ex_pt = gpd.GeoSeries([pt_ex], crs=crs_metrique).to_crs("EPSG:4326")
                ex_geom = gdf_ex_pt.iloc[0]
                cluster_features.append({
                    "type": "Feature",
                    "geometry": mapping(ex_geom),
                    "properties": {
                        "type": "exutoire",
                        "cluster_id": b_id,
                        "nom": b_nom,
                        "exutoire_type": b_type
                    }
                })
            except Exception:
                pass

        # Ajouter les conduites de ce bassin
        bassin_pipes = pipes_by_exutoire.get(ex_id_str, [])
        cluster_features.extend(bassin_pipes)
        total_troncons_assignes += len(bassin_pipes)

        results_formatted.append({
            "cluster": {
                "id": b_id,
                "nom": b_nom,
                "surface_ha": props.get("surface_ha")
            },
            "exutoire": {
                "nom": b_nom,
                "type": b_type
            },
            "stats": {
                "surface_ha": props.get("surface_ha"),
                "nb_regards": props.get("nb_regards"),
                "nb_regards_orphelins": props.get("nb_regards_orphelins"),
                "nb_conduites": len(bassin_pipes)
            },
            "infrastructures": {
                "regards": props.get("nb_regards"),
                "conduites": len(bassin_pipes)
            },
            "geojson": {
                "type": "FeatureCollection",
                "features": cluster_features
            },
            "troncons": len(bassin_pipes)
        })

    # Sauvegarde du cache disque pour rapidité web instantanée (< 50ms)
    cache_clusters_path = gpkg_p.with_suffix(".clusters_cache.json")
    try:
        clusters_cache_data = {
            "status": "success",
            "exutoires_physiques": nb_exutoires,
            "clusters_crees": len(gdf_bassins_79),
            "surface_totale_ha": total_surface_ha,
            "nb_sous_bassins_voronoi": len(gdf_voronoi),
            "nb_regards_orphelins": len(gdf_orphelins_regards),
            "troncons_connectes": total_troncons_assignes,
            "bassins_geojson": bassins_geojson,
            "resultats": results_formatted
        }
        with open(cache_clusters_path, "w", encoding="utf-8") as f:
            json.dump(clusters_cache_data, f, ensure_ascii=False)
        print(f"[bassins_79] Cache disque des clusters mis à jour : {cache_clusters_path.name}", flush=True)
    except Exception as e:
        print(f"[bassins_79] Erreur écriture cache clusters: {e}", flush=True)

    cache_subcatchments_path = gpkg_p.with_suffix(".subcatchments_cache.json")
    try:
        sub_cache_data = {
            "type": "FeatureCollection",
            "features": voronoi_geojson.get("features", []),
            "total_area_ha": total_surface_ha,
            "subcatchments_count": len(gdf_voronoi)
        }
        with open(cache_subcatchments_path, "w", encoding="utf-8") as f:
            json.dump(sub_cache_data, f, ensure_ascii=False)
        print(f"[bassins_79] Cache disque subcatchments mis à jour : {cache_subcatchments_path.name}", flush=True)
    except Exception as e:
        print(f"[bassins_79] Erreur écriture cache subcatchments: {e}", flush=True)

    elapsed = round(time.time() - t0, 2)
    print(f"[bassins_79] Traitement complet terminé en {elapsed} secondes.", flush=True)

    return {
        "status": "success",
        "nb_bassins": len(gdf_bassins_79),
        "surface_totale_ha": total_surface_ha,
        "nb_voronoi": len(gdf_voronoi),
        "nb_orphelins": len(gdf_orphelins_regards),
        "elapsed_seconds": elapsed,
        "orphelins_file": str(orphelins_geojson_path)
    }
