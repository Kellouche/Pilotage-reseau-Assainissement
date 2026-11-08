# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Outil d'analyse qualité et de validation des couches GeoPackage
================================================================================
"""

import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import geopandas as gpd
import pandas as pd
import numpy as np


def _clean_id(val: Any) -> str:
    if val is None or pd.isna(val):
        return ""
    txt = str(val).strip()
    if txt.endswith(".0"):
        txt = txt[:-2]
    return txt


def _safe_float(val: Any) -> Optional[float]:
    """Convertit de façon robuste les valeurs numériques sales issues de SIG."""
    if val is None or pd.isna(val):
        return None
    try:
        if isinstance(val, (int, float)):
            return float(val)
        txt = str(val).strip().replace(" ", "").replace(",", ".")
        m = re.search(r"[-+]?\d*\.?\d+", txt)
        if m:
            return float(m.group(0))
        return None
    except Exception:
        return None


def analyser_qualite_gpkg(gpkg_path: Path, project_name: str = "Projet Actif") -> Dict[str, Any]:
    """
    Exécute un audit de qualité géométrique, attributaire et topologique
    directement sur le GeoPackage actif du projet.
    """
    if not gpkg_path.exists():
        raise FileNotFoundError(f"Fichier GeoPackage introuvable : {gpkg_path}")

    layers = gpd.list_layers(str(gpkg_path))["name"].tolist()
    regard_layer = next((l for l in layers if "regard" in l.lower()), None)
    pipe_layer = next((l for l in layers if any(k in l.lower() for k in ["canalisat", "conduit", "pipe", "troncon"]) and "désaffect" not in l.lower() and "desaffect" not in l.lower()), None)
    rejet_layer = next((l for l in layers if any(k in l.lower() for k in ["rejet", "exutoire", "outfall"])), None)

    regards = gpd.read_file(str(gpkg_path), layer=regard_layer) if regard_layer else gpd.GeoDataFrame()
    pipes = gpd.read_file(str(gpkg_path), layer=pipe_layer) if pipe_layer else gpd.GeoDataFrame()
    rejets = gpd.read_file(str(gpkg_path), layer=rejet_layer) if rejet_layer else gpd.GeoDataFrame()

    nb_regards = len(regards)
    nb_pipes = len(pipes)
    nb_rejets = len(rejets)
    total_elements = nb_regards + nb_pipes + nb_rejets

    # Référentiel des identifiants de nœuds valides
    valid_nodes: Dict[str, Any] = {}
    if not regards.empty:
        for idx, r in regards.iterrows():
            nid = _clean_id(r.get("Code") or r.get("CODE") or r.get("id") or r.get("swmm_id")) or str(idx)
            valid_nodes[nid] = r

    if not rejets.empty:
        for idx, rj in rejets.iterrows():
            r_id = _clean_id(rj.get("Code") or rj.get("CODE") or rj.get("id") or rj.get("NOM")) or f"REJ_{idx+1}"
            valid_nodes[r_id] = rj

    # Extraction des coordonnées WGS84 pour affichage cartographique
    wgs_pipes = pipes.to_crs("EPSG:4326") if (not pipes.empty and pipes.crs and pipes.crs != "EPSG:4326") else pipes

    anomalies: Dict[str, List[Dict[str, Any]]] = {
        "conduites_sans_regards": [],
        "troncons_orphelins": [],
        "champs_manquants": [],
        "geometries_invalides": [],
        "pentes_suspectes": [],
        "incoherences_amont_aval": [],
        "capacite_debit": []
    }

    upstream_connections = set()
    downstream_connections = set()

    for idx, c in pipes.iterrows():
        u = _clean_id(c.get("ID_AMONT") or c.get("id_amont") or c.get("amont"))
        d = _clean_id(c.get("ID_AVAL") or c.get("id_aval") or c.get("aval"))
        if u:
            upstream_connections.add(u)
        if d:
            downstream_connections.add(d)

    # 1. Analyse des canalisations
    for idx, c in pipes.iterrows():
        cid = f"C_{idx+1}"
        u = _clean_id(c.get("ID_AMONT") or c.get("id_amont") or c.get("amont"))
        d = _clean_id(c.get("ID_AVAL") or c.get("id_aval") or c.get("aval"))

        # Coordonnées pour centrage carte
        lat, lon = None, None
        if not wgs_pipes.empty and idx < len(wgs_pipes):
            geom = wgs_pipes.geometry.iloc[idx]
            if geom and not geom.is_empty:
                centroid = geom.centroid
                lat, lon = round(centroid.y, 6), round(centroid.x, 6)

        # A. Conduites sans regards
        manque_amont = not u or (u not in valid_nodes)
        manque_aval = not d or (d not in valid_nodes)
        if manque_amont or manque_aval:
            desc = []
            if manque_amont:
                desc.append(f"amont '{u or 'Non renseigné'}' introuvable")
            if manque_aval:
                desc.append(f"aval '{d or 'Non renseigné'}' introuvable")
            anomalies["conduites_sans_regards"].append({
                "id_conduite": cid,
                "type": "conduite_sans_regard",
                "id_amont": u,
                "id_aval": d,
                "severite": "majeure",
                "description": f"Extrémité déconnectée : {', '.join(desc)}",
                "latitude": lat,
                "longitude": lon
            })

        # B. Tronçons orphelins (ni amont ni aval relié à d'autres canalisations)
        if (u and u not in downstream_connections and u not in valid_nodes) and \
           (d and d not in upstream_connections and d not in valid_nodes):
            anomalies["troncons_orphelins"].append({
                "id_conduite": cid,
                "type": "troncon_orphelin",
                "severite": "mineure",
                "description": f"Tronçon complètement isolé du graphe hydraulique",
                "latitude": lat,
                "longitude": lon
            })

        # C. Champs manquants (Diamètre, Longueur, Matériau)
        diam = c.get("DIAMETRE", c.get("diametre", c.get("Diamètre", None)))
        mat = c.get("MATERIAU", c.get("materiau", c.get("Matériau", None)))
        longueur = c.get("Longeur", c.get("longueur", None))

        diam_val = _safe_float(diam)
        long_val = _safe_float(longueur)

        champs_absents = []
        if diam_val is None or diam_val <= 0:
            champs_absents.append("Diamètre")
        if not mat or pd.isna(mat) or str(mat).strip() == "":
            champs_absents.append("Matériau")
        if (long_val is None or long_val <= 0) and (not c.geometry or c.geometry.length <= 0):
            champs_absents.append("Longueur")

        if champs_absents:
            anomalies["champs_manquants"].append({
                "id_conduite": cid,
                "type": "champs_manquants",
                "severite": "majeure",
                "description": f"Attributs indispensables manquants : {', '.join(champs_absents)}",
                "latitude": lat,
                "longitude": lon
            })

        # D. Géométries invalides
        if not c.geometry or c.geometry.is_empty or c.geometry.length < 0.1:
            anomalies["geometries_invalides"].append({
                "id_conduite": cid,
                "type": "geometrie_invalide",
                "severite": "majeure",
                "description": "Longueur nulle ou géométrie géoréférencée corrompue",
                "latitude": lat,
                "longitude": lon
            })

        # E. Pentes suspectes et contre-pentes
        if u in valid_nodes and d in valid_nodes:
            node_u = valid_nodes[u]
            node_d = valid_nodes[d]
            # Rechercher cote radier ou TN
            z_u = None
            z_d = None
            for col in ["PROFRADI", "COTTN", "COORDZ", "Z", "cote_radier"]:
                if z_u is None and col in node_u and pd.notna(node_u[col]):
                    z_u = _safe_float(node_u[col])
                if z_d is None and col in node_d and pd.notna(node_d[col]):
                    z_d = _safe_float(node_d[col])

            if z_u is not None and z_d is not None and c.geometry and c.geometry.length > 0:
                delta_z = z_u - z_d
                pente_pct = (delta_z / c.geometry.length) * 100.0
                if delta_z < -0.05:  # Contre-pente réelle
                    anomalies["pentes_suspectes"].append({
                        "id_conduite": cid,
                        "type": "pente_suspecte",
                        "severite": "critique",
                        "description": f"Contre-pente détectée (pente = {pente_pct:.2f}%) : l'eau doit remonter de {abs(delta_z):.2f} m",
                        "latitude": lat,
                        "longitude": lon
                    })
                    anomalies["incoherences_amont_aval"].append({
                        "id_conduite": cid,
                        "type": "incoherence_amont_aval",
                        "severite": "majeure",
                        "description": f"Inversion de radier entre amont ({z_u:.2f} m) et aval ({z_d:.2f} m)",
                        "latitude": lat,
                        "longitude": lon
                    })
                elif 0 <= pente_pct < 0.1:
                    anomalies["pentes_suspectes"].append({
                        "id_conduite": cid,
                        "type": "pente_suspecte",
                        "severite": "mineure",
                        "description": f"Pente très faible ({pente_pct:.2f}%) inférieure au seuil d'autocurage (0.2%)",
                        "latitude": lat,
                        "longitude": lon
                    })
                elif pente_pct > 15.0:
                    anomalies["pentes_suspectes"].append({
                        "id_conduite": cid,
                        "type": "pente_suspecte",
                        "severite": "mineure",
                        "description": f"Pente excessive ({pente_pct:.2f}%) risquant une vitesse d'érosion",
                        "latitude": lat,
                        "longitude": lon
                    })

    # Calcul des scores
    total_anomalies_brutes = sum(len(v) for v in anomalies.values())
    elements_touches = set()
    for cat, items in anomalies.items():
        for item in items:
            elements_touches.add(item.get("id_conduite", "unknown"))

    nb_touches = len(elements_touches)
    if total_elements > 0:
        score_base = max(0.0, min(100.0, ((total_elements - nb_touches) / total_elements) * 100.0))
    else:
        score_base = 100.0

    score_global = round(score_base, 1)

    commune_col = next((c for c in regards.columns if "commune" in c.lower()), None)
    par_commune = []
    nb_communes = 1
    if commune_col:
        uniques = regards[commune_col].dropna().unique()
        for comm in uniques:
            c_str = str(comm).strip()
            if not c_str or c_str.lower() in ("nan", "none", "null"):
                continue
            count_c = int((regards[commune_col] == comm).sum())
            par_commune.append({
                "commune": c_str,
                "score_qualite": score_global,
                "regards_complets": count_c,
                "total_regards": count_c
            })
        if par_commune:
            nb_communes = len(par_commune)

    if not par_commune:
        par_commune = [
            {
                "commune": project_name,
                "score_qualite": score_global,
                "regards_complets": max(0, nb_regards - len(anomalies["conduites_sans_regards"])),
                "total_regards": nb_regards
            }
        ]

    scores_qualite = {
        "global": {
            "score_qualite": score_global,
            "total_elements": total_elements,
            "total_anomalies": total_anomalies_brutes,
            "total_anomalies_brutes": total_anomalies_brutes,
            "total_elements_uniques_affectes": nb_touches
        },
        "completude": {
            "score_qualite": round(max(0.0, 100.0 - (len(anomalies["champs_manquants"]) / max(1, nb_pipes) * 100.0)), 1),
            "total_anomalies": len(anomalies["champs_manquants"])
        },
        "topologie": {
            "score_qualite": round(max(0.0, 100.0 - ((len(anomalies["conduites_sans_regards"]) + len(anomalies["troncons_orphelins"])) / max(1, nb_pipes) * 100.0)), 1),
            "total_anomalies": len(anomalies["conduites_sans_regards"]) + len(anomalies["troncons_orphelins"])
        },
        "geometrie": {
            "score_qualite": round(max(0.0, 100.0 - (len(anomalies["geometries_invalides"]) / max(1, nb_pipes) * 100.0)), 1),
            "total_anomalies": len(anomalies["geometries_invalides"])
        },
        "hydraulique": {
            "score_qualite": round(max(0.0, 100.0 - (len(anomalies["pentes_suspectes"]) / max(1, nb_pipes) * 100.0)), 1),
            "total_anomalies": len(anomalies["pentes_suspectes"])
        },
        "par_commune": par_commune
    }

    longueur_totale = round(float(pipes.geometry.length.sum()), 1) if not pipes.empty else 0.0

    statistiques_globales = {
        "nb_regards": nb_regards,
        "nb_conduites": nb_pipes,
        "nb_rejets": nb_rejets,
        "nb_communes": nb_communes,
        "longueur_totale_m": longueur_totale,
        "nom_projet": project_name,
        "gpkg_path": str(gpkg_path)
    }

    rapport = {
        "date_analyse": datetime.now().isoformat(),
        "project_name": project_name,
        "statistiques_globales": statistiques_globales,
        "anomalies": anomalies,
        "scores_qualite": scores_qualite
    }

    return rapport
