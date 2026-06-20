"""
Routes pour l'intégration MNT/DEM et analyse de bassins versants.
Expose les fonctionnalités d'extraction de courbes de niveau et
de comparaison avec les bassins topologiques.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict, Any, Optional
import os
import logging
from datetime import datetime

from src.domain.contour_workflow import (
    harmoniser_crs,
    determiner_aire_etude,
    generer_contours,
    clipper_contours,
    exporter_contours
)
from src.domain.extracteur_contours import extract_contours_from_dem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mnt", tags=["MNT / DEM"])

# Cache pour les résultats MNT
_cache_mnt = {
    "contours": None,
    "aire_etude": None,
    "timestamp": None,
    "duree_validite": 3600  # 1 heure
}


@router.post("/analyser-bassins")
async def analyser_bassins_mnt(
    dem_path: str,
    contour_interval: float = 10.0,
    force_refresh: bool = False
):
    """
    Analyse les bassins versants à partir d'un fichier DEM (MNT).

    - **dem_path**: Chemin vers le fichier DEM TIFF
    - **contour_interval**: Intervalle des courbes de niveau en mètres (défaut 10.0)
    - **force_refresh**: Force un recalcul même si le cache est valide
    """
    global _cache_mnt

    maintenant = datetime.now().timestamp()

    # Vérifier le cache
    if (not force_refresh and
        _cache_mnt["contours"] is not None and
        _cache_mnt["timestamp"] is not None and
        (maintenant - _cache_mnt["timestamp"]) < _cache_mnt["duree_validite"]):

        logger.info("Utilisation du cache MNT")
        return {
            "source": "cache",
            "contours": _cache_mnt["contours"],
            "aire_etude": _cache_mnt["aire_etude"],
            "date_analyse": datetime.fromtimestamp(_cache_mnt["timestamp"]).isoformat()
        }

    # Vérifier que le fichier DEM existe
    if not os.path.exists(dem_path):
        raise HTTPException(
            status_code=404,
            detail=f"Fichier DEM introuvable: {dem_path}"
        )

    try:
        logger.info(f"Analyse MNT/DEM: {dem_path}")

        # Étape 1: Extraire les contours directement depuis le DEM
        contours_gdf = extract_contours_from_dem(
            dem_path=dem_path,
            contour_interval=contour_interval,
            output_format='geojson'
        )

        # Étape 2: Déterminer l'aire d'étude (pour l'instant, utiliser les bounds du DEM)
        # Dans une version future, on croisera avec les couches réseau
        from shapely.geometry import box
        import geopandas as gpd
        import rasterio

        with rasterio.open(dem_path) as src:
            bounds = src.bounds
            aire_etude = gpd.GeoDataFrame(
                {'id': [1], 'geometry': [box(bounds.left, bounds.bottom, bounds.right, bounds.top)]},
                crs=str(src.crs)
            )

        # Étape 3: Clipper les contours à l'aire d'étude
        contours_clipped = clipper_contours(contours_gdf, aire_etude)

        # Convertir en GeoJSON pour la réponse API
        contours_geojson = contours_clipped.__geo_interface__

        resultat = {
            "source": "nouvelle_analyse",
            "date_analyse": datetime.now().isoformat(),
            "dem_path": dem_path,
            "contour_interval": contour_interval,
            "aire_etude": {
                "crs": str(aire_etude.crs),
                "bounds": aire_etude.total_bounds.tolist(),
                "surface_m2": float(
                    (aire_etude.total_bounds[2] - aire_etude.total_bounds[0]) *
                    (aire_etude.total_bounds[3] - aire_etude.total_bounds[1])
                )
            },
            "contours": contours_geojson,
            "statistiques": {
                "nb_contours": len(contours_clipped),
                "niveaux_uniques": sorted(contours_clipped['level'].unique().tolist()) if 'level' in contours_clipped.columns else [],
                "altitude_min": float(contours_clipped['level'].min()) if len(contours_clipped) > 0 else None,
                "altitude_max": float(contours_clipped['level'].max()) if len(contours_clipped) > 0 else None
            }
        }

        # Mettre en cache
        _cache_mnt["contours"] = contours_geojson
        _cache_mnt["aire_etude"] = resultat["aire_etude"]
        _cache_mnt["timestamp"] = maintenant

        logger.info(f"Analyse MNT terminée: {len(contours_clipped)} contours générés")
        return resultat

    except Exception as e:
        logger.error(f"Erreur analyse MNT: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de l'analyse MNT: {str(e)}"
        )


@router.get("/cache/status")
async def get_cache_mnt_status():
    """
    Vérifie l'état du cache d'analyse MNT.
    """
    global _cache_mnt

    maintenant = datetime.now().timestamp()

    if _cache_mnt["timestamp"] is None:
        status_cache = "vide"
        age_secondes = None
    else:
        age_secondes = maintenant - _cache_mnt["timestamp"]
        if age_secondes < _cache_mnt["duree_validite"]:
            status_cache = "valide"
        else:
            status_cache = "expire"

    return {
        "status_cache": status_cache,
        "age_cache_secondes": age_secondes,
        "duree_validite_secondes": _cache_mnt["duree_validite"],
        "derniere_mise_a_jour": datetime.fromtimestamp(_cache_mnt["timestamp"]).isoformat() if _cache_mnt["timestamp"] else None,
        "analyse_disponible": _cache_mnt["contours"] is not None
    }


@router.delete("/cache")
async def clear_cache_mnt():
    """
    Vide le cache d'analyse MNT.
    """
    global _cache_mnt

    _cache_mnt["contours"] = None
    _cache_mnt["aire_etude"] = None
    _cache_mnt["timestamp"] = None

    return {"message": "Cache MNT vidé"}


@router.get("/statut")
async def get_mnt_statut():
    """
    Vérifie la disponibilité des outils MNT/DEM.
    """
    dependances = {
        "rasterio": False,
        "geopandas": False,
        "numpy": False,
        "skimage": False
    }

    try:
        import rasterio
        dependances["rasterio"] = True
    except ImportError:
        pass

    try:
        import geopandas
        dependances["geopandas"] = True
    except ImportError:
        pass

    try:
        import numpy
        dependances["numpy"] = True
    except ImportError:
        pass

    try:
        import skimage
        dependances["skimage"] = True
    except ImportError:
        pass

    return {
        "dependances": dependances,
        "pret": all(dependances.values()),
        "message": "Tous les outils MNT sont disponibles" if all(dependances.values()) else "Certains outils MNT sont manquants"
    }
