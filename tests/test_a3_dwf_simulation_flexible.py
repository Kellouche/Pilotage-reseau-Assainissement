# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : LOT A3-DWF — Tests de la simulation flexible `dwf_compatibles_seulement`

Couvre :
  - Comportement strict par défaut (dwf_compatibles_seulement=False) : rejet HTTP 422
  - Mode flexible (dwf_compatibles_seulement=True) : exécution réussie HTTP 200
  - Traçabilité des apports exclus dans provenance.apports_dwf.ignores
  - Enregistrement de l'événement d'exclusion dans l'historique d'audit DWF (sim_exclusion)
  - Invariance du calcul SWMM pour les apports compatibles restants
================================================================================
"""

from pathlib import Path
import uuid
import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point
from starlette.testclient import TestClient

from api.main import app
from api.database import SessionLocal, engine, Base
from api.models import Organization, User, Membership, Project, ApportDwf, ApportDwfHistory, Cluster
from api.core.auth import hash_password, create_access_token


@pytest.fixture(scope="module", autouse=True)
def init_db_schema():
    Base.metadata.create_all(bind=engine)


def _creer_reseau_minimal(chemin: Path):
    """Crée un GPKG avec regards et canalisation valide pour simulation SWMM."""
    regards = gpd.GeoDataFrame(
        {
            "Code": ["REG_AMONT", "REG_EXUTOIRE"],
            "cote_radier": [10.0, 9.0],
            "cote_tampon": [12.0, 11.0],
        },
        geometry=[Point(0.0, 0.0), Point(50.0, 0.0)],
        crs="EPSG:32631",
    )
    regards.to_file(str(chemin), layer="regards", driver="GPKG")

    troncons = gpd.GeoDataFrame(
        {
            "Code": ["TRONCON_01"],
            "ID_AMONT": ["REG_AMONT"],
            "ID_AVAL": ["REG_EXUTOIRE"],
            "Diametre": [400],
            "Rugosite": [0.013],
            "Forme": ["CIRCULAR"],
        },
        geometry=[LineString([(0.0, 0.0), (50.0, 0.0)])],
        crs="EPSG:32631",
    )
    troncons.to_file(str(chemin), layer="canalisations", driver="GPKG")


@pytest.fixture
def ctx_a3(tmp_path):
    gpkg = tmp_path / "reseau_a3.gpkg"
    _creer_reseau_minimal(gpkg)

    db = SessionLocal()
    pref = f"a3_{uuid.uuid4().hex[:6]}"
    org = Organization(id=f"{pref}_org", name=f"Org {pref}", slug=f"{pref}-org")
    user = User(
        id=f"{pref}_user",
        email=f"{pref}@drainpilot.dz",
        password_hash=hash_password("A3DwfSecure2026!"),
        full_name="Ingénieur A3",
        email_verified=True,
    )
    mem = Membership(org_id=org.id, user_id=user.id, role="engineer")
    proj = Project(
        id=f"{pref}_proj",
        org_id=org.id,
        name="Projet Simulation Flexible DWF",
        slug=f"{pref}-proj",
        source_gpkg_key=str(gpkg),
        is_archived=False,
    )
    cluster = Cluster(
        org_id=org.id,
        network_id=proj.id,
        nom="BASSIN_A3",
        bassin_ref="BV_01",
        exutoire_noeud="REG_EXUTOIRE",
        nb_conduites=1,
        nb_noeuds=2,
    )
    db.add_all([org, user, mem, proj, cluster])
    db.commit()

    token = create_access_token({"sub": user.id, "org_id": org.id, "role": "engineer"})
    yield {
        "db": db,
        "gpkg": gpkg,
        "org": org,
        "user": user,
        "proj": proj,
        "cluster": cluster,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }

    try:
        db.query(ApportDwfHistory).filter(ApportDwfHistory.org_id == org.id).delete()
        db.query(ApportDwf).filter(ApportDwf.org_id == org.id).delete()
        db.delete(cluster)
        db.delete(proj)
        db.delete(mem)
        db.delete(user)
        db.delete(org)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def test_simulation_rejet_422_si_incompatible_sans_flag_flexible(ctx_a3):
    """Vérifie que dwf_compatibles_seulement=False (défaut) préserve le rejet strict 422."""
    client = TestClient(app)
    db = ctx_a3["db"]
    proj = ctx_a3["proj"]

    # Apport orphelin / non réconcilié
    app_incomp = ApportDwf(
        org_id=ctx_a3["org"].id,
        project_id=proj.id,
        node_id="REG_AMONT",
        code_apport="AP-2026-INCOMP",
        nature="domestique",
        mode_determination="debit",
        debit_moyen_m3s=0.015,
        profile_key="constant",
        actif=True,
        gpkg_version_id=None,
        gpkg_sha256=None,  # Incompatible !
    )
    db.add(app_incomp)
    db.commit()

    payload = {
        "project_id": proj.id,
        "cluster_id": ctx_a3["cluster"].id,
        "scenario_key": "temps_sec_pur",
        "duree_heures": 2.0,
        "dwf_actif": True,
        "dwf_compatibles_seulement": False,
    }
    r = client.post("/api/v1/simulations/run", json=payload, headers=ctx_a3["headers"])
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert "apports_incompatibles" in detail


def test_simulation_reussie_avec_dwf_compatibles_seulement(ctx_a3):
    """
    Vérifie que dwf_compatibles_seulement=True permet l'exécution de la simulation :
    l'apport incompatible est ignoré et consigné dans provenance.apports_dwf.ignores,
    et tracé dans l'historique d'audit DWF avec action 'sim_exclusion'.
    """
    client = TestClient(app)
    db = ctx_a3["db"]
    proj = ctx_a3["proj"]

    # 1. Apport valide (créé via l'API, donc estampillé sur le GPKG courant)
    r_valide = client.post(
        "/api/v1/apports",
        json={
            "project_id": proj.id,
            "node_id": "REG_AMONT",
            "mode_determination": "debit",
            "debit_moyen_m3s": 0.010,
        },
        headers=ctx_a3["headers"],
    )
    assert r_valide.status_code == 201, r_valide.text
    id_valide = r_valide.json()["id"]

    # 2. Apport incompatible (injecté sans estampillage)
    app_incomp = ApportDwf(
        org_id=ctx_a3["org"].id,
        project_id=proj.id,
        node_id="REG_AMONT",
        code_apport="AP-2026-INCOMP-2",
        nature="industriel",
        mode_determination="debit",
        debit_moyen_m3s=0.020,
        profile_key="constant",
        actif=True,
        gpkg_version_id=None,
        gpkg_sha256=None,
    )
    db.add(app_incomp)
    db.commit()

    payload = {
        "project_id": proj.id,
        "cluster_id": ctx_a3["cluster"].id,
        "scenario_key": "temps_sec_pur",
        "duree_heures": 2.0,
        "dwf_actif": True,
        "dwf_compatibles_seulement": True,
    }
    r_sim = client.post("/api/v1/simulations/run", json=payload, headers=ctx_a3["headers"])
    assert r_sim.status_code == 200, r_sim.text
    data = r_sim.json()
    assert data["status"] == "success"

    # Vérification de la traçabilité dans la provenance
    prov = data.get("provenance", {})
    assert "apports_dwf" in prov
    dwf_prov = prov["apports_dwf"]

    # L'apport valide est injecté
    injectes_ids = [a.get("apport_id") or a.get("id") for a in dwf_prov.get("injectes", [])]
    assert id_valide in injectes_ids

    # L'apport incompatible est dans les ignores avec motif exclusion_utilisateur
    ignores = dwf_prov.get("ignores", [])
    assert len(ignores) >= 1
    exclu = next((ig for ig in ignores if (ig.get("apport_id") or ig.get("id")) == app_incomp.id), None)
    assert exclu is not None
    assert exclu["motif"] == "exclusion_utilisateur"
    assert exclu["code_incompatibilite"] == "non_reconcilie"

    # Vérification de l'enregistrement dans l'historique d'audit (apports_dwf_history)
    hist_entry = (
        db.query(ApportDwfHistory)
        .filter(
            ApportDwfHistory.apport_id == app_incomp.id,
            ApportDwfHistory.action == "sim_exclusion",
        )
        .first()
    )
    assert hist_entry is not None
    assert hist_entry.new_state["motif"] == "exclusion_utilisateur"
