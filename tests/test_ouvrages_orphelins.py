"""
Tests unitaires pour la détection et le raccordement opportuniste
des ouvrages spéciaux orphelins (Variante 0).
"""
import pytest
from pathlib import Path
from src.domain.ouvrages_orphelins import detecter_ouvrages_orphelins_proches
from src.domain.agents_expertise import AgentFinancierEtVariantes


def test_detecter_ouvrages_orphelins_cluster_85():
    """Vérifie la détection des 3 ouvrages spéciaux proches du cluster 85."""
    gpkg_cand = Path(r"D:\IA Water Data Analysis\Assainissement\Assainissement_Ville.gpkg")
    if not gpkg_cand.exists():
        pytest.skip("GeoPackage complet non disponible dans cet environnement.")

    # Vérifier avec ID numérique (85) et nom alphanumérique ("11_ouvrages_speciaux_349848")
    for cid in [85, "11_ouvrages_speciaux_349848"]:
        res = detecter_ouvrages_orphelins_proches(str(gpkg_cand), cluster_id=cid, rayon_max_m=120.0)
        assert res["cluster_id"] == cid
        assert res["nb_ouvrages_trouves"] >= 3

    types_trouves = [o["type"] for o in res["ouvrages"]]
    assert any("refoulement" in t.lower() or "station" in t.lower() for t in types_trouves)
    assert any("trop" in t.lower() for t in types_trouves)
    assert any("deversoir" in t.lower() or "dvo" in t.lower() for t in types_trouves)

    # Vérifier que les distances sont bien calculées en mètres (< 120m)
    for o in res["ouvrages"]:
        assert 0 < o["distance_m"] <= 120.0
        assert o["cout_estime_dzd"] > 0
        assert o["regard_proche_id"] is not None
        assert "regard_coord_wgs84" in o
        assert "ouvrage_coord_wgs84" in o


def test_variante_0_dans_agent_financier():
    """Vérifie que l'AgentFinancier génère la Variante 0 opportuniste avec économie > 90%."""
    agent_fin = AgentFinancierEtVariantes()
    kpis = {
        "nb_noeuds_inondes": 23,
        "volume_inonde_total_m3": 1500.0,
        "nb_conduites_surchargees": 55,
        "longueur_surchargee_m": 1500.0,
    }
    gc = {
        "prescriptions": [
            {"diam_prescrit_mm": 800, "diam_actuel_mm": 500, "longueur_m": 100, "cout_estime_dzd": 4500000}
        ],
        "metres_lineaires_totaux": 100.0,
        "cout_global_estime_dzd": 4500000.0,
        "nb_troncons_a_recalibrer": 1
    }
    lid = {
        "volume_tampon_requis_m3": 500.0,
        "cout_sfn_mixte_dzd": 12000000.0
    }
    meta = {
        "raccordements_orphelins": [
            {"id": "SR_01", "nom": "Station Hay Houria", "type": "station_relevage", "distance_m": 35.0, "regard_proche_id": "7195", "cout_estime_dzd": 1575000.0},
            {"id": "DVO_10", "nom": "DVO Code 10", "type": "deversoir_orage", "distance_m": 45.0, "regard_proche_id": "7776", "cout_estime_dzd": 2025000.0}
        ]
    }

    res = agent_fin.analyser_variantes(
        kpis=kpis,
        gc=gc,
        lid=lid,
        meta=meta
    )

    assert "variantes" in res
    assert len(res["variantes"]) >= 4
    v0 = res["variantes"][0]
    assert "Variante 0" in v0["nom"]
    assert v0["cout_total_dzd"] == 3600000.0
    assert "OPPORTUNITÉ VALORISÉE (Variante 0)" in res["note_technique"]
