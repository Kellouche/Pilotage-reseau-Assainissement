# -*- coding: utf-8 -*-
"""
Tests unitaires pour le générateur d'ordre de mission terrain BMS (PDF ReportLab).
"""

from src.domain.bms_ordre_mission import generer_pdf_ordre_mission_bms


def test_generer_pdf_ordre_mission_bms_succes():
    """Vérifie la génération complète du PDF avec métadonnées BMS et liste des regards."""
    simulation_data = {
        "peak_outflow_m3s": 2.15,
        "total_outflow_m3": 8500.0,
        "flooded_nodes_count": 2,
        "surcharged_nodes_count": 4,
        "flooded_nodes": [
            {"node": "J_102", "peak_flood_flow_cms": 0.42},
            {"node": "J_105", "peak_flood_flow_cms": 0.18}
        ],
        "node_results": {
            "J_102": {"status": "flooded"},
            "J_105": {"status": "flooded"},
            "J_108": {"status": "surcharged"},
            "J_110": {"status": "surcharged"}
        },
        "meta": {"bassin_nom": "Bassin Versant Centre Chlef"}
    }
    bms_info = {
        "vigilance": "orange",
        "cumul_mm": 40.0,
        "heure_debut": "07:00",
        "heure_fin": "21:00",
        "duree_heures": 14.0,
        "date_texte": "12/11/2026"
    }

    pdf_bytes = generer_pdf_ordre_mission_bms(
        simulation_data=simulation_data,
        bms_info=bms_info,
        nom_bassin="Bassin Versant Centre Chlef"
    )

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF-")


def test_detecter_adresse_intervention_regard_inonde():
    """Vérifie que l'adresse détectée priorise un regard inondé."""
    from src.domain.bms_ordre_mission import _detecter_adresse_intervention
    sim_data = {
        "flooded_nodes": [{"node": "J_102", "peak_flood_flow_cms": 0.42}],
        "meta": {"bassin_nom": "Bassin Versant Centre Chlef"}
    }
    adresse = _detecter_adresse_intervention(sim_data, "Bassin Versant Centre Chlef")
    assert "J_102" in adresse
    assert "débordement" in adresse


def test_detecter_adresse_intervention_regard_surcharge():
    """Vérifie que l'adresse détectée utilise un regard en charge si pas d'inondation."""
    from src.domain.bms_ordre_mission import _detecter_adresse_intervention
    sim_data = {
        "node_results": {
            "J_108": {"status": "surcharged"},
            "J_110": {"status": "surcharged"}
        },
        "meta": {"bassin_nom": "Bassin Versant Centre Chlef"}
    }
    adresse = _detecter_adresse_intervention(sim_data, "Bassin Versant Centre Chlef")
    assert "J_108" in adresse
    assert "mise en charge" in adresse


def test_detecter_adresse_intervention_fallback_bassin():
    """Vérifie que le fallback utilise le nom du bassin."""
    from src.domain.bms_ordre_mission import _detecter_adresse_intervention
    sim_data = {"meta": {"bassin_nom": "Bassin Versant Centre Chlef"}}
    adresse = _detecter_adresse_intervention(sim_data, "Bassin Versant Centre Chlef")
    assert "Bassin Versant Centre Chlef" in adresse


def test_generer_pdf_ordre_mission_bms_donnees_vides():
    """Vérifie que la fonction gère gracieusement les données minimales ou vides."""
    pdf_bytes = generer_pdf_ordre_mission_bms(
        simulation_data={},
        bms_info=None,
        nom_bassin=None
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
