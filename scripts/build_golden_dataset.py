#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script d'extraction et de génération du Golden Dataset de référence (Tâche 0.5).
Extrait un sous-réseau représentatif d'assainissement et son MNT associé
pour servir de jeu de données certifié et pérenne pour les tests de non-régression.

Auteur : Antigravity / Hakim
Date : Octobre 2026
"""

import os
import json
import hashlib
from pathlib import Path
import geopandas as gpd
from shapely.geometry import box
import rasterio
from rasterio.mask import mask

def compute_file_sha256(filepath: Path) -> str:
    """Calcule l'empreinte SHA-256 d'un fichier."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def build_golden_dataset():
    root_dir = Path(__file__).resolve().parent.parent
    output_dir = root_dir / "tests" / "data" / "golden_dataset"
    output_dir.mkdir(parents=True, exist_ok=True)

    gpkg_source = Path(r"D:\IA Water Data Analysis\Assainissement\Assainissement_Ville.gpkg")
    dem_source = root_dir / "AST14DEM_00407152025093958_20251010054647.tif"

    if not gpkg_source.exists():
        raise FileNotFoundError(f"Source GPKG introuvable : {gpkg_source}")
    if not dem_source.exists():
        raise FileNotFoundError(f"Source DEM introuvable : {dem_source}")

    print("=" * 60)
    print("🏗️  GÉNÉRATION DU GOLDEN DATASET CERTIFIÉ (Tâche 0.5)")
    print("=" * 60)

    # 1. Fenêtre géographique autour de l'exutoire Nouvelle ville hassania
    cx, cy = 349525.02, 4000241.05
    half_size = 600.0  # 1.2 km de côté
    bbox_geom = box(cx - half_size, cy - half_size, cx + half_size, cy + half_size)

    # 2. Extraction des couches vectorielles
    print("\n📦 1. Extraction des couches vectorielles depuis Assainissement_Ville.gpkg...")
    
    canalisations_layer = "Canalisations_860f298d_9fd9_40a5_bfa4_f913acc71f2e"
    regards_layer = "Regards_e3c22000_8bba_45a0_a575_d60bbd4b99d3"
    rejets_layer = "Rejets_3cc8eef2_2241_47a0_ad80_fd59749ab068"

    gdf_canalisations = gpd.read_file(gpkg_source, layer=canalisations_layer, bbox=bbox_geom)
    gdf_regards = gpd.read_file(gpkg_source, layer=regards_layer, bbox=bbox_geom)
    gdf_rejets = gpd.read_file(gpkg_source, layer=rejets_layer, bbox=bbox_geom)

    # Sélection stricte des colonnes utiles et propres (élimination des doublons de casse GPKG)
    cols_canas = [c for c in ["NOM-VOIE", "DIAMETRE", "MATERIAU", "LINEAIRE", "PROF_FE_AM", "PROF_FE_AV", "FONCTIONMT", "ID_AMONT", "ID_AVAL", "geometry"] if c in gdf_canalisations.columns]
    gdf_canalisations = gdf_canalisations[cols_canas].copy()

    cols_regards = [c for c in ["Code", "NOMVOIE", "COMMUNE", "Profondeur", "DIAMETRES", "TYPERES", "PROFRADI", "HFERMSOL", "geometry"] if c in gdf_regards.columns]
    gdf_regards = gdf_regards[cols_regards].copy()

    cols_rejets = [c for c in ["NOM", "COMMUNE", "NOMVOIE", "geometry"] if c in gdf_rejets.columns]
    gdf_rejets = gdf_rejets[cols_rejets].copy()

    target_gpkg = output_dir / "golden_network.gpkg"
    if target_gpkg.exists():
        target_gpkg.unlink()

    print(f"   ✓ Canalisations extraites : {len(gdf_canalisations)}")
    print(f"   ✓ Regards extraits       : {len(gdf_regards)}")
    print(f"   ✓ Rejets extraits        : {len(gdf_rejets)}")

    # Enregistrement dans le nouveau GeoPackage certifié
    gdf_canalisations.to_file(target_gpkg, layer="canalisations", driver="GPKG")
    gdf_regards.to_file(target_gpkg, layer="regards", driver="GPKG", mode="a")
    gdf_rejets.to_file(target_gpkg, layer="rejets", driver="GPKG", mode="a")
    print(f"   💾 GeoPackage créé : {target_gpkg} ({target_gpkg.stat().st_size / 1024:.1f} Ko)")

    # 3. Extraction de la base SQLite compacte associée pour les tests rapides
    print("\n🗄️ 2. Création de la base SQLite compacte golden_network.db...")
    sqlite_source = root_dir / "swmm_platform.db"
    target_sqlite = output_dir / "golden_network.db"
    if target_sqlite.exists():
        target_sqlite.unlink()

    import sqlite3
    src_conn = sqlite3.connect(sqlite_source)
    dst_conn = sqlite3.connect(target_sqlite)

    # Récupérer les schémas
    for table in ['regards', 'conduites', 'rejets']:
        sql = src_conn.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'").fetchone()[0]
        dst_conn.execute(sql)

    # Regards
    regards_codes = []
    for c in gdf_regards['Code'].dropna():
        try:
            regards_codes.append(f"{float(c):.1f}")
            regards_codes.append(str(int(float(c))))
        except Exception:
            regards_codes.append(str(c))

    placeholders = ','.join('?' for _ in regards_codes)
    rows_regards = src_conn.execute(f"SELECT * FROM regards WHERE code IN ({placeholders})", regards_codes).fetchall()
    cols_regards = [d[0] for d in src_conn.execute("SELECT * FROM regards LIMIT 1").description]
    dst_conn.executemany(f"INSERT INTO regards VALUES ({','.join('?' for _ in cols_regards)})", rows_regards)

    # Conduites
    cana_amont = []
    for a in gdf_canalisations['ID_AMONT'].dropna():
        try:
            cana_amont.append(f"{float(a):.1f}")
            cana_amont.append(str(int(float(a))))
        except Exception:
            cana_amont.append(str(a))

    placeholders_am = ','.join('?' for _ in cana_amont)
    rows_canas = src_conn.execute(f"SELECT * FROM conduites WHERE id_amont IN ({placeholders_am})", cana_amont).fetchall()
    cols_canas = [d[0] for d in src_conn.execute("SELECT * FROM conduites LIMIT 1").description]
    dst_conn.executemany(f"INSERT INTO conduites VALUES ({','.join('?' for _ in cols_canas)})", rows_canas)

    # Rejets
    rows_rejets = src_conn.execute("SELECT * FROM rejets LIMIT 2").fetchall()
    cols_rejets = [d[0] for d in src_conn.execute("SELECT * FROM rejets LIMIT 1").description]
    dst_conn.executemany(f"INSERT INTO rejets VALUES ({','.join('?' for _ in cols_rejets)})", rows_rejets)

    dst_conn.commit()
    src_conn.close()
    dst_conn.close()
    print(f"   💾 SQLite créé : {target_sqlite} ({target_sqlite.stat().st_size / 1024:.1f} Ko, {len(rows_canas)} conduites, {len(rows_regards)} regards)")

    # 4. Extraction et découpage du MNT raster
    print("\n🏔️ 3. Découpage du MNT raster (GeoTIFF)...")
    target_dem = output_dir / "golden_dem.tif"
    bbox_df = gpd.GeoDataFrame(geometry=[bbox_geom], crs="EPSG:32631")

    with rasterio.open(dem_source) as src:
        out_image, out_transform = mask(src, bbox_df.geometry, crop=True)
        out_meta = src.meta.copy()
        out_meta.update({
            "driver": "GTiff",
            "height": out_image.shape[1],
            "width": out_image.shape[2],
            "transform": out_transform,
            "compress": "lzw"
        })
        with rasterio.open(target_dem, "w", **out_meta) as dst:
            dst.write(out_image)

    print(f"   💾 DEM raster créé : {target_dem} ({target_dem.stat().st_size / 1024:.1f} Ko, {out_image.shape[1]}x{out_image.shape[2]} px)")

    # 4. Calcul des métadonnées de référence (Ground Truth)
    print("\n📋 3. Calcul des métadonnées officielles de référence...")
    longueur_totale = float(gdf_canalisations.geometry.length.sum())
    valid_elevations = out_image[out_image > -9999]
    elev_min = float(valid_elevations.min()) if len(valid_elevations) > 0 else 0.0
    elev_max = float(valid_elevations.max()) if len(valid_elevations) > 0 else 0.0

    metadata = {
        "dataset_name": "Golden Dataset Référence — SWMM Platform",
        "version": "1.0",
        "created_at": "2026-10-28",
        "crs": "EPSG:32631",
        "projection": "UTM Zone 31N",
        "bbox": {
            "minx": cx - half_size,
            "miny": cy - half_size,
            "maxx": cx + half_size,
            "maxy": cy + half_size
        },
        "inventory": {
            "nb_canalisations": len(gdf_canalisations),
            "nb_regards": len(gdf_regards),
            "nb_rejets": len(gdf_rejets),
            "longueur_totale_m": round(longueur_totale, 2)
        },
        "dem": {
            "width_px": int(out_image.shape[2]),
            "height_px": int(out_image.shape[1]),
            "resolution_m": 30.0,
            "elevation_min_m": round(elev_min, 2),
            "elevation_max_m": round(elev_max, 2)
        },
        "checksums_sha256": {
            "golden_network_gpkg": compute_file_sha256(target_gpkg),
            "golden_network_db": compute_file_sha256(target_sqlite),
            "golden_dem_tif": compute_file_sha256(target_dem)
        }
    }

    metadata_path = output_dir / "golden_metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"   💾 Métadonnées enregistrées : {metadata_path}")
    print("\n✅ Golden Dataset généré avec succès !")
    return metadata

if __name__ == "__main__":
    build_golden_dataset()
