# -*- coding: utf-8 -*-
"""
Tests unitaires et hydrauliques pour la prise en charge du colmatage
et du vieillissement dans les simulations SWMM 5.2.
"""

import os
import tempfile
from pyswmm import Simulation

from src.domain.moteur_swmm.etat_reseau import (
    normaliser_etat_reseau,
    est_etat_nominal,
    extraire_depot_sig_pct,
    appliquer_etat_conduite,
)


def test_etat_nominal_invariant():
    """En état nominal, aucun paramètre géométrique ou de rugosité n'est altéré."""
    etat = normaliser_etat_reseau(None)
    assert est_etat_nominal(etat) is True

    shape, g1, g2, sed, rough, info = appliquer_etat_conduite(
        row={"NIV_DEPOT": "50"},
        diam_m=0.6,
        shape="CIRCULAR",
        geom1=0.6,
        geom2=0.0,
        rough_base=0.013,
        pente_conduite_pct=0.2,
        etat_norm=etat,
    )
    assert shape == "CIRCULAR"
    assert g1 == 0.6
    assert g2 == 0.0
    assert sed == 0.0
    assert rough == 0.013
    assert info["colmate"] is False


def test_ciblage_faibles_pentes_vs_tout_reseau():
    """Le ciblage faibles_pentes n'affecte que les conduites sous le seuil de pente."""
    etat = normaliser_etat_reseau({
        "scenario_nom": "exploite",
        "colmatage_pct": 20.0,
        "facteur_vieillissement": 1.25,
        "cible_colmatage": "faibles_pentes",
        "seuil_pente_pct": 0.5,
        "appliquer_depots_sig": False,
    })
    assert est_etat_nominal(etat) is False

    # Conduite plate (0.2% <= 0.5%) -> colmatée (FILLED_CIRCULAR)
    shape_p, g1_p, g2_p, sed_p, rough_p, info_p = appliquer_etat_conduite(
        row={},
        diam_m=1.0,
        shape="CIRCULAR",
        geom1=1.0,
        geom2=0.0,
        rough_base=0.013,
        pente_conduite_pct=0.2,
        etat_norm=etat,
    )
    assert shape_p == "FILLED_CIRCULAR"
    assert g1_p == 1.0
    assert g2_p == 0.2
    assert sed_p == 0.2
    assert rough_p > 0.013 * 1.25
    assert info_p["colmate"] is True

    # Conduite pentue (2.0% > 0.5%) -> auto-curée (pas de dépôt, seul vieillissement n)
    shape_s, g1_s, g2_s, sed_s, rough_s, info_s = appliquer_etat_conduite(
        row={},
        diam_m=1.0,
        shape="CIRCULAR",
        geom1=1.0,
        geom2=0.0,
        rough_base=0.013,
        pente_conduite_pct=2.0,
        etat_norm=etat,
    )
    assert shape_s == "CIRCULAR"
    assert sed_s == 0.0
    assert rough_s == round(0.013 * 1.25, 4)
    assert info_s["colmate"] is False


def test_extraction_depot_sig_niv_depot():
    """Interprétation prudente des valeurs hétérogènes de NIV_DEPOT (% vs mm)."""
    assert extraire_depot_sig_pct({"NIV_DEPOT": "30"}, diam_mm=600) == 30.0
    assert extraire_depot_sig_pct({"NIV_DEPOT": "100%"}, diam_mm=600) == 90.0  # plafonné à 90%
    assert extraire_depot_sig_pct({"NIV_DEPOT": "200"}, diam_mm=1000) == 20.0  # 200 mm / 1000 mm = 20%
    assert extraire_depot_sig_pct({"NIV_DEPOT": None}, diam_mm=600) is None


def test_swmm_execution_filled_circular():
    """Vérifie que SWMM 5.2 simule sans erreur une conduite colmatée FILLED_CIRCULAR."""
    inp = (
        "[TITLE]\nTest Colmatage\n"
        "[OPTIONS]\nFLOW_UNITS CMS\nFLOW_ROUTING DYNWAVE\n"
        "START_DATE 01/01/2026\nSTART_TIME 00:00:00\n"
        "END_DATE 01/01/2026\nEND_TIME 01:00:00\nROUTING_STEP 0:00:05\n"
        "[JUNCTIONS]\nJ1 10.0 2.0 0 0 0\n"
        "[OUTFALLS]\nO1 9.0 FREE NO\n"
        "[CONDUITS]\nC1 J1 O1 100.0 0.0160 0 0 0 0\n"
        "[XSECTIONS]\nC1 FILLED_CIRCULAR 1.000 0.250 0.000 0.000 1\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".inp", delete=False) as f:
        f.write(inp)
        fname = f.name
    try:
        with Simulation(fname) as sim:
            for _ in sim:
                pass
    finally:
        for ext in [".inp", ".rpt", ".out"]:
            p = fname.replace(".inp", ext)
            if os.path.exists(p):
                os.remove(p)
