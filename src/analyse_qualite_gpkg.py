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

from src.domain.topologie.resolution_noeuds import (
    ResoluteurNoeuds, PROV_ID, PROV_ALIAS, PROV_SNAP, PROV_ABSENT,
)


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


def _col_val(row: Any, *names: str) -> Any:
    """
    Retourne la valeur de la première colonne correspondante dans une ligne
    (Series pandas ou dict), de façon insensible à la casse et aux accents
    courants des exports SIG (ex. 'LONGUEUR' ↔ 'longueur' ↔ 'Longeur').
    """
    if row is None:
        return None
    try:
        index = row.index if hasattr(row, "index") else row.keys()
    except Exception:
        return None
    lower_map = {}
    for col in index:
        try:
            lower_map.setdefault(str(col).strip().lower(), col)
        except Exception:
            continue
    for name in names:
        if name in row:
            return row[name]
        key = str(name).strip().lower()
        if key in lower_map:
            return row[lower_map[key]]
    return None


def _vers_metres_gdf(gdf: Any) -> Any:
    """Reprojette en CRS métrique (UTM 31N) si la géométrie est géographique."""
    if gdf is None or gdf.empty:
        return gdf
    try:
        if gdf.crs is not None and gdf.crs.is_geographic:
            from src.infrastructure.config import TARGET_CRS
            return gdf.to_crs(TARGET_CRS)
    except Exception:
        pass
    return gdf


def _point_geom(gdf_row_geom: Any):
    """Retourne (x, y) métriques du centroïde/point d'une géométrie."""
    try:
        if gdf_row_geom is None or gdf_row_geom.is_empty:
            return None
        pt = gdf_row_geom if gdf_row_geom.geom_type == "Point" else gdf_row_geom.centroid
        return (float(pt.x), float(pt.y))
    except Exception:
        return None


def _points_extremite(geom: Any) -> List[tuple]:
    """Points candidats d'une extrémité de tronçon : 1er et dernier vertex."""
    try:
        if geom is None or geom.is_empty:
            return []
        g = geom
        if g.geom_type == "MultiLineString":
            g = max(g.geoms, key=lambda s: s.length, default=None)
            if g is None:
                return []
        if g.geom_type == "LineString":
            coords = list(g.coords)
            if not coords:
                return []
            return [
                (float(coords[0][0]), float(coords[0][1])),
                (float(coords[-1][0]), float(coords[-1][1])),
            ]
        c = _point_geom(g)
        return [c] if c else []
    except Exception:
        return []


def _construire_resolveur(regards: Any, rejets: Any, gpkg_path: Path,
                          layers: List[str],
                          conventions: Optional[Dict[str, Any]] = None
                          ) -> Optional[ResoluteurNoeuds]:
    """
    Construit le résolveur canonique de nœuds (même source que le graphe de
    bassins et le générateur .inp) à partir des couches de nœuds du GPKG.
    Retourne None si aucun nœud exploitable n'est trouvé.
    """
    from src.domain.moteur_swmm.constants import _clean_node_id

    noeuds: Dict[str, tuple] = {}

    def _ajouter_couche(gdf: Any):
        gg = _vers_metres_gdf(gdf)
        if gg is None or gg.empty:
            return
        for _, r in gg.iterrows():
            nid = _clean_node_id(_col_val(
                r, "Code", "CODE", "id", "ID", "swmm_id", "SWMM_ID",
                "NOM", "nom", "INTITULE", "intitule"))
            if not nid or nid in noeuds:
                continue
            pt = _point_geom(getattr(r, "geometry", None))
            if pt is not None:
                noeuds[nid] = pt

    _ajouter_couche(regards)
    _ajouter_couche(rejets)

    # Stations de relèvement, STEP et ouvrages spéciaux : nœuds à part entière
    for lyr in layers:
        low = str(lyr).lower()
        if any(k in low for k in ("station", "step", "ouvrage")):
            try:
                _ajouter_couche(gpd.read_file(str(gpkg_path), layer=lyr))
            except Exception:
                continue

    if not noeuds:
        return None
    conv = conventions or {}
    alias_noyau = conv.get("alias_noyau") or {}
    return ResoluteurNoeuds(
        noeuds,
        tolerance_snap_m=float(conv.get("snap_tolerance_m") or 0.50),
        correspondance_noyau=bool(alias_noyau.get("actif")),
        alias_auto_max_dist_m=float(alias_noyau.get("max_dist_m") or 2.5),
    )


def _resoudre_extremite(resolveur: ResoluteurNoeuds, nid_brut: str,
                        points: List[tuple]):
    """
    Résout une extrémité via ID -> alias -> snap (1er puis dernier vertex).
    Retourne (ResolutionNoeud, a_point_disponible).
    """
    if not nid_brut and not points:
        from src.domain.topologie.resolution_noeuds import ResolutionNoeud
        return ResolutionNoeud(None, PROV_ABSENT, 0.0), False

    p1 = points[0] if points else None
    res = resolveur.resoudre(nid_brut, point=p1)
    if res.resolu:
        return res, True
    if len(points) > 1:
        res2 = resolveur.resoudre(nid_brut, point=points[1])
        if res2.resolu:
            return res2, True
        # Conserver la tentative de snap la plus informative
        if res2.provenance == PROV_SNAP:
            return res2, True
    return res, bool(points)


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

    # Référentiel des identifiants de nœuds valides (contrôle topologique brut)
    valid_nodes: Dict[str, Any] = {}
    if not regards.empty:
        for idx, r in regards.iterrows():
            nid = _clean_id(_col_val(r, "Code", "CODE", "id", "ID", "swmm_id", "SWMM_ID", "NOM", "nom")) or str(idx)
            valid_nodes[nid] = r

    if not rejets.empty:
        for idx, rj in rejets.iterrows():
            r_id = _clean_id(_col_val(rj, "Code", "CODE", "id", "ID", "NOM", "nom")) or f"REJ_{idx+1}"
            valid_nodes[r_id] = rj

    # Conventions auto-découvertes du GPKG (partagées avec graphe et .inp)
    conventions_gpkg = None
    try:
        from src.domain.topologie.decouverte_conventions import obtenir_conventions
        conventions_gpkg = obtenir_conventions(gpkg_path)
    except Exception:
        conventions_gpkg = None

    # Résolveur canonique de nœuds : le verdict de connectivité reflète ce que
    # la simulation résoudra réellement (ID -> alias RJ -> snap -> spatial),
    # au lieu du simple test d'appartenance textuelle à valid_nodes.
    resolveur_noeuds = _construire_resolveur(
        regards, rejets, gpkg_path, layers, conventions=conventions_gpkg)
    pipes_m = _vers_metres_gdf(pipes)

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

    # Statistiques de connectivité par provenance de résolution
    stats_conn = {
        "extremites_total": 0,
        PROV_ID: 0, PROV_ALIAS: 0, PROV_SNAP: 0,
        "spatial": 0, "absent": 0,
    }

    for idx, c in pipes.iterrows():
        u = _clean_id(_col_val(c, "ID_AMONT", "id_amont", "amont", "AMONT", "NOEUD_AMONT"))
        d = _clean_id(_col_val(c, "ID_AVAL", "id_aval", "aval", "AVAL", "NOEUD_AVAL"))
        if u:
            upstream_connections.add(u)
        if d:
            downstream_connections.add(d)

    # 1. Analyse des canalisations
    for idx, c in pipes.iterrows():
        cid = f"C_{idx+1}"
        u = _clean_id(_col_val(c, "ID_AMONT", "id_amont", "amont", "AMONT", "NOEUD_AMONT"))
        d = _clean_id(_col_val(c, "ID_AVAL", "id_aval", "aval", "AVAL", "NOEUD_AVAL"))

        # Coordonnées pour centrage carte
        lat, lon = None, None
        if not wgs_pipes.empty and idx < len(wgs_pipes):
            geom = wgs_pipes.geometry.iloc[idx]
            if geom and not geom.is_empty:
                centroid = geom.centroid
                lat, lon = round(centroid.y, 6), round(centroid.x, 6)

        # A. Extrémités non résolues — résolveur canonique (ID -> alias -> snap)
        #    Une extrémité avec point de snap disponible mais sans nœud déclaré
        #    est classée 'spatiale' (nœud créé par la simulation, à vérifier,
        #    sévérité mineure) ; sans aucun point elle est 'absente' (majeure).
        geom_m = None
        if resolveur_noeuds is not None and not pipes_m.empty and idx < len(pipes_m):
            geom_m = pipes_m.geometry.iloc[idx]
        points = _points_extremite(geom_m)

        def _statut_extremite(nid_brut):
            """Retourne (manque: bool, severite: str, detail: str)."""
            stats_conn["extremites_total"] += 1
            if resolveur_noeuds is None:
                # Repli : ancien contrôle textuel strict
                manque = not nid_brut or nid_brut not in valid_nodes
                return manque, "majeure", "introuvable (contrôle strict)"
            res, a_point = _resoudre_extremite(resolveur_noeuds, nid_brut, points)
            if res.resolu:
                stats_conn[res.provenance] = stats_conn.get(res.provenance, 0) + 1
                return False, "", ""
            if a_point:
                stats_conn["spatial"] += 1
                return True, "mineure", "sans nœud déclaré — raccordement spatial à vérifier"
            stats_conn["absent"] += 1
            return True, "majeure", "introuvable (ni ID, ni alias, ni snap, ni point)"

        manque_amont, sev_amont, det_amont = _statut_extremite(u)
        manque_aval, sev_aval, det_aval = _statut_extremite(d)

        if manque_amont or manque_aval:
            desc = []
            if manque_amont:
                desc.append(f"amont '{u or 'Non renseigné'}' {det_amont}")
            if manque_aval:
                desc.append(f"aval '{d or 'Non renseigné'}' {det_aval}")
            severites = [s for m, s in ((manque_amont, sev_amont), (manque_aval, sev_aval)) if m]
            severite = "majeure" if "majeure" in severites else "mineure"
            anomalies["conduites_sans_regards"].append({
                "id_conduite": cid,
                "type": "conduite_sans_regard",
                "id_amont": u,
                "id_aval": d,
                "severite": severite,
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
        diam = _col_val(c, "DIAMETRE", "diametre", "Diamètre", "DIAMETER", "diameter")
        mat = _col_val(c, "MATERIAU", "materiau", "Matériau", "MATERIAL", "material")
        longueur = _col_val(c, "LONGUEUR", "Longeur", "longueur", "Length", "length")

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
            # Rechercher cote radier ou TN (COTRAD/COTETN = schéma SIG français courant)
            z_u = None
            z_d = None
            for col in ["COTRAD", "PROFRADI", "COTTN", "COORDZ", "Z", "cote_radier", "COTETN", "TN", "ALTITUDE"]:
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

    total_ext = stats_conn["extremites_total"]
    nb_resolues = stats_conn.get(PROV_ID, 0) + stats_conn.get(PROV_ALIAS, 0) + stats_conn.get(PROV_SNAP, 0) + stats_conn.get(PROV_ALIAS_AUTO, 0)
    connectivite = {
        "methode": "résolveur canonique : ID -> alias RJ -> alias auto (noyau) -> snap <= tolérance -> nœud spatial",
        "extremites_total": total_ext,
        "resolues": {
            "par_identifiant": stats_conn.get(PROV_ID, 0),
            "par_alias": stats_conn.get(PROV_ALIAS, 0),
            "par_alias_auto": stats_conn.get(PROV_ALIAS_AUTO, 0),
            "par_snap": stats_conn.get(PROV_SNAP, 0),
        },
        "non_resolues_spatiales": stats_conn.get("spatial", 0),
        "non_resolues_absentes": stats_conn.get("absent", 0),
        "taux_resolution_pct": round(100.0 * nb_resolues / total_ext, 2) if total_ext else 100.0,
        "conventions": {
            "alias_noyau_actif": bool((conventions_gpkg or {}).get("alias_noyau", {}).get("actif")),
            "alias_noyau_occurrences": (conventions_gpkg or {}).get("alias_noyau", {}).get("occurrences", 0),
            "snap_tolerance_m": (conventions_gpkg or {}).get("snap_tolerance_m"),
            "decouvert_le": (conventions_gpkg or {}).get("decouvert_le"),
        } if conventions_gpkg else None,
    }

    statistiques_globales = {
        "nb_regards": nb_regards,
        "nb_conduites": nb_pipes,
        "nb_rejets": nb_rejets,
        "nb_communes": nb_communes,
        "longueur_totale_m": longueur_totale,
        "nom_projet": project_name,
        "gpkg_path": str(gpkg_path),
        "connectivite": connectivite,
    }

    rapport = {
        "date_analyse": datetime.now().isoformat(),
        "project_name": project_name,
        "statistiques_globales": statistiques_globales,
        "anomalies": anomalies,
        "scores_qualite": scores_qualite
    }

    return rapport
