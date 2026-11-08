#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Gestionnaire d'étiquettes et toponymie des voies urbaines
================================================================================
"""

def construire_labels_rues(regards_gdf):
    """Crée un GeoJSON de labels de rues."""
    if regards_gdf is None or regards_gdf.empty:
        return {"type": "FeatureCollection", "features": []}

    avec_rue = regards_gdf[
        regards_gdf["NOMVOIE"].notna() &
        (regards_gdf["NOMVOIE"] != "")
    ]
    if avec_rue.empty:
        return {"type": "FeatureCollection", "features": []}

    features = []
    for nom_rue, groupe in avec_rue.groupby("NOMVOIE"):
        centroide = groupe.geometry.unary_union.centroid
        commune = groupe["COMMUNE"].dropna()
        val_commune = commune.iloc[0] if not commune.empty else ""

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [centroide.x, centroide.y]
            },
            "properties": {
                "nom": str(nom_rue).strip(),
                "commune": str(val_commune).strip()
                if val_commune else "",
                "nb_regards": len(groupe)
            }
        })

    print(f"[data]   Labels rues : {len(features)} noms de rues",
          flush=True)
    return {"type": "FeatureCollection", "features": features}
