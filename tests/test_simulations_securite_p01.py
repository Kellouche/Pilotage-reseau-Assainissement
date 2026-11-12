"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : LOT P0.1 — Sécurisation des endpoints de simulation (AN-02)

Vérifie au niveau HTTP (TestClient + vrais jetons JWT) que :
  - les routes sensibles de simulation rejettent l'anonyme en 401 ;
  - un utilisateur n'accède qu'aux projets de sa propre organisation ;
  - un project_id inexistant ou cross-organisation produit un stealth 404 ;
  - plusieurs projets actifs sans project_id produisent un 409 ;
  - le mode démo n'est atteint que via le flag explicite
    DRAINPILOT_MODE_DEMO_RESEAU, jamais comme repli anonyme.
================================================================================
"""

import pytest
from starlette.testclient import TestClient

from api.main import app
from api.database import SessionLocal, engine, Base
from api.models import Organization, User, Membership, Project, Simulation
from api.core.auth import hash_password, create_access_token
from api.services.simulation_service import (
    resoudre_contexte_projet,
    _resoudre_projet_pour_simulation,
    ContexteProjetIntrouvable,
    ContexteSimulationIntrouvable,
    ProjetAmbigu,
)


@pytest.fixture(scope="module", autouse=True)
def init_db_schema():
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def ctx_securite(tmp_path):
    """Quatre organisations : A (1 projet), B (1 projet), C (2 projets → 409),
    D (aucun projet → test du gating démo)."""
    db = SessionLocal()
    prefix = "p01"

    def _org(uid, slug):
        return Organization(id=f"{prefix}_{uid}", name=f"Org {uid}", slug=f"{slug}-{uid}")

    def _user(uid, email):
        return User(id=f"{prefix}_u_{uid}", email=email,
                    password_hash=hash_password("SecurPass2026!"),
                    full_name=f"User {uid}", email_verified=True)

    def _proj(pid, org, name):
        return Project(id=f"{prefix}_{pid}", org_id=org.id, name=name,
                       slug=f"{pid}-{org.id}",
                       source_gpkg_key=str(tmp_path / f"{pid}.gpkg"),
                       is_archived=False)

    org_a, org_b, org_c, org_d = (_org("a", "org-a"), _org("b", "org-b"),
                                _org("c", "org-c"), _org("d", "org-d"))
    user_a, user_b, user_c, user_d = (
        _user("a", "a@p01.dz"), _user("b", "b@p01.dz"),
        _user("c", "c@p01.dz"), _user("d", "d@p01.dz"))
    mems = [Membership(org_id=o.id, user_id=u.id, role="admin")
            for o, u in ((org_a, user_a), (org_b, user_b),
                         (org_c, user_c), (org_d, user_d))]
    proj_a = _proj("pa", org_a, "Projet A")
    proj_b = _proj("pb", org_b, "Projet B")
    proj_c1 = _proj("pc1", org_c, "Projet C1")
    proj_c2 = _proj("pc2", org_c, "Projet C2")

    sim_a = Simulation(org_id=org_a.id, project_id=proj_a.id, name="sim_a")
    sim_b = Simulation(org_id=org_b.id, project_id=proj_b.id, name="sim_b")

    db.add_all([org_a, org_b, org_c, org_d, user_a, user_b, user_c, user_d,
                *mems, proj_a, proj_b, proj_c1, proj_c2, sim_a, sim_b])
    db.commit()

    ctx = {
        "db": db,
        "org_a": org_a, "org_b": org_b, "org_c": org_c, "org_d": org_d,
        "proj_a": proj_a, "proj_b": proj_b, "proj_c1": proj_c1, "proj_c2": proj_c2,
        "sim_a": sim_a, "sim_b": sim_b,
        "token_a": create_access_token({"sub": user_a.id, "org_id": org_a.id, "role": "admin"}),
        "token_b": create_access_token({"sub": user_b.id, "org_id": org_b.id, "role": "engineer"}),
        "token_c": create_access_token({"sub": user_c.id, "org_id": org_c.id, "role": "admin"}),
        "token_d": create_access_token({"sub": user_d.id, "org_id": org_d.id, "role": "admin"}),
    }
    yield ctx
    # Nettoyage
    for obj in (sim_a, sim_b, proj_a, proj_b, proj_c1, proj_c2):
        db.delete(obj)
    for m in mems:
        db.delete(m)
    for u in (user_a, user_b, user_c, user_d):
        db.delete(u)
    for o in (org_a, org_b, org_c, org_d):
        db.delete(o)
    db.commit()
    db.close()


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. Accès anonyme → 401 sur toutes les routes sensibles
# ---------------------------------------------------------------------------

ROUTES_ANONYMES = [
    ("get", "/api/v1/simulations"),
    ("get", "/api/v1/simulations/latest"),
    ("get", "/api/v1/simulations/timeseries"),
    ("get", "/api/v1/simulations/profil-en-long?node_amont=R1&node_aval=R2"),
    ("get", "/api/v1/simulations/download/inp"),
    ("get", "/api/v1/simulations/download/rpt"),
    ("get", "/api/v1/simulations/agents/interpretation"),
    ("get", "/api/v1/simulations/bassin/1"),
    ("get", "/api/v1/simulations/status/job_x"),
    ("get", "/api/v1/simulations/job/job_x"),
]


@pytest.mark.parametrize("methode,chemin", ROUTES_ANONYMES)
def test_anonyme_401_sur_routes_sensibles(methode, chemin):
    client = TestClient(app)
    resp = getattr(client, methode)(chemin)
    assert resp.status_code == 401, f"{chemin} aurait dû renvoyer 401, obtenu {resp.status_code}"


def test_anonyme_401_post_run(ctx_securite):
    client = TestClient(app)
    resp = client.post("/api/v1/simulations/run", json={"cluster_id": 1})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 2. Authentification propre organisation : fonctionne
# ---------------------------------------------------------------------------

def test_authentifie_propre_org_fonctionne(ctx_securite):
    client = TestClient(app)
    h = _headers(ctx_securite["token_a"])

    # Liste des simulations : 200, bornée à org A
    resp = client.get("/api/v1/simulations", headers=h)
    assert resp.status_code == 200
    ids = {s["id"] for s in resp.json()}
    assert str(ctx_securite["sim_a"].id) in ids
    assert str(ctx_securite["sim_b"].id) not in ids

    # Lecture directe de SA simulation : 200
    resp = client.get(f"/api/v1/simulations/{ctx_securite['sim_a'].id}", headers=h)
    assert resp.status_code == 200

    # /latest : aucune simulation ResultStore → 200 {"status": "none"}
    resp = client.get("/api/v1/simulations/latest", headers=h)
    assert resp.status_code == 200
    assert resp.json().get("status") in ("none", "success")


# ---------------------------------------------------------------------------
# 3. Isolation inter-organisations
# ---------------------------------------------------------------------------

def test_cross_org_simulation_refusee(ctx_securite):
    """Un utilisateur ne peut ni simuler ni lire les résultats d'un autre org."""
    client = TestClient(app)
    h_a = _headers(ctx_securite["token_a"])

    # POST /run sur le projet de l'org B → stealth 404
    resp = client.post(
        "/api/v1/simulations/run",
        json={"cluster_id": 1, "project_id": ctx_securite["proj_b"].id},
        headers=h_a)
    assert resp.status_code == 404

    # Lecture directe de la simulation de l'org B → 404
    resp = client.get(f"/api/v1/simulations/{ctx_securite['sim_b'].id}", headers=h_a)
    assert resp.status_code == 404

    # Download INP ciblant le projet de l'org B → 404 (contrôles 3C.7.5)
    resp = client.get(
        "/api/v1/simulations/download/inp",
        params={"project_id": ctx_securite["proj_b"].id, "cluster_id": "7"},
        headers=h_a)
    assert resp.status_code == 404


def test_projet_inexistant_404(ctx_securite):
    client = TestClient(app)
    h = _headers(ctx_securite["token_a"])

    resp = client.post(
        "/api/v1/simulations/run",
        json={"cluster_id": 1, "project_id": "proj_n_existe_pas"},
        headers=h)
    assert resp.status_code == 404

    resp = client.get(
        "/api/v1/simulations/download/inp",
        params={"project_id": "proj_n_existe_pas"},
        headers=h)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 4. Ambiguïté multi-projets → 409 explicite
# ---------------------------------------------------------------------------

def test_multi_projets_sans_project_id_409(ctx_securite):
    client = TestClient(app)
    h = _headers(ctx_securite["token_c"])

    resp = client.get("/api/v1/simulations/latest", headers=h)
    assert resp.status_code == 409

    resp = client.post("/api/v1/simulations/run", json={"cluster_id": 1}, headers=h)
    assert resp.status_code == 409

    resp = client.get(
        "/api/v1/simulations/download/inp", params={"cluster_id": "7"}, headers=h)
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# 5. Mode démo : uniquement via flag explicite, jamais en repli anonyme
# ---------------------------------------------------------------------------

def test_demo_desactivee_par_defaut(ctx_securite):
    """Org sans projet + flag démo OFF → /run renvoie 404, pas de repli démo."""
    client = TestClient(app)
    h = _headers(ctx_securite["token_d"])
    resp = client.post("/api/v1/simulations/run", json={"cluster_id": 1}, headers=h)
    assert resp.status_code == 404


def test_demo_service_nivel(ctx_securite, monkeypatch):
    """Niveau service : autoriser_demo=False refuse ; True retourne le GPKG démo."""
    db = ctx_securite["db"]
    org_d_id = ctx_securite["org_d"].id

    with pytest.raises(ContexteSimulationIntrouvable):
        resoudre_contexte_projet(db, org_d_id, autoriser_demo=False)

    monkeypatch.setattr("config.settings.MODE_DEMO_RESEAU", True)
    ctx = resoudre_contexte_projet(db, org_d_id, autoriser_demo=True)
    assert ctx.gpkg_path is not None
    assert ctx.gpkg_path.name == "demo_reseau.gpkg"
    assert ctx.project is None


def test_resolver_projet_refuse_contexte_anonyme(ctx_securite):
    """Niveau service : org_id=None ne doit JAMAIS résoudre un projet."""
    db = ctx_securite["db"]
    with pytest.raises(ContexteSimulationIntrouvable):
        _resoudre_projet_pour_simulation(db, None, None)
    with pytest.raises(ContexteProjetIntrouvable):
        resoudre_contexte_projet(db, None)


def test_organisation_sans_projet_404(ctx_securite):
    """Org authentifiée sans projet actif et sans démo → 404 explicite,
    aucun contenu de démonstration servi par défaut."""
    client = TestClient(app)
    h = _headers(ctx_securite["token_d"])
    resp = client.get("/api/v1/simulations/download/inp", headers=h)
    assert resp.status_code == 404
