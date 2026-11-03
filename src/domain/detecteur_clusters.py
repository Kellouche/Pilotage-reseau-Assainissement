"""
Module de détection, partitionnement et délimitation géométrique
des sous-bassins versants collectés pour les réseaux d'assainissement.
Fichier : src/domain/detecteur_clusters.py
"""

from typing import Dict, List, Set, Tuple, Any, Optional
from collections import Counter
import re
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
    'outfall': 3,
    'exutoire': 3,
    'exutoire_implicite': 8,
    'sortie_graphe': 9
}

def classifier_type_hydraulique(
    type_noeud: str,
    type_ouvrage: Optional[str] = None,
    milieu_rec: Optional[str] = None
) -> Tuple[str, str, str]:
    """
    Retourne (code_type, libelle, couleur_hex) pour un nœud hydraulique aval.
    """
    tn = str(type_noeud or '').lower()
    to = str(type_ouvrage or '').lower()
    mr = str(milieu_rec or '').strip()

    if 'déversoir' in to or 'deversoir' in to or 'dvo' in to:
        return ('deversoir_orage', "Déversoir d'orage (DVO)", '#06b6d4')
    elif 'trop plein' in to or 'trop-plein' in to:
        return ('trop_plein', "Trop-plein de réseau", '#a855f7')
    elif 'rétention' in to or 'retention' in to:
        return ('bassin_retention', "Bassin de rétention", '#10b981')
    elif 'régulation' in to or 'regulation' in to:
        return ('ouvrage_regulation', "Ouvrage de régulation", '#6366f1')
    elif 'réception' in to or 'reception' in to:
        return ('ouvrage_reception', "Ouvrage de réception", '#f59e0b')
    elif 'ouvrage' in tn or to:
        return ('ouvrage_special', "Ouvrage spécial", '#ec4899')
    elif 'rejet' in tn or 'outfall' in tn:
        libelle = f"Rejet direct ({mr})" if mr and mr.lower() != 'nan' else "Rejet vers milieu naturel"
        return ('rejet', libelle, '#ef4444')
    elif 'station' in tn:
        return ('station', "Station de pompage / relevage", '#f97316')
    elif 'step' in tn:
        return ('step', "Station d'épuration (STEP)", '#22c55e')
    return ('regard', "Regard de visite", '#64748b')

def _iterer_aretes_avec_data(G: nx.Graph):
    if G.is_multigraph():
        for u, v, k, data in G.edges(keys=True, data=True):
            yield u, v, k, data
    else:
        for u, v, data in G.edges(data=True):
            yield u, v, None, data

def trouver_exutoires_physiques(
    G: nx.DiGraph,
    priorite_map: Optional[Dict[str, int]] = None,
    inclure_exutoires_implicites: bool = False,
) -> Dict[str, Dict[str, Any]]:
    if priorite_map is None:
        priorite_map = PRIORITE_EXUTOIRES_DEFAUT

    exutoires = {}
    exutoires_bruts = []
    
    for noeud, data in G.nodes(data=True):
        type_noeud = str(data.get('type', '')).lower()
        matched_type = None
        for cle in priorite_map:
            if cle in type_noeud and cle not in ['exutoire_implicite', 'sortie_graphe']:
                matched_type = cle
                break

        if matched_type:
            exutoires_bruts.append((noeud, matched_type, data))

    # Trouver les nœuds connectés pour le snapping
    noeuds_connectes = [n for n in G.nodes() if G.in_degree(n) > 0 or G.out_degree(n) > 0]
    
    for noeud, matched_type, data in exutoires_bruts:
        if G.in_degree(noeud) == 0 and G.out_degree(noeud) == 0 and noeuds_connectes:
            x1, y1 = float(data.get('x', 0)), float(data.get('y', 0))
            meilleur_noeud = noeud
            dist_min = float('inf')
            
            for nc in noeuds_connectes:
                nc_data = G.nodes[nc]
                x2, y2 = float(nc_data.get('x', 0)), float(nc_data.get('y', 0))
                dist = ((x2 - x1)**2 + (y2 - y1)**2)**0.5
                if dist < dist_min:
                    dist_min = dist
                    meilleur_noeud = nc
            
            if dist_min <= 75.0:
                to_ouv = data.get('type_ouvrage') or G.nodes[meilleur_noeud].get('type_ouvrage')
                h_seuil = data.get('h_seuil') or G.nodes[meilleur_noeud].get('h_seuil')
                milieu_rec = data.get('milieu_rec') or G.nodes[meilleur_noeud].get('milieu_rec')
                zone_colle = data.get('zone_collecte') or G.nodes[meilleur_noeud].get('zone_collecte')
                typ_det, lib_det, coul_det = classifier_type_hydraulique(matched_type, to_ouv, milieu_rec)

                # Préférer l'adresse la plus descriptive et spécifique
                noms_candidats = [
                    _texte_valide(data.get('nom')),
                    _texte_valide(data.get('nom_voie')),
                    _texte_valide(G.nodes[meilleur_noeud].get('nom_voie')),
                ]
                nom_choisi = max([n for n in noms_candidats if n], key=lambda s: (len(s.split()), len(s)), default=str(noeud))

                exutoires[meilleur_noeud] = {
                    **G.nodes[meilleur_noeud],
                    "type": matched_type,
                    "type_detaille": typ_det,
                    "libelle_type": lib_det,
                    "couleur_type": coul_det,
                    "type_ouvrage": to_ouv,
                    "h_seuil": h_seuil,
                    "milieu_rec": milieu_rec,
                    "zone_collecte": zone_colle,
                    "priorite": priorite_map[matched_type],
                    "nom": nom_choisi
                }
                continue

        to_ouv = data.get('type_ouvrage')
        h_seuil = data.get('h_seuil')
        milieu_rec = data.get('milieu_rec')
        zone_colle = data.get('zone_collecte')
        typ_det, lib_det, coul_det = classifier_type_hydraulique(matched_type, to_ouv, milieu_rec)

        nom_exutoire = _texte_valide(data.get('nom')) or _texte_valide(data.get('nom_voie')) or str(noeud)
        exutoires[noeud] = {
            **data,
            "type": matched_type,
            "type_detaille": typ_det,
            "libelle_type": lib_det,
            "couleur_type": coul_det,
            "type_ouvrage": to_ouv,
            "h_seuil": h_seuil,
            "milieu_rec": milieu_rec,
            "zone_collecte": zone_colle,
            "priorite": priorite_map[matched_type],
            "nom": nom_exutoire
        }

    # 3. Nœuds morts du réseau (sans exutoire officiel) -> exutoires implicites
    if inclure_exutoires_implicites:
        for noeud in G.nodes():
            if G.out_degree(noeud) == 0 and noeud not in exutoires:
                exutoires[noeud] = {
                    **G.nodes[noeud],
                    "type": "exutoire_implicite",
                    "priorite": priorite_map["exutoire_implicite"],
                    "nom": str(noeud)
                }

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

def _texte_valide(value: Any) -> Optional[str]:
    if value is None:
        return None
    texte = str(value).strip()
    return texte if texte and texte.lower() not in {'none', 'nan', 'inconnu'} else None


def _premier_texte(*values: Any) -> Optional[str]:
    for value in values:
        texte = _texte_valide(value)
        if texte:
            return texte
    return None


def _est_nom_technique_ou_generique(val: Any) -> bool:
    if val is None:
        return True
    s = str(val).strip()
    if not s or s.lower() in {'none', 'nan', 'null', '', 'sans designation', 'inconnu', 'bassin', 'exutoire'}:
        return True
    if re.match(r'^\d+(\.0)?$', s):
        return True
    return False


def extraire_adresse_reelle_bassin(
    edges: Set[Tuple],
    G: nx.DiGraph,
    exutoire_node: Any,
    exutoire_info: Optional[Dict[str, Any]] = None
) -> str:
    """
    Extrait l'adresse urbaine réelle et signifiante (quartier, rue, cité, AADL)
    d'un bassin versant à partir de son réseau drainé (nœuds, tronçons et exutoire),
    en éliminant les identifiants techniques bruts (ex: '13', '15', '23', '32.0').
    """
    if exutoire_info is None:
        exutoire_info = {}

    # 1. Collecter les noms de voie des noeuds et troncons du cluster
    voies = []
    if edges:
        for e in edges:
            edata = G.edges[e] if e in G.edges else (G.edges[e[0], e[1], e[2]] if G.is_multigraph() else G.edges[e[0], e[1]])
            v = edata.get('nom_voie')
            if v and not _est_nom_technique_ou_generique(v):
                voies.append(str(v).strip())
            for n in e[:2]:
                if n in G.nodes:
                    nv = G.nodes[n].get('nom_voie')
                    if nv and not _est_nom_technique_ou_generique(nv):
                        voies.append(str(nv).strip())
    
    compteur = Counter(voies)
    top_voie = compteur.most_common(1)[0][0] if compteur else None

    # 2. Adresse sur le noeud exutoire
    ex_node_data = G.nodes.get(exutoire_node, {}) if exutoire_node in G.nodes else {}
    ex_node_voie = ex_node_data.get('nom_voie')
    if _est_nom_technique_ou_generique(ex_node_voie):
        ex_node_voie = None
    else:
        ex_node_voie = str(ex_node_voie).strip()

    # 3. Nom sur l'exutoire info
    ex_nom = exutoire_info.get('nom')
    if _est_nom_technique_ou_generique(ex_nom):
        ex_nom = None
    else:
        ex_nom = str(ex_nom).strip()

    # 4. Zone de collecte
    zc = exutoire_info.get('zone_collecte') or ex_node_data.get('zone_collecte')
    if zc and not _est_nom_technique_ou_generique(zc):
        zc = str(zc).replace('BC_', '').replace('_', ' ').strip()
    else:
        zc = None

    # 5. Déterminer la meilleure adresse : choisir le candidat le plus informatif
    candidats = []
    for val in [ex_nom, ex_node_voie, top_voie, zc]:
        if val and not _est_nom_technique_ou_generique(val):
            candidats.append(str(val).strip())

    if candidats:
        # Priorité au texte le plus complet / descriptif (mots + longueur)
        return max(candidats, key=lambda s: (len(s.split()), len(s)))
    return f"Secteur {exutoire_node}"


def determiner_nom_bassin(edges: Set[Tuple], G: nx.DiGraph, exutoire_info: Dict, exutoire_node: Any = None) -> str:
    """Produit l'adresse urbaine réelle du bassin pour l'utilisateur final."""
    return extraire_adresse_reelle_bassin(edges, G, exutoire_node, exutoire_info)


def bassin_hydraulique_valide(
    G: nx.DiGraph,
    exutoire: Any,
    edges: Set[Tuple],
    exutoire_info: Dict[str, Any],
) -> Tuple[bool, str]:
    """Vérifie les prérequis minimum avant création d'un bassin."""
    if exutoire_info.get('type') == 'exutoire_implicite':
        return False, "L'exutoire doit être un ouvrage physique identifié."
    if exutoire not in G or not edges:
        return False, "Le bassin doit drainer au moins un tronçon vers un exutoire."
    noeuds = {exutoire}
    for edge in edges:
        noeuds.update(edge[:2])
    if len(noeuds) < 2:
        return False, "Un bassin ne peut pas être constitué d'un seul point."
    return True, ''


def proposer_raccordement_exutoire(
    G: nx.DiGraph,
    exutoire_noeud: Any,
    distance_max_m: float = 50.0,
) -> Dict[str, Any]:
    """Propose un nœud réseau voisin sans modifier le graphe."""
    if exutoire_noeud not in G:
        return {'statut': 'introuvable', 'noeud_reseau': None, 'distance_m': None}
    if G.in_degree(exutoire_noeud) > 0:
        return {'statut': 'connecte', 'noeud_reseau': exutoire_noeud, 'distance_m': 0.0}

    source = G.nodes[exutoire_noeud]
    source_geom = source.get('geometry')
    if not isinstance(source_geom, Point):
        x, y = source.get('x'), source.get('y')
        source_geom = Point(float(x), float(y)) if x is not None and y is not None else None
    if source_geom is None:
        return {'statut': 'sans_geometrie', 'noeud_reseau': None, 'distance_m': None}

    candidats = []
    for noeud, data in G.nodes(data=True):
        if noeud == exutoire_noeud or data.get('geometry') is None:
            continue
        if G.in_degree(noeud) == 0 and G.out_degree(noeud) == 0:
            continue
        distance = source_geom.distance(data['geometry'])
        candidats.append((distance, noeud))
    if not candidats:
        return {'statut': 'aucun_candidat', 'noeud_reseau': None, 'distance_m': None}
    distance, noeud = min(candidats)
    return {
        'statut': 'propose' if distance <= distance_max_m else 'hors_tolerance',
        'noeud_reseau': noeud,
        'distance_m': round(float(distance), 2),
        'tolerance_m': distance_max_m,
    }


def calculer_polygone_urbain_estime(
    G: nx.DiGraph,
    edges: Set[Tuple],
    noeuds: Optional[Set[Any]] = None,
    largeur_reseau_m: float = 15.0,
    marge_urbaine_m: float = 50.0,
) -> Optional[Polygon]:
    """Construit une enveloppe urbaine provisoire à partir du réseau amont.

    Cette géométrie est une emprise de travail, pas une délimitation
    hydrologique : aucun MNT ni parcellaire n'est utilisé ici.
    """
    geometries = []
    points = []
    for edge in edges:
        data = G.edges[edge[0], edge[1], edge[2]] if G.is_multigraph() else G.edges[edge[0], edge[1]]
        geometry = data.get('geometry')
        if geometry is not None and not geometry.is_empty:
            geometries.append(geometry.buffer(largeur_reseau_m))
    for noeud in (noeuds or set()):
        data = G.nodes.get(noeud, {})
        geometry = data.get('geometry')
        if isinstance(geometry, Point):
            points.append(geometry)
    if not geometries and not points:
        return None
    union = unary_union(geometries + [point.buffer(marge_urbaine_m) for point in points])
    return union.buffer(5.0).buffer(-5.0)

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
                    'exutoire_type': exutoire_info.get('type', 'inconnu') if exutoire_info else 'inconnu',
                    'exutoire_type_detaille': exutoire_info.get('type_detaille') if exutoire_info else exutoire_info.get('type'),
                    'libelle_type': exutoire_info.get('libelle_type') if exutoire_info else None,
                    'couleur_type': exutoire_info.get('couleur_type') if exutoire_info else None,
                    'type_ouvrage': exutoire_info.get('type_ouvrage') if exutoire_info else None,
                    'h_seuil': exutoire_info.get('h_seuil') if exutoire_info else None,
                    'milieu_rec': exutoire_info.get('milieu_rec') if exutoire_info else None,
                    'sens_ecoulement': 'vers_exutoire',
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
