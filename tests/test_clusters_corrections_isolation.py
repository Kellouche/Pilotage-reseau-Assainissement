# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Lot A1 — Tests d'Isolation Multi-Tenant Clusters & Corrections (J3)
Objet : Vérifie le rejet anonyme (401), le contrôle RBAC (403),
        le stealth 404 inter-organisations et l'absence de fuite.
================================================================================
"""

import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.database import SessionLocal
from api.models import Organization, User, Membership, Project, Canalisation, Cluster
from api.core.auth import create_access_token


@pytest.fixture
def cluster_isolation_setup():
    db = SessionLocal()
    try:
        # Nettoyage préalable
        db.query(Membership).filter(Membership.org_id.in_(["org_cl_a", "org_cl_b"])).delete(synchronize_session=False)
        db.query(Cluster).filter(Cluster.org_id.in_(["org_cl_a", "org_cl_b"])).delete(synchronize_session=False)
        db.query(Canalisation).filter(Canalisation.org_id.in_(["org_cl_a", "org_cl_b"])).delete(synchronize_session=False)
        db.query(Project).filter(Project.org_id.in_(["org_cl_a", "org_cl_b"])).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(["user_cl_a", "user_cl_b", "viewer_cl_a", "admin_cl_a"])).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.id.in_(["org_cl_a", "org_cl_b"])).delete(synchronize_session=False)
        db.commit()

        # Création Org A et Org B
        org_a = Organization(id="org_cl_a", name="Org Clusters A", slug="org-cl-a", billing_plan="pro", is_active=True)
        org_b = Organization(id="org_cl_b", name="Org Clusters B", slug="org-cl-b", billing_plan="pro", is_active=True)
        db.add_all([org_a, org_b])
        db.commit()

        # Utilisateurs
        admin_a = User(id="admin_cl_a", email="admin_cl_a@example.com", is_active=True, email_verified=True, password_hash="dummy")
        eng_a = User(id="user_cl_a", email="eng_cl_a@example.com", is_active=True, email_verified=True, password_hash="dummy")
        view_a = User(id="viewer_cl_a", email="view_cl_a@example.com", is_active=True, email_verified=True, password_hash="dummy")
        eng_b = User(id="user_cl_b", email="eng_cl_b@example.com", is_active=True, email_verified=True, password_hash="dummy")
        db.add_all([admin_a, eng_a, view_a, eng_b])
        db.commit()

        # Memberships
        db.add_all([
            Membership(user_id="admin_cl_a", org_id="org_cl_a", role="admin"),
            Membership(user_id="user_cl_a", org_id="org_cl_a", role="engineer"),
            Membership(user_id="viewer_cl_a", org_id="org_cl_a", role="viewer"),
            Membership(user_id="user_cl_b", org_id="org_cl_b", role="engineer"),
        ])
        db.commit()

        # Clusters et conduites isolés
        cl_a = Cluster(id=9901, nom="Bassin A", org_id="org_cl_a", longueur_totale=125.0)
        cl_b = Cluster(id=9902, nom="Bassin B", org_id="org_cl_b", longueur_totale=80.0)
        cond_a = Canalisation(fid="COND_A_001", org_id="org_cl_a", longueur=50.0, diametre=400)
        cond_b = Canalisation(fid="COND_B_001", org_id="org_cl_b", longueur=60.0, diametre=500)
        db.add_all([cl_a, cl_b, cond_a, cond_b])
        db.commit()

        token_admin_a = create_access_token({"sub": "admin_cl_a", "type": "access"})
        token_eng_a = create_access_token({"sub": "user_cl_a", "type": "access"})
        token_view_a = create_access_token({"sub": "viewer_cl_a", "type": "access"})
        token_eng_b = create_access_token({"sub": "user_cl_b", "type": "access"})

        yield {
            "token_admin_a": token_admin_a,
            "token_eng_a": token_eng_a,
            "token_view_a": token_view_a,
            "token_eng_b": token_eng_b,
            "cl_a_id": cl_a.id,
            "cl_b_id": cl_b.id,
            "cond_a_fid": cond_a.fid,
            "cond_b_fid": cond_b.fid,
        }
    finally:
        db.query(Membership).filter(Membership.org_id.in_(["org_cl_a", "org_cl_b"])).delete(synchronize_session=False)
        db.query(Cluster).filter(Cluster.org_id.in_(["org_cl_a", "org_cl_b"])).delete(synchronize_session=False)
        db.query(Canalisation).filter(Canalisation.org_id.in_(["org_cl_a", "org_cl_b"])).delete(synchronize_session=False)
        db.query(Project).filter(Project.org_id.in_(["org_cl_a", "org_cl_b"])).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(["user_cl_a", "user_cl_b", "viewer_cl_a", "admin_cl_a"])).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.id.in_(["org_cl_a", "org_cl_b"])).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_clusters_corrections_anonymous_rejected():
    client = TestClient(app)
    unauth_urls = [
        ("GET", "/api/v1/clusters"),
        ("GET", "/api/v1/clusters/status"),
        ("GET", "/api/v1/clusters/9901"),
        ("POST", "/api/v1/clusters/graph/rebuild"),
        ("GET", "/api/v1/corrections/hybride/suggestable_fids"),
        ("GET", "/api/v1/corrections/profile/COND_A_001"),
        ("POST", "/api/v1/corrections/manuel/COND_A_001"),
        ("POST", "/api/v1/corrections/automatique"),
    ]
    for method, url in unauth_urls:
        resp = client.request(method, url)
        assert resp.status_code == 401, f"{method} {url} aurait dû renvoyer 401, reçu {resp.status_code}"


def test_clusters_corrections_isolation_and_stealth_404(cluster_isolation_setup):
    client = TestClient(app)
    headers_a = {"Authorization": f"Bearer {cluster_isolation_setup['token_eng_a']}"}
    headers_b = {"Authorization": f"Bearer {cluster_isolation_setup['token_eng_b']}"}

    # 1. Org A liste ses clusters et voit le sien
    resp_a = client.get("/api/v1/clusters", headers=headers_a)
    assert resp_a.status_code == 200
    ids_a = [c["id"] for c in resp_a.json()["clusters"]]
    assert cluster_isolation_setup["cl_a_id"] in ids_a
    assert cluster_isolation_setup["cl_b_id"] not in ids_a

    # 2. Org B tente d'accéder au cluster de Org A -> Stealth 404
    cl_a_id = cluster_isolation_setup["cl_a_id"]
    resp_cl_cross = client.get(f"/api/v1/clusters/{cl_a_id}", headers=headers_b)
    assert resp_cl_cross.status_code == 404
    assert resp_cl_cross.json()["detail"] == "Ressource introuvable"

    # 3. Org B tente d'accéder au profil conduite de Org A -> Stealth 404
    cond_a_fid = cluster_isolation_setup["cond_a_fid"]
    resp_prof_cross = client.get(f"/api/v1/corrections/profile/{cond_a_fid}", headers=headers_b)
    assert resp_prof_cross.status_code == 404
    assert resp_prof_cross.json()["detail"] == "Ressource introuvable"

    # 4. Org B tente de corriger la conduite de Org A -> Stealth 404
    resp_patch_cross = client.post(
        f"/api/v1/corrections/manuel/{cond_a_fid}",
        headers=headers_b,
        json={"prof_fe_am": 1.5}
    )
    assert resp_patch_cross.status_code == 404
    assert resp_patch_cross.json()["detail"] == "Ressource introuvable"


def test_clusters_corrections_rbac(cluster_isolation_setup):
    client = TestClient(app)
    headers_view = {"Authorization": f"Bearer {cluster_isolation_setup['token_view_a']}"}
    headers_admin = {"Authorization": f"Bearer {cluster_isolation_setup['token_admin_a']}"}

    # Viewer n'a pas le droit de lancer rebuild du graph (admin requis) -> 403
    resp_rebuild = client.post("/api/v1/clusters/graph/rebuild", headers=headers_view)
    assert resp_rebuild.status_code == 403

    # Admin a le droit -> 200
    resp_rebuild_ok = client.post("/api/v1/clusters/graph/rebuild", headers=headers_admin)
    assert resp_rebuild_ok.status_code == 200

    # Viewer n'a pas le droit de faire correction manuelle (engineer requis) -> 403
    cond_a_fid = cluster_isolation_setup["cond_a_fid"]
    resp_man = client.post(
        f"/api/v1/corrections/manuel/{cond_a_fid}",
        headers=headers_view,
        json={"prof_fe_am": 2.0}
    )
    assert resp_man.status_code == 403
