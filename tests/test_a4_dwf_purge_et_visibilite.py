# -*- coding: utf-8 -*-
"""
Tests unitaires et d'intégration pour les fonctionnalités DWF :
- Purge des apports orphelins (POST /api/v1/apports/purger-orphelins)
- Filtrage par réseau courant (GET /api/v1/apports?reseau_courant_seulement=true)
"""
import uuid
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.database import SessionLocal, Base, engine
from api.models import Organization, User, Membership, Project, ApportDwf, GpkgVersion
from api.core.auth import create_access_token

client = TestClient(app)


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def setup_test_dwf(db_session):
    slug_uid = uuid.uuid4().hex[:6]
    org = Organization(
        id=f"org_dwf_{slug_uid}",
        name=f"Org DWF {slug_uid}",
        slug=f"org-dwf-{slug_uid}"
    )
    user = User(
        id=f"usr_dwf_{slug_uid}",
        email=f"eng_{slug_uid}@test.fr",
        password_hash="hash",
        is_active=True,
        email_verified=True,
    )
    db_session.add_all([org, user])
    db_session.flush()

    mem = Membership(
        org_id=org.id,
        user_id=user.id,
        role="engineer"
    )
    proj = Project(
        id=f"prj_dwf_{slug_uid}",
        org_id=org.id,
        name=f"Projet DWF {slug_uid}",
        slug=f"prj-dwf-{slug_uid}",
        source_gpkg_key="data/demo_reseau.gpkg",
        is_archived=False,
    )
    db_session.add_all([mem, proj])
    db_session.commit()

    token = create_access_token(data={"sub": user.id, "org_id": org.id})
    headers = {"Authorization": f"Bearer {token}"}

    return {
        "org": org,
        "user": user,
        "project": proj,
        "headers": headers,
    }


def test_purger_apports_orphelins(setup_test_dwf, db_session):
    proj = setup_test_dwf["project"]
    org = setup_test_dwf["org"]
    headers = setup_test_dwf["headers"]

    # Création de deux apports sur des nœuds qui n'existent pas dans le réseau
    app1 = ApportDwf(
        id=str(uuid.uuid4()),
        org_id=org.id,
        project_id=proj.id,
        code_apport="AP-2026-9001",
        node_id="NOEUD_INEXISTANT_1",
        nature="domestique",
        mode_determination="debit",
        debit_moyen_m3s=0.001,
        profile_key="constant",
        actif=True
    )
    app2 = ApportDwf(
        id=str(uuid.uuid4()),
        org_id=org.id,
        project_id=proj.id,
        code_apport="AP-2026-9002",
        node_id="NOEUD_INEXISTANT_2",
        nature="domestique",
        mode_determination="debit",
        debit_moyen_m3s=0.002,
        profile_key="constant",
        actif=True
    )
    db_session.add_all([app1, app2])
    db_session.commit()

    # Appel endpoint purge
    r = client.post(f"/api/v1/apports/purger-orphelins?project_id={proj.id}", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "success"
    assert data["supprimes_count"] == 2

    # Vérification que la table ne contient plus ces apports
    restants = db_session.query(ApportDwf).filter_by(project_id=proj.id).count()
    assert restants == 0


def test_lister_apports_filtre_reseau_courant(setup_test_dwf, db_session):
    proj = setup_test_dwf["project"]
    org = setup_test_dwf["org"]
    headers = setup_test_dwf["headers"]

    v1_id = str(uuid.uuid4())
    v2_id = str(uuid.uuid4())

    v1 = GpkgVersion(
        id=v1_id,
        org_id=org.id,
        project_id=proj.id,
        sha256="1" * 64,
        size_bytes=100,
        storage_kind="LEGACY_LOCAL",
        storage_ref="data/demo_reseau.gpkg"
    )
    v2 = GpkgVersion(
        id=v2_id,
        org_id=org.id,
        project_id=proj.id,
        sha256="2" * 64,
        size_bytes=100,
        storage_kind="LEGACY_LOCAL",
        storage_ref="data/demo_reseau.gpkg"
    )
    db_session.add_all([v1, v2])

    proj.gpkg_version_id = v2_id
    db_session.commit()

    app_old = ApportDwf(
        id=str(uuid.uuid4()),
        org_id=org.id,
        project_id=proj.id,
        code_apport="AP-2026-8001",
        node_id="N_OLD",
        nature="domestique",
        mode_determination="debit",
        debit_moyen_m3s=0.001,
        profile_key="constant",
        gpkg_version_id=v1_id,
        actif=True
    )
    app_new = ApportDwf(
        id=str(uuid.uuid4()),
        org_id=org.id,
        project_id=proj.id,
        code_apport="AP-2026-8002",
        node_id="N_NEW",
        nature="domestique",
        mode_determination="debit",
        debit_moyen_m3s=0.002,
        profile_key="constant",
        gpkg_version_id=v2_id,
        actif=True
    )
    db_session.add_all([app_old, app_new])
    db_session.commit()

    # Sans filtre : retourne les 2
    r_all = client.get(f"/api/v1/apports?project_id={proj.id}", headers=headers)
    assert r_all.status_code == 200
    assert len(r_all.json()) == 2

    # Avec reseau_courant_seulement : ne retourne que le nouveau
    r_cur = client.get(f"/api/v1/apports?project_id={proj.id}&reseau_courant_seulement=true", headers=headers)
    assert r_cur.status_code == 200
    res_cur = r_cur.json()
    assert len(res_cur) == 1
    assert res_cur[0]["code_apport"] == "AP-2026-8002"
