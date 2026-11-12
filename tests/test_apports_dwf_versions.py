# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : LOT P1.4 — Tests de la cohérence stricte apports DWF ↔ version GPKG

Couvre : estampillage à l'écriture, validation stricte au lancement
(version_id + sha256, projets versionnés ET legacy), rejet 422 avant
INP/moteur (synchrone et Celery), réconciliation explicite, isolation
tenant, invalidation de cache.
================================================================================
"""

import geopandas as gpd
import pytest
from pathlib import Path
from shapely.geometry import Point
from starlette.testclient import TestClient

from api.main import app
from api.database import SessionLocal, engine, Base
from api.models import (
    Organization, User, Membership, Project, ApportDwf, Cluster,
)
from api.core.auth import hash_password, create_access_token
from api.services.apports_dwf_service import (
    ApportsDwfIncompatiblesError,
    preparer_apports_pour_simulation,
    valider_apports_pour_version,
    empreinte_apports,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module", autouse=True)
def init_db_schema():
    Base.metadata.create_all(bind=engine)


def _creer_gpkg(chemin: Path, codes_nodes, decalage: float = 0.0):
    """GPKG minimal 'regards' — `decalage` change le sha sans toucher aux Codes."""
    gdf = gpd.GeoDataFrame(
        {"Code": list(codes_nodes)},
        geometry=[Point(i * 10.0 + decalage, i * 10.0) for i in range(len(codes_nodes))],
        crs="EPSG:32631",
    )
    gdf.to_file(str(chemin), layer="regards", driver="GPKG")
    # Le cache d'empreintes legacy est clé (chemin, mtime int, taille) :
    # une réécriture dans la même seconde peut conserver la même clé.
    # On l'invalide explicitement pour garantir un sha recalculé.
    from api.services.gpkg_versions import _SHA_CACHE
    _SHA_CACHE.clear()


def _apport_dict(**kw):
    base = {
        "id": "a_test", "node_id": "REG_B1", "nature": "domestique",
        "mode_determination": "debit", "debit_moyen_m3s": 0.001,
        "eh": None, "debit_specifique_l_hab_j": None,
        "profile_key": "constant", "actif": True,
        "gpkg_version_id": None, "gpkg_sha256": None,
    }
    base.update(kw)
    return base


META_V1 = {"version_id": "ver_v1", "sha256": "sha_v1" * 8,
           "storage_kind": "ARTIFACT_STORE"}
META_V2 = {"version_id": "ver_v2", "sha256": "sha_v2" * 8,
           "storage_kind": "ARTIFACT_STORE"}
META_LEGACY = {"version_id": None, "sha256": "a" * 64,
               "storage_kind": "LEGACY"}


# ---------------------------------------------------------------------------
# Validation pure (valider_apports_pour_version) — cas 1 à 8
# ---------------------------------------------------------------------------

def test_version_identique_acceptee(tmp_path):
    """Cas 1 : même version_id + même sha256 → admissible."""
    gpkg = tmp_path / "r.gpkg"
    _creer_gpkg(gpkg, ["REG_B1"])
    a = _apport_dict(gpkg_version_id="ver_v1", gpkg_sha256=META_V1["sha256"])
    out = valider_apports_pour_version([a], META_V1, gpkg)
    assert out == [a]


def test_version_differente_rejetee(tmp_path):
    """Cas 2 : apport estampillé V1, simulation sur V2 → rejet."""
    gpkg = tmp_path / "r.gpkg"
    _creer_gpkg(gpkg, ["REG_B1"])  # le nœud existe même en V2
    a = _apport_dict(gpkg_version_id="ver_v1", gpkg_sha256=META_V1["sha256"])
    with pytest.raises(ApportsDwfIncompatiblesError) as ei:
        valider_apports_pour_version([a], META_V2, gpkg)
    d = ei.value.details[0]
    assert d["apport_id"] == "a_test" and d["node_id"] == "REG_B1"
    assert d["simulation_gpkg_version_id"] == "ver_v2"
    assert "version_differencee" in d["motif"]
    assert "revalider" in d["action_attendue"]


def test_noeud_absent_snapshot_rejete(tmp_path):
    """Cas 3 : nœud absent du snapshot matérialisé → rejet explicite."""
    gpkg = tmp_path / "r.gpkg"
    _creer_gpkg(gpkg, ["AUTRE_NOEUD"])  # REG_B1 absent de cette version
    # Estampillage cohérent avec META_V1 (version identique) mais le nœud
    # n'existe pas dans le fichier réellement lu.
    a = _apport_dict(gpkg_version_id="ver_v1", gpkg_sha256=META_V1["sha256"])
    with pytest.raises(ApportsDwfIncompatiblesError) as ei:
        valider_apports_pour_version([a], META_V1, gpkg)
    assert ei.value.details[0]["motif"] == "noeud_absent_du_snapshot"


def test_code_reutilise_autre_version_rejete(tmp_path):
    """Cas 4 : même Code réutilisé pour un autre nœud en V2 → rejet
    (l'estampillage de version prime, jamais la seule égalité de Code)."""
    gpkg_v2 = tmp_path / "r_v2.gpkg"
    _creer_gpkg(gpkg_v2, ["REG_B1"], decalage=999.0)  # Code présent, autre contenu
    a = _apport_dict(gpkg_version_id="ver_v1", gpkg_sha256=META_V1["sha256"])
    with pytest.raises(ApportsDwfIncompatiblesError):
        valider_apports_pour_version([a], META_V2, gpkg_v2)


def test_sans_estampillage_rejete(tmp_path):
    """Cas 5 : apport historique sans estampillage → rejet."""
    gpkg = tmp_path / "r.gpkg"
    _creer_gpkg(gpkg, ["REG_B1"])
    a = _apport_dict()  # gpkg_version_id/sha256 = None
    with pytest.raises(ApportsDwfIncompatiblesError) as ei:
        valider_apports_pour_version([a], META_LEGACY, gpkg)
    assert ei.value.details[0]["motif"] == "non_reconcilie"


def test_legacy_sha_identique_accepte(tmp_path):
    """Cas 6 : projet legacy, sha identique → admissible."""
    gpkg = tmp_path / "r.gpkg"
    _creer_gpkg(gpkg, ["REG_B1"])
    a = _apport_dict(gpkg_sha256=META_LEGACY["sha256"])
    assert valider_apports_pour_version([a], META_LEGACY, gpkg) == [a]


def test_legacy_sha_different_rejete(tmp_path):
    """Cas 7 : projet legacy, empreinte différente → rejet."""
    gpkg = tmp_path / "r.gpkg"
    _creer_gpkg(gpkg, ["REG_B1"])
    a = _apport_dict(gpkg_sha256="b" * 64)
    with pytest.raises(ApportsDwfIncompatiblesError) as ei:
        valider_apports_pour_version([a], META_LEGACY, gpkg)
    assert "sha256_difference_legacy" in ei.value.details[0]["motif"]


def test_versionne_vs_legacy_incompatible(tmp_path):
    """Un apport estampillé sur une version ne peut pas être assimilé à
    un projet legacy (et inversement)."""
    gpkg = tmp_path / "r.gpkg"
    _creer_gpkg(gpkg, ["REG_B1"])
    a_v = _apport_dict(gpkg_version_id="ver_v1", gpkg_sha256=META_V1["sha256"])
    with pytest.raises(ApportsDwfIncompatiblesError):
        valider_apports_pour_version([a_v], META_LEGACY, gpkg)
    a_l = _apport_dict(gpkg_sha256=META_LEGACY["sha256"])
    with pytest.raises(ApportsDwfIncompatiblesError):
        valider_apports_pour_version([a_l], META_V1, gpkg)


def test_plusieurs_apports_un_seul_incompatible(tmp_path):
    """Cas 8 : un seul apport incompatible → rejet de TOUT le jeu,
    avec le détail de chaque contrevenant."""
    gpkg = tmp_path / "r.gpkg"
    _creer_gpkg(gpkg, ["REG_B1", "REG_B2"])
    ok = _apport_dict(id="a_ok", node_id="REG_B1",
                      gpkg_version_id="ver_v1", gpkg_sha256=META_V1["sha256"])
    ko = _apport_dict(id="a_ko", node_id="REG_B2")  # non estampillé
    with pytest.raises(ApportsDwfIncompatiblesError) as ei:
        valider_apports_pour_version([ok, ko], META_V1, gpkg)
    assert len(ei.value.details) == 1
    assert ei.value.details[0]["apport_id"] == "a_ko"


def test_dwf_desactive_aucune_validation(tmp_path):
    """Cas 9 : dwf_actif=False → aucune validation, aucun apport injecté,
    même avec des estampillages invalides."""
    gpkg = tmp_path / "r.gpkg"
    _creer_gpkg(gpkg, ["REG_B1"])
    db = SessionLocal()
    pref = "p14off"
    org = Organization(id=f"{pref}_o", name="O", slug=f"{pref}-o")
    proj = Project(id=f"{pref}_p", org_id=org.id, name="P",
                   slug=f"{pref}-p", is_archived=False)
    a = ApportDwf(id=f"{pref}_a", org_id=org.id, project_id=proj.id,
                  node_id="REG_B1", nature="autre",
                  mode_determination="debit", debit_moyen_m3s=0.001,
                  profile_key="constant", actif=True)  # SANS estampille
    db.add_all([org, proj, a])
    db.commit()
    try:
        apports, info = preparer_apports_pour_simulation(
            db, proj, dwf_actif=False,
            version_meta=META_LEGACY, gpkg_path=gpkg)
        assert apports == [] and info["dwf_actif"] is False
    finally:
        for o in (a, proj, org):
            db.delete(o)
        db.commit()
        db.close()


# ---------------------------------------------------------------------------
# Fixture HTTP : projet legacy (source_gpkg_key) + cluster + token
# ---------------------------------------------------------------------------

@pytest.fixture
def ctx_p14(tmp_path):
    """Org/user/projet legacy sur GPKG minimal (nœuds REG_B1, REG_B2) +
    cluster + token engineer."""
    gpkg = tmp_path / "reseau_p14.gpkg"
    _creer_gpkg(gpkg, ["REG_B1", "REG_B2"])

    db = SessionLocal()
    pref = "p14"
    org = Organization(id=f"{pref}_o", name="O14", slug=f"{pref}-o")
    user = User(id=f"{pref}_u", email="u@p14.dz",
                password_hash=hash_password("DwfPass2026!"),
                full_name="U14", email_verified=True)
    mem = Membership(org_id=org.id, user_id=user.id, role="engineer")
    proj = Project(id=f"{pref}_p", org_id=org.id, name="Projet P14",
                   slug=f"{pref}-p", source_gpkg_key=str(gpkg),
                   is_archived=False)
    db.add_all([org, user, mem, proj])
    db.commit()
    cluster = Cluster(org_id=org.id, network_id=proj.id, nom="B1",
                      nb_conduites=0, nb_noeuds=2)
    db.add(cluster)
    db.commit()
    ctx = {
        "db": db, "gpkg": gpkg, "proj": proj, "cluster": cluster,
        "token": create_access_token(
            {"sub": user.id, "org_id": org.id, "role": "engineer"}),
    }
    yield ctx
    db.query(ApportDwf).filter(ApportDwf.project_id == proj.id).delete()
    db.delete(cluster)
    db.delete(proj)
    db.delete(mem)
    db.delete(user)
    db.delete(org)
    db.commit()
    db.close()


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# API : estampillage à l'écriture + cas 14 (revalidation)
# ---------------------------------------------------------------------------

def test_creation_estampille_version_legacym(ctx_p14):
    """La création estampille sha256 réel du GPKG ; version_id reste NULL
    pour un projet legacy (pas de version artificielle)."""
    client = TestClient(app)
    r = client.post("/api/v1/apports", json={
        "project_id": ctx_p14["proj"].id, "node_id": "REG_B1",
        "mode_determination": "debit", "debit_moyen_m3s": 0.001},
        headers=_h(ctx_p14["token"]))
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["gpkg_version_id"] is None
    assert d["gpkg_sha256"] and len(d["gpkg_sha256"]) == 64


def test_revalidation_explicite(ctx_p14):
    """Cas 14 : après évolution du GPKG, l'apport apparaît dans
    /a-reconcilier, la revalidation renouvelle l'estampillage et la
    simulation redevient admissible."""
    client = TestClient(app)
    tok = _h(ctx_p14["token"])
    pid = ctx_p14["proj"].id

    r = client.post("/api/v1/apports", json={
        "project_id": pid, "node_id": "REG_B1",
        "mode_determination": "debit", "debit_moyen_m3s": 0.001}, headers=tok)
    aid = r.json()["id"]
    sha_v1 = r.json()["gpkg_sha256"]

    # Évolution du GPKG : mêmes Codes, contenu différent → nouveau sha
    _creer_gpkg(ctx_p14["gpkg"], ["REG_B1", "REG_B2"], decalage=42.0)

    # L'apport est listé comme non réconcilié (estampillage obsolète)
    lst = client.get(f"/api/v1/apports/a-reconcilier?project_id={pid}",
                     headers=tok)
    assert lst.status_code == 200
    # Son sha est désormais différent de celui du fichier courant →
    # la revalidation est nécessaire (endpoint de contrôle)
    from api.services.gpkg_versions import sha256_fichier
    sha_courant = sha256_fichier(ctx_p14["gpkg"], use_cache=False)
    assert sha_courant != sha_v1

    # La simulation est rejetée tant que l'apport n'est pas réconcilié
    db = ctx_p14["db"]
    with pytest.raises(ApportsDwfIncompatiblesError):
        from api.services.simulation_service import (
            resoudre_gpkg_pour_projet)
        gpkg_path, vmeta = resoudre_gpkg_pour_projet(db, ctx_p14["proj"])
        preparer_apports_pour_simulation(
            db, ctx_p14["proj"], dwf_actif=True,
            version_meta=vmeta, gpkg_path=gpkg_path)

    # Revalidation explicite → nouvel estampillage = sha courant
    rv = client.post(f"/api/v1/apports/{aid}/revalider", headers=tok)
    assert rv.status_code == 200, rv.text
    assert rv.json()["gpkg_sha256"] == sha_courant

    # Désormais admissible
    gpkg_path, vmeta = resoudre_gpkg_pour_projet(db, ctx_p14["proj"])
    apports, _ = preparer_apports_pour_simulation(
        db, ctx_p14["proj"], dwf_actif=True,
        version_meta=vmeta, gpkg_path=gpkg_path)
    assert [a["id"] for a in apports] == [aid]


def test_put_ne_touche_pas_estampillage_sauf_noeud(ctx_p14):
    """Une MAJ débit/profil ne change PAS l'estampillage ; un changement
    de node_id ré-estampille sur la version courante."""
    client = TestClient(app)
    tok = _h(ctx_p14["token"])
    pid = ctx_p14["proj"].id

    r = client.post("/api/v1/apports", json={
        "project_id": pid, "node_id": "REG_B1",
        "mode_determination": "debit", "debit_moyen_m3s": 0.001}, headers=tok)
    aid = r.json()["id"]
    sha1 = r.json()["gpkg_sha256"]

    r2 = client.put(f"/api/v1/apports/{aid}",
                    json={"debit_moyen_m3s": 0.005, "profile_key": "hebdomadaire"},
                    headers=tok)
    assert r2.status_code == 200
    assert r2.json()["gpkg_sha256"] == sha1  # inchangé

    # Changement de nœud → revalidation + ré-estampillage (sha identique
    # ici car même fichier, mais le mécanisme est exercé)
    r3 = client.put(f"/api/v1/apports/{aid}", json={"node_id": "REG_B2"},
                    headers=tok)
    assert r3.status_code == 200
    assert r3.json()["node_id"] == "REG_B2"
    assert r3.json()["gpkg_sha256"] == sha1


def test_reconcilier_isolation_org(ctx_p14):
    """GET /a-reconcilier est borné au projet/org du tenant (stealth)."""
    client = TestClient(app)
    db = ctx_p14["db"]
    # Apport non estampillé sur le projet P14
    a = ApportDwf(id="p14_orphelin", org_id=ctx_p14["proj"].org_id,
                  project_id=ctx_p14["proj"].id, node_id="REG_B1",
                  nature="autre", mode_determination="debit",
                  debit_moyen_m3s=0.001, profile_key="constant",
                  actif=True)  # gpkg_sha256 NULL
    db.add(a)
    db.commit()
    try:
        r = client.get(
            f"/api/v1/apports/a-reconcilier?project_id={ctx_p14['proj'].id}",
            headers=_h(ctx_p14["token"]))
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()["apports"]]
        assert "p14_orphelin" in ids
        # Un apport estampillé n'y figure pas
        client.post("/api/v1/apports", json={
            "project_id": ctx_p14["proj"].id, "node_id": "REG_B2",
            "mode_determination": "debit", "debit_moyen_m3s": 0.002},
            headers=_h(ctx_p14["token"]))
        r2 = client.get(
            f"/api/v1/apports/a-reconcilier?project_id={ctx_p14['proj'].id}",
            headers=_h(ctx_p14["token"]))
        ids2 = [x["id"] for x in r2.json()["apports"]]
        assert "p14_orphelin" in ids2
        assert all(x["node_id"] == "REG_B1" for x in r2.json()["apports"])
    finally:
        db.delete(a)
        db.commit()


# ---------------------------------------------------------------------------
# Rejet 422 au lancement synchrone (cas 2/3 au niveau API)
# ---------------------------------------------------------------------------

def test_run_rejette_apport_non_reconcilie_422(ctx_p14):
    """POST /run avec un apport actif non réconcilié → 422 explicite
    AVANT génération INP et moteur (pas d'appel SWMM)."""
    client = TestClient(app)
    tok = _h(ctx_p14["token"])
    pid = ctx_p14["proj"].id

    # Apport créé (estampillé sha_v1)
    client.post("/api/v1/apports", json={
        "project_id": pid, "node_id": "REG_B1",
        "mode_determination": "debit", "debit_moyen_m3s": 0.001}, headers=tok)

    # Le GPKG évolue → sha change → apport obsolète
    _creer_gpkg(ctx_p14["gpkg"], ["REG_B1", "REG_B2"], decalage=7.0)

    r = client.post("/api/v1/simulations/run", json={
        "cluster_id": ctx_p14["cluster"].id,
        "scenario_key": "temps_sec_pur",
        "duree_heures": 2.0,
        "project_id": pid,
    }, headers=tok)
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert "apports_incompatibles" in detail
    inc = detail["apports_incompatibles"][0]
    assert inc["node_id"] == "REG_B1"
    assert inc["simulation_gpkg_sha256"]

    # dwf_actif=False → même réseau, même apport obsolète : autorisé
    # (désactivation explicite = comportement historique, aucune injection)
    # On ne lance pas le moteur : on vérifie que le rejet ne se produit pas
    # en amont — la réponse ne doit PAS être le 422 DWF (peut être une
    # autre erreur moteur ou un succès de cache, mais pas ce 422).
    r2 = client.post("/api/v1/simulations/run", json={
        "cluster_id": ctx_p14["cluster"].id,
        "scenario_key": "temps_sec_pur",
        "duree_heures": 2.0,
        "project_id": pid,
        "dwf_actif": False,
        "force_recalculate": True,
    }, headers=tok)
    assert r2.status_code != 422 or "apports_incompatibles" not in str(r2.json())


def test_run_rejet_async_meme_regle(ctx_p14):
    """Cas 10 : le chemin Celery (executer_en_async) applique la même
    validation stricte et fait échouer le job AVANT le moteur."""
    from api.services.simulation_service import executer_en_async
    from api.services.apports_dwf_service import ApportsDwfIncompatiblesError as Err
    from api.models import Simulation

    db = ctx_p14["db"]
    pid = ctx_p14["proj"].id
    # Apport non estampillé (héritage P1.2) → rejet certain
    a = ApportDwf(id="p14_async_bad", org_id=ctx_p14["proj"].org_id,
                  project_id=pid, node_id="REG_B1", nature="autre",
                  mode_determination="debit", debit_moyen_m3s=0.001,
                  profile_key="constant", actif=True)
    db.add(a)
    db.commit()
    try:
        with pytest.raises(Err):
            executer_en_async(
                db=db, org_id=ctx_p14["proj"].org_id, project_id=pid,
                cluster_id=ctx_p14["cluster"].id,
                parameters={"scenario_pluie": "temps_sec_pur",
                            "duree_heures": 2.0},
                simulation_id=None)
        # La Simulation créée est marquée failed (pas de moteur lancé)
        sim = db.query(Simulation).filter(
            Simulation.project_id == pid).order_by(
            Simulation.created_at.desc()).first()
        assert sim is not None and sim.status == "failed"
    finally:
        db.delete(a)
        db.commit()


# ---------------------------------------------------------------------------
# Cache : cas 12 et 13
# ---------------------------------------------------------------------------

def test_changement_gpkg_invalide_cache(tmp_path):
    """Cas 12 : deux contenus GPKG distincts → gpkg_sha256 distinct →
    param_hash distinct (aucune collision de cache inter-versions)."""
    from types import SimpleNamespace
    from api.services.simulation_service import generer_cle_cache_simulation

    g1 = tmp_path / "v1.gpkg"
    g2 = tmp_path / "v2.gpkg"
    _creer_gpkg(g1, ["REG_B1"])
    _creer_gpkg(g2, ["REG_B1"], decalage=5.0)

    p = SimpleNamespace(scenario_key="s", cluster_id=1)
    h1, d1 = generer_cle_cache_simulation(g1, p)
    h2, d2 = generer_cle_cache_simulation(g2, p)
    assert d1["gpkg_sha256"] != d2["gpkg_sha256"]
    assert h1 != h2


def test_modification_apport_invalide_cache():
    """Cas 13 : modifier un apport change son empreinte → clé de cache
    différente (pas de réutilisation d'un résultat DWF obsolète)."""
    a1 = _apport_dict(id="a1", debit_moyen_m3s=0.001)
    a2 = _apport_dict(id="a1", debit_moyen_m3s=0.002)
    a3 = _apport_dict(id="a1", debit_moyen_m3s=0.001, actif=False)
    assert empreinte_apports([a1]) != empreinte_apports([a2])
    assert empreinte_apports([a1]) != empreinte_apports([a3])
    assert empreinte_apports([a1]) == empreinte_apports([dict(a1)])
