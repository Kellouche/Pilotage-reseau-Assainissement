#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : Pilotage Réseau d'Assainissement
Numéro version : 1.0.0
Date de création : 2026-04-02
Date de modification : 2026-04-02
Objectif : Génération des labels de rues pour la carte.
Crée un GeoJSON de points avec les noms de rues,
un par rue, positionnés au centroïde de ses regards.
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

    print(f"[data]   Labels rues : {len(features)} noms de rues")
    return {"type": "FeatureCollection", "features": features}
