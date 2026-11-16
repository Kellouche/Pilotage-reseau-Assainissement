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
from typing import Any, Dict, Optional, Tuple

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
