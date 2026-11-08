"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Tests des options du bilan hydraulique et formatage monétaire DZD
================================================================================
"""

import pytest
from src.domain.moteur_swmm import MoteurSWMM
from src.domain.agents_expertise import AgentSyntheseExecutive
from api.routes.simulations import _construire_reponse_simulation


def test_moteur_swmm_bilan_hydraulique_options():
    """Vérifie le calcul automatique du bilan de flux et des pourcentages dans le moteur SWMM."""
    moteur = MoteurSWMM()

    # Simulation d'un rapport avec un exutoire et un tronçon de raccordement d'ouvrage spécial
    rpt_sample = """
  *******************************************************************
  *                         EPA SWMM 5.2.4                          *
  *******************************************************************
  
  WARNING 04: minimum elevation drop used for Conduit C1
  
  *************************
  Routing Continuity Errors
  *************************
  Routing Continuity Error ... -0.05 %
  
  ************************
  Runoff Continuity Errors
  ************************
  Runoff Continuity Error ... 0.12 %
  
  ****************************
  Outfall Loading Summary
  ****************************
  Outfall Node       Flow Freq.    Avg Flow    Max Flow    Total Vol
                     %             CMS         CMS         10^6 ltr
  ------------------------------------------------------------------
  OUTFALL_1          95.2          0.820       1.580       12.450
  
  ****************************
  Link Flow Summary
  ****************************
  Link               Type      Max Flow   Time of Max   Max Veloc  Max /    Max /
                               CMS        days hr:min   m/sec      Full Q   Full Depth
  ------------------------------------------------------------------------------------
  C1                 CONDUIT   0.450      0 01:15       0.95       0.75     0.65
  C_RACC_1           CONDUIT   1.325      0 01:20       1.20       0.82     0.70
  
  ****************************
  Node Inflow Summary
  ****************************
  Node               Type        Max Inflow  Total Inflow
                                 CMS         10^6 ltr
  -----------------------------------------------------------
  OUTFALL_1          OUTFALL     1.580       12.450
"""
    meta = {
        "cluster_id": 30,
        "cluster_nom": "30_ouvrages_speciaux_351607",
        "raccordements_orphelins": [{"nom": "Ouvrage 1", "distance_m": 12.0}],
        "bassin_nom": "30_ouvrages_speciaux_351607"
    }

    kpis = moteur._analyser_rapport_swmm(rpt_sample, meta)


    # 1. Vérification des débits individuels et total
    assert kpis["q_exutoire_m3s"] == 1.580
    assert kpis["q_derive_m3s"] == 1.325
    assert kpis["q_genere_m3s"] == round(1.580 + 1.325, 3)  # 2.905 m³/s
    assert kpis["nb_ouvrages_raccordes"] == 1

    # 2. Vérification des pourcentages de répartition
    # 1.325 / 2.905 = ~45.6%
    assert kpis["taux_derive_pct"] == 45.6
    # 100 - 45.6 = 54.4%
    assert kpis["taux_exutoire_pct"] == 54.4
    assert kpis["soulagement_reseau_pct"] == 45.6
    assert kpis["reduction_charge_pct"] == 45.6

    # 3. Vérification du texte décisionnel Option 3 (Option Décideur bonifiée)
    decisionnel = kpis["bilan_hydraulique_decisionnel"]
    assert "Bassin versant : 30_ouvrages_speciaux_351607" in decisionnel
    assert "Débit total généré par le bassin : 2.905 m³/s" in decisionnel
    assert "Soulagement du collecteur principal : 45.6%" in decisionnel
    assert "Débit résiduel vers l'exutoire principal : 1.580 m³/s (54.4%)" in decisionnel
    assert "Débit capté par 1 ouvrages spéciaux mobilisés : 1.325 m³/s (45.6%)" in decisionnel


def test_agent_synthese_executive_option_3():
    """Vérifie que l'Agent 6 (Synthèse Exécutive) intègre correctement le bloc décisionnel Option 3."""
    kpis = {
        "peak_outflow_m3s": 1.580,
        "q_exutoire_m3s": 1.580,
        "q_derive_m3s": 1.325,
        "q_genere_m3s": 2.905,
        "taux_derive_pct": 45.6,
        "taux_exutoire_pct": 54.4,
        "soulagement_reseau_pct": 45.6,
        "reduction_charge_pct": 45.6,
        "nb_ouvrages_raccordes": 4,
        "total_outflow_m3": 12450.0,
        "bilan_hydraulique_decisionnel": (
            "Bassin versant : 30_ouvrages_speciaux_351607\n"
            "• Débit total généré par le bassin : 2.905 m³/s\n"
            "• Soulagement du collecteur principal : 45.6%\n"
            "• Débit résiduel vers l'exutoire principal : 1.580 m³/s (54.4%)\n"
            "• Débit capté par 4 ouvrages spéciaux mobilisés : 1.325 m³/s (45.6%)"
        )
    }
    meta = {
        "cluster_nom": "30_ouvrages_speciaux_351607",
        "scenario": "Pluie Décennale"
    }
    diag = {}
    gc = {"metres_lineaires_totaux": 120.0, "cout_global_estime_dzd": 5000000.0}
    lid = {"volume_tampon_requis_m3": 350.0}
    risques = {"synthese": {"nb_p1_critique": 0, "nb_p2_majeur": 1}}

    agent = AgentSyntheseExecutive()
    synthese = agent.generer_note(kpis, meta, diag, gc, lid, risques)

    assert "bilan_hydraulique" in synthese
    assert "bilan_hydraulique_decisionnel" in synthese
    assert "Bassin versant : 30_ouvrages_speciaux_351607" in synthese["bilan_hydraulique_decisionnel"]

    # Vérification des indicateurs marquants
    im = synthese["indicateurs_marquants"]
    assert im["debit_total_genere_m3s"] == 2.905
    assert im["debit_maintenu_reseau_principal_m3s"] == 1.580
    assert im["debit_devie_ouvrages_speciaux_m3s"] == 1.325
    assert im["taux_reduction_charge_pct"] == 45.6
    assert im["nb_ouvrages_speciaux_actifs"] == 4


def test_api_reponse_simulation_kpis_exposition():
    """Vérifie que la fonction _construire_reponse_simulation expose bien les nouveaux KPIs."""
    resultat = {
        "meta": {"cluster_id": 30},
        "peak_outflow_m3s": 1.580,
        "q_exutoire_m3s": 1.580,
        "q_derive_m3s": 1.325,
        "q_deleste_m3s": 1.325,
        "q_genere_m3s": 2.905,
        "taux_derive_pct": 45.6,
        "taux_exutoire_pct": 54.4,
        "reduction_charge_pct": 45.6,
        "nb_ouvrages_raccordes": 4,
        "bilan_hydraulique_decisionnel": "Bassin versant : Test"
    }

    rep = _construire_reponse_simulation(resultat, cached=False)
    kpis = rep["kpis"]

    assert kpis["q_genere_m3s"] == 2.905
    assert kpis["q_exutoire_m3s"] == 1.580
    assert kpis["q_derive_m3s"] == 1.325
    assert kpis["taux_derive_pct"] == 45.6
    assert kpis["taux_exutoire_pct"] == 54.4
    assert kpis["soulagement_reseau_pct"] == 45.6
    assert kpis["reduction_charge_pct"] == 45.6
    assert kpis["bilan_hydraulique_decisionnel"] == "Bassin versant : Test"


def test_invariance_hydrologique_q_genere_rationnel():
    """
    RÈGLE D'INVARIANCE HYDROLOGIQUE :
    Vérifie que Q_généré est une constante hydrologique issue de la pluie rationnelle
    Q = (C * I * A) / 360, et ne change pas qu'il y ait 0 ouvrage ou 4 ouvrages spéciaux.
    """
    moteur = MoteurSWMM()

    rpt_base = """
  ****************************
  Outfall Loading Summary
  ****************************
  Outfall Node       Flow Freq.    Avg Flow    Max Flow    Total Vol
                     %             CMS         CMS         10^6 ltr
  ------------------------------------------------------------------
  OUTFALL_1          95.2          0.020       0.038       0.150
  
  ****************************
  Link Flow Summary
  ****************************
  Link               Type      Max Flow   Time of Max   Max Veloc  Max /    Max /
                               CMS        days hr:min   m/sec      Full Q   Full Depth
  ------------------------------------------------------------------------------------
  C1                 CONDUIT   0.038      0 01:15       0.85       0.45     0.40
"""
    # Cas 1 : Sans ouvrage spécial (Scénario A)
    # Area = 25.0 ha, I_max = 60.0 mm/h, C_eff = 0.70 => Q_rat = (0.70 * 60 * 25) / 360 = 2.917 m³/s
    meta_a = {
        "cluster_id": 92,
        "cluster_nom": "Bassin_Test",
        "total_area_ha": 25.0,
        "pluvio_intensite_max_mmh": 60.0,
        "effective_runoff_coeff": 0.70,
        "raccordements_orphelins": []
    }
    kpis_a = moteur._analyser_rapport_swmm(rpt_base, meta_a)

    # Cas 2 : Avec 2 ouvrages spéciaux qui dérivent 1.200 m³/s (Scénario B)
    rpt_b = rpt_base + """
  C_RACC_1           CONDUIT   0.700      0 01:20       1.20       0.80     0.70
  C_RACC_2           CONDUIT   0.500      0 01:22       1.10       0.75     0.65
"""
    meta_b = {
        "cluster_id": 92,
        "cluster_nom": "Bassin_Test",
        "total_area_ha": 25.0,
        "pluvio_intensite_max_mmh": 60.0,
        "effective_runoff_coeff": 0.70,
        "raccordements_orphelins": [{"nom": "Ouvrage 1"}, {"nom": "Ouvrage 2"}]
    }
    kpis_b = moteur._analyser_rapport_swmm(rpt_b, meta_b)

    # Invariance hydrologique stricte
    q_rat_theorique = round((0.70 * 60.0 * 25.0) / 360.0, 3)  # 2.917 m³/s
    assert kpis_a["q_genere_m3s"] == q_rat_theorique
    assert kpis_b["q_genere_m3s"] == q_rat_theorique
    assert kpis_a["q_genere_m3s"] == kpis_b["q_genere_m3s"]

    # Scénario A : Dérivé = 0 m³/s, Soulagement = 0%
    assert kpis_a["q_derive_m3s"] == 0.0
    assert kpis_a["soulagement_reseau_pct"] == 0.0

    # Scénario B : Dérivé = 1.200 m³/s, Soulagement = (1.200 / 2.917) * 100 = 41.1%
    assert kpis_b["q_derive_m3s"] == 1.200
    assert kpis_b["soulagement_reseau_pct"] == round((1.200 / q_rat_theorique) * 100.0, 1)


def test_assembler_inp_filtrage_spatial_ouvrages_distants(tmp_path):
    """
    RÈGLE DE LÉGITIMITÉ SPATIALE & TOPOLOGIQUE :
    Vérifie qu'un ouvrage orphelin éloigné (> 45 m) ou dont le regard n'appartient pas
    au sous-réseau simulé est STRICTEMENT IGNORÉ et NON RACCORDÉ dans le modèle .INP.
    """
    moteur = MoteurSWMM()
    from pathlib import Path
    gpkg_cands = [p for p in Path("uploads").glob("**/*.gpkg") if "network_Assainissement_Ville" in p.name]
    if not gpkg_cands:
        gpkg_cands = list(Path("uploads").glob("**/*.gpkg"))
    if not gpkg_cands:
        pytest.skip("Aucun GPKG disponible dans uploads/ pour ce test.")
    gpkg = gpkg_cands[0]

    # Test avec un ouvrage valide au regard 711 (adjacent au cluster 92)
    # et un ouvrage distant factice au regard 999999
    racc_test = [
        {"id": "OUV_VALIDE", "regard_proche_id": "711", "distance_m": 25.0},
        {"id": "OUV_DISTANT", "regard_proche_id": "999999", "distance_m": 850.0}
    ]

    inp, meta = moteur.assembler_modele_inp(
        gpkg_path=gpkg,
        cluster_id="25_ouvrages_speciaux_348883",
        pente_moyenne_pct=1.0,
        raccordements_orphelins=racc_test
    )

    # L'ouvrage valide doit être présent
    assert "OUT_OUV_VALIDE" in inp
    assert "C_RACC_OUV_VALIDE" in inp

    # L'ouvrage distant doit être TOTALEMENT ABSENT du modèle INP
    assert "OUT_OUV_DISTANT" not in inp
    assert "C_RACC_OUV_DISTANT" not in inp
