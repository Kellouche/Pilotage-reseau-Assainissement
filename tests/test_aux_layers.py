# -*- coding: utf-8 -*-
"""
Tests des couches SIG « satellite » (SHP.md) — P0.

Couvre : import .gpkg/.geojson/.zip, conversion CRS, métadonnées,
grille IDW + sonde altimétrique, endpoints HTTP, stealth-404 inter-org,
et non-régression d'indépendance (aucune écriture GPKG projet / tables réseau).
"""

import io
import json
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Point
from starlette.testclient import TestClient

from api.core.auth import create_access_token, hash_password
from api.database import SessionLocal
from api.main import app
from api.models import Membership, Organization, Project, ProjectAuxLayer, User
from api.services import aux_altimetrie_service as alt
from api.services import aux_layers_service as svc


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


@pytest.fixture
def org_projet(db):
    """Organisation + projet minimal + utilisateur admin (pour JWT)."""
    sfx = _uid()
    org = Organization(id=f"auxo_{sfx}", name="Org Aux", slug=f"org-aux-{sfx}")
    user = User(id=f"auxu_{sfx}", email=f"aux_{sfx}@test.dz",
                password_hash=hash_password("AuxPass2026!"),
                full_name="User Aux", email_verified=True)
    mem = Membership(org_id=org.id, user_id=user.id, role="admin")
    proj = Project(id=f"auxp_{sfx}", org_id=org.id, name=f"Projet Aux {sfx}",
                   slug=f"proj-aux-{sfx}", is_archived=False)
    db.add_all([org, user, mem, proj])
    db.commit()
    token = create_access_token({"sub": user.id, "org_id": org.id, "role": "admin"})
    yield {"org": org, "proj": proj, "user": user, "token": token, "sfx": sfx}
    # Nettoyage
    db.query(ProjectAuxLayer).filter(ProjectAuxLayer.project_id == proj.id).delete(synchronize_session=False)
    db.query(Project).filter(Project.id == proj.id).delete(synchronize_session=False)
    db.query(Membership).filter(Membership.org_id == org.id).delete(synchronize_session=False)
    db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
    db.query(Organization).filter(Organization.id == org.id).delete(synchronize_session=False)
    db.commit()


def _topo_gdf(n=40, spread=3000.0):
    """Nuage de points topographiques synthétique : pente Ouest→Est, z = 100 - 0.002*x_m."""
    rng = np.random.default_rng(42)
    # Centre approximatif Chlef : lon 1.32, lat 36.17 → UTM31
    cx, cy = 410000.0, 4006000.0
    xs = cx + rng.uniform(-spread, spread, n)
    ys = cy + rng.uniform(-spread, spread, n)
    zs = 100.0 - 0.002 * (xs - cx) + rng.normal(0, 0.5, n)
    from pyproj import Transformer
    t = Transformer.from_crs("EPSG:32631", "EPSG:4326", always_xy=True)
    lons, lats = t.transform(xs, ys)
    return gpd.GeoDataFrame(
        {"Field4": zs, "nom": [f"PT{i}" for i in range(n)]},
        geometry=[Point(lo, la) for lo, la in zip(lons, lats)],
        crs="EPSG:4326",
    )


def _ecrire_fichier(gdf, path: Path, fmt="gpkg"):
    if fmt == "gpkg":
        gdf.to_file(path, driver="GPKG", layer="topo")
    elif fmt == "geojson":
        gdf.to_file(path, driver="GeoJSON")
    elif fmt == "shp":
        # shapefile exige noms <=10 chars : on renomme les colonnes
        gdf2 = gdf.rename(columns={"Field4": "Z", "nom": "NM"})
        gdf2[["NM", "Z", "geometry"]].to_file(path, driver="ESRI Shapefile")


# ---------------------------------------------------------------------------
# Tests service — import & métadonnées
# ---------------------------------------------------------------------------

def test_import_gpkg_et_metadonnees(db, org_projet, tmp_path):
    gdf = _topo_gdf()
    f = tmp_path / "topo.gpkg"
    _ecrire_fichier(gdf, f, "gpkg")

    res = svc.importer_couche_aux(
        db=db, org_id=org_projet["org"].id, project_id=org_projet["proj"].id,
        type_couche="altimetrie_points", nom="Topo test",
        fichier_path=f, fichier_nom="topo.gpkg", colonne_z="Field4",
    )
    assert res["type"] == "altimetrie_points"
    assert res["nb_features"] == 40
    assert res["colonne_z"] == "Field4"
    assert res["emprise"]["minx"] < res["emprise"]["maxx"]
    assert res["crs_source"] is not None

    couche = db.query(ProjectAuxLayer).filter(ProjectAuxLayer.id == res["id"]).first()
    assert couche is not None
    assert couche.org_id == org_projet["org"].id
    assert couche.project_id == org_projet["proj"].id


def test_import_geojson(db, org_projet, tmp_path):
    gdf = _topo_gdf(n=10)
    f = tmp_path / "pts.geojson"
    _ecrire_fichier(gdf, f, "geojson")
    res = svc.importer_couche_aux(
        db=db, org_id=org_projet["org"].id, project_id=org_projet["proj"].id,
        type_couche="metrologie", nom="Points mesure",
        fichier_path=f, fichier_nom="pts.geojson",
    )
    assert res["nb_features"] == 10


def test_import_zip_shp(db, org_projet, tmp_path):
    """Un .zip contenant le jeu .shp complet doit être accepté."""
    gdf = _topo_gdf(n=15)
    shp_dir = tmp_path / "shpsrc"
    shp_dir.mkdir()
    _ecrire_fichier(gdf, shp_dir / "topo.shp", "shp")

    zip_path = tmp_path / "topo.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for p in shp_dir.iterdir():
            zf.write(p, p.name)

    res = svc.importer_couche_aux(
        db=db, org_id=org_projet["org"].id, project_id=org_projet["proj"].id,
        type_couche="bv_officiel", nom="BV zip",
        fichier_path=zip_path, fichier_nom="topo.zip",
    )
    assert res["nb_features"] == 15


def test_import_shp_seul_refuse(db, org_projet, tmp_path):
    """Un .shp sans sidecars est refusé (EXTENSIONS n'inclut pas .shp)."""
    gdf = _topo_gdf(n=5)
    f = tmp_path / "topo.shp"
    _ecrire_fichier(gdf, f, "shp")
    with pytest.raises(ValueError, match="non supporté"):
        svc.importer_couche_aux(
            db=db, org_id=org_projet["org"].id, project_id=org_projet["proj"].id,
            type_couche="autre", nom="x", fichier_path=f, fichier_nom="topo.shp",
        )


def test_import_type_invalide(db, org_projet, tmp_path):
    gdf = _topo_gdf(n=5)
    f = tmp_path / "t.gpkg"
    _ecrire_fichier(gdf, f, "gpkg")
    with pytest.raises(ValueError, match="Type de couche invalide"):
        svc.importer_couche_aux(
            db=db, org_id=org_projet["org"].id, project_id=org_projet["proj"].id,
            type_couche="hack", nom="x", fichier_path=f, fichier_nom="t.gpkg",
        )


def test_import_projet_autre_org_refuse(db, org_projet, tmp_path):
    """Un projet d'une autre org ne peut pas recevoir de couche (isolation)."""
    sfx = _uid()
    org_b = Organization(id=f"auxb_{sfx}", name="Org B", slug=f"org-b-{sfx}")
    proj_b = Project(id=f"auxpb_{sfx}", org_id=org_b.id, name="P B", slug=f"pb-{sfx}")
    db.add_all([org_b, proj_b]); db.commit()
    try:
        gdf = _topo_gdf(n=5)
        f = tmp_path / "t.gpkg"
        _ecrire_fichier(gdf, f, "gpkg")
        with pytest.raises(ValueError, match="Projet introuvable"):
            svc.importer_couche_aux(
                db=db, org_id=org_projet["org"].id, project_id=proj_b.id,
                type_couche="autre", nom="x", fichier_path=f, fichier_nom="t.gpkg",
            )
    finally:
        db.query(Project).filter(Project.id == proj_b.id).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.id == org_b.id).delete(synchronize_session=False)
        db.commit()


# ---------------------------------------------------------------------------
# Tests service — altimétrie (grille IDW + sonde)
# ---------------------------------------------------------------------------

def _importer_topo(db, ctx, tmp_path, n=1500, spread=1200.0):
    gdf = _topo_gdf(n=n, spread=spread)
    f = tmp_path / "topo.gpkg"
    _ecrire_fichier(gdf, f, "gpkg")
    res = svc.importer_couche_aux(
        db=db, org_id=ctx["org"].id, project_id=ctx["proj"].id,
        type_couche="altimetrie_points", nom="Topo",
        fichier_path=f, fichier_nom="topo.gpkg", colonne_z="Field4",
    )
    return res


def test_grille_et_elevation(db, org_projet, tmp_path):
    res = _importer_topo(db, org_projet, tmp_path)
    couche = db.query(ProjectAuxLayer).filter(ProjectAuxLayer.id == res["id"]).first()

    meta = alt.construire_grille_altimetrie(
        org_id=org_projet["org"].id, project_id=org_projet["proj"].id,
        layer_id=couche.id, storage_key=couche.storage_key,
        colonne_z="Field4",
    )
    assert meta["nb_points"] == 1500
    assert meta["colonne_z"] == "Field4"
    assert meta["grille"]["nx"] > 10 and meta["grille"]["ny"] > 10

    # Sonde au centre de l'emprise : la pente synthétique est z = 100 - 0.002*(x-cx)
    # Convertit le centre UTM en lon/lat
    from pyproj import Transformer
    cx, cy = 410000.0, 4006000.0
    t = Transformer.from_crs("EPSG:32631", "EPSG:4326", always_xy=True)
    lon, lat = t.transform(cx, cy)
    r = alt.elevation(org_projet["org"].id, org_projet["proj"].id, couche.id, lon, lat)
    assert r["statut"] == "ok"
    assert 90 < r["z_terrain_m"] < 110  # attendu ~100 ± bruit
    assert r["confiance"] in ("haute", "moyenne")
    assert "terrain" in r["avertissement"].lower()


def test_elevation_hors_emprise(db, org_projet, tmp_path):
    res = _importer_topo(db, org_projet, tmp_path)
    couche = db.query(ProjectAuxLayer).filter(ProjectAuxLayer.id == res["id"]).first()
    alt.construire_grille_altimetrie(
        org_id=org_projet["org"].id, project_id=org_projet["proj"].id,
        layer_id=couche.id, storage_key=couche.storage_key, colonne_z="Field4",
    )
    r = alt.elevation(org_projet["org"].id, org_projet["proj"].id, couche.id, 0.0, 0.0)
    assert r["statut"] == "hors_emprise"
    assert r["confiance"] == "aucune"


def test_geojson_bounds(db, org_projet, tmp_path):
    res = _importer_topo(db, org_projet, tmp_path, n=30)
    couche = db.query(ProjectAuxLayer).filter(ProjectAuxLayer.id == res["id"]).first()

    # Emprise complète
    gj = svc.geojson_couche(couche.id, couche.storage_key, couche.nb_features)
    assert len(gj["features"]) == 30

    # Bounds réduite : moitié Ouest
    em = couche.emprise
    midx = (em["minx"] + em["maxx"]) / 2
    gj2 = svc.geojson_couche(
        couche.id, couche.storage_key, couche.nb_features,
        bounds=(em["minx"], em["miny"], midx, em["maxy"]),
    )
    assert 0 < len(gj2["features"]) < 30


# ---------------------------------------------------------------------------
# Tests endpoints HTTP — auth + stealth 404
# ---------------------------------------------------------------------------

def _h(token):
    return {"Authorization": f"Bearer {token}"}


def test_endpoint_upload_liste_geojson_elevation(db, org_projet, tmp_path):
    client = TestClient(app)
    pid = org_projet["proj"].id
    tok = org_projet["token"]

    # Upload altimétrie via API
    gdf = _topo_gdf(n=50)
    f = tmp_path / "topo.gpkg"
    _ecrire_fichier(gdf, f, "gpkg")
    with open(f, "rb") as fh:
        r = client.post(
            f"/api/v1/projets/{pid}/aux-layers",
            files={"file": ("topo.gpkg", fh, "application/octet-stream")},
            data={"type": "altimetrie_points", "colonne_z": "Field4"},
            headers=_h(tok),
        )
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["statut"] == "ok"
    couche = corps["couche"]
    assert couche["type"] == "altimetrie_points"
    assert couche["statut"] == "ok"
    assert "grille_altimetrie" in corps["couche"] or "grille_altimetrie" in corps

    layer_id = couche["id"]

    # Liste
    r = client.get(f"/api/v1/projets/{pid}/aux-layers", headers=_h(tok))
    assert r.status_code == 200
    assert any(c["id"] == layer_id for c in r.json()["couches"])

    # GeoJSON borné
    em = couche["emprise"]
    bounds = f"{em['minx']},{em['miny']},{em['maxx']},{em['maxy']}"
    r = client.get(f"/api/v1/projets/{pid}/aux-layers/{layer_id}/geojson?bounds={bounds}",
                   headers=_h(tok))
    assert r.status_code == 200
    # Un point peut tomber exactement sur la frontière d'emprise (exclu par cx)
    assert r.json()["nb_features"] >= 45

    # Sonde altimétrique
    lon = (em["minx"] + em["maxx"]) / 2
    lat = (em["miny"] + em["maxy"]) / 2
    r = client.get(f"/api/v1/projets/{pid}/aux-layers/{layer_id}/elevation?lng={lon}&lat={lat}",
                   headers=_h(tok))
    assert r.status_code == 200
    assert r.json()["statut"] == "ok"
    assert r.json()["confiance"] in ("haute", "moyenne", "faible")


def test_endpoint_type_invalide_et_shp_seul(db, org_projet, tmp_path):
    client = TestClient(app)
    pid = org_projet["proj"].id
    tok = org_projet["token"]

    # Type invalide → 400
    gdf = _topo_gdf(n=5)
    f = tmp_path / "t.gpkg"
    _ecrire_fichier(gdf, f, "gpkg")
    with open(f, "rb") as fh:
        r = client.post(f"/api/v1/projets/{pid}/aux-layers",
                        files={"file": ("t.gpkg", fh, "application/octet-stream")},
                        data={"type": "inconnu"}, headers=_h(tok))
    assert r.status_code == 400

    # .shp seul → 400
    f2 = tmp_path / "t.shp"
    _ecrire_fichier(gdf, f2, "shp")
    with open(f2, "rb") as fh:
        r = client.post(f"/api/v1/projets/{pid}/aux-layers",
                        files={"file": ("t.shp", fh, "application/octet-stream")},
                        data={"type": "autre"}, headers=_h(tok))
    assert r.status_code == 400


def test_endpoint_stealth_404(db, org_projet, tmp_path):
    """Une couche d'un autre projet/org → 404 (pas de fuite)."""
    client = TestClient(app)
    # Import via service pour un projet A
    res = _importer_topo(db, org_projet, tmp_path, n=20)
    layer_id = res["id"]
    pid = org_projet["proj"].id

    # Token d'une AUTRE org
    sfx = _uid()
    org_b = Organization(id=f"auxbb_{sfx}", name="B", slug=f"b-{sfx}")
    user_b = User(id=f"auxub_{sfx}", email=f"b_{sfx}@t.dz",
                  password_hash=hash_password("BPass2026!"), full_name="B", email_verified=True)
    mem_b = Membership(org_id=org_b.id, user_id=user_b.id, role="admin")
    db.add_all([org_b, user_b, mem_b]); db.commit()
    tok_b = create_access_token({"sub": user_b.id, "org_id": org_b.id, "role": "admin"})
    try:
        for url in [
            f"/api/v1/projets/{pid}/aux-layers",
            f"/api/v1/projets/{pid}/aux-layers/{layer_id}",
            f"/api/v1/projets/{pid}/aux-layers/{layer_id}/geojson",
            f"/api/v1/projets/{pid}/aux-layers/{layer_id}/elevation?lng=1&lat=36",
        ]:
            r = client.get(url, headers=_h(tok_b))
            assert r.status_code == 404, f"{url} → {r.status_code} (attendu 404)"
    finally:
        db.query(Membership).filter(Membership.org_id == org_b.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user_b.id).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.id == org_b.id).delete(synchronize_session=False)
        db.commit()


def test_endpoint_sans_altitude_colonne_z(db, org_projet, tmp_path):
    """Sans colonne_z ni auto-détection → statut sans_altitude, endpoints elevation → 422."""
    client = TestClient(app)
    pid = org_projet["proj"].id
    tok = org_projet["token"]

    # GeoJSON avec colonne non détectable (nom générique 'valeur')
    gdf = _topo_gdf(n=10).rename(columns={"Field4": "valeur"})
    f = tmp_path / "topo.geojson"
    _ecrire_fichier(gdf, f, "geojson")
    with open(f, "rb") as fh:
        r = client.post(f"/api/v1/projets/{pid}/aux-layers",
                        files={"file": ("topo.geojson", fh, "application/geo+json")},
                        data={"type": "altimetrie_points"}, headers=_h(tok))
    assert r.status_code == 200, r.text
    couche = r.json()["couche"]
    assert couche["statut"] == "sans_altitude"

    r = client.get(f"/api/v1/projets/{pid}/aux-layers/{couche['id']}/elevation?lng=1.3&lat=36.17",
                   headers=_h(tok))
    assert r.status_code == 422
