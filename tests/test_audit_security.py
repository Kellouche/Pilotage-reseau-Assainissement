# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : LOT P6.0-S — Tests de sécurité, authentification, isolation multi-tenant
        et intégrité référentielle SQLite des routes Audit
================================================================================
"""

import pytest
from starlette.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from api.main import app
from api.database import SessionLocal, engine, Base
from api.models import (
    Organization, User, Membership, AuditLog, Regard, Canalisation,
)
from api.core.auth import hash_password, create_access_token


@pytest.fixture(scope="module", autouse=True)
def init_db_schema():
    Base.metadata.create_all(bind=engine)


# ============================================================
# 1. TESTS INTÉGRITÉ RÉFÉRENTIELLE SQLITE (PRAGMA foreign_keys)
# ============================================================

def test_sqlite_foreign_keys_pragma_active():
    """Vérifie que le listener connect active bien PRAGMA foreign_keys=1 sur SQLite."""
    with engine.connect() as conn:
        dialect_name = conn.dialect.name
        if dialect_name == "sqlite":
            val = conn.execute(text("PRAGMA foreign_keys;")).scalar()
            assert val == 1, "PRAGMA foreign_keys doit être égal à 1 pour SQLite."


def test_sqlite_foreign_key_violation_rejected():
    """Vérifie qu'une insertion violant une clé étrangère est effectivement rejetée."""
    db = SessionLocal()
    try:
        # Tenter d'insérer un Membership avec un org_id inexistant
        violating_membership = Membership(
            id="violating_mem_001",
            org_id="non_existent_org_99999",
            user_id="non_existent_user_99999",
            role="viewer"
        )
        db.add(violating_membership)
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


# ============================================================
# FIXTURE MULTI-TENANT AUDIT
# ============================================================

@pytest.fixture
def ctx_audit():
    """Initialise deux organisations étanches A et B avec leurs utilisateurs et logs d'audit."""
    db = SessionLocal()
    prefix = "sec_audit"

    # Nettoyage préalable
    db.query(AuditLog).filter(AuditLog.org_id.in_([f"{prefix}_org_a", f"{prefix}_org_b"])).delete(synchronize_session=False)
    db.query(Regard).filter(Regard.org_id.in_([f"{prefix}_org_a", f"{prefix}_org_b"])).delete(synchronize_session=False)
    db.query(Canalisation).filter(Canalisation.org_id.in_([f"{prefix}_org_a", f"{prefix}_org_b"])).delete(synchronize_session=False)
    db.query(Membership).filter(Membership.org_id.in_([f"{prefix}_org_a", f"{prefix}_org_b"])).delete(synchronize_session=False)
    db.query(User).filter(User.id.in_([f"{prefix}_u_a", f"{prefix}_u_b"])).delete(synchronize_session=False)
    db.query(Organization).filter(Organization.id.in_([f"{prefix}_org_a", f"{prefix}_org_b"])).delete(synchronize_session=False)
    db.commit()

    # Création Organisation A et B
    org_a = Organization(id=f"{prefix}_org_a", name="ONA Chlef", slug=f"{prefix}-ona-chlef", is_active=True)
    org_b = Organization(id=f"{prefix}_org_b", name="SEACO Constantine", slug=f"{prefix}-seaco", is_active=True)
    db.add_all([org_a, org_b])
    db.commit()

    # Création Utilisateurs A et B
    u_a = User(
        id=f"{prefix}_u_a", email=f"{prefix}_a@ona.dz",
        password_hash=hash_password("Secret123!"),
        full_name="Ingénieur A", is_active=True, email_verified=True, is_superadmin=False
    )
    u_b = User(
        id=f"{prefix}_u_b", email=f"{prefix}_b@seaco.dz",
        password_hash=hash_password("Secret123!"),
        full_name="Ingénieur B", is_active=True, email_verified=True, is_superadmin=False
    )
    db.add_all([u_a, u_b])
    db.commit()

    mem_a = Membership(id=f"{prefix}_m_a", org_id=org_a.id, user_id=u_a.id, role="engineer")
    mem_b = Membership(id=f"{prefix}_m_b", org_id=org_b.id, user_id=u_b.id, role="viewer")
    db.add_all([mem_a, mem_b])
    db.commit()

    # Équipements hydrauliques pour Org A
    regard_a = Regard(
        id=98701, org_id=org_a.id, code="REG_CHLEF_01",
        version=2, profondeur=2.5
    )
    conduite_a = Canalisation(
        id=98702, org_id=org_a.id, id_amont="REG_CHLEF_01", id_aval="REG_CHLEF_02",
        diametre=400.0, version=1
    )
    db.add_all([regard_a, conduite_a])
    db.commit()

    # Logs d'audit distincts
    log_a1 = AuditLog(
        id=f"{prefix}_log_a1", org_id=org_a.id, user_id=u_a.id,
        action="network.import", target_type="network", target_id="net_chlef_01",
        details={"nb_regards": 150}
    )
    log_a2 = AuditLog(
        id=f"{prefix}_log_a2", org_id=org_a.id, user_id=u_a.id,
        action="regard.update", target_type="regard", target_id="98701",
        details={"champ": "profondeur", "ancienne": 2.0, "nouvelle": 2.5}
    )
    log_a3 = AuditLog(
        id=f"{prefix}_log_a3", org_id=org_a.id, user_id=u_a.id,
        action="conduite.update", target_type="conduite", target_id="98702",
        details={"champ": "diametre", "valeur": 400.0}
    )
    log_b1 = AuditLog(
        id=f"{prefix}_log_b1", org_id=org_b.id, user_id=u_b.id,
        action="terrain.sync", target_type="incident", target_id="inc_001",
        details={"statut": "resolu"}
    )
    db.add_all([log_a1, log_a2, log_a3, log_b1])
    db.commit()
    db.close()

    token_a = create_access_token({"sub": f"{prefix}_u_a", "type": "access"})
    token_b = create_access_token({"sub": f"{prefix}_u_b", "type": "access"})

    return {
        "org_a_id": f"{prefix}_org_a",
        "org_b_id": f"{prefix}_org_b",
        "token_a": token_a,
        "token_b": token_b,
        "regard_a_id": 98701,
        "conduite_a_id": 98702,
        "log_a1_id": f"{prefix}_log_a1",
        "log_b1_id": f"{prefix}_log_b1",
    }


# ============================================================
# 2. TESTS SÉCURITÉ : ACCÈS ANONYME (401 STRICT)
# ============================================================

def test_audit_routes_anonymous_rejected(ctx_audit):
    """Vérifie que les 4 routes d'audit rejettent immédiatement l'accès anonyme par 401."""
    client = TestClient(app)

    # 1. GET /logs
    r1 = client.get("/api/v1/audit/logs")
    assert r1.status_code == 401, f"GET /logs doit renvoyer 401, obtenu {r1.status_code}"

    # 2. GET /logs/{record_id}
    r2 = client.get(f"/api/v1/audit/logs/{ctx_audit['log_a1_id']}")
    assert r2.status_code == 401, f"GET /logs/{{id}} doit renvoyer 401, obtenu {r2.status_code}"

    # 3. GET /regards/{id}/history
    r3 = client.get(f"/api/v1/audit/regards/{ctx_audit['regard_a_id']}/history")
    assert r3.status_code == 401, f"GET /regards/{{id}}/history doit renvoyer 401, obtenu {r3.status_code}"

    # 4. GET /conduites/{id}/history
    r4 = client.get(f"/api/v1/audit/conduites/{ctx_audit['conduite_a_id']}/history")
    assert r4.status_code == 401, f"GET /conduites/{{id}}/history doit renvoyer 401, obtenu {r4.status_code}"


# ============================================================
# 3. TESTS SÉCURITÉ : ISOLATION MULTI-ORGANISATION STRICTE
# ============================================================

def test_audit_multitenant_isolation(ctx_audit):
    """Vérifie l'étanchéité stricte : Org A ne voit que A, Org B ne voit que B."""
    client = TestClient(app)

    # Org A liste ses logs
    res_a = client.get("/api/v1/audit/logs", headers={"Authorization": f"Bearer {ctx_audit['token_a']}"})
    assert res_a.status_code == 200
    logs_a = res_a.json()
    assert len(logs_a) == 3
    for l in logs_a:
        assert l["org_id"] == ctx_audit["org_a_id"]
        assert l["org_id"] != ctx_audit["org_b_id"]

    # Org B liste ses logs
    res_b = client.get("/api/v1/audit/logs", headers={"Authorization": f"Bearer {ctx_audit['token_b']}"})
    assert res_b.status_code == 200
    logs_b = res_b.json()
    assert len(logs_b) == 1
    assert logs_b[0]["id"] == ctx_audit["log_b1_id"]
    assert logs_b[0]["org_id"] == ctx_audit["org_b_id"]

    # Tentative d'accès croisé via /logs/{record_id} : Org A cherche le log_b1
    cross_res = client.get(
        f"/api/v1/audit/logs/{ctx_audit['log_b1_id']}",
        headers={"Authorization": f"Bearer {ctx_audit['token_a']}"}
    )
    assert cross_res.status_code == 200
    # Aucune fuite d'information : liste vide retournée pour l'org A
    assert len(cross_res.json()) == 0


# ============================================================
# 4. TESTS SÉCURITÉ : STEALTH 404 SUR LES HISTORIQUES OUVRAGES
# ============================================================

def test_audit_stealth_404_on_regards_and_conduites(ctx_audit):
    """
    Règle stealth 404 : un regard ou une conduite appartenant à une autre org
    ou inexistant doit renvoyer un 404 strict, sans dévoiler son existence.
    """
    client = TestClient(app)

    # Org A accède à son propre regard -> 200 OK
    res_a_regard = client.get(
        f"/api/v1/audit/regards/{ctx_audit['regard_a_id']}/history",
        headers={"Authorization": f"Bearer {ctx_audit['token_a']}"}
    )
    assert res_a_regard.status_code == 200
    entries = res_a_regard.json()
    assert len(entries) >= 1
    assert entries[0]["target_id"] == str(ctx_audit["regard_a_id"])

    # Org B tente d'accéder au regard de Org A -> Stealth 404
    res_b_cross_regard = client.get(
        f"/api/v1/audit/regards/{ctx_audit['regard_a_id']}/history",
        headers={"Authorization": f"Bearer {ctx_audit['token_b']}"}
    )
    assert res_b_cross_regard.status_code == 404, "Tentative cross-tenant regard doit renvoyer 404 furtif"

    # Org A accède à sa propre conduite -> 200 OK
    res_a_conduite = client.get(
        f"/api/v1/audit/conduites/{ctx_audit['conduite_a_id']}/history",
        headers={"Authorization": f"Bearer {ctx_audit['token_a']}"}
    )
    assert res_a_conduite.status_code == 200
    assert len(res_a_conduite.json()) >= 1

    # Org B tente d'accéder à la conduite de Org A -> Stealth 404
    res_b_cross_conduite = client.get(
        f"/api/v1/audit/conduites/{ctx_audit['conduite_a_id']}/history",
        headers={"Authorization": f"Bearer {ctx_audit['token_b']}"}
    )
    assert res_b_cross_conduite.status_code == 404, "Tentative cross-tenant conduite doit renvoyer 404 furtif"

    # ID totalement inexistant -> 404
    res_inexistant = client.get(
        "/api/v1/audit/regards/9999999/history",
        headers={"Authorization": f"Bearer {ctx_audit['token_a']}"}
    )
    assert res_inexistant.status_code == 404


# ============================================================
# 5. TESTS FILTRES ET RÉTROCOMPATIBILITÉ
# ============================================================

def test_audit_filters_and_compatibility_aliases(ctx_audit):
    """Vérifie le fonctionnement des filtres modernes et des alias rétrocompatibles."""
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {ctx_audit['token_a']}"}

    # 1. Filtre moderne par action
    r_act = client.get("/api/v1/audit/logs?action=network.import", headers=headers)
    assert r_act.status_code == 200
    assert len(r_act.json()) == 1
    assert r_act.json()[0]["action"] == "network.import"

    # 2. Filtre alias rétrocompatible 'operation'
    r_op = client.get("/api/v1/audit/logs?operation=network.import", headers=headers)
    assert r_op.status_code == 200
    assert len(r_op.json()) == 1

    # 3. Filtre moderne target_type
    r_type = client.get("/api/v1/audit/logs?target_type=regard", headers=headers)
    assert r_type.status_code == 200
    assert len(r_type.json()) == 1

    # 4. Filtre alias rétrocompatible 'table_name'
    r_tbl = client.get("/api/v1/audit/logs?table_name=regard", headers=headers)
    assert r_tbl.status_code == 200
    assert len(r_tbl.json()) == 1
