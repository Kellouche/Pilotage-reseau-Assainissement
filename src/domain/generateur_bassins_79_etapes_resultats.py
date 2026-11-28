# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Étape de formatage des résultats 79 bassins (extrait verbatim de
         src/domain/generateur_bassins_79.py)
================================================================================
"""

import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import time
import math
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import colorsys

import numpy as np
import networkx as nx
import geopandas as gpd
import pyproj
from shapely.geometry import Point, LineString, Polygon, MultiPolygon, MultiPoint, mapping
from shapely.ops import voronoi_diagram, unary_union, transform
from shapely import STRtree

from src.domain.graphe_reseau import construire_graphe
from src.domain.detecteur_clusters import (
    trouver_exutoires_physiques,
    extraire_adresse_reelle_bassin,
    classifier_type_hydraulique,
)
from src.domain.moteur_swmm import _clean_node_id
from collections import Counter
import re


def _etape_resultats_formatted(ctx):
    """Étape extraite verbatim de partitionner_79_bassins_versants."""
    bassins_geojson = ctx["bassins_geojson"]
    crs_metrique = ctx["crs_metrique"]
    exutoires_bassins = ctx["exutoires_bassins"]
    pipes_by_exutoire = ctx["pipes_by_exutoire"]
    results_formatted = ctx["results_formatted"]
    total_troncons_assignes = ctx["total_troncons_assignes"]

    for feat in bassins_geojson.get("features", []):
        props = feat.get("properties", {})
        b_id = props.get("id_bassin")
        ex_id_str = props.get("exutoire_id")
        b_nom = props.get("nom_exutoire")
        b_type = props.get("type_exutoire")
        b_color = props.get("couleur")
        bassin_pipes = pipes_by_exutoire.get(ex_id_str, [])

        feat["properties"]["type"] = "bassin_urbain"
        feat["properties"]["cluster_id"] = b_id
        feat["properties"]["nom"] = b_nom
        feat["properties"]["bassin_ref"] = f"exutoire:{ex_id_str}" if ex_id_str else None
        feat["properties"]["exutoire_type"] = b_type
        feat["properties"]["exutoire_type_detaille"] = props.get("type_exutoire")
        feat["properties"]["libelle_type"] = props.get("libelle_type")
        feat["properties"]["couleur_type"] = props.get("couleur_type")
        feat["properties"]["type_ouvrage"] = props.get("type_ouvrage")
        feat["properties"]["h_seuil"] = props.get("h_seuil")
        feat["properties"]["milieu_rec"] = props.get("milieu_rec")
        feat["properties"]["couleur"] = b_color
        feat["properties"]["surface_ha"] = float(props.get("surface_ha", 0.0))
        feat["properties"]["nb_regards"] = int(props.get("nb_regards", 0))
        feat["properties"]["nb_regards_orphelins"] = int(props.get("nb_regards_orphelins", 0))
        feat["properties"]["nb_conduites"] = len(bassin_pipes)
        longueur_bassin = round(sum(p['properties'].get('longueur', 0.0) for p in bassin_pipes), 1)
        feat["properties"]["longueur_totale_m"] = longueur_bassin

        cluster_features = [feat]

        # Ajouter l'exutoire ponctuel s'il a des coordonnées valides
        ex_info = exutoires_bassins.get(ex_id_str, {})
        if 'x' in ex_info and 'y' in ex_info:
            try:
                pt_ex = Point(float(ex_info['x']), float(ex_info['y']))
                gdf_ex_pt = gpd.GeoSeries([pt_ex], crs=crs_metrique).to_crs("EPSG:4326")
                ex_geom = gdf_ex_pt.iloc[0]
                cluster_features.append({
                    "type": "Feature",
                    "geometry": mapping(ex_geom),
                    "properties": {
                        "type": "exutoire",
                        "cluster_id": b_id,
                        "nom": b_nom,
                        "exutoire_id": ex_id_str,
                        "bassin_ref": f"exutoire:{ex_id_str}" if ex_id_str else None,
                        "exutoire_type": b_type,
                        "exutoire_type_detaille": props.get("type_exutoire"),
                        "libelle_type": props.get("libelle_type"),
                        "couleur_type": props.get("couleur_type"),
                        "type_ouvrage": props.get("type_ouvrage"),
                        "h_seuil": props.get("h_seuil"),
                        "milieu_rec": props.get("milieu_rec"),
                    }
                })
            except Exception:
                pass

        # Ajouter les conduites de ce bassin
        cluster_features.extend(bassin_pipes)
        total_troncons_assignes += len(bassin_pipes)

        results_formatted.append({
            "cluster": {
                "id": b_id,
                "nom": b_nom,
                "surface_ha": props.get("surface_ha")
            },
            "exutoire": {
                "nom": b_nom,
                "type": b_type
            },
            "stats": {
                "surface_ha": props.get("surface_ha"),
                "nb_regards": props.get("nb_regards"),
                "nb_regards_orphelins": props.get("nb_regards_orphelins"),
                "nb_conduites": len(bassin_pipes),
                "longueur_totale_m": longueur_bassin
            },
            "infrastructures": {
                "regards": props.get("nb_regards"),
                "conduites": len(bassin_pipes),
                "longueur_totale_m": longueur_bassin
            },
            "geojson": {
                "type": "FeatureCollection",
                "features": cluster_features
            },
            "troncons": len(bassin_pipes)
        })
    return total_troncons_assignes
