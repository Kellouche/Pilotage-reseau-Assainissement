# -*- coding: utf-8 -*-
"""
================================================================================
Service des couches SIG « satellite » — SHP.md
================================================================================
Indépendance totale : ces couches ne sont JAMAIS fusionnées dans le GPKG
projet, jamais lues par le pipeline SWMM/.inp, jamais sources d'écriture
dans les tables réseau (Canalisation, Regard, Simulation).

Formats d'entrée acceptés : .shp (avec ses sidecars .shx/.dbf/.prj/.cpg
présents dans le même dossier), .gpkg, .geojson/.json, .zip (contenant un
jeu .shp complet). Un .shp sans sidecars est refusé.
Sortie interne : GPKG mono-couche stocké via ArtifactStore (clé
org/projet/gis/aux_layers/{layer_id}/layer.gpkg).
================================================================================
"""

import json
import logging
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import geopandas as gpd
from shapely.geometry import shape

from api.core.storage import ArtifactStore, get_storage

logger = logging.getLogger(__name__)

WGS84 = "EPSG:4326"

TYPES_VALIDES = {
    "altimetrie_points",
    "bv_officiel",
    "metrologie",
    "autre",
}

EXTENSIONS_ACCEPTEES = {".gpkg", ".geojson", ".json", ".zip", ".shp"}
SIDECARS_SHP_REQUIS = (".shx", ".dbf")
TAILLE_MAX_OCTETS = 200 * 1024 * 1024  # 200 Mo
NB_FEATURES_MAX_SANS_BOUNDS = 20000


def cle_couche_aux(org_id: str, project_id: str, layer_id: str, nom_fichier: str) -> str:
    """Clé ArtifactStore : org/projet/gis/aux_layers/{layer_id}/{nom_fichier}."""
    return ArtifactStore.build_key(org_id, project_id, f"gis/aux_layers/{layer_id}/{nom_fichier}")


def _store() -> ArtifactStore:
    return get_storage()


def _resolver_entree(path: Path) -> Tuple[Path, Optional[Path]]:
    """
    Résout le fichier source à lire.
    Retourne (chemin_effectif, dossier_temp_a_nettoyer).
    Pour un .zip : extrait dans un dossier temporaire et retourne le .shp/.gpkg/.geojson trouvé.
    """
    if path.suffix.lower() != ".zip":
        return path, None

    tmp = Path(tempfile.mkdtemp(prefix="aux_layer_zip_"))
    try:
        with zipfile.ZipFile(path) as zf:
            # Garde-fou zip-slip
            for info in zf.infolist():
                cible = (tmp / info.filename).resolve()
                if not str(cible).startswith(str(tmp.resolve())):
                    raise ValueError("Archive zip invalide (chemin suspect).")
            zf.extractall(tmp)
    except zipfile.BadZipFile as e:
        raise ValueError(f"Archive .zip invalide : {e}")

    candidats = [
        p for p in tmp.rglob("*")
        if p.suffix.lower() in {".shp", ".gpkg", ".geojson", ".json"}
        and not p.name.lower().endswith((".cpg",))
    ]
    # .shp prioritaire si présent (cas nominal des exports SIG)
    shps = [p for p in candidats if p.suffix.lower() == ".shp"]
    if shps:
        if len(shps) > 1:
            raise ValueError(
                "L'archive contient plusieurs jeux .shp : importez-les un par un."
            )
        return shps[0], tmp
    gpkg = [p for p in candidats if p.suffix.lower() == ".gpkg"]
    if gpkg:
        if len(gpkg) > 1:
            raise ValueError("L'archive contient plusieurs .gpkg : importez-les un par un.")
        return gpkg[0], tmp
    if candidats:
        return candidats[0], tmp
    raise ValueError("Archive .zip sans fichier SIG exploitable (.shp/.gpkg/.geojson).")


def _lire_gdf(chemin: Path) -> gpd.GeoDataFrame:
    """Lit un fichier SIG en GeoDataFrame."""
    suffixe = chemin.suffix.lower()
    if suffixe == ".shp":
        gdf = gpd.read_file(chemin)
    elif suffixe == ".gpkg":
        couches = gpd.list_layers(chemin)["name"].tolist()
        couches_data = [c for c in couches if c.lower() not in ("gpkg_contents", "gpkg_geometry_columns", "gpkg_tile_matrix", "gpkg_tile_matrix_set")]
        # Exclut aussi les tables log_* éventuelles
        couches_data = [c for c in couches_data if not c.lower().startswith("log_")]
        if not couches_data:
            raise ValueError("GeoPackage sans couche de données.")
        gdf = gpd.read_file(chemin, layer=couches_data[0])
    else:
        gdf = gpd.read_file(chemin)
    if gdf.empty:
        raise ValueError("Couche vide : aucune entité géographique.")
    return gdf


def _normaliser_4326(gdf: gpd.GeoDataFrame) -> Tuple[gpd.GeoDataFrame, Optional[str]]:
    """Reprojette en EPSG:4326 et retourne (gdf, crs_source)."""
    crs_source = str(gdf.crs) if gdf.crs else None
    if gdf.crs is None:
        raise ValueError("CRS indéterminé : impossible de garantir la cohérence spatiale.")
    if str(gdf.crs) != WGS84:
        gdf = gpd.GeoDataFrame(gdf, geometry=gdf.geometry.to_crs(WGS84), crs=WGS84)
    return gdf, crs_source


def importer_couche_aux(
    db,
    org_id: str,
    project_id: str,
    type_couche: str,
    nom: str,
    fichier_path: Path,
    fichier_nom: str,
    colonne_z: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Importe un fichier SIG satellite pour un projet.

    Retourne le dict de la couche créée (ProjectAuxLayer.to_dict()).
    Lève ValueError avec un message utilisateur en cas de donnée invalide.
    """
    from api.models import ProjectAuxLayer, Project

    if type_couche not in TYPES_VALIDES:
        raise ValueError(f"Type de couche invalide : {type_couche!r}. Attendu : {sorted(TYPES_VALIDES)}")

    project = db.query(Project).filter(
        Project.id == project_id, Project.org_id == org_id
    ).first()
    if not project:
        raise ValueError("Projet introuvable pour cette organisation.")

    suffixe = fichier_path.suffix.lower()
    if suffixe not in EXTENSIONS_ACCEPTEES:
        raise ValueError(
            f"Format non supporté ({suffixe}). Formats acceptés : .shp (avec "
            "sidecars), .gpkg, .geojson ou .zip."
        )
    if suffixe == ".shp":
        manquants = [s for s in SIDECARS_SHP_REQUIS
                     if not fichier_path.with_suffix(s).exists()]
        if manquants:
            raise ValueError(
                "Shapefile incomplet : sidecars manquants "
                f"({', '.join(manquants)}). Sélectionnez le .shp avec tous ses "
                "sidecars (.shx .dbf .prj .cpg) ou compressez-les en .zip."
            )
    if fichier_path.stat().st_size > TAILLE_MAX_OCTETS:
        raise ValueError("Fichier trop volumineux (limite 200 Mo).")

    chemin_effectif, tmp_dir = _resolver_entree(fichier_path)
    try:
        gdf = _lire_gdf(chemin_effectif)
    finally:
        if tmp_dir:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    gdf, crs_source = _normaliser_4326(gdf)

    # Métadonnées
    minx, miny, maxx, maxy = gdf.total_bounds
    emprise = {
        "minx": round(float(minx), 6),
        "miny": round(float(miny), 6),
        "maxx": round(float(maxx), 6),
        "maxy": round(float(maxy), 6),
    }
    geom_type = str(gdf.geom_type.iloc[0]) if len(gdf) else None
    # Type de géométrie dominant
    if gdf.geom_type.nunique() > 1:
        geom_type = gdf.geom_type.mode().iloc[0]
    attributs = [str(c) for c in gdf.columns if c != "geometry"]

    # Identité de la couche (UUID déterministe côté service)
    from api.models import _gen_uuid
    layer_id = _gen_uuid()

    # Écriture GPKG mono-couche dans un fichier temporaire puis ArtifactStore
    store = _store()
    with tempfile.TemporaryDirectory(prefix="aux_layer_") as td:
        gpkg_tmp = Path(td) / "layer.gpkg"
        # Nom de couche générique et sûr
        gdf_out = gpd.GeoDataFrame(gdf.copy(), geometry="geometry", crs=WGS84)
        gdf_out.to_file(gpkg_tmp, driver="GPKG", layer="data")

        cle = cle_couche_aux(org_id, project_id, layer_id, "layer.gpkg")
        store.put_file(cle, gpkg_tmp)

    # Copie de la source brute pour traçabilité (optionnelle, même clé prefixée)
    try:
        cle_src = cle_couche_aux(org_id, project_id, layer_id, "source" + fichier_path.suffix.lower())
        store.put_file(cle_src, fichier_path)
    except Exception as e:
        logger.warning("Copie source satellite non stockée (%s) : %s", layer_id, e)

    couche = ProjectAuxLayer(
        id=layer_id,
        org_id=org_id,
        project_id=project_id,
        # Rattachement à la version GPKG du réseau courant : la couche
        # n'est visible que tant que ce réseau est chargé.
        gpkg_version_id=getattr(project, "gpkg_version_id", None),
        type=type_couche,
        nom=nom or fichier_nom,
        fichier_source=fichier_nom,
        storage_key=cle,
        crs_source=crs_source,
        geom_type=geom_type,
        emprise=emprise,
        nb_features=len(gdf),
        attributs=attributs,
        colonne_z=colonne_z,
        statut="ok",
    )
    db.add(couche)
    db.commit()
    db.refresh(couche)
    return couche.to_dict()


# ---------------------------------------------------------------------------
# Lecture / matérialisation
# ---------------------------------------------------------------------------

_CACHE_MATERIALISE: Dict[str, Path] = {}


def _chemin_materialise(layer_id: str, storage_key: str) -> Path:
    """Matérialise le GPKG satellite dans un cache local (comme gpkg_versions)."""
    if layer_id in _CACHE_MATERIALISE:
        p = _CACHE_MATERIALISE[layer_id]
        if p.exists():
            return p

    cache_dir = Path("data/.aux_layers_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cible = cache_dir / f"{layer_id}.gpkg"
    if not cible.exists():
        tmp = cache_dir / f"{layer_id}.tmp.gpkg"
        try:
            _store().get_file(storage_key, tmp)
            tmp.replace(cible)
        except Exception:
            if tmp.exists():
                tmp.unlink()
            raise
    _CACHE_MATERIALISE[layer_id] = cible
    return cible


def supprimer_artefacts_couche(org_id: str, project_id: str, layer_id: str) -> int:
    """Purge tous les artefacts stockés d'une couche satellite.

    Couvre layer.gpkg, la copie source et les dérivés (derive/grid.npz,
    derive/regards_terrain.json) — tous sous gis/aux_layers/{layer_id}/.
    Purge aussi le cache local matérialisé. Retourne le nb d'objets
    supprimés du store (0 si indisponible)."""
    _CACHE_MATERIALISE.pop(layer_id, None)
    cache_dir = Path("data/.aux_layers_cache")
    if cache_dir.exists():
        for p in cache_dir.glob(f"{layer_id}*"):
            try:
                p.unlink()
            except OSError:
                pass
    prefix = ArtifactStore.build_key(org_id, project_id, f"gis/aux_layers/{layer_id}/")
    try:
        return _store().delete_prefix(prefix)
    except Exception as e:
        logger.warning("Purge artefacts couche satellite %s : %s", layer_id, e)
        return 0


def lire_gdf_couche(layer_id: str, storage_key: str, bounds: Optional[Tuple[float, float, float, float]] = None) -> gpd.GeoDataFrame:
    """Lit la couche satellite (avec filtre d'emprise optionnel en EPSG:4326)."""
    chemin = _chemin_materialise(layer_id, storage_key)
    gdf = gpd.read_file(chemin, layer="data")
    if bounds is not None:
        minx, miny, maxx, maxy = bounds
        gdf = gdf.cx[minx:maxx, miny:maxy]
    return gdf


def geojson_couche(
    layer_id: str,
    storage_key: str,
    nb_features: int,
    bounds: Optional[Tuple[float, float, float, float]] = None,
) -> Dict[str, Any]:
    """Produit le FeatureCollection GeoJSON borné de la couche."""
    if bounds is None and nb_features > NB_FEATURES_MAX_SANS_BOUNDS:
        raise ValueError(
            f"Couche trop volumineuse ({nb_features} entités) : précisez le paramètre "
            "bounds=minx,miny,maxx,maxy."
        )
    gdf = lire_gdf_couche(layer_id, storage_key, bounds)
    return json.loads(gdf.to_json(na="drop"))
