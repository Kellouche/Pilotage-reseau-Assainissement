#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Serveur Flask pour la visualisation interactive du réseau d'assainissement.

Charge les données depuis un GeoPackage, les reprojette en WGS84
et les sert via API JSON pour affichage sur carte Leaflet.
"""

import sys
import io
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

import json
import logging
import sqlite3

import geopandas as gpd
import numpy as np
import pandas as pd
from flask import Flask, jsonify, make_response
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GPKG_PATH = Path(r"c:\Users\Hakim\Downloads\Assainissement_Ville.gpkg")
HTML_PATH = Path(__file__).parent / "index.html"

TARGET_CRS = "EPSG:4326"  # WGS84

LAYER_PATTERNS = {
    "regards":   "Regards",
    "rejets":    "Rejets",
    "conduites": "Canalisations",
    "ouvrages":  "Ouvrages_Speciaux",
    "stations":  "Station_de_relevage",
    "step":      "STEP",
}

# Colonnes utiles à conserver pour l'affichage (réduit le poids du GeoJSON)
KEEP_COLS = {
    "regards": ["Code", "NOMVOIE", "COMMUNE", "Profondeur", "DIAMETRES", "TYPERES",
                "PROFRADI", "HFERMSOL", "geometry"],
    "rejets": ["NOM", "COMMUNE", "NOMVOIE", "geometry"],
    "conduites": ["fid", "NOM-VOIE", "DIAMETRE", "MATERIAU", "LINEAIRE",
                  "PROF_FE_AM", "PROF_FE_AV", "FONCTIONMT", "ID_AMONT", "ID_AVAL",
                  "FORMESECT", "HAUTEUR", "GDEBASE", "geometry"],
    "ouvrages": ["geometry"],
    "stations": ["geometry"],
    "step": ["NOM", "COMMUNE", "geometry"],
}

# ---------------------------------------------------------------------------
# Application Flask
# ---------------------------------------------------------------------------

app = Flask(__name__)
logging.getLogger("werkzeug").setLevel(logging.ERROR)

_cache: dict = {}


# ---------------------------------------------------------------------------
# Chargement des données GeoPackage
# ---------------------------------------------------------------------------

def _get_geo_tables(gpkg):
    """Retourne la liste des tables géospatiales (hors tables système)."""
    conn = sqlite3.connect(gpkg)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        conn.close()
    system_prefixes = ("gpkg_", "sqlite_", "rtree_", "log_")
    return [r[0] for r in rows if not r[0].startswith(system_prefixes)]


def _match_layers(tables):
    mapping = {}
    for key, pattern in LAYER_PATTERNS.items():
        for table in tables:
            if pattern in table and key not in mapping:
                mapping[key] = table
                break
    return mapping


def _safe_float(value):
    """Convertit une valeur en float (gère les virgules décimales)."""
    if value is None:
        return None
    try:
        s = str(value).replace(",", ".").strip()
        if not s or s == "None" or s == "nan":
            return None
        return float(s)
    except (ValueError, TypeError):
        return None


def _orient_conduits_by_hydraulics(conduites_geojson, regards_gdf_wgs84):
    """
    Oriente chaque canalisation dans le sens amont → aval hydraulique.
    Vectorisé avec numpy pour la performance.
    """
    if regards_gdf_wgs84 is None or regards_gdf_wgs84.empty:
        return

    if conduites_geojson is None:
        return

    features = conduites_geojson.get("features")
    if not features:
        return

    # Construire les arrays numpy directement depuis le GeoDataFrame
    geoms = regards_gdf_wgs84.geometry
    valid = ~geoms.is_empty & geoms.notna()
    gdf_valid = regards_gdf_wgs84[valid]

    coords_arr = np.column_stack([gdf_valid.geometry.x.values, gdf_valid.geometry.y.values])

    prof_arr = gdf_valid["PROFRADI"].apply(_safe_float).values
    surf_arr = gdf_valid["HFERMSOL"].apply(_safe_float).values

    cotes_arr = np.full(len(gdf_valid), np.nan)
    has_prof = ~np.array([x is None for x in prof_arr])
    has_surf = ~np.array([x is None for x in surf_arr])

    prof_float = np.where(has_prof, [float(x) if x is not None else np.nan for x in prof_arr], np.nan)
    surf_float = np.where(has_surf, [float(x) if x is not None else np.nan for x in surf_arr], np.nan)

    # prof + surf → cote = surf - prof
    both = has_prof & has_surf
    cotes_arr[both] = surf_float[both] - prof_float[both]

    # prof seul → cote = -prof
    prof_only = has_prof & ~has_surf
    cotes_arr[prof_only] = -prof_float[prof_only]

    # surf seul → cote = surf
    surf_only = has_surf & ~has_prof
    cotes_arr[surf_only] = surf_float[surf_only]

    n_with_cote = int(np.sum(~np.isnan(cotes_arr)))
    print(f"[data]   Index spatial : {len(coords_arr)} regards ({n_with_cote} avec cote)")

    # Vérifier et inverser les canalisations
    inversions = 0
    no_cote = 0

    for feat in features:
        geom = feat.get("geometry", {})
        geom_type = geom.get("type", "")
        raw_coords = geom.get("coordinates", [])
        if not raw_coords:
            continue

        # Gérer LineString et MultiLineString
        if geom_type == "MultiLineString":
            if not raw_coords[0] or len(raw_coords[0]) < 2:
                continue
            start_lon, start_lat = raw_coords[0][0][0], raw_coords[0][0][1]
            end_lon, end_lat = raw_coords[-1][-1][0], raw_coords[-1][-1][1]
        elif geom_type == "LineString":
            if len(raw_coords) < 2:
                continue
            start_lon, start_lat = raw_coords[0][0], raw_coords[0][1]
            end_lon, end_lat = raw_coords[-1][0], raw_coords[-1][1]
        else:
            continue

        # Trouver le regard le plus proche (distance vectorisée)
        dists_s = np.sqrt((coords_arr[:, 0] - start_lon) ** 2 + (coords_arr[:, 1] - start_lat) ** 2)
        idx_s = int(np.argmin(dists_s))
        cote_start = cotes_arr[idx_s] if dists_s[idx_s] < 0.0005 else None

        dists_e = np.sqrt((coords_arr[:, 0] - end_lon) ** 2 + (coords_arr[:, 1] - end_lat) ** 2)
        idx_e = int(np.argmin(dists_e))
        cote_end = cotes_arr[idx_e] if dists_e[idx_e] < 0.0005 else None

        if cote_start is None or np.isnan(cote_start) or cote_end is None or np.isnan(cote_end):
            no_cote += 1
            continue

        if cote_start < cote_end:
            if geom_type == "MultiLineString":
                geom["coordinates"] = [seg[::-1] for seg in raw_coords[::-1]]
            else:
                geom["coordinates"] = raw_coords[::-1]
            inversions += 1

    print(f"[data]   Canalisations inversées (sens hydraulique) : {inversions}/{len(features)}")
    print(f"[data]   Canalisations sans cote (sens inchangé) : {no_cote}/{len(features)}")


def _build_street_labels(regards_gdf):
    """Crée un GeoJSON de points avec les noms de rues, un par rue, au centroïde de ses regards."""
    if regards_gdf is None or regards_gdf.empty:
        return {"type": "FeatureCollection", "features": []}

    # Filtrer les regards avec un nom de rue
    with_street = regards_gdf[regards_gdf["NOMVOIE"].notna() & (regards_gdf["NOMVOIE"] != "")]
    if with_street.empty:
        return {"type": "FeatureCollection", "features": []}

    features = []
    for nom_rue, group in with_street.groupby("NOMVOIE"):
        # Centroïde des regards de cette rue
        centroid = group.geometry.unary_union.centroid
        commune = group["COMMUNE"].dropna()
        commune_val = commune.iloc[0] if not commune.empty else ""

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [centroid.x, centroid.y]
            },
            "properties": {
                "nom": str(nom_rue).strip(),
                "commune": str(commune_val).strip() if commune_val else "",
                "nb_regards": len(group)
            }
        })

    print(f"[data]   Labels rues : {len(features)} noms de rues")
    return {"type": "FeatureCollection", "features": features}


def load_layers():
    if _cache:
        return _cache

    print("[data] Chargement du GeoPackage …")

    try:
        tables = _get_geo_tables(GPKG_PATH)
        mapping = _match_layers(tables)

        print(f"[data] Tables détectées : {tables}")
        print(f"[data] Mapping couches  : {mapping}")

        regards_gdf = None

        for key, layer_name in mapping.items():
            try:
                gdf = gpd.read_file(GPKG_PATH, layer=layer_name)
                if gdf.crs and gdf.crs != TARGET_CRS:
                    gdf = gdf.to_crs(TARGET_CRS)

                # Garder une copie complète des regards pour l'orientation hydraulique
                if key == "regards":
                    regards_gdf = gdf.copy()

                # Filtrer les colonnes pour alléger le GeoJSON
                keep = KEEP_COLS.get(key)
                if keep:
                    cols = [c for c in keep if c in gdf.columns]
                    gdf = gdf[cols]

                geojson = json.loads(gdf.to_json())
                _cache[key] = geojson

                print(f"[data]   {key:12s} → {len(gdf)} features")
            except Exception as exc:
                print(f"[data]   {key:12s} → ERREUR : {exc}")
                _cache[key] = {"type": "FeatureCollection", "features": []}

        # Orienter les canalisations dans le sens hydraulique amont → aval
        if "conduites" in _cache and regards_gdf is not None:
            _orient_conduits_by_hydraulics(_cache["conduites"], regards_gdf)

        # Générer les labels de rues à partir des regards
        if regards_gdf is not None:
            _cache["rues_labels"] = _build_street_labels(regards_gdf)

        # Calculer le centre de la zone d'étude
        all_bounds = []
        for geojson in _cache.values():
            fc = geojson.get("features", [])
            if not fc:
                continue
            gdf_tmp = gpd.GeoDataFrame.from_features(fc, crs=TARGET_CRS)
            b = gdf_tmp.total_bounds  # minx, miny, maxx, maxy
            if not any(np.isnan(b)):
                all_bounds.append(b)

        if all_bounds:
            arr = np.array(all_bounds)
            minx, miny = arr[:, 0].min(), arr[:, 1].min()
            maxx, maxy = arr[:, 2].max(), arr[:, 3].max()
            _cache["_center"] = [(miny + maxy) / 2, (minx + maxx) / 2]
            print(f"[data]   Centre zone : {_cache['_center']}")

    except Exception as exc:
        print(f"[data] ERREUR chargement GeoPackage : {exc}")

    return _cache


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    resp = make_response(HTML_PATH.read_text(encoding="utf-8"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


@app.route("/get-data")
def get_data():
    from flask import request
    if request.args.get("reload"):
        _cache.clear()
    layers = load_layers()
    empty = {"type": "FeatureCollection", "features": []}
    resp = jsonify({
        "regards": layers.get("regards", empty),
        "rejets": layers.get("rejets", empty),
        "conduites": layers.get("conduites", empty),
        "ouvrages": layers.get("ouvrages", empty),
        "stations": layers.get("stations", empty),
        "step": layers.get("step", empty),
        "center": layers.get("_center"),
        "rues_labels": layers.get("rues_labels", empty),
    })
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main():
    print("[data] Pré-chargement …")
    load_layers()

    print("""

    ╔════════════════════════════════════════════════════╗
    ║   SERVEUR RÉSEAU D'ASSAINISSEMENT DÉMARRÉ         ║
    ╚════════════════════════════════════════════════════╝

    Ouvrez votre navigateur :
       http://localhost:5000

    Appuyez sur Ctrl+C pour arrêter.
    """)

    app.run(debug=False, port=5000, threaded=True)


if __name__ == "__main__":
    main()
