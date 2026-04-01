#!/usr/bin/env python3
"""
Serveur Flask pour la visualisation interactive du reseau d'assainissement.

Charge les donnees depuis un GeoPackage, les reprojette en WGS84
et les sert via une API JSON pour l'affichage sur carte Leaflet.
"""

import json
import logging
import sqlite3

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

# ---------------------------------------------------------------------------
# Application Flask
# ---------------------------------------------------------------------------

app = Flask(__name__)

# Desactiver les logs HTTP de Werkzeug
logging.getLogger("werkzeug").setLevel(logging.ERROR)

# Cache des donnees chargees
_cache: dict = {}


# ---------------------------------------------------------------------------
# Chargement des donnees
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
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Sert la page HTML principale."""
    return HTML_PATH.read_text(encoding="utf-8")


@app.route("/get-data")
def get_data():
    """API : retourne toutes les couches en GeoJSON."""
    layers = load_layers()

    empty = {"type": "FeatureCollection", "features": []}
    return jsonify({key: layers.get(key, empty) for key in LAYER_PATTERNS})


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
