# -*- coding: utf-8 -*-
"""
Tests API du système de jobs asynchrones : lancement sécurisé et téléchargement d'artefacts.
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


# ============================================================
# LOT 3C.7.2 — Sécurisation identité et lancement asynchrone
# ============================================================

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

    # 1. Org A télécharge son propre fichier (contexte projet déclaré) -> 200 OK
    resp_a = download_artifact(key=key_a, project_id=proj_a, tenant=tenant_a, db=db)
    assert resp_a.body == content
    assert resp_a.media_type == "application/pdf"

    # 1b. Sans project_id sur une clé projet -> refus (contexte ambigu)
    with pytest.raises(HTTPException) as exc_no_proj:
        download_artifact(key=key_a, project_id=None, tenant=tenant_a, db=db)
    assert exc_no_proj.value.status_code == 404

    # 2. Org B tente de télécharger le fichier de Org A -> Stealth 404
    with pytest.raises(HTTPException) as exc_info_b:
        download_artifact(key=key_a, project_id=proj_a, tenant=tenant_b, db=db)
    assert exc_info_b.value.status_code == 404

    # 3. Tentative de traversée de répertoire -> Stealth 404
    hack_key = f"{org_a.id}/../../etc/shadow"
    with pytest.raises(HTTPException) as exc_info_hack:
        download_artifact(key=hack_key, project_id=None, tenant=tenant_a, db=db)
    assert exc_info_hack.value.status_code == 404

    db.close()


def test_artifact_download_isolation_projet(test_setup):
    """3C.7.5 — une clé d'un AUTRE projet de la même organisation est refusée
    lorsque le contexte projet déclaré ne correspond pas."""
    db = SessionLocal()
    org_a = db.query(Organization).filter_by(id=test_setup["org_a_id"]).first()
    user_a = db.query(User).filter_by(email="ingenieur@regie-alpha.dz").first()
    tenant_a = TenantContext(actor=user_a, org=org_a, role="admin")

    proj_a = test_setup["proj_a_id"]
    proj_b = Project(id="proj_alpha_b", org_id=org_a.id, name="Réseau Est", slug="net-est-b")
    db.add(proj_b)
    db.commit()

    try:
        storage = get_storage()
        key_b = f"{org_a.id}/{proj_b.id}/reports/secret.pdf"
        storage.put_bytes(key_b, b"%PDF secret projet B", content_type="application/pdf")

        # Contexte projet A + clé projet B -> 404
        with pytest.raises(HTTPException) as exc:
            download_artifact(key=key_b, project_id=proj_a, tenant=tenant_a, db=db)
        assert exc.value.status_code == 404

        # Contexte projet B déclaré + clé projet B -> 200 (même org)
        resp = download_artifact(key=key_b, project_id=proj_b.id, tenant=tenant_a, db=db)
        assert resp.body == b"%PDF secret projet B"

        # Segment non-projet (licences) : contrôle org seul, comportement legacy
        key_lic = f"{org_a.id}/licences/bc_001_justificatif.pdf"
        storage.put_bytes(key_lic, b"pdf-licence", content_type="application/pdf")
        resp_lic = download_artifact(key=key_lic, project_id=None, tenant=tenant_a, db=db)
        assert resp_lic.body == b"pdf-licence"
    finally:
        # Nettoyage : la base de test est partagée avec d'autres modules
        db.delete(proj_b)
        db.commit()
        db.close()


def test_artifact_download_isolation_inter_org(test_setup):
    """Contrôle final — isolation inter-organisation des clés ResultStore.

    Sept cas : le second segment de la clé est classifié en base ;
    un Project.id d'une autre organisation n'est JAMAIS assimilé à un
    chemin legacy non-projet."""
    db = SessionLocal()
    org_a = db.query(Organization).filter_by(id=test_setup["org_a_id"]).first()
    org_b = db.query(Organization).filter_by(id=test_setup["org_b_id"]).first()
    user_a = db.query(User).filter_by(email="ingenieur@regie-alpha.dz").first()
    tenant_a = TenantContext(actor=user_a, org=org_a, role="admin")

    proj_a = test_setup["proj_a_id"]
    # Projet appartenant à l'organisation B (absent du fixture)
    proj_b = Project(id="proj_beta_id", org_id=org_b.id, name="Réseau Beta", slug="net-beta")
    db.add(proj_b)
    db.commit()

    try:
        storage = get_storage()
        payload = b'{"result": "ok"}'

        # Artefact projet A (stocké sous le préfixe org A)
        key_a = f"{org_a.id}/{proj_a}/simulations/sim_1/result.json"
        storage.put_bytes(key_a, payload, content_type="application/json")

        # Cas 1 : clé projet A + project_id=proj_A -> autorisé
        resp = download_artifact(key=key_a, project_id=proj_a, tenant=tenant_a, db=db)
        assert resp.body == payload

        # Cas 2 : clé projet A sans project_id -> 404
        with pytest.raises(HTTPException) as e2:
            download_artifact(key=key_a, project_id=None, tenant=tenant_a, db=db)
        assert e2.value.status_code == 404

        # Clé craftée : préfixe org A mais segment = Project.id de l'org B
        key_cross = f"{org_a.id}/{proj_b.id}/simulations/sim_x/result.json"
        storage.put_bytes(key_cross, payload, content_type="application/json")

        # Cas 3 : clé cross-org + project_id=proj_B -> 404
        with pytest.raises(HTTPException) as e3:
            download_artifact(key=key_cross, project_id=proj_b.id, tenant=tenant_a, db=db)
        assert e3.value.status_code == 404

        # Cas 4 : clé cross-org SANS project_id -> 404
        # (avant correction : assimilée à un chemin legacy -> fuite)
        with pytest.raises(HTTPException) as e4:
            download_artifact(key=key_cross, project_id=None, tenant=tenant_a, db=db)
        assert e4.value.status_code == 404

        # Cas 5 : clé sous le préfixe org B, tenant A -> 404 (stealth)
        key_b = f"{org_b.id}/{proj_b.id}/simulations/sim_1/result.json"
        storage.put_bytes(key_b, payload, content_type="application/json")
        with pytest.raises(HTTPException) as e5:
            download_artifact(key=key_b, project_id=proj_b.id, tenant=tenant_a, db=db)
        assert e5.value.status_code == 404

        # Cas 6 : véritable clé non-projet legacy -> comportement conservé
        key_lic = f"{org_a.id}/licences/bc_001_justificatif.pdf"
        storage.put_bytes(key_lic, b"pdf-licence", content_type="application/pdf")
        resp_lic = download_artifact(key=key_lic, project_id=None, tenant=tenant_a, db=db)
        assert resp_lic.body == b"pdf-licence"

        # Cas 7 : clé non-projet + project_id fourni -> 404 par prudence
        with pytest.raises(HTTPException) as e7:
            download_artifact(key=key_lic, project_id=proj_a, tenant=tenant_a, db=db)
        assert e7.value.status_code == 404
    finally:
        db.delete(proj_b)
        db.commit()
        db.close()
