# -*- coding: utf-8 -*-
"""
Étape 3C.0 — Cohérence snapshot simulé / réseau affiché.

Couvre :
- resoudre_gpkg_pour_simulation (version_id, sha256, source_gpkg, erreurs) ;
- isolation tenant/projet des versions résolues ;
- /latest et /bassin/{cluster_id} affichant le réseau DE la simulation ;
- déterminisme du choix de simulation pour un même bassin ;
- caches graphiques isolés par contenu (_get_graph).
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from api.database import SessionLocal
from api.models import Organization, Project, GpkgVersion, Simulation
from api.services import gpkg_versions as gv


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def _creer_gpkg(path: Path, nb_regards: int = 2, nb_cana: int = 2,
                marqueur: str = "") -> Path:
    """GeoPackage minimal valide (couches regards + canalisations)."""
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
    monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setattr(gv, "GPKG_CACHE_DIR", tmp_path / "gpkg_cache")
    return tmp_path


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


def _projet(db, tmp_path, marqueur=""):
    """Organisation + projet + GPKG source (non versionné au départ)."""
    sfx = _uid()
    org = Organization(id=f"org_{sfx}", name="Org C", slug=f"org-c-{sfx}")
    db.add(org)
    db.flush()
    gpkg = _creer_gpkg(tmp_path / f"reseau_{sfx}.gpkg", marqueur=marqueur or sfx)
    proj = Project(id=f"proj_{sfx}", org_id=org.id, name=f"Projet C {sfx}",
                   source_gpkg_key=str(gpkg))
    db.add(proj)
    db.commit()
    return {"org": org, "proj": proj, "gpkg": gpkg, "sfx": sfx}


def _nettoyer(db, ctx):
    pid = ctx["proj"].id
    oid = ctx["org"].id
    db.query(Simulation).filter(Simulation.project_id == pid).delete(synchronize_session=False)
    db.query(GpkgVersion).filter(GpkgVersion.project_id == pid).delete(synchronize_session=False)
    db.query(Project).filter(Project.id == pid).delete(synchronize_session=False)
    db.query(Organization).filter(Organization.id == oid).delete(synchronize_session=False)
    db.commit()


def _data_sim(version_id=None, sha=None, source=None, cluster_id=1, bass_nom=""):
    """Payload minimal ressemblant à un résultat de simulation persisté."""
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
    if source is not None:
        d["source_gpkg"] = str(source)
    return d


# ---------------------------------------------------------------------------
# resoudre_gpkg_pour_simulation — unitaire
# ---------------------------------------------------------------------------

def test_resolution_version_id_snapshot_imms(db, env_versions):
    ctx = _projet(db, env_versions)
    try:
        v = gv.enregistrer_version_gpkg(db, ctx["proj"], ctx["gpkg"], valider=False)
        db.commit()
        data = _data_sim(version_id=v.id, sha=v.sha256)
        chemin, meta = gv.resoudre_gpkg_pour_simulation(db, ctx["proj"], data)
        assert chemin is not None and chemin.exists()
        assert meta["resolution"] == "gpkg_version_id"
        assert gv.sha256_fichier(chemin) == v.sha256
    finally:
        _nettoyer(db, ctx)


def test_resolution_deux_versions_distinctes(db, env_versions):
    ctx = _projet(db, env_versions)
    try:
        gpkg2 = _creer_gpkg(env_versions / f"v2_{ctx['sfx']}.gpkg", marqueur="B")
        v1 = gv.enregistrer_version_gpkg(db, ctx["proj"], ctx["gpkg"], valider=False)
        v2 = gv.enregistrer_version_gpkg(db, ctx["proj"], gpkg2, valider=False)
        db.commit()
        assert v1.sha256 != v2.sha256

        c1, _ = gv.resoudre_gpkg_pour_simulation(db, ctx["proj"], _data_sim(version_id=v1.id))
        c2, _ = gv.resoudre_gpkg_pour_simulation(db, ctx["proj"], _data_sim(version_id=v2.id))
        assert gv.sha256_fichier(c1) == v1.sha256
        assert gv.sha256_fichier(c2) == v2.sha256
        assert c1 != c2
    finally:
        _nettoyer(db, ctx)


def test_resolution_snapshot_fige_apres_remplacement_source(db, env_versions):
    """V1 simulée puis source remplacée par V2 : la sim V1 résout toujours V1."""
    ctx = _projet(db, env_versions)
    try:
        v1 = gv.enregistrer_version_gpkg(db, ctx["proj"], ctx["gpkg"], valider=False)
        db.commit()
        # Le projet passe à V2 (nouvel import)
        gpkg2 = _creer_gpkg(env_versions / f"v2b_{ctx['sfx']}.gpkg", marqueur="B")
        v2 = gv.enregistrer_version_gpkg(db, ctx["proj"], gpkg2, valider=False)
        db.commit()
        assert ctx["proj"].gpkg_version_id == v2.id

        # La simulation historique porte la provenance V1
        chemin, meta = gv.resoudre_gpkg_pour_simulation(
            db, ctx["proj"], _data_sim(version_id=v1.id, sha=v1.sha256))
        assert gv.sha256_fichier(chemin) == v1.sha256
        assert meta["version_id"] == v1.id
    finally:
        _nettoyer(db, ctx)


def test_resolution_legacy_sans_provenance(db, env_versions):
    """Simulation historique sans provenance : source_gpkg existant = fallback."""
    ctx = _projet(db, env_versions)
    try:
        data = _data_sim(source=ctx["gpkg"])
        chemin, meta = gv.resoudre_gpkg_pour_simulation(db, ctx["proj"], data)
        assert chemin == Path(ctx["gpkg"])
        assert meta["resolution"] == "source_gpkg_legacy"
    finally:
        _nettoyer(db, ctx)


def test_resolution_sha_sans_version_mais_source_verifie(db, env_versions):
    """sha256 de provenance sans version enregistrée : source_gpkg retenu
    uniquement si son empreinte réelle correspond."""
    ctx = _projet(db, env_versions)
    try:
        sha = gv.sha256_fichier(ctx["gpkg"])
        chemin, meta = gv.resoudre_gpkg_pour_simulation(
            db, ctx["proj"], _data_sim(sha=sha, source=ctx["gpkg"]))
        assert chemin == Path(ctx["gpkg"])
        assert meta["resolution"] == "source_gpkg_sha256"
    finally:
        _nettoyer(db, ctx)


def test_resolution_provenance_invalide_erreur_expresse(db, env_versions):
    """Provenance explicite irrésoluble → GpkgSimulationError, jamais de repli."""
    ctx = _projet(db, env_versions)
    ctx2 = _projet(db, env_versions)
    try:
        # version_id inexistant
        with pytest.raises(gv.GpkgSimulationError):
            gv.resoudre_gpkg_pour_simulation(
                db, ctx["proj"], _data_sim(version_id="version-inexistante"))

        # sha256 sans version ni source correspondante
        with pytest.raises(gv.GpkgSimulationError):
            gv.resoudre_gpkg_pour_simulation(
                db, ctx["proj"], _data_sim(sha="f" * 64, source=ctx["gpkg"]))

        # version d'un AUTRE projet utilisée dans le contexte de ctx → incohérent
        v_autre = gv.enregistrer_version_gpkg(db, ctx2["proj"], ctx2["gpkg"], valider=False)
        db.commit()
        with pytest.raises(gv.GpkgSimulationError):
            gv.resoudre_gpkg_pour_simulation(
                db, ctx["proj"], _data_sim(version_id=v_autre.id))
    finally:
        _nettoyer(db, ctx)
        _nettoyer(db, ctx2)


# ---------------------------------------------------------------------------
# Endpoints : /latest et /bassin — réseau de la simulation, pas du mutable
# ---------------------------------------------------------------------------

def _sim_row(db, ctx, data, bassin_ref=None, exutoire=None, cluster_id=1,
             created_at=None):
    """Crée une ligne Simulation + fichier JSON de résultats."""
    sim_id = str(uuid.uuid4())
    fjson = Path(ctx["tmp"]) / f"sim_{sim_id}.json"
    fjson.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    sim = Simulation(
        id=sim_id,
        org_id=ctx["org"].id,
        project_id=ctx["proj"].id,
        name=f"SWMM_{ctx['proj'].name}_{cluster_id}_pluie",
        status="completed",
        scenario_pluie="pluie_decennale",
        duree_heures=4.0,
        results_s3_key=str(fjson.resolve()),
        gpkg_version_id=(data.get("provenance") or {}).get("gpkg_version_id"),
        gpkg_sha256=(data.get("provenance") or {}).get("gpkg_sha256"),
        bassin_ref=bassin_ref,
        exutoire_noeud=exutoire,
        summary_kpis={"cluster_id": cluster_id, "parameters": {}},
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(sim)
    db.commit()
    return sim


@pytest.fixture
def endpoint_ctx(db, env_versions):
    ctx = _projet(db, env_versions)
    ctx["tmp"] = env_versions
    yield ctx
    _nettoyer(db, ctx)


def _tenant(ctx):
    """TenantContext minimal pour l'organisation du projet de test."""
    from api.core.security import TenantContext
    return TenantContext(actor=None, org=ctx["org"], role="admin")


def _sim_autorisee(db, org_id, **kwargs):
    """Résout la simulation autorisée exactement comme les routes (3D.5 :
    plus de lecture de la globale `_DERNIERE_SIMULATION`, supprimée)."""
    from api.services.simulation_service import resoudre_simulation_courante
    return resoudre_simulation_courante(
        db, org_id=org_id, resoudre_gpkg=True, **kwargs)


def test_latest_utilise_snapshot_de_la_simulation(db, endpoint_ctx, env_versions):
    """Sim sur V1, projet passé à V2 : /latest affiche toujours V1."""
    from api.routes import simulations as sim_routes

    ctx = endpoint_ctx
    v1 = gv.enregistrer_version_gpkg(db, ctx["proj"], ctx["gpkg"], valider=False)
    db.commit()

    data_v1 = _data_sim(version_id=v1.id, sha=v1.sha256, cluster_id=7)
    data_v1["meta"]["bassin_nom"] = "BASSIN_V1"
    _sim_row(db, ctx, data_v1, bassin_ref="exutoire:3479")

    # Le projet évolue vers V2
    gpkg2 = _creer_gpkg(env_versions / f"v2c_{ctx['sfx']}.gpkg", marqueur="B")
    v2 = gv.enregistrer_version_gpkg(db, ctx["proj"], gpkg2, valider=False)
    db.commit()

    resp = sim_routes.get_latest_simulation(db=db, tenant=_tenant(ctx))
    ctx2 = _sim_autorisee(db, ctx["org"].id)
    assert ctx2.gpkg_path and gv.sha256_fichier(ctx2.gpkg_path) == v1.sha256, (
        f"latest aurait dû utiliser le snapshot V1, obtenu {ctx2.gpkg_path}")


def test_bassin_choisit_simulation_la_plus_recente(db, endpoint_ctx):
    """Deux simulations du même bassin : /bassin retourne la plus récente."""
    from api.routes import simulations as sim_routes

    ctx = endpoint_ctx
    v = gv.enregistrer_version_gpkg(db, ctx["proj"], ctx["gpkg"], valider=False)
    db.commit()
    now = datetime.now(timezone.utc)

    ancien_data = _data_sim(version_id=v.id, sha=v.sha256, cluster_id=3)
    ancien_data["meta"]["bassin_nom"] = "ANCIENNE_SIM"
    _sim_row(db, ctx, ancien_data, bassin_ref="exutoire:3479",
             created_at=now - timedelta(hours=2))

    recent_data = _data_sim(version_id=v.id, sha=v.sha256, cluster_id=3)
    recent_data["meta"]["bassin_nom"] = "RECENTE_SIM"
    _sim_row(db, ctx, recent_data, bassin_ref="exutoire:3479",
             created_at=now)

    resp = sim_routes.get_bassin_simulation(cluster_id="exutoire:3479", db=db, tenant=_tenant(ctx))
    ctx2 = _sim_autorisee(db, ctx["org"].id, cluster_id="exutoire:3479")
    assert ctx2.data.get("meta", {}).get("bassin_nom") == "RECENTE_SIM", (
        f"Attendu RECENTE_SIM, obtenu {resp} / {ctx2.data.get('meta')}")


def test_bassin_simulation_version_v1_apres_passage_v2(db, endpoint_ctx, env_versions):
    """La simulation V1 d'un bassin reste affichée sur V1 même si le projet est V2."""
    from api.routes import simulations as sim_routes

    ctx = endpoint_ctx
    v1 = gv.enregistrer_version_gpkg(db, ctx["proj"], ctx["gpkg"], valider=False)
    db.commit()
    data = _data_sim(version_id=v1.id, sha=v1.sha256, cluster_id=9)
    _sim_row(db, ctx, data, bassin_ref="exutoire:1111")

    gpkg2 = _creer_gpkg(env_versions / f"v2d_{ctx['sfx']}.gpkg", marqueur="B")
    gv.enregistrer_version_gpkg(db, ctx["proj"], gpkg2, valider=False)
    db.commit()

    sim_routes.get_bassin_simulation(cluster_id="exutoire:1111", db=db, tenant=_tenant(ctx))
    ctx2 = _sim_autorisee(db, ctx["org"].id, cluster_id="exutoire:1111")
    assert ctx2.gpkg_path is not None
    assert gv.sha256_fichier(ctx2.gpkg_path) == v1.sha256


def test_bassin_isolation_tenant(db, endpoint_ctx, env_versions):
    """Un tenant B (avec son propre projet) ne doit pas voir la simulation du tenant A."""
    from api.routes import simulations as sim_routes
    from api.core.security import TenantContext

    ctx = endpoint_ctx
    v = gv.enregistrer_version_gpkg(db, ctx["proj"], ctx["gpkg"], valider=False)
    db.commit()
    data = _data_sim(version_id=v.id, sha=v.sha256, cluster_id=5)
    _sim_row(db, ctx, data, bassin_ref="exutoire:9999")

    # Tenant B : organisation + projet distincts (GPKG différent, non versionné)
    sfx = _uid()
    org_b = Organization(id=f"orgB_{sfx}", name="Org B", slug=f"org-b-{sfx}")
    db.add(org_b)
    db.flush()
    gpkg_b = _creer_gpkg(env_versions / f"reseau_b_{sfx}.gpkg", marqueur="Z")
    proj_b = Project(id=f"projb_{sfx}", org_id=org_b.id, name="Projet B",
                     source_gpkg_key=str(gpkg_b))
    db.add(proj_b)
    db.commit()
    tenant_b = TenantContext(actor=None, org=org_b, role="admin")

    resp = sim_routes.get_bassin_simulation(cluster_id="exutoire:9999", db=db, tenant=tenant_b)
    assert resp.get("status") == "none", (
        f"Le tenant B ne devrait voir aucune simulation du tenant A, obtenu {resp}")
    db.query(Project).filter(Project.id == proj_b.id).delete(synchronize_session=False)
    db.query(Organization).filter(Organization.id == org_b.id).delete(synchronize_session=False)
    db.commit()


# ---------------------------------------------------------------------------
# Caches graphiques : isolation par contenu
# ---------------------------------------------------------------------------

def test_get_graph_cle_isolee_par_contenu(db, env_versions):
    """Deux GPKG différents → deux entrées de cache distinctes."""
    from api.routes import clusters as clusters_routes

    p1 = _creer_gpkg(env_versions / "g1.gpkg", marqueur="A")
    p2 = _creer_gpkg(env_versions / "g2.gpkg", marqueur="B")

    ancien = dict(clusters_routes._GRAPH_CACHES)
    clusters_routes._GRAPH_CACHES = {}
    try:
        g1 = clusters_routes._get_graph(str(p1))
        g2 = clusters_routes._get_graph(str(p2))
        g1_again = clusters_routes._get_graph(str(p1))
        assert len(clusters_routes._GRAPH_CACHES) == 2
        assert g1_again is g1  # cache hit sur même contenu
        assert g1 is not g2
        # Si les graphes sont peuplés, les nœuds doivent différer (marqueurs)
        if len(g1.nodes) and len(g2.nodes):
            assert set(g1.nodes) != set(g2.nodes)
    finally:
        clusters_routes._GRAPH_CACHES = ancien


# ---------------------------------------------------------------------------
# E2E HTTP : remplacement du GPKG source entre deux versions
# ---------------------------------------------------------------------------

def test_e2e_http_latest_snapshot_v1_puis_reseau_v2(env_versions):
    """Scénario E2E via TestClient :

    1. utilisateur authentifié, projet approvisionné ;
    2. GPKG V1 importé + versionné + simulation rattachée ;
    3. GET /simulations/latest → réseau V1 ;
    4. source remplacée par V2 (nouvelle version + pointeur projet) ;
    5. GET /simulations/latest → toujours V1 (snapshot de la simulation) ;
    6. GET /layers → V2 (réseau courant du projet).
    """
    from fastapi.testclient import TestClient
    from api.main import app
    from api.models import User, Membership
    from api.routes import simulations as sim_routes

    sfx = _uid()
    email = f"e2e.{sfx}@example.com"
    client = TestClient(app)

    reg = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": "E2E Snapshot",
        "org_name": f"Org E2E {sfx}",
        "plan_type": "pro",
    })
    assert reg.status_code == 201
    dev_code = reg.json()["dev_code"]
    ver = client.post("/api/v1/auth/verify-email", json={"email": email, "code": dev_code})
    assert ver.status_code == 200
    vdata = ver.json()
    token = vdata.get("access_token") or vdata.get("tokens", {}).get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    # Projet + org créés par le provisioning d'inscription
    s = SessionLocal()
    user = s.query(User).filter(User.email == email).first()
    membership = s.query(Membership).filter(Membership.user_id == user.id).first()
    proj = s.query(Project).filter(
        Project.org_id == membership.org_id, Project.is_archived.is_(False)).first()
    org_id, proj_id = membership.org_id, proj.id

    sim_ids, version_ids = [], []
    from api.services.simulation_service import resoudre_simulation_courante
    try:
        # --- V1 : réseau 2 regards / 2 canalisations ---
        gpkg_v1 = _creer_gpkg(env_versions / f"e2e_v1_{sfx}.gpkg",
                              nb_regards=2, nb_cana=2, marqueur="V1")
        proj.source_gpkg_key = str(gpkg_v1)
        s.commit()
        v1 = gv.enregistrer_version_gpkg(s, proj, gpkg_v1, valider=False)
        s.commit()
        version_ids.append(v1.id)
        data_v1 = _data_sim(version_id=v1.id, sha=v1.sha256, cluster_id=1)
        sim_id = str(uuid.uuid4())
        fjson = env_versions / f"e2e_sim_{sim_id}.json"
        fjson.write_text(json.dumps(data_v1), encoding="utf-8")
        sim = Simulation(
            id=sim_id, org_id=org_id, project_id=proj_id,
            name=f"SWMM_E2E_{proj_id}_1_pluie", status="completed",
            scenario_pluie="pluie_decennale", duree_heures=4.0,
            results_s3_key=str(fjson.resolve()),
            gpkg_version_id=v1.id, gpkg_sha256=v1.sha256,
            summary_kpis={"cluster_id": 1, "parameters": {}},
            created_at=datetime.now(timezone.utc),
        )
        s.add(sim)
        s.commit()
        sim_ids.append(sim_id)

        # GET /latest → la simulation V1 doit afficher le snapshot V1
        r1 = client.get("/api/v1/simulations/latest", headers=headers)
        assert r1.status_code == 200, r1.text
        assert r1.json().get("status") == "success"
        c1 = resoudre_simulation_courante(
            s, org_id=org_id, project_id=proj_id, resoudre_gpkg=True)
        sha_affiche = gv.sha256_fichier(c1.gpkg_path)
        assert sha_affiche == v1.sha256

        # --- Remplacement : V2 = 7 regards / 1 canalisation ---
        gpkg_v2 = _creer_gpkg(env_versions / f"e2e_v2_{sfx}.gpkg",
                              nb_regards=7, nb_cana=1, marqueur="V2")
        proj.source_gpkg_key = str(gpkg_v2)
        s.commit()
        v2 = gv.enregistrer_version_gpkg(s, proj, gpkg_v2, valider=False)
        s.commit()
        version_ids.append(v2.id)
        assert proj.gpkg_version_id == v2.id

        # GET /latest → toujours la simulation V1 (snapshot figé)
        r2 = client.get("/api/v1/simulations/latest", headers=headers)
        assert r2.status_code == 200, r2.text
        c2 = resoudre_simulation_courante(
            s, org_id=org_id, project_id=proj_id, resoudre_gpkg=True)
        sha_affiche2 = gv.sha256_fichier(c2.gpkg_path)
        assert sha_affiche2 == v1.sha256, (
            f"latest aurait dû rester sur V1 ({v1.sha256[:12]}), "
            f"obtenu {sha_affiche2[:12]}")

        # GET /layers → le RÉSEAU COURANT doit être V2
        rl = client.get("/api/v1/layers", headers=headers)
        assert rl.status_code == 200, rl.text
        comp = rl.json()["compteurs"]
        assert comp["regards"] == 7 and comp["conduites"] == 1, (
            f"layers devrait refléter V2 (7/1), obtenu {comp}")
    finally:
        # Nettoyage complet : sim → versions → projet → membership → user → org
        if sim_ids:
            s.query(Simulation).filter(Simulation.id.in_(sim_ids)).delete(synchronize_session=False)
        if version_ids:
            s.query(GpkgVersion).filter(GpkgVersion.id.in_(version_ids)).delete(synchronize_session=False)
        s.query(Project).filter(Project.id == proj_id).delete(synchronize_session=False)
        s.query(Membership).filter(Membership.org_id == org_id).delete(synchronize_session=False)
        s.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        s.query(Organization).filter(Organization.id == org_id).delete(synchronize_session=False)
        s.commit()
        s.close()
