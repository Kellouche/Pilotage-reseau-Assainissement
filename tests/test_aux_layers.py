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


def test_regards_terrain_artefact(db, org_projet, tmp_path):
    """L'artefact produit z_terrain + pente + azimut pour chaque regard du GPKG projet."""
    # Regarder positions = sous-ensemble des points topo (dans l'emprise)
    topo = _topo_gdf(n=1500, spread=1200.0)
    coords = [(p.x, p.y) for p in topo.geometry.iloc[::100]]  # ~15 regards
    codes = [str(700 + i) for i in range(len(coords))]
    gpkg_regards = _gpkg_regards(tmp_path, coords, codes)

    # Rattacher le GPKG au projet
    proj = db.query(Project).filter(Project.id == org_projet["proj"].id).first()
    proj.source_gpkg_key = str(gpkg_regards)
    db.commit()

    # Import topo + grille
    f = tmp_path / "topo.gpkg"
    _ecrire_fichier(topo, f, "gpkg")
    res = svc.importer_couche_aux(
        db=db, org_id=org_projet["org"].id, project_id=org_projet["proj"].id,
        type_couche="altimetrie_points", nom="Topo",
        fichier_path=f, fichier_nom="topo.gpkg", colonne_z="Field4",
    )
    couche = db.query(ProjectAuxLayer).filter(ProjectAuxLayer.id == res["id"]).first()
    meta = alt.construire_grille_altimetrie(
        org_id=org_projet["org"].id, project_id=org_projet["proj"].id,
        layer_id=couche.id, storage_key=couche.storage_key, colonne_z="Field4",
    )
    assert meta["nb_points"] == 1500

    rt = alt.calculer_regards_terrain(
        db=db, org_id=org_projet["org"].id, project_id=org_projet["proj"].id,
        layer_id=couche.id, storage_key=couche.storage_key,
    )
    assert rt["statut"] == "ok"
    assert rt["nb_regards"] == len(coords)

    artefact = alt.charger_regards_terrain(org_projet["org"].id, org_projet["proj"].id, couche.id)
    assert artefact is not None
    assert artefact["meta"]["gpkg_sha256"]
    r0 = artefact["regards"]["700"]
    assert r0["z_terrain_m"] is not None
    assert 90 < r0["z_terrain_m"] < 110
    assert r0["confiance"] in ("haute", "moyenne")
    assert r0["pente_terrain_pct"] is not None
    assert 0 <= r0["azimut_pente_deg"] < 360


def test_regards_terrain_sans_gpkg(db, org_projet, tmp_path):
    """Projet sans GPKG → artefact 'ignore' honnête, pas d'erreur."""
    res = _importer_topo(db, org_projet, tmp_path, n=100, spread=800.0)
    couche = db.query(ProjectAuxLayer).filter(ProjectAuxLayer.id == res["id"]).first()
    alt.construire_grille_altimetrie(
        org_id=org_projet["org"].id, project_id=org_projet["proj"].id,
        layer_id=couche.id, storage_key=couche.storage_key, colonne_z="Field4",
    )
    rt = alt.calculer_regards_terrain(
        db=db, org_id=org_projet["org"].id, project_id=org_projet["proj"].id,
        layer_id=couche.id, storage_key=couche.storage_key,
    )
    assert rt["statut"] == "ignore"


def test_endpoint_regards_terrain(db, org_projet, tmp_path):
    """GET /regards-terrain → artefact + flag perime ; POST recalculer → ok."""
    client = TestClient(app)
    pid = org_projet["proj"].id
    tok = org_projet["token"]

    topo = _topo_gdf(n=800, spread=1000.0)
    coords = [(p.x, p.y) for p in topo.geometry.iloc[::80]]
    codes = [str(800 + i) for i in range(len(coords))]
    gpkg_regards = _gpkg_regards(tmp_path, coords, codes)
    proj = db.query(Project).filter(Project.id == pid).first()
    proj.source_gpkg_key = str(gpkg_regards)
    db.commit()

    f = tmp_path / "topo.gpkg"
    _ecrire_fichier(topo, f, "gpkg")
    with open(f, "rb") as fh:
        r = client.post(f"/api/v1/projets/{pid}/aux-layers",
                        files=[("files", ("topo.gpkg", fh, "application/octet-stream"))],
                        data={"type": "altimetrie_points", "colonne_z": "Field4"},
                        headers=_h(tok))
    assert r.status_code == 200, r.text
    layer_id = r.json()["couche"]["id"]

    # GET artefact (calculé à l'import)
    r = client.get(f"/api/v1/projets/{pid}/aux-layers/{layer_id}/regards-terrain", headers=_h(tok))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["meta"]["nb_regards"] == len(coords)
    assert "perime" in j["meta"]
    assert j["regards"]["800"]["z_terrain_m"] is not None

    # POST recalculer
    r = client.post(f"/api/v1/projets/{pid}/aux-layers/{layer_id}/regards-terrain/recalculer",
                    headers=_h(tok))
    assert r.status_code == 200, r.text
    assert r.json()["resultat"]["nb_regards"] == len(coords)


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
                        files=[("files", ("topo.geojson", fh, "application/geo+json"))],
                        data={"type": "altimetrie_points"}, headers=_h(tok))
    assert r.status_code == 200, r.text
    couche = r.json()["couche"]
    assert couche["statut"] == "sans_altitude"

    r = client.get(f"/api/v1/projets/{pid}/aux-layers/{couche['id']}/elevation?lng=1.3&lat=36.17",
                   headers=_h(tok))
    assert r.status_code == 422


def test_terrain_aux_pour_profil(db, org_projet):
    """P3 — l'artefact regards_terrain n'est servi au profil que si son
    estampillage gpkg_sha256 correspond au GPKG actif (jamais périmé)."""
    import json as _json
    from api.routes.simulations import _terrain_aux_pour_profil
    from api.services.aux_layers_service import cle_couche_aux, _store
    from api.models import ProjectAuxLayer

    oid, pid = org_projet["org"].id, org_projet["proj"].id
    couche = ProjectAuxLayer(
        org_id=oid, project_id=pid, type="altimetrie_points",
        nom="topo test", storage_key="cle-test", statut="ok",
        colonne_z="Field4", nb_features=10,
    )
    db.add(couche)
    db.commit()

    art = {
        "meta": {"gpkg_sha256": "sha_test_123", "resolution_m": 30.0},
        "regards": {"123": {"z_terrain_m": 100.5, "confiance": "haute"}},
    }
    _store().put_bytes(
        cle_couche_aux(oid, pid, couche.id, "derive/regards_terrain.json"),
        _json.dumps(art).encode("utf-8"),
    )

    # SHA correspondant → artefact retourné
    res = _terrain_aux_pour_profil(db, oid, org_projet["proj"], {"gpkg_sha": "sha_test_123"})
    assert res is not None
    assert res["artefact"]["regards"]["123"]["z_terrain_m"] == 100.5

    # SHA différent → artefact périmé ignoré
    assert _terrain_aux_pour_profil(db, oid, org_projet["proj"], {"gpkg_sha": "autre_sha"}) is None
    # Pas de sha → pas de lookup
    assert _terrain_aux_pour_profil(db, oid, org_projet["proj"], {}) is None
    # Projet None → pas de lookup
    assert _terrain_aux_pour_profil(db, oid, None, {"gpkg_sha": "sha_test_123"}) is None


def test_calculer_apercu_terrain(db, org_projet):
    """Calcul pur de l'aperçu terrain→radier : médiane profondeur, flags,
    inversions amont/aval, seuil 95 %."""
    import geopandas as gpd
    from shapely.geometry import Point
    from api.services.aux_altimetrie_service import calculer_apercu_terrain

    regards = gpd.GeoDataFrame(
        {"Code": ["A", "B", "C"], "Profondeur": [2.0, None, 3.0]},
        geometry=[Point(0, 0), Point(1, 0), Point(2, 0)], crs="EPSG:4326",
    )
    canas = gpd.GeoDataFrame(
        {"ID_AMONT": ["A", "B"], "ID_AVAL": ["B", "C"]},
        geometry=[Point(0, 0), Point(1, 0)], crs="EPSG:4326",
    )
    artefact = {
        "meta": {"gpkg_sha256": "x", "resolution_m": 30.0},
        "regards": {
            "A": {"z_terrain_m": 100.0, "confiance": "haute"},
            "B": {"z_terrain_m": 99.0, "confiance": "haute"},
            "C": {"z_terrain_m": 100.0, "confiance": "haute"},
        },
    }
    res = calculer_apercu_terrain(regards, canas, artefact)

    # Médiane des profondeurs réelles {2.0, 3.0} = 2.5
    assert res["profondeur"]["mediane_reseau_m"] == 2.5
    assert res["profondeur"]["nb_estimees"] == 1
    # B sans profondeur → médiane 2.5, flaggé
    assert res["par_regard"]["B"]["profondeur_estimee"] is True
    assert res["par_regard"]["B"]["profondeur_m"] == 2.5
    assert res["par_regard"]["B"]["z_radier_terrain_m"] == 96.5
    # A→B : 98 > 96.5 OK ; B→C : 96.5 <= 97.0 → inversion
    assert res["inversions_amont_aval"]["nb"] == 1
    assert res["inversions_amont_aval"]["echantillon"][0]["amont"] == "B"
    assert res["couverture"]["pct"] == 100.0
    assert res["eligible_injection_95"] is True


def test_endpoint_apercu_inp_absent(db, org_projet):
    """Sans artefact regards_terrain, l'aperçu répond 'absent' (pas de crash)."""
    client = TestClient(app)
    pid = org_projet["proj"].id
    tok = org_projet["token"]

    couche = ProjectAuxLayer(
        org_id=org_projet["org"].id, project_id=pid,
        type="altimetrie_points", nom="topo sans artefact",
        storage_key="cle-test", statut="ok", colonne_z="Field4",
    )
    db.add(couche)
    db.commit()

    r = client.get(f"/api/v1/projets/{pid}/aux-layers/{couche.id}/apercu-inp",
                   headers=_h(tok))
    assert r.status_code == 200
    assert r.json()["statut"] == "absent"

    # Couche d'un autre org → stealth 404
    r2 = client.get(f"/api/v1/projets/{pid}/aux-layers/{couche.id}/apercu-inp")
    assert r2.status_code in (401, 404)


def test_analyser_ecoulement_terrain():
    """P1 — file de revue : terrain qui monte le long du flux = suspect,
    conduit cohérent ignoré, sévérité et motifs corrects."""
    import geopandas as gpd
    from shapely.geometry import LineString, Point
    from api.services.aux_altimetrie_service import analyser_ecoulement_terrain

    # A(0,0) → B(0.001,0) : ~111 m vers l'Est ; C(0.002,0) plus loin
    regards = gpd.GeoDataFrame(
        {"Code": ["A", "B", "C"], "Profondeur": [2.0, 2.0, 2.0]},
        geometry=[Point(0, 0), Point(0.001, 0), Point(0.002, 0)],
        crs="EPSG:4326",
    )
    canas = gpd.GeoDataFrame(
        {"ID_AMONT": ["A", "B"], "ID_AVAL": ["B", "C"], "Longeur": [100.0, 100.0]},
        geometry=[LineString([(0, 0), (0.001, 0)]),
                  LineString([(0.001, 0), (0.002, 0)])],
        crs="EPSG:4326",
    )
    artefact = {
        "meta": {"gpkg_sha256": "x", "resolution_m": 30.0},
        "regards": {
            # A→B : terrain descend (100→99) = cohérent ; B→C : monte (99→100.5)
            "A": {"z_terrain_m": 100.0, "confiance": "haute",
                  "pente_terrain_pct": 1.0, "azimut_pente_deg": 90.0},
            "B": {"z_terrain_m": 99.0, "confiance": "haute",
                  "pente_terrain_pct": 1.5, "azimut_pente_deg": 270.0},
            "C": {"z_terrain_m": 100.5, "confiance": "haute",
                  "pente_terrain_pct": 1.0, "azimut_pente_deg": 90.0},
        },
    }
    res = analyser_ecoulement_terrain(regards, canas, artefact)

    assert res["statut"] == "ok"
    assert res["nb_conduites_analysées"] == 2
    assert res["nb_suspects"] == 1
    s = res["suspects"][0]
    assert s["amont"] == "B" and s["aval"] == "C"
    assert s["ecart_terrain_m"] == 1.5
    # 1.5 m / 100 m = 1.5 % > 1 % → fort ; + radier + azimut → score élevé
    assert s["severite"] in ("fort", "moyen")
    assert any("monte" in m for m in s["motifs"])


def test_endpoint_suspects_ecoulement_absent(db, org_projet):
    """Sans artefact, l'endpoint répond 'absent' proprement."""
    client = TestClient(app)
    pid = org_projet["proj"].id
    tok = org_projet["token"]

    couche = ProjectAuxLayer(
        org_id=org_projet["org"].id, project_id=pid,
        type="altimetrie_points", nom="topo sans artefact 2",
        storage_key="cle-test2", statut="ok", colonne_z="Field4",
    )
    db.add(couche)
    db.commit()

    r = client.get(f"/api/v1/projets/{pid}/aux-layers/{couche.id}/suspects-ecoulement",
                   headers=_h(tok))
    assert r.status_code == 200
    assert r.json()["statut"] == "absent"

    # Couche d'un autre org → stealth 404
    r2 = client.get(f"/api/v1/projets/{pid}/aux-layers/{couche.id}/suspects-ecoulement")
    assert r2.status_code in (401, 404)


def test_analyser_raccordements_terrain():
    """P2 — orphelin proche d'une cible connectée : candidat classé par
    cohérence altimétrique ; orphelin isolé → aucun candidat."""
    import geopandas as gpd
    from shapely.geometry import LineString, Point
    from api.services.aux_altimetrie_service import analyser_raccordements_terrain

    # CRS métrique (UTM-like) pour des distances en mètres
    regards = gpd.GeoDataFrame(
        {"Code": ["A", "B", "O", "O2"], "Profondeur": [2.0, 2.0, 2.0, 2.0]},
        geometry=[Point(100, 0), Point(200, 0), Point(200, 10), Point(5000, 5000)],
        crs="EPSG:32631",
    )
    canas = gpd.GeoDataFrame(
        {"ID_AMANT": ["A"], "ID_AVAL": ["B"], "Longeur": [100.0]},
        geometry=[LineString([(100, 0), (200, 0)])],
        crs="EPSG:32631",
    )
    artefact = {
        "meta": {"gpkg_sha256": "x", "resolution_m": 30.0},
        "regards": {
            "A": {"z_terrain_m": 103.0, "confiance": "haute",
                  "pente_terrain_pct": 1.0, "azimut_pente_deg": 90.0,
                  "lng": 1.0, "lat": 36.0},
            "B": {"z_terrain_m": 100.0, "confiance": "haute",
                  "pente_terrain_pct": 1.0, "azimut_pente_deg": 90.0,
                  "lng": 1.001, "lat": 36.0},
            # O : 10 m au nord de B, terrain plus haut → O→B descend
            "O": {"z_terrain_m": 105.0, "confiance": "haute",
                  "pente_terrain_pct": 1.0, "azimut_pente_deg": 180.0,
                  "lng": 1.001, "lat": 36.0001},
            "O2": {"z_terrain_m": 90.0, "confiance": "haute",
                   "pente_terrain_pct": 1.0, "azimut_pente_deg": 0.0,
                   "lng": 1.05, "lat": 36.05},
        },
    }
    res = analyser_raccordements_terrain(regards, canas, artefact, rayon_max_m=50.0)

    assert res["statut"] == "ok"
    assert res["nb_orphelins"] == 2
    par_code = {r["orphelin"]: r for r in res["orphelins"]}
    # O : cible B à 10 m, terrain descend 105→100, radier cohérent
    o = par_code["O"]
    assert o["candidats"], "O devrait avoir au moins un candidat"
    top = o["candidats"][0]
    assert top["cible"] == "B"
    assert top["distance_m"] == 10.0
    assert top["score"] > 50.0
    assert any("descend" in m for m in top["motifs"])
    # O2 : isolé à >4 km → aucun candidat dans le rayon
    assert par_code["O2"]["candidats"] == []


def test_endpoint_raccordements_orphelins_absent(db, org_projet):
    """Sans artefact, l'endpoint raccordements répond 'absent' + stealth 404."""
    client = TestClient(app)
    pid = org_projet["proj"].id
    tok = org_projet["token"]

    couche = ProjectAuxLayer(
        org_id=org_projet["org"].id, project_id=pid,
        type="altimetrie_points", nom="topo sans artefact 3",
        storage_key="cle-test3", statut="ok", colonne_z="Field4",
    )
    db.add(couche)
    db.commit()

    r = client.get(f"/api/v1/projets/{pid}/aux-layers/{couche.id}/raccordements-orphelins",
                   headers=_h(tok))
    assert r.status_code == 200
    assert r.json()["statut"] == "absent"

    r2 = client.get(f"/api/v1/projets/{pid}/aux-layers/{couche.id}/raccordements-orphelins")
    assert r2.status_code in (401, 404)


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
