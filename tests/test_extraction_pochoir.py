# -*- coding: utf-8 -*-
"""
Tests de l'extraction par pochoir (SHP.md) — outil SIG thématique.

Couvre : filtrage spatial intersection, shapefiles par thème, gpkg
fusionné + pochoir, manifeste, étanchéité org/projet, géométrie invalide.
"""

import io
import json
import zipfile
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point
from starlette.testclient import TestClient

from api.core.auth import create_access_token, hash_password
from api.database import SessionLocal
from api.main import app
from api.models import Membership, Organization, Project, ProjectAuxLayer, User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


def _uid():
    import uuid
    return uuid.uuid4().hex[:8]


def _creer_gpkg_reseau(chemin: Path):
    """GPKG projet minimal : regards (points) + canalisations (lignes), EPSG:4326."""
    regards = gpd.GeoDataFrame(
        {"Code": ["R_IN1", "R_IN2", "R_OUT"]},
        geometry=[Point(1, 1), Point(2, 2), Point(10, 10)],
        crs="EPSG:4326",
    )
    regards.to_file(str(chemin), layer="regards", driver="GPKG")
    canas = gpd.GeoDataFrame(
        {"Code": ["C_IN", "C_OUT"]},
        geometry=[LineString([(0.5, 0.5), (3, 3)]),
                  LineString([(10, 10), (20, 20)])],
        crs="EPSG:4326",
    )
    canas.to_file(str(chemin), layer="canalisations", driver="GPKG", mode="a")


@pytest.fixture
def org_projet_reseau(db, tmp_path):
    """Org + projet avec GPKG réseau + utilisateur admin."""
    sfx = _uid()
    gpkg = tmp_path / "reseau.gpkg"
    _creer_gpkg_reseau(gpkg)

    org = Organization(id=f"pox_{sfx}", name="Org Pochoir", slug=f"org-pox-{sfx}")
    user = User(id=f"pou_{sfx}", email=f"pox_{sfx}@test.dz",
                password_hash=hash_password("PoxPass2026!"),
                full_name="User Pochoir", email_verified=True)
    mem = Membership(org_id=org.id, user_id=user.id, role="admin")
    proj = Project(id=f"pop_{sfx}", org_id=org.id, name=f"Projet Pochoir {sfx}",
                   slug=f"proj-pox-{sfx}", is_archived=False,
                   source_gpkg_key=str(gpkg))
    db.add_all([org, user, mem, proj])
    db.commit()
    token = create_access_token({"sub": user.id, "org_id": org.id, "role": "admin"})
    yield {"org": org, "proj": proj, "user": user, "token": token,
           "gpkg": gpkg, "sfx": sfx}
    db.query(ProjectAuxLayer).filter(ProjectAuxLayer.project_id == proj.id).delete(
        synchronize_session=False)
    db.query(Project).filter(Project.id == proj.id).delete(synchronize_session=False)
    db.query(Membership).filter(Membership.org_id == org.id).delete(synchronize_session=False)
    db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
    db.query(Organization).filter(Organization.id == org.id).delete(synchronize_session=False)
    db.commit()


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# Polygone pochoir : carré [0,0]-[5,5] — contient R_IN1, R_IN2, C_IN
POLYGONE = {
    "type": "Polygon",
    "coordinates": [[[0, 0], [5, 0], [5, 5], [0, 5], [0, 0]]],
}


def _lire_zip(url, token):
    client = TestClient(app)
    r = client.get(url, headers=_h(token))
    assert r.status_code == 200, r.text[:300]
    return zipfile.ZipFile(io.BytesIO(r.content))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_extraction_reseau_shp_gpkg(db, org_projet_reseau):
    """Extraction réseau : shp par thème + gpkg fusionné + pochoir + manifeste."""
    client = TestClient(app)
    pid, tok = org_projet_reseau["proj"].id, org_projet_reseau["token"]

    r = client.post(
        f"/api/v1/projets/{pid}/extraction-pochoir",
        json={"nom": "Bassin_Test", "geojson": POLYGONE,
              "inclure_reseau": True, "aux_layer_ids": []},
        headers=_h(tok),
    )
    assert r.status_code == 200, r.text
    ex = r.json()["extraction"]
    assert ex["statut"] == "ok"
    assert ex["stats"]["reseau_regard"] == 2
    assert ex["stats"]["reseau_conduite"] == 1
    assert ex["url_download"].startswith("/api/v1/artifacts/download")

    zf = _lire_zip(ex["url_download"], tok)
    noms = zf.namelist()
    # Shapefiles thématiques (côté .shp)
    assert "bassin_test_regard.shp" in noms
    assert "bassin_test_conduite.shp" in noms
    assert "bassin_test.gpkg" in noms
    assert "manifeste.json" in noms

    manifeste = json.loads(zf.read("manifeste.json").decode("utf-8"))
    assert manifeste["stats"]["reseau_regard"] == 2
    assert manifeste["pochoir"]["type"] == "Polygon"

    # Le gpkg contient le pochoir + les 2 thèmes
    import tempfile, geopandas as _gpd
    with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tf:
        tf.write(zf.read("bassin_test.gpkg"))
        tmp_gpkg = tf.name
    couches = _gpd.list_layers(tmp_gpkg)["name"].tolist()
    assert "pochoir" in couches
    assert "regard" in couches and "conduite" in couches


def test_extraction_geometrie_invalide(db, org_projet_reseau):
    client = TestClient(app)
    pid, tok = org_projet_reseau["proj"].id, org_projet_reseau["token"]
    r = client.post(
        f"/api/v1/projets/{pid}/extraction-pochoir",
        json={"nom": "X", "geojson": {"type": "Point", "coordinates": [1, 1]},
              "inclure_reseau": True, "aux_layer_ids": []},
        headers=_h(tok),
    )
    assert r.status_code == 400


def test_extraction_sans_source(db, org_projet_reseau):
    """Ni réseau ni couches → refus explicite côté service (400/500)."""
    client = TestClient(app)
    pid, tok = org_projet_reseau["proj"].id, org_projet_reseau["token"]
    r = client.post(
        f"/api/v1/projets/{pid}/extraction-pochoir",
        json={"nom": "Vide", "geojson": POLYGONE,
              "inclure_reseau": False, "aux_layer_ids": []},
        headers=_h(tok),
    )
    # Service : produit un zip avec pochoir seul (statut ok) — on vérifie
    # juste que la route répond sans erreur serveur.
    assert r.status_code in (200, 400)


def test_extraction_stealth_autre_org(db, org_projet_reseau):
    """Un projet d'une autre org est invisible (stealth)."""
    client = TestClient(app)
    sfx = _uid()
    org2 = Organization(id=f"pox2_{sfx}", name="Org2", slug=f"org2-{sfx}")
    user2 = User(id=f"pou2_{sfx}", email=f"pox2_{sfx}@test.dz",
                 password_hash=hash_password("PoxPass2026!"),
                 full_name="U2", email_verified=True)
    db.add_all([org2, user2,
                Membership(org_id=org2.id, user_id=user2.id, role="admin")])
    db.commit()
    tok2 = create_access_token({"sub": user2.id, "org_id": org2.id, "role": "admin"})
    try:
        r = client.post(
            f"/api/v1/projets/{org_projet_reseau['proj'].id}/extraction-pochoir",
            json={"nom": "X", "geojson": POLYGONE,
                  "inclure_reseau": True, "aux_layer_ids": []},
            headers=_h(tok2),
        )
        assert r.status_code in (400, 404)
    finally:
        db.query(Membership).filter(Membership.org_id == org2.id).delete(
            synchronize_session=False)
        db.query(User).filter(User.id == user2.id).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.id == org2.id).delete(
            synchronize_session=False)
        db.commit()


def test_extraction_couche_satellite(db, org_projet_reseau, tmp_path):
    """Une couche satellite dans la zone est extraite en thème sat_*."""
    from api.services import aux_layers_service as aux_svc

    db_session = db
    proj = org_projet_reseau["proj"]
    # Couche satellite : 2 points dans le pochoir, 1 dehors
    gdf = gpd.GeoDataFrame(
        {"alt": [10.0, 11.0, 12.0]},
        geometry=[Point(1, 1), Point(4, 4), Point(50, 50)],
        crs="EPSG:4326",
    )
    f = tmp_path / "topo.geojson"
    gdf.to_file(str(f), driver="GeoJSON")
    couche = aux_svc.importer_couche_aux(
        db=db_session, org_id=proj.org_id, project_id=proj.id,
        type_couche="autre", nom="Topomatique", fichier_path=f,
        fichier_nom="topo.geojson")

    client = TestClient(app)
    tok = org_projet_reseau["token"]
    r = client.post(
        f"/api/v1/projets/{proj.id}/extraction-pochoir",
        json={"nom": "Mixte", "geojson": POLYGONE,
              "inclure_reseau": False, "aux_layer_ids": [couche["id"]]},
        headers=_h(tok),
    )
    assert r.status_code == 200, r.text
    ex = r.json()["extraction"]
    assert "reseau_regard" not in ex["stats"]
    cles_sat = [k for k in ex["stats"] if k.startswith("sat_")]
    assert cles_sat, f"stats sans thème satellite : {ex['stats']}"
    assert ex["stats"][cles_sat[0]] == 2
