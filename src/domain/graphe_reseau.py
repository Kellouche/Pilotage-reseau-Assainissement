#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : Pilotage Réseau d'Assainissement
Numéro version : 1.0.0
Date de création : 02-04-2026
Date de modification : 02-04-2026
Objectif : Construction du graphe topologique du réseau
d'assainissement à partir des coordonnées des extrémités
de canalisations. Les nœuds sont les points de connexion
(arrondis), les arêtes sont les conduites orientées.
"""

import logging

import geopandas as gpd
import networkx as nx
import pandas as pd

from src.infrastructure.chargeur_geopackage import (
    GPKG_PATH, WGS84, TARGET_CRS
)

logger = logging.getLogger(__name__)

PRECISION = 6  # décimales pour arrondir les coordonnées

LAYER_PATTERNS = {
    "regards":   "Regards",
    "rejets":    "Rejets",
    "conduites": "Canalisations",
    "ouvrages":  "Ouvrages_Speciaux",
    "stations":  "Station_de_relevage",
    "step":      "STEP",
}


def _trouver_nom_couche(cle):
    """Trouve le nom réel de la couche dans le GeoPackage."""
    import sqlite3
    connexion = sqlite3.connect(GPKG_PATH)
    try:
        tables = connexion.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        connexion.close()
    patron = LAYER_PATTERNS.get(cle, "")
    for table in tables:
        if patron in table[0]:
            return table[0]
    return patron


def _arrondir(x, y):
    """Arrondit les coordonnées pour créer un identifiant de nœud."""
    return (round(x, PRECISION), round(y, PRECISION))


def construire_graphe():
    """Construit le graphe orienté du réseau.

    Les nœuds sont les coordonnées arrondies des extrémités
    de conduites. Les arêtes sont les conduites orientées
    amont → aval selon la pente.

    Retourne:
        G: NetworkX DiGraph
    """
    print("[graphe] Chargement des conduites …", flush=True)
    nom_couche = _trouver_nom_couche("conduites")
    conduits = gpd.read_file(GPKG_PATH, layer=nom_couche)

    # Reprojeter en WGS84 pour les coordonnées GeoJSON
    if conduits.crs and conduits.crs != WGS84:
        conduits_wgs84 = conduits.to_crs(WGS84)
    else:
        conduits_wgs84 = conduits

    G = nx.DiGraph()

    nb_vides = 0
    nb_multilines = 0
    nb_fusions = 0

    for idx, ligne in conduits_wgs84.iterrows():
        geom = ligne.geometry
        if geom is None:
            nb_vides += 1
            continue

        segments = []
        if geom.geom_type == "LineString":
            segments = [geom]
        elif geom.geom_type == "MultiLineString":
            segments = list(geom.geoms)
            nb_multilines += 1
        else:
            nb_vides += 1
            continue

        for seg in segments:
            coords = list(seg.coords)
            if len(coords) < 2:
                continue

            noeud_amont = _arrondir(coords[0][0], coords[0][1])
            noeud_aval = _arrondir(coords[-1][0], coords[-1][1])

            if G.has_edge(noeud_amont, noeud_aval):
                nb_fusions += 1

            try:
                longueur = float(ligne.get("LINEAIRE", 0) or 0)
            except (ValueError, TypeError):
                longueur = 0.0

            try:
                diametre = float(ligne.get("DIAMETRE", 0) or 0)
            except (ValueError, TypeError):
                diametre = 0.0

            geom_wkt = None
            try:
                geom_wkt = list(seg.coords)
            except Exception:
                geom_wkt = None

            G.add_edge(
                noeud_amont, noeud_aval,
                conduit_id=f"C_{idx}",
                longueur=longueur,
                diametre=diametre,
                materiau=str(ligne.get("MATERIAU", "")),
                idx_origine=idx,
                geometry_wkt=geom_wkt
            )

    n_noeuds = G.number_of_nodes()
    n_aretes = G.number_of_edges()

    print(f"[graphe] Graphe construit : {n_noeuds} nœuds, "
          f"{n_aretes} arêtes", flush=True)
    print(f"[graphe] MultiLineString : {nb_multilines}, "
          f"vides : {nb_vides}, fusions (doublons topologiques) : {nb_fusions}", flush=True)

    return G


def trouver_exutoires(G):
    """Associe chaque rejet au nœud aval le plus proche.

    Le rejet est le point de chute du réseau. On cherche
    le nœud du graphe (extrémité aval de conduite) le plus
    proche spatiallement.
    Les nœuds du graphe sont en WGS84 (lon, lat).
    On les reprojette en UTM pour calculer les distances
    en mètres.
    """
    nom_rejets = _trouver_nom_couche("rejets")
    rejets = gpd.read_file(GPKG_PATH, layer=nom_rejets)
    if rejets.crs and rejets.crs != TARGET_CRS:
        rejets_utm = rejets.to_crs(TARGET_CRS)
    else:
        rejets_utm = rejets

    noeuds = list(G.nodes())
    if not noeuds:
        print("[graphe] Aucun nœud dans le graphe", flush=True)
        return []

    # Créer un GeoDataFrame des nœuds en WGS84,
    # puis reprojeter en UTM pour les distances
    noeuds_wgs84 = gpd.GeoDataFrame(
        {"noeud": noeuds},
        geometry=gpd.points_from_xy(
            [n[0] for n in noeuds],
            [n[1] for n in noeuds]
        ),
        crs=WGS84
    ).to_crs(TARGET_CRS)

    seuil = 200  # mètres (UTM)
    exutoires = []

    for idx, rejet in rejets_utm.iterrows():
        if rejet.geometry is None:
            continue

        dists = noeuds_wgs84.geometry.distance(rejet.geometry)
        pos_min = dists.idxmin()
        dist_min = dists.loc[pos_min]

        if dist_min < seuil:
            noeud = noeuds_wgs84.loc[pos_min, "noeud"]
            nom = str(rejet.get("NOM", f"Rejet_{idx}"))
            exutoires.append({
                "noeud": noeud,
                "nom": nom,
                "dist": float(dist_min)
            })

    print(f"[graphe] Exutoires trouvés : {len(exutoires)}",
          flush=True)

    return exutoires


def calculer_ordre_topologique(G, edges):
    """Calcule l'ordre topologique des conduites dans un bassin.

    Utilise un tri topologique sur le sous-graphe formé par les edges
    du bassin. Retourne une liste ordonnée de (conduite_id, rang).

    Args:
        G: graphe NetworkX du réseau complet
        edges: liste des edge IDs (conduite_id) du bassin

    Returns:
        list: [(conduite_id, rang), ...] trié par rang croissant
    """
    # Construire le sous-graphe du bassin
    sous_graphe = G.edge_subgraph([
        (u, v) for u, v, d in G.edges(data=True)
        if d.get("conduit_id") in edges
    ]).copy()

    # Vérifier que le sous-graphe est un DAG
    if not nx.is_directed_acyclic_graph(sous_graphe):
        # Le graphe contient des cycles, on utilise un tri partiel
        try:
            ordre = list(nx.topological_sort(sous_graphe))
        except nx.NetworkXError:
            # Fallback : tri par profondeur depuis les exutoires
            ordre = _tri_par_profondeur(sous_graphe)
    else:
        ordre = list(nx.topological_sort(sous_graphe))

    # Construire le mapping edge_id -> rang
    edge_id_to_node = {}
    for u, v, d in sous_graphe.edges(data=True):
        edge_id = d.get("conduit_id")
        if edge_id is not None:
            edge_id_to_node[edge_id] = (u, v)

    resultat = []
    for idx, node in enumerate(ordre):
        # Trouver l'edge sortant de ce nœud
        for u, v, d in sous_graphe.out_edges(node, data=True):
            cid = d.get("conduit_id")
            if cid and cid not in [r[0] for r in resultat]:
                resultat.append((cid, idx))

    # Trier par rang
    resultat.sort(key=lambda x: x[1])

    return resultat


def _tri_par_profondeur(G):
    """Tri de fallback par profondeur depuis les exutoires (nœuds sans sortie)."""
    # Trouver les exutoires (nœuds avec out_degree == 0)
    exutoires = [n for n in G.nodes() if G.out_degree(n) == 0]

    if not exutoires:
        # Pas d'exutoire, tri arbitraire
        return list(G.nodes())

    # BFS inverse depuis chaque exutoire
    visites = set()
    ordre = []

    from collections import deque
    file = deque(exutoires)

    while file:
        noeud = file.popleft()
        if noeud in visites:
            continue
        visites.add(noeud)
        ordre.append(noeud)

        # Ajouter les prédécesseurs
        for pred in G.predecessors(noeud):
            if pred not in visites:
                file.append(pred)

    # Ajouter les nœuds non visités (cycles)
    for noeud in G.nodes():
        if noeud not in visites:
            ordre.append(noeud)

    return ordre
