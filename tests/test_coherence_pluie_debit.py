# -*- coding: utf-8 -*-
"""
Test de non-régression : Cohérence Pluie-Débit et parsing de l'Outfall Loading Summary
Vérifie que :
1. L'analyse du rapport officiel SWMM extrait fidèlement les débits de pointe des exutoires
   et du système (System), sans être tronqué par les en-têtes de colonnes (ex: 'Outfall Node').
2. Le débit simulé dans kpis['coherence_pluie_debit'] n'est jamais 0.0 quand le réseau débite.
3. Le ratio rationnel Q_sim / Q_rat et les messages associés sont fidèles et hydrauliquement justes.
"""

from src.domain.moteur_swmm.analyse_rapport import analyser_rapport_swmm_impl, calculer_coherence_pluie_debit
from api.services.simulation_service import corriger_pic_depuis_timeseries


RPT_OUTFALL_SAMPLE = """
  EPA STATISTICAL WATER MANAGEMENT MODEL - VERSION 5.2.4
  ------------------------------------------------------

  ***********************
  Outfall Loading Summary
  ***********************

  -----------------------------------------------------------
                         Flow       Avg       Max       Total
                         Freq      Flow      Flow      Volume
  Outfall Node           Pcnt       CMS       CMS    10^6 ltr
  -----------------------------------------------------------
  OUT_31259             98.50     0.014     0.082       0.121
  OUT_orph_rejet_44     96.01     0.067     0.506       0.549
  OUT_orph_rejet_50     97.99     0.007     0.038       0.057
  OUT_BND_3676          98.55     0.234     1.199       1.978
  -----------------------------------------------------------
  System                97.76     0.322     1.798       2.704


  ********************
  Link Flow Summary
  ********************
"""


def test_outfall_loading_summary_and_system_peak():
    meta = {
        "outfall_code": "OUT_31259",
        "junction_outfall_code": "31259",
        "total_area_ha": 107.34,
        "pluvio_intensite_max_mmh": 74.9,
    }

    kpis = analyser_rapport_swmm_impl(RPT_OUTFALL_SAMPLE, meta)

    # 1. Pic système
    assert kpis["peak_outflow_m3s"] == 1.798
    assert "OUT_31259" in kpis.get("outfall_loading_summary", {})
    assert kpis["outfall_loading_summary"]["OUT_31259"]["max_cms"] == 0.082

    # 2. Cohérence rationnelle
    coh = kpis["coherence_pluie_debit"]
    assert coh["q_simule_m3s"] == 1.798
    assert coh["q_rationnel_m3s"] > 10.0
    assert coh["ratio"] > 0
    assert coh["statut"] == "AMORTI"
    assert "1.798 m³/s" in coh["message"]


def test_corriger_pic_depuis_timeseries_synchronisation():
    resultat = {
        "peak_outflow_m3s": 0.0,
        "effective_runoff_coeff": 0.70,
        "meta": {
            "total_area_ha": 50.0,
            "pluvio_intensite_max_mmh": 60.0
        },
        "timeseries": {
            "status": "SUCCESS",
            "peak_outflow_m3s": 2.50,
            "peak_time": "01:15"
        }
    }

    corrige = corriger_pic_depuis_timeseries(resultat)
    assert corrige["peak_outflow_m3s"] == 2.50
    assert "coherence_pluie_debit" in corrige
    assert corrige["coherence_pluie_debit"]["q_simule_m3s"] == 2.50
    assert corrige["coherence_pluie_debit"]["ratio"] > 0
