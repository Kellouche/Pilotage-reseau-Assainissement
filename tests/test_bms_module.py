# -*- coding: utf-8 -*-
"""
Tests unitaires pour le module BMS (Bulletins Météorologiques Spéciaux)
"""

import pytest
from src.domain.bms_module import (
    calculer_duree_heures,
    generer_hyetogramme_bms,
    creer_scenario_bms
)


def test_calculer_duree_heures_standard():
    duree = calculer_duree_heures("07:00", "21:00")
    assert duree == 14.0


def test_calculer_duree_heures_passage_minuit():
    duree = calculer_duree_heures("22:00", "06:00")
    assert duree == 8.0


def test_generer_hyetogramme_bms_cloche():
    cumul = 30.0
    duree = 14.0
    ts, i_max = generer_hyetogramme_bms(cumul_pluie_mm=cumul, duree_heures=duree, type_profil="cloche")
    
    assert len(ts) > 0
    assert i_max > 0.0
    # Vérifier que le cumul trapézoïdal est cohérent avec les 30 mm (tolérance 5%)
    pas_h = 15.0 / 60.0
    cumul_calc = sum(((ts[i-1][1] + ts[i][1]) / 2.0) * pas_h for i in range(1, len(ts)))
    assert pytest.approx(cumul_calc, rel=0.1) == cumul


def test_generer_hyetogramme_bms_uniforme():
    cumul = 28.0
    duree = 14.0
    ts, i_max = generer_hyetogramme_bms(cumul_pluie_mm=cumul, duree_heures=duree, type_profil="uniforme")
    
    assert i_max == pytest.approx(2.0, abs=0.1)


def test_creer_scenario_bms_structure():
    scen = creer_scenario_bms(
        cumul_pluie_mm=35.0,
        heure_debut="07:00",
        heure_fin="21:00",
        niveau_vigilance="orange",
        wilaya="Chlef"
    )

    assert scen["bms_metadata"]["is_bms"] is True
    assert scen["bms_metadata"]["vigilance"] == "orange"
    assert scen["bms_metadata"]["cumul_mm"] == 35.0
    assert scen["hauteur_totale_mm"] == 35.0
    assert scen["duree_heures"] == 15.0  # 14h + 1h ressuyage
    assert len(scen["timeseries"]) > 0
