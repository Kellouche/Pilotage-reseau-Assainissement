# -*- coding: utf-8 -*-
"""
Validation d'intégration des endpoints Qualité Réseau V2.1.
Spec : docs/05_CONTROLE_QUALITE_V2.md §6/§7/§8.
"""
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.database import SessionLocal
from api.models import User, Organization, Membership, Project
from api.core.auth import create_access_token
from api.routes.qualite import reinitialiser_cache_qualite


def _trouver_gpkg_ville() -> Path:
    for p in Path("uploads").glob("*/network_Assainissement_Ville.gpkg"):
        return p
    cand = Path("D:/IA Water Data Analysis/Assainissement/Assainissement_Ville.gpkg")
    if cand.exists():
        return cand
    return Path("data/demo_reseau.gpkg")


@pytest.fixture(scope="module")
def auth_headers():
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.id == "org_test_qualite_v2").first()
        if not org:
            org = Organization(
                id="org_test_qualite_v2",
                name="Org Test Qualite V2",
                slug="org-test-qualite-v2",
                billing_plan="pro",
                is_active=True
            )
            db.add(org)
            db.commit()

        user = db.query(User).filter(User.id == "user_test_qualite_v2").first()
        if not user:
            user = User(
                id="user_test_qualite_v2",
                email="test_qualite_v2@example.com",
                is_active=True,
                email_verified=True,
                password_hash="dummy"
            )
            db.add(user)
            db.commit()

        membership = db.query(Membership).filter(
            Membership.user_id == "user_test_qualite_v2",
            Membership.org_id == "org_test_qualite_v2"
        ).first()
        if not membership:
            membership = Membership(
                user_id="user_test_qualite_v2",
                org_id="org_test_qualite_v2",
                role="engineer"
            )
            db.add(membership)
            db.commit()

        gpkg = _trouver_gpkg_ville()
        proj = db.query(Project).filter(
            Project.org_id == "org_test_qualite_v2",
            Project.is_archived.is_(False)
        ).first()
        if not proj:
            proj = Project(
                id="proj_test_qualite_v2",
                org_id="org_test_qualite_v2",
                name="Projet Test Qualite V2",
                source_gpkg_key=str(gpkg),
                is_archived=False
            )
            db.add(proj)
            db.commit()
        else:
            proj.source_gpkg_key = str(gpkg)
            db.commit()

        reinitialiser_cache_qualite()
        token = create_access_token({"sub": "user_test_qualite_v2", "type": "access"})
        return {"Authorization": f"Bearer {token}"}
    finally:
        db.close()


def test_qualite_cache_status(auth_headers):
    """GET /cache/status renvoie un statut de cache valide."""
    client = TestClient(app)
    resp = client.get("/api/v1/qualite/cache/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "status_cache" in data
    assert "analyse_disponible" in data


def test_qualite_synthese(auth_headers):
    """GET /synthese retourne le verdict, les scores et le top 3 actions."""
    client = TestClient(app)
    resp = client.get("/api/v1/qualite/synthese", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    # Contrat Spec §7
    assert "verdict" in data
    assert data["verdict"] in ["conforme", "a_surveiller", "action_requise", "indetermine"]
    assert "reseau" in data
    assert data["reseau"]["nb_conduites"] > 0
    assert "scores" in data
    assert "topologie" in data["scores"]
    assert "altimetrie" in data
    assert "couverture_pct" in data["altimetrie"]
    assert "anomalies" in data
    assert "top_actions" in data
    assert isinstance(data["top_actions"], list)


def test_qualite_synthese_force_refresh(auth_headers):
    """GET /synthese?force_refresh=true force le recalcul sans erreur."""
    client = TestClient(app)
    resp = client.get("/api/v1/qualite/synthese?force_refresh=true", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] in ["conforme", "a_surveiller", "action_requise", "indetermine"]


def test_qualite_anomalies_geojson(auth_headers):
    """GET /anomalies.geojson retourne une FeatureCollection WGS84 avec cle_anomalie et statut."""
    client = TestClient(app)
    resp = client.get("/api/v1/qualite/anomalies.geojson", headers=auth_headers)
    assert resp.status_code == 200
    fc = resp.json()

    assert fc["type"] == "FeatureCollection"
    assert "features" in fc
    assert isinstance(fc["features"], list)
    assert len(fc["features"]) > 0

    first = fc["features"][0]
    assert first["type"] == "Feature"
    assert first["geometry"]["type"] == "Point"
    coords = first["geometry"]["coordinates"]
    assert len(coords) == 2
    # Longitude, Latitude WGS84 plausibles pour la région d'Alger / Chlef (EPSG:4326)
    assert -5.0 <= coords[0] <= 15.0
    assert 25.0 <= coords[1] <= 45.0

    props = first["properties"]
    assert "cle_anomalie" in props
    assert "statut" in props
    assert props["statut"] in ["a_traiter", "revu", "corrige"]
    assert "severite" in props
    assert "categorie" in props


def test_qualite_anomalies_pagination(auth_headers):
    """GET /anomalies/{type} gère correctement cursor et limit."""
    client = TestClient(app)
    resp = client.get("/api/v1/qualite/anomalies/inversions_sens_ecoulement?cursor=0&limit=10", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["type_anomalie"] == "inversions_sens_ecoulement"
    assert data["cursor"] == 0
    assert data["limit"] == 10
    assert len(data["anomalies"]) <= 10
    assert "total" in data


def test_qualite_anomalie_cycle_de_vie(auth_headers):
    """POST /anomalies/{cle}/statut permet de mettre à jour le statut."""
    client = TestClient(app)
    # Récupérer une anomalie existante
    resp_geo = client.get("/api/v1/qualite/anomalies.geojson", headers=auth_headers)
    assert resp_geo.status_code == 200
    features = resp_geo.json()["features"]
    assert len(features) > 0

    target = features[0]["properties"]
    cle = target["cle_anomalie"]
    assert cle, "cle_anomalie manquante"

    # Marquer comme 'revu'
    resp_post = client.post(
        f"/api/v1/qualite/anomalies/{cle}/statut",
        headers=auth_headers,
        json={"statut": "revu", "commentaire": "Audit contre-expertise"}
    )
    assert resp_post.status_code == 200
    res_data = resp_post.json()
    assert res_data.get("anomalie", {}).get("statut") == "revu" or res_data.get("statut") in ["ok", "revu"]

    # Vérifier que le statut est persisté dans GET /statuts
    resp_statuts = client.get("/api/v1/qualite/statuts", headers=auth_headers)
    assert resp_statuts.status_code == 200
    statuts_data = resp_statuts.json()
    cles_enregistrees = [s["cle_anomalie"] for s in statuts_data.get("statuts", [])]
    assert cle in cles_enregistrees
    assert statuts_data.get("distribution", {}).get("revu") == 1

    # Remettre à 'a_traiter' pour laisser l'état propre
    resp_reset = client.post(
        f"/api/v1/qualite/anomalies/{cle}/statut",
        headers=auth_headers,
        json={"statut": "a_traiter"}
    )
    assert resp_reset.status_code == 200
    res_reset = resp_reset.json()
    assert res_reset.get("anomalie", {}).get("statut") == "a_traiter" or res_reset.get("statut") in ["ok", "a_traiter"]


def test_qualite_modifier_attributs_conduite(auth_headers):
    """PATCH /conduites/{id_conduite} modifie les attributs dans le GPKG et purge le cache."""
    client = TestClient(app)
    resp = client.patch(
        "/api/v1/qualite/conduites/1",
        headers=auth_headers,
        json={"diametre": 800.0, "materiau": "PVC", "commentaire": "Correction test diamètre"}
    )
    print("PATCH RESP:", resp.status_code, resp.text)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["id_conduite"] == "1"
    assert "800.0" in str(data["champs_modifies"])
    assert "PVC" in str(data["champs_modifies"])


def test_qualite_inverser_sens_conduite(auth_headers):
    """POST /conduites/{id_conduite}/inverser-sens permute ID_AMONT et ID_AVAL."""
    client = TestClient(app)
    # 1ère inversion
    resp1 = client.post(
        "/api/v1/qualite/conduites/1/inverser-sens",
        headers=auth_headers,
        json={"commentaire": "Test inversion sens écoulement"}
    )
    assert resp1.status_code == 200
    d1 = resp1.json()
    assert d1["status"] == "success"
    amont1 = d1["nouvel_amont"]
    aval1 = d1["nouvel_aval"]
    assert amont1 == d1["ancien_aval"]
    assert aval1 == d1["ancien_amont"]

    # 2ème inversion pour remettre dans l'état initial
    resp2 = client.post(
        "/api/v1/qualite/conduites/1/inverser-sens",
        headers=auth_headers,
        json={"commentaire": "Rétablissement état initial"}
    )
    assert resp2.status_code == 200
    d2 = resp2.json()
    assert d2["nouvel_amont"] == d1["ancien_amont"]
    assert d2["nouvel_aval"] == d1["ancien_aval"]

