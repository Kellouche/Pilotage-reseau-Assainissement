# -*- coding: utf-8 -*-
"""
Étape 3D.1 — Résolution contextuelle des simulations.

Couvre l'isolation stricte org_id/project_id du service
`resoudre_simulation_courante` :
- jamais de sélection arbitraire de projet (ambiguïté → erreur explicite) ;
- simulation_id explicite vérifié contre org/projet ;
- « dernière simulation » déterministe et bornée au projet ;
- filtres de bassin (cluster_id / bassin_ref / exutoire_noeud) ;
- chargement du résultat via chemin local ET clé ArtifactStore (Celery) ;
- rattachement du snapshot GPKG exact (3C.0).
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from api.database import SessionLocal
from api.models import Organization, Project, GpkgVersion, Simulation
from api.services import gpkg_versions as gv
from api.services import simulation_service as svc


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def _creer_gpkg(path: Path, marqueur: str = "") -> Path:
    import geopandas as gpd
    from shapely.geometry import Point, LineString
    path = Path(path)
    gpd.GeoDataFrame(
        {"id": [f"N{i}{marqueur}" for i in range(2)]},
        geometry=[Point(3.0 + i * 0.001, 36.0) for i in range(2)],
        crs="EPSG:4326",
    ).to_file(path, layer="regards", driver="GPKG")
    gpd.GeoDataFrame(
        {"id": ["C1"]},
        geometry=[LineString([(3.0, 36.0), (3.001, 36.001)])],
        crs="EPSG:4326",
    ).to_file(path, layer="canalisations", driver="GPKG", mode="a")
    return path


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setattr(gv, "GPKG_CACHE_DIR", tmp_path / "gpkg_cache")
    return tmp_path


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


def _org(db, sfx=None):
    sfx = sfx or _uid()
    org = Organization(id=f"org_{sfx}", name="Org", slug=f"org-{sfx}")
    db.add(org)
    db.flush()
    return org


def _projet(db, org, sfx=None, gpkg=True, tmp=None):
    sfx = sfx or _uid()
    chemin = None
    if gpkg and tmp is not None:
        chemin = str(_creer_gpkg(tmp / f"reseau_{sfx}.gpkg", marqueur=sfx))
    proj = Project(id=f"proj_{sfx}", org_id=org.id, name=f"Projet {sfx}",
                   source_gpkg_key=chemin)
    db.add(proj)
    db.commit()
    return proj


def _data_sim(version_id=None, sha=None, cluster_id=1, bass_nom="B1"):
    d = {
        "node_results": {"N1": {"hgl": 1.0}},
        "conduit_results": {"C1": {"q": 0.1}},
        "meta": {"cluster_id": cluster_id, "cluster_nom": bass_nom,
                 "bbox": [3.0, 36.0, 3.1, 36.1]},
    }
    prov = {}
    if version_id is not None:
        prov["gpkg_version_id"] = version_id
    if sha is not None:
        prov["gpkg_sha256"] = sha
    if prov:
        d["provenance"] = prov
    return d


def _sim(db, org, proj, data, tmp, nom_suffix="", cluster_id=1,
         created_at=None, status="completed", key_mode="local",
         bassin_ref=None, exutoire=None):
    """Crée une ligne Simulation + résultat (fichier local ou clé store)."""
    sim_id = str(uuid.uuid4())
    if key_mode == "local":
        fjson = Path(tmp) / f"sim_{sim_id}.json"
        fjson.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        key = str(fjson.resolve())
    else:  # clé ArtifactStore (style Celery)
        key = f"{org.id}/{proj.id}/jobs/{sim_id}/summary.json"
        from api.core.storage import get_storage
        get_storage().put_bytes(key, json.dumps(data).encode("utf-8"),
                                content_type="application/json")
    sim = Simulation(
        id=sim_id, org_id=org.id, project_id=proj.id,
        name=f"SWMM_{proj.name}_{cluster_id}_{nom_suffix}",
        status=status,
        scenario_pluie="pluie_decennale", duree_heures=4.0,
        results_s3_key=key,
        gpkg_version_id=(data.get("provenance") or {}).get("gpkg_version_id"),
        gpkg_sha256=(data.get("provenance") or {}).get("gpkg_sha256"),
        bassin_ref=bassin_ref, exutoire_noeud=exutoire,
        summary_kpis={"cluster_id": cluster_id, "parameters": {}},
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(sim)
    db.commit()
    return sim


def _nettoyer(db, orgs, projs, sims):
    pids = [p.id for p in projs]
    for s in sims:
        db.delete(s)
    for p in projs:
        db.delete(p)
    if pids:
        db.query(GpkgVersion).filter(GpkgVersion.project_id.in_(pids)).delete(
            synchronize_session=False)
    for o in orgs:
        db.delete(o)
    db.commit()


# ---------------------------------------------------------------------------
# Isolation organisation / projet
# ---------------------------------------------------------------------------

def test_isolation_inter_org(db, env):
    """La sim de l'org A n'est JAMAIS résoluble pour l'org B."""
    orgA, orgB = _org(db), _org(db)
    pA = _projet(db, orgA, tmp=env)
    pB = _projet(db, orgB, tmp=env)
    sA = _sim(db, orgA, pA, _data_sim(), env, nom_suffix="A")
    sB = _sim(db, orgB, pB, _data_sim(), env, nom_suffix="B")
    try:
        # Contexte B → sim B uniquement
        ctxB = svc.resoudre_simulation_courante(db, org_id=orgB.id, resoudre_gpkg=False)
        assert ctxB.simulation.id == sB.id
        assert ctxB.data["meta"]["cluster_nom"] == "B1"

        # simulation_id de A demandé dans le contexte B → introuvable
        with pytest.raises(svc.ContexteSimulationIntrouvable):
            svc.resoudre_simulation_courante(
                db, org_id=orgB.id, project_id=pB.id,
                simulation_id=sA.id, resoudre_gpkg=False)

        # project_id de A avec org_id B → introuvable
        with pytest.raises(svc.ContexteSimulationIntrouvable):
            svc.resoudre_simulation_courante(
                db, org_id=orgB.id, project_id=pA.id, resoudre_gpkg=False)
    finally:
        _nettoyer(db, [orgA, orgB], [pA, pB], [sA, sB])


def test_ambiguite_projet_meme_org(db, env):
    """Deux projets actifs dans la même org sans project_id → erreur explicite."""
    org = _org(db)
    p1 = _projet(db, org, tmp=env)
    p2 = _projet(db, org, tmp=env)
    s1 = _sim(db, org, p1, _data_sim(), env, nom_suffix="P1")
    try:
        with pytest.raises(svc.ProjetAmbigu):
            svc.resoudre_simulation_courante(db, org_id=org.id, resoudre_gpkg=False)
        # Avec project_id explicite → la bonne sim
        ctx = svc.resoudre_simulation_courante(
            db, org_id=org.id, project_id=p1.id, resoudre_gpkg=False)
        assert ctx.simulation.id == s1.id
        assert ctx.resolution == "derniere"
    finally:
        _nettoyer(db, [org], [p1, p2], [s1])


def test_projet_unique_resolu_sans_ambiguite(db, env):
    """Un seul projet actif dans l'org → résolution implicite non ambiguë."""
    org = _org(db)
    p = _projet(db, org, tmp=env)
    s = _sim(db, org, p, _data_sim(), env)
    try:
        ctx = svc.resoudre_simulation_courante(db, org_id=org.id, resoudre_gpkg=False)
        assert ctx.simulation.id == s.id
        assert ctx.project.id == p.id
    finally:
        _nettoyer(db, [org], [p], [s])


def test_sans_aucun_projet_introuvable(db, env):
    org = _org(db)
    try:
        with pytest.raises(svc.ContexteSimulationIntrouvable):
            svc.resoudre_simulation_courante(db, org_id=org.id, resoudre_gpkg=False)
    finally:
        _nettoyer(db, [org], [], [])


# ---------------------------------------------------------------------------
# Choix déterministe et filtres de bassin
# ---------------------------------------------------------------------------

def test_derniere_simulation_ordre_deterministe(db, env):
    """La plus récente par created_at (puis id) est choisie — jamais .first()."""
    org = _org(db)
    p = _projet(db, org, tmp=env)
    now = datetime.now(timezone.utc)
    s_old = _sim(db, org, p, _data_sim(cluster_id=1), env, nom_suffix="old",
                 created_at=now - timedelta(hours=2))
    s_new = _sim(db, org, p, _data_sim(cluster_id=2), env, nom_suffix="new",
                 created_at=now)
    try:
        ctx = svc.resoudre_simulation_courante(db, org_id=org.id, resoudre_gpkg=False)
        assert ctx.simulation.id == s_new.id
        assert ctx.data["meta"]["cluster_id"] == 2
        # Et la plus ancienne reste accessible par simulation_id explicite
        ctx_old = svc.resoudre_simulation_courante(
            db, org_id=org.id, project_id=p.id, simulation_id=s_old.id,
            resoudre_gpkg=False)
        assert ctx_old.simulation.id == s_old.id
        assert ctx_old.resolution == "simulation_id"
    finally:
        _nettoyer(db, [org], [p], [s_old, s_new])


def test_filtres_bassin(db, env):
    """cluster_id / bassin_ref / exutoire_noeud sélectionnent la bonne sim."""
    org = _org(db)
    p = _projet(db, org, tmp=env)
    s_b1 = _sim(db, org, p, _data_sim(cluster_id=1), env, nom_suffix="b1",
                cluster_id=1, bassin_ref="exutoire:100", exutoire="100")
    s_b2 = _sim(db, org, p, _data_sim(cluster_id=2), env, nom_suffix="b2",
                cluster_id=2, bassin_ref="exutoire:200", exutoire="200")
    try:
        ctx = svc.resoudre_simulation_courante(
            db, org_id=org.id, cluster_id=2, resoudre_gpkg=False)
        assert ctx.simulation.id == s_b2.id and ctx.resolution == "bassin"

        ctx = svc.resoudre_simulation_courante(
            db, org_id=org.id, bassin_ref="exutoire:100", resoudre_gpkg=False)
        assert ctx.simulation.id == s_b1.id

        ctx = svc.resoudre_simulation_courante(
            db, org_id=org.id, exutoire_noeud="200", resoudre_gpkg=False)
        assert ctx.simulation.id == s_b2.id

        # Bassin inexistant → introuvable, pas de repli sur une autre sim
        with pytest.raises(svc.ContexteSimulationIntrouvable):
            svc.resoudre_simulation_courante(
                db, org_id=org.id, cluster_id=999, resoudre_gpkg=False)
    finally:
        _nettoyer(db, [org], [p], [s_b1, s_b2])


# ---------------------------------------------------------------------------
# Chargement du résultat : chemin local vs clé ArtifactStore (Celery)
# ---------------------------------------------------------------------------

def test_chargement_chemin_local_et_cle_store(db, env):
    """results_s3_key local (sync) et clé store (Celery) sont tous deux lus."""
    org = _org(db)
    p = _projet(db, org, tmp=env)
    s_local = _sim(db, org, p, _data_sim(cluster_id=1), env,
                   nom_suffix="loc", key_mode="local")
    s_store = _sim(db, org, p, _data_sim(cluster_id=2), env,
                   nom_suffix="celery", key_mode="store")
    try:
        # Direct : les deux modes de clé produisent le bon JSON
        d_local = svc.charger_resultat_simulation(s_local)
        d_store = svc.charger_resultat_simulation(s_store)
        assert d_local["meta"]["cluster_id"] == 1
        assert d_store["meta"]["cluster_id"] == 2
        # Et le service les résout tous les deux
        ctx = svc.resoudre_simulation_courante(
            db, org_id=org.id, project_id=p.id, simulation_id=s_store.id,
            resoudre_gpkg=False)
        assert ctx.data["meta"]["cluster_id"] == 2
    finally:
        _nettoyer(db, [org], [p], [s_local, s_store])


# ---------------------------------------------------------------------------
# Snapshot GPKG rattaché (3C.0) + rejet des données invalides
# ---------------------------------------------------------------------------

def test_snapshot_gpkg_rattache(db, env):
    """resoudre_gpkg=True → ctx.gpkg_path = snapshot de la version de la sim."""
    org = _org(db)
    proj = _projet(db, org, tmp=env)
    v = gv.enregistrer_version_gpkg(db, proj, Path(proj.source_gpkg_key), valider=False)
    db.commit()
    data = _data_sim(version_id=v.id, sha=v.sha256)
    s = _sim(db, org, proj, data, env)
    try:
        ctx = svc.resoudre_simulation_courante(db, org_id=org.id, resoudre_gpkg=True)
        assert ctx.gpkg_path is not None and ctx.gpkg_path.exists()
        assert gv.sha256_fichier(ctx.gpkg_path) == v.sha256
        assert ctx.meta_version.get("resolution") == "gpkg_version_id"
    finally:
        _nettoyer(db, [org], [proj], [s])


def test_donnees_invalides_ignorees(db, env):
    """Une sim sans node_results/conduit_results n'est jamais servie."""
    org = _org(db)
    p = _projet(db, org, tmp=env)
    mauvais = {"meta": {"cluster_id": 1, "bbox": [3.0, 36.0, 3.1, 36.1]}}
    s_bad = _sim(db, org, p, mauvais, env, nom_suffix="bad")
    s_ok = _sim(db, org, p, _data_sim(), env, nom_suffix="ok")
    try:
        ctx = svc.resoudre_simulation_courante(db, org_id=org.id, resoudre_gpkg=False)
        assert ctx.simulation.id == s_ok.id
        # La mauvaise seule → introuvable
        s_ok.status = "failed"
        db.commit()
        with pytest.raises(svc.ContexteSimulationIntrouvable):
            svc.resoudre_simulation_courante(db, org_id=org.id, resoudre_gpkg=False)
    finally:
        _nettoyer(db, [org], [p], [s_bad, s_ok])
