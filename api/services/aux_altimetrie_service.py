# -*- coding: utf-8 -*-
"""
================================================================================
Service altimétrie des couches SIG « satellite » — SHP.md §4
================================================================================
Grille IDW pré-calculée à l'import d'une couche `altimetrie_points`.

RÈGLE SCIENTIFIQUE (SHP.md §5) : la cote retournée est la COTE DU TERRAIN
interpolée — jamais le fond de regard. Les usages se limitent aux différences
(pentes, cohérence amont/aval, classement de candidats).

La confiance décroît avec la distance au point topographique le plus proche :
  < 15 m  → haute
  < 50 m  → moyenne
  >= 50 m → faible
================================================================================
"""

import io
import logging
import re
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import geopandas as gpd
import numpy as np
from pyproj import Transformer
from scipy.interpolate import RegularGridInterpolator
from scipy.spatial import cKDTree

from api.services.aux_layers_service import (
    _chemin_materialise,
    cle_couche_aux,
    _store,
)

logger = logging.getLogger(__name__)

# Paramètres de la grille IDW
RESOLUTION_CIBLE_M = 30.0          # maille ~30 m
K_VOISINS_IDW = 8                  # voisins pour l'interpolation
PUISSANCE_IDW = 2.0
DIST_MAX_TOPO_M = 150.0            # au-delà : cellule considérée non couverte
TAILLE_MAX_CELLULES = 2_000_000

_CACHE_GRILLES: Dict[str, Dict[str, Any]] = {}
_CACHE_POINTS: Dict[str, cKDTree] = {}
_CACHE_LOCK = threading.Lock()

_COLONNE_Z_REGEX = re.compile(r"(^|_)(z|alt|altitude|cote|nivellement|altimetrie)(_|$)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Extraction des points (x, y, z)
# ---------------------------------------------------------------------------

def _zone_utm(lon: float, lat: float) -> int:
    """Zone UTM (WGS84) pour un point donné — hémisphère nord uniquement (Algérie)."""
    return int((lon + 180) // 6) + 1


def _crs_metric(gdf: gpd.GeoDataFrame):
    """CRS métrique local (UTM) dérivé du centroïde de la couche."""
    bounds = gdf.total_bounds  # en 4326
    lon = (bounds[0] + bounds[2]) / 2
    lat = (bounds[1] + bounds[3]) / 2
    zone = _zone_utm(lon, lat)
    return f"EPSG:326{zone:02d}", zone


def _extraire_xyz(gdf: gpd.GeoDataFrame, colonne_z: Optional[str]) -> Tuple[np.ndarray, str]:
    """
    Extrait (x_utm, y_utm, z) des entités.
    Source z : colonne_z explicite > geometry.z > colonne auto-détectée.
    Retourne (array N×3, nom_colonne_z_utilisée).
    """
    gmetric = gdf.to_crs(_crs_metric(gdf)[0])

    # Coordonnées métriques des entités (représentatives pour polygones/MultiPoint)
    pts = gmetric.geometry.representative_point()
    xy = np.array([[p.x, p.y] for p in pts])

    # Source d'altitude
    z = None
    nom_z = None
    if colonne_z and colonne_z in gdf.columns:
        z = pd_to_float(gdf[colonne_z].values)
        nom_z = colonne_z
    else:
        has_z = gmetric.geometry.has_z
        has_z = bool(has_z.any()) if hasattr(has_z, "any") else bool(has_z)
        if has_z:
            z = np.array([p.z if p.has_z else np.nan for p in gmetric.geometry])
            nom_z = "geometry.z"
        else:
            for col in gdf.columns:
                if col == "geometry":
                    continue
                if _COLONNE_Z_REGEX.search(str(col)):
                    cand = pd_to_float(gdf[col].values)
                    if np.isfinite(cand).sum() > len(gdf) * 0.5:
                        z = cand
                        nom_z = str(col)
                        break

    if z is None:
        raise ValueError(
            "Aucune colonne d'altitude détectée. Précisez 'colonne_z' à l'upload "
            "(ex. Field4 pour TOPO CHLEF)."
        )

    mask = np.isfinite(z) & np.isfinite(xy[:, 0]) & np.isfinite(xy[:, 1])
    if mask.sum() < 3:
        raise ValueError("Moins de 3 points cotés exploitables.")
    return np.column_stack([xy[mask], z[mask]]), nom_z or "inconnue"


def pd_to_float(values) -> np.ndarray:
    """Conversion robuste pandas → float64 (gère NaN, None, chaînes)."""
    import pandas as pd
    s = pd.to_numeric(pd.Series(values), errors="coerce")
    return s.to_numpy(dtype="float64")


# ---------------------------------------------------------------------------
# Construction de la grille IDW
# ---------------------------------------------------------------------------

def construire_grille_altimetrie(
    org_id: str,
    project_id: str,
    layer_id: str,
    storage_key: str,
    colonne_z: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Construit la grille IDW + l'index des points pour une couche
    `altimetrie_points`. Persiste derive/grid.npz via ArtifactStore.
    Retourne des métadonnées (résolution, emprise, nb points, colonne z).
    """
    from api.services.aux_layers_service import lire_gdf_couche

    gdf = lire_gdf_couche(layer_id, storage_key)
    xyz, nom_z = _extraire_xyz(gdf, colonne_z)

    crs_metric, zone = _crs_metric(gdf)
    xy = xyz[:, :2]
    z = xyz[:, 2]

    # Emprise de la grille = emprise des points + marge d'une cellule
    minx, miny = xy.min(axis=0)
    maxx, maxy = xy.max(axis=0)
    marge = RESOLUTION_CIBLE_M
    minx -= marge; miny -= marge; maxx += marge; maxy += marge

    largeur = maxx - minx
    hauteur = maxy - miny
    nx = max(2, int(np.ceil(largeur / RESOLUTION_CIBLE_M)))
    ny = max(2, int(np.ceil(hauteur / RESOLUTION_CIBLE_M)))
    if nx * ny > TAILLE_MAX_CELLULES:
        # Réduit la résolution plutôt que d'échouer
        facteur = np.sqrt(nx * ny / TAILLE_MAX_CELLULES)
        nx = max(2, int(nx / facteur))
        ny = max(2, int(ny / facteur))

    dx = largeur / nx
    dy = hauteur / ny

    # Centres des cellules
    xs = minx + (np.arange(nx) + 0.5) * dx
    ys = miny + (np.arange(ny) + 0.5) * dy
    gx, gy = np.meshgrid(xs, ys)  # (ny, nx)
    grid_pts = np.column_stack([gx.ravel(), gy.ravel()])

    tree = cKDTree(xy)
    dist, idx = tree.query(grid_pts, k=min(K_VOISINS_IDW, len(xy)))
    if idx.ndim == 1:
        idx = idx[:, None]; dist = dist[:, None]

    # IDW : poids 1/d^p avec epsilon pour éviter la singularité
    eps = 1e-6
    poids = 1.0 / np.power(dist + eps, PUISSANCE_IDW)
    zvals = z[idx]
    zgrid = (poids * zvals).sum(axis=1) / poids.sum(axis=1)
    zgrid = zgrid.reshape(ny, nx).astype("float32")

    # Cellules sans couverture suffisante → NaN puis comblement par plus proche
    dmin = dist[:, 0].reshape(ny, nx)
    zgrid[dmin > DIST_MAX_TOPO_M] = np.nan

    if np.isnan(zgrid).any():
        valides = ~np.isnan(zgrid)
        if valides.sum() == 0:
            raise ValueError("Grille altimétrique vide : aucun point topo exploitable.")
        # Coordonnées et valeurs des cellules valides, dans le même ordre (C-order)
        coords_valides = np.column_stack([gx[valides], gy[valides]])
        z_valides = zgrid[valides]
        tree_val = cKDTree(coords_valides)
        _, idx_proche = tree_val.query(np.column_stack([gx.ravel(), gy.ravel()]), k=1)
        remplissage = z_valides[idx_proche].reshape(ny, nx)
        zgrid = np.where(np.isnan(zgrid), remplissage, zgrid).astype("float32")

    # Persistance npz via ArtifactStore
    buf = io.BytesIO()
    np.savez_compressed(
        buf,
        x0=np.float64(minx), y0=np.float64(miny),
        dx=np.float64(dx), dy=np.float64(dy),
        nx=np.int32(nx), ny=np.int32(ny),
        utm_epsg=np.int32(32600 + zone),
        z=zgrid,
        px=xy[:, 0].astype("float64"), py=xy[:, 1].astype("float64"),
        colonne_z=np.array([nom_z]),
    )
    buf.seek(0)
    cle = cle_couche_aux(org_id, project_id, layer_id, "derive/grid.npz")
    _store().put_bytes(cle, buf.getvalue())

    with _CACHE_LOCK:
        _CACHE_GRILLES.pop(layer_id, None)
        _CACHE_POINTS.pop(layer_id, None)

    return {
        "resolution_m": round(float(dx), 2),
        "grille": {"nx": int(nx), "ny": int(ny)},
        "emprise_m": {"minx": float(minx), "miny": float(miny), "maxx": float(maxx), "maxy": float(maxy)},
        "nb_points": int(len(z)),
        "colonne_z": nom_z,
        "crs_metric": crs_metric,
    }


# ---------------------------------------------------------------------------
# Requête d'élévation (sonde)
# ---------------------------------------------------------------------------

def _charger_grille(org_id: str, project_id: str, layer_id: str) -> Optional[Dict[str, Any]]:
    """Charge la grille npz (cache mémoire par layer_id)."""
    with _CACHE_LOCK:
        if layer_id in _CACHE_GRILLES:
            return _CACHE_GRILLES[layer_id]

    cle = cle_couche_aux(org_id, project_id, layer_id, "derive/grid.npz")
    store = _store()
    if not store.exists(cle):
        return None
    data = np.load(io.BytesIO(store.get_bytes(cle)))
    grille = {
        "x0": float(data["x0"]), "y0": float(data["y0"]),
        "dx": float(data["dx"]), "dy": float(data["dy"]),
        "nx": int(data["nx"]), "ny": int(data["ny"]),
        "utm_epsg": int(data["utm_epsg"]),
        "z": data["z"],
        "px": data["px"], "py": data["py"],
    }
    with _CACHE_LOCK:
        _CACHE_GRILLES[layer_id] = grille
        _CACHE_POINTS[layer_id] = cKDTree(np.column_stack([grille["px"], grille["py"]]))
    return grille


def _confiance(distance_m: float) -> str:
    if distance_m < 15.0:
        return "haute"
    if distance_m < 50.0:
        return "moyenne"
    return "faible"


def elevation(org_id: str, project_id: str, layer_id: str, lng: float, lat: float) -> Dict[str, Any]:
    """
    Cote terrain estimée par IDW bilinéaire + distance au point topo le plus
    proche + niveau de confiance. COTE TERRAIN ≠ FOND DE REGARD (SHP.md §5).
    """
    grille = _charger_grille(org_id, project_id, layer_id)
    if grille is None:
        raise ValueError("Aucune grille altimétrique pour cette couche (pas de points cotés).")

    epsg = grille["utm_epsg"]
    t = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    x, y = t.transform(lng, lat)

    x0, y0, dx, dy, nx, ny = grille["x0"], grille["y0"], grille["dx"], grille["dy"], grille["nx"], grille["ny"]
    z = grille["z"]

    # Position dans la grille
    fx = (x - x0) / dx - 0.5
    fy = (y - y0) / dy - 0.5

    dans_emprise = (0 <= fx <= nx - 1) and (0 <= fy <= ny - 1)

    z_estime = None
    if dans_emprise:
        # Interpolation bilinéaire manuelle
        ix = int(np.clip(np.floor(fx), 0, nx - 2))
        iy = int(np.clip(np.floor(fy), 0, ny - 2))
        tx = float(np.clip(fx - ix, 0.0, 1.0))
        ty = float(np.clip(fy - iy, 0.0, 1.0))
        z00, z10 = z[iy, ix], z[iy, ix + 1]
        z01, z11 = z[iy + 1, ix], z[iy + 1, ix + 1]
        if np.isfinite([z00, z10, z01, z11]).all():
            z_estime = float(
                z00 * (1 - tx) * (1 - ty) + z10 * tx * (1 - ty)
                + z01 * (1 - tx) * ty + z11 * tx * ty
            )
        else:
            # Repli : cellule la plus proche
            z_estime = float(z[min(ny - 1, max(0, round(fy))), min(nx - 1, max(0, round(fx)))])

    # Distance au point topo le plus proche (confiance)
    with _CACHE_LOCK:
        tree = _CACHE_POINTS.get(layer_id)
    if tree is None:
        tree = cKDTree(np.column_stack([grille["px"], grille["py"]]))
        with _CACHE_LOCK:
            _CACHE_POINTS[layer_id] = tree
    dist_m, _ = tree.query([[x, y]], k=1)
    distance_m = float(dist_m[0])

    if z_estime is None or not np.isfinite(z_estime):
        return {
            "statut": "hors_emprise",
            "message": "Point hors de l'emprise de la couche altimétrique.",
            "lng": lng, "lat": lat,
            "distance_point_topo_m": round(distance_m, 1),
            "confiance": "aucune",
        }

    return {
        "statut": "ok",
        "lng": lng,
        "lat": lat,
        "z_terrain_m": round(z_estime, 2),
        "distance_point_topo_m": round(distance_m, 1),
        "confiance": _confiance(distance_m),
        "unite": "m",
        "avertissement": "Cote du terrain interpolée — ne correspond pas au fond de regard (égout enterré ~1-3 m).",
    }
