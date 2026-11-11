# -*- coding: utf-8 -*-
"""
Tests de traçabilité scientifique : bloc `provenance` des simulations SWMM.
Vérifie que tout résultat issu du vrai moteur EPA SWMM est identifiable
(moteur, versions, empreinte INP, horodatage, mode d'exécution).
"""

import hashlib
from datetime import datetime
from pathlib import Path

import pytest

from src.domain.moteur_swmm.moteur import (
    MoteurSWMM,
    construire_provenance_simulation,
    _extraire_version_moteur_swmm,
)


RPT_ECHANTILLON = """EPA STORM WATER MANAGEMENT MODEL - VERSION 5.2.4
BUILD 5.2.4.5
--------------------------------------------------------------
"""


def test_extraire_version_moteur_depuis_rpt():
    assert _extraire_version_moteur_swmm(RPT_ECHANTILLON) == "5.2.4"


def test_extraire_version_moteur_rpt_vide():
    assert _extraire_version_moteur_swmm("") == "inconnu"
    assert _extraire_version_moteur_swmm("pas un rapport swmm") == "inconnu"


def test_construire_provenance_champs_obligatoires():
    inp = "[TITLE]\ntest\n[END]\n"
    prov = construire_provenance_simulation(inp, RPT_ECHANTILLON, execution_mode="celery")

    assert prov["nature"] == "REAL"
    assert prov["engine"] == "EPA SWMM"
    assert prov["engine_version"] == "5.2.4"
    assert prov["execution_mode"] == "celery"
    assert prov["inp_sha256"] == hashlib.sha256(inp.encode("utf-8")).hexdigest()
    assert prov["inp_size_bytes"] == len(inp.encode("utf-8"))
    # Versions installées réellement (pyswmm présent dans l'environnement de test)
    assert prov["pyswmm_version"] not in (None, "")
    assert prov["swmm_toolkit_version"] not in (None, "")
    # Horodatage ISO 8601 valide
    datetime.fromisoformat(prov["executed_at_utc"])


def test_construire_provenance_sans_rpt():
    prov = construire_provenance_simulation("[TITLE]\nx\n", "", execution_mode="sync")
    assert prov["engine_version"] == "inconnu"
    assert prov["nature"] == "REAL"


@pytest.mark.parametrize("mode", ["sync", "celery"])
def test_mode_execution_propage(mode):
    prov = construire_provenance_simulation("x", RPT_ECHANTILLON, execution_mode=mode)
    assert prov["execution_mode"] == mode


# ---------------------------------------------------------------------------
# Test d'intégration : executer_simulation attache la provenance au résultat
# ---------------------------------------------------------------------------

GPKG_TEST = Path("uploads/a66e32ad-f32b-4529-acc3-7a6026eb5a8a/network_Assainissement_Ville.gpkg")


@pytest.mark.skipif(not GPKG_TEST.exists(), reason="GeoPackage de test non présent")
def test_executer_simulation_attache_provenance():
    moteur = MoteurSWMM()
    res = moteur.executer_simulation(
        gpkg_path=GPKG_TEST,
        scenario_key="decennale_chlef_orage",
        cluster_id="25_ouvrages_speciaux_348883",
        pente_moyenne_pct=1.0,
        raccordements_orphelins=[],
        execution_mode="sync",
    )

    assert res["status"] == "SUCCESS"
    prov = res.get("provenance")
    assert prov is not None, "Le résultat doit contenir le bloc provenance"
    assert prov["nature"] == "REAL"
    assert prov["engine"] == "EPA SWMM"
    assert prov["engine_version"] != "inconnu"
    assert prov["execution_mode"] == "sync"
    # L'empreinte INP doit correspondre au contenu INP embarqué dans le résultat
    assert prov["inp_sha256"] == hashlib.sha256(
        res["inp_content"].encode("utf-8")
    ).hexdigest()
    datetime.fromisoformat(prov["executed_at_utc"])


@pytest.mark.skipif(not GPKG_TEST.exists(), reason="GeoPackage de test non présent")
def test_executer_simulation_provenance_mode_celery():
    moteur = MoteurSWMM()
    res = moteur.executer_simulation(
        gpkg_path=GPKG_TEST,
        scenario_key="decennale_chlef_orage",
        cluster_id="25_ouvrages_speciaux_348883",
        pente_moyenne_pct=1.0,
        raccordements_orphelins=[],
        execution_mode="celery",
    )
    assert res["provenance"]["execution_mode"] == "celery"
    assert res["provenance"]["nature"] == "REAL"
