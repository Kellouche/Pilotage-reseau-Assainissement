# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : LOT P1.2 — Tests du modèle de données et de l'API des apports DWF

Couvre : CRUD HTTP authentifié, isolation org/projet (stealth 404),
validation des nœuds contre le GPKG versionné, modes débit/EH, profils
temporels, validations métier, migration Alembic sur base existante.
================================================================================
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from api.main import app
from api.database import SessionLocal, engine, Base
from api.models import (
    Organization, User, Membership, Project, ApportDwf,
)
from api.core.auth import hash_password, create_access_token

REPO_ROOT = Path(__file__).resolve().parent.parent
GPKG_DEMO = REPO_ROOT / "data" / "demo_reseau.gpkg"


@pytest.fixture(scope="module", autouse=True)
def init_db_schema():
    Base.metadata.create_all(bind=engine)


def _creer_gpkg_test(chemin: Path, codes_nodes):
    """GPKG minimal avec une couche 'regards' pour la validation des nœuds."""
    import geopandas as gpd
    from shapely.geometry import Point
    gdf = gpd.GeoDataFrame(
        {"Code": list(codes_nodes)},
        geometry=[Point(i * 10.0, i * 10.0) for i in range(len(codes_nodes))],
        crs="EPSG:32631",
    )
    gdf.to_file(str(chemin), layer="regards", driver="GPKG")


@pytest.fixture
def ctx_apports(tmp_path):
    """Deux organisations ; A a un projet sur le GPKG démo (nœuds 2653…),
    B a un projet sur un GPKG minimal (nœud REG_B1)."""
    gpkg_b = tmp_path / "reseau_b.gpkg"
    _creer_gpkg_test(gpkg_b, ["REG_B1", "REG_B2"])

    db = SessionLocal()
    prefix = "p12"

    def _org(uid):
        return Organization(id=f"{prefix}_{uid}", name=f"Org {uid}",
                            slug=f"org-{uid}-{prefix}")

    def _user(uid, email):
        return User(id=f"{prefix}_u_{uid}", email=email,
                    password_hash=hash_password("DwfPass2026!"),
                    full_name=f"User {uid}", email_verified=True)

    org_a, org_b = _org("a"), _org("b")
    user_a, user_b = _user("a", "a@p12.dz"), _user("b", "b@p12.dz")
    mem_a = Membership(org_id=org_a.id, user_id=user_a.id, role="admin")
    mem_b = Membership(org_id=org_b.id, user_id=user_b.id, role="admin")
    proj_a = Project(id=f"{prefix}_pa", org_id=org_a.id, name="Projet A",
                     slug=f"pa-{prefix}", source_gpkg_key=str(GPKG_DEMO),
                     is_archived=False)
    proj_b = Project(id=f"{prefix}_pb", org_id=org_b.id, name="Projet B",
                     slug=f"pb-{prefix}", source_gpkg_key=str(gpkg_b),
                     is_archived=False)

    db.add_all([org_a, org_b, user_a, user_b, mem_a, mem_b, proj_a, proj_b])
    db.commit()

    ctx = {
        "db": db, "gpkg_b": gpkg_b,
        "org_a": org_a, "org_b": org_b,
        "proj_a": proj_a, "proj_b": proj_b,
        "token_a": create_access_token({"sub": user_a.id, "org_id": org_a.id, "role": "admin"}),
        "token_b": create_access_token({"sub": user_b.id, "org_id": org_b.id, "role": "admin"}),
    }
    yield ctx

    db.query(ApportDwf).filter(ApportDwf.org_id.in_([org_a.id, org_b.id])).delete()
    for obj in (proj_a, proj_b, mem_a, mem_b, user_a, user_b, org_a, org_b):
        db.delete(obj)
    db.commit()
    db.close()


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _creer(client, token, **kw):
    body = {"project_id": kw.pop("project_id", None), **kw}
    return client.post("/api/v1/apports", json=body, headers=_h(token))


# ---------------------------------------------------------------------------
# Sécurité / isolation
# ---------------------------------------------------------------------------

def test_anonyme_refuse(ctx_apports):
    client = TestClient(app)
    assert client.get("/api/v1/apports").status_code == 401
    assert client.post("/api/v1/apports", json={}).status_code == 401
    assert client.get("/api/v1/apports/profils").status_code == 401


def test_isolation_lecture_écriture(ctx_apports):
    client = TestClient(app)
    r = _creer(client, ctx_apports["token_a"], project_id=ctx_apports["proj_a"].id,
               node_id="2653", nature="domestique", mode_determination="debit",
               debit_moyen_m3s=0.005)
    assert r.status_code == 201, r.text
    apport_id = r.json()["id"]

    # Org B ne voit pas l'apport de A (stealth 404)
    assert client.get(f"/api/v1/apports/{apport_id}",
                      headers=_h(ctx_apports["token_b"])).status_code == 404
    assert client.put(f"/api/v1/apports/{apport_id}", json={"actif": False},
                      headers=_h(ctx_apports["token_b"])).status_code == 404
    assert client.delete(f"/api/v1/apports/{apport_id}",
                         headers=_h(ctx_apports["token_b"])).status_code == 404
    # Liste de B bornée à son propre projet
    lst_b = client.get("/api/v1/apports", headers=_h(ctx_apports["token_b"]))
    assert lst_b.status_code == 200 and lst_b.json() == []


def test_projet_cross_org_404(ctx_apports):
    client = TestClient(app)
    # B tente de créer un apport sur le projet de A
    r = _creer(client, ctx_apports["token_b"], project_id=ctx_apports["proj_a"].id,
               node_id="2653", debit_moyen_m3s=0.001)
    assert r.status_code == 404
    # Projet inexistant → 404
    r = _creer(client, ctx_apports["token_a"], project_id="inexistant",
               node_id="2653", debit_moyen_m3s=0.001)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Validation des nœuds (GPKG versionné du projet)
# ---------------------------------------------------------------------------

def test_noeud_valide_et_invalide(ctx_apports):
    client = TestClient(app)
    pid = ctx_apports["proj_a"].id
    tok = ctx_apports["token_a"]

    ok = _creer(client, tok, project_id=pid, node_id="2653",
                debit_moyen_m3s=0.002)
    assert ok.status_code == 201, ok.text
    assert ok.json()["node_id"] == "2653"

    # Nœud inexistant dans le GPKG → 422
    ko = _creer(client, tok, project_id=pid, node_id="999999",
                debit_moyen_m3s=0.002)
    assert ko.status_code == 422

    # Nœud valide dans A mais absent du GPKG de B → 422 (pas de fuite inter-projets)
    kb = _creer(client, ctx_apports["token_b"],
                project_id=ctx_apports["proj_b"].id, node_id="2653",
                debit_moyen_m3s=0.002)
    assert kb.status_code == 422

    # Endpoint liste des nœuds disponibles
    noeuds = client.get(f"/api/v1/apports/noeuds?project_id={pid}",
                        headers=_h(tok))
    assert noeuds.status_code == 200
    assert "2653" in noeuds.json()["noeuds"]
    assert "999999" not in noeuds.json()["noeuds"]


# ---------------------------------------------------------------------------
# Modes de détermination et unités
# ---------------------------------------------------------------------------

def test_mode_debit_direct(ctx_apports):
    client = TestClient(app)
    r = _creer(client, ctx_apports["token_a"],
               project_id=ctx_apports["proj_a"].id, node_id="2654",
               nature="industriel", mode_determination="debit",
               debit_moyen_m3s=0.010)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["mode_determination"] == "debit"
    assert d["debit_moyen_m3s"] == pytest.approx(0.010)
    assert d["debit_moyen_ls"] == pytest.approx(10.0)
    assert d["eh"] is None
    assert d["nature"] == "industriel"


def test_mode_eh_conversion(ctx_apports):
    client = TestClient(app)
    # EH=1000, qspec défaut 200 L/hab/j → 1000*200/86400000 = 0.0023148 m³/s
    r = _creer(client, ctx_apports["token_a"],
               project_id=ctx_apports["proj_a"].id, node_id="2655",
               nature="domestique", mode_determination="eh", eh=1000)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["eh"] == 1000
    assert d["debit_specifique_l_hab_j"] == 200.0  # défaut documenté
    assert d["debit_moyen_m3s"] == pytest.approx(0.0023148, rel=1e-3)

    # qspec explicite
    r2 = _creer(client, ctx_apports["token_a"],
                project_id=ctx_apports["proj_a"].id, node_id="2656",
                mode_determination="eh", eh=500,
                debit_specifique_l_hab_j=150.0)
    assert r2.status_code == 201, r2.text
    assert r2.json()["debit_moyen_m3s"] == pytest.approx(
        500 * 150 / 86_400_000, rel=1e-6)


def test_validations_metier(ctx_apports):
    client = TestClient(app)
    pid = ctx_apports["proj_a"].id
    tok = ctx_apports["token_a"]

    # débit négatif → 422 (Pydantic)
    assert _creer(client, tok, project_id=pid, node_id="2653",
                  debit_moyen_m3s=-0.5).status_code == 422
    # mode debit sans débit → 422
    assert _creer(client, tok, project_id=pid, node_id="2653",
                  mode_determination="debit").status_code == 422
    # mode eh sans eh → 422
    assert _creer(client, tok, project_id=pid, node_id="2653",
                  mode_determination="eh").status_code == 422
    # profil inconnu → 422
    assert _creer(client, tok, project_id=pid, node_id="2653",
                  debit_moyen_m3s=0.001,
                  profile_key="inexistant").status_code == 422
    # nature invalide → 422
    assert _creer(client, tok, project_id=pid, node_id="2653",
                  nature="bidon", debit_moyen_m3s=0.001).status_code == 422
    # eh nul → 422
    assert _creer(client, tok, project_id=pid, node_id="2653",
                  mode_determination="eh", eh=0).status_code == 422


# ---------------------------------------------------------------------------
# Profils temporels
# ---------------------------------------------------------------------------

def test_profils_predfinis(ctx_apports):
    client = TestClient(app)
    r = client.get("/api/v1/apports/profils", headers=_h(ctx_apports["token_a"]))
    assert r.status_code == 200
    profils = {p["key"]: p for p in r.json()}
    assert set(profils) == {"constant", "journalier_type", "hebdomadaire"}
    for p in profils.values():
        assert p["type_swmm"] == "PATTERN"
        assert len(p["facteurs_168"]) == 168
        # moyenne des facteurs ≈ 1.0 (normalisation volume)
        assert p["moyenne_facteurs"] == pytest.approx(1.0, abs=0.01)
    # constant : tous les facteurs à 1.0
    assert all(f == pytest.approx(1.0) for f in profils["constant"]["facteurs_168"])
    # journalier : pic > creux
    j = profils["journalier_type"]["facteurs_168"]
    assert max(j) > min(j)


def test_apport_avec_profil_hebdo(ctx_apports):
    client = TestClient(app)
    r = _creer(client, ctx_apports["token_a"],
               project_id=ctx_apports["proj_a"].id, node_id="2661",
               debit_moyen_m3s=0.003, profile_key="hebdomadaire",
               source="Mesure STEP", observations="Rejet connu")
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["profile_key"] == "hebdomadaire"
    assert d["source"] == "Mesure STEP"
    assert d["actif"] is True


# ---------------------------------------------------------------------------
# Mise à jour, désactivation, suppression
# ---------------------------------------------------------------------------

def test_modification_et_desactivation(ctx_apports):
    client = TestClient(app)
    tok = ctx_apports["token_a"]
    pid = ctx_apports["proj_a"].id

    r = _creer(client, tok, project_id=pid, node_id="2658",
               debit_moyen_m3s=0.004)
    aid = r.json()["id"]

    # Désactivation
    r2 = client.put(f"/api/v1/apports/{aid}", json={"actif": False},
                    headers=_h(tok))
    assert r2.status_code == 200 and r2.json()["actif"] is False

    # Filtre actif_seulement
    lst = client.get(f"/api/v1/apports?project_id={pid}&actif_seulement=true",
                     headers=_h(tok)).json()
    assert all(a["actif"] for a in lst)
    assert aid not in [a["id"] for a in lst]

    # Changement de mode debit → eh recalcule le débit
    r3 = client.put(f"/api/v1/apports/{aid}",
                    json={"mode_determination": "eh", "eh": 2000,
                          "debit_specifique_l_hab_j": 200.0},
                    headers=_h(tok))
    assert r3.status_code == 200, r3.text
    d = r3.json()
    assert d["mode_determination"] == "eh"
    assert d["debit_moyen_m3s"] == pytest.approx(2000 * 200 / 86_400_000, rel=1e-6)

    # Suppression
    assert client.delete(f"/api/v1/apports/{aid}",
                         headers=_h(tok)).status_code == 204
    assert client.get(f"/api/v1/apports/{aid}",
                      headers=_h(tok)).status_code == 404


def test_liste_filtree_par_noeud(ctx_apports):
    client = TestClient(app)
    tok = ctx_apports["token_a"]
    pid = ctx_apports["proj_a"].id
    _creer(client, tok, project_id=pid, node_id="2659", debit_moyen_m3s=0.001)
    _creer(client, tok, project_id=pid, node_id="2659", debit_moyen_m3s=0.002,
           nature="industriel")
    _creer(client, tok, project_id=pid, node_id="2660", debit_moyen_m3s=0.001)

    lst = client.get(f"/api/v1/apports?project_id={pid}&node_id=2659",
                     headers=_h(tok)).json()
    assert len(lst) == 2
    assert all(a["node_id"] == "2659" for a in lst)
    natures = {a["nature"] for a in lst}
    assert "industriel" in natures  # multi-apports par nœud autorisés


# ---------------------------------------------------------------------------
# Migration Alembic sur base existante (sans perte de données)
# ---------------------------------------------------------------------------

def test_migration_apports_dwf_sur_base_existante(tmp_path, monkeypatch):
    """La révision c3d4e5f6a7b8 crée apports_dwf sur une base déjà peuplée
    sans altérer les données existantes."""
    db_path = tmp_path / "mig_test.db"
    url = "sqlite:///" + str(db_path).replace("\\", "/")
    monkeypatch.setenv("DATABASE_URL", url)

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    import api.models  # noqa: F401 — enregistre toutes les tables
    from api.database import Base

    eng = create_engine(url, future=True)
    Base.metadata.create_all(bind=eng)

    # Simule une base à la révision précédente : supprime la nouvelle table
    # et estampille alembic_version.
    with eng.begin() as conn:
        conn.execute(text("DROP TABLE apports_dwf"))
        conn.execute(text(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        conn.execute(text(
            "INSERT INTO alembic_version (version_num) VALUES ('b2c3d4e5f6a7')"))
        # Données préexistantes à conserver (ORM : toutes colonnes NOT NULL)
        sess = Session(bind=conn)
        sess.add(Organization(id="mig_org", name="Org Migration",
                              slug="org-mig", billing_plan="demo",
                              billing_status="trial", org_type="bet"))
        sess.add(Project(id="mig_proj", org_id="mig_org", slug="proj-mig",
                         name="Projet Migration", is_archived=False))
        sess.commit()
        sess.close()

    # Exécute alembic upgrade head (DATABASE_URL lu par alembic/env.py)
    env = dict(os.environ)
    env["DATABASE_URL"] = url
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(REPO_ROOT), env=env,
        capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, (
        f"alembic upgrade échoué:\n{result.stdout}\n{result.stderr}")

    # Vérifications post-migration
    with eng.connect() as conn:
        tables = {r[0] for r in conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'"))}
        assert "apports_dwf" in tables
        assert conn.execute(text(
            "SELECT COUNT(*) FROM organizations WHERE id='mig_org'"
        )).scalar() == 1
        assert conn.execute(text(
            "SELECT COUNT(*) FROM projects WHERE id='mig_proj'"
        )).scalar() == 1
        cols = {r[1] for r in conn.execute(
            text("PRAGMA table_info(apports_dwf)"))}
        assert {"org_id", "project_id", "node_id", "nature",
                "mode_determination", "debit_moyen_m3s", "eh",
                "debit_specifique_l_hab_j", "profile_key", "actif",
                "source", "observations"} <= cols
