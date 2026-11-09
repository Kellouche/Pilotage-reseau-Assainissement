# -*- coding: utf-8 -*-
"""
Tests unitaires pour la route preview BMS
"""

from api.routes.simulations import preview_bms_scenario, BMSPreviewRequest


def test_bms_preview_fonction():
    payload = BMSPreviewRequest(
        cumul_pluie_mm=35.0,
        heure_debut="07:00",
        heure_fin="21:00",
        niveau_vigilance="orange",
        type_profil="cloche",
        wilaya="Chlef"
    )
    data = preview_bms_scenario(payload)
    assert data["bms_metadata"]["is_bms"] is True
    assert data["bms_metadata"]["vigilance"] == "orange"
    assert data["hauteur_totale_mm"] == 35.0
    assert data["duree_bms_heures"] == 14.0
    assert len(data["timeseries"]) > 10
