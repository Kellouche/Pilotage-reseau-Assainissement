# -*- coding: utf-8 -*-
"""
Correctif 3C (R1/R2) — Isolation des téléchargements INP/RPT.

Couvre :
- propriétaire autorisé (simulation persistée) ;
- fichiers .simulation_cache estampillés pour un autre projet / une autre
  organisation → refus ;
- fichier legacy NON estampillé à propriétaire ambigu (GPKG partagé entre
  projets) → refus ;
- fichier legacy non estampillé à propriétaire unique → compatibilité ;
- deux projets dans la même organisation → ambiguïté explicite (409) ;
- project_id inexistant ou hors organisation → 404 explicite.
"""

import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.database import SessionLocal
from api.models import Organization, Project, Simulation
from api.routes import simulations as sim_routes
from api.services import gpkg_versions as gv
from api.services import simulation_service as svc


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def _creer_gpkg(path: Path) -> Path:
    import geopandas as gpd
    from shapely.geometry import Point, LineString
    gpd.GeoDataFrame(
        {"id": ["N1", "N2"]},
        geometry=[Point(3.0, 36.0), Point(3.001, 36.0)],
        crs="EPSG:4326",
    ).to_file(path, layer="regards", driver="GPKG")
    gpd.GeoDataFrame(
        {"id": ["C1"]},
        geometry=[LineString([(3.0, 36.0), (3.001, 36.0)])],
        crs="EPSG:4326",
    ).to_file(path, layer="canalisations", driver="GPKG", mode="a")
    return path


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Cache simulation isolé : data/.simulation_cache → tmp_path/.simulation_cache."""
    monkeypatch.setattr(gv, "GPKG_CACHE_DIR", tmp_path / "gpkg_cache")
    cache_dir = tmp_path / ".simulation_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return {"tmp": tmp_path, "cache_dir": cache_dir}


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


def _org(db, sfx=None):
    sfx = sfx or _uid()
    org = Organization(id=f"org_dl_{sfx}", name="OrgDL", slug=f"org-dl-{sfx}")
    db.add(org)
    db.flush()
    return org


def _projet(db, org, gpkg_path, sfx=None):
    sfx = sfx or _uid()
    proj = Project(id=f"proj_dl_{sfx}", org_id=org.id, name=f"Projet DL {sfx}",
                   source_gpkg_key=str(gpkg_path) if gpkg_path else None,
                   gpkg_version_id=None)
    db.add(proj)
    db.commit()
    return proj


def _tenant(org):
    return SimpleNamespace(org_id=org.id)


def _data_sim(cluster_id=7, secret="SECRET_X", stamped=None):
    d = {
        "status": "SUCCESS",
        "inp_content": f"[TITLE]\n{secret}_INP",
        "rpt_content": f"{secret}_RPT_CONTENT",
        "meta": {"cluster_id": cluster_id, "cluster_nom": "B7",
                 "bassin_nom": "Bassin7",
                 "bbox": [3.0, 36.0, 3.1, 36.1]},
        "node_results": {"N1": {"hgl": 1.0}},
        "conduit_results": {"C1": {"q": 0.1}},
    }
    if stamped:
        d["meta"].update(stamped)
    return d


def _ecrire_cache(env, gpkg_path, data, cluster_id=7):
    """Écrit un fichier .simulation_cache au nom content-adressé attendu."""
    cle = svc._cle_cache_gpkg(gpkg_path)
    cid = svc.__dict__  # noqa - garde lisibilité
    clean_cid = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(cluster_id))
    nom = f"sim_{cle}_cluster_{clean_cid}_testhash.json"
    f = env["cache_dir"] / nom
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return f


def _cleanup(db, orgs, projs, sims=()):
    for s in sims:
        db.delete(s)
    for p in projs:
        db.delete(p)
    for o in orgs:
        db.delete(o)
    db.commit()


# ---------------------------------------------------------------------------
# Propriétaire autorisé — simulation persistée (chemin nominal)
# ---------------------------------------------------------------------------

def test_proprietaire_inp_rpt(db, env):
    """Le propriétaire télécharge INP et RPT de SA simulation."""
    org = _org(db)
    gpkg = _creer_gpkg(env["tmp"] / "p1.gpkg")
    proj = _projet(db, org, gpkg)
    data = _data_sim(secret="MA_PROPRE_SIM")
    fjson = env["tmp"] / "sim.json"
    fjson.write_text(json.dumps(data), encoding="utf-8")
    sim = Simulation(
        id=str(uuid.uuid4()), org_id=org.id, project_id=proj.id,
        name="SWMM_dl", status="completed", scenario_pluie="pluie_decennale",
        duree_heures=4.0, results_s3_key=str(fjson.resolve()),
        summary_kpis={"cluster_id": 7, "parameters": {}},
    )
    db.add(sim)
    db.commit()
    try:
        r_inp = sim_routes.download_latest_inp(db=db, tenant=_tenant(org))
        assert r_inp.status_code == 200
        assert "MA_PROPRE_SIM_INP" in r_inp.body.decode("utf-8")
        r_rpt = sim_routes.download_latest_rpt(db=db, tenant=_tenant(org))
        assert r_rpt.status_code == 200
        assert "MA_PROPRE_SIM_RPT_CONTENT" in r_rpt.body.decode("utf-8")
    finally:
        _cleanup(db, [org], [proj], [sim])


# ---------------------------------------------------------------------------
# R1 — fichiers .simulation_cache : propriété vérifiée
# ---------------------------------------------------------------------------

def test_cache_estampille_autre_projet_refuse(db, env):
    """Un fichier estampillé project_id d'un AUTRE projet est refusé."""
    org = _org(db)
    gpkg = _creer_gpkg(env["tmp"] / "partage.gpkg")
    p1 = _projet(db, org, gpkg)
    p2 = _projet(db, org, gpkg)
    # Fichier estampillé pour p2, demandé dans le contexte de p1
    _ecrire_cache(env, gpkg, _data_sim(
        secret="FUIE_P2", stamped={"project_id": p2.id, "org_id": org.id}))
    try:
        with pytest.raises(HTTPException) as exc:
            sim_routes.download_latest_rpt(
                cluster_id="7", project_id=p1.id, db=db, tenant=_tenant(org))
        assert exc.value.status_code == 404
        # INP : le secret d'un autre projet ne doit JAMAIS être servi —
        # soit 404, soit un INP assemblé générique sans le contenu stampillé.
        try:
            r_inp = sim_routes.download_latest_inp(
                cluster_id="7", project_id=p1.id, db=db, tenant=_tenant(org))
            assert "FUIE_P2_INP" not in r_inp.body.decode("utf-8")
        except HTTPException as exc_inp:
            assert exc_inp.status_code == 404
    finally:
        _cleanup(db, [org], [p1, p2])


def test_cache_estampille_autre_org_refuse(db, env):
    """Un fichier estampillé org_id d'une AUTRE organisation est refusé."""
    orgA, orgB = _org(db), _org(db)
    gpkg = _creer_gpkg(env["tmp"] / "orgb.gpkg")
    pA = _projet(db, orgA, gpkg)
    _ecrire_cache(env, gpkg, _data_sim(
        secret="FUIE_ORGB", stamped={"project_id": "proj_x", "org_id": orgB.id}))
    try:
        with pytest.raises(HTTPException) as exc:
            sim_routes.download_latest_rpt(
                cluster_id="7", project_id=pA.id, db=db, tenant=_tenant(orgA))
        assert exc.value.status_code == 404
    finally:
        _cleanup(db, [orgA, orgB], [pA])


def test_cache_non_estampille_gpkg_partage_refuse(db, env):
    """GPKG partagé entre deux projets (orgs distinctes) : un fichier
    NON estampillé a un propriétaire ambigu → refusé."""
    orgA, orgB = _org(db), _org(db)
    gpkg = _creer_gpkg(env["tmp"] / "partage_orgs.gpkg")
    pA = _projet(db, orgA, gpkg)
    pB = _projet(db, orgB, gpkg)  # même fichier source → même contenu
    _ecrire_cache(env, gpkg, _data_sim(secret="AMBIGU"))  # sans estampille
    try:
        with pytest.raises(HTTPException) as exc:
            sim_routes.download_latest_rpt(
                cluster_id="7", project_id=pA.id, db=db, tenant=_tenant(orgA))
        assert exc.value.status_code == 404
    finally:
        _cleanup(db, [orgA, orgB], [pA, pB])


def test_cache_legacy_non_estampille_proprietaire_unique(db, env):
    """Compatibilité : fichier legacy non estampillé, GPKG possédé par un
    SEUL projet → servi (téléchargements historiques légitimes)."""
    org = _org(db)
    gpkg = _creer_gpkg(env["tmp"] / "unique.gpkg")
    proj = _projet(db, org, gpkg)
    _ecrire_cache(env, gpkg, _data_sim(secret="LEGITIME"))
    try:
        r_rpt = sim_routes.download_latest_rpt(
            cluster_id="7", project_id=proj.id, db=db, tenant=_tenant(org))
        assert r_rpt.status_code == 200
        assert "LEGITIME_RPT_CONTENT" in r_rpt.body.decode("utf-8")
    finally:
        _cleanup(db, [org], [proj])


# ---------------------------------------------------------------------------
# R2 — résolution explicite du projet
# ---------------------------------------------------------------------------

def test_deux_projets_meme_org_ambiguite_refusee(db, env):
    """Deux projets actifs dans la même org, sans project_id → 409 explicite."""
    org = _org(db)
    gpkg = _creer_gpkg(env["tmp"] / "multi.gpkg")
    p1 = _projet(db, org, gpkg)
    p2 = _projet(db, org, _creer_gpkg(env["tmp"] / "multi2.gpkg"))
    try:
        for appel in (
            lambda: sim_routes.download_latest_inp(
                cluster_id="7", db=db, tenant=_tenant(org)),
            lambda: sim_routes.download_latest_rpt(
                cluster_id="7", db=db, tenant=_tenant(org)),
        ):
            with pytest.raises(HTTPException) as exc:
                appel()
            assert exc.value.status_code == 409
    finally:
        _cleanup(db, [org], [p1, p2])


def test_project_id_inexistant_ou_hors_org(db, env):
    """project_id inexistant ou appartenant à une autre org → 404 explicite."""
    orgA, orgB = _org(db), _org(db)
    gpkg = _creer_gpkg(env["tmp"] / "cross.gpkg")
    pA = _projet(db, orgA, gpkg)
    pB = _projet(db, orgB, _creer_gpkg(env["tmp"] / "cross_b.gpkg"))
    try:
        # project_id d'une autre organisation
        with pytest.raises(HTTPException) as exc:
            sim_routes.download_latest_rpt(
                project_id=pB.id, db=db, tenant=_tenant(orgA))
        assert exc.value.status_code == 404
        # project_id inexistant
        with pytest.raises(HTTPException) as exc2:
            sim_routes.download_latest_inp(
                project_id="proj_inexistant", db=db, tenant=_tenant(orgA))
        assert exc2.value.status_code == 404
    finally:
        _cleanup(db, [orgA, orgB], [pA, pB])
