# -*- coding: utf-8 -*-
"""
Tests unitaires du système de jobs asynchrones : CRUD, workers SWMM/MNT, result_store
"""

import json
import pytest
from starlette.testclient import TestClient

from api.main import app
from api.database import SessionLocal, engine, Base
from api.models import Organization, User, Membership, Project, Cluster, Regard, Canalisation, Job, Simulation
from api.core.auth import hash_password, create_access_token
from api.core.jobs import create_job, update_job, get_job, list_jobs
from api.core.storage import get_storage, LocalStore
from workers.tasks.swmm_tasks import run_swmm_simulation_task
import workers.tasks.swmm_tasks as swmm_tasks_module
from api import schemas
from api.routes.simulations import launch_simulation
from workers.tasks.mnt_tasks import run_mnt_extraction_task

from tests.async_jobs_support import _construire_tenant, init_db_schema, test_setup


def test_job_crud_lifecycle(test_setup):
    """Vérifie le cycle de vie complet d'un Job en base de données."""
    db = SessionLocal()
    org_id = test_setup["org_a_id"]

    # Création
    job = create_job(db, org_id=org_id, job_type="simulation_swmm", payload={"scenario": "decennale"})
    assert job.id is not None
    assert job.status == "pending"
    assert job.progress == 0

    # Progression intermédiaire
    job_updated = update_job(db, job.id, progress=50, status="running", message="Calculs en cours")
    assert job_updated.progress == 50
    assert job_updated.status == "running"
    assert job_updated.message == "Calculs en cours"

    # Clôture avec succès
    job_final = update_job(
        db,
        job.id,
        progress=100,
        status="completed",
        message="Terminé",
        result_refs={"kpi_peak_flow": 1.25},
    )
    assert job_final.progress == 100
    assert job_final.status == "completed"
    assert job_final.result_refs["kpi_peak_flow"] == 1.25

    db.close()


def test_job_multi_tenant_isolation(test_setup):
    """Prouve l'isolation stricte des tâches : Org B ne peut pas accéder aux jobs de Org A."""
    db = SessionLocal()
    org_a = test_setup["org_a_id"]
    org_b = test_setup["org_b_id"]

    job_a = create_job(db, org_id=org_a, job_type="simulation_swmm")

    # Lecture par Org A -> succès
    found_a = get_job(db, job_a.id, org_id=org_a)
    assert found_a is not None
    assert found_a.id == job_a.id

    # Lecture par Org B -> None (stealth)
    found_b = get_job(db, job_a.id, org_id=org_b)
    assert found_b is None

    # Listing cloisonné
    jobs_a = list_jobs(db, org_id=org_a)
    jobs_b = list_jobs(db, org_id=org_b)
    assert any(j.id == job_a.id for j in jobs_a)
    assert not any(j.id == job_a.id for j in jobs_b)

    db.close()


# ============================================================
# LOT 3C.7.3 — Worker Celery = adaptateur de SimulationService
# ============================================================

import api.services.simulation_service as simulation_service


def _resultat_moteur_fake():
    """Résultat minimal valide au format MoteurSWMM (injecté à la frontière moteur)."""
    return {
        "meta": {"bbox": [3.0, 36.7, 3.01, 36.71], "conduits_count": 1, "junctions_count": 2},
        "node_results": {"R1": {"max_depth_m": 0.1}},
        "conduit_results": {"C1": {"max_q_m3s": 0.05}},
        "peak_outflow_m3s": 0.05,
        "routing_continuity_error_pct": 1.0,
        "flooded_nodes_count": 0,
        "inp_content": "[TITLE]\nTest INP",
        "rpt_content": "EPA STORM WATER MANAGEMENT MODEL - VERSION 5.2\nTotal Inflow 100.0",
        "provenance": {"nature": "REAL", "engine": "EPA SWMM"},
        "timeseries": {"status": "SUCCESS", "steps": []},
    }


def _spy_moteur(monkeypatch, resultat=None, erreur=None):
    """Espionne executer_moteur_swmm (frontière moteur) et prouve les appels réels."""
    appels = []

    def fake(gpkg_path, params, execution_mode="sync", garde_fou_config=None):
        appels.append({"gpkg_path": gpkg_path, "params": dict(params),
                       "execution_mode": execution_mode,
                       "garde_fou_config": garde_fou_config})
        if erreur is not None:
            raise erreur
        return dict(resultat if resultat is not None else _resultat_moteur_fake())

    monkeypatch.setattr(simulation_service, "executer_moteur_swmm", fake)
    return appels


def _verifier_worker_sans_chemin_hydraulique():
    """Preuve statique : le worker ne contient plus AUCUN chemin
    d'exécution hydraulique autonome (ni subprocess, ni INP, ni solveur)."""
    from pathlib import Path
    src = Path(swmm_tasks_module.__file__).read_text(encoding="utf-8")
    for interdit in ("import subprocess", "subprocess.run", "shutil.which(",
                     "import shutil", "_execute_swmm_solver(",
                     "_build_swmm_inp_content(", "_parse_swmm_report(",
                     "SolveurSWMMIndisponible(", "select(Regard)",
                     "select(Canalisation)", "put_bytes(", "get_storage("):
        assert interdit not in src, f"Chemin hydraulique résiduel : {interdit}"


def test_swmm_simulation_worker_task(test_setup, monkeypatch):
    """Le worker délègue à SimulationService : même moteur, même GPKG, ResultStore."""
    appels_moteur = _spy_moteur(monkeypatch)
    _verifier_worker_sans_chemin_hydraulique()
    db = SessionLocal()
    org_id = test_setup["org_a_id"]
    proj_id = test_setup["proj_a_id"]

    job = create_job(db, org_id=org_id, job_type="simulation_swmm", network_id=proj_id)

    result = run_swmm_simulation_task(
        job_id=job.id,
        org_id=org_id,
        network_id=proj_id,
        scenario_pluie="pluie_decennale",
        duree_heures=12.0,
        parameters={"cluster_id": test_setup["cluster_a_id"], "project_id": proj_id,
                    "simulation_id": job.id, "scenario_pluie": "pluie_decennale",
                    "duree_heures": 12.0},
    )

    # 1. Le moteur COMMUN a été appelé exactement une fois, en mode celery,
    #    sur le GPKG résolu du projet (source_gpkg_key legacy)
    assert len(appels_moteur) == 1
    appel = appels_moteur[0]
    assert appel["execution_mode"] == "celery"
    assert str(appel["gpkg_path"]).endswith("reseau_alpha.gpkg")
    assert appel["params"]["cluster_id"] == test_setup["cluster_a_id"]
    assert appel["params"]["scenario_key"] == "pluie_decennale"
    # Les clés d'identité ne polluent pas le contrat moteur
    assert "project_id" not in appel["params"]
    assert "simulation_id" not in appel["params"]

    # 2. Payload de clôture : référence ResultStore, pas d'anciennes clés
    assert result["simulation_id"] == job.id
    assert result["param_hash"]
    assert result["result_store"]["complet"] is True
    assert result["result_key"]

    # 3. Artefacts ResultStore réellement déposés et lisibles
    storage = get_storage()
    assert storage.exists(result["result_key"]) is True

    # 4. Ligne Simulation = job_id, complétée, provenance celery
    db.expire_all()
    sim = db.query(Simulation).filter_by(id=job.id).first()
    assert sim is not None
    assert sim.status == "completed"
    assert sim.org_id == org_id
    assert sim.project_id == proj_id
    assert sim.results_s3_key.endswith(".json")
    prov = (sim.summary_kpis or {}).get("provenance") or {}
    assert prov.get("execution_mode") == "celery"
    assert prov.get("gpkg_sha256")

    # 5. Le même service de lecture que le chemin synchrone fonctionne
    from api.services.simulation_service import charger_resultat_simulation
    data = charger_resultat_simulation(sim)
    assert data is not None
    assert data.get("node_results")

    # 6. Job complété avec références de résultat
    db.refresh(job)
    assert job.status == "completed"
    assert job.progress == 100
    assert "result_key" in (job.result_refs or {})

    db.close()


def test_swmm_worker_moteur_en_echec(test_setup, monkeypatch):
    """Erreur métier propagée : job FAILED, simulation FAILED, aucun artefact."""
    _spy_moteur(monkeypatch, erreur=RuntimeError("pyswmm indisponible"))
    _verifier_worker_sans_chemin_hydraulique()
    db = SessionLocal()
    org_id = test_setup["org_a_id"]
    proj_id = test_setup["proj_a_id"]

    job = create_job(db, org_id=org_id, job_type="simulation_swmm", network_id=proj_id)

    with pytest.raises(RuntimeError, match="pyswmm indisponible"):
        run_swmm_simulation_task(
            job_id=job.id,
            org_id=org_id,
            network_id=proj_id,
            parameters={"cluster_id": test_setup["cluster_a_id"], "project_id": proj_id,
                        "simulation_id": job.id},
        )

    db.refresh(job)
    assert job.status == "failed"
    assert "pyswmm indisponible" in (job.error_message or "")

    sim = db.query(Simulation).filter_by(id=job.id).first()
    assert sim is not None and sim.status == "failed"

    db.close()


def test_swmm_worker_gpkg_absent(test_setup, monkeypatch):
    """Projet sans GPKG disponible : interruption explicite, job FAILED."""
    _spy_moteur(monkeypatch)
    _verifier_worker_sans_chemin_hydraulique()
    db = SessionLocal()
    org_id = test_setup["org_a_id"]
    # Projet Org A sans aucun GPKG
    proj_sans = Project(id="proj_sans_gpkg", org_id=org_id, name="Sans GPKG", slug="sans-gpkg")
    db.add(proj_sans)
    db.commit()

    job = create_job(db, org_id=org_id, job_type="simulation_swmm", network_id=proj_sans.id)

    with pytest.raises(Exception):
        run_swmm_simulation_task(
            job_id=job.id,
            org_id=org_id,
            network_id=proj_sans.id,
            parameters={"cluster_id": test_setup["cluster_a_id"], "project_id": proj_sans.id,
                        "simulation_id": job.id},
        )

    # Le cluster appartient à proj_alpha, pas à proj_sans → refus cluster OU gpkg
    db.refresh(job)
    assert job.status == "failed"
    db.close()


def test_service_metier_independence_celery():
    """SimulationService ne doit dépendre ni de Celery ni de FastAPI."""
    from pathlib import Path
    src = Path(simulation_service.__file__).read_text(encoding="utf-8")
    for interdit in ("import celery", "from celery", "from fastapi", "import fastapi",
                     "from starlette", "celery_app"):
        assert interdit not in src.lower(), f"Dépendance interdite : {interdit}"


def test_service_async_bms_applique(test_setup, monkeypatch):
    """Les paramètres BMS sont réellement préparés par le chemin commun (preparer_scenario_bms)."""
    from src.domain.moteur_swmm import MoteurSWMM

    appels = []

    def fake_exec(self, **kwargs):
        appels.append(kwargs)
        return _resultat_moteur_fake()

    monkeypatch.setattr(MoteurSWMM, "executer_simulation", fake_exec)
    db = SessionLocal()
    org_id = test_setup["org_a_id"]
    proj_id = test_setup["proj_a_id"]

    result = simulation_service.executer_en_async(
        db,
        org_id=org_id,
        project_id=proj_id,
        cluster_id=test_setup["cluster_a_id"],
        parameters={
            "scenario_pluie": "pluie_decennale",
            "bms_mode": True,
            "bms_cumul_mm": 45.0,
            "bms_vigilance": "orange",
            "project_id": "tentative_ecrasement",  # ne doit PAS être honoré
        },
        simulation_id="sim_test_bms_001",
    )

    assert len(appels) == 1
    kw = appels[0]
    # Le scénario BMS a été construit et injecté comme scenario_personnalise
    assert kw["scenario_key"] == "bms_alerte"
    assert kw["scenario_personnalise"] is not None
    assert kw["cluster_id"] == test_setup["cluster_a_id"]
    assert kw["execution_mode"] == "celery"
    # L'identité projet n'a pas été écrasée par les paramètres
    assert result["project_id"] == proj_id
    assert result["gpkg"]["sha256"]
    db.close()


# ============================================================
# LOT 3C.7.4 — Unification persistance / results_s3_key / result_url
# ============================================================


def test_result_url_priorise_resultstore(test_setup, monkeypatch):
    """Une sim Celery complétée expose result_url pointant vers ResultStore result.json."""
    _spy_moteur(monkeypatch)
    _verifier_worker_sans_chemin_hydraulique()
    db = SessionLocal()
    org_id = test_setup["org_a_id"]
    proj_id = test_setup["proj_a_id"]

    job = create_job(db, org_id=org_id, job_type="simulation_swmm", network_id=proj_id)
    run_swmm_simulation_task(
        job_id=job.id, org_id=org_id, network_id=proj_id,
        parameters={"cluster_id": test_setup["cluster_a_id"], "project_id": proj_id,
                    "simulation_id": job.id},
    )

    from api.routes.simulations import get_simulation_status
    tenant = _construire_tenant(db, org_id, "ingenieur@regie-alpha.dz")
    status = get_simulation_status(job_id=job.id, db=db, tenant=tenant)

    assert status["status"] == "completed"
    assert f"simulations/{job.id}/result.json" in status["result_url"]
    assert status["result_url"].startswith("/api/v1/artifacts/download?key=")
    # La clé est une clé ArtifactStore (préfixe org), jamais un chemin local
    cle = status["result_url"].split("key=", 1)[1]
    assert cle.startswith(f"{org_id}/")
    db.close()


def test_result_url_repli_results_s3_key_legacy(test_setup):
    """Sans artefact ResultStore, result_url retombe sur results_s3_key (clé ArtifactStore legacy)."""
    db = SessionLocal()
    org_id = test_setup["org_a_id"]
    proj_id = test_setup["proj_a_id"]

    cle_legacy = f"{org_id}/{proj_id}/simulations/legacy_job/summary.json"
    sim = Simulation(
        id="legacy_job", org_id=org_id, project_id=proj_id,
        name="Legacy", status="completed", results_s3_key=cle_legacy,
        summary_kpis={},
    )
    db.add(sim)
    db.commit()

    from api.routes.simulations import get_simulation_status
    tenant = _construire_tenant(db, org_id, "ingenieur@regie-alpha.dz")
    status = get_simulation_status(job_id="legacy_job", db=db, tenant=tenant)

    assert f"key={cle_legacy}" in status["result_url"]
    assert "project_id=proj_alpha_id" in status["result_url"]
    db.close()


def test_resoudre_simulation_resultstore_sans_results_s3_key(test_setup):
    """Une sim avec identité complète et result.json ResultStore est résolue
    même si results_s3_key est vide (contrat ResultStore prioritaire)."""
    from api.services.result_store import ArtifactKind, ResultRef, ResultStore
    from api.services.simulation_service import resoudre_simulation_courante

    db = SessionLocal()
    org_id = test_setup["org_a_id"]
    proj_id = test_setup["proj_a_id"]

    sim = Simulation(
        id="sim_sans_cle", org_id=org_id, project_id=proj_id,
        name="Sans cle", status="completed", results_s3_key=None,
        summary_kpis={},
    )
    db.add(sim)
    db.commit()

    resultat = {
        "meta": {"bbox": [3.0, 36.7, 3.01, 36.71], "conduits_count": 1, "junctions_count": 2},
        "node_results": {"R1": {}}, "conduit_results": {"C1": {}},
        "peak_outflow_m3s": 0.1,
    }
    store = ResultStore()
    store.save_idempotent(ResultRef(org_id, proj_id, "sim_sans_cle"),
                          resultat, kind=ArtifactKind.RESULT_JSON)

    ctx = resoudre_simulation_courante(db, org_id=org_id, project_id=proj_id,
                                       resoudre_gpkg=False)
    assert ctx.simulation.id == "sim_sans_cle"
    assert ctx.data["node_results"]
    db.close()
