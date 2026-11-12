# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : LOT P1.5.1 — Tests de GET /api/v1/apports/a-reconcilier exhaustif

L'endpoint doit identifier TOUS les apports actifs incompatibles avec le
réseau GPKG courant (non estampillés, version différente, sha différent,
nœud absent du snapshot) avec un code motif stable — en lecture seule,
strictement cohérent avec la validation réelle de preparer_apports_pour_
simulation. Les apports inactifs ne bloquent jamais.
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
)


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


@pytest.fixture
def ctx_p15(tmp_path):
    """Org/user/projet legacy sur GPKG minimal (nœuds REG_B1, REG_B2) +
    cluster + token engineer."""
    gpkg = tmp_path / "reseau_p15.gpkg"
    _creer_gpkg(gpkg, ["REG_B1", "REG_B2"])

    db = SessionLocal()
    pref = "p15"
    org = Organization(id=f"{pref}_o", name="O15", slug=f"{pref}-o")
    user = User(id=f"{pref}_u", email="u@p15.dz",
                password_hash=hash_password("DwfPass2026!"),
                full_name="U15", email_verified=True)
    mem = Membership(org_id=org.id, user_id=user.id, role="engineer")
    proj = Project(id=f"{pref}_p", org_id=org.id, name="Projet P15",
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


def _get_reconcilier(client, tok, pid):
    r = client.get(f"/api/v1/apports/a-reconcilier?project_id={pid}",
                   headers=tok)
    assert r.status_code == 200, r.text
    return r.json()


def _creer_apport_api(client, tok, pid, node="REG_B1", **kw):
    body = {"project_id": pid, "node_id": node,
            "mode_determination": "debit", "debit_moyen_m3s": 0.001}
    body.update(kw)
    r = client.post("/api/v1/apports", json=body, headers=tok)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Cas obligatoires
# ---------------------------------------------------------------------------

def test_reconcilier_non_estampille_et_inactif(ctx_p15):
    """Apport actif sans estampillage → 'non_reconcilie' ; apport inactif
    non estampillé → PAS listé (ne bloque pas la simulation)."""
    client = TestClient(app)
    tok = _h(ctx_p15["token"])
    pid = ctx_p15["proj"].id
    db = ctx_p15["db"]

    actif = _creer_apport_api(client, tok, pid)
    a = db.get(ApportDwf, actif["id"])
    a.gpkg_version_id = None
    a.gpkg_sha256 = None
    inactif = _creer_apport_api(client, tok, pid, node="REG_B2", actif=False)
    b = db.get(ApportDwf, inactif["id"])
    b.gpkg_version_id = None
    b.gpkg_sha256 = None
    db.commit()

    res = _get_reconcilier(client, tok, pid)
    assert res["count"] == 1
    d = res["incompatibles"][0]
    assert d["code"] == "non_reconcilie"
    assert d["apport_id"] == actif["id"]
    assert d["node_id"] == "REG_B1"
    assert d["motif"]
    assert "revalider" in d["action_attendue"]
    assert res["apports"][0]["id"] == actif["id"]
    assert res["reseau_courant"]["gpkg_sha256"]
    assert res["reseau_courant"]["disponible"] is True
    assert res["erreur"] is None


def test_reconcilier_legacy_sha_identique_compatible(ctx_p15):
    """Apport legacy estampillé sur le sha courant → compatible : absent
    de la liste, et la validation réelle ne le rejette pas."""
    client = TestClient(app)
    tok = _h(ctx_p15["token"])
    pid = ctx_p15["proj"].id
    db = ctx_p15["db"]

    a = _creer_apport_api(client, tok, pid)
    res = _get_reconcilier(client, tok, pid)
    assert res["count"] == 0 and res["incompatibles"] == []
    assert res["apports"] == []

    from api.services.gpkg_versions import resoudre_version_pour_simulation
    gpkg_path, vmeta = resoudre_version_pour_simulation(db, ctx_p15["proj"])
    apports, _ = preparer_apports_pour_simulation(
        db, ctx_p15["proj"], dwf_actif=True,
        version_meta=vmeta, gpkg_path=gpkg_path)
    assert [x["id"] for x in apports] == [a["id"]]


def test_reconcilier_legacy_sha_different(ctx_p15):
    """GPKG remplacé → apport estampillé ancien sha →
    'sha256_difference_legacy'."""
    client = TestClient(app)
    tok = _h(ctx_p15["token"])
    pid = ctx_p15["proj"].id

    _creer_apport_api(client, tok, pid)
    _creer_gpkg(ctx_p15["gpkg"], ["REG_B1", "REG_B2"], decalage=55.0)

    res = _get_reconcilier(client, tok, pid)
    assert res["count"] == 1
    d = res["incompatibles"][0]
    assert d["code"] == "sha256_difference_legacy"
    assert d["apport_gpkg_sha256"] != res["reseau_courant"]["gpkg_sha256"]


def test_reconcilier_noeud_absent_du_snapshot(ctx_p15):
    """Estampillage correct mais node_id absent du réseau courant →
    'noeud_absent_du_snapshot' (estampillage posé directement pour isoler
    le motif du contrôle nœud)."""
    client = TestClient(app)
    tok = _h(ctx_p15["token"])
    pid = ctx_p15["proj"].id
    db = ctx_p15["db"]

    from api.services.gpkg_versions import sha256_fichier
    sha_courant = sha256_fichier(ctx_p15["gpkg"])
    a = ApportDwf(id="p15_noeud_absent", org_id=ctx_p15["proj"].org_id,
                  project_id=pid, node_id="NOEUD_FANTOME",
                  nature="autre", mode_determination="debit",
                  debit_moyen_m3s=0.001, profile_key="constant",
                  actif=True, gpkg_sha256=sha_courant)
    db.add(a)
    db.commit()
    try:
        res = _get_reconcilier(client, tok, pid)
        assert res["count"] == 1
        assert res["incompatibles"][0]["code"] == "noeud_absent_du_snapshot"
        assert res["incompatibles"][0]["node_id"] == "NOEUD_FANTOME"
    finally:
        db.delete(a)
        db.commit()


def test_reconcilier_version_differencee(ctx_p15, tmp_path, monkeypatch):
    """Projet VERSIONNÉ : apport estampillé V1, projet basculé sur V2 →
    'version_differencee' ; même version_id mais sha altéré →
    'sha256_difference' ; revalidation → liste vide."""
    import api.services.gpkg_versions as gv
    monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setattr(gv, "GPKG_CACHE_DIR", tmp_path / "gpkg_cache")

    client = TestClient(app)
    tok = _h(ctx_p15["token"])
    pid = ctx_p15["proj"].id
    db = ctx_p15["db"]
    proj = ctx_p15["proj"]

    v1 = gv.enregistrer_version_gpkg(db, proj, ctx_p15["gpkg"], valider=False)
    proj.gpkg_version_id = v1.id
    db.commit()

    a = _creer_apport_api(client, tok, pid)
    assert a["gpkg_version_id"] == v1.id
    assert a["gpkg_sha256"] == v1.sha256

    _creer_gpkg(ctx_p15["gpkg"], ["REG_B1", "REG_B2"], decalage=77.0)
    v2 = gv.enregistrer_version_gpkg(db, proj, ctx_p15["gpkg"], valider=False)
    proj.gpkg_version_id = v2.id
    db.commit()

    res = _get_reconcilier(client, tok, pid)
    assert res["count"] == 1
    d = res["incompatibles"][0]
    assert d["code"] == "version_differencee"
    assert d["apport_gpkg_version_id"] == v1.id
    assert res["reseau_courant"]["gpkg_version_id"] == v2.id

    row = db.get(ApportDwf, a["id"])
    row.gpkg_version_id = v2.id
    row.gpkg_sha256 = "0" * 64
    db.commit()
    res2 = _get_reconcilier(client, tok, pid)
    assert res2["incompatibles"][0]["code"] == "sha256_difference"

    rv = client.post(f"/api/v1/apports/{a['id']}/revalider", headers=tok)
    assert rv.status_code == 200, rv.text
    res3 = _get_reconcilier(client, tok, pid)
    assert res3["count"] == 0

    # Nettoyage versionnage : le fixture supprime l'apport, on retire les
    # versions et le rattachement pour ne pas polluer les autres tests.
    db.query(ApportDwf).filter(ApportDwf.project_id == pid).delete()
    from api.models import GpkgVersion
    db.query(GpkgVersion).filter(GpkgVersion.project_id == pid).delete()
    proj.gpkg_version_id = None
    db.commit()


def test_reconcilier_plusieurs_motifs_et_isolation(ctx_p15):
    """Plusieurs apports à motifs distincts + isolation org/projet :
    l'apport d'un autre projet n'apparaît jamais."""
    client = TestClient(app)
    tok = _h(ctx_p15["token"])
    pid = ctx_p15["proj"].id
    db = ctx_p15["db"]

    a1 = _creer_apport_api(client, tok, pid)
    a2 = _creer_apport_api(client, tok, pid, node="REG_B2")
    r2 = db.get(ApportDwf, a2["id"])
    r2.gpkg_sha256 = None
    a3 = _creer_apport_api(client, tok, pid, node="REG_B1", actif=False)
    r3 = db.get(ApportDwf, a3["id"])
    r3.gpkg_sha256 = None
    org2 = Organization(id="p15_o2", name="O2", slug="p15-o2")
    proj2 = Project(id="p15_p2", org_id=org2.id, name="P2",
                    slug="p15-p2", source_gpkg_key=str(ctx_p15["gpkg"]),
                    is_archived=False)
    a4 = ApportDwf(id="p15_a4", org_id=org2.id, project_id=proj2.id,
                   node_id="REG_B1", nature="autre",
                   mode_determination="debit", debit_moyen_m3s=0.001,
                   profile_key="constant", actif=True)
    db.add_all([org2, proj2, a4])
    db.commit()
    try:
        res = _get_reconcilier(client, tok, pid)
        codes = {d["apport_id"]: d["code"] for d in res["incompatibles"]}
        assert codes == {a2["id"]: "non_reconcilie"}
        assert a1["id"] not in codes and a3["id"] not in codes
        assert "p15_a4" not in codes
        assert res["count"] == 1
    finally:
        db.delete(a4)
        db.delete(proj2)
        db.delete(org2)
        db.commit()


def test_reconcilier_sans_effet_de_bord(ctx_p15):
    """GET /a-reconcilier est strictement lecture seule : aucun
    ré-estampillage — deux appels identiques, apport inchangé."""
    client = TestClient(app)
    tok = _h(ctx_p15["token"])
    pid = ctx_p15["proj"].id
    db = ctx_p15["db"]

    a = _creer_apport_api(client, tok, pid)
    row = db.get(ApportDwf, a["id"])
    stamp_avant = (row.gpkg_version_id, row.gpkg_sha256)

    r1 = _get_reconcilier(client, tok, pid)
    r2 = _get_reconcilier(client, tok, pid)
    assert r1 == r2
    db.refresh(row)
    assert (row.gpkg_version_id, row.gpkg_sha256) == stamp_avant
    assert row.actif is True


def test_reconcilier_coherence_avec_rejet_reel(ctx_p15):
    """Tout apport signalé incompatible est effectivement rejeté par
    preparer_apports_pour_simulation ; une fois réconcilié, le jeu passe."""
    client = TestClient(app)
    tok = _h(ctx_p15["token"])
    pid = ctx_p15["proj"].id
    db = ctx_p15["db"]

    ok = _creer_apport_api(client, tok, pid)
    ko = _creer_apport_api(client, tok, pid, node="REG_B2")
    row = db.get(ApportDwf, ko["id"])
    row.gpkg_sha256 = None
    db.commit()

    res = _get_reconcilier(client, tok, pid)
    flagges = {d["apport_id"] for d in res["incompatibles"]}
    assert flagges == {ko["id"]}

    from api.services.gpkg_versions import resoudre_version_pour_simulation
    gpkg_path, vmeta = resoudre_version_pour_simulation(db, ctx_p15["proj"])
    with pytest.raises(ApportsDwfIncompatiblesError) as ei:
        preparer_apports_pour_simulation(
            db, ctx_p15["proj"], dwf_actif=True,
            version_meta=vmeta, gpkg_path=gpkg_path)
    assert [d["apport_id"] for d in ei.value.details] == [ko["id"]]

    rv = client.post(f"/api/v1/apports/{ko['id']}/revalider", headers=tok)
    assert rv.status_code == 200
    # La revalidation a commité dans une session API distincte : expirer
    # le cache d'identité pour forcer la relecture du sha estampillé.
    db.expire_all()
    apports, _ = preparer_apports_pour_simulation(
        db, ctx_p15["proj"], dwf_actif=True,
        version_meta=vmeta, gpkg_path=gpkg_path)
    assert {x["id"] for x in apports} == {ok["id"], ko["id"]}
    res2 = _get_reconcilier(client, tok, pid)
    assert res2["count"] == 0
