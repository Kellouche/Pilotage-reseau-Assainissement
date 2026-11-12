# -*- coding: utf-8 -*-
"""
Tests de l'étape 3B — versionnement immuable des GeoPackage.

Couvre : validation GPKG, empreinte SHA-256, déduplication, deux versions
d'un projet, deux projets au même contenu, remplacement sans perte,
matérialisation atomique, indisponibilité, cohérence tenant,
persistance Simulation, import concurrent, compatibilité legacy.
"""

import json
import sqlite3
import threading
import uuid
from pathlib import Path

import pytest

from api.database import SessionLocal
from api.models import Organization, Project, GpkgVersion, Simulation
from api.services import gpkg_versions as gv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return uuid.uuid4().hex[:10]


def _creer_gpkg(path: Path, nb_regards: int = 2, nb_cana: int = 2,
                marqueur: str = "") -> Path:
    """Crée un GeoPackage minimal valide (couches regards + canalisations)."""
    import geopandas as gpd
    from shapely.geometry import Point, LineString
    path = Path(path)
    gdf_r = gpd.GeoDataFrame(
        {"id": [f"N{i}{marqueur}" for i in range(nb_regards)]},
        geometry=[Point(3.0 + i * 0.001, 36.0) for i in range(nb_regards)],
        crs="EPSG:4326",
    )
    gdf_c = gpd.GeoDataFrame(
        {"id": [f"C{i}" for i in range(nb_cana)]},
        geometry=[LineString([(3.0, 36.0), (3.001, 36.001)]) for _ in range(nb_cana)],
        crs="EPSG:4326",
    )
    gdf_r.to_file(path, layer="regards", driver="GPKG")
    gdf_c.to_file(path, layer="canalisations", driver="GPKG", mode="a")
    return path


@pytest.fixture
def env_versions(tmp_path, monkeypatch):
    """Store local + cache de matérialisation isolés dans tmp_path."""
    monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setattr(gv, "GPKG_CACHE_DIR", tmp_path / "gpkg_cache")
    return tmp_path


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def projet_avec_gpkg(db, tmp_path):
    """Organisation + projet + GPKG v1 sur disque."""
    sfx = _uid()
    org = Organization(id=f"org_{sfx}", name="Org V", slug=f"org-v-{sfx}")
    db.add(org)
    db.flush()
    gpkg = _creer_gpkg(tmp_path / f"reseau_{sfx}.gpkg", marqueur=sfx)
    proj = Project(id=f"proj_{sfx}", org_id=org.id, name=f"Projet V {sfx}",
                   source_gpkg_key=str(gpkg))
    db.add(proj)
    db.commit()
    yield {"org": org, "proj": proj, "gpkg": gpkg, "sfx": sfx}
    # nettoyage
    db.query(GpkgVersion).filter(GpkgVersion.project_id == proj.id).delete(synchronize_session=False)
    db.query(Simulation).filter(Simulation.project_id == proj.id).delete(synchronize_session=False)
    db.query(Project).filter(Project.id == proj.id).delete(synchronize_session=False)
    db.query(Organization).filter(Organization.id == org.id).delete(synchronize_session=False)
    db.commit()


# ---------------------------------------------------------------------------
# Validation GPKG
# ---------------------------------------------------------------------------

def test_validation_gpkg_invalide_fichier_texte(tmp_path):
    f = tmp_path / "faux.gpkg"
    f.write_text("ceci n'est pas un gpkg")
    with pytest.raises(gv.GpkgInvalide):
        gv.valider_gpkg(f)


def test_validation_gpkg_sans_couches_requises(tmp_path):
    """SQLite valide + gpkg_contents mais sans couche 'regard' → invalide."""
    import geopandas as gpd
    from shapely.geometry import Point
    f = tmp_path / "incomplet.gpkg"
    gpd.GeoDataFrame({"x": [1]}, geometry=[Point(0, 0)], crs="EPSG:4326").to_file(
        f, layer="parcelles", driver="GPKG")
    with pytest.raises(gv.GpkgInvalide) as ei:
        gv.valider_gpkg(f)
    assert any("regard" in r or "canalisat" in r for r in ei.value.raisons)


def test_validation_gpkg_rejets_optionnel(tmp_path):
    """Un GPKG sans couche rejets reste valide (comportement moteur réel)."""
    f = _creer_gpkg(tmp_path / "sans_rejets.gpkg")
    meta = gv.valider_gpkg(f)
    assert meta["nb_regards"] == 2 and meta["nb_conduites"] == 2
    assert meta["couche_rejets"] is None


def test_sha256_stable_et_sensible(tmp_path):
    f = _creer_gpkg(tmp_path / "a.gpkg")
    sha1 = gv.sha256_fichier(f)
    assert len(sha1) == 64
    # un octet modifié → empreinte différente
    with open(f, "r+b") as fh:
        fh.seek(100)
        fh.write(b"X")
    assert gv.sha256_fichier(f) != sha1


# ---------------------------------------------------------------------------
# Enregistrement & déduplication
# ---------------------------------------------------------------------------

def test_enregistrer_version_cree_et_dedup(db, projet_avec_gpkg, env_versions):
    p = projet_avec_gpkg["proj"]
    v1 = gv.enregistrer_version_gpkg(db, p, projet_avec_gpkg["gpkg"], valider=False)
    db.commit()
    assert v1.sha256 and v1.storage_kind == "ARTIFACT_STORE"
    assert v1.project_id == p.id and v1.org_id == p.org_id
    assert p.gpkg_version_id == v1.id

    # Réimport identique → même version, aucun doublon
    v2 = gv.enregistrer_version_gpkg(db, p, projet_avec_gpkg["gpkg"], valider=False)
    db.commit()
    assert v2.id == v1.id
    assert db.query(GpkgVersion).filter(GpkgVersion.project_id == p.id).count() == 1


def test_deux_versions_remplacement_sans_perte(db, projet_avec_gpkg, env_versions, tmp_path):
    p = projet_avec_gpkg["proj"]
    v1 = gv.enregistrer_version_gpkg(db, p, projet_avec_gpkg["gpkg"], valider=False)
    db.commit()

    # v2 : contenu différent (regard supplémentaire)
    gpkg2 = _creer_gpkg(tmp_path / f"v2_{projet_avec_gpkg['sfx']}.gpkg",
                        nb_regards=3, marqueur=projet_avec_gpkg["sfx"])
    v2 = gv.enregistrer_version_gpkg(db, p, gpkg2, valider=False)
    db.commit()

    assert v2.id != v1.id and v2.sha256 != v1.sha256
    assert p.gpkg_version_id == v2.id  # pointeur courant déplacé
    # v1 toujours présente et lisible
    assert db.get(GpkgVersion, v1.id) is not None
    assert gv.version_disponible(v1)[0] is True


def test_deux_projets_meme_contenu(db, tmp_path, env_versions):
    """Même GPKG pour deux projets → même sha256, deux lignes distinctes."""
    sfx = _uid()
    org = Organization(id=f"org_{sfx}", name="O", slug=f"o-{sfx}")
    db.add(org)
    db.flush()
    gpkg = _creer_gpkg(tmp_path / f"partage_{sfx}.gpkg", marqueur=sfx)
    pa = Project(id=f"pa_{sfx}", org_id=org.id, name="PA", source_gpkg_key=str(gpkg))
    pb = Project(id=f"pb_{sfx}", org_id=org.id, name="PB", source_gpkg_key=str(gpkg))
    db.add_all([pa, pb])
    db.commit()
    try:
        va = gv.enregistrer_version_gpkg(db, pa, gpkg, valider=False)
        vb = gv.enregistrer_version_gpkg(db, pb, gpkg, valider=False)
        db.commit()
        assert va.sha256 == vb.sha256
        assert va.id != vb.id
        assert va.project_id != vb.project_id
    finally:
        db.query(GpkgVersion).filter(GpkgVersion.project_id.in_([pa.id, pb.id])).delete(synchronize_session=False)
        db.query(Project).filter(Project.id.in_([pa.id, pb.id])).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.id == org.id).delete(synchronize_session=False)
        db.commit()


# ---------------------------------------------------------------------------
# Matérialisation atomique & disponibilité
# ---------------------------------------------------------------------------

def test_materialisation_et_verification_sha(db, projet_avec_gpkg, env_versions):
    p = projet_avec_gpkg["proj"]
    v = gv.enregistrer_version_gpkg(db, p, projet_avec_gpkg["gpkg"], valider=True)
    db.commit()

    chemin = gv.materialiser_version(v)
    assert chemin.exists()
    assert chemin.name == f"{v.sha256}.gpkg"
    assert gv.sha256_fichier(chemin) == v.sha256
    # la source n'est pas modifiée
    assert gv.sha256_fichier(projet_avec_gpkg["gpkg"]) == v.sha256


def test_materialisation_reecrit_cache_altere(db, projet_avec_gpkg, env_versions):
    p = projet_avec_gpkg["proj"]
    v = gv.enregistrer_version_gpkg(db, p, projet_avec_gpkg["gpkg"], valider=False)
    db.commit()
    chemin = gv.materialiser_version(v)
    # altérer le cache
    with open(chemin, "r+b") as fh:
        fh.seek(200)
        fh.write(b"Z")
    # re-matérialisation → détecte l'altération et régénère
    chemin2 = gv.materialiser_version(v)
    assert gv.sha256_fichier(chemin2) == v.sha256


def test_version_indisponible_objet_supprime(db, projet_avec_gpkg, env_versions):
    p = projet_avec_gpkg["proj"]
    v = gv.enregistrer_version_gpkg(db, p, projet_avec_gpkg["gpkg"], valider=False)
    db.commit()
    # supprimer l'objet du store
    store = gv._store()
    assert store.exists(v.storage_ref)
    store.delete(v.storage_ref)
    ok, _ = gv.version_disponible(v)
    assert ok is False


def test_resoudre_version_interdite_cross_tenant(db, projet_avec_gpkg, tmp_path, env_versions):
    """Un projet ne peut pas utiliser la version d'un autre projet (garde applicative)."""
    p = projet_avec_gpkg["proj"]
    v = gv.enregistrer_version_gpkg(db, p, projet_avec_gpkg["gpkg"], valider=False)
    db.commit()

    # Second projet SANS version, dont on force gpkg_version_id = version de P
    sfx = _uid()
    org = Organization(id=f"org_{sfx}", name="O2", slug=f"o2-{sfx}")
    db.add(org)
    db.flush()
    autre = Project(id=f"autre_{sfx}", org_id=org.id, name="Autre",
                    source_gpkg_key=str(projet_avec_gpkg["gpkg"]))
    db.add(autre)
    db.commit()
    autre = db.get(Project, autre.id)
    autre.gpkg_version_id = v.id  # écriture directe (contournement applicatif)
    db.commit()
    try:
        chemin, meta = gv.resoudre_version_pour_simulation(db, autre)
        assert chemin is None
        assert "incohérente" in meta.get("erreur", "")
    finally:
        db.query(Project).filter(Project.id == autre.id).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.id == org.id).delete(synchronize_session=False)
        db.commit()


# ---------------------------------------------------------------------------
# Résolution pour simulation : versionnée vs legacy, remplacement pendant run
# ---------------------------------------------------------------------------

def test_resoudre_version_pour_simulation_versionnee(db, projet_avec_gpkg, env_versions):
    p = projet_avec_gpkg["proj"]
    v = gv.enregistrer_version_gpkg(db, p, projet_avec_gpkg["gpkg"], valider=False)
    db.commit()

    chemin, meta = gv.resoudre_version_pour_simulation(db, p)
    assert chemin is not None
    assert meta["version_id"] == v.id
    assert meta["sha256"] == v.sha256
    assert chemin.name == f"{v.sha256}.gpkg"


def test_snapshot_utilise_meme_si_source_remplacee(db, projet_avec_gpkg, env_versions, tmp_path):
    """
    Preuve : une fois la version enregistrée, remplacer le fichier source
    ne change PAS ce que la simulation reçoit — le snapshot est figé.
    """
    p = projet_avec_gpkg["proj"]
    v = gv.enregistrer_version_gpkg(db, p, projet_avec_gpkg["gpkg"], valider=False)
    db.commit()
    sha_v1 = v.sha256

    # Remplacer le fichier source par un contenu DIFFÉRENT (sans réimport)
    _creer_gpkg(projet_avec_gpkg["gpkg"], nb_regards=5, marqueur="REMPLACE")

    chemin, meta = gv.resoudre_version_pour_simulation(db, p)
    assert meta["sha256"] == sha_v1  # la version capturée, pas le fichier courant
    assert gv.sha256_fichier(chemin) == sha_v1


def test_resoudre_legacy_sans_version(db, tmp_path, env_versions):
    """Projet sans version → source_gpkg_key + empreinte calculée à la volée."""
    sfx = _uid()
    org = Organization(id=f"org_{sfx}", name="O3", slug=f"o3-{sfx}")
    db.add(org)
    db.flush()
    gpkg = _creer_gpkg(tmp_path / f"legacy_{sfx}.gpkg")
    proj = Project(id=f"leg_{sfx}", org_id=org.id, name="Legacy",
                   source_gpkg_key=str(gpkg))
    db.add(proj)
    db.commit()
    try:
        chemin, meta = gv.resoudre_version_pour_simulation(db, proj)
        assert chemin == gpkg
        assert meta["version_id"] is None
        assert meta["sha256"] == gv.sha256_fichier(gpkg)
        assert meta["storage_kind"] == "LEGACY"
    finally:
        db.query(Project).filter(Project.id == proj.id).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.id == org.id).delete(synchronize_session=False)
        db.commit()


# ---------------------------------------------------------------------------
# Persistance Simulation
# ---------------------------------------------------------------------------

def test_sauvegarder_simulation_enregistre_version(db, projet_avec_gpkg, env_versions, tmp_path):
    from api.services import simulation_service as svc
    from types import SimpleNamespace

    p = projet_avec_gpkg["proj"]
    v = gv.enregistrer_version_gpkg(db, p, projet_avec_gpkg["gpkg"], valider=False)
    db.commit()

    gpkg_sim = tmp_path / "sim_src.gpkg"
    _creer_gpkg(gpkg_sim, marqueur="sim")
    resultat = {"meta": {"bbox": [3.0, 36.0, 3.1, 36.1], "conduits_count": 1,
                         "junctions_count": 2, "execution_duration_sec": 1.0},
                "node_results": {}, "conduit_results": {}, "inp_content": "x",
                "provenance": {"nature": "REAL"}}
    payload = SimpleNamespace(scenario_key="pluie_decennale", duree_heures=4.0,
                              cluster_id="exutoire:1")
    _, params = svc.generer_cle_cache_simulation(gpkg_sim, payload)

    svc.sauvegarder_simulation(
        db=db, gpkg_path=gpkg_sim, cluster_id="exutoire:1",
        param_hash="hash_test", params_dict=params, resultat=resultat,
        proj=p, version_meta={"version_id": v.id, "sha256": v.sha256,
                              "storage_kind": "ARTIFACT_STORE"},
        bassin_ref="exutoire:1", exutoire_noeud="1",
    )
    sim = db.query(Simulation).filter(Simulation.project_id == p.id).order_by(
        Simulation.created_at.desc()).first()
    assert sim is not None
    assert sim.gpkg_version_id == v.id
    assert sim.gpkg_sha256 == v.sha256
    assert sim.bassin_ref == "exutoire:1"
    assert sim.exutoire_noeud == "1"
    assert sim.project_id == p.id  # version_id jamais sans project_id


def test_sauvegarder_simulation_sans_projet_ignore_version(db, env_versions, tmp_path):
    """Garde : gpkg_version_id n'est JAMAIS persisté sans project_id."""
    from api.services import simulation_service as svc
    from types import SimpleNamespace

    gpkg_sim = tmp_path / "sim_src2.gpkg"
    _creer_gpkg(gpkg_sim)
    resultat = {"meta": {"bbox": [3.0, 36.0, 3.1, 36.1], "conduits_count": 1,
                         "junctions_count": 2},
                "node_results": {}, "conduit_results": {}, "inp_content": "x"}
    payload = SimpleNamespace(scenario_key="s", duree_heures=4.0, cluster_id=1)
    _, params = svc.generer_cle_cache_simulation(gpkg_sim, payload)
    svc.sauvegarder_simulation(
        db=db, gpkg_path=gpkg_sim, cluster_id=1, param_hash="h2",
        params_dict=params, resultat=resultat, proj=None,
        version_meta={"version_id": "fake_version", "sha256": "a" * 64},
    )
    sim = db.query(Simulation).filter(Simulation.project_id.is_(None)).order_by(
        Simulation.created_at.desc()).first()
    if sim is not None and sim.gpkg_sha256 == "a" * 64:
        assert sim.gpkg_version_id is None  # jamais de version sans projet


# ---------------------------------------------------------------------------
# Cohérence exutoire ↔ version
# ---------------------------------------------------------------------------

def test_exutoire_present_dans_gpkg(db, projet_avec_gpkg, env_versions):
    p = projet_avec_gpkg["proj"]
    sfx = projet_avec_gpkg["sfx"]
    v = gv.enregistrer_version_gpkg(db, p, projet_avec_gpkg["gpkg"], valider=False)
    db.commit()
    chemin = gv.materialiser_version(v)
    # les ids de regards sont N0<sfx>, N1<sfx>
    assert gv.exutoire_present_dans_gpkg(chemin, f"N0{sfx}") is True
    assert gv.exutoire_present_dans_gpkg(chemin, "INEXISTANT_123") is False
    assert gv.exutoire_present_dans_gpkg(chemin, None) is None


# ---------------------------------------------------------------------------
# Import concurrent (multi-thread, file SQLite)
# ---------------------------------------------------------------------------

def test_import_concurrent_meme_fichier(db, projet_avec_gpkg, env_versions):
    """Deux imports simultanés du même contenu → une seule version."""
    p = projet_avec_gpkg["proj"]
    gpkg = projet_avec_gpkg["gpkg"]
    resultats = []
    erreurs = []

    def _import():
        s = SessionLocal()
        try:
            proj = s.get(Project, p.id)
            v = gv.enregistrer_version_gpkg(s, proj, gpkg, valider=False)
            s.commit()
            resultats.append(v.id)
        except Exception as e:
            erreurs.append(e)
            s.rollback()
        finally:
            s.close()

    threads = [threading.Thread(target=_import) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert not erreurs, f"Erreurs import concurrent : {erreurs}"
    assert len(set(resultats)) == 1  # tous ont convergé vers la même version
    db.expire_all()
    assert db.query(GpkgVersion).filter(
        GpkgVersion.project_id == p.id).count() == 1
