"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Tests unitaires du système de gestion des jobs asynchrones
================================================================================
"""

import json
import subprocess
import pytest
from starlette.testclient import TestClient

from api.main import app
from api.database import SessionLocal, engine, Base
from api.models import Organization, User, Membership, Project, Cluster, Regard, Canalisation, Job, Simulation
from api.core.auth import hash_password, create_access_token
from api.core.jobs import create_job, update_job, get_job, list_jobs
from api.core.storage import get_storage, LocalStore
from workers.tasks.swmm_tasks import run_swmm_simulation_task, SolveurSWMMIndisponible
import workers.tasks.swmm_tasks as swmm_tasks_module
from api import schemas
from api.routes.simulations import launch_simulation
from workers.tasks.mnt_tasks import run_mnt_extraction_task


@pytest.fixture(scope="module", autouse=True)
def init_db_schema():
    """Garantit que le schéma complet existe dans la base de test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def test_setup(tmp_path, monkeypatch):
    """Prépare deux organisations distinctes (Tenant A et Tenant B) et configure le store local."""
    monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "true")

    db = SessionLocal()

    # Nettoyage ordonné
    db.query(Simulation).delete()
    db.query(Job).delete()
    db.query(Membership).delete()
    db.query(User).delete()
    db.query(Canalisation).delete()
    db.query(Regard).delete()
    db.query(Cluster).delete()
    db.query(Project).delete()
    db.query(Organization).delete()
    db.commit()

    # Org A
    org_a = Organization(id="org_alpha_id", name="Régie des Eaux Alpha", slug="regie-alpha")
    user_a = User(
        id="user_alpha_id",
        email="ingenieur@regie-alpha.dz",
        password_hash=hash_password("SecurPass2026!"),
        full_name="Ingénieur Alpha",
    )
    mem_a = Membership(org_id=org_a.id, user_id=user_a.id, role="admin")

    # Org B
    org_b = Organization(id="org_beta_id", name="Direction Beta", slug="dir-beta")
    user_b = User(
        id="user_beta_id",
        email="ingenieur@dir-beta.dz",
        password_hash=hash_password("SecurPass2026!"),
        full_name="Ingénieur Beta",
    )
    mem_b = Membership(org_id=org_b.id, user_id=user_b.id, role="engineer")

    # Éléments de réseau pour Org A
    gpkg_a = tmp_path / "reseau_alpha.gpkg"
    gpkg_a.write_bytes(b"fake-gpkg-content-for-async-tests")
    proj_a = Project(id="proj_alpha_id", org_id=org_a.id, name="Réseau Ouest", slug="net-alpha", source_gpkg_key=str(gpkg_a))
    regard_a1 = Regard(code="R1", org_id=org_a.id, network_id=proj_a.id, profrad=12.5, profondeur=2.5, longitude=3.0, latitude=36.7)
    regard_a2 = Regard(code="R2", org_id=org_a.id, network_id=proj_a.id, profrad=10.0, profondeur=2.8, longitude=3.01, latitude=36.71)
    conduite_a = Canalisation(fid="C1", org_id=org_a.id, network_id=proj_a.id, id_amont="R1", id_aval="R2", longueur=75.0, diametre=0.4)
    cluster_a = Cluster(id=101, org_id=org_a.id, network_id=proj_a.id, nom="Bassin Principal")

    db.add_all([org_a, user_a, mem_a, org_b, user_b, mem_b, proj_a, regard_a1, regard_a2, conduite_a, cluster_a])
    db.commit()

    token_a = create_access_token({"sub": user_a.id, "org_id": org_a.id, "role": "admin"})
    token_b = create_access_token({"sub": user_b.id, "org_id": org_b.id, "role": "engineer"})

    res = {
        "org_a_id": org_a.id,
        "token_a": token_a,
        "org_b_id": org_b.id,
        "token_b": token_b,
        "proj_a_id": proj_a.id,
        "cluster_a_id": cluster_a.id,
        "tmp_dir": tmp_path,
    }
    db.close()
    return res


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

    def fake(gpkg_path, params, execution_mode="sync"):
        appels.append({"gpkg_path": gpkg_path, "params": dict(params), "execution_mode": execution_mode})
        if erreur is not None:
            raise erreur
        return dict(resultat if resultat is not None else _resultat_moteur_fake())

    monkeypatch.setattr(simulation_service, "executer_moteur_swmm", fake)
    return appels


def _interdire_subprocess_worker(monkeypatch):
    """Prouve que le worker n'appelle JAMAIS subprocess directement."""
    def interdit(*a, **kw):
        raise AssertionError("subprocess ne doit plus être appelé par le worker")
    monkeypatch.setattr(swmm_tasks_module.subprocess, "run", interdit)


def test_swmm_simulation_worker_task(test_setup, monkeypatch):
    """Le worker délègue à SimulationService : même moteur, même GPKG, ResultStore."""
    appels_moteur = _spy_moteur(monkeypatch)
    _interdire_subprocess_worker(monkeypatch)
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
    _interdire_subprocess_worker(monkeypatch)
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
    _interdire_subprocess_worker(monkeypatch)
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


# --- Tests unitaires du helper _execute_swmm_solver (conservé jusqu'au lot 3C.7.5) ---
# Le worker ne l'appelle plus ; ces tests verrouillent son contrat
# « jamais de résultat synthétique » en attendant son retrait.


def test_helper_solveur_absent():
    with pytest.raises(SolveurSWMMIndisponible, match="introuvable"):
        swmm_tasks_module._execute_swmm_solver(
            inp_content="[TITLE]x", regards=[], conduites=[],
            duree_heures=1.0, scenario_pluie="pluie_decennale",
            parameters={"swmm_bin": "binaire_swmm_inexistant_3c73"},
        )


def test_helper_solveur_non_executable(monkeypatch):
    monkeypatch.setattr(swmm_tasks_module.shutil, "which", lambda name: "/fake/swmm5")

    def refuse(cmd, **kw):
        raise PermissionError(13, "Permission denied", cmd[0])
    monkeypatch.setattr(swmm_tasks_module.subprocess, "run", refuse)

    with pytest.raises(SolveurSWMMIndisponible, match="inaccessible"):
        swmm_tasks_module._execute_swmm_solver(
            inp_content="[TITLE]x", regards=[], conduites=[],
            duree_heures=1.0, scenario_pluie="p", parameters={"swmm_bin": "swmm5"},
        )


def test_helper_solveur_echec_execution(monkeypatch):
    monkeypatch.setattr(swmm_tasks_module.shutil, "which", lambda name: "/fake/swmm5")
    monkeypatch.setattr(
        swmm_tasks_module.subprocess, "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 3, "", "boom"))

    with pytest.raises(SolveurSWMMIndisponible, match="code retour 3"):
        swmm_tasks_module._execute_swmm_solver(
            inp_content="[TITLE]x", regards=[], conduites=[],
            duree_heures=1.0, scenario_pluie="p", parameters={"swmm_bin": "swmm5"},
        )


def test_helper_solveur_sans_rpt(monkeypatch):
    monkeypatch.setattr(swmm_tasks_module.shutil, "which", lambda name: "/fake/swmm5")
    monkeypatch.setattr(
        swmm_tasks_module.subprocess, "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "", ""))

    with pytest.raises(SolveurSWMMIndisponible, match="sans produire le rapport"):
        swmm_tasks_module._execute_swmm_solver(
            inp_content="[TITLE]x", regards=[], conduites=[],
            duree_heures=1.0, scenario_pluie="p", parameters={"swmm_bin": "swmm5"},
        )


# ============================================================
# LOT 3C.7.2 — Sécurisation identité et lancement asynchrone
# ============================================================


def _construire_tenant(db, org_id, email):
    """Construit un TenantContext réel pour les tests directs de route."""
    org = db.query(Organization).filter_by(id=org_id).first()
    user = db.query(User).filter_by(email=email).first()
    return TenantContext(actor=user, org=org, role="admin")


class _FakeTacheCelery:
    """Substitut de tâche Celery : capture les arguments de .delay()."""

    def __init__(self, erreur=None):
        self.appels = []
        self.erreur = erreur

    def delay(self, **kwargs):
        if self.erreur is not None:
            raise self.erreur
        self.appels.append(kwargs)
        return "fake-task-id"


def _patch_tache(monkeypatch, fake):
    """La route importe run_swmm_simulation_task au moment de l'appel :
    patcher l'attribut du module suffit et prouve l'appel réel."""
    monkeypatch.setattr(swmm_tasks_module, "run_swmm_simulation_task", fake)


def test_launch_simulation_sans_authentification_refuse(test_setup):
    """Aucun tenant : la dépendance stricte rejette en 401 — plus de Organization.first()."""
    client = TestClient(app)
    resp = client.post("/api/v1/simulations", json={"cluster_id": 101})
    assert resp.status_code == 401


def test_launch_simulation_tenant_valide(test_setup, monkeypatch):
    """Tenant valide : organisation résolue depuis le contexte, job pending, tâche publiée."""
    fake = _FakeTacheCelery()
    _patch_tache(monkeypatch, fake)
    db = SessionLocal()
    tenant = _construire_tenant(db, test_setup["org_a_id"], "ingenieur@regie-alpha.dz")

    payload = schemas.SimulationCreate(cluster_id=test_setup["cluster_a_id"], parameters={"scenario_pluie": "pluie_decennale"})
    result = launch_simulation(simulation=payload, db=db, tenant=tenant)

    assert result["status"] == "pending"
    assert result["org_id"] == test_setup["org_a_id"]
    assert result["project_id"] == test_setup["proj_a_id"]

    # Vérification des identifiants réellement transmis au worker
    assert len(fake.appels) == 1
    appel = fake.appels[0]
    assert appel["job_id"] == result["id"]
    assert appel["org_id"] == test_setup["org_a_id"]
    assert appel["network_id"] == test_setup["proj_a_id"]
    assert appel["parameters"]["project_id"] == test_setup["proj_a_id"]
    assert appel["parameters"]["simulation_id"] == result["id"]
    assert appel["parameters"]["cluster_id"] == test_setup["cluster_a_id"]

    # Job et Simulation cohérents, aucun orphelin
    job = db.query(Job).filter_by(id=result["id"]).first()
    assert job is not None and job.status == "pending"
    db.close()


def test_launch_simulation_cluster_autre_org_refuse(test_setup, monkeypatch):
    """Cluster appartenant à une autre organisation : refus stealth 404."""
    fake = _FakeTacheCelery()
    _patch_tache(monkeypatch, fake)
    db = SessionLocal()
    tenant = _construire_tenant(db, test_setup["org_a_id"], "ingenieur@regie-alpha.dz")

    # Créer un cluster dans Org B
    proj_b = Project(id="proj_beta_id", org_id=test_setup["org_b_id"], name="Réseau Beta", slug="net-beta")
    db.add(proj_b)
    db.flush()
    cluster_b = Cluster(id=202, org_id=test_setup["org_b_id"], network_id=proj_b.id, nom="Bassin Beta")
    db.add(cluster_b)
    db.commit()

    payload = schemas.SimulationCreate(cluster_id=cluster_b.id)
    with pytest.raises(HTTPException) as exc:
        launch_simulation(simulation=payload, db=db, tenant=tenant)
    assert exc.value.status_code == 404
    assert fake.appels == []
    db.close()


def test_launch_simulation_projet_incoherent_refuse(test_setup, monkeypatch):
    """Cluster Org A rattaché à un projet Org B : refus explicite, aucune publication."""
    fake = _FakeTacheCelery()
    _patch_tache(monkeypatch, fake)
    db = SessionLocal()
    tenant = _construire_tenant(db, test_setup["org_a_id"], "ingenieur@regie-alpha.dz")

    proj_b = Project(id="proj_gamma_id", org_id=test_setup["org_b_id"], name="Réseau Gamma", slug="net-gamma")
    db.add(proj_b)
    db.flush()
    cluster_incoherent = Cluster(id=303, org_id=test_setup["org_a_id"], network_id=proj_b.id, nom="Cluster incohérent")
    db.add(cluster_incoherent)
    db.commit()

    payload = schemas.SimulationCreate(cluster_id=cluster_incoherent.id)
    with pytest.raises(HTTPException) as exc:
        launch_simulation(simulation=payload, db=db, tenant=tenant)
    assert exc.value.status_code == 404
    assert fake.appels == []
    db.close()


def test_launch_simulation_cluster_sans_projet_refuse(test_setup, monkeypatch):
    """Cluster sans network_id : refus 422 explicite."""
    fake = _FakeTacheCelery()
    _patch_tache(monkeypatch, fake)
    db = SessionLocal()
    tenant = _construire_tenant(db, test_setup["org_a_id"], "ingenieur@regie-alpha.dz")

    cluster_orphelin = Cluster(id=404, org_id=test_setup["org_a_id"], network_id=None, nom="Sans projet")
    db.add(cluster_orphelin)
    db.commit()

    payload = schemas.SimulationCreate(cluster_id=cluster_orphelin.id)
    with pytest.raises(HTTPException) as exc:
        launch_simulation(simulation=payload, db=db, tenant=tenant)
    assert exc.value.status_code == 422
    assert fake.appels == []
    db.close()


def test_launch_simulation_broker_indisponible(test_setup, monkeypatch):
    """Échec de publication Celery : 503, job FAILED, simulation FAILED — aucun orphelin pending."""
    fake = _FakeTacheCelery(erreur=ConnectionError("broker Redis injoignable"))
    _patch_tache(monkeypatch, fake)
    db = SessionLocal()
    tenant = _construire_tenant(db, test_setup["org_a_id"], "ingenieur@regie-alpha.dz")

    payload = schemas.SimulationCreate(cluster_id=test_setup["cluster_a_id"])
    with pytest.raises(HTTPException) as exc:
        launch_simulation(simulation=payload, db=db, tenant=tenant)
    assert exc.value.status_code == 503

    # Le job créé avant l'échec est explicitement FAILED, pas laissé 'pending'
    jobs = db.query(Job).filter_by(org_id=test_setup["org_a_id"], job_type="simulation_swmm").all()
    assert len(jobs) == 1
    assert jobs[0].status == "failed"
    assert "Broker Celery indisponible" in (jobs[0].error_message or "")

    sim = db.query(Simulation).filter_by(id=jobs[0].id).first()
    assert sim is not None
    assert sim.status == "failed"

    db.close()


def test_swmm_worker_identifiants_incoherents(test_setup):
    """Le worker refuse de traiter une tâche dont project_id/simulation_id ne correspondent pas."""
    db = SessionLocal()
    org_id = test_setup["org_a_id"]
    proj_id = test_setup["proj_a_id"]

    job = create_job(db, org_id=org_id, job_type="simulation_swmm", network_id=proj_id)

    with pytest.raises(ValueError, match="Incohérence d'identité"):
        run_swmm_simulation_task(
            job_id=job.id,
            org_id=org_id,
            network_id=proj_id,
            parameters={"project_id": "un_autre_projet", "cluster_id": 101},
        )

    with pytest.raises(ValueError, match="Incohérence d'identité"):
        run_swmm_simulation_task(
            job_id=job.id,
            org_id=org_id,
            network_id=proj_id,
            parameters={"simulation_id": "un_autre_id", "cluster_id": 101},
        )

    db.refresh(job)
    assert job.status == "failed"
    db.close()


def test_mnt_extraction_worker_task(test_setup):
    """Exécute la tâche d'analyse altimétrique MNT et vérifie les calculs de relief."""
    db = SessionLocal()
    org_id = test_setup["org_a_id"]
    proj_id = test_setup["proj_a_id"]

    job = create_job(db, org_id=org_id, job_type="analyse_mnt", network_id=proj_id)

    result = run_mnt_extraction_task(
        job_id=job.id,
        org_id=org_id,
        network_id=proj_id,
        buffer_m=50.0,
    )

    assert "analysis_key" in result
    assert result["kpis"]["nodes_processed"] == 2
    assert result["kpis"]["elevation_min_m"] <= result["kpis"]["elevation_max_m"]

    # Vérification dans ArtifactStore
    storage = get_storage()
    assert storage.exists(result["analysis_key"]) is True

    db.refresh(job)
    assert job.status == "completed"
    assert job.progress == 100

    db.close()


from fastapi import HTTPException
from api.routes.jobs import get_job_status, get_jobs_list
from api.routes.artifacts import download_artifact
from api.core.security import TenantContext


def test_api_jobs_endpoints(test_setup):
    """Vérifie l'endpoint REST get_job_status et le cloisonnement strict (Stealth 404)."""
    db = SessionLocal()
    org_a = db.query(Organization).filter_by(id=test_setup["org_a_id"]).first()
    user_a = db.query(User).filter_by(email="ingenieur@regie-alpha.dz").first()
    org_b = db.query(Organization).filter_by(id=test_setup["org_b_id"]).first()
    user_b = db.query(User).filter_by(email="ingenieur@dir-beta.dz").first()

    tenant_a = TenantContext(actor=user_a, org=org_a, role="admin")
    tenant_b = TenantContext(actor=user_b, org=org_b, role="engineer")

    job_a = create_job(db, org_id=org_a.id, job_type="audit_qualite")

    # 1. Org A accède à son job -> succès
    data = get_job_status(job_id=job_a.id, tenant=tenant_a, db=db)
    assert data["id"] == job_a.id
    assert data["job_type"] == "audit_qualite"

    # 2. Org B tente d'accéder au job de Org A -> Stealth 404
    with pytest.raises(HTTPException) as exc_info:
        get_job_status(job_id=job_a.id, tenant=tenant_b, db=db)
    assert exc_info.value.status_code == 404

    # 3. Listing des jobs
    jobs_list = get_jobs_list(tenant=tenant_a, db=db)
    assert len(jobs_list) >= 1
    assert any(j["id"] == job_a.id for j in jobs_list)

    db.close()


def test_api_artifact_download_stealth_security(test_setup):
    """Prouve que le téléchargement d'artefacts est strictement cloisonné (Stealth 404)."""
    db = SessionLocal()
    org_a = db.query(Organization).filter_by(id=test_setup["org_a_id"]).first()
    user_a = db.query(User).filter_by(email="ingenieur@regie-alpha.dz").first()
    org_b = db.query(Organization).filter_by(id=test_setup["org_b_id"]).first()
    user_b = db.query(User).filter_by(email="ingenieur@dir-beta.dz").first()

    tenant_a = TenantContext(actor=user_a, org=org_a, role="admin")
    tenant_b = TenantContext(actor=user_b, org=org_b, role="engineer")

    storage = get_storage()
    proj_a = test_setup["proj_a_id"]

    # Créer un fichier dans le store pour Org A
    key_a = f"{org_a.id}/{proj_a}/reports/synthese.pdf"
    content = b"%PDF-1.4 Mock confidential report"
    storage.put_bytes(key_a, content, content_type="application/pdf")

    # 1. Org A télécharge son propre fichier -> 200 OK avec le contenu
    resp_a = download_artifact(key=key_a, tenant=tenant_a)
    assert resp_a.body == content
    assert resp_a.media_type == "application/pdf"

    # 2. Org B tente de télécharger le fichier de Org A -> Stealth 404
    with pytest.raises(HTTPException) as exc_info_b:
        download_artifact(key=key_a, tenant=tenant_b)
    assert exc_info_b.value.status_code == 404

    # 3. Tentative de traversée de répertoire -> Stealth 404
    hack_key = f"{org_a.id}/../../etc/shadow"
    with pytest.raises(HTTPException) as exc_info_hack:
        download_artifact(key=hack_key, tenant=tenant_a)
    assert exc_info_hack.value.status_code == 404

    db.close()
