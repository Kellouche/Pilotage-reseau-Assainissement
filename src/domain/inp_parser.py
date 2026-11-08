"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Parseur et lecteur de fichiers de modélisation SWMM au format .INP
================================================================================
"""

import os
import re
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union

import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon
import pyproj

logger = logging.getLogger(__name__)


def detecter_crs_coordonnees(min_x: float, min_y: float, max_x: float, max_y: float) -> str:
    """
    Détecte automatiquement le système de coordonnées de référence (CRS)
    à partir de l'emprise numérique des coordonnées du fichier .inp.
    """
    # Cas 1 : Coordonnées géographiques WGS84 (Degrés décimaux)
    if -180.0 <= min_x <= 180.0 and -90.0 <= min_y <= 90.0 and max_x <= 180.0 and max_y <= 90.0:
        return "EPSG:4326"

    # Cas 2 : Coordonnées UTM Zone 31N (Nord Algérie Centre/Ouest - Chlef, Alger, Oran)
    # X UTM typique : 200 000 à 800 000 m | Y UTM typique : 3 500 000 à 4 200 000 m
    if 100_000 <= min_x <= 900_000 and 3_000_000 <= min_y <= 4_500_000:
        return "EPSG:32631"

    # Cas 3 : Coordonnées UTM Zone 32N (Est Algérie - Constantine, Annaba)
    if 100_000 <= min_x <= 900_000 and 3_000_000 <= min_y <= 4_500_000:
        return "EPSG:32631"  # Défaut Algérie

    # Cas 4 : Coordonnées Lambert Nord Algérie (Anciennes minutes / mètres)
    if 100_000 <= min_x <= 1_200_000 and 100_000 <= min_y <= 600_000:
        return "EPSG:30731"

    # Par défaut pour l'Algérie : UTM Zone 31N
    return "EPSG:32631"


def parser_fichier_inp(inp_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Lit et parse un fichier .inp EPA SWMM standard en extrayant chaque section structurée.
    Ignore les commentaires (lignes débutant par ;) et lignes vides.
    """
    inp_path = Path(inp_path)
    if not inp_path.exists():
        raise FileNotFoundError(f"Fichier .inp introuvable : {inp_path}")

    sections: Dict[str, List[str]] = {}
    current_sec = None

    with open(inp_path, "r", encoding="utf-8", errors="ignore") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue

            # Détection d'un en-tête de section [SECTION]
            if line.startswith("[") and line.endswith("]"):
                current_sec = line[1:-1].strip().upper()
                if current_sec not in sections:
                    sections[current_sec] = []
                continue

            # Ignorer les lignes de commentaires
            if line.startswith(";"):
                continue

            if current_sec:
                sections[current_sec].append(line)

    return sections


def convertir_inp_vers_gpkg(
    inp_path: Union[str, Path],
    gpkg_output_path: Union[str, Path],
    force_crs: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convertit un fichier SWMM .inp en GeoPackage standardisé (.gpkg) pour DrainPilot.
    Couches créées :
      - canalisations (LineString)
      - regards (Point)
      - rejets (Point)
      - sous_bassins (Polygon, si présents dans l'INP)
    """
    inp_path = Path(inp_path)
    gpkg_output_path = Path(gpkg_output_path)
    gpkg_output_path.parent.mkdir(parents=True, exist_ok=True)

    sec = parser_fichier_inp(inp_path)

    # 1. Extraction des coordonnées géographiques des nœuds [COORDINATES]
    coords: Dict[str, Tuple[float, float]] = {}
    all_x, all_y = [], []
    for line in sec.get("COORDINATES", []):
        parts = line.split()
        if len(parts) >= 3:
            nid = parts[0].strip()
            try:
                x = float(parts[1])
                y = float(parts[2])
                coords[nid] = (x, y)
                all_x.append(x)
                all_y.append(y)
            except ValueError:
                continue

    # Détection automatique du CRS
    if force_crs:
        crs_code = force_crs
    elif all_x and all_y:
        crs_code = detecter_crs_coordonnees(min(all_x), min(all_y), max(all_x), max(all_y))
    else:
        crs_code = "EPSG:32631"

    # 2. Sommets intermédiaires des conduites [VERTICES]
    vertices: Dict[str, List[Tuple[float, float]]] = {}
    for line in sec.get("VERTICES", []):
        parts = line.split()
        if len(parts) >= 3:
            cid = parts[0].strip()
            try:
                x = float(parts[1])
                y = float(parts[2])
                if cid not in vertices:
                    vertices[cid] = []
                vertices[cid].append((x, y))
            except ValueError:
                continue

    # 3. Sections transversales [XSECTIONS] pour les diamètres
    diametres_mm: Dict[str, float] = {}
    formes: Dict[str, str] = {}
    for line in sec.get("XSECTIONS", []):
        parts = line.split()
        if len(parts) >= 3:
            cid = parts[0].strip()
            shape_str = parts[1].strip().upper()
            try:
                geom1 = float(parts[2])
                # En standard SWMM, pour CIRCULAR, geom1 est le diamètre en mètres (ou pieds si US)
                diametres_mm[cid] = round(geom1 * 1000.0, 1) if geom1 < 50.0 else round(geom1, 1)
                formes[cid] = shape_str
            except ValueError:
                formes[cid] = shape_str

    # 4. Junctions [JUNCTIONS] -> regards
    regards_data = []
    regards_geoms = []
    for line in sec.get("JUNCTIONS", []):
        parts = line.split()
        if len(parts) >= 2:
            nid = parts[0].strip()
            z_radier = float(parts[1]) if len(parts) > 1 else 100.0
            max_depth = float(parts[2]) if len(parts) > 2 else 2.0
            z_tn = z_radier + max_depth

            pt = None
            if nid in coords:
                pt = Point(coords[nid][0], coords[nid][1])
            else:
                pt = Point(0.0, 0.0)

            regards_geoms.append(pt)
            regards_data.append({
                "Code": nid,
                "ID": nid,
                "COTETN": round(z_tn, 3),
                "COTRAD": round(z_radier, 3),
                "Profondeur": round(max_depth, 3),
                "ACCESFERM": "Tampon Fonte",
                "FORMFERM": "Circulaire"
            })

    # Storage [STORAGE] -> Ajoutés aux regards avec type spécifique
    for line in sec.get("STORAGE", []):
        parts = line.split()
        if len(parts) >= 2:
            nid = parts[0].strip()
            z_radier = float(parts[1]) if len(parts) > 1 else 100.0
            max_depth = float(parts[2]) if len(parts) > 2 else 3.0
            z_tn = z_radier + max_depth

            pt = Point(coords[nid][0], coords[nid][1]) if nid in coords else Point(0.0, 0.0)
            regards_geoms.append(pt)
            regards_data.append({
                "Code": nid,
                "ID": nid,
                "COTETN": round(z_tn, 3),
                "COTRAD": round(z_radier, 3),
                "Profondeur": round(max_depth, 3),
                "ACCESFERM": "Bassin de stockage / Rétention",
                "FORMFERM": "Spécial"
            })

    # 5. Outfalls [OUTFALLS] -> rejets
    rejets_data = []
    rejets_geoms = []
    for line in sec.get("OUTFALLS", []):
        parts = line.split()
        if len(parts) >= 2:
            nid = parts[0].strip()
            z_out = float(parts[1]) if len(parts) > 1 else 100.0
            type_out = parts[2].strip() if len(parts) > 2 else "FREE"

            pt = Point(coords[nid][0], coords[nid][1]) if nid in coords else Point(0.0, 0.0)
            rejets_geoms.append(pt)
            rejets_data.append({
                "CODE": nid,
                "id": nid,
                "NOM": f"Exutoire {nid}",
                "COTETN": round(z_out, 3),
                "TYPE_EXUTOIRE": type_out
            })

    # 6. Conduits [CONDUITS] -> canalisations
    conduits_data = []
    conduits_geoms = []
    for line in sec.get("CONDUITS", []):
        parts = line.split()
        if len(parts) >= 4:
            cid = parts[0].strip()
            u_node = parts[1].strip()
            d_node = parts[2].strip()
            try:
                length_m = float(parts[3])
            except ValueError:
                length_m = 50.0
            roughness = float(parts[4]) if len(parts) > 4 else 0.013

            # Construction de la géométrie LineString
            pts_line = []
            if u_node in coords:
                pts_line.append(coords[u_node])
            if cid in vertices:
                pts_line.extend(vertices[cid])
            if d_node in coords:
                pts_line.append(coords[d_node])

            if len(pts_line) >= 2:
                line_geom = LineString(pts_line)
            else:
                line_geom = LineString([(0.0, 0.0), (1.0, 1.0)])

            dn_mm = diametres_mm.get(cid, 600.0)
            forme = formes.get(cid, "CIRCULAR")

            conduits_geoms.append(line_geom)
            conduits_data.append({
                "ID": cid,
                "ID_AMONT": u_node,
                "ID_AVAL": d_node,
                "DIAMETRE": dn_mm,
                "HAUTEUR": dn_mm,
                "FORMESECT": forme,
                "LONGUEUR": round(length_m, 2),
                "RUGOSITE": roughness,
                "MATERIAU": "Béton" if roughness >= 0.012 else "PVC/PEHD"
            })

    # 7. Sous-bassins versants [SUBCATCHMENTS] & [POLYGONS]
    polygons_coords: Dict[str, List[Tuple[float, float]]] = {}
    for line in sec.get("POLYGONS", []):
        parts = line.split()
        if len(parts) >= 3:
            s_id = parts[0].strip()
            try:
                px = float(parts[1])
                py = float(parts[2])
                if s_id not in polygons_coords:
                    polygons_coords[s_id] = []
                polygons_coords[s_id].append((px, py))
            except ValueError:
                continue

    sb_data = []
    sb_geoms = []
    for line in sec.get("SUBCATCHMENTS", []):
        parts = line.split()
        if len(parts) >= 4:
            s_id = parts[0].strip()
            rg_id = parts[1].strip()
            out_node = parts[2].strip()
            try:
                area_ha = float(parts[3])
            except ValueError:
                area_ha = 0.5
            imperv = float(parts[4]) if len(parts) > 4 else 50.0

            poly_geom = None
            if s_id in polygons_coords and len(polygons_coords[s_id]) >= 3:
                try:
                    poly_geom = Polygon(polygons_coords[s_id])
                except Exception:
                    poly_geom = None

            if poly_geom and poly_geom.is_valid:
                sb_geoms.append(poly_geom)
                sb_data.append({
                    "subcatchment_id": s_id,
                    "outlet_node": out_node,
                    "area_ha": round(area_ha, 3),
                    "imperv_pct": round(imperv, 1)
                })

    # 8. Assemblage et écriture dans le GeoPackage (.gpkg)
    # Suppression de l'ancien fichier s'il existait
    if gpkg_output_path.exists():
        try:
            gpkg_output_path.unlink()
        except Exception:
            pass

    # Écriture des couches
    gdf_conduites = gpd.GeoDataFrame(conduits_data, geometry=conduits_geoms, crs=crs_code)
    gdf_regards = gpd.GeoDataFrame(regards_data, geometry=regards_geoms, crs=crs_code)
    gdf_rejets = gpd.GeoDataFrame(rejets_data, geometry=rejets_geoms, crs=crs_code)

    gdf_conduites.to_file(str(gpkg_output_path), layer="canalisations", driver="GPKG")
    gdf_regards.to_file(str(gpkg_output_path), layer="regards", driver="GPKG")
    gdf_rejets.to_file(str(gpkg_output_path), layer="rejets", driver="GPKG")

    if sb_data and sb_geoms:
        gdf_sb = gpd.GeoDataFrame(sb_data, geometry=sb_geoms, crs=crs_code)
        gdf_sb.to_file(str(gpkg_output_path), layer="sous_bassins", driver="GPKG")

    summary = {
        "status": "success",
        "inp_path": str(inp_path.resolve()),
        "gpkg_path": str(gpkg_output_path.resolve()),
        "crs": crs_code,
        "conduits_count": len(gdf_conduites),
        "junctions_count": len(gdf_regards),
        "outfalls_count": len(gdf_rejets),
        "subcatchments_count": len(sb_data),
        "has_subcatchments": len(sb_data) > 0,
        "message": f"Conversion réussie : {len(gdf_conduites)} conduites, {len(gdf_regards)} regards, {len(gdf_rejets)} exutoires importés."
    }
    logger.info(f"[INP Converter] {summary['message']}")
    return summary

