# -*- coding: utf-8 -*-
"""
Extraction par pochoir (SHP.md — outil SIG).

Découpe le réseau projet et/ou les couches SIG satellites par un polygone
« pochoir » et produit un livrable zip :
  - un .shp par thème  ({nom}_regard.shp, {nom}_conduite.shp, …)
  - un .gpkg fusionnant tous les thèmes + le polygone pochoir
    (traçabilité de la zone extraite)
  - un manifeste JSON (comptages par thème)

Règle spatiale actée : INTERSECTION — un objet qui touche la zone est
extrait ENTIER (pas de découpe de géométrie ; la traçabilité prime).

Indépendance : lecture seule du GPKG projet et des couches satellites ;
aucune écriture dans les tables réseau ni le pipeline SWMM.
"""

import json
import logging
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon, shape
from sqlalchemy.orm import Session

from api.core.storage import ArtifactStore, get_storage
from api.models import Project, ProjectAuxLayer
from api.services.aux_layers_service import lire_gdf_couche
from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet

logger = logging.getLogger(__name__)

WGS84 = "EPSG:4326"

# Thème canonique par nom de couche GPKG projet (singulier, nom de fichier)
_THEMES_RESEAU = {
    "regards": "regard",
    "canalisations": "conduite",
    "conduites": "conduite",
    "rejets": "rejet",
    "sous_bassins": "sous_bassin",
    "bassins": "bassin",
}


def _slug(nom: str) -> str:
    """Nom de fichier/couche sûr : minuscules, accents retirés, _-only."""
    import unicodedata
    s = unicodedata.normalize("NFKD", str(nom))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()
    return s or "couche"


_UUID_SUFFIX = re.compile(
    r"_[0-9a-f]{8}_[0-9a-f]{4}_[0-9a-f]{4}_[0-9a-f]{4}_[0-9a-f]{12}$")


def _theme_reseau(layer_name: str) -> str:
    """Thème canonique : retire le suffixe UUID des couches GPKG projet
    (canalisations_860f298d_… → conduite) et gère les variantes
    (canalisations_desaffecte → conduite_desaffecte)."""
    cle = _slug(layer_name)
    cle = _UUID_SUFFIX.sub("", cle)
    if cle in _THEMES_RESEAU:
        return _THEMES_RESEAU[cle]
    for prefix, theme in _THEMES_RESEAU.items():
        if cle.startswith(prefix + "_"):
            suffixe = cle[len(prefix) + 1:]
            return f"{theme}_{suffixe}"
    return cle


def _valider_polygone(geojson_geom: Dict[str, Any]) -> Polygon:
    """Valide le polygone pochoir (GeoJSON Polygon/MultiPolygon, EPSG:4326)."""
    if not isinstance(geojson_geom, dict):
        raise ValueError("géométrie du pochoir invalide (objet GeoJSON attendu).")
    try:
        geom = shape(geojson_geom)
    except Exception as e:
        raise ValueError(f"géométrie du pochoir illisible : {e}")
    if geom.is_empty or not geom.is_valid:
        raise ValueError("géométrie du pochoir vide ou invalide.")
    if geom.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("le pochoir doit être un polygone (Polygon/MultiPolygon).")
    return geom


def _gdf_en_4326(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        gdf = gdf.set_crs(WGS84)
    elif str(gdf.crs) != WGS84:
        gdf = gdf.to_crs(WGS84)
    return gdf


def _filtrer(gdf: gpd.GeoDataFrame, pochoir: Polygon) -> gpd.GeoDataFrame:
    """Objets intersectant le pochoir, géométrie conservée entière."""
    if gdf.empty:
        return gdf
    return gdf[gdf.geometry.notna() & gdf.intersects(pochoir)].copy()


def _fusionner_par_theme(entrees: List[Tuple[str, gpd.GeoDataFrame]]
                         ) -> List[Tuple[str, gpd.GeoDataFrame]]:
    """Regroupe les gdf par thème en une seule couche par thème.

    Plusieurs couches sources peuvent mapper sur le même thème
    (canalisations + conduites → conduite) : on les concatène pour
    produire un unique {nom}_conduite.shp / couche gpkg 'conduite'.
    Si un thème mélange des types de géométrie (le shapefile n'en
    supporte qu'un), on éclate en sous-couches theme_<type>."""
    par_theme: Dict[str, List[gpd.GeoDataFrame]] = {}
    ordre: List[str] = []
    for theme, gdf in entrees:
        if theme not in par_theme:
            par_theme[theme] = []
            ordre.append(theme)
        par_theme[theme].append(gdf)

    resultat: List[Tuple[str, gpd.GeoDataFrame]] = []
    for theme in ordre:
        gdfs = par_theme[theme]
        if len(gdfs) == 1:
            resultat.append((theme, gdfs[0]))
            continue
        try:
            fusion = gpd.GeoDataFrame(
                pd.concat(gdfs, ignore_index=True), crs=WGS84)
        except Exception as e:
            logger.warning("[pochoir] fusion thème %s impossible (%s) — couches séparées", theme, e)
            resultat.extend((theme, g) for g in gdfs)
            continue
        types_geom = {str(t) for t in fusion.geometry.geom_type.unique()}
        if len(types_geom) <= 1:
            resultat.append((theme, fusion))
        else:
            _court = {"point": "point", "linestring": "line",
                      "polygon": "polygone", "multipoint": "points",
                      "multilinestring": "lines", "multipolygon": "polygones"}
            for gt, sous in fusion.groupby(fusion.geometry.geom_type):
                suffixe = _court.get(str(gt).lower(), str(gt).lower())
                resultat.append((f"{theme}_{suffixe}", sous))
    return resultat


def _prep_gdf_ecriture(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Colonnes à renommer avant écriture GPKG : 'fid' est le nom
    réservé de la clé primaire GeoPackage — une colonne attribut
    'fid' fait échouer to_file ('Error adding field fid') et laisse
    une couche vide dans gpkg_contents."""
    if "fid" in gdf.columns:
        if "fid_attribut" in gdf.columns:
            gdf = gdf.drop(columns=["fid"])
        else:
            gdf = gdf.rename(columns={"fid": "fid_attribut"})
    return gdf


def _ecrire_shp(gdf: gpd.GeoDataFrame, chemin_shp: Path) -> List[Path]:
    """Écrit un shapefile (shp+shx+dbf+prj+…) et retourne les fichiers créés.
    Le chemin DOIT finir par .shp : sans extension, GDAL crée un dossier
    dataset et les fichiers tombent un niveau plus bas."""
    if chemin_shp.suffix.lower() != ".shp":
        chemin_shp = chemin_shp.with_suffix(".shp")
    gdf.to_file(str(chemin_shp), driver="ESRI Shapefile")
    base = chemin_shp.with_suffix("")
    return sorted(chemin_shp.parent.glob(base.name + ".*"))


def extraire_par_pochoir(
    db: Session,
    org_id: str,
    project_id: str,
    nom: str,
    geojson_geom: Dict[str, Any],
    inclure_reseau: bool = True,
    aux_layer_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Extrait le réseau projet et/ou des couches satellites par pochoir.

    Retourne {statut, cle_zip, nom_zip, manifeste, stats} — le zip est
    déposé dans l'ArtifactStore sous gis/extractions/{eid}/.
    """
    projet = db.query(Project).filter(
        Project.id == project_id, Project.org_id == org_id,
        Project.is_archived.is_(False),
    ).first()
    if not projet:
        raise ValueError("Projet introuvable pour cette organisation.")

    pochoir = _valider_polygone(geojson_geom)
    nom_propre = (nom or "extraction").strip() or "extraction"
    nom_base = _slug(nom_propre)

    gpkg_path = resoudre_gpkg_effectif_pour_projet(db, projet)
    if inclure_reseau and gpkg_path is None:
        raise ValueError("Aucun réseau chargé : impossible d'extraire le projet.")

    stats: Dict[str, int] = {}
    themes: List[Tuple[str, gpd.GeoDataFrame]] = []  # (theme_slug, gdf filtré)

    # ---------------------------------------------------------------
    # 1. Couches du réseau projet (GPKG courant)
    # ---------------------------------------------------------------
    if inclure_reseau and gpkg_path is not None:
        couches = gpd.list_layers(str(gpkg_path))["name"].tolist()
        for layer_name in couches:
            try:
                gdf = gpd.read_file(str(gpkg_path), layer=layer_name)
            except Exception as e:
                logger.warning("[pochoir] couche réseau illisible %s : %s", layer_name, e)
                continue
            if not isinstance(gdf, gpd.GeoDataFrame):
                continue  # table non spatiale (log_*) — pas de géométrie
            gdf = _gdf_en_4326(gdf)
            extrait = _filtrer(gdf, pochoir)
            theme = _theme_reseau(layer_name)
            cle_stat = f"reseau_{theme}"
            stats[cle_stat] = stats.get(cle_stat, 0) + len(extrait)
            if len(extrait):
                themes.append((theme, extrait))

    # ---------------------------------------------------------------
    # 2. Couches SIG satellites demandées (isolation org + version GPKG)
    # ---------------------------------------------------------------
    if aux_layer_ids:
        vid = getattr(projet, "gpkg_version_id", None)
        for lid in aux_layer_ids:
            q = db.query(ProjectAuxLayer).filter(
                ProjectAuxLayer.id == lid,
                ProjectAuxLayer.project_id == project_id,
                ProjectAuxLayer.org_id == org_id,
            )
            q = q.filter(
                ProjectAuxLayer.gpkg_version_id.is_(None) if vid is None
                else ProjectAuxLayer.gpkg_version_id == vid
            )
            couche = q.first()
            if couche is None:
                continue  # hors version courante → invisible, ignorée
            try:
                gdf = _gdf_en_4326(lire_gdf_couche(couche.id, couche.storage_key))
            except Exception as e:
                logger.warning("[pochoir] couche satellite illisible %s : %s", lid, e)
                continue
            extrait = _filtrer(gdf, pochoir)
            theme = f"sat_{_slug(couche.nom)}"
            cle_stat = f"sat_{theme[4:]}"
            stats[cle_stat] = stats.get(cle_stat, 0) + len(extrait)
            if len(extrait):
                themes.append((theme, extrait))

    # Un thème = une couche en sortie (fusion des sources homonymes)
    themes = _fusionner_par_theme(themes)

    # ---------------------------------------------------------------
    # 3. Assemblage : shp par thème + gpkg fusionné + manifeste → zip
    # ---------------------------------------------------------------
    from api.models import _gen_uuid
    eid = _gen_uuid()
    prefixe_store = f"gis/extractions/{eid}"

    with tempfile.TemporaryDirectory(prefix="pochoir_") as td:
        td_path = Path(td)
        fichiers_zip: List[Tuple[str, Path]] = []
        gpkg_sortie = td_path / f"{nom_base}.gpkg"
        noms_utilises: Dict[str, int] = {}

        # Le polygone pochoir en premier : traçabilité de la zone
        gdf_pochoir = gpd.GeoDataFrame(
            {"type": ["pochoir"], "nom": [nom_propre]},
            geometry=[pochoir], crs=WGS84,
        )
        premier = True
        for theme, gdf in [("pochoir", gdf_pochoir)] + themes:
            # Nom de couche unique dans le gpkg
            base_nom = _slug(theme)
            n = noms_utilises.get(base_nom, 0)
            noms_utilises[base_nom] = n + 1
            nom_couche = base_nom if n == 0 else f"{base_nom}_{n + 1}"
            try:
                gdf = _prep_gdf_ecriture(gdf)
                if gdf.crs is None:
                    gdf = gdf.set_crs(WGS84)
                gdf.to_file(str(gpkg_sortie), layer=nom_couche, driver="GPKG",
                            mode="w" if premier else "a")
                premier = False
            except Exception as e:
                logger.warning("[pochoir] couche gpkg %s non écrite : %s", nom_couche, e)
                continue

        # Shapefiles thématiques (hors pochoir : un shp de polygone
        # unique n'apporte rien — il est dans le gpkg)
        for theme, gdf in themes:
            shp_base = td_path / f"{nom_base}_{theme}.shp"
            try:
                _ecrire_shp(_prep_gdf_ecriture(gdf), shp_base)
            except Exception as e:
                logger.warning("[pochoir] shp %s non écrit : %s", theme, e)
                continue

        manifeste = {
            "nom": nom_propre,
            "date": datetime.now(timezone.utc).isoformat(),
            "pochoir": geojson_geom,
            "stats": stats,
            "couches": [t for t, _ in themes],
        }
        (td_path / "manifeste.json").write_text(
            json.dumps(manifeste, ensure_ascii=False, indent=2), encoding="utf-8")

        # Zip : tous les fichiers produits + manifeste
        zip_path = td_path / f"{nom_base}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(td_path.rglob("*")):
                if not p.is_file() or p == zip_path:
                    continue
                if p.suffix.lower() in (".shp", ".shx", ".dbf", ".prj", ".cpg", ".qix",
                                        ".sbn", ".sbx", ".gpkg", ".json"):
                    zf.write(p, arcname=p.relative_to(td_path).as_posix())

        # Dépôt ArtifactStore : org/projet/gis/extractions/{eid}/{nom}.zip
        store = get_storage()
        cle_zip = ArtifactStore.build_key(org_id, project_id, f"{prefixe_store}/{zip_path.name}")
        store.put_file(cle_zip, zip_path, content_type="application/zip")

    nb_objets = sum(stats.values())
    return {
        "statut": "ok",
        "extraction_id": eid,
        "nom_zip": zip_path.name,
        "cle_zip": cle_zip,
        "url_download": f"/api/v1/artifacts/download?key={cle_zip}&project_id={project_id}",
        "manifeste": manifeste,
        "stats": stats,
        "nb_objets": nb_objets,
    }
