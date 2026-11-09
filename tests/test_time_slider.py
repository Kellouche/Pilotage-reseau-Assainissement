# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-09
Objet : Tests unitaires et d'intégration pour le Time Slider (Phase 6.B)
================================================================================
"""

import os
os.environ["TESTING"] = "true"

import pytest
from fastapi import HTTPException
from api.database import SessionLocal
from src.domain.moteur_swmm.timeseries_extractor import extraire_series_temporelles
from src.domain.moteur_swmm.execution_solver import executer_solver_swmm
from api.routes.simulations import get_simulation_timeseries, _DERNIERE_SIMULATION
from api.routes import simulations


def test_extraire_series_temporelles_fichier_inexistant():
    """Vérifie le comportement gracieux si le fichier .out n'existe pas."""
    res = extraire_series_temporelles("non_existent_file.out")
    assert res["status"] == "NO_DATA"
    assert res["steps"] == []


def test_executer_solver_swmm_retrocompatibilite():
    """Vérifie que executer_solver_swmm sans argument renvoie bien un tuple de 2 éléments."""
    inp = """[TITLE]
Test SWMM
[OPTIONS]
FLOW_UNITS CFS
INFILTRATION HORTON
FLOW_ROUTING KINWAVE
START_DATE 01/01/2026
START_TIME 00:00:00
END_DATE 01/01/2026
END_TIME 00:05:00
REPORT_STEP 00:01:00
[JUNCTIONS]
J1 10 0 0 0 0
J2 9 0 0 0 0
[OUTFALLS]
OUT1 8 FREE NO
[CONDUITS]
C1 J1 J2 100 0.01 0 0 0 0
C2 J2 OUT1 100 0.01 0 0 0 0
[XSECTIONS]
C1 CIRCULAR 1 0 0 0 1
C2 CIRCULAR 1 0 0 0 1
[REPORT]
INPUT NO
CONTROLS NO
SUBCATCHMENTS ALL
NODES ALL
LINKS ALL
"""
    # Appel classique (2 valeurs)
    ret = executer_solver_swmm(inp, return_timeseries=False)
    assert isinstance(ret, tuple)
    assert len(ret) == 2
    rpt_text, tmp_inp = ret
    assert isinstance(rpt_text, str)

    # Appel avec return_timeseries=True (3 valeurs)
    ret_ts = executer_solver_swmm(inp, return_timeseries=True)
    assert isinstance(ret_ts, tuple)
    assert len(ret_ts) == 3
    rpt_text2, tmp_inp2, ts_data = ret_ts
    assert isinstance(ts_data, dict)
    assert "steps" in ts_data
    assert ts_data["status"] == "SUCCESS"


def test_endpoint_timeseries_sans_simulation():
    """Vérifie que get_simulation_timeseries lève une 404 pédagogique si aucune simulation active."""
    old_sim = simulations._DERNIERE_SIMULATION
    simulations._DERNIERE_SIMULATION = {}
    db = SessionLocal()
    try:
        with pytest.raises(HTTPException) as exc_info:
            get_simulation_timeseries(db=db, tenant=None)
        assert exc_info.value.status_code == 404
        assert "simulation" in exc_info.value.detail.lower()
    finally:
        db.close()
        simulations._DERNIERE_SIMULATION = old_sim


def test_endpoint_timeseries_avec_donnees():
    """Vérifie que get_simulation_timeseries retourne le payload complet lorsque des séries temporelles sont présentes."""
    old_sim = simulations._DERNIERE_SIMULATION
    simulations._DERNIERE_SIMULATION = {
        "status": "SUCCESS",
        "conduit_results": {"C_1": {"flow_ratio": 0.5}},
        "node_results": {"2287": {"status": "normal"}},
        "timeseries": {
            "status": "SUCCESS",
            "duration_hours": 4.0,
            "total_steps": 240,
            "sampled_count": 2,
            "peak_outflow_m3s": 0.45,
            "peak_time": "01:30",
            "time_labels": ["00:00", "01:30"],
            "outflow_series": [0.0, 0.45],
            "steps": [
                {
                    "step_index": 0,
                    "time_str": "00:00",
                    "minute": 0,
                    "outflow_m3s": 0.0,
                    "surcharged_pipes_count": 0,
                    "flooded_nodes_count": 0,
                    "flooded_nodes": [],
                    "links": {}
                },
                {
                    "step_index": 1,
                    "time_str": "01:30",
                    "minute": 90,
                    "outflow_m3s": 0.45,
                    "surcharged_pipes_count": 5,
                    "flooded_nodes_count": 1,
                    "flooded_nodes": ["2287"],
                    "links": {"C_1": 0.85}
                }
            ]
        }
    }
    db = SessionLocal()
    try:
        data = get_simulation_timeseries(db=db, tenant=None)
        assert data["status"] == "SUCCESS"
        assert len(data["steps"]) == 2
        assert data["peak_outflow_m3s"] == 0.45
        assert "2287" in data["steps"][1]["flooded_nodes"]
    finally:
        db.close()
        simulations._DERNIERE_SIMULATION = old_sim
