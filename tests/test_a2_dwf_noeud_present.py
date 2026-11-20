# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : LOT A2-DWF — Tests de l'indicateur de présence réseau `noeud_present`

Couvre :
  - Diagnostic précis dans GET /api/v1/apports/a-reconcilier
  - Cas A : Nœud existant dans le réseau courant mais estampillage divergent -> noeud_present=True
  - Cas B : Nœud supprimé/absent du réseau courant -> noeud_present=False
  - Cas C : Réseau GPKG courant indisponible -> noeud_present=False
  - Cohérence structurelle (présence du champ dans 'incompatibles' et dans 'apports')
================================================================================
"""

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


@pytest.fixture(scope="module", autouse=True)
def init_db_schema():
    Base.metadata.create_all(bind=engine)


def _creer_gpkg(chemin: Path, codes_nodes, decalage: float = 0.0):
    gdf = gpd.GeoDataFrame(
        {"Code": list(codes_nodes)},
        geometry=[Point(i * 10.0 + decalage, i * 10.0) for i in range(len(codes_nodes))],
        crs="EPSG:32631",
    )
    gdf.to_file(str(chemin), layer="regards", driver="GPKG")


@pytest.fixture
def ctx_a2(tmp_path):
    gpkg = tmp_path / "reseau_a2.gpkg"
    # Le réseau actuel contient REG_ACTIF_1 et REG_ACTIF_2 (REG_ANCIEN a été supprimé)
    _creer_gpkg(gpkg, ["REG_ACTIF_1", "REG_ACTIF_2"])

    db = SessionLocal()
    pref = f"a2_{uuid.uuid4().hex[:6]}"
    org = Organization(id=f"{pref}_org", name=f"Org {pref}", slug=f"{pref}-org")
    user = User(
        id=f"{pref}_user",
        email=f"{pref}@drainpilot.dz",
        password_hash=hash_password("A2DwfSecure2026!"),
        full_name="Ingénieur A2",
        email_verified=True,
    )
    mem = Membership(org_id=org.id, user_id=user.id, role="engineer")
    proj = Project(
        id=f"{pref}_proj",
        org_id=org.id,
        name="Projet Diagnostic Réconciliation",
        slug=f"{pref}-proj",
        source_gpkg_key=str(gpkg),
        is_archived=False,
    )
    db.add_all([org, user, mem, proj])
    db.commit()

    token = create_access_token({"sub": user.id, "org_id": org.id, "role": "engineer"})
    yield {
        "db": db,
        "gpkg": gpkg,
        "org": org,
        "user": user,
        "proj": proj,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }

    try:
        db.query(ApportDwf).filter(ApportDwf.org_id == org.id).delete()
        db.delete(proj)
        db.delete(mem)
        db.delete(user)
        db.delete(org)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def test_noeud_present_vrai_quand_noeud_existe_mais_non_reconcilie(ctx_a2):
    """
    Apport sur un nœud existant (REG_ACTIF_1) mais sans estampillage ou avec sha obsolète.
    Doit être incompatible mais signaler noeud_present=True.
    """
    client = TestClient(app)
    db = ctx_a2["db"]
    proj = ctx_a2["proj"]

    # Création directe d'un apport non estampillé (historique) sur REG_ACTIF_1
    app1 = ApportDwf(
        org_id=ctx_a2["org"].id,
        project_id=proj.id,
        node_id="REG_ACTIF_1",
        code_apport="AP-2026-0001",
        nature="domestique",
        mode_determination="debit",
        debit_moyen_m3s=0.01,
        profile_key="constant",
        actif=True,
        gpkg_version_id=None,
        gpkg_sha256=None,  # non réconcilié
    )
    db.add(app1)
    db.commit()

    r = client.get(f"/api/v1/apports/a-reconcilier?project_id={proj.id}", headers=ctx_a2["headers"])
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["count"] == 1

    incomp = data["incompatibles"][0]
    assert incomp["apport_id"] == app1.id
    assert incomp["code"] == "non_reconcilie"
    assert incomp["noeud_present"] is True

    # Vérification de l'enrichissement dans apports
    assert len(data["apports"]) == 1
    assert data["apports"][0]["id"] == app1.id
    assert data["apports"][0]["noeud_present"] is True


def test_noeud_present_faux_quand_noeud_supprime_du_reseau(ctx_a2):
    """
    Apport sur un nœud (REG_SUPPRIME) absent du GPKG courant.
    Doit signaler noeud_present=False et code='noeud_absent_du_snapshot'.
    """
    client = TestClient(app)
    db = ctx_a2["db"]
    proj = ctx_a2["proj"]

    app_orphelin = ApportDwf(
        org_id=ctx_a2["org"].id,
        project_id=proj.id,
        node_id="REG_SUPPRIME",
        code_apport="AP-2026-0002",
        nature="industriel",
        mode_determination="debit",
        debit_moyen_m3s=0.02,
        profile_key="constant",
        actif=True,
        gpkg_version_id=None,
        gpkg_sha256="abc123fauxsha",
    )
    db.add(app_orphelin)
    db.commit()

    r = client.get(f"/api/v1/apports/a-reconcilier?project_id={proj.id}", headers=ctx_a2["headers"])
    assert r.status_code == 200, r.text
    data = r.json()

    incomp = next(d for d in data["incompatibles"] if d["apport_id"] == app_orphelin.id)
    assert incomp["node_id"] == "REG_SUPPRIME"
    assert incomp["noeud_present"] is False

    apport_enrichi = next(a for a in data["apports"] if a["id"] == app_orphelin.id)
    assert apport_enrichi["noeud_present"] is False


def test_noeud_present_faux_si_gpkg_introuvable(ctx_a2):
    """
    Si le GPKG du projet est introuvable sur le disque, tous les apports doivent
    indiquer noeud_present=False.
    """
    client = TestClient(app)
    db = ctx_a2["db"]
    proj = ctx_a2["proj"]

    # On pointe le projet vers un fichier inexistant
    proj.source_gpkg_key = "chemin/inexistant/reseau_fantome.gpkg"
    db.commit()

    app1 = ApportDwf(
        org_id=ctx_a2["org"].id,
        project_id=proj.id,
        node_id="REG_ACTIF_1",
        code_apport="AP-2026-0003",
        nature="domestique",
        mode_determination="debit",
        debit_moyen_m3s=0.01,
        profile_key="constant",
        actif=True,
    )
    db.add(app1)
    db.commit()

    r = client.get(f"/api/v1/apports/a-reconcilier?project_id={proj.id}", headers=ctx_a2["headers"])
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["reseau_courant"]["disponible"] is False

    incomp = next(d for d in data["incompatibles"] if d["apport_id"] == app1.id)
    assert incomp["code"] == "gpkg_courant_indisponible"
    assert incomp["noeud_present"] is False
