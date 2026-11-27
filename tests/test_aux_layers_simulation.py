# -*- coding: utf-8 -*-
"""
Tests résolution altimétrie & versioning GPKG (ex-test_aux_layers.py)
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

def test_resoudre_altimetrie_noeuds_mode_terrain():
    """Option C — elevations_terrain : cotes injectées, nœud non couvert
    estimé par voisinage (jamais de repli datum 100 m), provenance tracée."""
    import geopandas as gpd
    from shapely.geometry import LineString, Point
    from src.domain.moteur_swmm.assainissement_topologique import (
        _resoudre_altimetrie_noeuds,
    )

    regards = gpd.GeoDataFrame(
        {"Code": ["A", "B", "C"], "Profondeur": [2.0, 2.0, 2.0]},
        geometry=[Point(0, 0), Point(100, 0), Point(200, 0)],
        crs="EPSG:32631",
    )
    canas = gpd.GeoDataFrame(
        {"ID_AMANT": ["A", "B"], "ID_AVAL": ["B", "C"], "Longeur": [100.0, 100.0]},
        geometry=[LineString([(0, 0), (100, 0)]), LineString([(100, 0), (200, 0)])],
        crs="EPSG:32631",
    )
    elevations_terrain = {"A": 105.0, "B": 103.5}  # C non couvert
    meta = {"layer_nom": "Topographie Chlef", "resolution_m": 29.94,
            "gpkg_sha256": "abcdef1234567890"}

    elevs, src = _resoudre_altimetrie_noeuds(
        regards, canas, None, "C", pente_moyenne_pct=1.0,
        elevations_terrain=elevations_terrain, altimetrie_meta=meta)

    assert elevs["A"] == 105.0
    assert elevs["B"] == 103.5
    # C non couvert → estimé par le voisin le plus proche (B, 100 m)
    assert elevs["C"] == 103.5
    assert "Terrain IDW" in src
    assert "Topographie Chlef" in src
    # Toutes les cotes sont dans le datum terrain — aucune valeur ~100 m
    # du datum synthétique (sauf coïncidence)
    assert all(100.0 < v < 200.0 for v in elevs.values())


def test_resoudre_elevations_terrain_pour_simulation_absent(db, org_projet):
    """Option C — sans couche altimétrie, le résolveur répond 'absent'."""
    from api.services.aux_altimetrie_service import (
        resoudre_elevations_terrain_pour_simulation,
    )
    res = resoudre_elevations_terrain_pour_simulation(
        db, org_projet["org"].id, org_projet["proj"].id)
    assert res["statut"] in ("absent", "ignore")

def test_couches_scopees_par_version_gpkg(db, org_projet, tmp_path):
    """Cloisonnement réseau : une couche importée sur la version V1 du
    projet disparaît quandcelui-ci pointe sur V2 (autre réseau chargé),
    et réapparaît sur V1 — jamais visible sur un réseau différent."""
    client = TestClient(app)
    proj = org_projet["proj"]
    pid, tok = proj.id, org_projet["token"]

    # Deux versions GPKG factices du MÊME projet (même project_id)
    v1 = GpkgVersion(org_id=proj.org_id, project_id=pid,
                     sha256="a" * 64, size_bytes=1,
                     storage_kind="LEGACY_LOCAL", storage_ref="/tmp/v1.gpkg")
    v2 = GpkgVersion(org_id=proj.org_id, project_id=pid,
                     sha256="b" * 64, size_bytes=1,
                     storage_kind="LEGACY_LOCAL", storage_ref="/tmp/v2.gpkg")
    db.add_all([v1, v2])
    db.commit()

    # Projet sur V1 → import d'une couche altimétrie
    proj.gpkg_version_id = v1.id
    db.commit()
    gdf = _topo_gdf(n=30)
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
    layer_id = r.json()["couche"]["id"]
    assert r.json()["couche"]["gpkg_version_id"] == v1.id

    try:
        # Visible sur V1
        r = client.get(f"/api/v1/projets/{pid}/aux-layers", headers=_h(tok))
        assert any(c["id"] == layer_id for c in r.json()["couches"])

        # Bascule sur V2 (autre réseau chargé) → couche invisible partout
        proj.gpkg_version_id = v2.id
        db.commit()
        r = client.get(f"/api/v1/projets/{pid}/aux-layers", headers=_h(tok))
        assert r.status_code == 200
        assert not any(c["id"] == layer_id for c in r.json()["couches"])
        assert client.get(f"/api/v1/projets/{pid}/aux-layers/{layer_id}",
                          headers=_h(tok)).status_code == 404
        assert client.get(f"/api/v1/projets/{pid}/aux-layers/{layer_id}/geojson",
                          headers=_h(tok)).status_code == 404

        # Retour sur V1 → la couche réapparaît (même réseau = même version)
        proj.gpkg_version_id = v1.id
        db.commit()
        r = client.get(f"/api/v1/projets/{pid}/aux-layers", headers=_h(tok))
        assert any(c["id"] == layer_id for c in r.json()["couches"])
    finally:
        # FK project_aux_layers.gpkg_version_id : couches d'abord
        db.query(ProjectAuxLayer).filter(
            ProjectAuxLayer.project_id == pid).delete(synchronize_session=False)
        db.query(GpkgVersion).filter(GpkgVersion.id.in_([v1.id, v2.id])).delete(
            synchronize_session=False)
        db.commit()


def test_endpoint_delete_couche(db, org_projet, tmp_path):
    """DELETE /aux-layers/{id} : supprime ligne + artefacts stockés ;
    stealth 404 pour un tenant d'une autre organisation."""
    client = TestClient(app)
    pid = org_projet["proj"].id
    tok = org_projet["token"]

    res = _importer_topo(db, org_projet, tmp_path, n=20)
    layer_id = res["id"]

    # Visible dans la liste
    r = client.get(f"/api/v1/projets/{pid}/aux-layers", headers=_h(tok))
    assert any(c["id"] == layer_id for c in r.json()["couches"])

    # Artefact stocké présent avant suppression
    from api.services.aux_layers_service import cle_couche_aux, _store
    cle = cle_couche_aux(org_projet["org"].id, pid, layer_id, "layer.gpkg")
    assert _store().exists(cle)

    # Suppression par une AUTRE org → stealth 404, couche conservée
    sfx = _uid()
    org_b = Organization(id=f"auxdb_{sfx}", name="B", slug=f"b-{sfx}")
    user_b = User(id=f"auxub2_{sfx}", email=f"b2_{sfx}@t.dz",
                  password_hash=hash_password("BPass2026!"), full_name="B",
                  email_verified=True)
    db.add_all([org_b, user_b,
                Membership(org_id=org_b.id, user_id=user_b.id, role="admin")])
    db.commit()
    tok_b = create_access_token({"sub": user_b.id, "org_id": org_b.id, "role": "admin"})
    try:
        r = client.delete(f"/api/v1/projets/{pid}/aux-layers/{layer_id}",
                          headers=_h(tok_b))
        assert r.status_code == 404
        assert db.query(ProjectAuxLayer).filter(
            ProjectAuxLayer.id == layer_id).first() is not None
    finally:
        db.query(Membership).filter(Membership.org_id == org_b.id).delete(
            synchronize_session=False)
        db.query(User).filter(User.id == user_b.id).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.id == org_b.id).delete(
            synchronize_session=False)
        db.commit()

    # Suppression par le bon tenant → ok, ligne + artefacts purgés
    r = client.delete(f"/api/v1/projets/{pid}/aux-layers/{layer_id}", headers=_h(tok))
    assert r.status_code == 200, r.text
    assert r.json()["statut"] == "ok"
    assert db.query(ProjectAuxLayer).filter(
        ProjectAuxLayer.id == layer_id).first() is None
    assert not _store().exists(cle)

    # Désormais absente de la liste et en 404
    r = client.get(f"/api/v1/projets/{pid}/aux-layers", headers=_h(tok))
    assert not any(c["id"] == layer_id for c in r.json()["couches"])
    assert client.get(f"/api/v1/projets/{pid}/aux-layers/{layer_id}",
                      headers=_h(tok)).status_code == 404
    # Double suppression → 404 (idempotent côté client, pas de 500)
    assert client.delete(f"/api/v1/projets/{pid}/aux-layers/{layer_id}",
                         headers=_h(tok)).status_code == 404
