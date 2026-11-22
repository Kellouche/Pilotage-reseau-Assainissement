# -*- coding: utf-8 -*-
"""
Tests unitaires pour le module d'audit des exclusions et bilan de réconciliation 1:1.
"""
import pytest
from src.domain.moteur_swmm.audit_exclusions import RegistreExclusions, generer_bilan_reconciliation

def test_registre_exclusions():
    reg = RegistreExclusions()
    reg.ajouter_exclusion(
        objet_id="C_DESAFF_1",
        type_objet="Canalisation",
        motif="desaffecte",
        detail="Canalisation marquée désaffectée dans le SIG",
        attributs={"MATERIAU": "Béton"}
    )
    reg.ajouter_exclusion(
        objet_id="C_ORPH_1",
        type_objet="Canalisation",
        motif="orphelin",
        detail="Tronçon isolé sans raccordement possible",
    )
    
    synthese = reg.obtenir_synthese()
    assert synthese["total_exclusions"] == 2
    assert synthese["par_motif"]["desaffecte"] == 1
    assert synthese["par_motif"]["orphelin"] == 1
    assert synthese["par_type"]["Canalisation"] == 2


def test_generer_bilan_reconciliation():
    gpkg_counts = {
        "canalisations_gravitaires": 100,
        "canalisations_refoulement": 2,
        "regards": 120,
        "rejets": 2,
        "stations_relevage": 1,
        "deversoirs_orage": 1,
        "repartition_materiaux": {"Béton": 80, "PEHD": 20},
        "repartition_formes": {"Circulaire": 95, "Rectangulaire": 5},
    }
    inp_counts = {
        "canalisations_gravitaires": 100,
        "canalisations_refoulement": 2,
        "regards": 120,
        "rejets": 2,
        "stations_relevage": 1,
        "deversoirs_orage": 1,
    }
    sections_presents = {"TITLE", "OPTIONS", "JUNCTIONS", "CONDUITS", "XSECTIONS", "PUMPS", "WEIRS", "OUTFALLS"}
    
    bilan = generer_bilan_reconciliation(
        gpkg_counts=gpkg_counts,
        inp_counts=inp_counts,
        exclusions=[],
        sections_inp_presents=sections_presents,
    )
    
    assert bilan["statut_global"] == "RÉCONCILIÉ"
    assert len(bilan["comparatif_composants"]) == 7
    # Vérifier matrice sections
    sections_map = {s["section"]: s["statut"] for s in bilan["matrice_sections_swmm"]}
    assert sections_map["CONDUITS"] == "ALIMENTÉE"
    assert sections_map["PUMPS"] == "ALIMENTÉE"
    assert sections_map["WEIRS"] == "ALIMENTÉE"
    assert sections_map["POLLUTANTS"] == "NON_APPLICABLE"


def test_endpoint_reconciliation_404_quand_pas_de_simulation():
    from fastapi.testclient import TestClient
    from api.main import app
    client = TestClient(app)
    # Sans simulation, doit retourner 404
    resp = client.get("/api/simulations/reconciliation?cluster_id=9999")
    assert resp.status_code in (401, 403, 404)
