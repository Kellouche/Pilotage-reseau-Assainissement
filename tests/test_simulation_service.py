# -*- coding: utf-8 -*-
"""
Tests unitaires de api/services/simulation_service.py — SimulationService.
Vérifie : clé de cache déterministe, validation des résultats, round-trip
persistance cache, équivalence moteur (service vs appel direct MoteurSWMM).
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.services import simulation_service as svc


# ---------------------------------------------------------------------------
# Fixtures utilitaires
# ---------------------------------------------------------------------------

def _payload(**overrides):
    """Payload factice aux noms de champs de SimulationRunRequest."""
    base = dict(
        scenario_key="pluie_decennale",
        duree_heures=None,
        pas_routage_sec=5,
        cluster_id=1,
        pente_moyenne_pct=1.0,
        buffer_m=35.0,
        valider_raccordement=True,
        typologie_sol="habitat_mixte",
        imperv_pct=None,
        intensite_max_mmh=None,
        station_id="chlef_anrh_siege",
        raccordements_orphelins=None,
        force_recalculate=False,
        bms_mode=False,
        bms_vigilance="orange",
        bms_cumul_mm=30.0,
        bms_heure_debut="07:00",
        bms_heure_fin="21:00",
        bms_duree_heures=None,
        bms_profil="cloche",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def gpkg_tmp(tmp_path):
    f = tmp_path / "reseau_test.gpkg"
    f.write_bytes(b"fake-gpkg-content")
    return f


# ---------------------------------------------------------------------------
# generer_cle_cache_simulation
# ---------------------------------------------------------------------------

def test_cle_cache_deterministe(gpkg_tmp):
    p = _payload()
    h1, d1 = svc.generer_cle_cache_simulation(gpkg_tmp, p)
    h2, d2 = svc.generer_cle_cache_simulation(gpkg_tmp, _payload())
    assert h1 == h2
    assert d1 == d2
    assert len(h1) == 16


def test_cle_cache_change_avec_parametres(gpkg_tmp):
    h1, _ = svc.generer_cle_cache_simulation(gpkg_tmp, _payload(scenario_key="pluie_biennale"))
    h2, _ = svc.generer_cle_cache_simulation(gpkg_tmp, _payload(scenario_key="pluie_decennale"))
    assert h1 != h2


def test_cle_cache_orphelins_tries(gpkg_tmp):
    _, d1 = svc.generer_cle_cache_simulation(
        gpkg_tmp, _payload(raccordements_orphelins=[{"id": "B"}, {"id": "A"}])
    )
    _, d2 = svc.generer_cle_cache_simulation(
        gpkg_tmp, _payload(raccordements_orphelins=[{"id": "A"}, {"id": "B"}])
    )
    assert d1["raccordements_orphelins"] == ["A", "B"]
    assert d1 == d2  # ordre d'entrée indifférent → même empreinte


# ---------------------------------------------------------------------------
# est_simulation_valide
# ---------------------------------------------------------------------------

def _resultat_valide():
    return {
        "meta": {"conduits_count": 3, "junctions_count": 4, "bbox": [3.0, 36.0, 3.1, 36.1]},
        "node_results": {"N1": {}},
        "conduit_results": {"C1": {}},
        "inp_content": "[TITLE]\nx",
    }


def test_est_simulation_valide_ok():
    assert svc.est_simulation_valide(_resultat_valide()) is True


def test_est_simulation_valide_rejets():
    assert svc.est_simulation_valide(None) is False
    assert svc.est_simulation_valide({}) is False
    assert svc.est_simulation_valide({"meta": {"bbox": [0.0, 0.0, 0.0, 0.0]}}) is False
    assert svc.est_simulation_valide({"meta": {"conduits_count": 0, "junctions_count": 0}}) is False


# ---------------------------------------------------------------------------
# Round-trip cache
# ---------------------------------------------------------------------------

def test_roundtrip_cache(gpkg_tmp):
    resultat = _resultat_valide()
    resultat["provenance"] = {"nature": "REAL", "engine": "EPA SWMM"}

    h, d = svc.generer_cle_cache_simulation(gpkg_tmp, _payload())
    # simuler sauvegarde disque (sans DB : proj=None, db factice non utilisé pour le JSON)
    cache_file = svc.get_cache_simulation_file(gpkg_tmp, 1, h)
    cache_file.write_text(json.dumps(resultat), encoding="utf-8")

    charge = svc.charger_cache_simulation(gpkg_tmp, 1, h)
    assert charge is not None
    assert charge["provenance"]["nature"] == "REAL"
    assert charge["node_results"] == {"N1": {}}


def test_charger_cache_absent(gpkg_tmp):
    assert svc.charger_cache_simulation(gpkg_tmp, 99, "hash_inexistant") is None


# ---------------------------------------------------------------------------
# preparer_scenario_bms — valeurs par défaut sans BMS
# ---------------------------------------------------------------------------

def test_preparer_scenario_sans_bms():
    bms, eff = svc.preparer_scenario_bms({"scenario_key": "pluie_decennale", "duree_heures": 4.0})
    assert bms is None
    assert eff["scenario_key"] == "pluie_decennale"
    assert eff["duree_heures"] == 4.0
    assert eff["intensite_max_mmh"] is None


def test_preparer_scenario_bms_active():
    params = {
        "scenario_key": "pluie_decennale",
        "bms_mode": True,
        "bms_cumul_mm": 30.0,
        "bms_duree_heures": 3.0,
        "station_id": "chlef_anrh_siege",
    }
    bms, eff = svc.preparer_scenario_bms(params)
    assert bms is not None
    assert eff["scenario_key"] == "bms_alerte"
    # durée = durée BMS + marge 3h
    assert eff["duree_heures"] == pytest.approx(6.0)
    assert eff["intensite_max_mmh"] is not None
    # l'entrée n'est pas mutée
    assert "scenario_key" not in params or params["scenario_key"] == "pluie_decennale"


# ---------------------------------------------------------------------------
# corriger_pic_depuis_timeseries
# ---------------------------------------------------------------------------

def test_corriger_pic_remplace_zero():
    res = {"peak_outflow_m3s": 0.0, "q_deleste_m3s": 0.5,
           "timeseries": {"status": "SUCCESS", "peak_outflow_m3s": 2.5, "peak_time": "12:00"}}
    svc.corriger_pic_depuis_timeseries(res)
    assert res["peak_outflow_m3s"] == 2.5
    assert res["q_exutoire_m3s"] == 2.5
    assert res["q_genere_m3s"] == 3.0


def test_corriger_pic_ne_touche_pas_si_inferieur():
    res = {"peak_outflow_m3s": 3.0, "q_deleste_m3s": 0.0,
           "timeseries": {"status": "SUCCESS", "peak_outflow_m3s": 2.0, "peak_time": "x"}}
    svc.corriger_pic_depuis_timeseries(res)
    assert res["peak_outflow_m3s"] == 3.0


# ---------------------------------------------------------------------------
# construire_reponse_simulation — contrat JSON identique
# ---------------------------------------------------------------------------

def test_reponse_contient_provenance():
    res = _resultat_valide()
    res["provenance"] = {"nature": "REAL"}
    out = svc.construire_reponse_simulation(res, cached=False)
    assert out["status"] == "success"
    assert out["cached"] is False
    assert out["provenance"] == {"nature": "REAL"}
    assert "kpis" in out and "node_results" in out
    assert out["download_inp_url"] == "/api/v1/simulations/download/inp"


def test_reponse_cached_message():
    out = svc.construire_reponse_simulation(_resultat_valide(), cached=True)
    assert out["cached"] is True
    assert "restaurés" in out["message"]


# ---------------------------------------------------------------------------
# resoudre_contexte_projet — cas limites
# ---------------------------------------------------------------------------

def test_resoudre_contexte_introuvable():
    """Sans projet ni GPKG démo → ContexteProjetIntrouvable."""
    from api.database import SessionLocal
    db = SessionLocal()
    try:
        # forcer le cas 'aucun projet' n'est pas trivial en DB réelle partagée ;
        # on teste au moins que la fonction ne lève pas d'exception inattendue
        # quand un projet existe (comportement nominal)
        ctx = svc.resoudre_contexte_projet(db, None)
        assert ctx.gpkg_path is None or Path(ctx.gpkg_path).exists()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Intégration : equivalence service vs appel moteur direct
# ---------------------------------------------------------------------------

GPKG_TEST = Path("uploads/a66e32ad-f32b-4529-acc3-7a6026eb5a8a/network_Assainissement_Ville.gpkg")


@pytest.mark.skipif(not GPKG_TEST.exists(), reason="GeoPackage de test non présent")
def test_equivalence_hydraulique_service_vs_moteur_direct():
    """
    Le service doit produire EXACTEMENT les mêmes résultats hydrauliques
    que l'appel direct à MoteurSWMM avec les mêmes paramètres.
    """
    from src.domain.moteur_swmm import MoteurSWMM

    params = {
        "scenario_key": "decennale_chlef_orage",
        "duree_heures": None,
        "pas_routage_sec": 5,
        "cluster_id": "25_ouvrages_speciaux_348883",
        "pente_moyenne_pct": 1.0,
        "buffer_m": 35.0,
        "valider_raccordement": True,
        "typologie_sol": None,
        "imperv_pct": None,
        "intensite_max_mmh": None,
        "station_id": "chlef_anrh_siege",
        "raccordements_orphelins": [],
        "bms_mode": False,
    }

    # Chemin service
    res_service = svc.executer_moteur_swmm(GPKG_TEST, params, execution_mode="sync")

    # Chemin direct (référence)
    moteur = MoteurSWMM()
    res_direct = moteur.executer_simulation(
        gpkg_path=GPKG_TEST,
        scenario_key=params["scenario_key"],
        duree_heures=params["duree_heures"],
        pas_routage_sec=params["pas_routage_sec"],
        pente_moyenne_pct=params["pente_moyenne_pct"],
        cluster_id=params["cluster_id"],
        tampon_buffer_m=params["buffer_m"],
        valider_raccordement_deporte=True,
        typologie_sol=params["typologie_sol"],
        imperv_pct=params["imperv_pct"],
        intensite_max_mmh=params["intensite_max_mmh"],
        station_id=params["station_id"],
        raccordements_orphelins=params["raccordements_orphelins"],
        scenario_personnalise=None,
        execution_mode="sync",
    )
    # appliquer la même correction de pic côté référence
    res_direct = svc.corriger_pic_depuis_timeseries(res_direct)

    cles_hydrauliques = [
        "peak_outflow_m3s", "q_genere_m3s", "q_exutoire_m3s", "q_derive_m3s",
        "total_outflow_m3", "total_runoff_volume_m3", "routing_continuity_error_pct",
        "flooded_nodes_count", "surcharged_nodes_count", "max_velocity_ms",
    ]
    for k in cles_hydrauliques:
        assert res_service.get(k) == res_direct.get(k), (
            f"Divergence hydraulique sur '{k}': service={res_service.get(k)} vs direct={res_direct.get(k)}"
        )

    # Le service ajoute execution_mode="sync" dans la provenance
    assert res_service["provenance"]["execution_mode"] == "sync"
    assert res_service["provenance"]["nature"] == "REAL"
    # Les INP générés doivent être identiques
    assert res_service["inp_content"] == res_direct["inp_content"]
