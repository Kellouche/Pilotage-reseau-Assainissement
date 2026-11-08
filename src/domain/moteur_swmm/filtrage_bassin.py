# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Extraction et filtrage topologique du sous-réseau amont d'un bassin versant
================================================================================
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Set, Union
import pandas as pd
import geopandas as gpd

from src.domain.moteur_swmm.constants import _clean_node_id, _EXUTOIRES_MAP_CACHE

logger = logging.getLogger("swmm_platform.moteur_swmm.filtrage_bassin")


def extraire_sous_reseau_bassin(
    gpkg_path: Path,
    cluster_id: Optional[Union[int, str]],
    regards: gpd.GeoDataFrame,
    canalisations: gpd.GeoDataFrame,
    rejets: gpd.GeoDataFrame,
    G_topo: Optional[Any],
    exutoires_map: Optional[Dict[Any, Any]],
    valider_raccordement_deporte: bool,
    pente_moyenne_pct: Optional[float]
) -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, Optional[str], Optional[str], Optional[str], Set[str], Dict[Any, Any]]:
    """
    Filtre le réseau pour n'extraire que les éléments drainant vers le cluster/bassin spécifié.
    Retourne (regards, canalisations, outfall_code, target_ex_id, bassin_nom, clean_target_nodes, exutoires_map).
    """
    bassin_nom = None
    outfall_code = None
    target_ex_id = None
    clean_target_nodes: Set[str] = set()

    if exutoires_map is None:
        exutoires_map = {}

    if cluster_id is None:
        return regards, canalisations, outfall_code, target_ex_id, bassin_nom, clean_target_nodes, exutoires_map

    if G_topo is None:
        try:
            from api.routes.clusters import _get_graph
            G_topo = _get_graph(str(gpkg_path))
        except Exception:
            from src.domain.graphe_reseau import construire_graphe
            G_topo = construire_graphe(str(gpkg_path))

    if not exutoires_map:
        cache_key = str(gpkg_path)
        if cache_key in _EXUTOIRES_MAP_CACHE:
            exutoires_map = _EXUTOIRES_MAP_CACHE[cache_key]
        else:
            from src.domain.detecteur_clusters import trouver_exutoires_physiques
            exutoires_map = trouver_exutoires_physiques(G_topo)
            _EXUTOIRES_MAP_CACHE[cache_key] = exutoires_map

    cid_str = str(cluster_id).strip()
    try:
        cid_int = int(cid_str)
    except ValueError:
        cid_int = None

    cache_file = Path(gpkg_path).with_suffix(".clusters_cache.json")
    if not target_ex_id and cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as fc:
                cdata = json.load(fc)
            feats = cdata.get("bassins_geojson", {}).get("features", [])
            matched_fp = None
            for f in feats:
                fp = f.get("properties", {})
                fnom = str(fp.get("nom", "")).strip()
                fcid = fp.get("cluster_id")
                if fnom.lower() == cid_str.lower() or (cid_int is not None and fcid == cid_int):
                    matched_fp = fp
                    break
                if fnom.lower().startswith(f"{cid_str.lower()}_"):
                    matched_fp = fp
                    break

            if matched_fp:
                bassin_nom = matched_fp.get("nom")
                cand_ids = [
                    matched_fp.get("exutoire_id"),
                    matched_fp.get("regard_proche_id"),
                    matched_fp.get("nom_exutoire"),
                    matched_fp.get("nom")
                ]
                for cand in cand_ids:
                    if not cand:
                        continue
                    cand_str = str(cand).strip()
                    if cand_str in exutoires_map or (G_topo and G_topo.has_node(cand_str)):
                        target_ex_id = cand_str
                        break
                    if cand_str.endswith(".0") and G_topo and G_topo.has_node(cand_str[:-2]):
                        target_ex_id = cand_str[:-2]
                        break
                    if G_topo and G_topo.has_node(f"{cand_str}.0"):
                        target_ex_id = f"{cand_str}.0"
                        break

                if not target_ex_id and bassin_nom:
                    for ex_k, ex_v in exutoires_map.items():
                        if str(ex_v.get("nom", "")).strip().lower() == bassin_nom.lower():
                            target_ex_id = str(ex_k)
                            break
        except Exception as e_cjson:
            logger.warning(f"Lecture clusters_cache: {e_cjson}")

    try:
        import sqlite3
        con_meta = sqlite3.connect(str(gpkg_path))
        cur_meta = con_meta.cursor()
        has_b79 = cur_meta.execute("SELECT count(*) FROM gpkg_contents WHERE table_name = 'bassins_versants_79'").fetchone()[0] > 0
        if has_b79:
            if cid_int is not None:
                row_b79 = cur_meta.execute("SELECT nom_exutoire, exutoire_id FROM bassins_versants_79 WHERE id_bassin = ?", (cid_int,)).fetchone()
            else:
                row_b79 = cur_meta.execute("SELECT nom_exutoire, exutoire_id FROM bassins_versants_79 WHERE nom_exutoire = ? OR exutoire_id = ?", (cid_str, cid_str)).fetchone()
            if row_b79:
                if row_b79[0]:
                    bassin_nom = str(row_b79[0])
                if row_b79[1]:
                    cand_ex_id = str(row_b79[1])
                    if cand_ex_id in G_topo:
                        target_ex_id = cand_ex_id
                    elif cand_ex_id.endswith('.0') and cand_ex_id[:-2] in G_topo:
                        target_ex_id = cand_ex_id[:-2]
                    elif f"{cand_ex_id}.0" in G_topo:
                        target_ex_id = f"{cand_ex_id}.0"
                    else:
                        target_ex_id = cand_ex_id
        con_meta.close()
    except Exception as e_b79:
        logger.warning(f"Lecture bassins_versants_79: {e_b79}")

    if not target_ex_id:
        if cid_str in exutoires_map:
            target_ex_id = cid_str
            bassin_nom = exutoires_map[cid_str].get("nom") or cid_str
        else:
            for ex_k, ex_v in exutoires_map.items():
                if str(ex_v.get("nom", "")).strip().lower() == cid_str.lower():
                    target_ex_id = ex_k
                    bassin_nom = ex_v.get("nom") or cid_str
                    break
                if str(ex_k).strip().lower() == cid_str.lower():
                    target_ex_id = ex_k
                    bassin_nom = ex_v.get("nom") or cid_str
                    break

    ex_list = list(exutoires_map.items())
    if not target_ex_id and cid_int is not None and 1 <= cid_int <= len(ex_list):
        target_ex_id, ex_info = ex_list[cid_int - 1]
        if not bassin_nom:
            bassin_nom = ex_info.get("nom") or f"Bassin {cid_int}"
    elif not bassin_nom and cid_int is not None and 1 <= cid_int <= len(ex_list):
        bassin_nom = ex_list[cid_int - 1][1].get("nom") or f"Bassin {cid_int}"

    if target_ex_id:
        ex_info = exutoires_map.get(target_ex_id, {})
        est_deporte = bool(ex_info.get("est_deporte", False))
        regard_proche = ex_info.get("regard_proche_id")
        distance_deport = float(ex_info.get("distance_regard_proche_m") or 5.0)

        target_nodes = set([target_ex_id])
        queue = [target_ex_id]
        ex_set = set(exutoires_map.keys())

        if regard_proche and G_topo.has_node(regard_proche) and (est_deporte or G_topo.in_degree(target_ex_id) == 0):
            target_nodes.add(regard_proche)
            queue.append(regard_proche)

        while queue:
            curr = queue.pop(0)
            for pred in G_topo.predecessors(curr):
                if pred not in ex_set and pred not in target_nodes:
                    target_nodes.add(pred)
                    queue.append(pred)

        if len(target_nodes) == 1 and G_topo.has_node(target_ex_id) and G_topo.out_degree(target_ex_id) > 0:
            queue = [target_ex_id]
            while queue:
                curr = queue.pop(0)
                for succ in G_topo.successors(curr):
                    if succ not in target_nodes:
                        target_nodes.add(succ)
                        if succ not in ex_set:
                            queue.append(succ)

        clean_target_nodes = set(_clean_node_id(x) for x in target_nodes)
        clean_target_nodes.add(_clean_node_id(target_ex_id))
        if est_deporte and valider_raccordement_deporte and regard_proche:
            clean_target_nodes.add(_clean_node_id(regard_proche))

        c_filter = canalisations.apply(
            lambda c: (
                (_clean_node_id(c.get("ID_AMONT")) in clean_target_nodes and _clean_node_id(c.get("ID_AVAL")) in clean_target_nodes)
                or (_clean_node_id(c.get("ID_AVAL")) == _clean_node_id(target_ex_id))
                or (len(target_nodes) == 1 and _clean_node_id(c.get("ID_AMONT")) == _clean_node_id(target_ex_id))
            ),
            axis=1
        )
        canalisations = canalisations[c_filter].copy()

        if est_deporte and valider_raccordement_deporte and regard_proche:
            geom_line = None
            if G_topo.has_node(regard_proche) and G_topo.has_node(target_ex_id):
                p1 = G_topo.nodes[regard_proche].get('geometry')
                p2 = G_topo.nodes[target_ex_id].get('geometry')
                if p1 and p2:
                    from shapely.geometry import LineString
                    geom_line = LineString([p1, p2])
            conduit_racc = {
                "ID_TRONCON": f"C_RACC_{target_ex_id}",
                "ID_AMONT": _clean_node_id(regard_proche),
                "ID_AVAL": _clean_node_id(target_ex_id),
                "LONGUEUR": max(distance_deport, 1.0),
                "Longeur": max(distance_deport, 1.0),
                "DIAMETRE": 600,
                "Diametre": 600,
                "MATERIAU": "Beton arme",
                "RUGOSITE": 0.013,
                "PENTE": pente_moyenne_pct if pente_moyenne_pct else 1.0,
                "geometry": geom_line,
            }
            canalisations = pd.concat([canalisations, gpd.GeoDataFrame([conduit_racc])], ignore_index=True)

        for _, c in canalisations.iterrows():
            u = _clean_node_id(c.get("ID_AMONT"))
            d = _clean_node_id(c.get("ID_AVAL"))
            if u: clean_target_nodes.add(u)
            if d: clean_target_nodes.add(d)

        regards = regards[regards.apply(lambda r: _clean_node_id(r.get("Code")) in clean_target_nodes, axis=1)].copy()

        if len(canalisations) == 0:
            from shapely.geometry import Point, LineString
            ex_pt = ex_info.get("geometry")
            if ex_pt is None or (hasattr(ex_pt, 'is_empty') and ex_pt.is_empty):
                if G_topo and G_topo.has_node(target_ex_id) and G_topo.nodes[target_ex_id].get("geometry"):
                    ex_pt = G_topo.nodes[target_ex_id].get("geometry")
                elif not regards.empty and hasattr(regards.iloc[0], "geometry"):
                    ex_pt = regards.iloc[0].geometry
                else:
                    x = float(ex_info.get("x") or 345000.0)
                    y = float(ex_info.get("y") or 4000000.0)
                    ex_pt = Point(x, y)

            reg_code = _clean_node_id(target_ex_id, fallback=f"REG_{cid_int}")
            if len(regards) == 0:
                reg_dict = {
                    "Code": reg_code,
                    "Profondeur": 2.0,
                    "COTTN": 100.0,
                    "geometry": ex_pt
                }
                regards = gpd.GeoDataFrame([reg_dict], crs=regards.crs or "EPSG:32631")

            line_geom = LineString([(ex_pt.x, ex_pt.y), (ex_pt.x + 5.0, ex_pt.y + 5.0)])
            dummy_pipe = {
                "ID_AMONT": reg_code,
                "ID_AVAL": f"OUT_{reg_code}",
                "Longeur": 5.0,
                "DIAMETRE": 600.0,
                "MATERIAU": "Béton",
                "geometry": line_geom
            }
            canalisations = gpd.GeoDataFrame([dummy_pipe], crs=canalisations.crs or "EPSG:32631")

        outfall_code = _clean_node_id(target_ex_id)

    return regards, canalisations, outfall_code, target_ex_id, bassin_nom, clean_target_nodes, exutoires_map

