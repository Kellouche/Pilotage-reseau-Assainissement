# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : LOT A1-DWF — Tests de la clé métier unique code_apport (AP-YYYY-NNNN)

Couvre :
  - Génération automatique séquentielle par projet et par année
  - Respect du format canonique AP-YYYY-NNNN
  - Unicité stricte intra-projet (HTTP 409 en cas de doublon)
  - Indépendance multi-projets (même code possible sur deux projets distincts)
  - Modification via PUT (renommage valide vs conflit 409)
  - Backfill idempotent des enregistrements existants sans code
================================================================================
"""

from datetime import datetime, timezone
from pathlib import Path
import uuid
import geopandas as gpd
import pytest
from shapely.geometry import Point
from starlette.testclient import TestClient

from api.main import app
from api.database import SessionLocal, engine, Base
from api.models import Organization, User, Membership, Project, ApportDwf
from api.core.auth import hash_password, create_access_token
from api.services.apports_dwf_service import generer_code_apport, backfill_codes_apports


@pytest.fixture(scope="module", autouse=True)
def init_db_schema():
    Base.metadata.create_all(bind=engine)


def _creer_gpkg(chemin: Path, codes_nodes):
    gdf = gpd.GeoDataFrame(
        {"Code": list(codes_nodes)},
        geometry=[Point(i * 10.0, i * 10.0) for i in range(len(codes_nodes))],
        crs="EPSG:32631",
    )
    gdf.to_file(str(chemin), layer="regards", driver="GPKG")


@pytest.fixture
def ctx_a1(tmp_path):
    """Fixture de test avec deux projets distincts pour vérifier l'isolation des séquences."""
    gpkg1 = tmp_path / "reseau_p1.gpkg"
    gpkg2 = tmp_path / "reseau_p2.gpkg"
    _creer_gpkg(gpkg1, ["REG_01", "REG_02", "REG_03"])
    _creer_gpkg(gpkg2, ["REG_10", "REG_11"])

    db = SessionLocal()
    pref = f"a1_{uuid.uuid4().hex[:6]}"
    org = Organization(id=f"{pref}_org", name=f"Org {pref}", slug=f"{pref}-org")
    user = User(
        id=f"{pref}_user",
        email=f"{pref}@drainpilot.dz",
        password_hash=hash_password("A1DwfSecure2026!"),
        full_name="Ingénieur A1",
        email_verified=True,
    )
    mem = Membership(org_id=org.id, user_id=user.id, role="engineer")
    proj1 = Project(
        id=f"{pref}_p1",
        org_id=org.id,
        name="Projet Principal",
        slug=f"{pref}-p1",
        source_gpkg_key=str(gpkg1),
        is_archived=False,
    )
    proj2 = Project(
        id=f"{pref}_p2",
        org_id=org.id,
        name="Projet Secondaire",
        slug=f"{pref}-p2",
        source_gpkg_key=str(gpkg2),
        is_archived=False,
    )
    db.add_all([org, user, mem, proj1, proj2])
    db.commit()

    token = create_access_token({"sub": user.id, "org_id": org.id, "role": "engineer"})
    yield {
        "db": db,
        "org": org,
        "user": user,
        "proj1": proj1,
        "proj2": proj2,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }

    try:
        db.query(ApportDwf).filter(ApportDwf.org_id == org.id).delete()
        db.delete(proj1)
        db.delete(proj2)
        db.delete(mem)
        db.delete(user)
        db.delete(org)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def test_generation_automatique_code_sequentiel(ctx_a1):
    """Vérifie que la création d'apports sans code génère AP-YYYY-0001 puis AP-YYYY-0002."""
    client = TestClient(app)
    pid = ctx_a1["proj1"].id
    annee = datetime.now(timezone.utc).year

    # Création apport 1
    r1 = client.post(
        "/api/v1/apports",
        json={"project_id": pid, "node_id": "REG_01", "mode_determination": "debit", "debit_moyen_m3s": 0.01},
        headers=ctx_a1["headers"],
    )
    assert r1.status_code == 201, r1.text
    d1 = r1.json()
    assert d1["code_apport"] == f"AP-{annee}-0001"

    # Création apport 2
    r2 = client.post(
        "/api/v1/apports",
        json={"project_id": pid, "node_id": "REG_02", "mode_determination": "debit", "debit_moyen_m3s": 0.02},
        headers=ctx_a1["headers"],
    )
    assert r2.status_code == 201, r2.text
    d2 = r2.json()
    assert d2["code_apport"] == f"AP-{annee}-0002"


def test_unicite_intra_projet_rejet_doublon_409(ctx_a1):
    """Vérifie qu'un code apport déjà existant dans le projet déclenche une HTTP 409 Conflict."""
    client = TestClient(app)
    pid = ctx_a1["proj1"].id

    # Création d'un apport avec un code personnalisé
    r1 = client.post(
        "/api/v1/apports",
        json={
            "project_id": pid,
            "node_id": "REG_01",
            "code_apport": "AP-CUSTOM-99",
            "mode_determination": "debit",
            "debit_moyen_m3s": 0.015,
        },
        headers=ctx_a1["headers"],
    )
    assert r1.status_code == 201, r1.text
    assert r1.json()["code_apport"] == "AP-CUSTOM-99"

    # Tentative d'insertion d'un autre apport avec le même code sur le même projet
    r2 = client.post(
        "/api/v1/apports",
        json={
            "project_id": pid,
            "node_id": "REG_02",
            "code_apport": "AP-CUSTOM-99",
            "mode_determination": "debit",
            "debit_moyen_m3s": 0.025,
        },
        headers=ctx_a1["headers"],
    )
    assert r2.status_code == 409, r2.text
    assert "existe déjà" in r2.json()["detail"]


def test_independance_codes_inter_projets(ctx_a1):
    """Vérifie que deux projets distincts peuvent utiliser le même code sans conflit."""
    client = TestClient(app)
    p1_id = ctx_a1["proj1"].id
    p2_id = ctx_a1["proj2"].id

    # Apport sur projet 1
    r1 = client.post(
        "/api/v1/apports",
        json={
            "project_id": p1_id,
            "node_id": "REG_01",
            "code_apport": "AP-PARTAGE-01",
            "mode_determination": "debit",
            "debit_moyen_m3s": 0.01,
        },
        headers=ctx_a1["headers"],
    )
    assert r1.status_code == 201, r1.text

    # Apport avec le MÊME code sur projet 2 (doit être accepté car scopé au projet)
    r2 = client.post(
        "/api/v1/apports",
        json={
            "project_id": p2_id,
            "node_id": "REG_10",
            "code_apport": "AP-PARTAGE-01",
            "mode_determination": "debit",
            "debit_moyen_m3s": 0.02,
        },
        headers=ctx_a1["headers"],
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["code_apport"] == "AP-PARTAGE-01"


def test_modification_code_apport_put(ctx_a1):
    """Vérifie la mise à jour du code_apport via PUT (succès vs conflit 409)."""
    client = TestClient(app)
    pid = ctx_a1["proj1"].id

    r1 = client.post(
        "/api/v1/apports",
        json={"project_id": pid, "node_id": "REG_01", "code_apport": "AP-INIT-01", "mode_determination": "debit", "debit_moyen_m3s": 0.01},
        headers=ctx_a1["headers"],
    )
    assert r1.status_code == 201
    id1 = r1.json()["id"]

    r2 = client.post(
        "/api/v1/apports",
        json={"project_id": pid, "node_id": "REG_02", "code_apport": "AP-INIT-02", "mode_determination": "debit", "debit_moyen_m3s": 0.02},
        headers=ctx_a1["headers"],
    )
    assert r2.status_code == 201
    id2 = r2.json()["id"]

    # Renommage de l'apport 1 vers un code valide libre
    r_put1 = client.put(
        f"/api/v1/apports/{id1}",
        json={"code_apport": "AP-RENOMME-01"},
        headers=ctx_a1["headers"],
    )
    assert r_put1.status_code == 200, r_put1.text
    assert r_put1.json()["code_apport"] == "AP-RENOMME-01"

    # Tentative de renommage de l'apport 2 vers AP-RENOMME-01 (conflit avec apport 1)
    r_put2 = client.put(
        f"/api/v1/apports/{id2}",
        json={"code_apport": "AP-RENOMME-01"},
        headers=ctx_a1["headers"],
    )
    assert r_put2.status_code == 409, r_put2.text


def test_backfill_codes_apports_idempotent(ctx_a1):
    """Vérifie que le backfill assigne des codes uniques aux enregistrements existants sans code."""
    db = ctx_a1["db"]
    pid = ctx_a1["proj1"].id

    # Insertion directe de 3 apports sans code_apport
    app1 = ApportDwf(
        org_id=ctx_a1["org"].id,
        project_id=pid,
        node_id="REG_01",
        code_apport=None,
        nature="domestique",
        mode_determination="debit",
        debit_moyen_m3s=0.01,
        profile_key="constant",
        actif=True,
    )
    app2 = ApportDwf(
        org_id=ctx_a1["org"].id,
        project_id=pid,
        node_id="REG_02",
        code_apport=None,
        nature="industriel",
        mode_determination="debit",
        debit_moyen_m3s=0.02,
        profile_key="constant",
        actif=True,
    )
    db.add_all([app1, app2])
    db.commit()

    nb = backfill_codes_apports(db, pid)
    assert nb == 2

    db.refresh(app1)
    db.refresh(app2)
    assert app1.code_apport is not None and app1.code_apport.startswith("AP-")
    assert app2.code_apport is not None and app2.code_apport.startswith("AP-")
    assert app1.code_apport != app2.code_apport

    # Un deuxième appel immédiat ne doit rien modifier (idempotence)
    nb_rejoue = backfill_codes_apports(db, pid)
    assert nb_rejoue == 0
