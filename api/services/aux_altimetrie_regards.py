# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Normalisation codes regards, échantillonnage grille, calcul/chargement cotes terrain (extrait de services/aux_altimetrie_service.py)
================================================================================
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import geopandas as gpd
import numpy as np

logger = logging.getLogger(__name__)
from pyproj import Transformer
from scipy.spatial import cKDTree

from api.services.aux_altimetrie_grille import (
    _CACHE_GRILLES,
    _CACHE_LOCK,
    _CACHE_POINTS,
    _charger_grille,
    _confiance,
)
from api.services.aux_layers_service import (
    cle_couche_aux,
    _store,
)


def _normaliser_code_regard(valeurs) -> np.ndarray:
    """Normalise les codes regards comme le frontend : str, strip, retire '.0'."""
    out = []
    for v in valeurs:
        if v is None:
            out.append("")
            continue
        s = str(v).strip()
        if s.endswith(".0"):
            s = s[:-2]
        out.append(s)
    return np.array(out, dtype=object)


def _lire_regards_projet(db, org_id: str, project_id: str):
    """Lit les regards du GPKG projet (code + position WGS84)."""
    from api.models import Project
    from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet_avec_meta
    import geopandas as gpd

    project = db.query(Project).filter(
        Project.id == project_id, Project.org_id == org_id
    ).first()
    if project is None:
        return None, None, "Projet introuvable."
    gpkg_path, meta_v = resoudre_gpkg_effectif_pour_projet_avec_meta(db, project)
    if gpkg_path is None:
        return None, None, "Aucun GeoPackage projet résolu."

    try:
        couches = gpd.list_layers(gpkg_path)["name"].tolist()
    except Exception as e:
        return None, None, f"Lecture GPKG impossible : {e}"
    nom_layer = next((l for l in couches if "regard" in l.lower()), None)
    if nom_layer is None:
        return None, None, "Couche 'regards' absente du GPKG projet."

    try:
        g = gpd.read_file(gpkg_path, layer=nom_layer)
    except Exception as e:
        return None, None, f"Lecture couche regards impossible : {e}"
    if g.empty:
        return None, None, "Couche regards vide."
    if "Code" not in g.columns:
        return None, None, "Colonne 'Code' absente de la couche regards."
    if g.crs is None:
        return None, None, "CRS des regards indéterminé."
    if str(g.crs) != "EPSG:4326":
        g = gpd.GeoDataFrame(g, geometry=g.geometry.to_crs("EPSG:4326"), crs="EPSG:4326")

    gpkg_sha = (meta_v or {}).get("sha256")
    if not gpkg_sha:
        try:
            from api.services.gpkg_versions import sha256_fichier
            gpkg_sha = sha256_fichier(Path(gpkg_path))
        except Exception:
            gpkg_sha = None
    return g, gpkg_sha, None


def _echantillonner_grille_bilin(grid, x, y):
    """Interpolation bilinéaire vectorisée sur la grille + indices de cellules."""
    x0, y0, dx, dy, nx, ny = grid["x0"], grid["y0"], grid["dx"], grid["dy"], grid["nx"], grid["ny"]
    z = grid["z"]
    fx = (x - x0) / dx - 0.5
    fy = (y - y0) / dy - 0.5
    dans = (fx >= 0) & (fx <= nx - 1) & (fy >= 0) & (fy <= ny - 1)

    ix = np.clip(np.floor(fx).astype(int), 0, nx - 2)
    iy = np.clip(np.floor(fy).astype(int), 0, ny - 2)
    tx = np.clip(fx - ix, 0.0, 1.0)
    ty = np.clip(fy - iy, 0.0, 1.0)

    z00 = z[iy, ix]; z10 = z[iy, ix + 1]
    z01 = z[iy + 1, ix]; z11 = z[iy + 1, ix + 1]
    vals = z00 * (1 - tx) * (1 - ty) + z10 * tx * (1 - ty) + z01 * (1 - tx) * ty + z11 * tx * ty

    # Repli cellule la plus proche pour les NaN résiduels
    if np.isnan(vals).any():
        cx = np.clip(np.round(fx).astype(int), 0, nx - 1)
        cy = np.clip(np.round(fy).astype(int), 0, ny - 1)
        vals_proches = z[cy, cx]
        vals = np.where(np.isnan(vals), vals_proches, vals)
    return vals, dans


def calculer_regards_terrain(db, org_id: str, project_id: str, layer_id: str, storage_key: str) -> Dict[str, Any]:
    """
    Produit l'artefact derive/regards_terrain.json : pour chaque regard du
    GPKG projet → coords, cote terrain IDW, distance topo, confiance,
    pente terrain et azimut de plus forte descente.

    Estampillé meta.gpkg_sha256 (version réseau au moment du calcul).
    """
    g, gpkg_sha, err = _lire_regards_projet(db, org_id, project_id)
    if g is None:
        return {"statut": "ignore", "raison": err}

    grille = _charger_grille(org_id, project_id, layer_id)
    if grille is None:
        return {"statut": "ignore", "raison": "Aucune grille altimétrique."}

    epsg = grille["utm_epsg"]
    t = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    coords = np.array(g.geometry.apply(lambda p: (p.x, p.y) if p is not None else (np.nan, np.nan)).tolist())
    vals = t.transform(coords[:, 0], coords[:, 1])
    x, y = np.asarray(vals[0], dtype="float64"), np.asarray(vals[1], dtype="float64")

    zvals, dans = _echantillonner_grille_bilin(grille, x, y)

    # Gradient de la grille (dérivées partielles) pour pente + azimut
    dx, dy = grille["dx"], grille["dy"]
    dg_dy, dg_dx = np.gradient(grille["z"].astype("float64"), dy, dx)

    # Échantillonnage du gradient aux points (cellule la plus proche suffit)
    x0, y0, nx, ny = grille["x0"], grille["y0"], grille["nx"], grille["ny"]
    ix = np.clip(np.round((x - x0) / dx - 0.5).astype(int), 0, nx - 1)
    iy = np.clip(np.round((y - y0) / dy - 0.5).astype(int), 0, ny - 1)
    gx = dg_dx[iy, ix]
    gy = dg_dy[iy, ix]
    with np.errstate(invalid="ignore"):
        pente_pct = np.sqrt(gx ** 2 + gy ** 2) * 100.0
        # Direction de plus forte descente : opposé du gradient, azimut horaire depuis le Nord
        azimut = (np.degrees(np.arctan2(-gx, -gy)) + 360.0) % 360.0

    # Distance au point topo le plus proche
    with _CACHE_LOCK:
        tree = _CACHE_POINTS.get(layer_id)
    if tree is None:
        tree = cKDTree(np.column_stack([grille["px"], grille["py"]]))
        with _CACHE_LOCK:
            _CACHE_POINTS[layer_id] = tree
    dist_m, _ = tree.query(np.column_stack([x, y]), k=1)

    codes = _normaliser_code_regard(g["Code"].values)
    lngs = coords[:, 0]
    lats = coords[:, 1]

    regards = {}
    doublons = 0
    hors = 0
    for i in range(len(g)):
        code = codes[i]
        if not code:
            continue
        ok = bool(dans[i]) and np.isfinite(zvals[i])
        if not ok:
            hors += 1
        if code in regards:
            doublons += 1
            continue
        regards[code] = {
            "lng": round(float(lngs[i]), 6),
            "lat": round(float(lats[i]), 6),
            "z_terrain_m": round(float(zvals[i]), 2) if ok else None,
            "distance_topo_m": round(float(dist_m[i]), 1),
            "confiance": _confiance(float(dist_m[i])) if ok else "aucune",
            "pente_terrain_pct": round(float(pente_pct[i]), 2) if ok and np.isfinite(pente_pct[i]) else None,
            "azimut_pente_deg": round(float(azimut[i]), 1) if ok and np.isfinite(azimut[i]) else None,
        }

    artefact = {
        "meta": {
            "layer_id": layer_id,
            "type": "regards_terrain",
            "gpkg_sha256": gpkg_sha,
            "resolution_m": round(float(dx), 2),
            "utm_epsg": int(epsg),
            "nb_regards": len(regards),
            "nb_hors_emprise": hors,
            "codes_en_doublon": doublons,
            "avertissement": "Cotes du terrain interpolées — ne correspondent pas aux fonds de regard.",
        },
        "regards": regards,
    }

    payload = json.dumps(artefact, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    cle = cle_couche_aux(org_id, project_id, layer_id, "derive/regards_terrain.json")
    _store().put_bytes(cle, payload)

    with _CACHE_LOCK:
        _CACHE_GRILLES.pop(layer_id, None)
        _CACHE_POINTS.pop(layer_id, None)

    return {
        "statut": "ok",
        "nb_regards": len(regards),
        "nb_hors_emprise": hors,
        "codes_en_doublon": doublons,
        "gpkg_sha256": gpkg_sha,
        "taille_octets": len(payload),
    }


def charger_regards_terrain(org_id: str, project_id: str, layer_id: str) -> Optional[Dict[str, Any]]:
    """Charge l'artefact regards_terrain.json s'il existe."""
    cle = cle_couche_aux(org_id, project_id, layer_id, "derive/regards_terrain.json")
    store = _store()
    if not store.exists(cle):
        return None
    try:
        return json.loads(store.get_bytes(cle).decode("utf-8"))
    except Exception:
        return None


def sha_gpkg_projet(db, org_id: str, project_id: str) -> Optional[str]:
    """Empreinte de la version GPKG projet courante (pour détecter la péremption)."""
    from api.models import Project
    from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet_avec_meta
    project = db.query(Project).filter(
        Project.id == project_id, Project.org_id == org_id
    ).first()
    if project is None:
        return None
    _, meta_v = resoudre_gpkg_effectif_pour_projet_avec_meta(db, project)
    sha = (meta_v or {}).get("sha256")
    if sha:
        return sha
    chemin, _ = resoudre_gpkg_effectif_pour_projet_avec_meta(db, project)
    if chemin:
        try:
            from api.services.gpkg_versions import sha256_fichier
            return sha256_fichier(Path(chemin))
        except Exception:
            return None
    return None


# ---------------------------------------------------------------------------
# Aperçu « terrain → radier » pour injection .inp (option C, SHP.md §7)
# ---------------------------------------------------------------------------
