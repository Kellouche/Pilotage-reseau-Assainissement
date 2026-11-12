# -*- coding: utf-8 -*-
"""
Étape 3C.4 — Tests intégrité, manifeste, immuabilité et reprise.

Critère d'acceptation bloquant : des enrichissements successifs ne doivent
modifier d'AUCUN octet result.json / model.inp / report.rpt.
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
    ResultRef,
    ResultStore,
    ResultStoreError,
    ResultIntegrityError,
    ResultNotFound,
)


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
def contexte(db, tmp_path):
    sfx = _uid()
    org = Organization(id=f"org_{sfx}", name="Org", slug=f"org-{sfx}")
    db.add(org)
    db.flush()
    gpkg = tmp_path / f"reseau_{sfx}.gpkg"
    gpkg.write_bytes(b"GPF" + sfx.encode())
    proj = Project(id=f"proj_{sfx}", org_id=org.id, name=f"Projet {sfx}",
                   source_gpkg_key=str(gpkg))
    db.add(proj)
    db.commit()
    yield {"org": org, "proj": proj, "gpkg": gpkg,
           "tenant": SimpleNamespace(org_id=org.id), "sfx": sfx}
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


def _sauvegarder(db, ctx, resultat=None):
    return svc.sauvegarder_simulation(
        db=db, gpkg_path=ctx["gpkg"], cluster_id=1,
        param_hash=f"h_{_uid()}",
        params_dict={"scenario_key": "pluie_decennale", "duree_heures": 4.0},
        resultat=resultat if resultat is not None else _resultat(),
        proj=ctx["proj"], tenant=ctx["tenant"])


def _derniere_sim(db, ctx):
    return db.query(Simulation).filter(
        Simulation.project_id == ctx["proj"].id).order_by(
        Simulation.created_at.desc()).first()


def _ref(sim):
    return ResultRef(org_id=sim.org_id, project_id=sim.project_id,
                     simulation_id=sim.id)


def _store():
    return ResultStore()


# ---------------------------------------------------------------------------
# Manifeste et états métier
# ---------------------------------------------------------------------------

def test_manifeste_depose_et_complet(db, store_root, contexte):
    _sauvegarder(db, contexte)
    sim = _derniere_sim(db, contexte)
    store = _store()
    manifeste = store.load_json(_ref(sim), ArtifactKind.MANIFEST)
    assert manifeste["execution"] == "EXECUTED"
    assert manifeste["etat"] == "PERSISTED"
    for nom in ("result.json", "model.inp", "report.rpt"):
        entree = manifeste["artefacts"][nom]
        assert len(entree["sha256"]) == 64
    assert "simulation_manifest.json" not in manifeste["artefacts"]
    # Vérification → VERIFIED
    v = store.verifier_manifeste(_ref(sim))
    assert v["etat"] == "VERIFIED"
    # Diagnostic métier : persistance complète
    diag = svc.diagnostiquer_resultats_store(sim)
    assert diag["execution"] == "EXECUTED"
    assert diag["manifeste"] == "VERIFIED"
    assert diag["persistance_complete"] is True


def test_verify_detecte_artefact_altère(db, store_root, contexte):
    """Un artefact modifié hors ResultStore est détecté par verify()."""
    _sauvegarder(db, contexte)
    sim = _derniere_sim(db, contexte)
    ref = _ref(sim)
    store = _store()
    v_ok = store.verify(ref, ArtifactKind.INP)
    assert v_ok["present"] and v_ok["intègre"]

    # Altération directe du fichier physique
    key = v_ok["key"]
    chemin = store_root / key
    assert chemin.exists()
    chemin.write_bytes(b"CONTENU_ALTERE")

    v_ko = store.verify(ref, ArtifactKind.INP, v_ok["sha256"])
    assert v_ko["present"] is True
    assert v_ko["intègre"] is False
    assert v_ko["sha256"] != v_ok["sha256"]
    with pytest.raises(ResultIntegrityError):
        store.load_verified(ref, ArtifactKind.INP, v_ok["sha256"])
    # Le manifeste constate la dégradation
    assert store.verifier_manifeste(ref)["etat"] == "DEGRADED"
    assert svc.diagnostiquer_resultats_store(sim)["persistance_complete"] is False


def test_verify_absent_et_load_verified(db, store_root, contexte):
    _sauvegarder(db, contexte)
    sim = _derniere_sim(db, contexte)
    ref = _ref(sim)
    store = _store()
    v = store.verify(ref, ArtifactKind.TIMESERIES)  # jamais déposé
    assert v["present"] is False and v["intègre"] is False
    with pytest.raises(ResultNotFound):
        store.load_verified(ref, ArtifactKind.TIMESERIES, "0" * 64)


# ---------------------------------------------------------------------------
# CRITÈRE BLOQUANT : enrichissements sans altérer les originaux
# ---------------------------------------------------------------------------

def _empreintes_originaux(store, ref):
    return {
        "result.json": store.verify(ref, ArtifactKind.RESULT_JSON)["sha256"],
        "model.inp": store.verify(ref, ArtifactKind.INP)["sha256"],
        "report.rpt": store.verify(ref, ArtifactKind.RPT)["sha256"],
    }


def test_enrichissements_successifs_originaux_intacts(db, store_root, contexte):
    """CRITÈRE D'ACCEPTATION : N enrichissements → originaux inchangés."""
    _sauvegarder(db, contexte)
    sim = _derniere_sim(db, contexte)
    ref = _ref(sim)
    store = _store()
    avant = _empreintes_originaux(store, ref)

    # 3 enrichissements successifs via le canal métier
    for i in range(3):
        data = svc.charger_resultat_simulation(sim)
        data["timeseries"] = {"status": "SUCCESS", "peak_outflow_m3s": 0.1 + i}
        data["buffer_sensitivity"] = {"active_buffer_m": 35 + i}
        svc.persister_resultat_simulation(sim, data)

    apres = _empreintes_originaux(store, ref)
    assert apres == avant, "Les artefacts originaux ont été altérés !"

    # L'enrichi existe, avec historique de révisions
    enrichi = store.load_json(ref, ArtifactKind.RESULT_ENRICHED)
    assert enrichi["timeseries"]["peak_outflow_m3s"] == 2.1
    assert enrichi["buffer_sensitivity"]["active_buffer_m"] == 37
    assert len(enrichi["_revision_history"]) == 3

    # La lecture fusionne : timeseries dérivée visible, hydraulique intact
    relu = svc.charger_resultat_simulation(sim)
    assert relu["timeseries"]["peak_outflow_m3s"] == 2.1
    assert relu["peak_outflow_m3s"] == 0.456  # original hydraulique


def test_fusion_ne_ecrase_jamais_hydraulique(db, store_root, contexte):
    """Un enrichi contenant des champs hydrauliques ne les applique pas."""
    _sauvegarder(db, contexte)
    sim = _derniere_sim(db, contexte)
    ref = _ref(sim)
    store = _store()
    # Injection hostile : l'enrichi tente de modifier le pic moteur
    store.replace_enriched(ref, {
        "peak_outflow_m3s": 999.0,
        "node_results": {"N1": {"flooded": True}},
        "timeseries": {"status": "SUCCESS", "peak_outflow_m3s": 0.7},
    })
    relu = svc.charger_resultat_simulation(sim)
    assert relu["peak_outflow_m3s"] == 0.456       # original préservé
    assert relu["node_results"]["N1"]["flooded"] is False
    assert relu["timeseries"]["peak_outflow_m3s"] == 0.7  # dérivé appliqué


def test_replace_enriched_refuse_types_etrangers():
    """replace_enriched ne peut cibler que RESULT_ENRICHED — aucun paramètre
    kind n'existe : la signature elle-même est la barrière."""
    store = _store()
    ref = ResultRef("o", "p", "s")
    with pytest.raises(TypeError):
        store.replace_enriched(ref, {"x": 1}, kind=ArtifactKind.RESULT_JSON)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Persistance partielle et reprise
# ---------------------------------------------------------------------------

def test_persistance_partielle_manifeste_partiel(db, store_root, contexte,
                                                 monkeypatch):
    """RPT en échec → manifeste PARTIAL, diagnostic explicite."""
    from api.core import storage as st
    from api.services import result_store as rs

    class _StorePartiel(st.LocalStore):
        def put_bytes_if_absent(self, key, data, content_type=None):
            if key.endswith("report.rpt"):
                raise st.StorageError("panne RPT")
            return super().put_bytes_if_absent(key, data, content_type)

    monkeypatch.setattr(rs, "get_storage",
                        lambda *a, **k: _StorePartiel(root_dir=store_root))
    _sauvegarder(db, contexte)
    sim = _derniere_sim(db, contexte)
    store = _store()
    manifeste = store.load_json(_ref(sim), ArtifactKind.MANIFEST)
    assert manifeste["etat"] == "PARTIAL"
    assert "report.rpt" in manifeste["manquants"]
    diag = svc.diagnostiquer_resultats_store(sim)
    assert diag["manifeste"] == "PARTIAL"
    assert diag["persistance_complete"] is False


def test_reprise_apres_perte_artefact(db, store_root, contexte):
    """Un artefact perdu est reconstitué par reprise_resultat_simulation
    SANS relancer le moteur ; le manifeste repasse PERSISTED."""
    _sauvegarder(db, contexte)
    sim = _derniere_sim(db, contexte)
    ref = _ref(sim)
    store = _store()

    # Perte simulée du RPT
    cle_rpt = store.cle(ref, ArtifactKind.RPT)
    (store_root / cle_rpt).unlink()
    assert store.verifier_manifeste(ref)["etat"] == "DEGRADED"

    # Reprise à partir des données disponibles (cache/ORM)
    resultat = svc.charger_resultat_simulation(sim)
    statut = svc.reprise_resultat_simulation(sim, resultat)
    assert statut["artefacts"]["report.rpt"] == "created"
    assert statut["artefacts"]["result.json"] == "identical"
    assert statut["manifeste"] == "PERSISTED"
    assert statut["persistance_complete"] is True
    assert store.verifier_manifeste(ref)["etat"] == "VERIFIED"


def test_reprise_divergence_jamais_ecrasee(db, store_root, contexte):
    """Un artefact divergent n'est JAMAIS écrasé par la reprise."""
    _sauvegarder(db, contexte)
    sim = _derniere_sim(db, contexte)
    ref = _ref(sim)
    store = _store()

    # Altération : on remplace le RPT par un contenu étranger
    cle_rpt = store.cle(ref, ArtifactKind.RPT)
    (store_root / cle_rpt).write_bytes(b"RPT_ETRANGER")

    resultat = _resultat()
    statut = svc.reprise_resultat_simulation(sim, resultat)
    assert statut["artefacts"]["report.rpt"] == "error:divergence"
    assert "divergence:report.rpt" in statut["anomalies"]
    assert statut["persistance_complete"] is False
    # Le contenu étranger est toujours là — pas d'écrasement silencieux
    assert store.load(ref, ArtifactKind.RPT) == b"RPT_ETRANGER"


def test_reprise_identite_incomplete(db, store_root, tmp_path):
    """Sans identité complète, la reprise échoue explicitement."""
    sim = SimpleNamespace(id="sim_x", org_id=None, project_id=None)
    statut = svc.reprise_resultat_simulation(sim, {"a": 1})
    assert statut["erreur"] == "identite_incomplete"
    assert statut["persistance_complete"] is False
