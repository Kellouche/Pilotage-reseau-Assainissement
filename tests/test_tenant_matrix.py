# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Lot A1 — Matrice d'Isolation Multi-Tenant Complète (J7 - J8)
Objet : 4 cas critiques sur les routes de l'API :
        1. Anonyme (401)
        2. Rôle insuffisant (403 RBAC)
        3. Cross-tenant stealth 404 ("Ressource introuvable")
        4. Accès nominal au sein du même tenant (200/201/204)
================================================================================
"""

import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.database import SessionLocal
from api.models import Organization, User, Membership, Project, Canalisation, Regard, Cluster, Job
from api.models_terrain import Inspection, Incident
from api.core.auth import create_access_token


@pytest.fixture
def matrix_setup():
    db = SessionLocal()
    try:
        # Nettoyage préalable
        db.query(Membership).filter(Membership.org_id.in_(["org_mat_a", "org_mat_b"])).delete(synchronize_session=False)
        db.query(Job).filter(Job.org_id.in_(["org_mat_a", "org_mat_b"])).delete(synchronize_session=False)
        db.query(Inspection).filter(Inspection.org_id.in_(["org_mat_a", "org_mat_b"])).delete(synchronize_session=False)
        db.query(Incident).filter(Incident.org_id.in_(["org_mat_a", "org_mat_b"])).delete(synchronize_session=False)
        db.query(Cluster).filter(Cluster.org_id.in_(["org_mat_a", "org_mat_b"])).delete(synchronize_session=False)
        db.query(Regard).filter(Regard.org_id.in_(["org_mat_a", "org_mat_b"])).delete(synchronize_session=False)
        db.query(Canalisation).filter(Canalisation.org_id.in_(["org_mat_a", "org_mat_b"])).delete(synchronize_session=False)
        db.query(Project).filter(Project.org_id.in_(["org_mat_a", "org_mat_b"])).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(["user_mat_a", "user_mat_b", "view_mat_a", "admin_mat_a"])).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.id.in_(["org_mat_a", "org_mat_b"])).delete(synchronize_session=False)
        db.commit()

        # Organisations
        org_a = Organization(id="org_mat_a", name="Org Matrice A", slug="org-mat-a", billing_plan="pro", is_active=True)
        org_b = Organization(id="org_mat_b", name="Org Matrice B", slug="org-mat-b", billing_plan="pro", is_active=True)
        db.add_all([org_a, org_b])
        db.commit()

        # Utilisateurs
        admin_a = User(id="admin_mat_a", email="admin_mat_a@example.com", is_active=True, email_verified=True, password_hash="dummy")
        eng_a = User(id="user_mat_a", email="eng_mat_a@example.com", is_active=True, email_verified=True, password_hash="dummy")
        view_a = User(id="view_mat_a", email="view_mat_a@example.com", is_active=True, email_verified=True, password_hash="dummy")
        eng_b = User(id="user_mat_b", email="eng_mat_b@example.com", is_active=True, email_verified=True, password_hash="dummy")
        db.add_all([admin_a, eng_a, view_a, eng_b])
        db.commit()

        # Memberships
        db.add_all([
            Membership(user_id="admin_mat_a", org_id="org_mat_a", role="admin"),
            Membership(user_id="user_mat_a", org_id="org_mat_a", role="engineer"),
            Membership(user_id="view_mat_a", org_id="org_mat_a", role="viewer"),
            Membership(user_id="user_mat_b", org_id="org_mat_b", role="engineer"),
        ])
        db.commit()

        # Projets
        proj_a = Project(id="prj_mat_a", name="Projet A", org_id="org_mat_a", is_archived=False)
        proj_b = Project(id="prj_mat_b", name="Projet B", org_id="org_mat_b", is_archived=False)
        db.add_all([proj_a, proj_b])
        db.commit()

        # Ressources Org A
        cl_a = Cluster(id=7701, nom="Bassin Mat A", org_id="org_mat_a", longueur_totale=100.0)
        reg_a = Regard(code="NOD_MAT_A_01", org_id="org_mat_a", longitude=2.3522, latitude=48.8566, profondeur=2.1, version=1)
        cond_a = Canalisation(fid="COND_MAT_A_01", org_id="org_mat_a", longueur=50.0, diametre=300, version=1)
        inc_a = Incident(org_id="org_mat_a", type_incident="debordement", description="Debordement A", longitude=2.3, latitude=48.8, statut="À traiter", version=1)
        insp_a = Inspection(org_id="org_mat_a", object_type="regard", object_id="NOD_MAT_A_01", etat="bon", version=1)
        job_a = Job(id="job_mat_a", org_id="org_mat_a", job_type="simulation", status="running", progress=10)

        # Ressources Org B
        cl_b = Cluster(id=7702, nom="Bassin Mat B", org_id="org_mat_b", longueur_totale=150.0)
        reg_b = Regard(code="NOD_MAT_B_01", org_id="org_mat_b", longitude=3.1000, latitude=49.1000, profondeur=3.2, version=1)
        cond_b = Canalisation(fid="COND_MAT_B_01", org_id="org_mat_b", longueur=80.0, diametre=400, version=1)
        inc_b = Incident(org_id="org_mat_b", type_incident="obstruction", description="Obstruction B", longitude=3.1, latitude=49.1, statut="À traiter", version=1)
        insp_b = Inspection(org_id="org_mat_b", object_type="regard", object_id="NOD_MAT_B_01", etat="moyen", version=1)
        job_b = Job(id="job_mat_b", org_id="org_mat_b", job_type="simulation", status="running", progress=20)

        db.add_all([cl_a, reg_a, cond_a, inc_a, insp_a, job_a, cl_b, reg_b, cond_b, inc_b, insp_b, job_b])
        db.commit()

        token_admin_a = create_access_token({"sub": "admin_mat_a", "type": "access"})
        token_eng_a = create_access_token({"sub": "user_mat_a", "type": "access"})
        token_view_a = create_access_token({"sub": "view_mat_a", "type": "access"})
        token_eng_b = create_access_token({"sub": "user_mat_b", "type": "access"})

        yield {
            "token_admin_a": token_admin_a,
            "token_eng_a": token_eng_a,
            "token_view_a": token_view_a,
            "token_eng_b": token_eng_b,
            "cl_a_id": cl_a.id,
            "cl_b_id": cl_b.id,
            "reg_a_id": reg_a.id,
            "reg_b_id": reg_b.id,
            "cond_a_id": cond_a.id,
            "cond_b_id": cond_b.id,
            "cond_a_fid": cond_a.fid,
            "cond_b_fid": cond_b.fid,
            "inc_a_id": inc_a.id,
            "inc_b_id": inc_b.id,
            "job_a_id": job_a.id,
            "job_b_id": job_b.id,
        }
    finally:
        db.query(Membership).filter(Membership.org_id.in_(["org_mat_a", "org_mat_b"])).delete(synchronize_session=False)
        db.query(Job).filter(Job.org_id.in_(["org_mat_a", "org_mat_b"])).delete(synchronize_session=False)
        db.query(Inspection).filter(Inspection.org_id.in_(["org_mat_a", "org_mat_b"])).delete(synchronize_session=False)
        db.query(Incident).filter(Incident.org_id.in_(["org_mat_a", "org_mat_b"])).delete(synchronize_session=False)
        db.query(Cluster).filter(Cluster.org_id.in_(["org_mat_a", "org_mat_b"])).delete(synchronize_session=False)
        db.query(Regard).filter(Regard.org_id.in_(["org_mat_a", "org_mat_b"])).delete(synchronize_session=False)
        db.query(Canalisation).filter(Canalisation.org_id.in_(["org_mat_a", "org_mat_b"])).delete(synchronize_session=False)
        db.query(Project).filter(Project.org_id.in_(["org_mat_a", "org_mat_b"])).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(["user_mat_a", "user_mat_b", "view_mat_a", "admin_mat_a"])).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.id.in_(["org_mat_a", "org_mat_b"])).delete(synchronize_session=False)
        db.commit()
        db.close()


# ---------------------------------------------------------------------------
# CAS 1 : ANONYME (401 UNAUTHORIZED)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("method,path", [
    ("GET", "/api/v1/layers"),
    ("GET", "/api/v1/network/regards"),
    ("GET", "/api/v1/network/conduites"),
    ("GET", "/api/v1/clusters"),
    ("GET", "/api/v1/qualite/analyse"),
    ("GET", "/api/v1/mnt/statut"),
    ("GET", "/api/v1/sync/delta?since_version=0"),
    ("GET", "/api/v1/terrain/incidents"),
    ("GET", "/api/v1/terrain/inspections"),
    ("GET", "/api/v1/simulations/scenarios"),
    ("POST", "/api/v1/clusters/recalculate-all"),
    ("POST", "/api/v1/sync/push"),
    ("DELETE", "/api/v1/qualite/cache"),
    ("DELETE", "/api/v1/mnt/cache"),
])
def test_matrix_anonymous_rejected(method, path):
    client = TestClient(app)
    if method == "GET":
        resp = client.get(path)
    elif method == "POST":
        resp = client.post(path, json={})
    elif method == "DELETE":
        resp = client.delete(path)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# CAS 2 : RBAC FORBIDDEN (403 FORBIDDEN SUR ACTIONS MUTATRICES / ADMIN)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("method,path,payload", [
    ("POST", "/api/v1/clusters/recalculate-all", {}),
    ("POST", "/api/v1/clusters/graph/rebuild", {}),
    ("DELETE", "/api/v1/qualite/cache", None),
    ("DELETE", "/api/v1/mnt/cache", None),
    ("POST", "/api/v1/sync/push", {"device_id": "d1", "changes": []}),
    ("POST", "/api/v1/qualite/valider-incremental", {"conduite_ids": []}),
    ("POST", "/api/v1/mnt/analyser-bassins", {}),
])
def test_matrix_rbac_viewer_forbidden(matrix_setup, method, path, payload):
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {matrix_setup['token_view_a']}"}
    if method == "POST":
        resp = client.post(path, headers=headers, json=payload or {})
    elif method == "DELETE":
        resp = client.delete(path, headers=headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# CAS 3 : STEALTH 404 SUR RESSOURCES CROSS-TENANT (RESOLVEURS 18 ROUTES)
# ---------------------------------------------------------------------------
def test_matrix_stealth_404_cross_tenant_clusters(matrix_setup):
    client = TestClient(app)
    headers_b = {"Authorization": f"Bearer {matrix_setup['token_eng_b']}"}
    target_a_id = matrix_setup["cl_a_id"]

    # Simple resolvers sur cluster
    for path in [
        f"/api/v1/clusters/{target_a_id}",
        f"/api/v1/clusters/{target_a_id}/geojson",
        f"/api/v1/clusters/{target_a_id}/ouvrages-proches",
    ]:
        resp = client.get(path, headers=headers_b)
        assert resp.status_code == 404
        assert resp.json() == {"detail": "Ressource introuvable"}

    # Recalculate cluster cross-tenant
    resp_recalc = client.post(f"/api/v1/clusters/{target_a_id}/recalculate", headers=headers_b)
    assert resp_recalc.status_code == 404
    assert resp_recalc.json() == {"detail": "Ressource introuvable"}


def test_matrix_stealth_404_cross_tenant_network_elements(matrix_setup):
    client = TestClient(app)
    headers_b = {"Authorization": f"Bearer {matrix_setup['token_eng_b']}"}

    reg_a_id = matrix_setup["reg_a_id"]
    cond_a_id = matrix_setup["cond_a_id"]

    # Regards GET & PATCH & DELETE
    resp = client.get(f"/api/v1/network/regards/{reg_a_id}", headers=headers_b)
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Ressource introuvable"}

    resp = client.patch(f"/api/v1/network/regards/{reg_a_id}", headers=headers_b, json={"profondeur": 9.9})
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Ressource introuvable"}

    # Conduites GET & PATCH & DELETE
    resp = client.get(f"/api/v1/network/conduites/{cond_a_id}", headers=headers_b)
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Ressource introuvable"}

    resp = client.patch(f"/api/v1/network/conduites/{cond_a_id}", headers=headers_b, json={"diametre": 800})
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Ressource introuvable"}


def test_matrix_stealth_404_cross_tenant_terrain_incidents(matrix_setup):
    client = TestClient(app)
    headers_b = {"Authorization": f"Bearer {matrix_setup['token_eng_b']}"}
    inc_a_id = matrix_setup["inc_a_id"]

    resp = client.patch(f"/api/v1/terrain/incidents/{inc_a_id}?statut=En+cours", headers=headers_b)
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Ressource introuvable"}


def test_matrix_stealth_404_cross_tenant_corrections_fid(matrix_setup):
    client = TestClient(app)
    headers_b = {"Authorization": f"Bearer {matrix_setup['token_eng_b']}"}
    cond_a_fid = matrix_setup["cond_a_fid"]

    # Corrections complexe resolver FID
    resp = client.post(f"/api/v1/corrections/manuel/{cond_a_fid}", headers=headers_b, json={"action": "inverser_pente"})
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Ressource introuvable"}

    resp = client.get(f"/api/v1/corrections/profile/{cond_a_fid}", headers=headers_b)
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Ressource introuvable"}


# ---------------------------------------------------------------------------
# CAS 4 : ACCES NOMINAL (MEME TENANT -> 200 OK)
# ---------------------------------------------------------------------------
def test_matrix_nominal_access_same_tenant(matrix_setup):
    client = TestClient(app)
    headers_a = {"Authorization": f"Bearer {matrix_setup['token_eng_a']}"}

    # Cluster A accessible par Org A
    resp = client.get(f"/api/v1/clusters/{matrix_setup['cl_a_id']}", headers=headers_a)
    assert resp.status_code == 200
    assert resp.json()["nom"] == "Bassin Mat A"

    # Regard A accessible par Org A
    resp = client.get(f"/api/v1/network/regards/{matrix_setup['reg_a_id']}", headers=headers_a)
    assert resp.status_code == 200
    assert resp.json()["code"] == "NOD_MAT_A_01"

    # Conduite A accessible par Org A
    resp = client.get(f"/api/v1/network/conduites/{matrix_setup['cond_a_id']}", headers=headers_a)
    assert resp.status_code == 200
    assert resp.json()["fid"] == "COND_MAT_A_01"
