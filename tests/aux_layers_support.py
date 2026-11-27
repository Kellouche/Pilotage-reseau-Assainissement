# -*- coding: utf-8 -*-
"""
Support partagé des tests de couches SIG « satellite » : fixtures et helpers.
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

def _h(token):
    return {"Authorization": f"Bearer {token}"}

def _gpkg_regards(tmp_path, coords_ll, codes):
    """Petit GPKG avec couche 'Regards_…' (code + points WGS84)."""
    g = gpd.GeoDataFrame(
        {"Code": codes, "NOM": [f"R{i}" for i in range(len(codes))]},
        geometry=[Point(lo, la) for lo, la in coords_ll],
        crs="EPSG:4326",
    )
    f = tmp_path / "reseau_test.gpkg"
    g.to_file(f, driver="GPKG", layer="Regards_test")
    return f
