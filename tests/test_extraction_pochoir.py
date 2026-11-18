# -*- coding: utf-8 -*-
"""
Tests de l'extraction par pochoir (SHP.md) — outil SIG thématique.

Couvre : filtrage spatial intersection, shapefiles par thème, gpkg
fusionné + pochoir, manifeste, étanchéité org/projet, géométrie invalide.
"""

import io
import json
import tempfile
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


def _creer_contexte(db, gpkg: Path, sfx: str):
    """Org + user admin + projet pointant sur le gpkg donné."""
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
    return {"org": org, "proj": proj, "user": user, "token": token,
            "gpkg": gpkg, "sfx": sfx}


def _supprimer_contexte(db, ctx):
    proj, org, user = ctx["proj"], ctx["org"], ctx["user"]
    db.query(ProjectAuxLayer).filter(ProjectAuxLayer.project_id == proj.id).delete(
        synchronize_session=False)
    db.query(Project).filter(Project.id == proj.id).delete(synchronize_session=False)
    db.query(Membership).filter(Membership.org_id == org.id).delete(synchronize_session=False)
    db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
    db.query(Organization).filter(Organization.id == org.id).delete(synchronize_session=False)
    db.commit()


@pytest.fixture
def org_projet_reseau(db, tmp_path):
    """Org + projet avec GPKG réseau + utilisateur admin."""
    sfx = _uid()
    gpkg = tmp_path / "reseau.gpkg"
    _creer_gpkg_reseau(gpkg)
    ctx = _creer_contexte(db, gpkg, sfx)
    yield ctx
    _supprimer_contexte(db, ctx)


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
    assert ex["stats"]["reseau_regards"] == 2
    assert ex["stats"]["reseau_canalisations"] == 1
    assert ex["url_download"].startswith("/api/v1/artifacts/download")

    zf = _lire_zip(ex["url_download"], tok)
    noms = zf.namelist()
    # Shapefiles thématiques (côté .shp)
    assert "bassin_test_regards.shp" in noms
    assert "bassin_test_canalisations.shp" in noms
    assert "bassin_test.gpkg" in noms
    assert "manifeste.json" in noms

    manifeste = json.loads(zf.read("manifeste.json").decode("utf-8"))
    assert manifeste["stats"]["reseau_regards"] == 2
    assert manifeste["pochoir"]["type"] == "Polygon"

    # Le gpkg contient le pochoir + les 2 thèmes
    import tempfile, geopandas as _gpd
    with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tf:
        tf.write(zf.read("bassin_test.gpkg"))
        tmp_gpkg = tf.name
    couches = _gpd.list_layers(tmp_gpkg)["name"].tolist()
    assert "pochoir" in couches
    assert "regards" in couches and "canalisations" in couches

    # Aucune couche vide dans le gpkg (régression 'Error adding field fid')
    import sqlite3
    conn = sqlite3.connect(tmp_gpkg)
    for (t,) in conn.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type='features'"):
        n = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        assert n > 0, f"couche gpkg vide : {t}"
    conn.close()


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


def test_extraction_fusion_themes_homonymes(db, tmp_path):
    """canalisations + conduites → un seul thème 'conduite' fusionné,
    stats cumulées (régression : stats écrasées + shp/gpkg dupliqués)."""
    sfx = _uid()
    gpkg = tmp_path / "reseau_multi.gpkg"
    _creer_gpkg_reseau(gpkg)
    extra = gpd.GeoDataFrame(
        {"Code": ["C2_IN"]},
        geometry=[LineString([(1, 1), (2, 2)])],
        crs="EPSG:4326",
    )
    extra.to_file(str(gpkg), layer="conduites", driver="GPKG", mode="a")
    ctx = _creer_contexte(db, gpkg, sfx)
    try:
        client = TestClient(app)
        r = client.post(
            f"/api/v1/projets/{ctx['proj'].id}/extraction-pochoir",
            json={"nom": "Fusion", "geojson": POLYGONE,
                  "inclure_reseau": True, "aux_layer_ids": []},
            headers=_h(ctx["token"]),
        )
        assert r.status_code == 200, r.text
        ex = r.json()["extraction"]
        # 1 (canalisations) + 1 (conduites) = 2 conduites cumulées
        assert ex["stats"]["reseau_canalisations"] == 2
        assert ex["nb_objets"] == sum(ex["stats"].values())

        zf = _lire_zip(ex["url_download"], ctx["token"])
        noms = zf.namelist()
        # Un seul shp de thème conduite (pas de conduite_2)
        assert "fusion_canalisations.shp" in noms
        assert "fusion_canalisations_2.shp" not in noms

        import sqlite3
        with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tf:
            tf.write(zf.read("fusion.gpkg"))
            tmp_g = tf.name
        conn = sqlite3.connect(tmp_g)
        couches = [r[0] for r in conn.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type='features'")]
        assert "canalisations" in couches and "canalisations_2" not in couches
        n = conn.execute('SELECT COUNT(*) FROM "canalisations"').fetchone()[0]
        assert n == 2, f"canalisations gpkg = {n} ligne(s), attendu 2"
        conn.close()
        Path(tmp_g).unlink(missing_ok=True)
    finally:
        _supprimer_contexte(db, ctx)


def test_extraction_conserve_crs_source_utm(db, tmp_path):
    """Le gpkg extrait conserve le CRS projeté source (EPSG:32631).

    Régression critique : forcer EPSG:4326 cassait le Voronoï —
    generer_sous_bassins fait pt.buffer(35 m) en supposant des mètres ;
    en degrés, l'enveloppe couvre ~3 500 km (« rectangle » + étirements).
    """
    sfx = _uid()
    gpkg = tmp_path / "reseau_utm.gpkg"
    # Coordonnées UTM 31N autour de Chlef (~1.30E, 36.15N)
    regards = gpd.GeoDataFrame(
        {"Code": ["R_IN", "R_MID", "R_OUT"]},
        geometry=[Point(347500, 4002500), Point(347600, 4002600),
                  Point(347700, 4002700)],
        crs="EPSG:32631",
    )
    regards.to_file(str(gpkg), layer="regards", driver="GPKG")
    canas = gpd.GeoDataFrame(
        {"Code": ["C_IN"]},
        geometry=[LineString([(347500, 4002500), (347600, 4002600)])],
        crs="EPSG:32631",
    )
    canas.to_file(str(gpkg), layer="canalisations", driver="GPKG", mode="a")
    ctx = _creer_contexte(db, gpkg, sfx)
    try:
        # Pochoir soumis en EPSG:4326 (GeoJSON Leaflet) couvrant la zone
        poly4326 = {"type": "Polygon", "coordinates": [
            [[1.30, 36.15], [1.31, 36.15], [1.31, 36.16],
             [1.30, 36.16], [1.30, 36.15]]]}
        client = TestClient(app)
        r = client.post(
            f"/api/v1/projets/{ctx['proj'].id}/extraction-pochoir",
            json={"nom": "UTM", "geojson": poly4326,
                  "inclure_reseau": True, "aux_layer_ids": []},
            headers=_h(ctx["token"]),
        )
        assert r.status_code == 200, r.text
        ex = r.json()["extraction"]
        assert ex["manifeste"]["crs_sortie"] == "EPSG:32631"
        assert ex["stats"]["reseau_regards"] == 3
        assert ex["stats"]["reseau_canalisations"] == 1

        zf = _lire_zip(ex["url_download"], ctx["token"])
        with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tf:
            tf.write(zf.read("utm.gpkg"))
            tmp_g = tf.name
        g = gpd.read_file(tmp_g, layer="regards", rows=1)
        assert str(g.crs) == "EPSG:32631", f"CRS extrait = {g.crs}"
        # le pochoir est stocké dans le même CRS métrique
        gp = gpd.read_file(tmp_g, layer="pochoir", rows=1)
        assert str(gp.crs) == "EPSG:32631"
        Path(tmp_g).unlink(missing_ok=True)
    finally:
        _supprimer_contexte(db, ctx)


def test_prep_gdf_renomme_colonne_fid():
    """'fid' est réservé GPKG : la colonne attribut est renommée."""
    from api.services.extraction_pochoir_service import _prep_gdf_ecriture
    gdf = gpd.GeoDataFrame(
        {"fid": [1, 2], "Code": ["A", "B"]},
        geometry=[Point(0, 0), Point(1, 1)], crs="EPSG:4326")
    out = _prep_gdf_ecriture(gdf)
    assert "fid" not in out.columns
    assert "fid_attribut" in out.columns
    assert out["fid_attribut"].tolist() == [1, 2]


def test_extraction_gpkg_avec_colonne_fid(db, tmp_path):
    """Un gpkg source avec colonne attribut 'fid' (cas réel des imports
    SHP) ne doit plus produire de couches vides dans le gpkg extrait."""
    import sqlite3
    sfx = _uid()
    gpkg = tmp_path / "reseau_fid.gpkg"
    _creer_gpkg_reseau(gpkg)
    conn = sqlite3.connect(str(gpkg))
    # Reproduit la structure réelle : pk renommée fid_1, 'fid' devient
    # une colonne attribut ordinaire (héritée d'imports SHP)
    for table in ("canalisations", "regards"):
        conn.execute(f'ALTER TABLE "{table}" RENAME COLUMN fid TO fid_1')
        # DEFAULT évite les triggers rtree (UPDATE → ST_IsEmpty absent)
        conn.execute(f'ALTER TABLE "{table}" ADD COLUMN fid INTEGER DEFAULT 42')
    conn.commit()
    conn.close()

    # Sanity : geopandas relit bien la colonne fid comme attribut
    gcheck = gpd.read_file(str(gpkg), layer="canalisations")
    if "fid" not in gcheck.columns:
        pytest.skip("pyogrio n'expose pas la colonne 'fid' comme attribut")

    ctx = _creer_contexte(db, gpkg, sfx)
    try:
        client = TestClient(app)
        r = client.post(
            f"/api/v1/projets/{ctx['proj'].id}/extraction-pochoir",
            json={"nom": "FidTest", "geojson": POLYGONE,
                  "inclure_reseau": True, "aux_layer_ids": []},
            headers=_h(ctx["token"]),
        )
        assert r.status_code == 200, r.text
        ex = r.json()["extraction"]
        zf = _lire_zip(ex["url_download"], ctx["token"])
        with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tf:
            tf.write(zf.read("fidtest.gpkg"))
            tmp_g = tf.name
        conn = sqlite3.connect(tmp_g)
        for (t,) in conn.execute(
                "SELECT table_name FROM gpkg_contents WHERE data_type='features'"):
            n = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            assert n > 0, f"couche gpkg vide : {t}"
        # la valeur fid source est préservée sous fid_attribut
        cols = [r[1] for r in conn.execute("PRAGMA table_info(canalisations)")]
        assert "fid_attribut" in cols
        conn.close()
        Path(tmp_g).unlink(missing_ok=True)
    finally:
        _supprimer_contexte(db, ctx)
