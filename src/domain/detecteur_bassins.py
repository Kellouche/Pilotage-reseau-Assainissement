# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Partitionnement des bassins hydrauliques, geometries et geojson clusters (extrait de domain/detecteur_clusters.py)
================================================================================
"""

from typing import Dict, List, Set, Tuple, Any, Optional
from collections import Counter
import re
import networkx as nx
from shapely.geometry import Point, LineString, MultiPoint, Polygon, MultiPolygon, mapping
from shapely.ops import unary_union
import shapely

from src.domain.detecteur_exutoires import (
    _iterer_aretes_avec_data,
    trouver_exutoires_physiques,
)
from src.domain.detecteur_nommage import bassin_hydraulique_valide

def partitionner_bassins_hydrauliques(
    G: nx.DiGraph,
    exutoires: Dict[str, Dict[str, Any]]
) -> Tuple[Dict[str, Set[Tuple]], Set[Tuple], Dict[str, str]]:
    
    bassins_par_exutoire = {ex: set() for ex in exutoires.keys()}
    attribution_noeuds = {}
    
    exutoires_tries = sorted(exutoires.items(), key=lambda x: x[1]['priorite'])
    
    for ex_id, _ in exutoires_tries:
        noeuds_amont = nx.ancestors(G, ex_id) | {ex_id}
        for n in noeuds_amont:
            if n not in attribution_noeuds:
                attribution_noeuds[n] = ex_id
                
    troncons_orphelins = set()
    for u, v, k, data in _iterer_aretes_avec_data(G):
        edge_tuple = (u, v, k) if G.is_multigraph() else (u, v)
        bassin_v = attribution_noeuds.get(v)
        bassin_u = attribution_noeuds.get(u)
        
        if bassin_v:
            bassins_par_exutoire[bassin_v].add(edge_tuple)
        elif bassin_u:
             bassins_par_exutoire[bassin_u].add(edge_tuple)
        else:
            troncons_orphelins.add(edge_tuple)

    return bassins_par_exutoire, troncons_orphelins, attribution_noeuds


def identifier_exutoires(G: nx.DiGraph) -> List[Tuple[Any, Dict[str, Any]]]:
    """Retourne les exutoires dans l'ordre hydraulique de priorité."""
    exutoires = trouver_exutoires_physiques(G)
    return sorted(exutoires.items(), key=lambda item: item[1].get('priorite', 99))


def partitionner_bassins_exclusifs(
    G: nx.DiGraph,
    exutoires: Optional[Any] = None,
) -> Dict[str, Dict[str, Any]]:
    """Construit des bassins collectés exclusifs, sans double attribution."""
    if exutoires is None:
        exutoires_map = trouver_exutoires_physiques(G)
    elif isinstance(exutoires, dict):
        exutoires_map = exutoires
    else:
        exutoires_map = dict(exutoires)

    bassins, _, attribution = partitionner_bassins_hydrauliques(G, exutoires_map)
    resultats = {}
    for exutoire, info in exutoires_map.items():
        edges = bassins.get(exutoire, set())
        noeuds = {exutoire}
        for edge in edges:
            noeuds.update(edge[:2])
        valide, motif = bassin_hydraulique_valide(G, exutoire, edges, info)
        resultats[exutoire] = {
            'exutoire': exutoire,
            'nom': info.get('nom', str(exutoire)),
            'type': info.get('type', 'exutoire'),
            'priorite': info.get('priorite', 99),
            'edges': edges,
            'noeuds': noeuds,
            'attribution': {n: exutoire for n, owner in attribution.items() if owner == exutoire},
            'polygon': calculer_bassin_polygon(edges, G),
            'valide': valide,
            'motif_invalidation': motif,
        }
    return resultats

import math

def safe_float(val: Any, default: float = 0.0) -> float:
    try:
        if val is None:
            return default
        f = float(val)
        return default if math.isnan(f) or math.isinf(f) else f
    except (ValueError, TypeError):
        return default

def calculer_statistiques(G: nx.DiGraph, edges: Set[Tuple]) -> Dict[str, float]:
    longueur_totale = 0.0
    diametres = []
    noeuds = set()
    for edge in edges:
        u, v = edge[0], edge[1]
        noeuds.add(u)
        noeuds.add(v)
        if G.is_multigraph():
            data = G.edges[u, v, edge[2]]
        else:
            data = G.edges[u, v]
            
        longueur_totale += safe_float(data.get('length', data.get('longueur', 0.0)))
        d = safe_float(data.get('diametre_mm', data.get('diametre', 0.0)))
        if d > 0: diametres.append(d)
        
    return {
        "nb_conduites": len(edges),
        "nb_noeuds": len(noeuds),
        "longueur_totale_m": round(longueur_totale, 2),
        "diametre_min_m": min(diametres) if diametres else 0.0,
        "diametre_max_m": max(diametres) if diametres else 0.0,
        "diametre_moy_m": round(sum(diametres)/len(diametres), 2) if diametres else 0.0
    }

def compter_infrastructures(edges: Set[Tuple]) -> Dict[str, int]:
    return {"nb_regards": 0, "nb_stations": 0, "nb_ouvrages": 0}


def calculer_bassin_polygon(edges: Set[Tuple], G: nx.DiGraph, largeur_bande_drainage_m: float = 20.0) -> Optional[Polygon]:
    geometries_a_unir = []
    points_coords = []
    
    noeuds = set()
    for edge in edges:
        u, v = edge[0], edge[1]
        noeuds.add(u)
        noeuds.add(v)
        
        data = G.edges[u, v, edge[2]] if G.is_multigraph() else G.edges[u, v]
        geom = data.get('geometry')
        if geom is not None and isinstance(geom, LineString) and not geom.is_empty:
            geometries_a_unir.append(geom.buffer(largeur_bande_drainage_m, cap_style=1, join_style=1))

    for noeud in noeuds:
        node_data = G.nodes[noeud]
        geom = node_data.get('geometry')
        x = node_data.get('x', node_data.get('coord_x'))
        y = node_data.get('y', node_data.get('coord_y'))

        if geom is not None and isinstance(geom, Point):
            points_coords.append((geom.x, geom.y))
            geometries_a_unir.append(geom.buffer(largeur_bande_drainage_m * 0.8))
        elif x is not None and y is not None:
            points_coords.append((float(x), float(y)))
            geometries_a_unir.append(Point(float(x), float(y)).buffer(largeur_bande_drainage_m * 0.8))

    if not geometries_a_unir and not points_coords:
        return None

    if geometries_a_unir:
        union_geom = unary_union(geometries_a_unir)
        polygone_nettoye = union_geom.buffer(3.0).buffer(-3.0)
        if isinstance(polygone_nettoye, MultiPolygon):
            polygone_nettoye = max(polygone_nettoye.geoms, key=lambda p: p.area)
        # Comblement systématique des cavités intérieures des îlots urbains
        if isinstance(polygone_nettoye, Polygon):
            polygone_nettoye = Polygon(polygone_nettoye.exterior)
        elif isinstance(polygone_nettoye, MultiPolygon):
            polygone_nettoye = MultiPolygon([Polygon(p.exterior) for p in polygone_nettoye.geoms if p.area > 50.0])
        return polygone_nettoye

    return None

def construire_geojson_cluster(
    G: nx.DiGraph,
    edges: Set[Tuple],
    classification: Dict,
    bassin_hull: Optional[Polygon] = None,
    cluster_id: Any = None,
    exutoire_node: Any = None,
    exutoire_info: Dict = None,
    nom_bassin: str = ""
) -> Dict[str, Any]:
    import pyproj
    from shapely.ops import transform
    
    crs_source = G.graph.get('crs')
    transformer = None
    if crs_source:
        try:
            # Check if it's already 4326, if not create transformer
            if crs_source.to_epsg() != 4326:
                transformer = pyproj.Transformer.from_crs(crs_source, "EPSG:4326", always_xy=True).transform
        except Exception:
            pass

    features = []
    
    if bassin_hull and not bassin_hull.is_empty:
        geom_export = transform(transformer, bassin_hull) if transformer else bassin_hull
        features.append({
            'type': 'Feature',
            'properties': {
                'type': 'bassin_urbain',
                'cluster_id': cluster_id,
                'nom': nom_bassin,
                'exutoire_id': str(exutoire_node) if exutoire_node is not None else None,
                'bassin_ref': f"exutoire:{exutoire_node}" if exutoire_node is not None else None,
                'exutoire_type': exutoire_info.get('type') if exutoire_info else 'inconnu',
                'exutoire_type_detaille': exutoire_info.get('type_detaille') if exutoire_info else exutoire_info.get('type'),
                'libelle_type': exutoire_info.get('libelle_type') if exutoire_info else None,
                'couleur_type': exutoire_info.get('couleur_type') if exutoire_info else None,
                'type_ouvrage': exutoire_info.get('type_ouvrage') if exutoire_info else None,
                'h_seuil': exutoire_info.get('h_seuil') if exutoire_info else None,
                'milieu_rec': exutoire_info.get('milieu_rec') if exutoire_info else None,
                'surface_source': exutoire_info.get('surface_source', 'non_precisee') if exutoire_info else 'non_precisee',
                'raccordement_statut': exutoire_info.get('raccordement', {}).get('statut') if exutoire_info else None,
                'raccordement_noeud': exutoire_info.get('raccordement', {}).get('noeud_reseau') if exutoire_info else None,
                'est_deporte': bool(exutoire_info.get('est_deporte', False)) if exutoire_info else False,
                'distance_regard_proche_m': exutoire_info.get('distance_regard_proche_m') if exutoire_info else None,
                'regard_proche_id': exutoire_info.get('regard_proche_id') if exutoire_info else None,
            },
            'geometry': mapping(geom_export)
        })

    # Exutoire explicite : un symbole séparé permet de lire immédiatement le
    # point de sortie du bassin et son type sur la carte.
    if exutoire_node in G.nodes:
        noeud_data = G.nodes[exutoire_node]
        noeud_geom = noeud_data.get('geometry')
        if not isinstance(noeud_geom, Point):
            x, y = noeud_data.get('x'), noeud_data.get('y')
            if x is not None and y is not None:
                noeud_geom = Point(float(x), float(y))
        if isinstance(noeud_geom, Point) and not noeud_geom.is_empty:
            geom_export = transform(transformer, noeud_geom) if transformer else noeud_geom
            features.append({
                'type': 'Feature',
                'properties': {
                    'type': 'exutoire',
                    'cluster_id': cluster_id,
                    'nom': nom_bassin or exutoire_info.get('nom', str(exutoire_node)),
                    'exutoire_id': str(exutoire_node) if exutoire_node is not None else None,
                    'bassin_ref': f"exutoire:{exutoire_node}" if exutoire_node is not None else None,
                    'exutoire_type': exutoire_info.get('type', 'inconnu') if exutoire_info else 'inconnu',
                    'exutoire_type_detaille': exutoire_info.get('type_detaille') if exutoire_info else exutoire_info.get('type'),
                    'libelle_type': exutoire_info.get('libelle_type') if exutoire_info else None,
                    'couleur_type': exutoire_info.get('couleur_type') if exutoire_info else None,
                    'type_ouvrage': exutoire_info.get('type_ouvrage') if exutoire_info else None,
                    'h_seuil': exutoire_info.get('h_seuil') if exutoire_info else None,
                    'milieu_rec': exutoire_info.get('milieu_rec') if exutoire_info else None,
                    'sens_ecoulement': 'vers_exutoire',
                    'est_deporte': bool(exutoire_info.get('est_deporte', False)) if exutoire_info else False,
                    'distance_regard_proche_m': exutoire_info.get('distance_regard_proche_m') if exutoire_info else None,
                    'regard_proche_id': exutoire_info.get('regard_proche_id') if exutoire_info else None,
                },
                'geometry': mapping(geom_export)
            })
        
    for edge in edges:
        u, v = edge[0], edge[1]
        data = G.edges[u, v, edge[2]] if G.is_multigraph() else G.edges[u, v]
        geom = data.get('geometry')
        if geom:
            geom_export = transform(transformer, geom) if transformer else geom
            features.append({
                'type': 'Feature',
                'properties': {
                    'type': 'conduite',
                    'cluster_id': cluster_id,
                    'u': str(u),
                    'v': str(v),
                    'longueur': safe_float(data.get('length', data.get('longueur', 0.0))),
                    'diametre': safe_float(data.get('diametre_mm', data.get('diametre', 0.0))),
                    **classification.get(edge, {})
                },
                'geometry': mapping(geom_export)
            })
            
    return {'type': 'FeatureCollection', 'features': features}

def tracer_cluster_depuis_exutoire(G: nx.DiGraph, exutoire_noeud: str) -> Dict[str, Any]:
    if exutoire_noeud not in G:
        return {'edges': set(), 'noeuds': set(), 'longueur_totale_m': 0.0, 'cycles': []}

    noeuds_amont = nx.ancestors(G, exutoire_noeud) | {exutoire_noeud}
    edges_cluster = set()

    for u, v, k, data in _iterer_aretes_avec_data(G):
        if u in noeuds_amont and v in noeuds_amont:
            edges_cluster.add((u, v, k) if G.is_multigraph() else (u, v))

    stats = calculer_statistiques(G, edges_cluster)
    cycles = []
    try:
        cycles = [list(nx.find_cycle(G.subgraph(noeuds_amont)))]
    except nx.NetworkXNoCycle:
        pass
    return {
        'edges': edges_cluster,
        'noeuds': noeuds_amont,
        'longueur_totale_m': stats['longueur_totale_m'],
        'cycles': cycles,
    }
