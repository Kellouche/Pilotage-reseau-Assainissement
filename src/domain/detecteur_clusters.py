#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : Pilotage Réseau d'Assainissement
Numéro version : 1.0.0
Date de création : 02-04-2026
Date de modification : 02-04-2026
Objectif : Détection des clusters hydrauliques par parcours
BFS inverse depuis les exutoires du réseau.
Les nœuds du graphe sont des coordonnées (x, y).

Améliorations hydrauliques :
- Classifie les tronçons par type (connecté/exutoire vs orphelin)
- Identifie les composantes sans exutoire physique (manque de données)
- Différenciation visuelle par couleur
"""

import logging
import geopandas as gpd
import networkx as nx

from src.infrastructure.chargeur_geopackage import (
    GPKG_PATH, WGS84, TARGET_CRS
)
from src.domain.graphe_reseau import construire_graphe

logger = logging.getLogger(__name__)

def construire_graphe_depuis_geopackage():
    """Proxy pour construire_graphe() afin de maintenir la compatibilité avec server.py."""
    return construire_graphe()

# Cache pour les couches GeoPackage afin d'éviter des lectures redondantes (O(N^2) -> O(N))
_LAYER_CACHE = {}

def _get_cached_layer(cle):
    """Récupère une couche du GeoPackage avec mise en cache."""
    global _LAYER_CACHE
    if cle not in _LAYER_CACHE:
        nom = _trouver_nom_couche(cle)
        if not nom:
            return gpd.GeoDataFrame(geometry=[])
            
        try:
            gdf = gpd.read_file(GPKG_PATH, layer=nom)
            if gdf.crs and gdf.crs != WGS84:
                gdf = gdf.to_crs(WGS84)
            elif not gdf.crs:
                gdf.set_crs(WGS84, inplace=True)
            _LAYER_CACHE[cle] = gdf
        except Exception as e:
            logger.error(f"[data] Erreur chargement {cle}: {e}")
            _LAYER_CACHE[cle] = gpd.GeoDataFrame(geometry=[])
            
    return _LAYER_CACHE[cle]

def vider_cache_couches():
    """Vide le cache des couches GeoPackage."""
    global _LAYER_CACHE
    _LAYER_CACHE.clear()


def trouver_exutoires_physiques(G):
    """Trouve les exutoires physiques (rejets, stations, ouvrages, STEP) dans le graphe.
    
    Associe chaque nœud du graphe aux objets physiques les plus proches
    et retourne uniquement les exutoires réels (où l'eau s'évacue).
    
    Returns:
        dict: {noeud: {'type': 'rejet'|'station'|'ouvrage'|'step', 'nom': str, 'distance': float}}
    """
    noeuds = list(G.nodes())
    if not noeuds:
        return {}
    
    # Créer GeoDataFrame des nœuds
    noeuds_gdf = gpd.GeoDataFrame(
        {"noeud": noeuds},
        geometry=gpd.points_from_xy([n[0] for n in noeuds], [n[1] for n in noeuds]),
        crs=WGS84
    ).to_crs(TARGET_CRS)
    
    exutoires = {}
    seuil = 200  # mètres
    
    # 1. Rejets (exutoires principaux)
    try:
        rejets = _get_cached_layer("rejets")
        if not rejets.empty:
            rejets_target = rejets.to_crs(TARGET_CRS) if rejets.crs != TARGET_CRS else rejets
            for idx, rejet in rejets_target.iterrows():
                if rejet.geometry is None: continue
                dists = noeuds_gdf.geometry.distance(rejet.geometry)
                pos_min = dists.idxmin()
                dist_min = dists.loc[pos_min]
                if dist_min < seuil:
                    noeud = noeuds[pos_min]
                    exutoires[noeud] = {
                        "type": "rejet",
                        "nom": str(rejet.get("nom", f"Rejet_{idx}")),
                        "distance": float(dist_min)
                    }
    except Exception as e:
        logger.warning(f"Erreur traitement rejets: {e}")
    
    # 2. Stations de relevage
    try:
        stations = _get_cached_layer("stations")
        if not stations.empty:
            stations_target = stations.to_crs(TARGET_CRS) if stations.crs != TARGET_CRS else stations
            for idx, station in stations_target.iterrows():
                if station.geometry is None: continue
                dists = noeuds_gdf.geometry.distance(station.geometry)
                pos_min = dists.idxmin()
                dist_min = dists.loc[pos_min]
                if dist_min < seuil:
                    noeud = noeuds[pos_min]
                    if noeud not in exutoires or dist_min < exutoires[noeud]["distance"]:
                        exutoires[noeud] = {
                            "type": "station",
                            "nom": str(station.get("type", f"Station_{idx}")),
                            "distance": float(dist_min)
                        }
    except Exception as e:
        logger.warning(f"Erreur traitement stations: {e}")
    
    # 3. Ouvrages spéciaux
    try:
        ouvrages = _get_cached_layer("ouvrages")
        if not ouvrages.empty:
            ouvrages_target = ouvrages.to_crs(TARGET_CRS) if ouvrages.crs != TARGET_CRS else ouvrages
            for idx, ouvrage in ouvrages_target.iterrows():
                if ouvrage.geometry is None: continue
                dists = noeuds_gdf.geometry.distance(ouvrage.geometry)
                pos_min = dists.idxmin()
                dist_min = dists.loc[pos_min]
                if dist_min < seuil:
                    noeud = noeuds[pos_min]
                    if noeud not in exutoires or dist_min < exutoires[noeud]["distance"]:
                        exutoires[noeud] = {
                            "type": "ouvrage",
                            "nom": str(ouvrage.get("nom", f"Ouvrage_{idx}")),
                            "distance": float(dist_min)
                        }
    except Exception as e:
        logger.warning(f"Erreur traitement ouvrages: {e}")
    
    # 4. STEP (Stations d'Épuration)
    try:
        step_gdf = _get_cached_layer("step")
        if not step_gdf.empty:
            step_target = step_gdf.to_crs(TARGET_CRS) if step_gdf.crs != TARGET_CRS else step_gdf
            for idx, step in step_target.iterrows():
                if step.geometry is None: continue
                dists = noeuds_gdf.geometry.distance(step.geometry)
                pos_min = dists.idxmin()
                dist_min = dists.loc[pos_min]
                if dist_min < seuil:
                    noeud = noeuds[pos_min]
                    if noeud not in exutoires or dist_min < exutoires[noeud]["distance"]:
                        exutoires[noeud] = {
                            "type": "step",
                            "nom": str(step.get("NOM", f"STEP_{idx}")),
                            "distance": float(dist_min)
                        }
    except Exception as e:
        logger.warning(f"Erreur traitement STEP: {e}")
    
    logger.info(f"[hydraulique] {len(exutoires)} exutoires physiques identifiés")
    return exutoires


def detecter_composantes_orphelines(G):
    """Détecte les composantes connexes sans exutoire physique.
    
    Returns:
        list: [(set(noeuds), set(edges), type_issue)]
    """
    composantes = list(nx.weakly_connected_components(G))
    orphelines = []
    
    for comp in composantes:
        if len(comp) < 2:
            continue
        
        edges_comp = set()
        for u in comp:
            for v in G.successors(u):
                if v in comp:
                    edges_comp.add((u, v))
        
        # Nœuds sans successeurs = potentiels exutoires
        noeuds_sortie = [n for n in comp if G.out_degree(n) == 0]
        
        if not noeuds_sortie:
            type_issue = "cycle_sans_sortie"
        else:
            type_issue = "sortie_non_identifiee"
        
        orphelines.append((comp, edges_comp, type_issue))
    
    return orphelines


def partitionner_bassins_exclusifs(G, exutoires):
    """Partitionne le réseau en bassins exclusifs (sans chevauchement).

    Algorithme BFS multi-sources inversé :
    - On part simultanément de TOUS les exutoires
    - On remonte le réseau (graphe inversé) en BFS par vagues
    - Chaque nœud est attribué à l'exutoire qui l'atteint le PREMIER
      (= l'exutoire le plus proche en aval, en nombre de sauts)
    - Chaque arête (u→v) est attribuée au bassin du nœud aval v

    Résultat : bassins disjoints, chaque conduite appartient à UN SEUL bassin.

    Args:
        G: DiGraph NetworkX (amont → aval)
        exutoires: dict {noeud: {'type': str, 'nom': str, ...}}

    Returns:
        dict {noeud_exutoire: set of (amont, aval) edges}
    """
    from collections import deque

    # Priorité d'attribution en cas d'égalité de distance
    # (exutoire de plus haute priorité gagne)
    PRIORITE = {'step': 0, 'station': 1, 'ouvrage': 2, 'rejet': 3, 'sortie_graphe': 9}

    # Trier les exutoires par priorité pour initialiser la file dans le bon ordre
    exutoires_tries = sorted(
        [(n, info) for n, info in exutoires.items() if n in G],
        key=lambda x: PRIORITE.get(x[1].get('type', ''), 9)
    )

    bassins = {n: set() for n, _ in exutoires_tries}
    attribution = {}   # nœud → exutoire propriétaire
    file = deque()

    # Chaque exutoire se réclame lui-même en premier
    for noeud, _ in exutoires_tries:
        attribution[noeud] = noeud
        file.append(noeud)

    # BFS multi-sources : remontée simultanée depuis tous les exutoires
    while file:
        noeud_courant = file.popleft()
        exutoire_courant = attribution[noeud_courant]

        for predecesseur in G.predecessors(noeud_courant):
            if predecesseur not in attribution:
                attribution[predecesseur] = exutoire_courant
                file.append(predecesseur)
            # Si déjà attribué → appartient déjà au bassin le plus proche, on ne touche pas

    # Assigner chaque arête au bassin de son nœud AVAL (v)
    nb_orphelines = 0
    for u, v in G.edges():
        exutoire_v = attribution.get(v)
        if exutoire_v and exutoire_v in bassins:
            bassins[exutoire_v].add((u, v))
        else:
            nb_orphelines += 1

    total = sum(len(e) for e in bassins.values())
    logger.info(
        f"[partition] {len(bassins)} bassins exclusifs | "
        f"{total} conduites attribuées | {nb_orphelines} conduites orphelines"
    )
    return bassins


def tracer_cluster_depuis_exutoire(G, exutoire_noeud, max_profondeur=2000):
    """Compatibilité : trace le bassin cumulatif d'un seul exutoire (nx.ancestors).

    NOTE : Pour des bassins non-chevauchants, utiliser partitionner_bassins_exclusifs().
    Cette fonction conserve le comportement original (bassin cumulatif incluant
    les sous-bassins intermédiaires) et est gardée pour les appels API individuels.
    """
    if exutoire_noeud not in G:
        logger.warning(f"[cluster] Exutoire {exutoire_noeud} absent du graphe")
        return set()

    noeuds_amont = nx.ancestors(G, exutoire_noeud)
    noeuds_amont.add(exutoire_noeud)
    G_bassin = G.subgraph(noeuds_amont)
    return set(G_bassin.edges())


def calculer_bassin_polygon(edges_cluster):
    """Calcule le polygone (convex hull buffered) représentant le bassin urbain.
    
    Args:
        edges_cluster: set des arêtes (amont, aval)
        
    Returns:
        shapely.geometry.Polygon: Le polygone du bassin ou None
    """
    from shapely.geometry import MultiPoint, Point
    
    noeuds = set()
    for amont, aval in edges_cluster:
        noeuds.add(amont)
        noeuds.add(aval)
    
    if len(noeuds) < 2:
        return None
        
    points = [Point(n) for n in noeuds]
    hull = MultiPoint(points).convex_hull
    
    # Appliquer un buffer pour donner du volume au bassin
    if hull.geom_type == 'Point':
        return hull.buffer(0.003)
    elif hull.geom_type == 'LineString':
        return hull.buffer(0.002)
    else:
        return hull.buffer(0.001)


def construire_geojson_cluster(G, edges_cluster, classification=None, bassin_hull=None, cluster_id=None):
    """Convertit les arêtes du cluster en GeoJSON avec couleur par type hydraulique.
    
    Args:
        G: graphe NetworkX
        edges_cluster: set des arêtes du cluster
        classification: dict optionnel {(amont,aval): {'type': str, 'couleur': str}}
        bassin_hull: shapely.geometry.Polygon optionnel représentant le bassin
        cluster_id: identifiant unique du cluster
    
    Returns:
        dict GeoJSON FeatureCollection
    """
    features = []
    
    # Ajouter le polygone du bassin en premier (pour qu'il soit en dessous des conduites)
    if bassin_hull and not bassin_hull.is_empty:
        import json
        from shapely.geometry import mapping
        features.append({
            "type": "Feature",
            "geometry": mapping(bassin_hull),
            "properties": {
                "type": "bassin_urbain",
                "cluster_id": cluster_id,
                "couleur": "#2ecc71",
                "nom": f"Bassin Urban {cluster_id}" if cluster_id else "Bassin Urbain",
                "opacite": 0.3
            }
        })
    
    for amont, aval in edges_cluster:
        attrs = G[amont][aval]
        
        # Classification par défaut
        if classification and (amont, aval) in classification:
            info = classification[(amont, aval)]
            couleur = info.get('couleur', '#4a90e2')
            type_troncon = info.get('type', 'inconnu')
        else:
            couleur = '#4a90e2'  # Bleu par défaut
            type_troncon = 'connecte'
        
        # Valeurs sûres (pas de NaN)
        longueur = attrs.get("longueur", 0) or 0.0
        diametre = attrs.get("diametre", 0) or 0.0
        try:
            longueur = float(longueur) if not (isinstance(longueur, float) and (longueur != longueur)) else 0.0
        except:
            longueur = 0.0
        try:
            diametre = float(diametre) if not (isinstance(diametre, float) and (diametre != diametre)) else 0.0
        except:
            diametre = 0.0
        
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[amont[0], amont[1]], [aval[0], aval[1]]]
            },
            "properties": {
                "conduit_id": attrs.get("conduit_id", ""),
                "longueur": longueur,
                "diametre": diametre,
                "materiau": str(attrs.get("materiau", "")),
                "type_hydraulique": type_troncon,
                "couleur": couleur
            }
        })
    
    return {
        "type": "FeatureCollection",
        "features": features
    }


def calculer_statistiques(G, edges_cluster):
    """Calcule les statistiques du cluster."""
    longueur_totale = 0.0
    diametres = []
    
    for amont, aval in edges_cluster:
        attrs = G[amont][aval]
        try:
            l = float(attrs.get("longueur", 0) or 0)
            if l == l:  # filtre NaN
                longueur_totale += l
        except:
            pass
        try:
            d = float(attrs.get("diametre", 0) or 0)
            if d == d:  # filtre NaN
                diametres.append(d)
        except:
            pass
    
    noeuds = set()
    for amont, aval in edges_cluster:
        noeuds.add(amont)
        noeuds.add(aval)
    
    return {
        "nb_conduites": len(edges_cluster),
        "nb_noeuds": len(noeuds),
        "longueur_totale_m": round(longueur_totale, 1),
        "diametre_min_m": round(min(diametres), 3) if diametres else 0.0,
        "diametre_max_m": round(max(diametres), 3) if diametres else 0.0,
        "diametre_moy_m": round(sum(diametres) / len(diametres), 3) if diametres else 0.0
    }


def compter_infrastructures(edges_cluster, hull=None):
    """Compte les regards, stations, STEP et ouvrages dans un cluster.
    
    Args:
        edges_cluster: set des arêtes
        hull: polygone shapely optionnel (si déjà calculé)
    """
    if hull is None:
        from shapely.geometry import Point, MultiPoint
        
        noeuds = set()
        for amont, aval in edges_cluster:
            noeuds.add(amont)
            noeuds.add(aval)
        
        if len(noeuds) < 3:
            return {"nb_regards": 0, "nb_stations": 0, "nb_step": 0, "nb_ouvrages": 0}
        
        points = [Point(n) for n in noeuds]
        hull = MultiPoint(points).convex_hull
        
        if hull.geom_type in ('LineString', 'Point'):
            hull = hull.buffer(0.003)
        else:
            hull = hull.buffer(0.001)
    
    import geopandas as gpd
    nb_regards = nb_stations = nb_step = nb_ouvrages = 0
    
    try:
        regards = _get_cached_layer("regards")
        if not regards.empty:
            nb_regards = int(regards.geometry.within(hull).sum())
    except Exception: pass
    
    try:
        stations = _get_cached_layer("stations")
        if not stations.empty:
            nb_stations = int(stations.geometry.within(hull).sum())
    except Exception: pass
    
    try:
        step = _get_cached_layer("step")
        if not step.empty:
            nb_step = int(step.geometry.within(hull).sum())
    except Exception: pass
    
    try:
        ouvrages = _get_cached_layer("ouvrages")
        if not ouvrages.empty:
            nb_ouvrages = int(ouvrages.geometry.within(hull).sum())
    except Exception: pass
    
    return {
        "nb_regards": nb_regards,
        "nb_stations": nb_stations,
        "nb_step": nb_step,
        "nb_ouvrages": nb_ouvrages
    }


def _trouver_nom_couche(cle):
    """Trouve le nom réel de la couche dans le GeoPackage."""
    patron_map = {
        "regards": "Regards", 
        "rejets": "Rejets", 
        "conduites": "Canalisations",
        "ouvrages": "Ouvrages_Speciaux", 
        "stations": "Station_de_relevage", 
        "step": "STEP"
    }
    patron = patron_map.get(cle, "")
    
    import sqlite3
    if not GPKG_PATH.exists():
        return patron
        
    try:
        connexion = sqlite3.connect(GPKG_PATH)
        try:
            tables = connexion.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            for table in tables:
                if patron.lower() in table[0].lower():
                    return table[0]
        finally:
            connexion.close()
    except Exception:
        pass
        
    return patron