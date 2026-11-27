# -*- coding: utf-8 -*-
"""
Tests des couches SIG « satellite » : import & métadonnées (ex-test_aux_layers.py)
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

# ---------------------------------------------------------------------------
# Tests service — import & métadonnées
# ---------------------------------------------------------------------------

class TestCrsObligatoire:
    """Règle CRS : aucune projection → blocage, jamais de repli silencieux."""

    def _gdf_sans_crs(self):
        gdf = gpd.GeoDataFrame(
            {"z": [10.0, 20.0]},
            geometry=[Point(600000, 4005000), Point(600100, 4005100)],
            crs=None,
        )
        return gdf

    def test_sans_crs_refuse(self):
        with pytest.raises(ValueError, match="(?i)crs|projection"):
            svc._normaliser_4326(self._gdf_sans_crs())

    def test_crs_forcee_accepte(self):
        gdf, source = svc._normaliser_4326(self._gdf_sans_crs(), crs_forcee="EPSG:32631")
        assert gdf.crs is not None
        assert "utilisateur" in source
        # Reprojection WGS84 effective : coordonnées en degrés
        assert gdf.total_bounds[0] < 10

    def test_crs_invalide_refuse(self):
        with pytest.raises(ValueError, match="(?i)invalide"):
            svc._normaliser_4326(self._gdf_sans_crs(), crs_forcee="EPSG:999999")


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
    """Un .shp sans sidecars est refusé (validation explicite)."""
    gdf = _topo_gdf(n=5)
    f = tmp_path / "topo.shp"
    _ecrire_fichier(gdf, f, "shp")
    # Supprime les sidecars pour simuler un .shp isolé
    for ext in (".shx", ".dbf", ".prj", ".cpg"):
        p = f.with_suffix(ext)
        if p.exists():
            p.unlink()
    with pytest.raises(ValueError, match="incomplet"):
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
