#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Tests de non-régression par rapport au Golden Master de référence
================================================================================
"""

import os
import json
from pathlib import Path
import pytest
import geopandas as gpd
import pandas as pd
import networkx as nx

from src.domain.graphe_reseau import ConstructeurGrapheReseau
from src.domain.detecteur_clusters import partitionner_bassins_exclusifs, trouver_exutoires_physiques
from src.domain.extracteur_contours import extract_contours_from_dem
from src.qualite_reseau import QualiteReseau

GOLDEN_DIR = Path(__file__).resolve().parent / "data" / "golden_dataset"
GPKG_PATH = GOLDEN_DIR / "golden_network.gpkg"
DB_PATH = GOLDEN_DIR / "golden_network.db"
DEM_PATH = GOLDEN_DIR / "golden_dem.tif"
META_PATH = GOLDEN_DIR / "golden_metadata.json"
REFERENCE_SNAPSHOT_PATH = GOLDEN_DIR / "golden_master_reference.json"


@pytest.fixture(scope="module")
def golden_data():
    """Charge les couches du Golden Dataset."""
    assert GPKG_PATH.exists(), f"GeoPackage introuvable : {GPKG_PATH}"
    assert DB_PATH.exists(), f"Base SQLite introuvable : {DB_PATH}"
    assert DEM_PATH.exists(), f"Raster DEM introuvable : {DEM_PATH}"

    gdf_canalisations = gpd.read_file(GPKG_PATH, layer="canalisations")
    gdf_regards = gpd.read_file(GPKG_PATH, layer="regards")
    gdf_rejets = gpd.read_file(GPKG_PATH, layer="rejets")

    gdf_regards['original_gdf'] = 'regard'
    gdf_rejets['original_gdf'] = 'rejet'
    gdf_noeuds = pd.concat([gdf_regards, gdf_rejets], ignore_index=True)

    with open(META_PATH, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    return {
        "canalisations": gdf_canalisations,
        "regards": gdf_regards,
        "rejets": gdf_rejets,
        "noeuds": gdf_noeuds,
        "metadata": metadata
    }


def test_01_integrite_physique_golden_dataset(golden_data):
    """Vérifie l'inventaire physique et le linéaire du Golden Dataset."""
    canas = golden_data["canalisations"]
    regards = golden_data["regards"]
    rejets = golden_data["rejets"]
    meta = golden_data["metadata"]

    assert len(canas) == 379, f"Nombre de canalisations altéré : {len(canas)}"
    assert len(regards) == 372, f"Nombre de regards altéré : {len(regards)}"
    assert len(rejets) == 2, f"Nombre de rejets altéré : {len(rejets)}"

    longueur_calculee = float(canas.geometry.length.sum())
    longueur_attendue = meta["inventory"]["longueur_totale_m"]
    assert abs(longueur_calculee - longueur_attendue) < 0.1, (
        f"Linéaire total déviant : {longueur_calculee:.2f} m vs {longueur_attendue:.2f} m attendus"
    )


def test_02_analyse_morphologique_mnt(golden_data):
    """Vérifie l'extraction des courbes de niveau depuis le raster MNT."""
    contours = extract_contours_from_dem(str(DEM_PATH), contour_interval=10.0, output_format='gdf')
    assert len(contours) >= 1, "Aucune courbe de niveau extraite depuis le raster DEM"
    # Vérifie que les géométries extraites sont bien valides
    for geom in contours.geometry:
        assert geom.is_valid, "Courbe de niveau MNT géométriquement invalide"


def test_03_graphe_topologique_et_clusters(golden_data):
    """Vérifie l'invariance de construction du graphe orienté et de partitionnement."""
    constructeur = ConstructeurGrapheReseau()
    G = constructeur.construire_graphe(golden_data["noeuds"], golden_data["canalisations"])

    # Vérification du graphe orienté
    assert G.number_of_nodes() == 373, f"Nombre de nœuds du graphe altéré : {G.number_of_nodes()}"
    assert G.number_of_edges() == 365, f"Nombre d'arêtes du graphe altéré : {G.number_of_edges()}"

    # Détection des exutoires
    exutoires = trouver_exutoires_physiques(G)
    assert len(exutoires) >= 1, "Aucun exutoire physique détecté sur le réseau test"

    # Partitionnement en sous-bassins exclusifs
    bassins = partitionner_bassins_exclusifs(G)
    assert len(bassins) >= 1, "Échec du partitionnement des bassins versants exclusifs"
    premier_bassin = next(iter(bassins.values()))
    assert len(premier_bassin["edges"]) == 86, (
        f"Nombre d'arêtes du bassin principal altéré : {len(premier_bassin['edges'])} vs 86"
    )


def test_04_diagnostic_qualite_anomalies():
    """Vérifie l'invariance exacte de l'audit de qualité et de détection d'anomalies."""
    db_url = f"sqlite:///{DB_PATH}"
    qualite = QualiteReseau(db_url)
    rapport = qualite.analyser_reseau_complet()

    anomalies = rapport.get("anomalies", {})

    # Métriques clés figées de non-régression
    assert len(anomalies.get("doublon_regards", [])) == 1, "Altération de la détection de doublons regards"
    assert len(anomalies.get("sauts_pente", [])) == 86, "Altération de la détection des sauts de pente"
    assert len(anomalies.get("incoherences_amont_aval", [])) == 138, "Altération de la détection d'incohérences amont/aval"
    assert len(anomalies.get("pentes_suspectes", [])) == 285, "Altération de la détection de pentes suspectes"
    assert len(anomalies.get("troncons_orphelins", [])) == 0, "Détection inattendue de tronçons orphelins"


def test_05_snapshot_reference_global(golden_data):
    """
    Compare l'empreinte complète des calculs avec le fichier de référence officiel.
    Si le fichier de référence n'existe pas, il est initialisé automatiquement.
    """
    db_url = f"sqlite:///{DB_PATH}"
    qualite = QualiteReseau(db_url)
    rapport = qualite.analyser_reseau_complet()

    current_snapshot = {
        "version": "1.0",
        "inventory": {
            "canalisations": len(golden_data["canalisations"]),
            "regards": len(golden_data["regards"]),
            "rejets": len(golden_data["rejets"]),
            "longueur_totale_m": round(float(golden_data["canalisations"].geometry.length.sum()), 2)
        },
        "anomalies_counts": {
            k: len(v) for k, v in rapport.get("anomalies", {}).items()
        }
    }

    if not REFERENCE_SNAPSHOT_PATH.exists():
        with open(REFERENCE_SNAPSHOT_PATH, "w", encoding="utf-8") as f:
            json.dump(current_snapshot, f, indent=2, ensure_ascii=False)
        print(f"Snapshot officiel créé dans : {REFERENCE_SNAPSHOT_PATH}")

    with open(REFERENCE_SNAPSHOT_PATH, "r", encoding="utf-8") as f:
        expected_snapshot = json.load(f)

    # Tolérance zéro sur les anomalies du Golden Master
    assert current_snapshot["inventory"] == expected_snapshot["inventory"], (
        f"Régression sur l'inventaire du réseau : {current_snapshot['inventory']} vs {expected_snapshot['inventory']}"
    )
    assert current_snapshot["anomalies_counts"] == expected_snapshot["anomalies_counts"], (
        f"Régression sur les anomalies détectées : {current_snapshot['anomalies_counts']} vs {expected_snapshot['anomalies_counts']}"
    )
