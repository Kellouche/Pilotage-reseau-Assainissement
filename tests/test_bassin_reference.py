# -*- coding: utf-8 -*-
"""
Tests de l'étape 3A — référence métier stable des bassins (bassin_ref).

Couvre : résolution par bassin_ref / Cluster.id / exutoire_noeud / nom unique /
nom ambigu / manuel / ordinal legacy / absence de correspondance ;
isolation multi-projets et multi-organisations ; unicité (network_id, bassin_ref) ;
purge scopée par projet ; compatibilité du contrat /run.
"""

import json
import tempfile
import uuid
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from api.database import SessionLocal
from api.models import Organization, Project, Cluster, Regard
from api.services.bassin_reference import resoudre_bassin
from api.routes.clusters import _purger_clusters_du_projet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return uuid.uuid4().hex[:12]


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def deux_projets(db):
    """Deux projets de la MÊME organisation partageant le même exutoire_id,
    + un projet d'une SECONDE organisation avec le même exutoire."""
    suffixe = _uid()
    org1 = Organization(id=f"org1_{suffixe}", name="Org Test 1", slug=f"org1-{suffixe}")
    org2 = Organization(id=f"org2_{suffixe}", name="Org Test 2", slug=f"org2-{suffixe}")
    db.add_all([org1, org2])
    db.flush()

    projA = Project(id=f"projA_{suffixe}", org_id=org1.id, name="Projet A", source_gpkg_key="")
    projB = Project(id=f"projB_{suffixe}", org_id=org1.id, name="Projet B", source_gpkg_key="")
    projC = Project(id=f"projC_{suffixe}", org_id=org2.id, name="Projet C Org2", source_gpkg_key="")
    db.add_all([projA, projB, projC])
    db.flush()

    # Même exutoire_id "999" dans les trois projets (cas exige : collision inter-projets)
    cA = Cluster(nom="Bassin A", exutoire_noeud="999", bassin_ref="exutoire:999",
                 network_id=projA.id, org_id=org1.id)
    cB = Cluster(nom="Bassin B", exutoire_noeud="999", bassin_ref="exutoire:999",
                 network_id=projB.id, org_id=org1.id)
    cC = Cluster(nom="Bassin C Org2", exutoire_noeud="999", bassin_ref="exutoire:999",
                 network_id=projC.id, org_id=org2.id)
    cNom = Cluster(nom="Bassin Unique XYZ", exutoire_noeud="555",
                   bassin_ref="exutoire:555", network_id=projA.id, org_id=org1.id)
    db.add_all([cA, cB, cC, cNom])
    db.commit()

    ids = {
        "org1": org1.id, "org2": org2.id,
        "A": projA.id, "B": projB.id, "C": projC.id,
        "cA": cA.id, "cB": cB.id, "cC": cC.id, "cNom": cNom.id,
        "org1_obj": org1, "org2_obj": org2,
        "A_obj": projA, "B_obj": projB, "C_obj": projC,
    }
    yield ids

    # Nettoyage par IDs (insensible aux suppressions bulk / cascades ORM)
    db.query(Cluster).filter(Cluster.id.in_([ids["cA"], ids["cB"], ids["cC"], ids["cNom"]])).delete(synchronize_session=False)
    db.query(Project).filter(Project.id.in_([ids["A"], ids["B"], ids["C"]])).delete(synchronize_session=False)
    db.query(Organization).filter(Organization.id.in_([ids["org1"], ids["org2"]])).delete(synchronize_session=False)
    db.commit()


# ---------------------------------------------------------------------------
# Résolution par bassin_ref explicite
# ---------------------------------------------------------------------------

def test_resolution_par_bassin_ref(db, deux_projets):
    r = resoudre_bassin(db, deux_projets["A"], "exutoire:999")
    assert r.statut == "RESOLU_ORM"
    assert r.cluster_orm_id == deux_projets["cA"]
    assert r.bassin_ref == "exutoire:999"
    assert r.exutoire_noeud == "999"


def test_bassin_ref_sans_orm_resout_contexte_gpkg(db, deux_projets):
    """exutoire:777 sans ligne ORM → RESOLU_GPKG contextuel, jamais d'association arbitraire."""
    r = resoudre_bassin(db, deux_projets["A"], "exutoire:777")
    assert r.statut == "RESOLU_GPKG"
    assert r.exutoire_noeud == "777"
    assert r.cluster_orm_id is None


# ---------------------------------------------------------------------------
# Résolution par Cluster.id ORM (compat POST /simulations)
# ---------------------------------------------------------------------------

def test_resolution_par_cluster_id_orm(db, deux_projets):
    r = resoudre_bassin(db, deux_projets["A"], deux_projets["cA"])
    assert r.statut == "RESOLU_ORM"
    assert r.source == "cluster_id"
    assert r.bassin_ref == "exutoire:999"


def test_cluster_id_hors_projet_non_resolu(db, deux_projets):
    """Le Cluster.id du projet B ne doit PAS être résolu dans le contexte du projet A."""
    r = resoudre_bassin(db, deux_projets["A"], deux_projets["cB"])
    # id numérique introuvable dans le scope A → tentative ordinal GPKG → NON_TROUVE sans cache
    assert r.statut == "NON_TROUVE"


# ---------------------------------------------------------------------------
# Résolution par exutoire_noeud brut
# ---------------------------------------------------------------------------

def test_resolution_par_exutoire_noeud(db, deux_projets):
    r = resoudre_bassin(db, deux_projets["A"], "555")
    assert r.statut == "RESOLU_ORM"
    assert r.cluster_orm_id == deux_projets["cNom"]
    assert r.bassin_ref == "exutoire:555"


# ---------------------------------------------------------------------------
# Nom unique vs nom ambigu
# ---------------------------------------------------------------------------

def test_nom_unique_resolu(db, deux_projets):
    r = resoudre_bassin(db, deux_projets["A"], "Bassin Unique XYZ")
    assert r.statut == "RESOLU_ORM"
    assert r.source == "nom"
    assert r.cluster_orm_id == deux_projets["cNom"]


def test_nom_ambigu_rejete(db, deux_projets):
    """'Bassin A' n'existe que dans A — mais créons un homonyme dans B pour tester l'ambiguïté."""
    homonyme = Cluster(nom="Bassin A", exutoire_noeud="111",
                       network_id=deux_projets["A"], org_id=deux_projets["org1"])
    db.add(homonyme)
    db.commit()
    try:
        r = resoudre_bassin(db, deux_projets["A"], "Bassin A")
        assert r.statut == "AMBIGU"
        assert "2 clusters" in r.detail
    finally:
        db.delete(db.get(Cluster, homonyme.id))
        db.commit()


# ---------------------------------------------------------------------------
# Isolation multi-projets / multi-organisations (exutoire identique)
# ---------------------------------------------------------------------------

def test_meme_exutoire_deux_projets_meme_org(db, deux_projets):
    """exutoire:999 existe dans A, B (même org) et C (autre org) : chaque scope résout le sien."""
    rA = resoudre_bassin(db, deux_projets["A"], "exutoire:999")
    rB = resoudre_bassin(db, deux_projets["B"], "exutoire:999")
    rC = resoudre_bassin(db, deux_projets["C"], "exutoire:999")
    assert rA.cluster_orm_id == deux_projets["cA"]
    assert rB.cluster_orm_id == deux_projets["cB"]
    assert rC.cluster_orm_id == deux_projets["cC"]
    # et jamais de confusion inter-organisations
    assert rA.cluster_orm_id != rC.cluster_orm_id


# ---------------------------------------------------------------------------
# Ordinal legacy — résolution contextuelle via cache GPKG du projet
# ---------------------------------------------------------------------------

def test_ordinal_legacy_resolu_via_cache_gpkg(db, deux_projets, tmp_path):
    """cluster_id=3 (ordinal) → cache GPKG du projet → exutoire 999 → Cluster ORM."""
    gpkg = tmp_path / "proj_a.gpkg"
    gpkg.write_bytes(b"gpkg")
    cache = tmp_path / "proj_a.clusters_cache.json"
    cache.write_text(json.dumps({
        "bassins_geojson": {"features": [{
            "type": "Feature",
            "properties": {
                "type": "bassin_urbain", "cluster_id": 3, "id_bassin": 3,
                "exutoire_id": "999", "nom": "Bassin A",
            },
            "geometry": None,
        }]}
    }), encoding="utf-8")

    r = resoudre_bassin(db, deux_projets["A"], 3, gpkg_path=gpkg)
    assert r.statut == "RESOLU_ORM"
    assert r.source == "ordinal"
    assert r.cluster_orm_id == deux_projets["cA"]
    assert r.exutoire_noeud == "999"


def test_ordinal_hors_contexte_rejete(db, deux_projets, tmp_path):
    """Un ordinal qui n'existe pas dans le cache du projet courant → NON_TROUVE."""
    gpkg = tmp_path / "proj_a.gpkg"
    gpkg.write_bytes(b"gpkg")
    (tmp_path / "proj_a.clusters_cache.json").write_text(json.dumps({
        "bassins_geojson": {"features": [{
            "type": "Feature",
            "properties": {"type": "bassin_urbain", "cluster_id": 1,
                           "exutoire_id": "999", "nom": "Bassin A"},
            "geometry": None,
        }]}
    }), encoding="utf-8")
    r = resoudre_bassin(db, deux_projets["A"], 42, gpkg_path=gpkg)
    assert r.statut == "NON_TROUVE"


# ---------------------------------------------------------------------------
# Absence de correspondance
# ---------------------------------------------------------------------------

def test_absence_correspondance(db, deux_projets):
    r = resoudre_bassin(db, deux_projets["A"], "exutoire:inexistant_zzz")
    # exutoire:inexistant_zzz → préfixe exutoire, pas d'ORM → RESOLU_GPKG contextuel
    assert r.statut == "RESOLU_GPKG"
    r2 = resoudre_bassin(db, deux_projets["A"], "Nom Qui N Existe Pas")
    assert r2.statut == "NON_TROUVE"
    r3 = resoudre_bassin(db, deux_projets["A"], "")
    assert r3.statut == "NON_TROUVE"
    r4 = resoudre_bassin(db, deux_projets["A"], None)
    assert r4.statut == "NON_TROUVE"


# ---------------------------------------------------------------------------
# Bassins manuels M_x — contexte uniquement, jamais persistés
# ---------------------------------------------------------------------------

def test_bassin_manuel_resolu_contexte_seulement(db, deux_projets, monkeypatch):
    import src.infrastructure.persistance_manuelle as pm
    monkeypatch.setattr(pm, "charger_bassins_manuels", lambda: [
        {"id": 7, "nom": "Bassin Manuel Test", "conduits": ["T1"]}
    ])
    r = resoudre_bassin(db, deux_projets["A"], "manuel:M_7")
    assert r.statut == "RESOLU_MANUEL"
    # l'identifiant transmis au moteur reste M_7 (contexte), pas de ligne ORM créée
    assert r.cluster_id_moteur == "M_7"
    assert r.cluster_orm_id is None
    # aucun Cluster ORM ne doit exister pour ce bassin manuel
    nb = db.query(Cluster).filter(Cluster.bassin_ref == "manuel:M_7").count()
    assert nb == 0


def test_bassin_manuel_inconnu(db, deux_projets, monkeypatch):
    import src.infrastructure.persistance_manuelle as pm
    monkeypatch.setattr(pm, "charger_bassins_manuels", lambda: [])
    r = resoudre_bassin(db, deux_projets["A"], "manuel:M_99")
    assert r.statut == "NON_TROUVE"


# ---------------------------------------------------------------------------
# Unicité (network_id, bassin_ref) — et NULL exclus
# ---------------------------------------------------------------------------

def test_unicite_network_bassin_ref(db, deux_projets):
    """Deux clusters du MÊME projet ne peuvent partager le même bassin_ref."""
    dup = Cluster(nom="Doublon", exutoire_noeud="999", bassin_ref="exutoire:999",
                  network_id=deux_projets["A"], org_id=deux_projets["org1"])
    db.add(dup)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_bassin_ref_null_autorise_plusieurs(db, deux_projets):
    """Les valeurs NULL sont exclues de l'unicité : plusieurs clusters sans ref coexistent."""
    n1 = Cluster(nom="Sans ref 1", network_id=deux_projets["A"], org_id=deux_projets["org1"])
    n2 = Cluster(nom="Sans ref 2", network_id=deux_projets["A"], org_id=deux_projets["org1"])
    db.add_all([n1, n2])
    db.commit()
    try:
        assert n1.id and n2.id and n1.id != n2.id
    finally:
        db.delete(db.get(Cluster, n1.id))
        db.delete(db.get(Cluster, n2.id))
        db.commit()


# ---------------------------------------------------------------------------
# Purge scopée — recalcul projet A préserve projet B
# ---------------------------------------------------------------------------

def test_purge_projet_a_preserve_projet_b(db, deux_projets):
    """_purger_clusters_du_projet(A) ne doit ni supprimer ni modifier les clusters de B."""
    # Élément rattaché au projet B (ne doit pas être détaché)
    regard_b = Regard(code=f"R-B-{_uid()}", network_id=deux_projets["B"],
                      cluster_id=deux_projets["cB"])
    db.add(regard_b)
    db.commit()
    regard_code = regard_b.code

    _purger_clusters_du_projet(db, deux_projets["A"])
    db.expunge_all()

    def _existe(cid):
        return db.query(Cluster).filter(Cluster.id == cid).count() == 1

    # Cluster de B toujours présent
    assert _existe(deux_projets["cB"])
    # Cluster de C (autre org) toujours présent
    assert _existe(deux_projets["cC"])
    # Cluster de A supprimé
    assert not _existe(deux_projets["cA"])
    assert not _existe(deux_projets["cNom"])
    # Regard de B conserve son cluster_id
    r_b = db.query(Regard).filter(Regard.code == regard_code).first()
    assert r_b is not None and r_b.cluster_id == deux_projets["cB"]

    db.delete(r_b)
    db.commit()


def test_purge_sans_projet_ne_touche_que_legacy(db, deux_projets):
    """Sans network_id résolu : seuls les clusters sans network_id sont purgés."""
    legacy = Cluster(nom="Legacy NULL", network_id=None, org_id=None)
    db.add(legacy)
    db.commit()
    legacy_id = legacy.id
    try:
        _purger_clusters_du_projet(db, None)
        db.expunge_all()

        def _existe(cid):
            return db.query(Cluster).filter(Cluster.id == cid).count() == 1

        assert not _existe(legacy_id)
        assert _existe(deux_projets["cA"])
        assert _existe(deux_projets["cB"])
    finally:
        db.query(Cluster).filter(Cluster.id == legacy_id).delete(synchronize_session=False)
        db.commit()


# ---------------------------------------------------------------------------
# Compatibilité contrat /run — SimulationRunRequest accepte bassin_ref
# ---------------------------------------------------------------------------

def test_simulation_run_request_accepte_bassin_ref():
    from api.routes.simulations import SimulationRunRequest
    p = SimulationRunRequest(scenario_key="pluie_decennale", bassin_ref="exutoire:999")
    assert p.bassin_ref == "exutoire:999"
    assert p.cluster_id is None
    # rétrocompatibilité : cluster_id seul reste valide
    p2 = SimulationRunRequest(scenario_key="pluie_decennale", cluster_id=3)
    assert p2.cluster_id == 3 and p2.bassin_ref is None


def test_cle_cache_inclut_bassin_ref_sans_casser_legacy(tmp_path):
    """bassin_ref entre dans l'empreinte seulement si fourni ; sinon hash inchangé."""
    from types import SimpleNamespace
    from api.services import simulation_service as svc
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "r.gpkg"
        f.write_bytes(b"x")
        base = dict(scenario_key="s", duree_heures=None, pas_routage_sec=5, cluster_id=1,
                    pente_moyenne_pct=1.0, buffer_m=35.0, valider_raccordement=True,
                    typologie_sol="t", imperv_pct=None, intensite_max_mmh=None,
                    station_id="st", raccordements_orphelins=None, force_recalculate=False,
                    bms_mode=False, bms_vigilance="o", bms_cumul_mm=30.0,
                    bms_heure_debut="07:00", bms_heure_fin="21:00", bms_duree_heures=None,
                    bms_profil="cloche")
        h1, d1 = svc.generer_cle_cache_simulation(f, SimpleNamespace(**base))
        assert "bassin_ref" not in d1
        p2 = SimpleNamespace(**{**base, "bassin_ref": "exutoire:999"})
        h2, d2 = svc.generer_cle_cache_simulation(f, p2)
        assert d2["bassin_ref"] == "exutoire:999"
        assert h1 != h2
        # deux refs différentes → empreintes différentes
        p3 = SimpleNamespace(**{**base, "bassin_ref": "exutoire:555"})
        h3, _ = svc.generer_cle_cache_simulation(f, p3)
        assert h3 != h2
