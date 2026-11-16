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
import json
import logging
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import geopandas as gpd
import numpy as np
from pyproj import Transformer
from scipy.spatial import cKDTree

from api.services.aux_layers_service import (
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


# ---------------------------------------------------------------------------
# Artefact dérivé : cote terrain + pente par regard (SHP.md §7)
# ---------------------------------------------------------------------------

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

SEUIL_COUVERTURE_INP = 0.95   # garde-fou : ≥95 % des nœuds couverts sinon refus


def _mediane(valeurs) -> Optional[float]:
    vals = sorted(float(v) for v in valeurs
                  if v is not None and np.isfinite(float(v)))
    if not vals:
        return None
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2.0


def calculer_apercu_terrain(regards_gdf, canalisations_gdf, artefact) -> Dict[str, Any]:
    """
    Calcul PUR (sans IO) : pour chaque regard du réseau → z_terrain IDW,
    profondeur réelle ou médiane réseau (flag `profondeur_estimee`),
    z_radier_terrain = z_terrain − profondeur.

    + statistiques de couverture et détection d'inversions amont/aval
    (z_radier amont ≤ z_radier aval) sur les conduites du GPKG.
    """
    import pandas as pd

    profondeurs = []
    regards = {}
    for _, r in regards_gdf.iterrows():
        codes = _normaliser_code_regard([r.get("Code")])
        code = codes[0] if len(codes) else ""
        if not code:
            continue
        try:
            prof = float(r.get("Profondeur")) if pd.notna(r.get("Profondeur")) else None
        except (TypeError, ValueError):
            prof = None
        if prof is not None and prof > 0:
            profondeurs.append(prof)
        regards[code] = {"profondeur": prof}

    med = _mediane(profondeurs)
    par_code = (artefact or {}).get("regards") or {}
    meta = (artefact or {}).get("meta") or {}

    par_regard: Dict[str, Any] = {}
    stats_conf: Dict[str, int] = {"haute": 0, "moyenne": 0, "faible": 0, "aucune": 0}
    nb_terrain = 0
    nb_prof_reelle = 0
    nb_prof_estimee = 0

    for code, info in regards.items():
        rt = par_code.get(code) or {}
        zt = rt.get("z_terrain_m")
        conf = rt.get("confiance") or "aucune"
        stats_conf[conf] = stats_conf.get(conf, 0) + 1
        if zt is None:
            continue
        nb_terrain += 1
        prof = info["profondeur"]
        if prof is not None:
            nb_prof_reelle += 1
            prof_utilisee = prof
            estimee = False
        else:
            nb_prof_estimee += 1
            prof_utilisee = med
            estimee = True
        z_rad = (round(float(zt) - float(prof_utilisee), 3)
                 if prof_utilisee is not None else None)
        par_regard[code] = {
            "z_terrain_m": float(zt),
            "confiance": conf,
            "profondeur_m": round(float(prof_utilisee), 3) if prof_utilisee is not None else None,
            "profondeur_estimee": estimee,
            "z_radier_terrain_m": z_rad,
        }

    # Inversions amont→aval sur les conduites : le radier amont devrait
    # être strictement plus haut que le radier aval (écoulement gravitaire).
    inversions = []
    _lignes_canas = canalisations_gdf.iterrows() if canalisations_gdf is not None else []
    for _, c in _lignes_canas:
        us = _normaliser_code_regard([c.get("ID_AMONT")])
        vs = _normaliser_code_regard([c.get("ID_AVAL")])
        u, v = (us[0] if us else ""), (vs[0] if vs else "")
        ru, rv = par_regard.get(u), par_regard.get(v)
        if not ru or not rv:
            continue
        za, zv = ru.get("z_radier_terrain_m"), rv.get("z_radier_terrain_m")
        if za is None or zv is None:
            continue
        if za <= zv:
            inversions.append({
                "amont": u, "aval": v,
                "z_radier_amont": za, "z_radier_aval": zv,
                "ecart_m": round(zv - za, 3),
            })

    total = len(regards)
    pct = round(100.0 * nb_terrain / total, 1) if total else 0.0

    return {
        "statut": "ok",
        "gpkg_sha256": meta.get("gpkg_sha256"),
        "resolution_m": meta.get("resolution_m"),
        "utm_epsg": meta.get("utm_epsg"),
        "couverture": {
            "total_regards": total,
            "avec_terrain": nb_terrain,
            "pct": pct,
            "par_confiance": stats_conf,
        },
        "profondeur": {
            "nb_reelles": nb_prof_reelle,
            "nb_estimees": nb_prof_estimee,
            "mediane_reseau_m": round(med, 3) if med is not None else None,
        },
        "inversions_amont_aval": {
            "nb": len(inversions),
            "echantillon": inversions[:20],
        },
        "eligible_injection_95": bool(total and pct >= SEUIL_COUVERTURE_INP * 100),
        "par_regard": par_regard,
        "avertissement": (
            "Cotes radier estimées = terrain IDW − profondeur (réelle ou médiane "
            "réseau). Terrain interpolé ≠ mesure : à valider avant injection .inp."
        ),
    }


def apercu_elevations_terrain(db, org_id: str, project_id: str, layer_id: str) -> Dict[str, Any]:
    """
    IO : charge l'artefact regards_terrain de la couche, vérifie
    l'estampillage SHA-256 vs le GPKG projet courant, lit regards +
    canalisations et délègue à `calculer_apercu_terrain`.
    """
    from api.models import Project, ProjectAuxLayer
    from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet_avec_meta

    couche = db.query(ProjectAuxLayer).filter(
        ProjectAuxLayer.id == layer_id,
        ProjectAuxLayer.project_id == project_id,
        ProjectAuxLayer.org_id == org_id,
    ).first()
    if couche is None:
        return {"statut": "absent", "raison": "Couche introuvable."}
    if couche.type != "altimetrie_points" or couche.statut != "ok":
        return {"statut": "ignore",
                "raison": "La couche n'est pas une altimétrie opérationnelle."}

    artefact = charger_regards_terrain(org_id, project_id, layer_id)
    if not artefact:
        return {"statut": "absent",
                "raison": "Aucun artefact regards_terrain — lancez le recalcul."}

    project = db.query(Project).filter(
        Project.id == project_id, Project.org_id == org_id
    ).first()
    gpkg_path, meta_v = resoudre_gpkg_effectif_pour_projet_avec_meta(db, project)
    sha_courant = (meta_v or {}).get("sha256")
    if not sha_courant and gpkg_path:
        try:
            from api.services.gpkg_versions import sha256_fichier
            sha_courant = sha256_fichier(Path(gpkg_path))
        except Exception:
            sha_courant = None
    sha_artefact = ((artefact.get("meta") or {}).get("gpkg_sha256"))
    if sha_courant and sha_artefact and sha_courant != sha_artefact:
        return {
            "statut": "perime",
            "raison": "L'artefact a été calculé sur une autre version du réseau "
                       "— recalcul requis avant tout usage.",
            "gpkg_sha256_courant": sha_courant,
            "gpkg_sha256_artefact": sha_artefact,
        }
    if gpkg_path is None:
        return {"statut": "absent", "raison": "Aucun GPKG projet résolu."}

    try:
        couches = gpd.list_layers(str(gpkg_path))["name"].tolist()
        nom_regards = next((l for l in couches if "regard" in l.lower()), None)
        nom_canas = next(
            (l for l in couches
             if any(k in l.lower() for k in ["canalisat", "conduit", "pipe", "troncon"])
             and "désaffect" not in l.lower() and "desaffect" not in l.lower()),
            None,
        )
        if nom_regards is None:
            return {"statut": "absent", "raison": "Couche 'regards' absente du GPKG."}
        regards_gdf = gpd.read_file(str(gpkg_path), layer=nom_regards)
        canas_gdf = (gpd.read_file(str(gpkg_path), layer=nom_canas)
                     if nom_canas else None)
    except Exception as e:
        return {"statut": "erreur", "raison": f"Lecture GPKG impossible : {e}"}

    res = calculer_apercu_terrain(regards_gdf, canas_gdf, artefact)
    res["layer_id"] = layer_id
    res["layer_nom"] = couche.nom
    return res


# ---------------------------------------------------------------------------
# P1 — suspects de sens d'écoulement (SHP.md §8)
# ---------------------------------------------------------------------------
#
# Trois signaux par conduite, jamais de verdict automatique :
#   1. terrain : z_terrain(aval) > z_terrain(amont) → le terrain MONTE le
#      long du sens d'écoulement supposé (pente_contre = écart/longueur) ;
#   2. radier estimé : z_radier_terrain(aval) > z_radier_terrain(amont)
#      (signal plus faible : la profondeur injectée lisse une partie du bruit) ;
#   3. azimut : la plus forte descente du terrain (azimut_pente_deg de
#      l'artefact) s'oppose au cap de la conduite — seulement si la pente
#      locale est significative (sinon le bruit domine).
#
# Le classement alimente une FILE DE REVUE — aucune correction n'est
# appliquée sans validation utilisateur (règle SHP.md : jamais de snap
# automatique).

PENTE_INVERSION_FORT_PCT = 1.0     # terrain monte > 1 % le long du flux
PENTE_INVERSION_MOYEN_PCT = 0.3    # ... > 0,3 %
PENTE_LOCALE_MIN_AZIMUT_PCT = 1.0  # en dessous, l'azimut n'est pas probant
ECART_AZIMUT_OPPOSE_DEG = 120.0
SEUIL_CONFIANCE_AZIMUT = {"haute", "moyenne"}


def _longueur_conduite_m(c) -> float:
    """Longueur de la conduite en mètres (attribut SIG prioritaire)."""
    import pandas as pd
    for col in ("Longeur", "LONGUEUR", "Longueur", "LINEAIRE", "length", "Length"):
        if col in c and pd.notna(c.get(col)):
            try:
                v = float(c.get(col))
                if v > 0:
                    return v
            except (TypeError, ValueError):
                continue
    # Repli : distance à vol d'oiseau entre extrémités (approx. locale)
    try:
        geom = c.geometry
        if geom is not None and not geom.is_empty and len(geom.coords) >= 2:
            (x1, y1), (x2, y2) = geom.coords[0], geom.coords[-1]
            lat_m = np.radians((y1 + y2) / 2.0)
            dx = (x2 - x1) * 111320.0 * np.cos(lat_m)
            dy = (y2 - y1) * 110540.0
            return float(np.hypot(dx, dy))
    except Exception:
        pass
    return 0.0


def _cap_conduite_deg(c) -> Optional[float]:
    """Cap (azimut horaire depuis le Nord) de la conduite, ou None."""
    try:
        geom = c.geometry
        if geom is None or geom.is_empty or len(geom.coords) < 2:
            return None
        (x1, y1), (x2, y2) = geom.coords[0], geom.coords[-1]
        dx = (x2 - x1) * np.cos(np.radians((y1 + y2) / 2.0))
        dy = y2 - y1
        if dx == 0 and dy == 0:
            return None
        return float((np.degrees(np.arctan2(dx, dy)) + 360.0) % 360.0)
    except Exception:
        return None


def _ecart_angulaire(a: float, b: float) -> float:
    """Écart angulaire minimal en degrés entre deux azimuts [0,360)."""
    d = abs((a - b) % 360.0)
    return min(d, 360.0 - d)


def _pire_confiance(c1: str, c2: str) -> str:
    ordre = {"haute": 0, "moyenne": 1, "faible": 2, "aucune": 3}
    return c1 if ordre.get(c1, 3) >= ordre.get(c2, 3) else c2


def analyser_ecoulement_terrain(regards_gdf, canalisations_gdf, artefact) -> Dict[str, Any]:
    """
    Calcul PUR : file de revue des conduites dont le sens d'écoulement
    supposé (ID_AMONT → ID_AVAL) est suspect au regard du terrain.
    Réutilise `calculer_apercu_terrain` pour les cotes radier estimées.
    """
    apercu = calculer_apercu_terrain(regards_gdf, canalisations_gdf, artefact)
    par_regard = apercu.get("par_regard") or {}
    par_code_art = (artefact or {}).get("regards") or {}

    suspects = []
    nb_analysées = 0
    _lignes = canalisations_gdf.iterrows() if canalisations_gdf is not None else []
    for _, c in _lignes:
        us = _normaliser_code_regard([c.get("ID_AMONT")])
        vs = _normaliser_code_regard([c.get("ID_AVAL")])
        u = us[0] if us else ""
        v = vs[0] if vs else ""
        if not u or not v or u == v:
            continue
        ru, rv = par_regard.get(u), par_regard.get(v)
        if not ru or not rv:
            continue
        zt_a, zt_v = ru.get("z_terrain_m"), rv.get("z_terrain_m")
        if zt_a is None or zt_v is None:
            continue
        longueur = _longueur_conduite_m(c)
        if longueur <= 0:
            continue
        nb_analysées += 1

        # Signal 1 — terrain : écart positif = le terrain MONTE le long du flux
        dz_terr = round(float(zt_v) - float(zt_a), 3)
        pente_contre = round(100.0 * dz_terr / longueur, 3)

        # Signal 2 — radier estimé (profondeur lisse une partie du bruit)
        zr_a, zr_v = ru.get("z_radier_terrain_m"), rv.get("z_radier_terrain_m")
        dz_rad = round(float(zr_v) - float(zr_a), 3) if (zr_a is not None and zr_v is not None) else None

        # Signal 3 — azimut de plus forte descente vs cap de la conduite
        cap = _cap_conduite_deg(c)
        art_u = par_code_art.get(u) or {}
        art_v = par_code_art.get(v) or {}
        azimut = art_u.get("azimut_pente_deg")
        pente_loc = art_u.get("pente_terrain_pct")
        conf_u, conf_v = ru.get("confiance") or "aucune", rv.get("confiance") or "aucune"
        ecart_azimut = None
        if cap is not None and azimut is not None and conf_u in SEUIL_CONFIANCE_AZIMUT:
            ecart_azimut = round(_ecart_angulaire(cap, float(azimut)), 1)

        motifs = []
        score = 0
        if dz_terr > 0:
            if pente_contre >= PENTE_INVERSION_FORT_PCT:
                motifs.append(f"terrain monte de {dz_terr} m le long du flux "
                              f"({pente_contre} % > {PENTE_INVERSION_FORT_PCT} %)")
                score += 3
            elif pente_contre >= PENTE_INVERSION_MOYEN_PCT:
                motifs.append(f"terrain monte de {dz_terr} m le long du flux "
                              f"({pente_contre} %)")
                score += 2
            else:
                motifs.append(f"léger relèvement terrain ({dz_terr} m, {pente_contre} %) — probable bruit")
                score += 1
        if dz_rad is not None and dz_rad > 0:
            motifs.append(f"radier estimé aval plus haut de {dz_rad} m")
            score += 1
        if (ecart_azimut is not None and ecart_azimut > ECART_AZIMUT_OPPOSE_DEG
                and (pente_loc or 0) >= PENTE_LOCALE_MIN_AZIMUT_PCT):
            motifs.append(f"plus forte descente du terrain à {ecart_azimut:.0f}° "
                          f"du cap de la conduite (pente locale {pente_loc} %)")
            score += 2

        if score <= 0:
            continue

        severite = "fort" if score >= 4 else ("moyen" if score >= 2 else "faible")
        suspects.append({
            "amont": u,
            "aval": v,
            "longueur_m": round(longueur, 1),
            "z_terrain_amont": zt_a,
            "z_terrain_aval": zt_v,
            "ecart_terrain_m": dz_terr,
            "pente_contre_pct": pente_contre,
            "z_radier_amont": zr_a,
            "z_radier_aval": zr_v,
            "ecart_radier_m": dz_rad,
            "cap_conduite_deg": round(cap, 1) if cap is not None else None,
            "azimut_pente_amont_deg": azimut,
            "pente_terrain_amont_pct": pente_loc,
            "ecart_azimut_deg": ecart_azimut,
            "confiance": _pire_confiance(conf_u, conf_v),
            "lng_amont": art_u.get("lng"), "lat_amont": art_u.get("lat"),
            "lng_aval": art_v.get("lng"), "lat_aval": art_v.get("lat"),
            "score": score,
            "severite": severite,
            "motifs": motifs,
        })

    suspects.sort(key=lambda s: (-s["score"], -abs(s["pente_contre_pct"])))
    par_sev = {"fort": 0, "moyen": 0, "faible": 0}
    for s in suspects:
        par_sev[s["severite"]] += 1

    return {
        "statut": "ok",
        "nb_conduites_analysées": nb_analysées,
        "nb_suspects": len(suspects),
        "par_severite": par_sev,
        "suspects": suspects[:300],
        "meta_artefact": {
            "gpkg_sha256": ((artefact or {}).get("meta") or {}).get("gpkg_sha256"),
            "resolution_m": ((artefact or {}).get("meta") or {}).get("resolution_m"),
            "nb_regards": ((artefact or {}).get("meta") or {}).get("nb_regards"),
        },
        "avertissement": (
            "File de revue indicative : le terrain IDW (±1–2 m) produit des "
            "relèvements sur terrain plat — chaque suspect doit être recoupé "
            "avec le sens d'écoulement supposé et les profils radier avant "
            "toute correction. Aucune modification automatique n'est appliquée."
        ),
    }


def _charger_contexte_altimetrie(db, org_id: str, project_id: str, layer_id: str):
    """
    IO commun aux analyses P1/P2 : résout couche + artefact regards_terrain
    (estampillage SHA-256) + GPKG projet. Retourne
    (erreur_dict_ou_None, couche, regards_gdf, canas_gdf, artefact).
    """
    from api.models import Project, ProjectAuxLayer
    from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet_avec_meta

    couche = db.query(ProjectAuxLayer).filter(
        ProjectAuxLayer.id == layer_id,
        ProjectAuxLayer.project_id == project_id,
        ProjectAuxLayer.org_id == org_id,
    ).first()
    if couche is None:
        return {"statut": "absent", "raison": "Couche introuvable."}, None, None, None, None
    if couche.type != "altimetrie_points" or couche.statut != "ok":
        return {"statut": "ignore",
                "raison": "Analyse réservée aux couches altimétrie opérationnelles."}, None, None, None, None

    artefact = charger_regards_terrain(org_id, project_id, layer_id)
    if not artefact:
        return {"statut": "absent",
                "raison": "Aucun artefact regards_terrain — recalcul requis."}, None, None, None, None

    project = db.query(Project).filter(
        Project.id == project_id, Project.org_id == org_id
    ).first()
    gpkg_path, meta_v = resoudre_gpkg_effectif_pour_projet_avec_meta(db, project)
    sha_courant = (meta_v or {}).get("sha256")
    if not sha_courant and gpkg_path:
        try:
            from api.services.gpkg_versions import sha256_fichier
            sha_courant = sha256_fichier(Path(gpkg_path))
        except Exception:
            sha_courant = None
    sha_artefact = ((artefact.get("meta") or {}).get("gpkg_sha256"))
    if sha_courant and sha_artefact and sha_courant != sha_artefact:
        return {"statut": "perime",
                "raison": "Artefact calculé sur une autre version du réseau."}, None, None, None, None
    if gpkg_path is None:
        return {"statut": "absent", "raison": "Aucun GPKG projet résolu."}, None, None, None, None

    try:
        couches = gpd.list_layers(str(gpkg_path))["name"].tolist()
        nom_regards = next((l for l in couches if "regard" in l.lower()), None)
        nom_canas = next(
            (l for l in couches
             if any(k in l.lower() for k in ["canalisat", "conduit", "pipe", "troncon"])
             and "désaffect" not in l.lower() and "desaffect" not in l.lower()),
            None,
        )
        if nom_regards is None or nom_canas is None:
            return {"statut": "absent", "raison": "Couches regards/canalisations absentes."}, None, None, None, None
        regards_gdf = gpd.read_file(str(gpkg_path), layer=nom_regards)
        canas_gdf = gpd.read_file(str(gpkg_path), layer=nom_canas)
    except Exception as e:
        return {"statut": "erreur", "raison": f"Lecture GPKG impossible : {e}"}, None, None, None, None

    return None, couche, regards_gdf, canas_gdf, artefact


def analyser_ecoulement_projet(db, org_id: str, project_id: str, layer_id: str) -> Dict[str, Any]:
    """
    IO : charge couche + artefact + GPKG projet, délègue à
    `analyser_ecoulement_terrain`. Mêmes gardes que l'aperçu .inp
    (estampillage SHA-256, statut couche, artefact présent).
    """
    err, couche, regards_gdf, canas_gdf, artefact = _charger_contexte_altimetrie(
        db, org_id, project_id, layer_id)
    if err is not None:
        return err

    res = analyser_ecoulement_terrain(regards_gdf, canas_gdf, artefact)
    res["layer_id"] = layer_id
    res["layer_nom"] = couche.nom
    return res


# ---------------------------------------------------------------------------
# P2 — candidats de raccordement pour regards orphelins (SHP.md §9)
# ---------------------------------------------------------------------------

RACCORDEMENT_RAYON_DEFAUT_M = 50.0
RACCORDEMENT_TOP_K = 3
RACCORDEMENT_MAX_ORPHELINS = 800


def _coordonnees_regards_m(regards_gdf, artefact) -> Dict[str, Tuple[float, float]]:
    """
    code normalisé → (x, y) en mètres. Réutilise le CRS de la couche ;
    si la couche est en degrés (EPSG:4326), projette vers l'UTM de
    l'artefact (`meta.utm_epsg`).
    """
    epsg_cible = None
    try:
        epsg_cible = int(((artefact or {}).get("meta") or {}).get("utm_epsg") or 0) or None
    except (TypeError, ValueError):
        epsg_cible = None

    src_crs = getattr(regards_gdf, "crs", None)
    g = regards_gdf
    if src_crs is not None and epsg_cible:
        try:
            if src_crs.to_epsg() == 4326 and src_crs.to_epsg() != epsg_cible:
                g = regards_gdf.to_crs(epsg_cible)
        except Exception:
            pass

    out: Dict[str, Tuple[float, float]] = {}
    for _, r in g.iterrows():
        codes = _normaliser_code_regard([r.get("Code")])
        code = codes[0] if codes else ""
        if not code:
            continue
        geom = r.geometry
        if geom is None:
            continue
        try:
            out[code] = (float(geom.x), float(geom.y))
        except Exception:
            continue
    return out


def _azimut_vers(x1: float, y1: float, x2: float, y2: float) -> float:
    """Azimut horaire depuis le Nord [0,360) du segment p1 → p2 (plan UTM)."""
    dx, dy = x2 - x1, y2 - y1
    return (np.degrees(np.arctan2(dx, dy)) + 360.0) % 360.0


def _score_raccordement(dist_m: float, rayon_m: float, zt_o, zt_c,
                        zr_o, zr_c, cap_azimut: Optional[float],
                        azimut_descente, conf_orphelin: str) -> Tuple[float, List[str]]:
    """
    Score 0–100 + motifs explicites pour un candidat orphelin → cible
    (sens proposé : l'orphelin se raccorde EN AMONT de la cible).
    """
    motifs: List[str] = []
    score = 40.0 * max(0.0, 1.0 - dist_m / rayon_m)  # proximité : 0–40
    motifs.append(f"distance {dist_m:.1f} m")

    # Terrain : le flux proposé orphelin→cible exige z_terrain qui descend
    if zt_o is not None and zt_c is not None:
        dz = zt_c - zt_o
        if dz < -0.3:
            score += 30.0
            motifs.append(f"terrain descend de {-dz:.2f} m vers la cible")
        elif dz <= 0.3:
            score += 5.0
            motifs.append("terrain quasi horizontal (±0,3 m)")
        else:
            score -= 25.0
            motifs.append(f"terrain remonte de {dz:.2f} m vers la cible — sens à vérifier")

    # Radier estimé : gravitaire exige radier amont > radier aval
    if zr_o is not None and zr_c is not None:
        dzr = zr_c - zr_o
        if dzr < 0:
            score += 20.0
            motifs.append(f"radier estimé cohérent ({-dzr:.2f} m de chute)")
        else:
            score -= 20.0
            motifs.append(f"radier estimé aval plus haut de {dzr:.2f} m — contre-pente probable")

    # Azimut : la cible devrait se situer vers la descente du terrain
    if (cap_azimut is not None and azimut_descente is not None
            and conf_orphelin in SEUIL_CONFIANCE_AZIMUT):
        ecart = _ecart_angulaire(cap_azimut, float(azimut_descente))
        if ecart <= 60.0:
            score += 10.0
            motifs.append(f"cible dans l'axe de descente du terrain (écart {ecart:.0f}°)")
        elif ecart >= 120.0:
            score -= 10.0
            motifs.append(f"cible opposée à la descente du terrain (écart {ecart:.0f}°)")

    return max(0.0, min(100.0, score)), motifs


def analyser_raccordements_terrain(regards_gdf, canalisations_gdf, artefact,
                                   rayon_max_m: float = RACCORDEMENT_RAYON_DEFAUT_M,
                                   top_k: int = RACCORDEMENT_TOP_K) -> Dict[str, Any]:
    """
    Calcul PUR : pour chaque regard orphelin (aucune conduite amont/aval),
    propose les `top_k` nœuds connectés les plus proches dans `rayon_max_m`
    et les classe par score altimétrique. File de revue — aucune écriture.
    """
    from scipy.spatial import cKDTree
    import pandas as pd

    apercu = calculer_apercu_terrain(regards_gdf, canalisations_gdf, artefact)
    par_regard = apercu.get("par_regard") or {}
    par_code_art = (artefact or {}).get("regards") or {}

    # Ensemble des codes connectés (extrémités de conduites)
    connectes = set()
    for _, c in (canalisations_gdf.iterrows() if canalisations_gdf is not None else []):
        for col in ("ID_AMANT", "ID_AVAL"):
            codes = _normaliser_code_regard([c.get(col)])
            if codes:
                connectes.update(codes)

    coords = _coordonnees_regards_m(regards_gdf, artefact)

    # Infos par code : coords + cotes issues de l'aperçu + azimut artefact
    infos: Dict[str, Dict[str, Any]] = {}
    for code, xy in coords.items():
        rt = par_regard.get(code)
        if not rt or rt.get("z_terrain_m") is None:
            continue
        art = par_code_art.get(code) or {}
        infos[code] = {
            "x": xy[0], "y": xy[1],
            "z_terrain_m": rt.get("z_terrain_m"),
            "z_radier_terrain_m": rt.get("z_radier_terrain_m"),
            "confiance": rt.get("confiance") or "aucune",
            "azimut_pente_deg": art.get("azimut_pente_deg"),
            "pente_terrain_pct": art.get("pente_terrain_pct"),
            "lng": art.get("lng"), "lat": art.get("lat"),
        }

    orphelins = {c: i for c, i in infos.items() if c not in connectes}
    cibles = {c: i for c, i in infos.items() if c in connectes}

    if not orphelins or not cibles:
        return {
            "statut": "ok",
            "nb_orphelins": len(orphelins),
            "nb_candidats": 0,
            "orphelins": [],
            "avertissement": "Aucun regard orphelin exploitable ou aucune cible connectée.",
        }

    # Arbre spatial sur les cibles connectées
    codes_cibles = sorted(cibles.keys())
    xy_cibles = np.array([[cibles[c]["x"], cibles[c]["y"]] for c in codes_cibles])
    arbre = cKDTree(xy_cibles)

    resultats = []
    nb_analyses = 0
    codes_orphelins = sorted(orphelins.keys())
    for code in codes_orphelins[:RACCORDEMENT_MAX_ORPHELINS]:
        o = orphelins[code]
        dist, idx = arbre.query([o["x"], o["y"]], k=min(top_k * 4, len(codes_cibles)))
        candidats = []
        for d, i in zip(np.atleast_1d(dist), np.atleast_1d(idx)):
            if d > rayon_max_m:
                continue
            cible = codes_cibles[int(i)]
            ci = cibles[cible]
            azimut_cap = _azimut_vers(o["x"], o["y"], ci["x"], ci["y"])
            score, motifs = _score_raccordement(
                float(d), rayon_max_m,
                o["z_terrain_m"], ci["z_terrain_m"],
                o["z_radier_terrain_m"], ci["z_radier_terrain_m"],
                azimut_cap, o.get("azimut_pente_deg"), o.get("confiance") or "aucune")
            candidats.append({
                "cible": cible,
                "distance_m": round(float(d), 1),
                "score": round(score, 1),
                "z_terrain_cible_m": ci["z_terrain_m"],
                "ecart_terrain_m": (round(ci["z_terrain_m"] - o["z_terrain_m"], 3)
                                    if ci["z_terrain_m"] is not None and o["z_terrain_m"] is not None else None),
                "confiance_cible": ci.get("confiance"),
                "lng_cible": ci.get("lng"), "lat_cible": ci.get("lat"),
                "motifs": motifs,
            })
            if len(candidats) >= top_k:
                break
        nb_analyses += 1
        resultats.append({
            "orphelin": code,
            "lng": o.get("lng"), "lat": o.get("lat"),
            "z_terrain_m": o.get("z_terrain_m"),
            "confiance": o.get("confiance"),
            "candidats": sorted(candidats, key=lambda x: -x["score"]),
        })

    resultats.sort(key=lambda r: (
        -(r["candidats"][0]["score"] if r["candidats"] else -1)))
    avec_candidats = sum(1 for r in resultats if r["candidats"])

    return {
        "statut": "ok",
        "nb_orphelins": len(orphelins),
        "nb_orphelins_analyses": nb_analyses,
        "nb_avec_candidats": avec_candidats,
        "rayon_max_m": rayon_max_m,
        "orphelins": resultats[:RACCORDEMENT_MAX_ORPHELINS],
        "avertissement": (
            "Propositions indicatives classées par cohérence altimétrique "
            "(proximité, descente du terrain, radier estimé, azimut). "
            "Aucune connexion n'est créée automatiquement — validation "
            "hydraulique requise avant toute modification du réseau."
        ),
    }


def analyser_raccordements_projet(db, org_id: str, project_id: str, layer_id: str,
                                  rayon_max_m: float = RACCORDEMENT_RAYON_DEFAUT_M) -> Dict[str, Any]:
    """IO : même contexte que P1, délègue à `analyser_raccordements_terrain`."""
    err, couche, regards_gdf, canas_gdf, artefact = _charger_contexte_altimetrie(
        db, org_id, project_id, layer_id)
    if err is not None:
        return err

    res = analyser_raccordements_terrain(regards_gdf, canas_gdf, artefact,
                                         rayon_max_m=rayon_max_m)
    res["layer_id"] = layer_id
    res["layer_nom"] = couche.nom
    return res


# ---------------------------------------------------------------------------
# Option C — résolution des cotes radier « terrain » pour injection .inp
# ---------------------------------------------------------------------------

def resoudre_elevations_terrain_pour_simulation(
    db, org_id: str, project_id: str, layer_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Option C (SHP.md §7bis) — produit le dict {nid: z_radier} injectable
    dans le .inp quand l'utilisateur demande explicitement le mode
    « altimétrie terrain ». Garde-fous actés :
      - artefact présent et NON périmé (SHA-256 GPKG)
      - couverture ≥ 95 % (eligible_injection_95) sinon refus explicite
      - profondeurs manquantes → médiane réseau (flag provenance)
      - exutoire traité comme les autres nœuds
    Retourne {"statut": "ok", "elevations": {...}, "meta": {...}} ou
    {"statut": <raison>, ...} — l'appelant décide du refus (422).
    """
    from api.models import ProjectAuxLayer
    from src.domain.moteur_swmm.constants import _clean_node_id

    if layer_id:
        couche = db.query(ProjectAuxLayer).filter(
            ProjectAuxLayer.id == layer_id,
            ProjectAuxLayer.project_id == project_id,
            ProjectAuxLayer.org_id == org_id,
        ).first()
        if couche is None:
            return {"statut": "absent", "raison": "Couche altimétrie introuvable."}
    else:
        couche = db.query(ProjectAuxLayer).filter(
            ProjectAuxLayer.project_id == project_id,
            ProjectAuxLayer.org_id == org_id,
            ProjectAuxLayer.type == "altimetrie_points",
            ProjectAuxLayer.statut == "ok",
        ).order_by(ProjectAuxLayer.created_at.desc()).first()
        if couche is None:
            return {"statut": "absent",
                    "raison": "Aucune couche altimétrie opérationnelle sur ce projet."}

    err, _couche, regards_gdf, canas_gdf, artefact = _charger_contexte_altimetrie(
        db, org_id, project_id, couche.id)
    if err is not None:
        return err

    apercu = calculer_apercu_terrain(regards_gdf, canas_gdf, artefact)
    if not apercu.get("eligible_injection_95"):
        return {
            "statut": "couverture_insuffisante",
            "raison": (f"Couverture terrain {apercu.get('couverture', {}).get('pct', 0)} % "
                       f"< 95 % requis — repli sur le datum synthétique."),
            "apercu": apercu,
        }

    elevations: Dict[str, float] = {}
    nb_estimees = 0
    bruts: Dict[str, Tuple[float, bool]] = {}
    for code, info in (apercu.get("par_regard") or {}).items():
        zr = info.get("z_radier_terrain_m")
        if zr is None:
            continue
        nid = _clean_node_id(code)
        if not nid:
            continue
        bruts[nid] = (round(float(zr), 3), bool(info.get("profondeur_estimee")))

    # Garde-fou plausibilité : l'IDW peut extrapoler des cotes aberrantes
    # en bordure d'emprise (ex. z_radier < 0 ou > 3×MAD du médian).
    # Ces nœuds sont traités comme « non couverts » → estimation par
    # voisinage dans _resoudre_altimetrie_noeuds, jamais injectés tels quels.
    nb_hors_plage = 0
    if bruts:
        _vals = np.array([v[0] for v in bruts.values()], dtype="float64")
        _med = float(np.median(_vals))
        _mad = float(np.median(np.abs(_vals - _med))) or 1.0
        _seuil = max(80.0, 6.0 * _mad)
        for nid, (z, estimee) in bruts.items():
            if z < 0.0 or abs(z - _med) > _seuil:
                nb_hors_plage += 1
                continue
            elevations[nid] = z
            if estimee:
                nb_estimees += 1

    if not elevations:
        return {"statut": "absent", "raison": "Aucune cote radier terrain exploitable."}

    meta_art = (artefact or {}).get("meta") or {}
    return {
        "statut": "ok",
        "elevations": elevations,
        "meta": {
            "layer_id": couche.id,
            "layer_nom": couche.nom,
            "resolution_m": meta_art.get("resolution_m"),
            "gpkg_sha256": meta_art.get("gpkg_sha256"),
            "couverture_pct": (apercu.get("couverture") or {}).get("pct"),
            "nb_cotes": len(elevations),
            "nb_profondeurs_estimees": nb_estimees,
            "nb_hors_plage_terrain": nb_hors_plage,
            "profondeur_mediane_m": (apercu.get("profondeur") or {}).get("mediane_reseau_m"),
        },
    }
