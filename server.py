#!/usr/bin/env python3
"""
Serveur Flask pour la visualisation interactive du reseau d'assainissement.

Charge les donnees depuis un GeoPackage, les reprojette en WGS84,
analyse la topologie du reseau et sert les donnees via API JSON.
"""

import json
import logging
import sqlite3
from collections import defaultdict

import geopandas as gpd
from flask import Flask, jsonify
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GPKG_PATH = Path(r"c:\Users\Hakim\Downloads\Assainissement_Ville.gpkg")
HTML_PATH = Path(__file__).parent / "index.html"

SOURCE_CRS = "EPSG:32631"  # UTM Zone 31N
TARGET_CRS = "EPSG:4326"   # WGS84

LAYER_PATTERNS = {
    "regards":   "Regards",
    "rejets":    "Rejets",
    "conduites": "Canalisations",
    "ouvrages":  "Ouvrages_Speciaux",
    "stations":  "Station_de_relevage",
    "step":      "STEP",
}

# Couleurs pour les clusters hydrauliques
CLUSTER_COLORS = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4",
    "#42d4f4", "#f032e6", "#bfef45", "#fabed4", "#469990",
    "#dcbeff", "#9A6324", "#fffac8", "#800000", "#aaffc3",
    "#808000", "#ffd8b1", "#000075", "#a9a9a9", "#ffffff",
]

# ---------------------------------------------------------------------------
# Application Flask
# ---------------------------------------------------------------------------

app = Flask(__name__)
logging.getLogger("werkzeug").setLevel(logging.ERROR)

_cache: dict = {}


# ---------------------------------------------------------------------------
# Chargement des donnees GeoPackage
# ---------------------------------------------------------------------------

def _get_geo_tables(gpkg: Path) -> list[str]:
    """Retourne la liste des tables geospatiales (hors tables systeme)."""
    conn = sqlite3.connect(gpkg)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        conn.close()
    system_prefixes = ("gpkg_", "sqlite_", "rtree_", "log_")
    return [r[0] for r in rows if not r[0].startswith(system_prefixes)]


def _match_layers(tables: list[str]) -> dict[str, str]:
    """Associe chaque cle logique au nom de couche GeoPackage."""
    mapping = {}
    for key, pattern in LAYER_PATTERNS.items():
        for table in tables:
            if pattern in table and key not in mapping:
                mapping[key] = table
                break
    return mapping


def load_layers() -> dict:
    """Charge et met en cache toutes les couches du GeoPackage."""
    if _cache:
        return _cache

    print("[data] Chargement du GeoPackage ...")

    try:
        tables = _get_geo_tables(GPKG_PATH)
        mapping = _match_layers(tables)

        print(f"[data] Tables detectees : {tables}")
        print(f"[data] Mapping couches  : {mapping}")

        for key, layer_name in mapping.items():
            try:
                gdf = gpd.read_file(GPKG_PATH, layer=layer_name)
                if gdf.crs and gdf.crs != TARGET_CRS:
                    gdf = gdf.to_crs(TARGET_CRS)

                geojson = json.loads(gdf.to_json())
                _cache[key] = geojson

                print(f"[data]   {key:12s} -> {len(gdf)} features")
            except Exception as exc:
                print(f"[data]   {key:12s} -> ERREUR : {exc}")
                _cache[key] = {"type": "FeatureCollection", "features": []}

    except Exception as exc:
        print(f"[data] ERREUR chargement GeoPackage : {exc}")

    return _cache


# ---------------------------------------------------------------------------
# Analyse hydraulique
# ---------------------------------------------------------------------------

def _extract_conduit_lines(conduites_geojson: dict) -> list[dict]:
    """
    Extrait les LineString individuelles depuis les MultiLineString
    et ajoute les coordonnees de debut/fin pour le sens d'ecoulement.
    """
    lines = []

    for feat in conduites_geojson.get("features", []):
        geom = feat.get("geometry", {})
        props = feat.get("properties", {})
        geom_type = geom.get("type", "")
        coords = geom.get("coordinates", [])

        if geom_type == "MultiLineString":
            for segment in coords:
                if len(segment) >= 2:
                    lines.append({
                        "type": "Feature",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": segment
                        },
                        "properties": {
                            **props,
                            "_start": list(segment[0]),
                            "_end": list(segment[-1]),
                        }
                    })
        elif geom_type == "LineString":
            if len(coords) >= 2:
                lines.append({
                    "type": "Feature",
                    "geometry": geom,
                    "properties": {
                        **props,
                        "_start": list(coords[0]),
                        "_end": list(coords[-1]),
                    }
                })

    return lines


def _round_coord(coord: list, decimals: int = 6) -> tuple:
    """Arrondit une coordonnee pour le matching topologique."""
    return tuple(round(c, decimals) for c in coord[:2])


def _compute_hydraulic_clusters(conduit_features: list[dict]) -> dict:
    """
    Construit le graphe topologique du reseau a partir des extremites
    des conduites et trouve les composantes connexes (clusters hydrauliques).

    Returns:
        dict avec 'cluster_map' (id_conduit -> cluster_id) et 'cluster_stats'
    """
    # Construire le graphe : chaque noeud = coordonnee arrondie
    # Arete = conduite reliant deux noeuds
    graph = defaultdict(set)
    conduit_nodes = {}  # conduit_idx -> (node_a, node_b)

    for idx, feat in enumerate(conduit_features):
        props = feat["properties"]
        node_a = _round_coord(props["_start"])
        node_b = _round_coord(props["_end"])

        if node_a != node_b:
            graph[node_a].add(node_b)
            graph[node_b].add(node_a)
            conduit_nodes[idx] = (node_a, node_b)

    # BFS pour trouver les composantes connexes
    visited = set()
    cluster_map = {}
    cluster_id = 0
    cluster_stats = {}

    for idx, (node_a, node_b) in conduit_nodes.items():
        if idx in visited:
            continue

        # Nouveau cluster
        queue = [node_a, node_b]
        cluster_nodes = set()
        cluster_conduits = []

        while queue:
            node = queue.pop(0)
            if node in cluster_nodes:
                continue
            cluster_nodes.add(node)

            for neighbor in graph[node]:
                if neighbor not in cluster_nodes:
                    queue.append(neighbor)

        # Marquer toutes les conduites de ce cluster
        for c_idx, (na, nb) in conduit_nodes.items():
            if na in cluster_nodes or nb in cluster_nodes:
                cluster_map[c_idx] = cluster_id
                visited.add(c_idx)
                cluster_conduits.append(c_idx)

        cluster_stats[cluster_id] = len(cluster_conduits)
        cluster_id += 1

    return {
        "cluster_map": cluster_map,
        "cluster_stats": cluster_stats,
        "total_clusters": cluster_id,
    }


def build_network_data() -> dict:
    """
    Construit les donnees enrichies du reseau :
    - Canalisations avec sens d'ecoulement et cluster hydraulique
    - Statistiques des clusters
    """
    layers = load_layers()

    conduites_raw = layers.get("conduites", {"type": "FeatureCollection", "features": []})

    # Extraire les LineString individuelles avec sens d'ecoulement
    conduit_features = _extract_conduit_lines(conduites_raw)

    # Calculer les clusters hydrauliques
    cluster_info = _compute_hydraulic_clusters(conduit_features)

    # Enrichir chaque conduite avec son cluster et sa couleur
    for idx, feat in enumerate(conduit_features):
        cid = cluster_info["cluster_map"].get(idx, 0)
        feat["properties"]["_cluster"] = cid
        feat["properties"]["_color"] = CLUSTER_COLORS[cid % len(CLUSTER_COLORS)]

    conduites_enriched = {
        "type": "FeatureCollection",
        "features": conduit_features,
    }

    empty = {"type": "FeatureCollection", "features": []}

    return {
        "regards": layers.get("regards", empty),
        "rejets": layers.get("rejets", empty),
        "conduites": conduites_enriched,
        "ouvrages": layers.get("ouvrages", empty),
        "stations": layers.get("stations", empty),
        "step": layers.get("step", empty),
        "clusters": {
            "total": cluster_info["total_clusters"],
            "stats": cluster_info["cluster_stats"],
            "colors": CLUSTER_COLORS,
        },
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Sert la page HTML principale."""
    return HTML_PATH.read_text(encoding="utf-8")


@app.route("/get-data")
def get_data():
    """API : retourne toutes les couches enrichies en GeoJSON."""
    data = build_network_data()
    return jsonify(data)


# ---------------------------------------------------------------------------
# Point d'entree
# ---------------------------------------------------------------------------

def main():
    print("[server] Pre-chargement des donnees ...")
    load_layers()

    print("""

    ╔════════════════════════════════════════════════════╗
    ║   SERVEUR RESEAU D'ASSAINISSEMENT DEMARRE         ║
    ╚════════════════════════════════════════════════════╝

    Ouvrez votre navigateur :
       http://localhost:5000

    Appuyez sur Ctrl+C pour arreter.
    """)

    app.run(debug=False, port=5000, threaded=True)


if __name__ == "__main__":
    main()
