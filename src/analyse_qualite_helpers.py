# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Helpers audit qualite GPKG : nettoyage ids, colonnes, resolveur noeuds (extrait de src/analyse_qualite_gpkg.py)
================================================================================
"""

import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import re
from pathlib import Path
from typing import Dict, Any, List, Optional
import geopandas as gpd
import pandas as pd
import numpy as np

from src.domain.topologie.resolution_noeuds import (
    ResoluteurNoeuds, PROV_ID, PROV_ALIAS, PROV_ALIAS_AUTO, PROV_SNAP, PROV_ABSENT,
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


def _index_colonnes_bas(colonnes: Any) -> Dict[str, Any]:
    """
    Construit UNE fois la table {nom_colonne_minuscule: nom_reel} d'un jeu
    de colonnes. `_col_val` était appelée ~270 000 fois en reconstruisant
    cette table à chaque appel (profilage : ~75 s cumulées sur 10k tronçons).
    """
    lower_map: Dict[str, Any] = {}
    try:
        for col in colonnes:
            try:
                lower_map.setdefault(str(col).strip().lower(), col)
            except Exception:
                continue
    except Exception:
        pass
    return lower_map


def _resoudre_colonne(
    map_bas: Dict[str, Any],
    colonnes: Any,
    *names: str,
) -> Optional[str]:
    """
    Résout le nom RÉEL d'une colonne candidate dans un DataFrame, avec la
    même sémantique que `_col_val` (match exact prioritaire, puis
    insensible casse/espaces) — mais calculé UNE fois pour toute la table
    au lieu de chaque ligne. Retourne None si aucune candidate ne matche.
    """
    for name in names:
        if name in colonnes:
            return name
        key = str(name).strip().lower()
        if key in map_bas:
            return map_bas[key]
    return None


def _col_val(row: Any, *names: str, _lower_map: Optional[Dict[str, Any]] = None) -> Any:
    """
    Retourne la valeur de la première colonne correspondante dans une ligne
    (Series pandas ou dict), de façon insensible à la casse et aux accents
    courants des exports SIG (ex. 'LONGUEUR' ↔ 'longueur' ↔ 'Longeur').
    `_lower_map` permet de passer la table pré-calculée par `_index_colonnes_bas`
    (obligatoire dans les boucles chaudes sur DataFrame).
    """
    if row is None:
        return None
    try:
        index = row.index if hasattr(row, "index") else row.keys()
    except Exception:
        return None
    if _lower_map is None:
        _lower_map = _index_colonnes_bas(index)
    for name in names:
        if name in row:
            return row[name]
        key = str(name).strip().lower()
        if key in _lower_map:
            return row[_lower_map[key]]
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
        map_couche = _index_colonnes_bas(gg.columns)
        col_nid = _resoudre_colonne(
            map_couche, gg.columns,
            "Code", "CODE", "id", "ID", "swmm_id", "SWMM_ID",
            "NOM", "nom", "INTITULE", "intitule")
        vals = gg[col_nid].tolist() if col_nid is not None else [None] * len(gg)
        geoms = list(gg.geometry.values) if len(gg) else []
        for i, v in enumerate(vals):
            nid = _clean_node_id(v)
            if not nid or nid in noeuds:
                continue
            pt = _point_geom(geoms[i] if i < len(geoms) else None)
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
