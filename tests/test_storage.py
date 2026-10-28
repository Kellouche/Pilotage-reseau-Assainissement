"""
Tests unitaires pour la couche d'abstraction du stockage d'artefacts (Task 2.1).
"""

import pytest
from pathlib import Path
from api.core.storage import (
    ArtifactStore,
    LocalStore,
    StorageNotFoundError,
    get_storage,
    build_network_gpkg_key,
    build_dem_key,
    build_swmm_inp_key,
    build_simulation_result_key,
)


def test_build_key_normalization():
    key = ArtifactStore.build_key("org_123", "proj_456", "rasters/dem.tif")
    assert key == "org_123/proj_456/rasters/dem.tif"

    # Nettoyage des slashes redondants
    key2 = ArtifactStore.build_key("/org_123/", "\\proj_456\\", "/rasters/dem.tif")
    assert key2 == "org_123/proj_456/rasters/dem.tif"


def test_build_key_anti_traversal():
    with pytest.raises(ValueError, match="Traversée de répertoire interdite"):
        ArtifactStore.build_key("org_123", "proj_456", "../secrets.txt")

    with pytest.raises(ValueError, match="Traversée de répertoire interdite"):
        ArtifactStore.build_key("org_123", "proj_456", "sub/../../etc/passwd")


def test_local_store_lifecycle(tmp_path):
    store = LocalStore(root_dir=tmp_path)

    key = ArtifactStore.build_key("org_test", "proj_test", "data/test.txt")
    payload = b"Hello SWMM SaaS"

    # 1. Écriture bytes
    saved_key = store.put_bytes(key, payload)
    assert saved_key == key
    assert store.exists(key) is True

    # 2. Lecture bytes
    read_data = store.get_bytes(key)
    assert read_data == payload

    # 3. Listing
    keys = store.list_keys(prefix="org_test/proj_test")
    assert key in keys

    # 4. Téléchargement vers fichier local
    dest = tmp_path / "downloaded.txt"
    out_file = store.get_file(key, dest)
    assert out_file.exists()
    assert out_file.read_bytes() == payload

    # 5. Écriture depuis fichier
    key_uploaded = ArtifactStore.build_key("org_test", "proj_test", "uploaded.txt")
    store.put_file(key_uploaded, dest)
    assert store.exists(key_uploaded) is True
    assert store.get_bytes(key_uploaded) == payload

    # 6. Suppression unitaire
    assert store.delete(key) is True
    assert store.exists(key) is False

    # 7. Suppression avec préfixe
    deleted_count = store.delete_prefix("org_test")
    assert deleted_count >= 1
    assert store.exists(key_uploaded) is False


def test_local_store_not_found(tmp_path):
    store = LocalStore(root_dir=tmp_path)
    with pytest.raises(StorageNotFoundError):
        store.get_bytes("org_test/proj_test/inexistant.bin")


def test_helpers_and_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(tmp_path))
    store = get_storage()
    assert isinstance(store, LocalStore)
    assert store.root_dir == tmp_path.resolve()

    gpkg_key = build_network_gpkg_key("org1", "proj1")
    assert gpkg_key == "org1/proj1/gis/network.gpkg"

    dem_key = build_dem_key("org1", "proj1")
    assert dem_key == "org1/proj1/rasters/dem.tif"

    inp_key = build_swmm_inp_key("org1", "proj1")
    assert inp_key == "org1/proj1/swmm/model.inp"

    sim_key = build_simulation_result_key("org1", "proj1", "job-1", "report.rpt")
    assert sim_key == "org1/proj1/simulations/job-1/report.rpt"

    url = store.generate_presigned_url(sim_key)
    assert "/api/v1/artifacts/download?key=" in url
