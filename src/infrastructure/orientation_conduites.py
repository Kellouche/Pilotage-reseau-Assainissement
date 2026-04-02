#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : Pilotage Réseau d'Assainissement
Numéro version : 1.0.0
Date de création : 2026-04-02
Date de modification : 2026-04-02
Objectif : Orientation hydraulique des canalisations.
Calcule les cotes de radier à partir des regards et inverse
les coordonnées des canalisations dans le sens amont → aval.
"""

import numpy as np


def _safe_float(valeur):
    """Convertit une valeur en float (gère les virgules)."""
    if valeur is None:
        return None
    try:
        texte = str(valeur).replace(",", ".").strip()
        if not texte or texte in ("None", "nan"):
            return None
        return float(texte)
    except (ValueError, TypeError):
        return None


def orienter_conduites(conduites_geojson, regards_gdf_wgs84):
    """Oriente chaque canalisation dans le sens amont → aval."""
    if regards_gdf_wgs84 is None or regards_gdf_wgs84.empty:
        return
    if conduites_geojson is None:
        return

    features = conduites_geojson.get("features")
    if not features:
        return

    geoms = regards_gdf_wgs84.geometry
    valid = ~geoms.is_empty & geoms.notna()
    gdf_valid = regards_gdf_wgs84[valid]

    coords_arr = np.column_stack([
        gdf_valid.geometry.x.values,
        gdf_valid.geometry.y.values
    ])

    prof_arr = gdf_valid["PROFRADI"].apply(_safe_float).values
    surf_arr = gdf_valid["HFERMSOL"].apply(_safe_float).values

    cotes_arr = np.full(len(gdf_valid), np.nan)
    has_prof = ~np.array([x is None for x in prof_arr])
    has_surf = ~np.array([x is None for x in surf_arr])

    prof_float = np.where(has_prof,
                          [float(x) if x is not None else np.nan
                           for x in prof_arr],
                          np.nan)
    surf_float = np.where(has_surf,
                          [float(x) if x is not None else np.nan
                           for x in surf_arr],
                          np.nan)

    both = has_prof & has_surf
    cotes_arr[both] = surf_float[both] - prof_float[both]

    prof_only = has_prof & ~has_surf
    cotes_arr[prof_only] = -prof_float[prof_only]

    surf_only = has_surf & ~has_prof
    cotes_arr[surf_only] = surf_float[surf_only]

    n_avec_cote = int(np.sum(~np.isnan(cotes_arr)))
    print(f"[data]   Index spatial : {len(coords_arr)} regards "
          f"({n_avec_cote} avec cote)")

    inversions = 0
    sans_cote = 0

    for feat in features:
        geom = feat.get("geometry", {})
        type_geom = geom.get("type", "")
        coords_brutes = geom.get("coordinates", [])
        if not coords_brutes:
            continue

        if type_geom == "MultiLineString":
            if not coords_brutes[0] or len(coords_brutes[0]) < 2:
                continue
            lon_dep = coords_brutes[0][0][0]
            lat_dep = coords_brutes[0][0][1]
            lon_fin = coords_brutes[-1][-1][0]
            lat_fin = coords_brutes[-1][-1][1]
        elif type_geom == "LineString":
            if len(coords_brutes) < 2:
                continue
            lon_dep, lat_dep = coords_brutes[0][0], coords_brutes[0][1]
            lon_fin, lat_fin = coords_brutes[-1][0], coords_brutes[-1][1]
        else:
            continue

        dists_dep = np.sqrt(
            (coords_arr[:, 0] - lon_dep) ** 2 +
            (coords_arr[:, 1] - lat_dep) ** 2
        )
        idx_dep = int(np.argmin(dists_dep))
        cote_dep = (cotes_arr[idx_dep]
                    if dists_dep[idx_dep] < 0.0005 else None)

        dists_fin = np.sqrt(
            (coords_arr[:, 0] - lon_fin) ** 2 +
            (coords_arr[:, 1] - lat_fin) ** 2
        )
        idx_fin = int(np.argmin(dists_fin))
        cote_fin = (cotes_arr[idx_fin]
                    if dists_fin[idx_fin] < 0.0005 else None)

        if (cote_dep is None or np.isnan(cote_dep)
                or cote_fin is None or np.isnan(cote_fin)):
            sans_cote += 1
            continue

        if cote_dep < cote_fin:
            if type_geom == "MultiLineString":
                geom["coordinates"] = [
                    seg[::-1] for seg in coords_brutes[::-1]
                ]
            else:
                geom["coordinates"] = coords_brutes[::-1]
            inversions += 1

    print(f"[data]   Canalisations inversées : "
          f"{inversions}/{len(features)}")
    print(f"[data]   Canalisations sans cote : "
          f"{sans_cote}/{len(features)}")
