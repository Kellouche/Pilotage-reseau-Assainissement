#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : Pilotage Réseau d'Assainissement
Numéro version : 1.0.0
Date de création : 02-04-2026
Date de modification : 02-04-2026
Objectif : Chargement et prétraitement des données GeoPackage.
Gère la lecture des couches géospatiales, la reprojection
et le calcul du centre de la zone d'étude.
"""

import json
import sqlite3
from pathlib import Path

import geopandas as gpd
import numpy as np

from src.infrastructure.config import TARGET_CRS
from src.infrastructure.orientation_conduites import orienter_conduites
from src.infrastructure.labels_rues import construire_labels_rues

GPKG_PATH = Path(r"D:\IA Water Data Analysis\Assainissement\Assainissement_Ville.gpkg")
WGS84 = "EPSG:4326"

LAYER_PATTERNS = {
    "regards":   "Regards",
    "rejets":    "Rejets",
    "conduites": "Canalisations",
    "ouvrages":  "Ouvrages_Speciaux",
    "stations":  "Station_de_relevage",
    "step":      "STEP",
}

KEEP_COLS = {
    "regards": ["Code", "NOMVOIE", "COMMUNE", "Profondeur",
                "DIAMETRES", "TYPERES", "PROFRADI", "HFERMSOL",
                "geometry"],
    "rejets": ["NOM", "COMMUNE", "NOMVOIE", "geometry"],
    "conduites": ["fid", "NOM-VOIE", "DIAMETRE", "MATERIAU",
                  "LINEAIRE", "PROF_FE_AM", "PROF_FE_AV",
                  "FONCTIONMT", "ID_AMONT", "ID_AVAL",
                  "FORMESECT", "HAUTEUR", "GDEBASE", "geometry"],
    "ouvrages": ["geometry"],
    "stations": ["geometry"],
    "step": ["NOM", "COMMUNE", "geometry"],
}

_cache: dict = {}


def _get_geo_tables(chemin_gpkg):
    """Retourne la liste des tables géospatiales."""
    connexion = sqlite3.connect(chemin_gpkg)
    try:
        lignes = connexion.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        connexion.close()
    prefixes = ("gpkg_", "sqlite_", "rtree_", "log_")
    return [ligne[0] for ligne in lignes
            if not ligne[0].startswith(prefixes)]


def _match_layers(tables):
    """Associe les tables aux couches connues."""
    correspondance = {}
    for cle, patron in LAYER_PATTERNS.items():
        for table in tables:
            if patron in table and cle not in correspondance:
                correspondance[cle] = table
                break
    return correspondance


def charger_donnees():
    """Charge toutes les couches du GeoPackage."""
    if _cache:
        return _cache

    print("[data]   Lecture des tables …", flush=True)
    tables = _get_geo_tables(GPKG_PATH)
    mapping = _match_layers(tables)

    print(f"[data]   Tables détectées : {len(tables)}",
          flush=True)
    print(f"[data]   Couches identifiées : {len(mapping)}",
          flush=True)

    try:
        regards_gdf = None

        for cle, nom_couche in mapping.items():
            try:
                gdf = gpd.read_file(GPKG_PATH, layer=nom_couche)
                if gdf.crs and gdf.crs != TARGET_CRS:
                    gdf = gdf.to_crs(TARGET_CRS)

                if cle == "regards":
                    regards_gdf = gdf.copy()

                colonnes = KEEP_COLS.get(cle)
                if colonnes:
                    cols = [c for c in colonnes if c in gdf.columns]
                    gdf = gdf[cols]

                gdf_wgs84 = gdf.to_crs(WGS84)
                geojson = json.loads(gdf_wgs84.to_json())
                _cache[cle] = geojson

                print(
                    f"[data]   {cle:12s} → {len(gdf)} features",
                    flush=True
                )
            except Exception as exc:
                print(
                    f"[data]   {cle:12s} → ERREUR : {exc}",
                    flush=True
                )
                _cache[cle] = {
                    "type": "FeatureCollection",
                    "features": []
                }

        if "conduites" in _cache and regards_gdf is not None:
            print("[data]   Orientation hydraulique …",
                  flush=True)
            regards_wgs84 = regards_gdf.to_crs(WGS84)
            orienter_conduites(_cache["conduites"], regards_wgs84)

        if regards_gdf is not None:
            print("[data]   Labels de rues …", flush=True)
            regards_wgs84 = regards_gdf.to_crs(WGS84)
            _cache["rues_labels"] = construire_labels_rues(
                regards_wgs84
            )

        bornes = []
        for geojson in _cache.values():
            fc = geojson.get("features", [])
            if not fc:
                continue
            gdf_tmp = gpd.GeoDataFrame.from_features(
                fc, crs=WGS84
            )
            b = gdf_tmp.total_bounds
            if not any(np.isnan(b)):
                bornes.append(b)

        if bornes:
            arr = np.array(bornes)
            minlon = arr[:, 0].min()
            minlat = arr[:, 1].min()
            maxlon = arr[:, 2].max()
            maxlat = arr[:, 3].max()
            _cache["_center"] = [
                (minlat + maxlat) / 2,
                (minlon + maxlon) / 2
            ]
            print(
                f"[data]   Centre zone : {_cache['_center']}",
                flush=True
            )

        print("[data]   Données chargées avec succès ✓",
              flush=True)

    except Exception as exc:
        print(
            f"[data] ERREUR chargement GeoPackage : {exc}",
            flush=True
        )

    return _cache


def vider_cache():
    """Vide le cache des données chargées."""
    _cache.clear()
