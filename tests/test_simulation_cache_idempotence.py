# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Tests d'idempotence et mise en cache des résultats de simulation SWMM
================================================================================
"""

import pytest
import time
import glob
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

from api.database import SessionLocal, engine, Base
from api.models import Project, Simulation, Organization
from types import SimpleNamespace
from api.routes.simulations import (
    _generer_cle_cache_simulation,
    _get_cache_simulation_file,
    _charger_cache_simulation,
    _sauvegarder_simulation,
    _charger_derniere_simulation_disque_ou_db,
    run_native_swmm_simulation,
    get_latest_simulation,
    SimulationRunRequest
)


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    """LOT P0.1 — org dédiée + projet unique sur le GPKG de référence :
    la résolution de contexte est strictement bornée à l'organisation
    (plus de repli sur le premier projet de la base)."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        gpkgs = glob.glob("uploads/**/network_Assainissement_Ville.gpkg", recursive=True)
        if not gpkgs:
            gpkgs = glob.glob("data/demo_reseau.gpkg")
        gpkg_path = str(Path(gpkgs[0]).resolve()) if gpkgs else "data/demo_reseau.gpkg"

        org = db.query(Organization).filter_by(id="org_cache_idem").first()
        if not org:
            org = Organization(id="org_cache_idem", name="Org Cache Idem", slug="org-cache-idem")
            db.add(org)
            db.flush()
        proj = db.query(Project).filter_by(id="proj_cache_idem").first()
        if not proj:
            proj = Project(
                id="proj_cache_idem",
                org_id=org.id,
                name="Assainissement Ville Test",
                source_gpkg_key=gpkg_path,
                gpkg_version_id=None,
                is_archived=False
            )
            db.add(proj)
        else:
            proj.source_gpkg_key = gpkg_path
            proj.org_id = org.id
            proj.is_archived = False
        db.commit()
        setup_test_db.tenant = SimpleNamespace(org_id=org.id)
        setup_test_db.proj_id = proj.id
    finally:
        db.close()


def _gpkg_effectif_simulation(db, proj):
    """Chemin GPKG réellement utilisé par /run : snapshot versionné si le projet
    a une gpkg_version_id (3B), sinon source_gpkg_key. Le cache est
    content-adressé : semer via ce chemin garantit le même SHA-256 que la route."""
    from api.services.simulation_service import resoudre_contexte_projet
    ctx = resoudre_contexte_projet(db, proj.org_id)
    return ctx.gpkg_path


def test_generer_cle_cache_simulation_determinisme():
    """Vérifie que la clé de cache SHA-256 est strictement identique pour les mêmes paramètres."""
    gpkgs = glob.glob("uploads/**/network_Assainissement_Ville.gpkg", recursive=True) or ["data/demo_reseau.gpkg"]
    gpkg_p = Path(gpkgs[0])

    p1 = SimulationRunRequest(
        cluster_id=15,
        scenario_key="pluie_decennale",
        duree_heures=4.0,
        imperv_pct=65.0,
        pente_moyenne_pct=1.0,
        station_id="chlef_anrh_siege",
        raccordements_orphelins=[{"id": "OUV_1"}, {"id": "OUV_2"}]
    )

    p2 = SimulationRunRequest(
        cluster_id=15,
        scenario_key="pluie_decennale",
        duree_heures=4.0,
        imperv_pct=65.0,
        pente_moyenne_pct=1.0,
        station_id="chlef_anrh_siege",
        # Ordre inverse des orphelins : le tri interne garantit le déterminisme strict
        raccordements_orphelins=[{"id": "OUV_2"}, {"id": "OUV_1"}]
    )

    hash1, dict1 = _generer_cle_cache_simulation(gpkg_p, p1)
    hash2, dict2 = _generer_cle_cache_simulation(gpkg_p, p2)

    assert hash1 == hash2, "Deux requêtes avec mêmes paramètres doivent produire le même hash SHA-256"

    # Modification d'un paramètre (ex: imperv_pct=80) -> Hash différent
    p3 = SimulationRunRequest(
        cluster_id=15,
        scenario_key="pluie_decennale",
        duree_heures=4.0,
        imperv_pct=80.0,
        pente_moyenne_pct=1.0,
        station_id="chlef_anrh_siege"
    )
    hash3, _ = _generer_cle_cache_simulation(gpkg_p, p3)
    assert hash1 != hash3, "Un changement d'imperméabilisation doit modifier le hash"


def test_persistance_disque_et_base_de_donnees():
    """Vérifie l'écriture et relecture des fichiers de cache et tables de simulation."""
    db = SessionLocal()
    try:
        proj = db.get(Project, setup_test_db.proj_id)
        gpkg_path = _gpkg_effectif_simulation(db, proj)

        payload = SimulationRunRequest(
            cluster_id=15,
            scenario_key="pluie_decennale",
            duree_heures=4.0,
            pas_routage_sec=5,
            pente_moyenne_pct=1.0,
            buffer_m=35.0,
            valider_raccordement=True,
            typologie_sol="habitat_mixte",
            imperv_pct=65.0,
            intensite_max_mmh=62.0,
            station_id="chlef_anrh_siege"
        )
        param_hash, params_dict = _generer_cle_cache_simulation(gpkg_path, payload)

        mock_sim_result = {
            "meta": {"cluster_id": 15, "execution_duration_sec": 1.5, "cluster_nom": "Bassin 15"},
            "peak_outflow_m3s": 0.456,
            "routing_continuity_error_pct": 0.12,
            "total_outflow_m3": 1250.0,
            "node_results": {"N15": {"flooded": False, "max_depth_m": 0.5}},
            "conduit_results": {"C15": {"q_max": 0.45}},
            "inp_content": "[TITLE]\nSimulation Test Cache",
            "rpt_content": "SWMM 5.2 Test Report"
        }

        # 1. Sauvegarde
        saved_path = _sauvegarder_simulation(
            db=db,
            gpkg_path=gpkg_path,
            cluster_id=15,
            param_hash=param_hash,
            params_dict=params_dict,
            resultat=mock_sim_result,
            proj=proj
        )
        assert saved_path.exists(), "Le fichier de persistance JSON doit exister sur le disque"

        # 2. Lecture cache direct
        loaded = _charger_cache_simulation(gpkg_path, 15, param_hash)
        assert loaded is not None, "Le résultat doit pouvoir être restauré depuis le cache"
        assert loaded["peak_outflow_m3s"] == 0.456

        # 3. Restauration depuis DB / Disque — la « dernière » simulation peut
        # être un mock plus récent issu d'un run précédent (cache content-
        # adressé persistant) : on vérifie la restauration, pas la valeur.
        from_db = _charger_derniere_simulation_disque_ou_db(gpkg_path, db, proj)
        assert from_db is not None, "La dernière simulation doit être trouvable via la DB"
        assert isinstance(from_db.get("peak_outflow_m3s"), (int, float))
    finally:
        db.close()


def test_route_run_simulation_cache_hit_et_force_recalculate():
    """Vérifie l'exécution via run_native_swmm_simulation : cache hit instantané (cached=True) et recalcul (cached=False)."""
    db = SessionLocal()
    try:
        proj = db.get(Project, setup_test_db.proj_id)
        gpkg_path = _gpkg_effectif_simulation(db, proj)
        tenant = setup_test_db.tenant

        payload_cache = SimulationRunRequest(
            cluster_id=15,
            scenario_key="pluie_decennale",
            duree_heures=4.0,
            pas_routage_sec=5,
            pente_moyenne_pct=1.0,
            buffer_m=35.0,
            valider_raccordement=True,
            typologie_sol="habitat_mixte",
            imperv_pct=65.0,
            intensite_max_mmh=62.0,
            station_id="chlef_anrh_siege",
            force_recalculate=False
        )
        # LOT P1.3 : l'empreinte DWF entre dans la clé de cache — reproduire
        # exactement le calcul de la route (extra_params = info_cache_dwf).
        from api.services.apports_dwf_service import preparer_apports_pour_simulation
        _, info_cache_dwf = preparer_apports_pour_simulation(db, proj)
        param_hash, params_dict = _generer_cle_cache_simulation(
            gpkg_path, payload_cache, extra_params=info_cache_dwf)

        # Pré-enregistrer le cache
        mock_sim_result = {
            "meta": {"cluster_id": 15, "execution_duration_sec": 1.5, "cluster_nom": "Bassin 15"},
            "peak_outflow_m3s": 0.456,
            "routing_continuity_error_pct": 0.12,
            "total_outflow_m3": 1250.0,
            "node_results": {"N15": {"flooded": False, "max_depth_m": 0.5}},
            "conduit_results": {"C15": {"q_max": 0.45}},
            "inp_content": "[TITLE]\nSimulation Test Cache",
            "rpt_content": "SWMM 5.2 Test Report"
        }
        _sauvegarder_simulation(
            db=db,
            gpkg_path=gpkg_path,
            cluster_id=15,
            param_hash=param_hash,
            params_dict=params_dict,
            resultat=mock_sim_result,
            proj=proj
        )

        # 1. Appel route avec paramètres existants -> CACHE HIT instantané
        t0 = time.time()
        res_cached = run_native_swmm_simulation(payload_cache, db=db, tenant=tenant)
        elapsed = time.time() - t0

        assert res_cached["status"] == "success"
        assert res_cached["cached"] is True, "Le run avec paramètres existants en cache doit retourner cached=True"
        assert "restaurés" in res_cached["message"]
        assert elapsed < 0.1, f"Le hit de cache doit répondre instantanément (< 100ms), obtenu {elapsed:.3f}s"

        # 2. Vérification get_latest_simulation (résolution DB, 3D.5)
        res_latest = get_latest_simulation(db=db, tenant=tenant)
        assert res_latest["status"] == "success"
        assert res_latest["cached"] is True
        assert "node_results" in res_latest

        # 3. Test recalcul avec paramètre inédit (duree_heures = 99.0) : Le mock simule le moteur SWMM sans latence
        mock_new_result = {
            "meta": {"cluster_id": 15, "execution_duration_sec": 0.8},
            "peak_outflow_m3s": 0.888,
            "routing_continuity_error_pct": 0.05,
            "node_results": {"N15": {"flooded": True}},
            "conduit_results": {"C15": {"q_max": 0.88}},
            "inp_content": "[TITLE]\nSimulation 99h",
            "rpt_content": "SWMM Report 99h"
        }

        with patch("api.routes.simulations.MoteurSWMM.executer_simulation", return_value=mock_new_result):
            payload_new = SimulationRunRequest(
                cluster_id=15,
                scenario_key="pluie_decennale",
                duree_heures=99.0,
                pas_routage_sec=5,
                pente_moyenne_pct=1.0,
                buffer_m=35.0,
                valider_raccordement=True,
                typologie_sol="habitat_mixte",
                imperv_pct=65.0,
                intensite_max_mmh=round(1000.0 + (time.time() % 10000), 2),  # Paramètre dynamique inédit non en cache -> DOIT recalculer
                station_id="chlef_anrh_siege",
                force_recalculate=False
            )
            res_recalculated = run_native_swmm_simulation(payload_new, db=db, tenant=tenant)
            assert res_recalculated["cached"] is False, "Avec un nouveau paramètre jamais calculé, cached doit être False"
            assert res_recalculated["kpis"]["peak_outflow_m3s"] == 0.888

            # 4. Test avec force_recalculate=True sur le paramètre en cache -> DOIT forcer le recalcul
            res_forced = run_native_swmm_simulation(payload_cache.model_copy(update={"force_recalculate": True}), db=db, tenant=tenant)
            assert res_forced["cached"] is False, "Avec force_recalculate=True, le cache doit être ignoré"
    finally:
        db.close()
