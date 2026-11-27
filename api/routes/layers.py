# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Endpoint /api/v1/layers : couches GeoJSON avec cache et snapshots (extrait de api/main.py)
================================================================================
"""

import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import Project
from api.core.security import require_role, TenantContext

router = APIRouter()


_LAYERS_CACHE = {}
_GDF_CACHE = {}

def clean_nan(obj):
    if isinstance(obj, float) and math.isnan(obj):
        return None
    elif isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan(v) for v in obj]
    elif isinstance(obj, tuple):
        return tuple(clean_nan(v) for v in obj)
    return obj

def _has_bounds(ne_lat, ne_lng, sw_lat, sw_lng):
    return None not in (ne_lat, ne_lng, sw_lat, sw_lng)

def reset_layers_cache():
    global _LAYERS_CACHE, _GDF_CACHE
    _LAYERS_CACHE = {}
    _GDF_CACHE = {}

@router.get("/api/v1/layers")
def get_layers(
    request: Request,
    ne_lat: Optional[float] = None,
    ne_lng: Optional[float] = None,
    sw_lat: Optional[float] = None,
    sw_lng: Optional[float] = None,
    snapshot: Optional[str] = None,
    project_id: Optional[str] = None,
    ctx: TenantContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db),
):
    """
    Retourne les données GeoJSON des couches du réseau pour le projet actif de l'organisation.
    Si aucun fichier de réseau n'est associé au projet, retourne un espace vierge (Option B).

    `snapshot` (optionnel) : gpkg_version_id ou préfixe sha256 d'une version
    archivée du MÊME projet — permet de consulter une simulation sur le réseau
    qui l'a produite (jamais de substitution silencieuse : snapshot inconnu
    → 404). Absent → version courante, comportement historique inchangé.
    `project_id` (optionnel) : explicite le projet quand l'organisation en a
    plusieurs (sinon repli sur le comportement historique).
    """
    global _LAYERS_CACHE, _GDF_CACHE
    has_bounds = _has_bounds(ne_lat, ne_lng, sw_lat, sw_lng)

    empty_response = {
        "statut": "ok",
        "is_empty": True,
        "project_name": "Nouveau Projet (Espace vierge)",
        "compteurs": {
            "conduites": 0, "regards": 0, "stations": 0, "step": 0, "ouvrages": 0, "rejets": 0
        },
        "couches": {
            "conduites": {"type": "FeatureCollection", "features": []},
            "regards": {"type": "FeatureCollection", "features": []},
            "stations": {"type": "FeatureCollection", "features": []},
            "step": {"type": "FeatureCollection", "features": []},
            "ouvrages": {"type": "FeatureCollection", "features": []},
            "rejets": {"type": "FeatureCollection", "features": []}
        }
    }

    # Détermination du fichier GeoPackage pour le projet actif (strictement cloisonné par org_id)
    from api.services.gpkg_versions import (
        resoudre_snapshot_pour_lecture, GpkgSimulationError)
    gpkg_target = None
    snap_meta = None
    project_name = "Nouveau Projet"
    cache_org_id = ctx.org_id
    cache_project_id = "none"

    query = db.query(Project).filter(
        Project.org_id == ctx.org_id,
        Project.is_archived.is_(False)
    )
    if project_id:
        query = query.filter(Project.id == project_id)
    project = query.first()

    if project:
        project_name = project.name
        cache_project_id = project.id
        try:
            snap_ctx = resoudre_snapshot_pour_lecture(db, project, snapshot)
            gpkg_target = snap_ctx["path"]
            snap_meta = snap_ctx
        except GpkgSimulationError:
            # Snapshot explicite demandé mais introuvable/hors projet :
            # stealth 404, jamais de repli sur la version courante.
            if snapshot:
                raise HTTPException(status_code=404, detail="Ressource introuvable")
            # Aucun fichier associé au projet courant -> espace vierge (Option B)
            gpkg_target = None

    # Le client reçoit toujours la métadonnée du snapshot réellement servi :
    # c'est la clé de vérification INV-2 (sha256) côté frontend.
    snap_payload = None
    if snap_meta:
        snap_payload = {
            "version_id": snap_meta.get("version_id"),
            "sha256": snap_meta.get("sha256"),
            "est_version_courante": snap_meta.get("est_version_courante"),
            "libelle": snap_meta.get("libelle"),
            "nb_regards": snap_meta.get("nb_regards"),
            "nb_conduites": snap_meta.get("nb_conduites"),
        }

    def _with_snapshot(payload: dict) -> dict:
        if snap_payload:
            return {**payload, "snapshot": snap_payload}
        return payload

    if not gpkg_target:
        empty_response["project_name"] = project_name
        return _with_snapshot(empty_response)

    # Clé de cache content-adressée : org + projet + SHA-256 du GPKG —
    # deux versions ne partagent jamais leurs données cartographiques.
    cache_key = str(gpkg_target)
    try:
        from api.services.gpkg_versions import sha256_fichier
        empreinte = sha256_fichier(gpkg_target)[:16]
        cache_key = f"{cache_org_id}|{cache_project_id}|{empreinte}"
    except Exception:
        pass

    if cache_key in _LAYERS_CACHE and not has_bounds:
        res = dict(_LAYERS_CACHE[cache_key])
        res["project_name"] = project_name
        res["is_empty"] = False
        return _with_snapshot(res)

    if cache_key in _GDF_CACHE and has_bounds:
        result = {"statut": "ok", "is_empty": False, "project_name": project_name, "couches": {}, "compteurs": {}}
        for key, gdf in _GDF_CACHE[cache_key].items():
            if not gdf.empty:
                filtered_gdf = gdf.cx[sw_lng:ne_lng, sw_lat:ne_lat]
                import json
                geojson = json.loads(filtered_gdf.to_json(na="drop"))
                result["couches"][key] = geojson
                result["compteurs"][key] = len(geojson.get('features', []))
            else:
                result["couches"][key] = {"type": "FeatureCollection", "features": []}
                result["compteurs"][key] = 0
        return _with_snapshot(result)

    # Construction du cache pour ce GeoPackage
    import geopandas as gpd

    result = {"statut": "ok", "is_empty": False, "project_name": project_name, "couches": {}, "compteurs": {}}
    gdf_cache_temp = {}
    WGS84 = "EPSG:4326"

    KEYWORDS = {
        'conduites': 'canalisations',
        'regards': 'regards',
        'stations': 'station_de_relevage',
        'step': 'step',
        'ouvrages': 'ouvrages_speciaux',
        'rejets': 'rejets'
    }

    try:
        layers = gpd.list_layers(gpkg_target)['name'].tolist()
    except Exception as e:
        print(f"[ERROR] Impossible de lister les couches de {gpkg_target}: {e}")
        return _with_snapshot(empty_response)

    for key, motcle in KEYWORDS.items():
        layer_name = next((l for l in layers if motcle.lower() in l.lower()), None)
        if not layer_name:
            result["couches"][key] = {"type": "FeatureCollection", "features": []}
            result["compteurs"][key] = 0
            gdf_cache_temp[key] = gpd.GeoDataFrame()
            continue

        try:
            gdf = gpd.read_file(gpkg_target, layer=layer_name)
            if gdf.crs and gdf.crs != WGS84:
                gdf = gpd.GeoDataFrame(gdf, geometry=gdf.geometry.to_crs(WGS84))

            _ = gdf.sindex
            gdf_cache_temp[key] = gdf

            if has_bounds and not gdf.empty:
                gdf_to_export = gdf.cx[sw_lng:ne_lng, sw_lat:ne_lat]
            else:
                gdf_to_export = gdf

            import json
            geojson = json.loads(gdf_to_export.to_json(na="drop"))
            result["couches"][key] = geojson
            result["compteurs"][key] = len(geojson.get('features', []))
        except Exception as e:
            print(f"[ERROR] {key}: {e}")
            result["couches"][key] = {"type": "FeatureCollection", "features": []}
            result["compteurs"][key] = 0
            gdf_cache_temp[key] = gpd.GeoDataFrame()

    # Calcul de la bounding box globale du réseau (WGS84 [lat_min, lon_min], [lat_max, lon_max])
    total_bounds = None
    for gdf in gdf_cache_temp.values():
        if not gdf.empty:
            b = gdf.total_bounds
            if total_bounds is None:
                total_bounds = [float(b[0]), float(b[1]), float(b[2]), float(b[3])]
            else:
                total_bounds[0] = min(total_bounds[0], float(b[0]))
                total_bounds[1] = min(total_bounds[1], float(b[1]))
                total_bounds[2] = max(total_bounds[2], float(b[2]))
                total_bounds[3] = max(total_bounds[3], float(b[3]))
    if total_bounds:
        result["bbox"] = [[total_bounds[1], total_bounds[0]], [total_bounds[3], total_bounds[2]]]

    _GDF_CACHE[cache_key] = gdf_cache_temp
    if not has_bounds:
        _LAYERS_CACHE[cache_key] = result

    return _with_snapshot(result)




# ============================================================
# PAGES HTML
# ============================================================
