# -*- coding: utf-8 -*-
"""
Tests unitaires pour la Restitution Hydraulique Exacte et Réconciliation SWMM 5.2.
Vérifie les chantiers 1, 2, 3 du CAHIER_DE_CHARGES_RESTITUTION_INP.md.
"""
import pytest
import geopandas as gpd
from shapely.geometry import Point, LineString
import pandas as pd

from src.domain.moteur_swmm.sections_inp import generer_lignes_sections_inp, _determiner_rugosite, _determiner_forme_section


def test_determiner_rugosite():
    assert _determiner_rugosite("PEHD") == 0.010
    assert _determiner_rugosite("PEHD annelé") == 0.010
    assert _determiner_rugosite("PVC") == 0.011
    assert _determiner_rugosite("PVC lisse") == 0.011
    assert _determiner_rugosite("Acier") == 0.012
    assert _determiner_rugosite("Fonte ductile") == 0.012
    assert _determiner_rugosite("Béton armé") == 0.013
    assert _determiner_rugosite(None) == 0.013


def test_determiner_forme_section():
    row_circ = pd.Series({"FORMESECT": "Circulaire", "DIAMETRE": 800.0})
    shape, g1, g2, b = _determiner_forme_section(row_circ, 0.8)
    assert shape == "CIRCULAR"
    assert g1 == 0.8
    assert g2 == 0.0

    row_rect = pd.Series({"FORMESECT": "Carré ou Réctengulaire", "HAUTEUR": 2000.0, "GDEBASE": 2500.0})
    shape, g1, g2, b = _determiner_forme_section(row_rect, 0.6)
    assert shape == "RECTANGULAR"
    assert g1 == 2.0
    assert g2 == 2.5


def test_generation_sections_completes_avec_pompes_et_weirs():
    # Regards
    regards = gpd.GeoDataFrame({
        "Code": ["REG_1", "SR_01", "REG_HAUT"],
        "Profondeur": [2.5, 3.0, 2.0],
        "geometry": [Point(0, 0), Point(100, 100), Point(200, 200)]
    })
    
    # Canalisations : 1 gravitaire rectangulaire, 1 refoulement PEHD, 1 sans IDs (orphelin sauvé)
    canalisations = gpd.GeoDataFrame({
        "ID_AMONT": ["REG_1", "SR_01", None],
        "ID_AVAL": ["SR_01", "REG_HAUT", None],
        "Longeur": [100.0, 150.0, 50.0],
        "DIAMETRE": [600.0, 400.0, 300.0],
        "MATERIAU": ["Béton", "PEHD", "PVC"],
        "FORMESECT": ["Carré ou Réctengulaire", "Circulaire", "Circulaire"],
        "HAUTEUR": [1500.0, None, None],
        "GDEBASE": [2000.0, None, None],
        "FONCTIONMT": ["Gravitaire", "Refoulement", "Gravitaire"],
        "geometry": [
            LineString([(0, 0), (100, 100)]),
            LineString([(100, 100), (200, 200)]),
            LineString([(0.05, 0.05), (50, 0)])  # Extrémité amont à 5 cm de REG_1 (0,0) -> snapping spatial !
        ]
    })

    # Ouvrages spéciaux : 1 DVO
    ouvrages = gpd.GeoDataFrame({
        "Code": ["DVO_01"],
        "TYPEOUVR": ["Déversoir d'orage"],
        "H_de_Seuil": [0.75],
        "geometry": [Point(1.0, 1.0)]
    })

    scen = {
        "nom": "Pluie décennale test",
        "duree_heures": 2.0,
        "timeseries": [("00:00", 0.0), ("01:00", 50.0), ("02:00", 0.0)],
        "intensite_max_defaut": 50.0,
    }

    swmm_sec = {
        "SUBCATCHMENTS": [";;Subcatchment"],
        "SUBAREAS": [";;Subarea"],
        "INFILTRATION": [";;Infil"],
        "POLYGONS": [";;Polygons"],
    }

    lines, meta = generer_lignes_sections_inp(
        regards=regards,
        canalisations=canalisations,
        rejets=gpd.GeoDataFrame(),
        sb_gdf=gpd.GeoDataFrame(),
        swmm_sec=swmm_sec,
        scen=scen,
        duree_sim=2.0,
        pas_routage_sec=5,
        pente_moyenne_pct=1.0,
        outfall_code="REG_HAUT",
        target_ex_id=None,
        exutoires_map={},
        clean_target_nodes={"REG_1", "SR_01", "REG_HAUT"},
        raccordements_orphelins=None,
        intensite_max_mmh=50.0,
        active_imperv=65.0,
        typ_nom="Habitat mixte",
        typologie_sol="habitat_mixte",
        st_id="test_st",
        scenario_key="test",
        cluster_id=1,
        bassin_nom="Bassin Test",
        buf_actuel=25.0,
        stations_relevage=None,
        ouvrages_speciaux=ouvrages,
        gpkg_counts={
            "canalisations_total": 3,
            "canalisations_gravitaires": 2,
            "canalisations_refoulement": 1,
            "regards": 3,
            "rejets": 0,
            "stations_relevage": 1,
            "deversoirs_orage": 1
        }
    )

    inp_text = "\n".join(lines)

    # 1. Vérifier la présence des sections [PUMPS], [CURVES], [WEIRS], [XSECTIONS]
    assert "[PUMPS]" in inp_text
    assert "[CURVES]" in inp_text
    assert "[WEIRS]" in inp_text
    assert "[XSECTIONS]" in inp_text

    # 2. Vérifier la section rectangulaire
    assert "RECTANGULAR" in inp_text
    assert "1.500" in inp_text
    assert "2.000" in inp_text

    # 3. Vérifier la pompe de refoulement et sa courbe
    assert "PMP_C_2" in inp_text
    assert "CURV_PMP_C_2" in inp_text

    # 4. Vérifier le déversoir d'orage
    assert "W_DVO_01" in inp_text
    assert "TRANSVERSE" in inp_text

    # 5. Vérifier le sauvetage du tronçon orphelin C_3 via raccordement spatial
    assert "C_3" in inp_text
    assert len(meta["raccordements_spatiaux"]) >= 1
    assert meta["raccordements_spatiaux"][0]["cid"] == "C_3"
    assert meta["raccordements_spatiaux"][0]["noeud"] == "REG_1"

    # 6. Vérifier le bilan de réconciliation
    assert "reconciliation" in meta
    reconcil = meta["reconciliation"]
    assert reconcil["statut_global"] == "RÉCONCILIÉ"
    assert len(reconcil["comparatif_composants"]) > 0
