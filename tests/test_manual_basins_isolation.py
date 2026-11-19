# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Lot A1 — Tests d'Isolation Multi-Tenant Bassins Manuels & Surfaces Mortes (J4)
Objet : Vérifie le partitionnement strict des bassins manuels par org_id,
        le rejet anonyme (401), le contrôle RBAC (403), le stealth 404,
        et la disparition effective des anciennes surfaces supprimées.
================================================================================
"""

import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.database import SessionLocal
from api.models import Organization, User, Membership
from api.core.auth import create_access_token


@pytest.fixture
def manual_basins_setup():
    db = SessionLocal()
    try:
        # Nettoyage préalable
        db.query(Membership).filter(Membership.org_id.in_(["org_mb_a", "org_mb_b"])).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(["admin_mb_a", "viewer_mb_a", "admin_mb_b"])).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.id.in_(["org_mb_a", "org_mb_b"])).delete(synchronize_session=False)
        db.commit()

        # Création des organisations
        org_a = Organization(id="org_mb_a", name="Org MB A", slug="org-mb-a", billing_plan="pro", is_active=True)
        org_b = Organization(id="org_mb_b", name="Org MB B", slug="org-mb-b", billing_plan="pro", is_active=True)
        db.add_all([org_a, org_b])
        db.commit()

        # Utilisateurs
        admin_a = User(id="admin_mb_a", email="admin_mb_a@example.com", is_active=True, email_verified=True, password_hash="dummy")
        view_a = User(id="viewer_mb_a", email="viewer_mb_a@example.com", is_active=True, email_verified=True, password_hash="dummy")
        admin_b = User(id="admin_mb_b", email="admin_mb_b@example.com", is_active=True, email_verified=True, password_hash="dummy")
        db.add_all([admin_a, view_a, admin_b])
        db.commit()

        # Memberships
        db.add_all([
            Membership(user_id="admin_mb_a", org_id="org_mb_a", role="admin"),
            Membership(user_id="viewer_mb_a", org_id="org_mb_a", role="viewer"),
            Membership(user_id="admin_mb_b", org_id="org_mb_b", role="admin"),
        ])
        db.commit()

        # Jetons d'accès
        token_admin_a = create_access_token({"sub": "admin_mb_a", "org_id": "org_mb_a", "role": "admin"})
        token_view_a = create_access_token({"sub": "viewer_mb_a", "org_id": "org_mb_a", "role": "viewer"})
        token_admin_b = create_access_token({"sub": "admin_mb_b", "org_id": "org_mb_b", "role": "admin"})

        yield {
            "token_admin_a": token_admin_a,
            "token_view_a": token_view_a,
            "token_admin_b": token_admin_b,
        }
    finally:
        db.query(Membership).filter(Membership.org_id.in_(["org_mb_a", "org_mb_b"])).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(["admin_mb_a", "viewer_mb_a", "admin_mb_b"])).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.id.in_(["org_mb_a", "org_mb_b"])).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_dead_surfaces_removed():
    """Les 5 surfaces mortes / alias supprimés renvoient 404 (ou 405)."""
    client = TestClient(app)
    # Les 3 alias racine /api/v1/manual-basin n'existent plus
    assert client.get("/api/v1/manual-basin").status_code == 404
    assert client.post("/api/v1/manual-basin", json={}).status_code == 404
    assert client.delete("/api/v1/manual-basin/M_1").status_code == 404


def test_anonymous_rejected():
    """Les routes /api/v1/clusters/manual-basin rejettent les requêtes anonymes (401)."""
    client = TestClient(app)
    assert client.get("/api/v1/clusters/manual-basin").status_code == 401
    assert client.post("/api/v1/clusters/manual-basin", json={"nom": "Test"}).status_code == 401
    assert client.delete("/api/v1/clusters/manual-basin/M_1").status_code == 401


def test_rbac_controls(manual_basins_setup):
    """Un rôle viewer ne peut pas modifier les bassins manuels (admin requis)."""
    client = TestClient(app)
    view_headers = {"Authorization": f"Bearer {manual_basins_setup['token_view_a']}"}
    r = client.post("/api/v1/clusters/manual-basin", json={"nom": "Bassin Interdit"}, headers=view_headers)
    assert r.status_code == 403

    r = client.delete("/api/v1/clusters/manual-basin/M_1", headers=view_headers)
    assert r.status_code == 403


def test_strict_tenant_isolation_manual_basins(manual_basins_setup):
    """
    Cloisonnement strict multi-tenant :
    - Admin A crée un bassin manuel.
    - Admin A le voit dans sa liste.
    - Admin B ne voit rien (0 bassin).
    - Admin B tente de supprimer le bassin de A -> Stealth 404 {"detail": "Ressource introuvable"}.
    - Admin A supprime son bassin avec succès.
    """
    client = TestClient(app)
    headers_a = {"Authorization": f"Bearer {manual_basins_setup['token_admin_a']}"}
    headers_b = {"Authorization": f"Bearer {manual_basins_setup['token_admin_b']}"}

    # 1. Admin A crée un bassin
    payload = {
        "conduites": ["C1", "C2"],
        "nom": "Bassin Manuel Org A",
        "exutoire": {"nom": "Ex1", "type": "rejet"}
    }
    r_create = client.post("/api/v1/clusters/manual-basin", json=payload, headers=headers_a)
    assert r_create.status_code == 200, r_create.text
    bassin = r_create.json()
    b_id = bassin["id"]

    try:
        # 2. Admin A le voit
        r_list_a = client.get("/api/v1/clusters/manual-basin", headers=headers_a)
        assert r_list_a.status_code == 200, f"Error GET manual-basin: {r_list_a.status_code} - {r_list_a.text}"
        ids_a = [b["id"] for b in r_list_a.json()]
        assert b_id in ids_a

        # 3. Admin B ne le voit PAS
        r_list_b = client.get("/api/v1/clusters/manual-basin", headers=headers_b)
        assert r_list_b.status_code == 200
        ids_b = [b["id"] for b in r_list_b.json()]
        assert b_id not in ids_b

        # 4. Admin B tente de supprimer le bassin de A -> Stealth 404
        r_del_b = client.delete(f"/api/v1/clusters/manual-basin/M_{b_id}", headers=headers_b)
        assert r_del_b.status_code == 404
        assert r_del_b.json() == {"detail": "Ressource introuvable"}

        # Vérifier que le bassin de A est toujours là
        r_check_a = client.get("/api/v1/clusters/manual-basin", headers=headers_a)
        assert any(b["id"] == b_id for b in r_check_a.json())

    finally:
        # 5. Nettoyage : Admin A supprime son bassin
        r_del_a = client.delete(f"/api/v1/clusters/manual-basin/M_{b_id}", headers=headers_a)
        assert r_del_a.status_code == 200
        assert r_del_a.json() == {"status": "ok"}
