"""
Module de détection, partitionnement et délimitation géométrique
des sous-bassins versants collectés pour les réseaux d'assainissement.
Fichier : src/domain/detecteur_clusters.py
"""

from typing import Dict, List, Set, Tuple, Any, Optional
import networkx as nx
from shapely.geometry import Point, LineString, MultiPoint, Polygon, MultiPolygon, mapping
from shapely.ops import unary_union
import shapely

PRIORITE_EXUTOIRES_DEFAUT = {
    'step': 0,
    'station': 1,
    'station_pompage': 1,
    'station_relevement': 1,
    'ouvrage': 2,
    'deversoir': 2,
    'rejet': 3,
    'exutoire': 3,
    'sortie_graphe': 9
}

def _iterer_aretes_avec_data(G: nx.Graph):
    if G.is_multigraph():
        for u, v, k, data in G.edges(keys=True, data=True):
            yield u, v, k, data
    else:
        for u, v, data in G.edges(data=True):
            yield u, v, None, data

def trouver_exutoires_physiques(
    G: nx.DiGraph,
    priorite_map: Optional[Dict[str, int]] = None
) -> Dict[str, Dict[str, Any]]:
    if priorite_map is None:
        priorite_map = PRIORITE_EXUTOIRES_DEFAUT

    exutoires = {}
    for noeud, data in G.nodes(data=True):
        type_noeud = str(data.get('type', '')).lower()
        out_deg = G.out_degree(noeud)

        matched_type = None
        for cle in priorite_map:
            if cle in type_noeud:
                matched_type = cle
                break

        if matched_type:
            exutoires[noeud] = {"type": matched_type, "priorite": priorite_map[matched_type], "nom": str(noeud), **data}
        elif out_deg == 0 and G.in_degree(noeud) > 0:
            exutoires[noeud] = {"type": "sortie_graphe", "priorite": priorite_map.get('sortie_graphe', 9), "nom": str(noeud), **data}

    return exutoires

def detecter_composantes_orphelines(G: nx.DiGraph) -> List[Tuple[Set[str], Set[Tuple], str]]:
    orphelines = []
    composantes = list(nx.weakly_connected_components(G))
    exutoires = trouver_exutoires_physiques(G)
    
    for comp_noeuds in composantes:
        if not any(n in exutoires for n in comp_noeuds):
            edges = set()
            for u, v, k, _ in _iterer_aretes_avec_data(G):
                if u in comp_noeuds and v in comp_noeuds:
                    edges.add((u, v, k) if G.is_multigraph() else (u, v))
            orphelines.append((comp_noeuds, edges, "sans_exutoire"))
            
    return orphelines

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
            
        longueur_totale += float(data.get('length', data.get('longueur', 0.0)))
        d = float(data.get('diametre_mm', data.get('diametre', 0.0)))
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

def determiner_nom_bassin(edges: Set[Tuple], G: nx.DiGraph, exutoire_info: Dict) -> str:
    return f"Bassin {exutoire_info.get('nom', 'Inconnu')} [{exutoire_info.get('type', 'exutoire')}]"

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
    features = []
    
    if bassin_hull and not bassin_hull.is_empty:
        features.append({
            'type': 'Feature',
            'properties': {
                'type': 'bassin_urbain',
                'cluster_id': cluster_id,
                'nom': nom_bassin,
                'exutoire_type': exutoire_info.get('type') if exutoire_info else 'inconnu'
            },
            'geometry': mapping(bassin_hull)
        })
        
    for edge in edges:
        u, v = edge[0], edge[1]
        data = G.edges[u, v, edge[2]] if G.is_multigraph() else G.edges[u, v]
        geom = data.get('geometry')
        if geom:
            features.append({
                'type': 'Feature',
                'properties': {
                    'type': 'conduite',
                    'u': str(u),
                    'v': str(v),
                    **classification.get(edge, {})
                },
                'geometry': mapping(geom)
            })
            
    return {'type': 'FeatureCollection', 'features': features}

def tracer_cluster_depuis_exutoire(G: nx.DiGraph, exutoire_noeud: str) -> Set[Tuple]:
    if exutoire_noeud not in G:
        return set()

    noeuds_amont = nx.ancestors(G, exutoire_noeud) | {exutoire_noeud}
    edges_cluster = set()

    for u, v, k, data in _iterer_aretes_avec_data(G):
        if u in noeuds_amont and v in noeuds_amont:
            edges_cluster.add((u, v, k) if G.is_multigraph() else (u, v))

    return edges_cluster
