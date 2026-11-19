# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Lot A1 — Tests d'Isolation Multi-Tenant Terrain, Simulations & Couches (J6)
Objet : Vérifie le rejet anonyme (401), le contrôle RBAC (403),
        le stealth 404 inter-organisations et l'absence de fuite cross-tenant sur /layers.
================================================================================
"""

import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.database import SessionLocal
from api.models import Organization, User, Membership, Project
from api.models_terrain import Inspection, Incident
from api.core.auth import create_access_token


@pytest.fixture
def tsl_isolation_setup():
    db = SessionLocal()
    try:
        # Nettoyage préalable
        db.query(Membership).filter(Membership.org_id.in_(["org_tsl_a", "org_tsl_b"])).delete(synchronize_session=False)
        db.query(Inspection).filter(Inspection.org_id.in_(["org_tsl_a", "org_tsl_b"])).delete(synchronize_session=False)
        db.query(Incident).filter(Incident.org_id.in_(["org_tsl_a", "org_tsl_b"])).delete(synchronize_session=False)
        db.query(Project).filter(Project.org_id.in_(["org_tsl_a", "org_tsl_b"])).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(["user_tsl_a", "user_tsl_b", "viewer_tsl_a", "admin_tsl_a"])).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.id.in_(["org_tsl_a", "org_tsl_b"])).delete(synchronize_session=False)
        db.commit()

        # Création Org A et Org B
        org_a = Organization(id="org_tsl_a", name="Org TSL A", slug="org-tsl-a", billing_plan="pro", is_active=True)
        org_b = Organization(id="org_tsl_b", name="Org TSL B", slug="org-tsl-b", billing_plan="pro", is_active=True)
        db.add_all([org_a, org_b])
        db.commit()

        # Utilisateurs
        admin_a = User(id="admin_tsl_a", email="admin_tsl_a@example.com", is_active=True, email_verified=True, password_hash="dummy")
        eng_a = User(id="user_tsl_a", email="eng_tsl_a@example.com", is_active=True, email_verified=True, password_hash="dummy")
        view_a = User(id="viewer_tsl_a", email="view_tsl_a@example.com", is_active=True, email_verified=True, password_hash="dummy")
        eng_b = User(id="user_tsl_b", email="eng_tsl_b@example.com", is_active=True, email_verified=True, password_hash="dummy")
        db.add_all([admin_a, eng_a, view_a, eng_b])
        db.commit()

        # Memberships
        db.add_all([
            Membership(user_id="admin_tsl_a", org_id="org_tsl_a", role="admin"),
            Membership(user_id="user_tsl_a", org_id="org_tsl_a", role="engineer"),
            Membership(user_id="viewer_tsl_a", org_id="org_tsl_a", role="viewer"),
            Membership(user_id="user_tsl_b", org_id="org_tsl_b", role="engineer"),
        ])
        db.commit()

        # Incident et inspection créés pour Org A
        incident_a = Incident(
            org_id="org_tsl_a",
            type_incident="fuite",
            description="Fuite sur conduite principale Org A",
            longitude=2.3522,
            latitude=48.8566,
            statut="À traiter",
            version=1
        )
        inspection_a = Inspection(
            org_id="org_tsl_a",
            object_type="regard",
            object_id="NOD_A_01",
            etat="bon",
            version=1
        )
        db.add_all([incident_a, inspection_a])
        db.commit()

        token_admin_a = create_access_token({"sub": "admin_tsl_a", "type": "access"})
        token_eng_a = create_access_token({"sub": "user_tsl_a", "type": "access"})
        token_view_a = create_access_token({"sub": "viewer_tsl_a", "type": "access"})
        token_eng_b = create_access_token({"sub": "user_tsl_b", "type": "access"})

        yield {
            "token_admin_a": token_admin_a,
            "token_eng_a": token_eng_a,
            "token_view_a": token_view_a,
            "token_eng_b": token_eng_b,
            "incident_a_id": incident_a.id,
            "inspection_a_id": inspection_a.id,
        }
    finally:
        db.query(Membership).filter(Membership.org_id.in_(["org_tsl_a", "org_tsl_b"])).delete(synchronize_session=False)
        db.query(Inspection).filter(Inspection.org_id.in_(["org_tsl_a", "org_tsl_b"])).delete(synchronize_session=False)
        db.query(Incident).filter(Incident.org_id.in_(["org_tsl_a", "org_tsl_b"])).delete(synchronize_session=False)
        db.query(Project).filter(Project.org_id.in_(["org_tsl_a", "org_tsl_b"])).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(["user_tsl_a", "user_tsl_b", "viewer_tsl_a", "admin_tsl_a"])).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.id.in_(["org_tsl_a", "org_tsl_b"])).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_terrain_simulations_layers_anonymous_rejected():
    client = TestClient(app)
    unauthorized_endpoints = [
        ("GET", "/api/v1/layers"),
        ("GET", "/api/v1/terrain/inspections"),
        ("POST", "/api/v1/terrain/inspections"),
        ("GET", "/api/v1/terrain/inspections/regard/NOD_1"),
        ("GET", "/api/v1/terrain/incidents"),
        ("POST", "/api/v1/terrain/incidents"),
        ("PATCH", "/api/v1/terrain/incidents/1"),
        ("GET", "/api/v1/simulations/typologies-sol"),
        ("GET", "/api/v1/simulations/pluviometrie/referentiel"),
        ("GET", "/api/v1/simulations/pluviometrie/stations"),
        ("GET", "/api/v1/simulations/scenarios"),
        ("POST", "/api/v1/simulations/pluviometrie/bms-preview"),
    ]

    for method, path in unauthorized_endpoints:
        if method == "GET":
            resp = client.get(path)
        elif method == "POST":
            resp = client.post(path, json={})
        elif method == "PATCH":
            resp = client.patch(path + "?statut=En+cours")
        assert resp.status_code == 401, f"{method} {path} should return 401 for anonymous caller, got {resp.status_code}"


def test_terrain_rbac_forbidden(tsl_isolation_setup):
    client = TestClient(app)
    viewer_headers = {"Authorization": f"Bearer {tsl_isolation_setup['token_view_a']}"}

    # POST /terrain/inspections -> engineer only
    resp = client.post("/api/v1/terrain/inspections", headers=viewer_headers, json={
        "object_type": "regard", "object_id": "NOD_1"
    })
    assert resp.status_code == 403

    # POST /terrain/incidents -> engineer only
    resp = client.post("/api/v1/terrain/incidents", headers=viewer_headers, json={
        "type_incident": "fuite", "description": "test"
    })
    assert resp.status_code == 403

    # PATCH /terrain/incidents/{id} -> engineer only
    resp = client.patch(f"/api/v1/terrain/incidents/{tsl_isolation_setup['incident_a_id']}?statut=En+cours", headers=viewer_headers)
    assert resp.status_code == 403


def test_terrain_stealth_404_and_isolation(tsl_isolation_setup):
    client = TestClient(app)
    headers_a = {"Authorization": f"Bearer {tsl_isolation_setup['token_eng_a']}"}
    headers_b = {"Authorization": f"Bearer {tsl_isolation_setup['token_eng_b']}"}

    incident_a_id = tsl_isolation_setup["incident_a_id"]

    # Org B attempts to patch Org A's incident -> Stealth 404
    resp_cross = client.patch(f"/api/v1/terrain/incidents/{incident_a_id}?statut=En+cours", headers=headers_b)
    assert resp_cross.status_code == 404
    assert resp_cross.json() == {"detail": "Ressource introuvable"}

    # Org B lists incidents -> does not see Org A's incident
    resp_list_b = client.get("/api/v1/terrain/incidents", headers=headers_b)
    assert resp_list_b.status_code == 200
    ids_b = [inc["id"] for inc in resp_list_b.json()]
    assert incident_a_id not in ids_b

    # Org A patches its own incident -> 200 OK
    resp_patch_a = client.patch(f"/api/v1/terrain/incidents/{incident_a_id}?statut=En+cours", headers=headers_a)
    assert resp_patch_a.status_code == 200
    assert resp_patch_a.json()["statut"] == "En cours"


def test_layers_isolation_no_leak(tsl_isolation_setup):
    client = TestClient(app)
    headers_b = {"Authorization": f"Bearer {tsl_isolation_setup['token_eng_b']}"}

    # Org B has no project or network -> returns empty space (is_empty=True), NEVER Org A's or demo's data
    resp_layers = client.get("/api/v1/layers", headers=headers_b)
    assert resp_layers.status_code == 200
    data = resp_layers.json()
    assert data["is_empty"] is True
    assert data["compteurs"]["conduites"] == 0
    assert data["compteurs"]["regards"] == 0
