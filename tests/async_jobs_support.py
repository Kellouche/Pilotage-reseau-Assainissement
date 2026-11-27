# -*- coding: utf-8 -*-
"""
Support partagé des tests de jobs asynchrones : fixtures et helpers.
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
from api.core.security import TenantContext

@pytest.fixture(scope="module", autouse=True)
def init_db_schema():
    """Garantit que le schéma complet existe dans la base de test."""
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        Base.metadata.drop_all(bind=conn)
        Base.metadata.create_all(bind=conn)
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")


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

def _construire_tenant(db, org_id, email):
    """Construit un TenantContext réel pour les tests directs de route."""
    org = db.query(Organization).filter_by(id=org_id).first()
    user = db.query(User).filter_by(email=email).first()
    return TenantContext(actor=user, org=org, role="admin")
