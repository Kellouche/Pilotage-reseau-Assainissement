# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Nommage des bassins, adresses reelles et polygones urbains estimes (extrait de domain/detecteur_clusters.py)
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
    _est_nom_technique_ou_generique,
    _premier_texte,
    _texte_valide,
)

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
    if exutoire_info and "nom" in exutoire_info and edges:
        voies = []
        for e in edges:
            edata = G.edges[e] if e in G.edges else (G.edges[e[0], e[1], e[2]] if G.is_multigraph() else (G.edges.get((e[0], e[1])) or {}))
            v = edata.get('nom_voie')
            if v and str(v).strip():
                voies.append(str(v).strip())
        if voies and exutoire_info.get("nom"):
            return f"Bassin hydraulique ({exutoire_info['nom']}) — {voies[0]}"
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
