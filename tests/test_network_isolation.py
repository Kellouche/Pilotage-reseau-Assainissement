# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Lot A1 — Tests d'Isolation Multi-Tenant du Routeur Réseau (J2)
Objet : Vérifie le rejet anonyme (401), le contrôle RBAC (403),
        le stealth 404 inter-organisations et l'absence de fuite de données.
================================================================================
"""

import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.database import SessionLocal
from api.models import Organization, User, Membership, Project, Regard, Canalisation
from api.core.auth import create_access_token


@pytest.fixture
def isolation_setup():
    db = SessionLocal()
    try:
        # Nettoyage préalable
        db.query(Membership).filter(Membership.org_id.in_(["org_net_a", "org_net_b"])).delete(synchronize_session=False)
        db.query(Regard).filter(Regard.org_id.in_(["org_net_a", "org_net_b"])).delete(synchronize_session=False)
        db.query(Canalisation).filter(Canalisation.org_id.in_(["org_net_a", "org_net_b"])).delete(synchronize_session=False)
        db.query(Project).filter(Project.org_id.in_(["org_net_a", "org_net_b"])).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(["user_net_a", "user_net_b", "viewer_net_a"])).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.id.in_(["org_net_a", "org_net_b"])).delete(synchronize_session=False)
        db.commit()

        # Création Org A et Org B
        org_a = Organization(id="org_net_a", name="Org Réseau A", slug="org-net-a", billing_plan="pro", is_active=True)
        org_b = Organization(id="org_net_b", name="Org Réseau B", slug="org-net-b", billing_plan="pro", is_active=True)
        db.add_all([org_a, org_b])
        db.commit()

        # Utilisateurs
        user_a = User(id="user_net_a", email="eng_a@example.com", is_active=True, email_verified=True, password_hash="dummy")
        viewer_a = User(id="viewer_net_a", email="view_a@example.com", is_active=True, email_verified=True, password_hash="dummy")
        user_b = User(id="user_net_b", email="eng_b@example.com", is_active=True, email_verified=True, password_hash="dummy")
        db.add_all([user_a, viewer_a, user_b])
        db.commit()

        # Memberships
        m_a = Membership(user_id="user_net_a", org_id="org_net_a", role="engineer")
        m_v_a = Membership(user_id="viewer_net_a", org_id="org_net_a", role="viewer")
        m_b = Membership(user_id="user_net_b", org_id="org_net_b", role="engineer")
        db.add_all([m_a, m_v_a, m_b])
        db.commit()

        # Données réseau étanches
        regard_a = Regard(code="REG-A-001", org_id="org_net_a", latitude=36.1, longitude=1.3)
        regard_b = Regard(code="REG-B-001", org_id="org_net_b", latitude=36.2, longitude=1.4)
        db.add_all([regard_a, regard_b])
        db.commit()

        token_eng_a = create_access_token({"sub": "user_net_a", "type": "access"})
        token_view_a = create_access_token({"sub": "viewer_net_a", "type": "access"})
        token_eng_b = create_access_token({"sub": "user_net_b", "type": "access"})

        yield {
            "token_eng_a": token_eng_a,
            "token_view_a": token_view_a,
            "token_eng_b": token_eng_b,
            "regard_a_id": regard_a.id,
            "regard_b_id": regard_b.id,
        }
    finally:
        db.query(Membership).filter(Membership.org_id.in_(["org_net_a", "org_net_b"])).delete(synchronize_session=False)
        db.query(Regard).filter(Regard.org_id.in_(["org_net_a", "org_net_b"])).delete(synchronize_session=False)
        db.query(Canalisation).filter(Canalisation.org_id.in_(["org_net_a", "org_net_b"])).delete(synchronize_session=False)
        db.query(Project).filter(Project.org_id.in_(["org_net_a", "org_net_b"])).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(["user_net_a", "user_net_b", "viewer_net_a"])).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.id.in_(["org_net_a", "org_net_b"])).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_network_anonymous_rejected():
    client = TestClient(app)
    unauth_urls = [
        ("GET", "/api/v1/network/regards"),
        ("GET", "/api/v1/network/conduites"),
        ("GET", "/api/v1/network/rejets"),
        ("POST", "/api/v1/network/load-dataset/epa_example1"),
        ("GET", "/api/v1/network/subcatchments"),
        ("GET", "/api/v1/network/orphelins/geojson"),
        ("GET", "/api/v1/network/export/inp"),
    ]
    for method, url in unauth_urls:
        resp = client.request(method, url)
        assert resp.status_code == 401, f"{method} {url} aurait dû être refusé en 401, reçu {resp.status_code}"


def test_network_isolation_and_stealth_404(isolation_setup):
    client = TestClient(app)
    headers_a = {"Authorization": f"Bearer {isolation_setup['token_eng_a']}"}
    headers_b = {"Authorization": f"Bearer {isolation_setup['token_eng_b']}"}

    # 1. Org A liste ses regards et voit uniquement les siens
    resp_a = client.get("/api/v1/network/regards", headers=headers_a)
    assert resp_a.status_code == 200
    codes_a = [r["code"] for r in resp_a.json()["regards"]]
    assert "REG-A-001" in codes_a
    assert "REG-B-001" not in codes_a

    # 2. Org B tente d'accéder au regard de Org A -> Stealth 404
    regard_a_id = isolation_setup["regard_a_id"]
    resp_cross = client.get(f"/api/v1/network/regards/{regard_a_id}", headers=headers_b)
    assert resp_cross.status_code == 404
    assert resp_cross.json()["detail"] == "Ressource introuvable"

    # 3. Org B tente de PATCH le regard de Org A -> Stealth 404
    resp_patch_cross = client.patch(
        f"/api/v1/network/regards/{regard_a_id}",
        headers=headers_b,
        json={"notes": "Tentative intrusion cross-tenant"}
    )
    assert resp_patch_cross.status_code == 404
    assert resp_patch_cross.json()["detail"] == "Ressource introuvable"

    # 4. Org B tente de DELETE le regard de Org A -> Stealth 404
    resp_del_cross = client.delete(
        f"/api/v1/network/regards/{regard_a_id}",
        headers=headers_b
    )
    assert resp_del_cross.status_code == 404
    assert resp_del_cross.json()["detail"] == "Ressource introuvable"


def test_network_rbac_viewer_forbidden_on_write(isolation_setup):
    client = TestClient(app)
    headers_view_a = {"Authorization": f"Bearer {isolation_setup['token_view_a']}"}

    # Viewer tente de créer un regard -> 403 Forbidden
    resp = client.post(
        "/api/v1/network/regards",
        headers=headers_view_a,
        json={"code": "REG-VIEW-FAIL", "latitude": 36.1, "longitude": 1.3}
    )
    assert resp.status_code == 403
