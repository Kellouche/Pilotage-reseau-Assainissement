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
import pytest
from starlette.testclient import TestClient

from api.main import app
from api.database import SessionLocal, engine, Base
from api.models import Organization, User, Membership, Project, Cluster, Regard, Canalisation, Job, Simulation
from api.core.auth import hash_password, create_access_token
from api.core.jobs import create_job, update_job, get_job, list_jobs
from api.core.storage import get_storage, LocalStore
from workers.tasks.swmm_tasks import run_swmm_simulation_task
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
    proj_a = Project(id="proj_alpha_id", org_id=org_a.id, name="Réseau Ouest", slug="net-alpha")
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


def test_swmm_simulation_worker_task(test_setup):
    """Exécute la tâche de simulation SWMM et vérifie les artefacts sauvegardés."""
    db = SessionLocal()
    org_id = test_setup["org_a_id"]
    proj_id = test_setup["proj_a_id"]

    job = create_job(db, org_id=org_id, job_type="simulation_swmm", network_id=proj_id)

    # Exécution de la tâche
    result = run_swmm_simulation_task(
        job_id=job.id,
        org_id=org_id,
        network_id=proj_id,
        scenario_pluie="pluie_decennale",
        duree_heures=12.0,
    )

    assert result["simulation_id"] == job.id
    assert "kpis" in result
    assert result["kpis"]["status"] == "COMPLETED"
    assert result["kpis"]["total_inflow_m3"] > 0

    # Vérification dans ArtifactStore
    storage = get_storage()
    assert storage.exists(result["inp_key"]) is True
    assert storage.exists(result["rpt_key"]) is True
    assert storage.exists(result["summary_key"]) is True

    # Vérification du job en DB
    db.refresh(job)
    assert job.status == "completed"
    assert job.progress == 100
    assert "summary_key" in job.result_refs

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
