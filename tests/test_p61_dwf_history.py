# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : LOT P6.1 — Tests de l'historique métier DWF (apports_dwf_history)

Couvre :
  - Traçabilité de création (action create, snapshot new_state, user_id).
  - Traçabilité de modification (action update, changed_fields, previous/new).
  - Traçabilité du changement de nœud (action node_change distincte).
  - Traçabilité de l'activation et désactivation (actions activate et deactivate).
  - Traçabilité de la réconciliation explicite (action reconcile).
  - Traçabilité de l'exclusion de simulation (action sim_exclusion).
  - Traçabilité et persistance post-suppression (DELETE puis GET /history).
  - Protection anti-cascade (RESTRICT sur project_id et org_id).
  - Atomicité transactionnelle avec injection contrôlée d'erreur (fault injection).
  - Isolation multi-tenant stricte (stealth 404 cross-tenant).
  - Consultation paginée et filtrage par action.
  - Validation des actions autorisées.
  - Réversibilité de la migration Alembic (upgrade/downgrade canonique).
================================================================================
"""

import importlib.util
from pathlib import Path
from unittest.mock import patch
import uuid
import pytest
from starlette.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from api.main import app
from api.database import SessionLocal, engine, Base
from api.models import (
    Organization, User, Membership, Project, ApportDwf, ApportDwfHistory,
)
from api.core.auth import hash_password, create_access_token
from api.services.apports_dwf_history_service import (
    enregistrer_historique_apport,
    enregistrer_exclusion_simulation,
    lister_historique_apport,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
GPKG_DEMO = REPO_ROOT / "data" / "demo_reseau.gpkg"


@pytest.fixture(scope="module", autouse=True)
def init_db():
    Base.metadata.create_all(bind=engine)


def _creer_gpkg_test(chemin: Path, codes_nodes):
    """Crée un GPKG minimal avec une couche regards."""
    import geopandas as gpd
    from shapely.geometry import Point
    gdf = gpd.GeoDataFrame(
        {"Code": list(codes_nodes)},
        geometry=[Point(i * 10.0, i * 10.0) for i in range(len(codes_nodes))],
        crs="EPSG:32631",
    )
    gdf.to_file(str(chemin), layer="regards", driver="GPKG")


@pytest.fixture
def ctx_p61(tmp_path):
    """Fixture avec deux organisations isolées A et B."""
    gpkg_a = tmp_path / "reseau_a.gpkg"
    gpkg_b = tmp_path / "reseau_b.gpkg"
    _creer_gpkg_test(gpkg_a, ["REG_A1", "REG_A2", "REG_A3"])
    _creer_gpkg_test(gpkg_b, ["REG_B1", "REG_B2"])

    db = SessionLocal()
    prefix = f"p61_{uuid.uuid4().hex[:6]}"

    def _org(uid):
        return Organization(id=f"{prefix}_{uid}", name=f"Org {uid}",
                            slug=f"org-{uid}-{prefix}")

    def _user(uid, email, role="engineer"):
        return User(id=f"{prefix}_u_{uid}", email=email,
                    password_hash=hash_password("DwfPass2026!"),
                    full_name=f"User {uid}", email_verified=True)

    org_a, org_b = _org("a"), _org("b")
    user_a, user_b = _user("a", f"a_{prefix}@p61.dz"), _user("b", f"b_{prefix}@p61.dz")
    mem_a = Membership(org_id=org_a.id, user_id=user_a.id, role="engineer")
    mem_b = Membership(org_id=org_b.id, user_id=user_b.id, role="engineer")

    proj_a = Project(
        id=f"{prefix}_pa", org_id=org_a.id, name="Projet A",
        slug=f"pa-{prefix}", source_gpkg_key=str(gpkg_a),
        is_archived=False,
    )
    proj_b = Project(
        id=f"{prefix}_pb", org_id=org_b.id, name="Projet B",
        slug=f"pb-{prefix}", source_gpkg_key=str(gpkg_b),
        is_archived=False,
    )

    db.add_all([org_a, org_b, user_a, user_b, mem_a, mem_b, proj_a, proj_b])
    db.commit()

    token_a = create_access_token({"sub": user_a.id, "org_id": org_a.id, "role": "engineer"})
    token_b = create_access_token({"sub": user_b.id, "org_id": org_b.id, "role": "engineer"})

    client_a = TestClient(app, headers={"Authorization": f"Bearer {token_a}"})
    client_b = TestClient(app, headers={"Authorization": f"Bearer {token_b}"})

    yield {
        "db": db,
        "org_a": org_a,
        "org_b": org_b,
        "user_a": user_a,
        "user_b": user_b,
        "proj_a": proj_a,
        "proj_b": proj_b,
        "client_a": client_a,
        "client_b": client_b,
    }

    # Nettoyage
    try:
        db.query(ApportDwfHistory).filter(
            ApportDwfHistory.org_id.in_([org_a.id, org_b.id])).delete()
        db.query(ApportDwf).filter(
            ApportDwf.org_id.in_([org_a.id, org_b.id])).delete()
        db.query(Project).filter(
            Project.org_id.in_([org_a.id, org_b.id])).delete()
        db.query(Membership).filter(
            Membership.org_id.in_([org_a.id, org_b.id])).delete()
        db.query(User).filter(
            User.id.in_([user_a.id, user_b.id])).delete()
        db.query(Organization).filter(
            Organization.id.in_([org_a.id, org_b.id])).delete()
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def test_history_creation_on_create(ctx_p61):
    """Créer un apport enregistre immédiatement une entrée 'create' avec son snapshot."""
    client = ctx_p61["client_a"]
    proj_id = ctx_p61["proj_a"].id
    user_id = ctx_p61["user_a"].id

    resp = client.post("/api/v1/apports", json={
        "project_id": proj_id,
        "node_id": "REG_A1",
        "nature": "domestique",
        "mode_determination": "debit",
        "debit_moyen_m3s": 0.015,
        "actif": True,
        "observations": "Création test P6.1",
    })
    assert resp.status_code == 201, resp.text
    apport_id = resp.json()["id"]

    h_resp = client.get(f"/api/v1/apports/{apport_id}/history")
    assert h_resp.status_code == 200, h_resp.text
    data = h_resp.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["action"] == "create"
    assert item["apport_id"] == apport_id
    assert item["project_id"] == proj_id
    assert item["changed_by_id"] == user_id
    assert item["previous_state"] is None
    assert item["new_state"]["node_id"] == "REG_A1"
    assert item["new_state"]["debit_moyen_m3s"] == 0.015


def test_history_on_update_debit(ctx_p61):
    """Modifier un champ métier (débit) trace l'action 'update' avec anciens/nouveaux snapshots."""
    client = ctx_p61["client_a"]
    proj_id = ctx_p61["proj_a"].id

    c_resp = client.post("/api/v1/apports", json={
        "project_id": proj_id,
        "node_id": "REG_A1",
        "nature": "domestique",
        "mode_determination": "debit",
        "debit_moyen_m3s": 0.010,
    })
    apport_id = c_resp.json()["id"]

    u_resp = client.put(f"/api/v1/apports/{apport_id}", json={
        "debit_moyen_m3s": 0.025,
        "observations": "Débit revu à la hausse",
    })
    assert u_resp.status_code == 200

    h_resp = client.get(f"/api/v1/apports/{apport_id}/history")
    assert h_resp.status_code == 200
    items = h_resp.json()["items"]
    assert len(items) == 2
    last_event = items[0]
    assert last_event["action"] == "update"
    assert "debit_moyen_m3s" in last_event["changed_fields"]
    assert last_event["previous_state"]["debit_moyen_m3s"] == 0.010
    assert last_event["new_state"]["debit_moyen_m3s"] == 0.025


def test_history_on_node_change(ctx_p61):
    """Changer de nœud trace l'événement métier dédié 'node_change'."""
    client = ctx_p61["client_a"]
    proj_id = ctx_p61["proj_a"].id

    c_resp = client.post("/api/v1/apports", json={
        "project_id": proj_id,
        "node_id": "REG_A1",
        "nature": "industriel",
        "mode_determination": "debit",
        "debit_moyen_m3s": 0.005,
    })
    apport_id = c_resp.json()["id"]

    u_resp = client.put(f"/api/v1/apports/{apport_id}", json={
        "node_id": "REG_A2",
    })
    assert u_resp.status_code == 200

    h_resp = client.get(f"/api/v1/apports/{apport_id}/history")
    items = h_resp.json()["items"]
    last_event = items[0]
    # L'événement métier doit être explicitement node_change (non un simple update)
    assert last_event["action"] == "node_change"
    assert "node_id" in last_event["changed_fields"]
    assert last_event["previous_state"]["node_id"] == "REG_A1"
    assert last_event["new_state"]["node_id"] == "REG_A2"


def test_history_on_activation_and_deactivation(ctx_p61):
    """Le basculement d'état trace spécifiquement 'activate' ou 'deactivate'."""
    client = ctx_p61["client_a"]
    proj_id = ctx_p61["proj_a"].id

    c_resp = client.post("/api/v1/apports", json={
        "project_id": proj_id,
        "node_id": "REG_A1",
        "nature": "domestique",
        "mode_determination": "debit",
        "debit_moyen_m3s": 0.010,
        "actif": True,
    })
    apport_id = c_resp.json()["id"]

    # 1. Désactivation -> deactivate
    d_resp = client.put(f"/api/v1/apports/{apport_id}", json={"actif": False})
    assert d_resp.status_code == 200

    # 2. Réactivation -> activate
    a_resp = client.put(f"/api/v1/apports/{apport_id}", json={"actif": True})
    assert a_resp.status_code == 200

    h_resp = client.get(f"/api/v1/apports/{apport_id}/history")
    items = h_resp.json()["items"]
    assert len(items) == 3
    # Ordre antichronologique : activate, deactivate, create
    assert items[0]["action"] == "activate"
    assert items[0]["previous_state"]["actif"] is False
    assert items[0]["new_state"]["actif"] is True

    assert items[1]["action"] == "deactivate"
    assert items[1]["previous_state"]["actif"] is True
    assert items[1]["new_state"]["actif"] is False


def test_history_on_reconcile(ctx_p61):
    """La réconciliation explicite est tracée sous l'action canonique 'reconcile'."""
    client = ctx_p61["client_a"]
    proj_id = ctx_p61["proj_a"].id

    c_resp = client.post("/api/v1/apports", json={
        "project_id": proj_id,
        "node_id": "REG_A1",
        "nature": "domestique",
        "mode_determination": "debit",
        "debit_moyen_m3s": 0.010,
    })
    apport_id = c_resp.json()["id"]

    r_resp = client.post(f"/api/v1/apports/{apport_id}/revalider")
    assert r_resp.status_code == 200

    h_resp = client.get(f"/api/v1/apports/{apport_id}/history")
    items = h_resp.json()["items"]
    last_event = items[0]
    # L'action canonique est 'reconcile'
    assert last_event["action"] == "reconcile"


def test_history_on_sim_exclusion(ctx_p61):
    """L'exclusion d'un apport lors d'une simulation trace l'action 'sim_exclusion'."""
    db = ctx_p61["db"]
    org_id = ctx_p61["org_a"].id
    proj_id = ctx_p61["proj_a"].id

    hist = enregistrer_exclusion_simulation(
        db=db,
        apport_id="apport-exclu-123",
        org_id=org_id,
        project_id=proj_id,
        simulation_id="sim-456",
        motif="noeud_absent_du_snapshot",
        details={"node_id": "REG_OBSOLETE", "reason": "noeud supprimé du gpkg"},
        user_id=ctx_p61["user_a"].id,
    )
    db.commit()

    assert hist.action == "sim_exclusion"
    assert hist.new_state["simulation_id"] == "sim-456"
    assert hist.new_state["motif"] == "noeud_absent_du_snapshot"


def test_history_persists_after_delete(ctx_p61):
    """
    Règle de conformité majeure : même après suppression physique de l'apport,
    son historique complet reste disponible et consultable (audit légal).
    """
    client = ctx_p61["client_a"]
    proj_id = ctx_p61["proj_a"].id

    c_resp = client.post("/api/v1/apports", json={
        "project_id": proj_id,
        "node_id": "REG_A3",
        "nature": "infiltration",
        "mode_determination": "debit",
        "debit_moyen_m3s": 0.002,
    })
    apport_id = c_resp.json()["id"]

    client.put(f"/api/v1/apports/{apport_id}", json={"debit_moyen_m3s": 0.004})

    del_resp = client.delete(f"/api/v1/apports/{apport_id}")
    assert del_resp.status_code == 204

    get_resp = client.get(f"/api/v1/apports/{apport_id}")
    assert get_resp.status_code == 404

    h_resp = client.get(f"/api/v1/apports/{apport_id}/history")
    assert h_resp.status_code == 200, h_resp.text
    data = h_resp.json()
    assert data["total"] == 3
    actions = [item["action"] for item in data["items"]]
    assert actions == ["delete", "update", "create"]
    assert data["items"][0]["previous_state"]["debit_moyen_m3s"] == 0.004
    assert data["items"][0]["new_state"] is None


def test_history_anti_cascade_protects_against_project_or_org_deletion(ctx_p61):
    """
    Protection anti-cascade stricte :
    Une suppression de Project ou Organization portant de l'historique est BLOQUÉE
    par intégrité référentielle RESTRICT (aucune suppression silencieuse des traces).
    """
    db = SessionLocal()
    prefix = f"anticad_{uuid.uuid4().hex[:6]}"
    org = Organization(id=f"{prefix}_o", name="O Cascade", slug=f"{prefix}-o")
    proj = Project(id=f"{prefix}_p", org_id=org.id, name="P Cascade", slug=f"{prefix}-p", is_archived=False)
    db.add_all([org, proj])
    db.commit()

    # Créer un enregistrement d'historique
    hist = enregistrer_historique_apport(
        db=db,
        apport_id="app-1",
        org_id=org.id,
        project_id=proj.id,
        action="create",
        new_state={"node_id": "N1"},
    )
    db.commit()

    # Tentative de suppression du projet -> rejetée par RESTRICT
    with pytest.raises(IntegrityError):
        db.delete(proj)
        db.commit()
    db.rollback()

    # Tentative de suppression de l'organisation -> rejetée par RESTRICT
    with pytest.raises(IntegrityError):
        db.delete(org)
        db.commit()
    db.rollback()

    # Nettoyage ordonné
    db.delete(hist)
    db.delete(proj)
    db.delete(org)
    db.commit()
    db.close()


def test_history_fault_injection_rolls_back_apport_mutation(ctx_p61):
    """
    Atomicité transactionnelle démontrée par injection de panne :
    Si l'écriture d'historique échoue au cours de la mutation, la mutation
    métier est intégralement annulée (statut HTTP 500, apport inchangé en base).
    """
    client = ctx_p61["client_a"]
    db = ctx_p61["db"]
    proj_id = ctx_p61["proj_a"].id

    # 1. Créer un apport normalement
    c_resp = client.post("/api/v1/apports", json={
        "project_id": proj_id,
        "node_id": "REG_A1",
        "nature": "domestique",
        "mode_determination": "debit",
        "debit_moyen_m3s": 0.010,
    })
    apport_id = c_resp.json()["id"]

    # 2. Injecter une panne forcée lors de l'enregistrement d'historique sur PUT
    client_safe = TestClient(app, raise_server_exceptions=False, headers=client.headers)
    with patch(
        "api.routes.apports.enregistrer_historique_apport",
        side_effect=RuntimeError("Panne simulée d'écriture d'historique P6.1"),
    ):
        put_resp = client_safe.put(f"/api/v1/apports/{apport_id}", json={
            "debit_moyen_m3s": 0.999,
        })
        # L'appel doit échouer avec HTTP 500
        assert put_resp.status_code == 500

    # 3. Vérifier que la mutation métier a été annulée (rollback effectif)
    db.expire_all()
    apport_db = db.get(ApportDwf, apport_id)
    assert apport_db.debit_moyen_m3s == 0.010  # Débit inchangé !
    assert apport_db.debit_moyen_m3s != 0.999


def test_history_multitenant_isolation(ctx_p61):
    """Isolation multi-tenant stricte : stealth 404 cross-tenant."""
    client_a = ctx_p61["client_a"]
    client_b = ctx_p61["client_b"]
    proj_a = ctx_p61["proj_a"]
    proj_b = ctx_p61["proj_b"]

    resp_a = client_a.post("/api/v1/apports", json={
        "project_id": proj_a.id,
        "node_id": "REG_A1",
        "nature": "domestique",
        "mode_determination": "debit",
        "debit_moyen_m3s": 0.010,
    })
    apport_a_id = resp_a.json()["id"]

    resp_b = client_b.post("/api/v1/apports", json={
        "project_id": proj_b.id,
        "node_id": "REG_B1",
        "nature": "domestique",
        "mode_determination": "debit",
        "debit_moyen_m3s": 0.020,
    })
    apport_b_id = resp_b.json()["id"]

    # B tente de consulter l'historique d'un apport de A -> 404 furtif
    cross_resp = client_b.get(f"/api/v1/apports/{apport_a_id}/history")
    assert cross_resp.status_code == 404

    # B tente de consulter l'historique du projet A -> 404 furtif
    cross_proj_resp = client_b.get(f"/api/v1/apports/history?project_id={proj_a.id}")
    assert cross_proj_resp.status_code == 404

    # Consultation globale du projet B : ne contient QUE les événements de B
    hist_b = client_b.get(f"/api/v1/apports/history?project_id={proj_b.id}")
    assert hist_b.status_code == 200
    for it in hist_b.json()["items"]:
        assert it["org_id"] == ctx_p61["org_b"].id
        assert it["project_id"] == proj_b.id


def test_history_pagination_and_filters(ctx_p61):
    """Pagination skip/limit et filtre par action sur la route projet."""
    client = ctx_p61["client_a"]
    proj_id = ctx_p61["proj_a"].id

    ids = []
    for i in range(3):
        r = client.post("/api/v1/apports", json={
            "project_id": proj_id,
            "node_id": "REG_A1",
            "nature": "domestique",
            "mode_determination": "debit",
            "debit_moyen_m3s": 0.010 + i * 0.001,
        })
        ids.append(r.json()["id"])

    client.put(f"/api/v1/apports/{ids[0]}", json={"debit_moyen_m3s": 0.050})

    p1 = client.get(f"/api/v1/apports/history?project_id={proj_id}&skip=0&limit=2")
    assert p1.status_code == 200
    d1 = p1.json()
    assert d1["limit"] == 2
    assert d1["skip"] == 0
    assert len(d1["items"]) == 2
    assert d1["total"] >= 4

    fu = client.get(f"/api/v1/apports/history?project_id={proj_id}&action=update")
    assert fu.status_code == 200
    items_u = fu.json()["items"]
    assert all(it["action"] == "update" for it in items_u)

    fc = client.get(f"/api/v1/apports/history?project_id={proj_id}&action=create")
    assert fc.status_code == 200
    items_c = fc.json()["items"]
    assert all(it["action"] == "create" for it in items_c)


def test_history_invalid_action_rejected(ctx_p61):
    """Une action non reconnue lève une ValueError explicite."""
    db = ctx_p61["db"]
    with pytest.raises(ValueError, match="Action 'invalide' non reconnue"):
        enregistrer_historique_apport(
            db=db,
            apport_id="x",
            org_id="y",
            project_id="z",
            action="invalide",
        )


def test_alembic_migration_reversibility():
    """
    Vérifie la réversibilité de la migration Alembic e5f6a7b8c9d0 (upgrade puis downgrade canonique)
    sans aucune condition masquante, sur un moteur temporaire dédié.
    """
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    mig_path = REPO_ROOT / "alembic" / "versions" / "e5f6a7b8c9d0_apports_dwf_history.py"
    spec = importlib.util.spec_from_file_location("mig_e5f6", str(mig_path))
    assert spec is not None and spec.loader is not None
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)

    temp_engine = create_engine("sqlite:///:memory:")
    with temp_engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        op = Operations(ctx)

        conn.execute(text("CREATE TABLE organizations (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
        conn.commit()

        orig_op = mig.op
        mig.op = op
        try:
            # 1. UPGRADE
            mig.upgrade()
            inspector = inspect(conn)
            assert "apports_dwf_history" in inspector.get_table_names()
            cols = [c["name"] for c in inspector.get_columns("apports_dwf_history")]
            assert "id" in cols
            assert "apport_id" in cols
            assert "action" in cols
            assert "changed_fields" in cols
            assert "previous_state" in cols
            assert "new_state" in cols

            # 2. DOWNGRADE
            mig.downgrade()
            inspector = inspect(conn)
            assert "apports_dwf_history" not in inspector.get_table_names()
        finally:
            mig.op = orig_op
