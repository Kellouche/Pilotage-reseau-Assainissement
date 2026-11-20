# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : Test unitaire et d'intégration - Renseignement intelligent des regards DWF
        (filtrage des nœuds connectés, exclusion des orphelins, filtrage par cluster)
================================================================================
"""

import uuid
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from api.main import app
from api.database import SessionLocal
from api.models import Project, User, Organization, Membership
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
    # On pointe vers network_HAY_GAZ_HASSANIA s'il existe, sinon demo_reseau.gpkg
    hay_gaz = Path("uploads/a66e32ad-f32b-4529-acc3-7a6026eb5a8a/network_HAY_GAZ_HASSANIA.gpkg")
    gpkg_key = str(hay_gaz) if hay_gaz.exists() else "data/demo_reseau.gpkg"

    proj = Project(
        id=f"prj_dwf_{slug_uid}",
        org_id=org.id,
        name=f"Projet DWF {slug_uid}",
        slug=f"prj-dwf-{slug_uid}",
        source_gpkg_key=gpkg_key,
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
        "is_hay_gaz": hay_gaz.exists(),
    }


def test_noeuds_intelligents_connectes_seulement(setup_test_dwf):
    proj = setup_test_dwf["project"]
    headers = setup_test_dwf["headers"]

    # 1. Appel par défaut avec connectes_seulement=true
    r = client.get(f"/api/v1/apports/noeuds?project_id={proj.id}&connectes_seulement=true", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["count"] > 0
    assert "noeuds" in data
    assert data["nb_connectes"] == data["count"]

    if setup_test_dwf["is_hay_gaz"]:
        assert "9080" in data["noeuds"]
        assert "55" in data["noeuds"]
        # 12122265 et 100070 sont orphelins, ne doivent PAS être retournés
        assert "12122265" not in data["noeuds"]
        assert "100070" not in data["noeuds"]
        assert data["nb_orphelins"] > 0

        # Vérification du tri naturel : '55' doit être avant '2168' et '9080'
        noeuds = data["noeuds"]
        idx_55 = noeuds.index("55")
        if "2168" in noeuds:
            assert idx_55 < noeuds.index("2168")
        if "9080" in noeuds:
            assert idx_55 < noeuds.index("9080")


def test_noeuds_intelligents_filtre_cluster(setup_test_dwf):
    proj = setup_test_dwf["project"]
    headers = setup_test_dwf["headers"]

    if not setup_test_dwf["is_hay_gaz"]:
        pytest.skip("Test spécifique à HAY_GAZ")

    # Filtrer spécifiquement pour le cluster OUT_55
    r = client.get(f"/api/v1/apports/noeuds?project_id={proj.id}&cluster_id=OUT_55&connectes_seulement=true", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["cluster_id"] == "OUT_55"
    assert "9080" in data["noeuds"]
    assert "55" in data["noeuds"]
    assert "12122265" not in data["noeuds"]


def test_validation_rejet_noeud_orphelin(setup_test_dwf):
    proj = setup_test_dwf["project"]
    headers = setup_test_dwf["headers"]

    if not setup_test_dwf["is_hay_gaz"]:
        pytest.skip("Test spécifique à HAY_GAZ")

    # Tentative d'insertion d'un apport sur un regard orphelin (12122265)
    payload = {
        "project_id": proj.id,
        "node_id": "12122265",
        "nature": "domestique",
        "mode_determination": "debit",
        "debit_moyen_m3s": 0.001,
        "profile_key": "constant",
        "actif": True,
    }
    r = client.post("/api/v1/apports", json=payload, headers=headers)
    assert r.status_code == 422, r.text
    assert "orphelin" in r.text.lower() or "canalisation" in r.text.lower()
