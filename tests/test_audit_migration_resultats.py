# -*- coding: utf-8 -*-
"""
Étape 3C.5 — Tests de l'audit de migration des résultats historiques.

Vérifie : classification A–G, types sync/celery, détection des identités
incomplètes, références introuvables, corruptions, ambiguïtés, provenance,
clés partagées — et SURTOUT l'absence totale d'écriture (dry-run).
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.core.storage import LocalStore
from api.database import SessionLocal
from api.models import Organization, Project, Simulation
from api.services import audit_migration_resultats as audit
from api.services.result_store import ResultStoreError


def _uid():
    import uuid
    return uuid.uuid4().hex[:10]


@pytest.fixture
def store_root(tmp_path, monkeypatch):
    root = tmp_path / "artifacts"
    monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(root))
    return root


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def env(db, tmp_path, store_root):
    sfx = _uid()
    org = Organization(id=f"org_{sfx}", name="O", slug=f"o-{sfx}")
    db.add(org)
    db.flush()
    gpkg = tmp_path / f"r_{sfx}.gpkg"
    gpkg.write_bytes(b"GPF")
    proj = Project(id=f"proj_{sfx}", org_id=org.id, name=f"P{sfx}",
                   source_gpkg_key=str(gpkg))
    db.add(proj)
    db.commit()
    yield {"org": org, "proj": proj, "sfx": sfx}
    db.query(Simulation).filter(Simulation.project_id == proj.id).delete(
        synchronize_session=False)
    db.query(Project).filter(Project.id == proj.id).delete(
        synchronize_session=False)
    db.query(Organization).filter(Organization.id == org.id).delete(
        synchronize_session=False)
    db.commit()


def _result_json(proj, org, **surcharge):
    d = {
        "meta": {"cluster_id": 1, "bbox": [3.0, 36.0, 3.1, 36.1],
                 "conduits_count": 1, "junctions_count": 2,
                 "project_id": proj.id, "org_id": org.id},
        "node_results": {"N1": {}},
        "conduit_results": {"C1": {}},
        "peak_outflow_m3s": 0.4,
        "inp_content": "[TITLE] x",
        "rpt_content": "RPT",
        "provenance": {"nature": "REAL"},
    }
    d.update(surcharge)
    return d


_MANQUANT = object()


def _sim(db, env, data=None, org=_MANQUANT, projet=_MANQUANT, cle=None, **kw):
    sim = Simulation(
        id=kw.pop("id", f"sim_{_uid()}"),
        org_id=env["org"].id if org is _MANQUANT else org,
        project_id=env["proj"].id if projet is _MANQUANT else projet,
        name="s", status="completed",
        results_s3_key=cle, summary_kpis={}, **kw)
    db.add(sim)
    db.commit()
    return sim


def _fichier_resultat(tmp_path, data):
    f = tmp_path / f"res_{_uid()}.json"
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return f


def _audit_une(db, sim):
    store = audit._StoreLectureSeule(LocalStore(root_dir=Path("x")))
    projets = {str(env_proj.id): env_proj for env_proj in
               db.query(Project).all()}
    orgs = {str(o.id): o for o in db.query(Organization).all()}
    return audit.auditer_simulation(sim, db, store, projets, orgs)


# ---------------------------------------------------------------------------
# Classes A et B — sync complet / partiel
# ---------------------------------------------------------------------------

def test_classe_A_sync_complet(db, env, tmp_path):
    data = _result_json(env["proj"], env["org"])
    f = _fichier_resultat(tmp_path, data)
    sim = _sim(db, env, cle=str(f))
    r = _audit_une(db, sim)
    assert r["classe"] == "A"
    assert r["decision"] == "migration_automatique"
    assert r["type_execution"] == "sync"
    assert r["ref_candidate"]["simulation_id"] == sim.id
    assert r["artefacts"]["result_source"]["sha256"]
    assert r["artefacts"]["model.inp"]["present"]
    assert r["artefacts"]["report.rpt"]["present"]


def test_classe_B_partiel_sans_inp_rpt(db, env, tmp_path):
    data = _result_json(env["proj"], env["org"])
    del data["inp_content"]
    del data["rpt_content"]
    f = _fichier_resultat(tmp_path, data)
    sim = _sim(db, env, cle=str(f))
    r = _audit_une(db, sim)
    assert r["classe"] == "B"
    assert r["decision"] == "validation_humaine"
    assert "model.inp" in r["artefacts"]["manquants"]


# ---------------------------------------------------------------------------
# Classes C à G
# ---------------------------------------------------------------------------

def test_classe_C_identite_incomplete(db, env, tmp_path):
    data = _result_json(env["proj"], env["org"])
    f = _fichier_resultat(tmp_path, data)
    sim = _sim(db, env, cle=str(f), org=None)
    r = _audit_une(db, sim)
    assert r["classe"] == "C"
    assert r["decision"] == "non_migrable_identite"
    assert r["ref_candidate"] is None


def test_classe_C_projet_absent(db, env, tmp_path):
    data = _result_json(env["proj"], env["org"])
    f = _fichier_resultat(tmp_path, data)
    sim = _sim(db, env, cle=str(f), projet="proj_inexistant")
    r = _audit_une(db, sim)
    assert r["classe"] == "C"
    assert "reference_fk_absente" in r["motifs"]


def test_classe_D_reference_introuvable(db, env):
    sim = _sim(db, env, cle=str(Path("Z:/inexistant/res.json")))
    r = _audit_une(db, sim)
    assert r["classe"] == "D"
    assert r["decision"] == "non_migrable_reference"


def test_classe_E_json_corrompu(db, env, tmp_path):
    f = tmp_path / "casse.json"
    f.write_text("{ ceci n'est pas du json", encoding="utf-8")
    sim = _sim(db, env, cle=str(f))
    r = _audit_une(db, sim)
    assert r["classe"] == "E"
    assert r["decision"] == "non_migrable_corrompu"


def test_classe_E_resultat_invalide(db, env, tmp_path):
    f = _fichier_resultat(tmp_path, {"meta": {}, "node_results": {},
                                     "conduit_results": {},
                                     "provenance": {"nature": "REAL"}})
    sim = _sim(db, env, cle=str(f))
    r = _audit_une(db, sim)
    assert r["classe"] == "E"
    assert "resultat_invalide" in r["motifs"]


def test_classe_F_estampille_contradictoire(db, env, tmp_path):
    autre = Project(id=f"proj_autre_{_uid()}", org_id=env["org"].id,
                    name="autre", source_gpkg_key="x")
    db.add(autre)
    db.commit()
    try:
        data = _result_json(env["proj"], env["org"])
        data["meta"]["project_id"] = autre.id  # estampille étrangère
        f = _fichier_resultat(tmp_path, data)
        sim = _sim(db, env, cle=str(f))
        r = _audit_une(db, sim)
        assert r["classe"] == "F"
        assert r["decision"] == "validation_humaine"
    finally:
        db.delete(autre)
        db.commit()


def test_classe_G_provenance_synthetique(db, env, tmp_path):
    data = _result_json(env["proj"], env["org"],
                        provenance={"nature": "SYNTHETIC"})
    f = _fichier_resultat(tmp_path, data)
    sim = _sim(db, env, cle=str(f))
    r = _audit_une(db, sim)
    assert r["classe"] == "G"
    assert r["decision"] == "exclu_provenance"


def test_classe_G_sans_provenance(db, env, tmp_path):
    data = _result_json(env["proj"], env["org"])
    del data["provenance"]
    f = _fichier_resultat(tmp_path, data)
    sim = _sim(db, env, cle=str(f))
    r = _audit_une(db, sim)
    assert r["classe"] == "G"


# ---------------------------------------------------------------------------
# Type Celery
# ---------------------------------------------------------------------------

def test_celery_summary_avec_provenance_reelle(db, env, store_root):
    store = LocalStore(root_dir=store_root)
    org_id, proj_id, job = env["org"].id, env["proj"].id, f"job_{_uid()}"
    base = f"{org_id}/{proj_id}/simulations/{job}"
    kpis = {"peak_outflow_m3s": 0.4, "provenance": {"nature": "REAL"}}
    store.put_bytes(f"{base}/summary.json",
                    json.dumps(kpis).encode(), content_type="application/json")
    store.put_bytes(f"{base}/report.rpt", b"RPT CELERY")
    store.put_bytes(f"{org_id}/{proj_id}/swmm/model_{job}.inp", b"[TITLE] c")
    sim = _sim(db, env, id=job, cle=f"{base}/summary.json")

    store_ro = audit._StoreLectureSeule(LocalStore(root_dir=store_root))
    projets = {str(p.id): p for p in db.query(Project).all()}
    orgs = {str(o.id): o for o in db.query(Organization).all()}
    r = audit.auditer_simulation(sim, db, store_ro, projets, orgs)
    assert r["type_execution"] == "celery"
    assert r["classe"] == "A"  # tous les artefacts attendus présents
    assert r["decision"] == "migration_automatique"


def test_celery_artefact_manquant_partiel(db, env, store_root):
    store = LocalStore(root_dir=store_root)
    org_id, proj_id, job = env["org"].id, env["proj"].id, f"job_{_uid()}"
    base = f"{org_id}/{proj_id}/simulations/{job}"
    store.put_bytes(f"{base}/summary.json",
                    json.dumps({"peak": 1, "provenance": {"nature": "REAL"}})
                    .encode())
    # report.rpt et model.inp absents
    sim = _sim(db, env, id=job, cle=f"{base}/summary.json")
    store_ro = audit._StoreLectureSeule(LocalStore(root_dir=store_root))
    projets = {str(p.id): p for p in db.query(Project).all()}
    orgs = {str(o.id): o for o in db.query(Organization).all()}
    r = audit.auditer_simulation(sim, db, store_ro, projets, orgs)
    assert r["classe"] == "B"
    assert "report.rpt" in r["artefacts"]["manquants"]


# ---------------------------------------------------------------------------
# Inventaire global, collisions, lecture seule
# ---------------------------------------------------------------------------

def test_auditer_base_resume_et_cles_partagees(db, env, tmp_path):
    data = _result_json(env["proj"], env["org"])
    f1 = _fichier_resultat(tmp_path, data)
    f2 = _fichier_resultat(tmp_path, data)
    ids = [_sim(db, env, cle=str(f1)).id,
           _sim(db, env, cle=str(f1)).id,
           _sim(db, env, cle=str(f2)).id,
           _sim(db, env, cle=str(tmp_path / "absent.json")).id]

    rapport = audit.auditer_base(db)
    assert rapport["total_simulations"] >= 4
    assert sum(rapport["par_classe"].values()) == rapport["total_simulations"]
    partagees = rapport["cles_resultats_partagees"]
    assert str(f1) in partagees and len(partagees[str(f1)]) == 2
    # Les 3 premières sont A (fichier valide), la 4e est D
    miens = [s for s in rapport["simulations"] if s["simulation_id"] in ids]
    classes = sorted(s["classe"] for s in miens)
    assert classes == ["A", "A", "A", "D"]


def test_store_lecture_seule_refuse_ecriture(store_root):
    store = audit._StoreLectureSeule(LocalStore(root_dir=store_root))
    with pytest.raises(audit.StoreWriteForbidden):
        store.put_bytes("a/b/c.txt", b"x")
    with pytest.raises(audit.StoreWriteForbidden):
        store.put_bytes_if_absent("a/b/c.txt", b"x")
    with pytest.raises(audit.StoreWriteForbidden):
        store.delete("a/b/c.txt")
    # Les lectures restent possibles
    assert store.exists("a/b/c.txt") is False


def test_audit_ne_modifie_aucune_donnee(db, env, tmp_path):
    """Le dry-run ne change ni le fichier ni la ligne Simulation."""
    data = _result_json(env["proj"], env["org"])
    f = _fichier_resultat(tmp_path, data)
    avant = f.read_bytes()
    sim = _sim(db, env, cle=str(f))
    kpis_avant = dict(sim.summary_kpis or {})

    audit.auditer_base(db)

    assert f.read_bytes() == avant
    db.refresh(sim)
    assert dict(sim.summary_kpis or {}) == kpis_avant
