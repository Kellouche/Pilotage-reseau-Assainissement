# -*- coding: utf-8 -*-
"""
Test de validation : Renseignement complet des cotes (Tampon TN, Radier, Cote d'eau max, Charge)
dans les détails des regards de visite pour la modale de résultats SWMM 5.2.
"""

import pytest
from src.domain.moteur_swmm.analyse_rapport import (
    analyser_rapport_swmm_impl,
    extraire_cotes_noeuds_inp,
    enrichir_node_results_cotes_inp,
)

INP_EXEMPLE = """
[TITLE]
Reseau Test

[JUNCTIONS]
;;Name           Elevation  MaxDepth   InitDepth  SurDepth   Aponded
7018             104.70     2.00       0.0        0.0        0.0
7019             105.23     2.00       0.0        0.0        0.0
7020             105.68     2.00       0.0        0.0        0.0

[OUTFALLS]
;;Name           Elevation  Type       Stage Data       Gated    Route To
Out1             100.00     FREE                        NO
"""

RPT_EXEMPLE = """
  Node Surcharge Summary
  **********************
  Node                 Type       Hours   Avg. Height   Max. Height   Min. Depth
                                                Above Crown     Below Rim
  7018                 JUNCTION     0.09       1.500         1.500        0.000
  7019                 JUNCTION     0.07       1.500         1.500        0.000

  Node Flooding Summary
  *********************
  Node                 Flooded       CMS   days hr:min    10^6 ltr    Meters
  --------------------------------------------------------------------------
  7018                    0.01     0.067      0  01:05       0.000     0.000

  Node Depth Summary
  ******************
  Node                 Type       Meters   Meters   Meters  days hr:min      Meters
  ---------------------------------------------------------------------------------
  7018                 JUNCTION     0.47     2.00   106.70     0  01:05        0.90
  7019                 JUNCTION     0.44     1.80   107.03     0  01:05        0.87
  7020                 JUNCTION     0.40     1.20   106.88     0  01:05        0.76
"""


def test_extraire_cotes_noeuds_inp():
    """Vérifie l'extraction des cotes radier et tampon depuis le fichier INP."""
    cotes = extraire_cotes_noeuds_inp(INP_EXEMPLE)
    assert "7018" in cotes
    assert cotes["7018"]["invert_elev"] == 104.70
    assert cotes["7018"]["rim_elev"] == pytest.approx(106.70)
    assert cotes["7018"]["max_depth_structure"] == 2.00

    assert "Out1" in cotes
    assert cotes["Out1"]["invert_elev"] == 100.00
    assert cotes["Out1"]["rim_elev"] == 100.00


def test_analyser_rapport_et_enrichir_cotes():
    """Vérifie que analyser_rapport_swmm_impl intègre tous les nœuds simulés et leurs cotes complètes."""
    meta = {"inp_content": INP_EXEMPLE}
    kpis = analyser_rapport_swmm_impl(rpt_text=RPT_EXEMPLE, meta=meta)

    node_res = kpis["node_results"]
    assert "7018" in node_res
    assert "7019" in node_res
    assert "7020" in node_res  # Nœud non surchargé ni inondé, mais présent via Node Depth Summary

    # Regard 7018 (Inondé)
    n18 = node_res["7018"]
    assert n18["status"] == "flooded"
    assert n18["invert_elev"] == pytest.approx(104.70)
    assert n18["rim_elev"] == pytest.approx(106.70)
    assert n18["max_head_m"] == pytest.approx(106.70)
    assert n18["max_depth_m"] == pytest.approx(2.00)

    # Regard 7019 (Surchargé)
    n19 = node_res["7019"]
    assert n19["status"] == "surcharged"
    assert n19["invert_elev"] == pytest.approx(105.23)
    assert n19["rim_elev"] == pytest.approx(107.23)
    assert n19["max_head_m"] == pytest.approx(107.03)

    # Regard 7020 (Libre / normal)
    n20 = node_res["7020"]
    assert n20["status"] == "normal"
    assert n20["invert_elev"] == pytest.approx(105.68)
    assert n20["rim_elev"] == pytest.approx(107.68)
    assert n20["max_head_m"] == pytest.approx(106.88)
    assert n20["max_depth_m"] == pytest.approx(1.20)
