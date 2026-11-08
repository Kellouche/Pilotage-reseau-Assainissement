"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Tests de chargement et d'intégrité du réseau de démonstration
================================================================================
"""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
from api.main import app
from api.database import SessionLocal, engine, Base
from api.models import User, Organization, Membership, Project

@pytest.fixture(autouse=True)
def clean_test_env():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.query(Membership).delete()
    db.query(Project).delete()
    db.query(User).delete()
    db.query(Organization).delete()
    db.commit()
    db.close()
    yield


def test_load_demo_and_detect_clusters():
    client = TestClient(app)
    # 1. Register and verify user
    reg_resp = client.post("/api/v1/auth/register", json={
        "email": "demo.tester@example.com",
        "password": "SecurePassword123!",
        "full_name": "Demo Tester",
        "org_name": "Demo Test Org",
        "plan_type": "pro"
    })
    assert reg_resp.status_code == 201
    dev_code = reg_resp.json()["dev_code"]

    verify_resp = client.post("/api/v1/auth/verify-email", json={
        "email": "demo.tester@example.com",
        "code": dev_code
    })
    assert verify_resp.status_code == 200
    vdata = verify_resp.json()
    token = vdata.get("access_token") or vdata.get("tokens", {}).get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Initially layers should report virgin workspace
    layers_empty = client.get("/api/v1/layers", headers=headers)
    assert layers_empty.status_code == 200
    assert layers_empty.json()["is_empty"] is True

    # 3. Load demo network
    load_resp = client.post("/api/v1/network/load-demo", headers=headers)
    assert load_resp.status_code == 200
    assert load_resp.json()["status"] == "ok"
    assert load_resp.json()["project"]["pipes_count"] == 58

    # 4. Check /api/v1/layers now returns demo features
    layers_demo = client.get("/api/v1/layers", headers=headers)
    assert layers_demo.status_code == 200
    d = layers_demo.json()
    assert d["is_empty"] is False
    assert d["compteurs"]["conduites"] == 58
    assert d["compteurs"]["regards"] == 59
    assert d["compteurs"]["rejets"] == 1

    # 5. Test recalculate clusters on demo network
    clusters_resp = client.post("/api/v1/clusters/recalculate-all?persist=false", headers=headers)
    assert clusters_resp.status_code == 200
    cdata = clusters_resp.json()
    assert cdata["clusters_crees"] >= 1
    assert len(cdata["resultats"]) >= 1
    first_bassin = cdata["resultats"][0]
    nb_troncons = first_bassin.get("troncons") or first_bassin.get("infrastructures", {}).get("conduites", 0)
    nb_noeuds = first_bassin.get("infrastructures", {}).get("regards", 0)
    assert nb_troncons == 58
    assert nb_noeuds == 59


