"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-27
Objet : Génération et calibration des bassins versants pour le scénario 79
================================================================================
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
import pyproj
from shapely.geometry import Point, LineString, Polygon, MultiPolygon, MultiPoint, mapping
from shapely.ops import voronoi_diagram, unary_union, transform
from shapely import STRtree

from src.domain.graphe_reseau import construire_graphe
from src.domain.detecteur_clusters import (
    trouver_exutoires_physiques,
    extraire_adresse_reelle_bassin,
    classifier_type_hydraulique,
)
from src.domain.moteur_swmm import _clean_node_id
from src.domain.generateur_bassins_79_etapes import (
    _etape_affectation_voronoi, _etape_classification_conduites,
    _etape_fusion_bassins,
)
from src.domain.generateur_bassins_79_etapes_resultats import _etape_resultats_formatted
from collections import Counter
import re


def _log_part(*args, **kwargs):
    """Affiche les logs d'ingénierie sauf si le mode silencieux est actif."""
    if os.getenv("DRAINPILOT_SILENT", "").lower() not in ("1", "true", "yes"):
        print(*args, **kwargs)


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

    _log_part(f"[partitionnement] Construction du graphe depuis {gpkg_p.name}...", flush=True)
    G = construire_graphe(str(gpkg_p))
    # Attribution : exutoires physiques + nœuds morts (exutoires implicites).
    # Un fragment connecté aboutissant à un nœud sans sortie n'est PAS orphelin :
    # il est rattaché à son exutoire implicite et soumis à revue.
    exutoires_attribution = trouver_exutoires_physiques(G, inclure_exutoires_implicites=True)
    nb_exutoires = len(exutoires_attribution)
    nb_exutoires_physiques = sum(
        1 for i in exutoires_attribution.values() if i.get('type') != 'exutoire_implicite'
    )
    _log_part(f"[partitionnement] {nb_exutoires} exutoires identifiés ({nb_exutoires_physiques} physiques, {nb_exutoires - nb_exutoires_physiques} implicites).", flush=True)

    # 1. Neutraliser les boucles / cycles pour un parcours amont strict
    try:
        while True:
            cycle = nx.find_cycle(G, orientation="original")
            G.remove_edge(cycle[-1][0], cycle[-1][1])
    except nx.NetworkXNoCycle:
        pass

    # 2. Attribution de chaque nœud au premier exutoire aval rencontré
    #    Chaque exutoire draine son réseau amont direct jusqu'aux exutoires amont voisins
    ex_set = set(exutoires_attribution.keys())
    node_to_exutoire: Dict[str, str] = {}

    # Tri par priorité hydraulique
    exutoires_tries = sorted(exutoires_attribution.items(), key=lambda x: x[1].get('priorite', 99))

    for ex_id, _ in exutoires_tries:
        node_to_exutoire[ex_id] = ex_id
        queue = [ex_id]
        while queue:
            curr = queue.pop(0)
            for pred in G.predecessors(curr):
                if pred not in ex_set and pred not in node_to_exutoire:
                    node_to_exutoire[pred] = ex_id
                    queue.append(pred)

    _log_part(f"[partitionnement] {len(node_to_exutoire)} nœuds connectés directement aux {nb_exutoires} exutoires.", flush=True)

    # Exutoires retenus pour la création de bassins versants fusionnés :
    # - exutoires physiques : toujours ;
    # - exutoires implicites : uniquement si le fragment drainé est significatif
    #   (>= SEUIL_NOEUDS_IMPLICITE nœuds attribués, miroir du min_edges=10 des clusters).
    # Les fragments plus petits restent rattachés (is_orphelin=0) mais sans
    # bassin propre : ils relèvent de la file de revue, pas de la simulation.
    SEUIL_NOEUDS_IMPLICITE = 10
    _comptage_noeuds = Counter(node_to_exutoire.values())
    exutoires_bassins = {
        ex_id: info for ex_id, info in exutoires_attribution.items()
        if info.get('type') != 'exutoire_implicite'
        or _comptage_noeuds.get(ex_id, 0) >= SEUIL_NOEUDS_IMPLICITE
    }
    _log_part(f"[partitionnement] {len(exutoires_bassins)} exutoires retenus pour les bassins versants "
              f"({sum(1 for i in exutoires_bassins.values() if i.get('type') == 'exutoire_implicite')} implicites significatifs).", flush=True)

    # 3. Charger les couches Regards et Canalisations du GPKG
    layers = gpd.list_layers(str(gpkg_p))['name'].tolist()
    regard_layer = next((l for l in layers if 'regard' in l.lower()), None)
    pipe_layer = next((l for l in layers if any(k in l.lower() for k in ['canalisat', 'conduit', 'pipe', 'troncon']) and 'désaffect' not in l.lower() and 'desaffect' not in l.lower()), None)

    if not regard_layer:
        raise ValueError("Couche Regards introuvable dans le GeoPackage.")

    regards_gdf = gpd.read_file(str(gpkg_p), layer=regard_layer)
    pipes_gdf = gpd.read_file(str(gpkg_p), layer=pipe_layer) if pipe_layer else gpd.GeoDataFrame()
    crs_metrique = regards_gdf.crs or "EPSG:32631"

    # Index spatial des regards connectés pour l'audit des distances orphelins
    connected_points = []
    connected_ex_ids = []
    connected_nodes = []
    for idx, row in regards_gdf.iterrows():
        c = str(row.get('Code', row.get('id', idx)))
        if c in node_to_exutoire:
            connected_points.append(row.geometry)
            connected_ex_ids.append(node_to_exutoire[c])
            connected_nodes.append(c)

    if not connected_points:
        # Fallback si aucun regard n'est connecté par code : utiliser la position des exutoires
        for ex_id, ex_data in exutoires_attribution.items():
            if 'x' in ex_data and 'y' in ex_data:
                connected_points.append(Point(float(ex_data['x']), float(ex_data['y'])))
                connected_ex_ids.append(ex_id)
                connected_nodes.append(str(ex_id))

    conn_tree = STRtree(connected_points)

    # Palette de couleurs (exutoires validés pour les bassins fusionnés)
    palette = generer_palette_couleurs(len(exutoires_bassins))
    exutoire_id_list = list(exutoires_bassins.keys())
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

    _etape_affectation_voronoi({
        "G": G,
        "bassin_polygons_map": bassin_polygons_map,
        "buffer_voronoi_m": buffer_voronoi_m,
        "conn_tree": conn_tree,
        "connected_ex_ids": connected_ex_ids,
        "connected_nodes": connected_nodes,
        "connected_points": connected_points,
        "ex_to_color": ex_to_color,
        "ex_to_num": ex_to_num,
        "exutoires_attribution": exutoires_attribution,
        "exutoires_bassins": exutoires_bassins,
        "node_to_exutoire": node_to_exutoire,
        "orphelins_regards_records": orphelins_regards_records,
        "pt_to_cell": pt_to_cell,
        "regards_gdf": regards_gdf,
        "voronoi_records": voronoi_records,
    })

    # Continuité hydraulique : intégrer le fuseau tampon (15m) des conduites connectées
    for u, v, data in G.edges(data=True):
        geom_metric = data.get('geometry')
        if geom_metric is not None and not geom_metric.is_empty:
            assigned_pipe_ex = node_to_exutoire.get(v) or node_to_exutoire.get(u)
            if assigned_pipe_ex and assigned_pipe_ex in bassin_polygons_map:
                bassin_polygons_map[assigned_pipe_ex].append(geom_metric.buffer(15.0))

    gdf_voronoi = gpd.GeoDataFrame(voronoi_records, crs=crs_metrique)
    _log_part(f"[partitionnement] {len(gdf_voronoi)} sous-bassins Voronoï générés et typés.", flush=True)

    # 6. Fusion géométrique (unary_union) pour créer les macro-bassins versants
    bassins_records = []
    _log_part(f"[partitionnement] Fusion spatiale des macro-bassins versants urbains ({len(bassin_polygons_map)} exutoires)...", flush=True)

    _etape_fusion_bassins({
        "G": G,
        "bassin_polygons_map": bassin_polygons_map,
        "bassins_records": bassins_records,
        "buffer_voronoi_m": buffer_voronoi_m,
        "est_invalide": est_invalide,
        "ex_to_color": ex_to_color,
        "ex_to_num": ex_to_num,
        "exutoires_bassins": exutoires_bassins,
        "voronoi_records": voronoi_records,
    })

    # Trier par numéro de bassin
    bassins_records.sort(key=lambda x: x['id_bassin'])
    gdf_bassins_79 = gpd.GeoDataFrame(bassins_records, crs=crs_metrique)

    # 7. Identifier et colorier les canalisations par bassin versant
    pipes_by_exutoire: Dict[str, List[Dict[str, Any]]] = {ex_id: [] for ex_id in exutoire_id_list}
    orphelins_pipes_features: List[Dict[str, Any]] = []
    fragments_pipes_features: List[Dict[str, Any]] = []

    _log_part("[partitionnement] Classification topologique des conduites par exutoire...", flush=True)
    _etape_classification_conduites({
        "G": G,
        "crs_metrique": crs_metrique,
        "ex_set": ex_set,
        "ex_to_color": ex_to_color,
        "ex_to_num": ex_to_num,
        "fragments_pipes_features": fragments_pipes_features,
        "gdf_bassins_79": gdf_bassins_79,
        "node_to_exutoire": node_to_exutoire,
        "orphelins_pipes_features": orphelins_pipes_features,
        "pipes_by_exutoire": pipes_by_exutoire,
        "pipes_gdf": pipes_gdf,
        "total_troncons_assignes": total_troncons_assignes,
    })

    gdf_orphelins_regards = gpd.GeoDataFrame(orphelins_regards_records, crs=crs_metrique) if orphelins_regards_records else gpd.GeoDataFrame()

    total_surface_ha = round(float(gdf_bassins_79['surface_ha'].sum()), 2)
    _log_part(f"[partitionnement] {len(gdf_bassins_79)} bassins versants créés (Surface totale : {total_surface_ha} ha).", flush=True)
    _log_part(f"[partitionnement] Regards orphelins isolés : {len(gdf_orphelins_regards)}.", flush=True)

    # 8. Persistance dans le GeoPackage (si demandé)
    if sauvegarder_gpkg:
        _log_part(f"[partitionnement] Écriture des nouvelles couches dans {gpkg_p.name}...", flush=True)
        try:
            gdf_bassins_79.to_file(str(gpkg_p), layer="bassins_versants_79", driver="GPKG")
            _log_part("[partitionnement] Couche 'bassins_versants_79' sauvegardée.", flush=True)
        except Exception as e:
            _log_part(f"[partitionnement] Erreur sauvegarde bassins_versants_79: {e}", flush=True)

        try:
            gdf_voronoi.to_file(str(gpkg_p), layer="sous_bassins_voronoi", driver="GPKG")
            _log_part("[partitionnement] Couche 'sous_bassins_voronoi' sauvegardée.", flush=True)
        except Exception as e:
            _log_part(f"[partitionnement] Erreur sauvegarde sous_bassins_voronoi: {e}", flush=True)

        if not gdf_orphelins_regards.empty:
            try:
                gdf_orphelins_regards.to_file(str(gpkg_p), layer="elements_orphelins_regards", driver="GPKG")
                _log_part("[partitionnement] Couche 'elements_orphelins_regards' sauvegardée.", flush=True)
            except Exception as e:
                _log_part(f"[partitionnement] Erreur sauvegarde orphelins: {e}", flush=True)

    # 9. Export du fichier isolé des orphelins (GeoJSON) dans le dossier upload
    orphelins_geojson_path = gpkg_p.parent / "elements_orphelins.geojson"
    gdf_orph_wgs84 = gdf_orphelins_regards.to_crs("EPSG:4326") if not gdf_orphelins_regards.empty else gpd.GeoDataFrame()
    if not gdf_orph_wgs84.empty:
        try:
            gdf_orph_wgs84.to_file(str(orphelins_geojson_path), driver="GeoJSON")
            _log_part(f"[partitionnement] Fichier d'isolation exporté : {orphelins_geojson_path.name}", flush=True)
        except Exception as e:
            _log_part(f"[partitionnement] Erreur export orphelins.geojson: {e}", flush=True)

    # 10. Préparation des structures GeoJSON WGS84 pour l'API et le cache Web
    gdf_bassins_wgs84 = gdf_bassins_79.to_crs("EPSG:4326")
    bassins_geojson = json.loads(gdf_bassins_wgs84.to_json(na="drop"))

    gdf_voronoi_wgs84 = gdf_voronoi.to_crs("EPSG:4326")
    voronoi_geojson = json.loads(gdf_voronoi_wgs84.to_json(na="drop"))

    # Construction des 79 items de resultats pour le cockpit
    results_formatted = []
    total_troncons_assignes = 0

    total_troncons_assignes = _etape_resultats_formatted({
        "bassins_geojson": bassins_geojson,
        "crs_metrique": crs_metrique,
        "exutoires_bassins": exutoires_bassins,
        "pipes_by_exutoire": pipes_by_exutoire,
        "results_formatted": results_formatted,
        "total_troncons_assignes": total_troncons_assignes,
    })

    # Sauvegarde du cache disque pour rapidité web instantanée (< 50ms)
    cache_clusters_path = gpkg_p.with_suffix(".clusters_cache.json")
    try:
        orph_reg_geojson = json.loads(gdf_orph_wgs84.to_json(na="drop")) if not gdf_orph_wgs84.empty else {"type": "FeatureCollection", "features": []}
        clusters_cache_data = {
            "status": "success",
            "exutoires_physiques": nb_exutoires_physiques,
            "exutoires_implicites": nb_exutoires - nb_exutoires_physiques,
            "clusters_crees": len(gdf_bassins_79),
            "surface_totale_ha": total_surface_ha,
            "nb_sous_bassins_voronoi": len(gdf_voronoi),
            "nb_regards_orphelins": len(gdf_orphelins_regards),
            "nb_troncons_orphelins": len(orphelins_pipes_features),
            "nb_conduites_fragments": len(fragments_pipes_features),
            "troncons_connectes": total_troncons_assignes,
            "bassins_geojson": bassins_geojson,
            "orphelins_conduites": {
                "type": "FeatureCollection",
                "features": orphelins_pipes_features
            },
            "fragments_conduites": {
                "type": "FeatureCollection",
                "features": fragments_pipes_features
            },
            "orphelins_regards": orph_reg_geojson,
            "resultats": results_formatted
        }
        with open(cache_clusters_path, "w", encoding="utf-8") as f:
            json.dump(clusters_cache_data, f, ensure_ascii=False)
        _log_part(f"[partitionnement] Cache disque des clusters mis à jour : {cache_clusters_path.name}", flush=True)
    except Exception as e:
        _log_part(f"[partitionnement] Erreur écriture cache clusters: {e}", flush=True)

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
        _log_part(f"[partitionnement] Cache disque subcatchments mis à jour : {cache_subcatchments_path.name}", flush=True)
    except Exception as e:
        _log_part(f"[partitionnement] Erreur écriture cache subcatchments: {e}", flush=True)

    elapsed = round(time.time() - t0, 2)
    _log_part(f"[partitionnement] Traitement complet terminé en {elapsed} secondes.", flush=True)

    return {
        "status": "success",
        "nb_bassins": len(gdf_bassins_79),
        "surface_totale_ha": total_surface_ha,
        "nb_voronoi": len(gdf_voronoi),
        "nb_orphelins": len(gdf_orphelins_regards),
        "elapsed_seconds": elapsed,
        "orphelins_file": str(orphelins_geojson_path)
    }
