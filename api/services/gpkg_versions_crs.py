# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Detection et application du CRS des GeoPackage (pyproj, SRS declares) (extrait de services/gpkg_versions.py)
================================================================================
"""

import sqlite3
from pathlib import Path
from typing import Optional, Union

import logging

logger = logging.getLogger(__name__)


_SRS_ID_UNDEFINED = {0, -1, 99999}


def _srs_ids_declares(conn) -> set:
    """srs_id réellement déclarés dans gpkg_geometry_columns (hors sentinelles)."""
    return {r[0] for r in conn.execute(
        "SELECT srs_id FROM gpkg_geometry_columns")
        if r[0] is not None and r[0] not in _SRS_ID_UNDEFINED}


def detecter_crs_gpkg(path: Union[str, Path]) -> Optional[str]:
    """
    Retourne le CRS déclaré par les couches du GeoPackage (ex. "EPSG:32631"),
    ou None si aucune couche ne déclare de système de coordonnées.
    Lecture seule — aucune modification du fichier.
    """
    path = Path(path)
    conn = None
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "gpkg_geometry_columns" not in tables:
            return None
        declares = sorted(_srs_ids_declares(conn))
        if not declares:
            return None
        if declares:
            # Résolution EPSG via gpkg_spatial_ref_sys si disponible
            if "gpkg_spatial_ref_sys" in tables:
                for sid in declares:
                    row = conn.execute(
                        "SELECT organization_coordsys_id FROM gpkg_spatial_ref_sys "
                        "WHERE srs_id = ? AND organization = 'EPSG'", (sid,)
                    ).fetchone()
                    if row:
                        return f"EPSG:{row[0]}"
            return f"EPSG:{declares[0]}"
        return None
    except sqlite3.Error:
        return None
    finally:
        if conn is not None:
            conn.close()


def appliquer_crs_gpkg(path: Union[str, Path], crs_input: str) -> str:
    """
    Déclare `crs_input` (code EPSG, "EPSG:XXXX", WKT ou PROJ) sur toutes les
    couches du GeoPackage qui n'ont pas de CRS (srs_id <= 0, NULL ou 99999
    « Undefined SRS » GDAL).

    Retourne le code EPSG normalisé (ex. "EPSG:32631").
    Lève ValueError si l'entrée n'est pas résolvable en EPSG.
    """
    from pyproj import CRS
    from pyproj.exceptions import CRSError

    try:
        crs = CRS.from_user_input(crs_input)
    except CRSError as e:
        raise ValueError(
            f"Projection invalide ou non reconnue : {crs_input!r} ({e}). "
            "Fournissez un code EPSG (ex. EPSG:32631)."
        )
    epsg = crs.to_epsg()
    if epsg is None:
        raise ValueError(
            f"Projection non convertible en code EPSG : {crs_input!r}. "
            "Fournissez un code EPSG explicite (ex. EPSG:32631)."
        )

    path = Path(path)
    conn = sqlite3.connect(str(path))
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "gpkg_geometry_columns" not in tables:
            raise ValueError("Fichier sans couches géométriques (gpkg_geometry_columns absent).")
        if "gpkg_spatial_ref_sys" in tables:
            conn.execute(
                "INSERT OR REPLACE INTO gpkg_spatial_ref_sys "
                "(srs_name, srs_id, organization, organization_coordsys_id, "
                " definition, description) VALUES (?, ?, 'EPSG', ?, ?, NULL)",
                (f"EPSG:{epsg}", epsg, epsg, crs.to_wkt()),
            )
        conn.execute(
            "UPDATE gpkg_geometry_columns SET srs_id = ? "
            "WHERE srs_id IS NULL OR srs_id <= 0 OR srs_id = 99999",
            (epsg,),
        )
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        raise ValueError(f"Impossible d'écrire le CRS dans le GeoPackage : {e}")
    finally:
        conn.close()
    return f"EPSG:{epsg}"


# ---------------------------------------------------------------------------
# Clés de stockage &ArtifactStore
# ---------------------------------------------------------------------------
