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


def test_telecharger_ordre_mission_bms_pdf():
    from types import SimpleNamespace
    from api.routes.simulations import telecharger_ordre_mission_bms_pdf
    # LOT P0.1 — tenant explicite requis ; sans simulation autorisée, le PDF
    # générique (données vides) reste produit dans le périmètre de l'org.
    tenant = SimpleNamespace(org_id="org_sans_simulation_test")
    resp = telecharger_ordre_mission_bms_pdf(cluster_id=None, db=None, tenant=tenant)
    assert resp.status_code == 200
    assert resp.media_type == "application/pdf"
    assert resp.body.startswith(b"%PDF-")
    assert "Ordre_Mission_Terrain_BMS" in resp.headers.get("Content-Disposition", "")
