import pytest
from fastapi.testclient import TestClient
import geopandas as gpd
from pathlib import Path

from api.main import app
from api.database import SessionLocal, engine, Base
from api.models import User, Organization, Membership, Project
from src.domain.hydrologie import GenerateurHydrologie

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.query(Membership).delete()
    db.query(Project).delete()
    db.query(User).delete()
    db.query(Organization).delete()
    db.commit()
    db.close()
    yield

def test_generateur_hydrologie_domain_direct():
    """Valide l'algorithme de génération Voronoï / Thiessen sur demo_reseau.gpkg."""
    demo_path = Path("data/demo_reseau.gpkg")
    assert demo_path.exists()

    regards = gpd.read_file(demo_path, layer="regards")
    canalisations = gpd.read_file(demo_path, layer="canalisations")

    assert len(regards) == 59
    assert len(canalisations) == 58

    gh = GenerateurHydrologie(tampon_buffer_m=35.0, imperv_defaut=70.0)
    subcatchments = gh.generer_sous_bassins(regards, canalisations)

    assert len(subcatchments) == 59
    assert subcatchments["area_ha"].sum() > 5.0  # Au moins 5 hectares
    assert (subcatchments["area_ha"] > 0).all()
    assert (subcatchments["width_m"] > 0).all()
    assert (subcatchments["imperv_pct"] == 70.0).all()

    # Vérification des sections SWMM formatées
    sections = gh.formater_sections_swmm(subcatchments, rain_gage_name="RG1")
    assert "SUBCATCHMENTS" in sections
    assert "SUBAREAS" in sections
    assert "INFILTRATION" in sections
    assert "POLYGONS" in sections

    # 1 ligne d'en-tête + 59 lignes de sous-bassins
    assert len(sections["SUBCATCHMENTS"]) == 60
    assert len(sections["SUBAREAS"]) == 60
    assert len(sections["INFILTRATION"]) == 60
    assert len(sections["POLYGONS"]) > 100

    # Vérifier qu'une ligne SUBCATCHMENTS contient le nom du rain gage et de l'outlet
    first_line = sections["SUBCATCHMENTS"][1]
    assert "RG1" in first_line
    assert "SB_" in first_line

def test_endpoint_subcatchments_with_demo():
    """Valide l'endpoint GET /api/v1/network/subcatchments avec un utilisateur authentifié."""
    # 1. Inscription et validation du compte
    reg = client.post("/api/v1/auth/register", json={
        "email": "hydro.tester@example.com",
        "password": "SecurePassword123!",
        "full_name": "Hydrologist Tester",
        "org_name": "Hydro Lab",
        "plan_type": "pro"
    })
    assert reg.status_code == 201
    dev_code = reg.json()["dev_code"]

    ver = client.post("/api/v1/auth/verify-code", json={
        "email": "hydro.tester@example.com",
        "code": dev_code
    })
    assert ver.status_code == 200
    token = ver.json()["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Avant chargement du réseau : retour vide
    resp_empty = client.get("/api/v1/network/subcatchments", headers=headers)
    assert resp_empty.status_code == 200
    assert resp_empty.json()["subcatchments_count"] == 0

    # 3. Chargement de la démo
    load_resp = client.post("/api/v1/network/load-demo", headers=headers)
    assert load_resp.status_code == 200

    # 4. Requête de génération des sous-bassins
    resp_demo = client.get("/api/v1/network/subcatchments", headers=headers)
    assert resp_demo.status_code == 200
    data = resp_demo.json()

    assert data["type"] == "FeatureCollection"
    assert data["subcatchments_count"] == 59
    assert len(data["features"]) == 59
    assert data["total_area_ha"] > 10.0

    # Vérifier la géométrie et les propriétés du premier sous-bassin
    first_feat = data["features"][0]
    assert first_feat["geometry"]["type"] in ("Polygon", "MultiPolygon")
    props = first_feat["properties"]
    assert "SB_" in props["subcatchment_id"]
    assert props["outlet"] != ""
    assert props["imperv_pct"] == 70.0
    assert props["area_ha"] > 0
    assert props["f0"] == 75.0
    assert props["fc"] == 10.0

