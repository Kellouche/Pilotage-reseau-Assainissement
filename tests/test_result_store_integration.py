# -*- coding: utf-8 -*-
"""
Étape 3C.3 — Tests d'intégration ResultStore dans SimulationService.

Couvre : dépôt des artefacts permanents (result.json / model.inp /
report.rpt) pour une simulation synchrone, lecture préférentielle par
ResultStore, write-through des enrichissements dérivés, compatibilité
legacy, absence d'identité, collisions (identique/divergente), échec de
stockage partiel, isolation org/projet et conservation du cache de calcul.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.database import SessionLocal
from api.models import Organization, Project, Simulation
from api.services import simulation_service as svc
from api.services.result_store import (
    ArtifactKind,
    ResultAlreadyExists,
    ResultNotFound,
    ResultRef,
    ResultStore,
    ResultStoreError,
)


def _uid():
    import uuid
    return uuid.uuid4().hex[:10]


@pytest.fixture
def store_root(tmp_path, monkeypatch):
    """Backend ArtifactStore local isolé pour toute la durée du test."""
    root = tmp_path / "artifacts"
    monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(root))
    return root


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def contexte(db, tmp_path):
    """Org + projet + fichier GPKG factice + tenant."""
    sfx = _uid()
    org = Organization(id=f"org_{sfx}", name="Org", slug=f"org-{sfx}")
    db.add(org)
    db.flush()
    gpkg = tmp_path / f"reseau_{sfx}.gpkg"
    gpkg.write_bytes(b"GPF" + sfx.encode())  # contenu quelconque
    proj = Project(id=f"proj_{sfx}", org_id=org.id, name=f"Projet {sfx}",
                   source_gpkg_key=str(gpkg))
    db.add(proj)
    db.commit()
    tenant = SimpleNamespace(org_id=org.id)
    yield {"org": org, "proj": proj, "gpkg": gpkg, "tenant": tenant,
           "sfx": sfx}
    db.query(Simulation).filter(Simulation.project_id == proj.id).delete(
        synchronize_session=False)
    db.query(Project).filter(Project.id == proj.id).delete(
        synchronize_session=False)
    db.query(Organization).filter(Organization.id == org.id).delete(
        synchronize_session=False)
    db.commit()


def _resultat(valeur=1):
    return {
        "meta": {"cluster_id": 1, "cluster_nom": "B1",
                 "bbox": [3.0, 36.0, 3.1, 36.1],
                 "conduits_count": 1, "junctions_count": 2,
                 "execution_duration_sec": 0.5},
        "node_results": {"N1": {"flooded": False}},
        "conduit_results": {"C1": {"q_max": 0.1}},
        "peak_outflow_m3s": 0.456,
        "inp_content": f"[TITLE]\nINP-{valeur}",
        "rpt_content": f"RPT-{valeur}",
        "provenance": {"nature": "REAL"},
    }


def _sauvegarder(db, ctx, resultat=None, **kw):
    params = {"scenario_key": "pluie_decennale", "duree_heures": 4.0}
    params.update(kw.pop("params_dict", {}))
    return svc.sauvegarder_simulation(
        db=db, gpkg_path=ctx["gpkg"], cluster_id=1,
        param_hash=f"h_{_uid()}", params_dict=params,
        resultat=resultat if resultat is not None else _resultat(),
        proj=ctx["proj"], tenant=ctx["tenant"], **kw)


def _derniere_sim(db, ctx):
    return db.query(Simulation).filter(
        Simulation.project_id == ctx["proj"].id).order_by(
        Simulation.created_at.desc()).first()


def _store():
    return ResultStore()  # lit STORAGE_LOCAL_ROOT via get_storage()


# ---------------------------------------------------------------------------
# Dépôt des artefacts permanents
# ---------------------------------------------------------------------------

def test_simulation_sync_depose_artefacts(db, store_root, contexte):
    """Une simulation synchrone persistée expose une ResultRef complète et
    ses artefacts permanents via ResultStore."""
    cache_file = _sauvegarder(db, contexte)
    sim = _derniere_sim(db, contexte)
    assert sim is not None and sim.org_id == contexte["org"].id

    statut = (sim.summary_kpis or {}).get("result_store") or {}
    assert statut.get("complet") is True, statut
    assert statut["ref"] == {"org_id": contexte["org"].id,
                             "project_id": contexte["proj"].id,
                             "simulation_id": sim.id}
    assert set(statut["artefacts"]) == {"result.json", "model.inp", "report.rpt"}

    ref = ResultRef(org_id=sim.org_id, project_id=sim.project_id,
                    simulation_id=sim.id)
    store = _store()
    assert store.exists(ref, ArtifactKind.RESULT_JSON)
    assert store.exists(ref, ArtifactKind.INP)
    assert store.exists(ref, ArtifactKind.RPT)
    data = store.load_json(ref)
    assert data["peak_outflow_m3s"] == 0.456
    assert store.load(ref, ArtifactKind.INP) == b"[TITLE]\nINP-1"
    assert store.load(ref, ArtifactKind.RPT) == b"RPT-1"

    # Le cache de calcul reste écrit (voie de travail historique)
    assert Path(cache_file).exists()


def test_lecture_prefere_resultstore(db, store_root, contexte):
    """charger_resultat_simulation lit result.json même si le cache disque
    a disparu : ResultStore est la voie permanente."""
    cache_file = _sauvegarder(db, contexte)
    sim = _derniere_sim(db, contexte)
    Path(cache_file).unlink()  # cache de calcul supprimé

    data = svc.charger_resultat_simulation(sim)
    assert data is not None
    assert data["peak_outflow_m3s"] == 0.456


def test_restauration_contexte_resultstore(db, store_root, contexte):
    """resoudre_simulation_courante retrouve la simulation via ResultStore."""
    _sauvegarder(db, contexte)
    ctx = svc.resoudre_simulation_courante(
        db, org_id=contexte["org"].id, project_id=contexte["proj"].id,
        resoudre_gpkg=False)
    assert ctx.data is not None
    assert ctx.data["meta"]["cluster_id"] == 1


def test_write_through_enrichissement(db, store_root, contexte):
    """persister_resultat_simulation réécrit aussi result.json : la lecture
    ResultStore reflète les enrichissements dérivés (timeseries, buffer)."""
    _sauvegarder(db, contexte)
    sim = _derniere_sim(db, contexte)
    data = svc.charger_resultat_simulation(sim)
    data["timeseries"] = {"status": "SUCCESS", "peak_outflow_m3s": 0.9}
    assert svc.persister_resultat_simulation(sim, data) is True

    relu = svc.charger_resultat_simulation(sim)
    assert relu["timeseries"]["peak_outflow_m3s"] == 0.9


# ---------------------------------------------------------------------------
# Compatibilité legacy et identité incomplète
# ---------------------------------------------------------------------------

def test_compatibilite_simulation_legacy(db, store_root, contexte, tmp_path):
    """Une simulation historique (results_s3_key = chemin local, sans
    artefacts ResultStore) reste lisible par la voie legacy."""
    legacy = tmp_path / "legacy_result.json"
    payload = _resultat()
    legacy.write_text(json.dumps(payload), encoding="utf-8")
    sim = Simulation(
        id=f"sim_legacy_{_uid()}", org_id=None, project_id=contexte["proj"].id,
        name="legacy", status="completed", results_s3_key=str(legacy),
        summary_kpis={})
    db.add(sim)
    db.commit()
    try:
        data = svc.charger_resultat_simulation(sim)
        assert data is not None and data["peak_outflow_m3s"] == 0.456
        # Aucun artefact ResultStore créé pour cette ligne
        assert not _store().exists_any(
            ResultRef(contexte["org"].id, contexte["proj"].id, sim.id))
    finally:
        db.delete(sim)
        db.commit()


def test_identite_incomplete_sans_org_ni_projet(db, store_root, tmp_path):
    """Sans org_id/project_id persistés, ResultStore est sauté explicitement
    et le cache legacy continue de fonctionner."""
    gpkg = tmp_path / "solo.gpkg"
    gpkg.write_bytes(b"GPFsolo")
    resultat = _resultat()
    cache_file = svc.sauvegarder_simulation(
        db=db, gpkg_path=gpkg, cluster_id=1, param_hash=f"h_{_uid()}",
        params_dict={"scenario_key": "s"}, resultat=resultat,
        proj=None, tenant=None)
    sim = db.query(Simulation).filter(
        Simulation.project_id.is_(None)).order_by(
        Simulation.created_at.desc()).first()
    try:
        assert Path(cache_file).exists()
        statut = (sim.summary_kpis or {}).get("result_store") or {}
        assert statut.get("complet") is False
        assert "identite_incomplete" in (statut.get("erreur") or "")
        # Lecture toujours possible via le chemin local
        assert svc.charger_resultat_simulation(sim)["peak_outflow_m3s"] == 0.456
    finally:
        if sim is not None:
            db.delete(sim)
            db.commit()


# ---------------------------------------------------------------------------
# Collisions et erreurs partielles
# ---------------------------------------------------------------------------

def test_collision_identique_idempotente(db, store_root, contexte):
    """Redéposer le MÊME contenu sur la même simulation est idempotent."""
    _sauvegarder(db, contexte)
    sim = _derniere_sim(db, contexte)
    # Le contenu stocké inclut les estampilles meta (project_id/org_id) :
    # on re-dépose exactement ce qui a été persisté.
    contenu_stocke = svc.charger_resultat_simulation(sim)
    statut = svc._persister_resultats_store(sim, contenu_stocke)
    assert statut["complet"] is True
    assert all(v == "identical" for v in statut["artefacts"].values())


def test_collision_divergente_refusee(db, store_root, contexte):
    """Un contenu DIFFÉRENT sur le même artefact est refusé explicitement."""
    _sauvegarder(db, contexte)
    sim = _derniere_sim(db, contexte)
    divergent = _resultat()
    divergent["peak_outflow_m3s"] = 99.9
    divergent["inp_content"] = "[TITLE]\nAUTRE-INP"
    statut = svc._persister_resultats_store(sim, divergent)
    assert statut["complet"] is False
    assert statut["artefacts"]["result.json"].startswith("error")
    assert statut["artefacts"]["model.inp"].startswith("error")
    # Le contenu original est intact
    ref = ResultRef(sim.org_id, sim.project_id, sim.id)
    assert _store().load_json(ref)["peak_outflow_m3s"] == 0.456


def test_echec_stockage_partiel_diagnostique(db, store_root, contexte,
                                           monkeypatch):
    """Si le backend échoue sur un artefact, le statut reflète la
    persistance partielle sans annonce erronée de complétude."""
    from api.core import storage as st
    from api.services import result_store as rs

    class _StorePartiel(st.LocalStore):
        def put_bytes_if_absent(self, key, data, content_type=None):
            if key.endswith("report.rpt"):
                raise st.StorageError("panne simulée RPT")
            return super().put_bytes_if_absent(key, data, content_type)

    monkeypatch.setattr(rs, "get_storage",
                        lambda *a, **k: _StorePartiel(root_dir=store_root))

    _sauvegarder(db, contexte)
    sim = _derniere_sim(db, contexte)
    statut = (sim.summary_kpis or {}).get("result_store") or {}
    assert statut["complet"] is False
    assert statut["artefacts"]["result.json"] == "created"
    assert statut["artefacts"]["model.inp"] == "created"
    assert "error" in statut["artefacts"]["report.rpt"]

    # result.json reste lisible ; le cache legacy reste fonctionnel
    assert svc.charger_resultat_simulation(sim)["peak_outflow_m3s"] == 0.456
    assert Path(sim.results_s3_key).exists()


# ---------------------------------------------------------------------------
# Isolation multi-tenant
# ---------------------------------------------------------------------------

def test_isolation_orgs_et_projets_resultstore(db, store_root, tmp_path):
    """Les artefacts d'une simulation d'un autre org/projet sont
    strictement inaccessibles via ResultStore."""
    ctx_a = {"org": None, "proj": None}
    ctxs = []
    for i in range(2):
        sfx = _uid()
        org = Organization(id=f"org_{sfx}", name="O", slug=f"o-{sfx}")
        db.add(org)
        db.flush()
        gpkg = tmp_path / f"r{i}_{sfx}.gpkg"
        gpkg.write_bytes(b"GPF")
        proj = Project(id=f"proj_{sfx}", org_id=org.id, name=f"P{sfx}",
                       source_gpkg_key=str(gpkg))
        db.add(proj)
        ctxs.append({"org": org, "proj": proj, "gpkg": gpkg,
                     "tenant": SimpleNamespace(org_id=org.id)})
    db.commit()
    try:
        for c in ctxs:
            _sauvegarder(db, c, resultat=_resultat(valeur=len(ctxs)))
        sim_a = _derniere_sim(db, ctxs[0])
        sim_b = _derniere_sim(db, ctxs[1])
        store = _store()
        ref_a = ResultRef(sim_a.org_id, sim_a.project_id, sim_a.id)
        ref_b = ResultRef(sim_b.org_id, sim_b.project_id, sim_b.id)
        assert ref_a.org_id != ref_b.org_id
        assert store.cle(ref_a) != store.cle(ref_b)
        # La référence de B ne lit pas les artefacts de A
        assert store.load_json(ref_a)["peak_outflow_m3s"] == 0.456
        with pytest.raises(ResultNotFound):
            store.load_json(ResultRef(ref_b.org_id, ref_b.project_id,
                                      sim_a.id))
        with pytest.raises(ResultNotFound):
            store.load_json(ResultRef(ref_a.org_id, ref_b.project_id,
                                      sim_a.id))
    finally:
        for c in ctxs:
            db.query(Simulation).filter(
                Simulation.project_id == c["proj"].id).delete(
                synchronize_session=False)
            db.query(Project).filter(Project.id == c["proj"].id).delete(
                synchronize_session=False)
            db.query(Organization).filter(
                Organization.id == c["org"].id).delete(synchronize_session=False)
        db.commit()
