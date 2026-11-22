"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Tests d'invariance des résultats hydrauliques entre scénarios A et B
================================================================================
"""

import pytest
from pathlib import Path
from src.domain.moteur_swmm import MoteurSWMM
from src.domain.ouvrages_orphelins import detecter_ouvrages_orphelins_proches

def test_resolution_cluster_id_variants():
    """Vérifie que '25_ouvrages_speciaux_348883', 92, '92' résolvent le même bassin.

    Rebaselinage 2026-11 : 86.54 -> 89.27 ha. Les stations de relèvement avec
    refoulement sortant (SR_HC, 434) ne sont plus des exutoires terminaux :
    leurs bassins d'aspiration et leurs têtes de refoulement sont rattachés
    au bassin de l'ouvrage aval, ce qui ajoute ~2.73 ha de surface."""
    gpkg_path = Path("uploads/a66e32ad-f32b-4529-acc3-7a6026eb5a8a/network_Assainissement_Ville.gpkg")
    if not gpkg_path.exists():
        pytest.skip("GeoPackage de test non présent")

    moteur = MoteurSWMM()
    variants = ["25_ouvrages_speciaux_348883", 92, "92"]
    
    for var in variants:
        inp, meta = moteur.assembler_modele_inp(
            gpkg_path=gpkg_path,
            cluster_id=var,
            scenario_key="decennale_chlef_orage",
            duree_heures=2.0,
            pente_moyenne_pct=1.0
        )
        assert meta["total_area_ha"] == 89.27, f"Pour variant {var}, surface attendue 89.27 ha mais reçu {meta['total_area_ha']}"
        assert "25_ouvrages_speciaux" in meta["bassin_nom"], f"Pour variant {var}, nom attendu contenant 25_ouvrages_speciaux mais reçu {meta['bassin_nom']}"

def test_invariance_scenarios_ab_complet():
    """Vérifie que le Scénario A et le Scénario B produisent STRICTEMENT le même Débit Généré."""
    gpkg_path = Path("uploads/a66e32ad-f32b-4529-acc3-7a6026eb5a8a/network_Assainissement_Ville.gpkg")
    if not gpkg_path.exists():
        pytest.skip("GeoPackage de test non présent")

    moteur = MoteurSWMM()

    # Détection des ouvrages proches (< 45 m)
    det = detecter_ouvrages_orphelins_proches(str(gpkg_path), "25_ouvrages_speciaux_348883", rayon_max_m=45.0)
    ouvrages = det.get("ouvrages", [])

    # SCÉNARIO A : sans ouvrage spécial (ouvrages désactivés)
    res_a = moteur.executer_simulation(
        gpkg_path=gpkg_path,
        scenario_key="decennale_chlef_orage",
        cluster_id="25_ouvrages_speciaux_348883",
        pente_moyenne_pct=1.0,
        raccordements_orphelins=[]
    )

    # SCÉNARIO B : avec raccordement des ouvrages spéciaux réels (< 45m)
    res_b = moteur.executer_simulation(
        gpkg_path=gpkg_path,
        scenario_key="decennale_chlef_orage",
        cluster_id="25_ouvrages_speciaux_348883",
        pente_moyenne_pct=1.0,
        raccordements_orphelins=ouvrages
    )

    # INVARIANCE HYDROLOGIQUE STRICTE
    assert res_a["q_genere_m3s"] == res_b["q_genere_m3s"], (
        f"Incohérence Débit Généré : Scénario A = {res_a['q_genere_m3s']} m³/s vs Scénario B = {res_b['q_genere_m3s']} m³/s"
    )
    assert res_a["q_genere_m3s"] > 0, "Le débit généré doit être strictement positif"

    # Scénario A : zéro dérivé, 100% vers exutoire
    assert res_a["q_derive_m3s"] == 0.0
    assert res_a["taux_derive_pct"] == 0.0
    assert res_a["taux_exutoire_pct"] == 100.0

    # Scénario B : débit dérivé positif par l'ouvrage raccordé
    assert res_b["q_derive_m3s"] > 0.0
    assert res_b["taux_derive_pct"] > 0.0
    assert res_b["nb_ouvrages_raccordes"] >= 1
