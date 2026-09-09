"""
Script de mise à jour du module detecteur_clusters.py
Compatibilité universelle NetworkX DiGraph et MultiDiGraph.
"""

import os

CODE_CORRIGE = '''"""
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
    """
    Itérateur universel : compatible avec nx.DiGraph et nx.MultiDiGraph.
    Renvoie toujours un tuple (u, v, key, data).
    """
    if G.is_multigraph():
        for u, v, k, data in G.edges(keys=True, data=True):
            yield u, v, k, data
    else:
        for u, v, data in G.edges(data=True):
            yield u, v, None, data


def identifier_exutoires(
    G: nx.DiGraph,
    priorite_map: Optional[Dict[str, int]] = None
) -> List[Tuple[str, str, int]]:
    if priorite_map is None:
        priorite_map = PRIORITE_EXUTOIRES_DEFAUT

    exutoires = []
    for noeud, data in G.nodes(data=True):
        type_noeud = str(data.get('type', '')).lower()
        out_deg = G.out_degree(noeud)

        matched_type = None
        for cle in priorite_map:
            if cle in type_noeud:
                matched_type = cle
                break

        if matched_type:
            exutoires.append((noeud, matched_type, priorite_map[matched_type]))
        elif out_deg == 0 and G.in_degree(noeud) > 0:
            exutoires.append((noeud, 'sortie_graphe', priorite_map.get('sortie_graphe', 9)))

    exutoires.sort(key=lambda x: (x[2], x[0]))
    return exutoires


def tracer_cluster_depuis_exutoire(
    G: nx.DiGraph,
    exutoire_noeud: str
) -> Dict[str, Any]:
    if exutoire_noeud not in G:
        return {'exutoire': exutoire_noeud, 'noeuds': [], 'edges': [], 'longueur_totale_m': 0.0}

    noeuds_amont: Set[str] = nx.ancestors(G, exutoire_noeud) | {exutoire_noeud}
    edges_cluster = []
    longueur_totale = 0.0

    for u, v, k, data in _iterer_aretes_avec_data(G):
        if u in noeuds_amont and v in noeuds_amont:
            edges_cluster.append((u, v, k, data))
            longueur_totale += float(data.get('length', data.get('longueur', 0.0)))

    return {
        'exutoire': exutoire_noeud,
        'noeuds': list(noeuds_amont),
        'edges': edges_cluster,
        'longueur_totale_m': round(longueur_totale, 2)
    }


def partitionner_bassins_exclusifs(
    G: nx.DiGraph,
    exutoires: Optional[List[Tuple[str, str, int]]] = None
) -> Dict[str, Dict[str, Any]]:
    if exutoires is None:
        exutoires = identifier_exutoires(G)

    if not exutoires:
        return {}

    poids_priorite = {ex[0]: ex[2] for ex in exutoires}
    liste_noeuds_exutoires = set(poids_priorite.keys())
    attribution_noeuds: Dict[str, str] = {}

    for noeud in G.nodes():
        if noeud in liste_noeuds_exutoires:
            attribution_noeuds[noeud] = noeud
            continue

        descendants = nx.descendants(G, noeud)
        exutoires_atteignables = descendants.intersection(liste_noeuds_exutoires)

        if not exutoires_atteignables:
            continue

        if len(exutoires_atteignables) == 1:
            attribution_noeuds[noeud] = next(iter(exutoires_atteignables))
        else:
            meilleur_exutoire = min(
                exutoires_atteignables,
                key=lambda ex: (
                    poids_priorite.get(ex, 99),
                    nx.shortest_path_length(G, noeud, ex)
                )
            )
            attribution_noeuds[noeud] = meilleur_exutoire

    bassins: Dict[str, Dict[str, Any]] = {}
    for ex_id, ex_type, prio in exutoires:
        bassins[ex_id] = {
            'exutoire_id': ex_id,
            'type_exutoire': ex_type,
            'priorite': prio,
            'noeuds': [],
            'edges': [],
            'longueur_totale_m': 0.0,
            'polygon': None
        }

    for noeud, ex_id in attribution_noeuds.items():
        if ex_id in bassins:
            bassins[ex_id]['noeuds'].append(noeud)

    for u, v, k, data in _iterer_aretes_avec_data(G):
        bassin_v = attribution_noeuds.get(v)
        bassin_u = attribution_noeuds.get(u)
        cible_bassin = bassin_v if bassin_v is not None else bassin_u
        if cible_bassin and cible_bassin in bassins:
            bassins[cible_bassin]['edges'].append((u, v, k, data))
            lg = float(data.get('length', data.get('longueur', 0.0)))
            bassins[cible_bassin]['longueur_totale_m'] += lg

    bassins_actifs = {}
    for ex_id, b_data in bassins.items():
        if b_data['noeuds']:
            b_data['longueur_totale_m'] = round(b_data['longueur_totale_m'], 2)
            poly = calculer_bassin_polygon(G, b_data['edges'], b_data['noeuds'])
            b_data['polygon'] = poly
            b_data['surface_ha'] = round(poly.area / 10000.0, 2) if poly else 0.0
            bassins_actifs[ex_id] = b_data

    return bassins_actifs


def calculer_bassin_polygon(
    G: nx.DiGraph,
    edges_cluster: List[Tuple],
    noeuds_cluster: List[str],
    largeur_bande_drainage_m: float = 20.0
) -> Optional[Polygon]:
    geometries_a_unir = []

    for edge in edges_cluster:
        data = edge[3] if len(edge) > 3 and isinstance(edge[3], dict) else (edge[-1] if isinstance(edge[-1], dict) else {})
        geom = data.get('geometry')
        if geom is not None and isinstance(geom, LineString) and not geom.is_empty:
            geometries_a_unir.append(geom.buffer(largeur_bande_drainage_m, cap_style=1, join_style=1))

    points_coords = []
    for noeud in noeuds_cluster:
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

    if len(points_coords) >= 3:
        multi_pt = MultiPoint(points_coords)
        if hasattr(shapely, 'concave_hull'):
            concave = shapely.concave_hull(multi_pt, ratio=0.25)
            return concave.buffer(largeur_bande_drainage_m)
        return unary_union([Point(pt).buffer(largeur_bande_drainage_m) for pt in points_coords])

    return None


def exporter_bassins_geojson(bassins: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    features = []
    for ex_id, b_data in bassins.items():
        poly = b_data.get('polygon')
        if poly is None or poly.is_empty:
            continue
        feature = {
            'type': 'Feature',
            'properties': {
                'id_exutoire': ex_id,
                'type_exutoire': b_data.get('type_exutoire'),
                'nombre_noeuds': len(b_data.get('noeuds', [])),
                'nombre_troncons': len(b_data.get('edges', [])),
                'longueur_reseau_m': b_data.get('longueur_totale_m', 0.0),
                'surface_drainée_ha': b_data.get('surface_ha', 0.0)
            },
            'geometry': mapping(poly)
        }
        features.append(feature)
    return {'type': 'FeatureCollection', 'features': features}
'''

cible = "src/domain/detecteur_clusters.py"
os.makedirs(os.path.dirname(cible), exist_ok=True)
with open(cible, "w", encoding="utf-8") as f:
    f.write(CODE_CORRIGE.strip() + "\n")

print(f"Correctif appliqué avec succès à {cible}.")