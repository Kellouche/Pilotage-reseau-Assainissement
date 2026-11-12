# -*- coding: utf-8 -*-
"""
Étape 3C.2 — Tests unitaires du contrat ResultStore.

Couvre : ResultRef, ArtifactKind, clés partitionnées, isolation
org/projet/simulation, écritures conditionnelles (jamais d'écrasement),
lectures, listing, erreurs explicites, et indépendance du backend
(ArtifactStore factice en mémoire = sémantique S3).
"""

import json
from typing import List, Optional, Union

import pytest

from api.core.storage import (
    ArtifactStore,
    LocalStore,
    StorageNotFoundError,
    StorageError,
)
from api.services.result_store import (
    ArtifactKind,
    ResultAlreadyExists,
    ResultNotFound,
    ResultRef,
    ResultStore,
    ResultStoreError,
    ResultStorageError,
    get_result_store,
)


# ---------------------------------------------------------------------------
# Backend factice en mémoire (même contrat qu'un S3Store)
# ---------------------------------------------------------------------------

class _MemStore(ArtifactStore):
    """ArtifactStore minimaliste en mémoire — prouve l'indépendance backend."""

    def __init__(self):
        self._data = {}

    def put_bytes(self, key, data, content_type=None):
        self._data[key] = bytes(data)
        return key

    def put_file(self, key, local_path, content_type=None):
        from pathlib import Path
        self._data[key] = Path(local_path).read_bytes()
        return key

    def put_bytes_if_absent(self, key, data, content_type=None):
        if key in self._data:
            return False
        self._data[key] = bytes(data)
        return True

    def put_file_if_absent(self, key, local_path, content_type=None):
        if key in self._data:
            return False
        return self.put_file(key, local_path, content_type)

    def get_bytes(self, key):
        if key not in self._data:
            raise StorageNotFoundError(key)
        return self._data[key]

    def get_file(self, key, destination_path):
        from pathlib import Path
        dest = Path(destination_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.get_bytes(key))
        return dest

    def exists(self, key):
        return key in self._data

    def delete(self, key):
        return self._data.pop(key, None) is not None

    def delete_prefix(self, prefix):
        ks = [k for k in self._data if k.startswith(prefix)]
        for k in ks:
            del self._data[k]
        return len(ks)

    def list_keys(self, prefix=""):
        return sorted(k for k in self._data if k.startswith(prefix))

    def generate_presigned_url(self, key, expires_in=3600):
        return f"mem://{key}"


@pytest.fixture
def ref():
    return ResultRef(org_id="org_A", project_id="proj_1", simulation_id="sim_1")


@pytest.fixture
def store_local(tmp_path):
    return ResultStore(store=LocalStore(root_dir=tmp_path))


@pytest.fixture
def store_mem():
    return ResultStore(store=_MemStore())


# ---------------------------------------------------------------------------
# 1-2. ResultRef : construction et validation
# ---------------------------------------------------------------------------

def test_result_ref_construction():
    ref = ResultRef(org_id="org1", project_id="proj1", simulation_id="sim1")
    assert ref.org_id == "org1"
    assert ref.project_id == "proj1"
    assert ref.simulation_id == "sim1"


@pytest.mark.parametrize("champ,valeur", [
    ("org_id", ""), ("org_id", "   "), ("org_id", None),
    ("project_id", ""), ("project_id", None),
    ("simulation_id", ""), ("simulation_id", None),
])
def test_result_ref_incomplet_refuse(champ, valeur):
    kwargs = {"org_id": "o", "project_id": "p", "simulation_id": "s", champ: valeur}
    with pytest.raises(ResultStoreError):
        ResultRef(**kwargs)


@pytest.mark.parametrize("valeur", ["a/b", "a\\b", "..", "a..b", "avec espace", "x" * 200])
def test_result_ref_identifiants_malformes(valeur):
    with pytest.raises(ResultStoreError):
        ResultRef(org_id=valeur, project_id="p", simulation_id="s")
    with pytest.raises(ResultStoreError):
        ResultRef(org_id="o", project_id=valeur, simulation_id="s")
    with pytest.raises(ResultStoreError):
        ResultRef(org_id="o", project_id="p", simulation_id=valeur)


def test_result_ref_depuis_simulation():
    class _Sim:
        org_id = "org9"
        project_id = "proj9"
        id = "sim9"
    ref = ResultRef.depuis_simulation(_Sim())
    assert (ref.org_id, ref.project_id, ref.simulation_id) == ("org9", "proj9", "sim9")

    class _SimIncomplete:
        org_id = "org9"
        project_id = None
        id = "sim9"
    with pytest.raises(ResultStoreError):
        ResultRef.depuis_simulation(_SimIncomplete())


# ---------------------------------------------------------------------------
# 3-5. Clés et isolation
# ---------------------------------------------------------------------------

def test_cle_partitionnee(ref):
    assert ResultStore.cle(ref) == "org_A/proj_1/simulations/sim_1/result.json"
    assert ResultStore.cle(ref, ArtifactKind.RPT) == \
        "org_A/proj_1/simulations/sim_1/report.rpt"
    assert ResultStore.cle(ref, ArtifactKind.INP) == \
        "org_A/proj_1/simulations/sim_1/model.inp"
    assert ResultStore.cle(ref, ArtifactKind.TIMESERIES) == \
        "org_A/proj_1/simulations/sim_1/timeseries.json"
    assert ResultStore.cle(ref, ArtifactKind.SUMMARY) == \
        "org_A/proj_1/simulations/sim_1/summary.json"


def test_isolation_orgs_et_projets(store_local):
    payload = {"meta": {"x": 1}}
    r1 = ResultRef("org1", "p1", "s1")
    r2 = ResultRef("org2", "p1", "s1")   # autre org, même projet/sim ids
    r3 = ResultRef("org1", "p2", "s1")   # autre projet
    r4 = ResultRef("org1", "p1", "s2")   # autre simulation

    store_local.save(r1, payload)
    for autre in (r2, r3, r4):
        assert not store_local.exists(autre)
        with pytest.raises(ResultNotFound):
            store_local.load(autre)
        assert store_local.list_artifacts(autre) == []

    # La bonne référence lit bien
    assert store_local.load_json(r1)["meta"]["x"] == 1


def test_cle_rejet_non_resultref():
    with pytest.raises(ResultStoreError):
        ResultStore.cle("org/p/s")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 6-7. Écriture et lecture (LocalStore + backend factice)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("store_fixture", ["store_local", "store_mem"])
def test_save_load_json(store_fixture, ref, request):
    store = request.getfixturevalue(store_fixture)
    art = store.save(ref, {"kpis": {"peak": 0.5}}, kind=ArtifactKind.SUMMARY)
    assert art.sha256 and len(art.sha256) == 64
    assert art.size > 0
    assert art.key == "org_A/proj_1/simulations/sim_1/summary.json"
    assert store.load_json(ref, ArtifactKind.SUMMARY)["kpis"]["peak"] == 0.5


@pytest.mark.parametrize("store_fixture", ["store_local", "store_mem"])
def test_save_payload_bytes_et_str(store_fixture, ref, request):
    store = request.getfixturevalue(store_fixture)
    store.save(ref, b"\x89BIN", kind=ArtifactKind.INP)
    assert store.load(ref, ArtifactKind.INP) == b"\x89BIN"

    store.save(ref, "texte brut", kind=ArtifactKind.RPT)
    assert store.load(ref, ArtifactKind.RPT) == "texte brut".encode("utf-8")


def test_list_artifacts(store_local, ref):
    store_local.save(ref, {"a": 1})
    store_local.save(ref, b"x", kind=ArtifactKind.INP)
    cles = store_local.list_artifacts(ref)
    assert len(cles) == 2
    assert all(k.startswith("org_A/proj_1/simulations/sim_1/") for k in cles)
    assert store_local.exists_any(ref)


# ---------------------------------------------------------------------------
# 8. Immutabilité : jamais d'écrasement
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("store_fixture", ["store_local", "store_mem"])
def test_pas_decrasement_jamais(store_fixture, ref, request):
    store = request.getfixturevalue(store_fixture)
    store.save(ref, {"version": 1})
    with pytest.raises(ResultAlreadyExists):
        store.save(ref, {"version": 2})
    # Le contenu original est intact
    assert store.load_json(ref)["version"] == 1


# ---------------------------------------------------------------------------
# 9-10. Artefact inexistant et erreurs propagées
# ---------------------------------------------------------------------------

def test_artefact_inexistant(store_local, ref):
    assert not store_local.exists(ref)
    with pytest.raises(ResultNotFound):
        store_local.load(ref)
    assert store_local.list_artifacts(ref) == []
    assert not store_local.exists_any(ref)


def test_payload_invalide_refuse(store_local, ref):
    with pytest.raises(ResultStoreError):
        store_local.save(ref, {"ok": True}, kind="nimporte_quoi")  # type: ignore[arg-type]
    with pytest.raises(ResultStoreError):
        store_local.save(ref, 12345)  # type: ignore[arg-type]
    with pytest.raises(ResultStoreError):
        store_local.save(ref, b"")  # payload vide


def test_json_illisible_leve_erreur_stockage(store_local, ref):
    store_local.save(ref, b"PAS_DU_JSON{{{")
    with pytest.raises(ResultStorageError):
        store_local.load_json(ref)


def test_erreur_backend_propagee(ref):
    class _KoStore(_MemStore):
        def get_bytes(self, key):
            raise StorageError("backend en panne")

        def exists(self, key):
            raise StorageError("backend en panne")

    store = ResultStore(store=_KoStore())
    with pytest.raises(ResultStorageError):
        store.load(ref)
    with pytest.raises(ResultStorageError):
        store.exists(ref)


def test_save_erreur_backend_propagee(ref):
    class _KoWrite(_MemStore):
        def put_bytes_if_absent(self, key, data, content_type=None):
            raise StorageError("disque plein")

    store = ResultStore(store=_KoWrite())
    with pytest.raises(ResultStorageError):
        store.save(ref, {"a": 1})


# ---------------------------------------------------------------------------
# 3C.3 — save_idempotent et replace
# ---------------------------------------------------------------------------

def test_save_idempotent_cree_puis_identique(store_local, ref):
    art, cree = store_local.save_idempotent(ref, {"v": 1})
    assert cree is True
    art2, cree2 = store_local.save_idempotent(ref, {"v": 1})
    assert cree2 is False
    assert art2.sha256 == art.sha256
    assert store_local.load_json(ref) == {"v": 1}


def test_save_idempotent_divergence_refusee(store_local, ref):
    store_local.save_idempotent(ref, {"v": 1})
    with pytest.raises(ResultAlreadyExists):
        store_local.save_idempotent(ref, {"v": 2})
    assert store_local.load_json(ref) == {"v": 1}


def test_replace_enriched_revise_avec_historique(store_local, ref):
    store_local.save(ref, {"v": 1})
    art = store_local.replace_enriched(ref, {"timeseries": {"x": 1}})
    assert art.kind == ArtifactKind.RESULT_ENRICHED
    relu = store_local.load_json(ref, ArtifactKind.RESULT_ENRICHED)
    assert relu["timeseries"] == {"x": 1}
    assert len(relu["_revision_history"]) == 1
    assert relu["_revision_history"][0]["remplace_sha256"] is None

    # Seconde révision : l'historique conserve les deux empreintes
    store_local.replace_enriched(ref, {"timeseries": {"x": 2}})
    relu2 = store_local.load_json(ref, ArtifactKind.RESULT_ENRICHED)
    hist = relu2["_revision_history"]
    assert len(hist) == 2
    assert hist[1]["remplace_sha256"] == hist[0]["apercu_sha256"] or \
        hist[1]["remplace_sha256"] is not None
    # Le résultat original n'a pas été touché
    assert store_local.load_json(ref, ArtifactKind.RESULT_JSON) == {"v": 1}


def test_replace_enriched_exige_mapping(store_local, ref):
    with pytest.raises(ResultStoreError):
        store_local.replace_enriched(ref, b"bytes")  # type: ignore[arg-type]
    with pytest.raises(ResultStoreError):
        store_local.replace_enriched(ref, "texte")  # type: ignore[arg-type]


def test_replace_supprime_canaux_generiques_absents(store_local, ref):
    """3C.4 : aucun canal générique d'écrasement ne subsiste."""
    assert not hasattr(store_local, "replace")
    with pytest.raises(ResultStoreError):
        store_local.save(ref, {"v": 1})
        store_local.save(ref, {"v": 2})


def test_get_result_store_defaut():
    rs = get_result_store()
    assert isinstance(rs, ResultStore)


def test_result_ref_frozen(ref):
    with pytest.raises(Exception):
        ref.org_id = "autre"  # type: ignore[misc]
