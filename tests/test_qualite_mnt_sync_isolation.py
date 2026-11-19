# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Lot A1 — Tests d'Isolation Multi-Tenant Qualité, MNT et Sync (J5)
Objet : Vérifie le rejet anonyme (401), le contrôle RBAC (403),
        l'isolation stricte des deltas de synchronisation et des opérations MNT/Qualité.
================================================================================
"""

import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.database import SessionLocal
from api.models import Organization, User, Membership, Project, Canalisation, Regard
from api.models_terrain import Inspection, Incident
from api.core.auth import create_access_token


@pytest.fixture
def qms_isolation_setup():
    db = SessionLocal()
    try:
        # Nettoyage préalable
        db.query(Membership).filter(Membership.org_id.in_(["org_qms_a", "org_qms_b"])).delete(synchronize_session=False)
        db.query(Inspection).filter(Inspection.org_id.in_(["org_qms_a", "org_qms_b"])).delete(synchronize_session=False)
        db.query(Incident).filter(Incident.org_id.in_(["org_qms_a", "org_qms_b"])).delete(synchronize_session=False)
        db.query(Regard).filter(Regard.org_id.in_(["org_qms_a", "org_qms_b"])).delete(synchronize_session=False)
        db.query(Canalisation).filter(Canalisation.org_id.in_(["org_qms_a", "org_qms_b"])).delete(synchronize_session=False)
        db.query(Project).filter(Project.org_id.in_(["org_qms_a", "org_qms_b"])).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(["user_qms_a", "user_qms_b", "viewer_qms_a", "admin_qms_a"])).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.id.in_(["org_qms_a", "org_qms_b"])).delete(synchronize_session=False)
        db.commit()

        # Création Org A et Org B
        org_a = Organization(id="org_qms_a", name="Org QMS A", slug="org-qms-a", billing_plan="pro", is_active=True)
        org_b = Organization(id="org_qms_b", name="Org QMS B", slug="org-qms-b", billing_plan="pro", is_active=True)
        db.add_all([org_a, org_b])
        db.commit()

        # Utilisateurs
        admin_a = User(id="admin_qms_a", email="admin_qms_a@example.com", is_active=True, email_verified=True, password_hash="dummy")
        eng_a = User(id="user_qms_a", email="eng_qms_a@example.com", is_active=True, email_verified=True, password_hash="dummy")
        view_a = User(id="viewer_qms_a", email="view_qms_a@example.com", is_active=True, email_verified=True, password_hash="dummy")
        eng_b = User(id="user_qms_b", email="eng_qms_b@example.com", is_active=True, email_verified=True, password_hash="dummy")
        db.add_all([admin_a, eng_a, view_a, eng_b])
        db.commit()

        # Memberships
        db.add_all([
            Membership(user_id="admin_qms_a", org_id="org_qms_a", role="admin"),
            Membership(user_id="user_qms_a", org_id="org_qms_a", role="engineer"),
            Membership(user_id="viewer_qms_a", org_id="org_qms_a", role="viewer"),
            Membership(user_id="user_qms_b", org_id="org_qms_b", role="engineer"),
        ])
        db.commit()

        # Regard et conduite pour Org A
        regard_a = Regard(code="NOD_QMS_A_01", org_id="org_qms_a", profondeur=2.0, version=1)
        cond_a = Canalisation(fid="COND_QMS_A_01", org_id="org_qms_a", longueur=45.0, diametre=300, version=1)
        # Regard et conduite pour Org B
        regard_b = Regard(code="NOD_QMS_B_01", org_id="org_qms_b", profondeur=3.0, version=2)
        cond_b = Canalisation(fid="COND_QMS_B_01", org_id="org_qms_b", longueur=55.0, diametre=400, version=2)
        db.add_all([regard_a, cond_a, regard_b, cond_b])
        db.commit()

        token_admin_a = create_access_token({"sub": "admin_qms_a", "type": "access"})
        token_eng_a = create_access_token({"sub": "user_qms_a", "type": "access"})
        token_view_a = create_access_token({"sub": "viewer_qms_a", "type": "access"})
        token_eng_b = create_access_token({"sub": "user_qms_b", "type": "access"})

        yield {
            "token_admin_a": token_admin_a,
            "token_eng_a": token_eng_a,
            "token_view_a": token_view_a,
            "token_eng_b": token_eng_b,
            "regard_a_id": regard_a.id,
            "regard_b_id": regard_b.id,
            "cond_a_fid": cond_a.fid,
            "cond_b_fid": cond_b.fid,
        }
    finally:
        db.query(Membership).filter(Membership.org_id.in_(["org_qms_a", "org_qms_b"])).delete(synchronize_session=False)
        db.query(Inspection).filter(Inspection.org_id.in_(["org_qms_a", "org_qms_b"])).delete(synchronize_session=False)
        db.query(Incident).filter(Incident.org_id.in_(["org_qms_a", "org_qms_b"])).delete(synchronize_session=False)
        db.query(Regard).filter(Regard.org_id.in_(["org_qms_a", "org_qms_b"])).delete(synchronize_session=False)
        db.query(Canalisation).filter(Canalisation.org_id.in_(["org_qms_a", "org_qms_b"])).delete(synchronize_session=False)
        db.query(Project).filter(Project.org_id.in_(["org_qms_a", "org_qms_b"])).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(["user_qms_a", "user_qms_b", "viewer_qms_a", "admin_qms_a"])).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.id.in_(["org_qms_a", "org_qms_b"])).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_qualite_mnt_sync_anonymous_rejected():
    client = TestClient(app)
    unauthorized_endpoints = [
        # Qualite
        ("GET", "/api/v1/qualite/analyse"),
        ("GET", "/api/v1/qualite/diagnostic"),
        ("GET", "/api/v1/qualite/anomalies/pente_faible"),
        ("GET", "/api/v1/qualite/scores"),
        ("GET", "/api/v1/qualite/statistiques"),
        ("POST", "/api/v1/qualite/valider-incremental"),
        ("GET", "/api/v1/qualite/scores-bassins"),
        ("POST", "/api/v1/qualite/export-csv"),
        ("GET", "/api/v1/qualite/cache/status"),
        ("DELETE", "/api/v1/qualite/cache"),
        # MNT
        ("GET", "/api/v1/mnt/statut"),
        ("GET", "/api/v1/mnt/cache/status"),
        ("POST", "/api/v1/mnt/analyser-bassins"),
        ("DELETE", "/api/v1/mnt/cache"),
        # Sync
        ("GET", "/api/v1/sync/delta?since_version=0"),
        ("POST", "/api/v1/sync/push"),
        ("POST", "/api/v1/sync/session?device_id=test_dev"),
    ]

    for method, path in unauthorized_endpoints:
        if method == "GET":
            resp = client.get(path)
        elif method == "POST":
            resp = client.post(path, json={})
        elif method == "DELETE":
            resp = client.delete(path)
        assert resp.status_code == 401, f"{method} {path} should return 401 for anonymous caller, got {resp.status_code}"


def test_qualite_mnt_sync_rbac_forbidden(qms_isolation_setup):
    client = TestClient(app)
    viewer_headers = {"Authorization": f"Bearer {qms_isolation_setup['token_view_a']}"}

    # DELETE /qualite/cache -> admin only
    resp = client.delete("/api/v1/qualite/cache", headers=viewer_headers)
    assert resp.status_code == 403

    # POST /qualite/valider-incremental -> engineer
    resp = client.post("/api/v1/qualite/valider-incremental", headers=viewer_headers, json={"conduite_ids": []})
    assert resp.status_code == 403

    # DELETE /mnt/cache -> admin only
    resp = client.delete("/api/v1/mnt/cache", headers=viewer_headers)
    assert resp.status_code == 403

    # POST /mnt/analyser-bassins -> engineer
    resp = client.post("/api/v1/mnt/analyser-bassins", headers=viewer_headers, json={})
    assert resp.status_code == 403

    # POST /sync/push -> engineer
    resp = client.post("/api/v1/sync/push", headers=viewer_headers, json={"device_id": "dev1", "changes": []})
    assert resp.status_code == 403


def test_sync_delta_isolation(qms_isolation_setup):
    client = TestClient(app)
    headers_a = {"Authorization": f"Bearer {qms_isolation_setup['token_eng_a']}"}
    headers_b = {"Authorization": f"Bearer {qms_isolation_setup['token_eng_b']}"}

    # Org A requests delta since version 0
    resp_a = client.get("/api/v1/sync/delta?since_version=0&tables=regards,conduites", headers=headers_a)
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert data_a["version"] >= 1
    # Check that changes only contain Org A elements
    features_a = [c["feature_id"] for c in data_a["changes"]]
    for change in data_a["changes"]:
        assert change["changes"].get("org_id") == "org_qms_a"

    # Org B requests delta since version 0
    resp_b = client.get("/api/v1/sync/delta?since_version=0&tables=regards,conduites", headers=headers_b)
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    assert data_b["version"] >= 2
    for change in data_b["changes"]:
        assert change["changes"].get("org_id") == "org_qms_b"


def test_sync_session_registered(qms_isolation_setup):
    client = TestClient(app)
    headers_a = {"Authorization": f"Bearer {qms_isolation_setup['token_view_a']}"}
    resp = client.post("/api/v1/sync/session?device_id=handheld_42", headers=headers_a)
    assert resp.status_code == 200
    assert resp.json()["registered"] is True


def test_sync_push_creates_and_isolates_records(qms_isolation_setup):
    from api.routes.sync import _SYNC_RATE_LIMITS
    _SYNC_RATE_LIMITS.clear()

    client = TestClient(app)
    headers_a = {"Authorization": f"Bearer {qms_isolation_setup['token_eng_a']}"}
    headers_b = {"Authorization": f"Bearer {qms_isolation_setup['token_eng_b']}"}

    # Org A pushes a new inspection and regard
    push_payload_a = {
        "device_id": "phone_a",
        "client_timestamp": "2026-11-19T06:00:00Z",
        "changes": [
            {
                "type": "create",
                "layer": "regards",
                "feature_id": "NEW_REG_A",
                "changes": {
                    "code": "NOD_NEW_A_99",
                    "profondeur": 1.75
                }
            }
        ]
    }
    resp_a = client.post("/api/v1/sync/push", headers=headers_a, json=push_payload_a)
    assert resp_a.status_code == 200
    assert resp_a.json()["accepted"] == 1

    # Verify that Org B cannot see this new regard in delta
    _SYNC_RATE_LIMITS.clear()
    resp_b_delta = client.get("/api/v1/sync/delta?since_version=0&tables=regards", headers=headers_b)
    assert resp_b_delta.status_code == 200
    b_codes = [c["changes"].get("code") for c in resp_b_delta.json()["changes"]]
    assert "NOD_NEW_A_99" not in b_codes

