# -*- coding: utf-8 -*-
"""
Tests endpoints HTTP des couches auxiliaires (ex-test_aux_layers.py)
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
from api.models import GpkgVersion, Membership, Organization, Project, ProjectAuxLayer, User
from api.services import aux_altimetrie_service as alt
from api.services import aux_layers_service as svc

from tests.aux_layers_support import (
    _ecrire_fichier, _gpkg_regards, _h, _importer_topo,
    _topo_gdf, _uid, db, org_projet,
)

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
            files=[("files", ("topo.gpkg", fh, "application/octet-stream"))],
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
                        files=[("files", ("t.gpkg", fh, "application/octet-stream"))],
                        data={"type": "inconnu"}, headers=_h(tok))
    assert r.status_code == 400

    # .shp SANS sidecars → 400
    f2 = tmp_path / "t.shp"
    _ecrire_fichier(gdf, f2, "shp")
    with open(f2, "rb") as fh:
        r = client.post(f"/api/v1/projets/{pid}/aux-layers",
                        files=[("files", ("t.shp", fh, "application/octet-stream"))],
                        data={"type": "autre"}, headers=_h(tok))
    assert r.status_code == 400


def test_endpoint_upload_shp_multi_fichiers(db, org_projet, tmp_path):
    """Un .shp + ses sidecars envoyés ensemble (multi-fichiers) doit être accepté."""
    client = TestClient(app)
    pid = org_projet["proj"].id
    tok = org_projet["token"]

    gdf = _topo_gdf(n=20, spread=500.0)
    shp_dir = tmp_path / "jeu_shp"
    shp_dir.mkdir()
    _ecrire_fichier(gdf, shp_dir / "topo.shp", "shp")

    fichiers = []
    for p in sorted(shp_dir.iterdir()):
        fichiers.append(("files", (p.name, open(p, "rb"), "application/octet-stream")))
    try:
        r = client.post(f"/api/v1/projets/{pid}/aux-layers",
                        files=fichiers,
                        data={"type": "metrologie", "nom": "Shp direct"},
                        headers=_h(tok))
    finally:
        for _, (_, fh, _) in fichiers:
            fh.close()
    assert r.status_code == 200, r.text
    assert r.json()["couche"]["nb_features"] == 20


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


# ---------------------------------------------------------------------------
# Tests artefact dérivé : cote terrain + pente par regard (SHP.md §7)
# ---------------------------------------------------------------------------
