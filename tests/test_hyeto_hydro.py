# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Tests Hyétogramme ↔ Hydrogramme (Format A)
Auteur : Dr Abdelhakim KELLOUCHE
Date : 2026-11-09
Objet : Vérification de l'extraction des données couplées pluie-débit et de l'UI
================================================================================
"""

import os
from pathlib import Path
import pytest


def test_hyeto_hydro_template_and_js_integrity():
    """Vérifie la présence et la structure du template HTML et du script JS."""
    template_path = Path("templates/partials/panel_hyeto_hydro.html")
    assert template_path.exists(), "Le template panel_hyeto_hydro.html doit exister."
    content = template_path.read_text(encoding="utf-8")
    assert "panel-hyeto-hydro" in content
    assert "canvas-hyeto-hydro" in content
    assert "badge-hyeto-rain" in content
    assert "badge-hyeto-flow" in content
    assert "badge-hyeto-lag" in content

    js_path = Path("static/js/app/hyeto_hydro.js")
    assert js_path.exists(), "Le script static/js/app/hyeto_hydro.js doit exister."
    js_content = js_path.read_text(encoding="utf-8")
    assert "toggleHyetoHydroPanel" in js_content
    assert "ouvrirHyetoHydroPanel" in js_content
    assert "fermerHyetoHydroPanel" in js_content
    assert "hyetoHydroVerticalCursor" in js_content


def test_hyetogram_interpolation_helper():
    """Vérifie l'algorithme d'interpolation linéaire de l'hyétogramme."""
    from src.domain.moteur_swmm.timeseries_extractor import _interpoler_pluie

    ts_points = [
        (0, 0.0),
        (30, 20.0),
        (60, 80.0),
        (90, 40.0),
        (120, 0.0)
    ]

    # Avant le premier point
    assert _interpoler_pluie(ts_points, 0) == 0.0
    # Exactement au pic
    assert _interpoler_pluie(ts_points, 60) == 80.0
    # Interpolation à mi-chemin (entre 0 et 30 min -> 10.0)
    assert _interpoler_pluie(ts_points, 15) == 10.0
    # Interpolation à mi-chemin (entre 30 et 60 min -> 50.0)
    assert _interpoler_pluie(ts_points, 45) == 50.0
    # Après le dernier point
    assert _interpoler_pluie(ts_points, 180) == 0.0


def test_hyeto_hydro_extraction_from_inp_sample(tmp_path):
    """Vérifie l'extraction des données pluie et surface depuis un .inp synthétique."""
    from src.domain.moteur_swmm.timeseries_extractor import (
        _extraire_hyetogramme_depuis_inp,
        _extraire_surface_totale_inp
    )

    inp_file = tmp_path / "test_sample.inp"
    inp_content = """
[SUBCATCHMENTS]
;;Name           Rain Gage        Outlet           Area     %Imperv  Width    %Slope
SB_1             RG1              1                2.5      70       100      0.5
SB_2             RG1              2                3.8      60       120      0.5

[TIMESERIES]
;;Name           Date       Time       Value
TS_SCENARIO                 00:00      0.00
TS_SCENARIO                 00:30      25.00
TS_SCENARIO                 01:00      75.00
TS_SCENARIO                 01:30      30.00
TS_SCENARIO                 02:00      0.00
"""
    inp_file.write_text(inp_content, encoding="utf-8")

    ts = _extraire_hyetogramme_depuis_inp(str(inp_file))
    assert len(ts) == 5
    assert ts[0] == (0, 0.0)
    assert ts[2] == (60, 75.0)

    area = _extraire_surface_totale_inp(str(inp_file))
    assert area == 6.3


def test_enrichir_timeseries_pluie_fallback():
    """Vérifie l'enrichissement automatique de la pluie sur un timeseries sans rainfall_series."""
    from src.domain.moteur_swmm.timeseries_extractor import enrichir_timeseries_pluie

    raw_ts = {
        "status": "SUCCESS",
        "duration_hours": 4.0,
        "steps": [
            {"step_index": 0, "minute": 0, "time_str": "00:00", "outflow_m3s": 0.0},
            {"step_index": 1, "minute": 30, "time_str": "00:30", "outflow_m3s": 0.25},
            {"step_index": 2, "minute": 60, "time_str": "01:00", "outflow_m3s": 1.80},
            {"step_index": 3, "minute": 64, "time_str": "01:04", "outflow_m3s": 2.23},
            {"step_index": 4, "minute": 90, "time_str": "01:30", "outflow_m3s": 0.90},
            {"step_index": 5, "minute": 240, "time_str": "04:00", "outflow_m3s": 0.0}
        ]
    }
    sim_data = {
        "meta": {
            "pluvio_scenario_key": "pluie_decennale",
            "pluvio_intensite_max_mmh": 74.9,
            "total_area_ha": 50.0,
            "pluvio_hauteur_totale_mm": 56.0
        }
    }

    enriched = enrichir_timeseries_pluie(raw_ts, sim_data)
    assert "rainfall_series" in enriched
    assert len(enriched["rainfall_series"]) == 6
    assert enriched["peak_rainfall_mmh"] == 74.9
    assert enriched["peak_rainfall_time"] == "01:00"
    assert enriched["lag_time_minutes"] == 4  # 64 min - 60 min
    assert enriched["total_rain_volume_m3"] > 0
    assert enriched["total_outflow_volume_m3"] > 0
    assert 0.0 <= enriched["runoff_coefficient"] <= 1.0


