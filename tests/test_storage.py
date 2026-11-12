"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Tests unitaires du gestionnaire de stockage des artefacts
================================================================================
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


def test_local_store_resolve_prefixe_etendu_windows():
    """
    Régression audit 3B : sous Windows, Path.resolve() peut retourner la forme
    étendue '\\\\?\\<lecteur>:\\…' de façon non déterministe (notamment quand la
    cible existe déjà). Sans normalisation, le contrôle anti-traversée rejetait
    des clés légitimes de façon intermittente en contexte concurrent.
    """
    norm = LocalStore._normaliser_prefixe_etendu
    assert norm("\\\\?\\D:\\data\\artifacts\\org\\f.gpkg") == "D:\\data\\artifacts\\org\\f.gpkg"
    assert norm("D:\\data\\artifacts\\org\\f.gpkg") == "D:\\data\\artifacts\\org\\f.gpkg"
    assert norm("/data/artifacts/org/f.gpkg") == "/data/artifacts/org/f.gpkg"


def test_local_store_put_if_absent_necrase_jamais(tmp_path):
    """Création conditionnelle : un objet existant n'est jamais écrasé."""
    store = LocalStore(root_dir=tmp_path)
    key = ArtifactStore.build_key("org_t", "proj_t", "gis/versions/" + "b" * 64 + "/network.gpkg")

    src1 = tmp_path / "v1.bin"
    src1.write_bytes(b"contenu-v1")
    assert store.put_file_if_absent(key, src1) is True

    src2 = tmp_path / "v2.bin"
    src2.write_bytes(b"contenu-v2-different")
    assert store.put_file_if_absent(key, src2) is False
    assert store.get_bytes(key) == b"contenu-v1"  # jamais écrasé

    # Idem pour put_bytes_if_absent
    key2 = ArtifactStore.build_key("org_t", "proj_t", "data/bin.dat")
    assert store.put_bytes_if_absent(key2, b"alpha") is True
    assert store.put_bytes_if_absent(key2, b"beta") is False
    assert store.get_bytes(key2) == b"alpha"


def test_local_store_put_if_absent_course_concurrente(tmp_path):
    """
    Course multi-thread sur la même clé : exactement un créateur gagne,
    le contenu final est toujours celui du gagnant (os.link atomique).
    """
    import threading
    store = LocalStore(root_dir=tmp_path)
    key = ArtifactStore.build_key("org_t", "proj_t", "gis/versions/" + "c" * 64 + "/network.gpkg")

    srcs = []
    for i in range(4):
        p = tmp_path / f"src{i}.bin"
        p.write_bytes(f"contenu-{i}".encode())
        srcs.append(p)

    resultats = []
    verrou = threading.Lock()

    def worker(i):
        ok = store.put_file_if_absent(key, srcs[i])
        with verrou:
            resultats.append((i, ok))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    gagnants = [i for i, ok in resultats if ok]
    assert len(gagnants) == 1, f"Exactement un créateur attendu, obtenu {gagnants}"
    assert store.get_bytes(key) == f"contenu-{gagnants[0]}".encode()


def test_local_store_resolve_cible_existante_repetable(tmp_path):
    """_resolve/exists/get_bytes doivent être stables sur une cible existante."""
    store = LocalStore(root_dir=tmp_path)
    key = "org/p/gis/versions/" + "a" * 64 + "/network.gpkg"
    payload = Path(__file__).read_bytes()
    store.put_file(key, Path(__file__))
    for _ in range(3):
        assert store.exists(key) is True
        assert store.get_bytes(key) == payload
        assert store._resolve(key).is_file()


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
