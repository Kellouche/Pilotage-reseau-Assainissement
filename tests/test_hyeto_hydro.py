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
