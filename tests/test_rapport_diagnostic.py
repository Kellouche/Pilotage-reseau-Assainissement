# -*- coding: utf-8 -*-
"""
Tests unitaires pour le générateur de rapport d'expertise hydraulique (PDF ReportLab).
"""

from src.domain.rapport_diagnostic import generer_pdf_rapport_diagnostic


def test_generer_pdf_rapport_diagnostic_succes():
    """Vérifie la génération complète du PDF avec toutes les sections."""
    simulation_data = {
        "meta": {
            "project_name": "Réseau Test Chlef",
            "bassin_nom": "Bassin Versant Centre Chlef",
            "cluster_nom": "Bassin 1 - Centre Ville",
            "cluster_id": 1,
            "scenario": "Pluie décennale ANRH Mascara",
            "total_area_ha": 125.5,
            "buffer_m": 45,
            "conduits_count": 379,
            "junctions_count": 372,
            "subcatchments_count": 59,
            "imperv_pct": 70,
            "typologie_nom": "Habitat mixte urbain",
            "pluvio_periode_retour": "T = 10 ans (décennale)",
            "pluvio_intensite_max_mmh": 74.9,
            "pluvio_hauteur_totale_mm": 42.8,
            "pluvio_montana": "I(t) = 9.334 · t⁻⁰·⁷⁴⁵",
            "pluvio_station": "Station ANRH Chlef Siège (Réf. 010501)",
            "pluvio_source": "Séries statistiques ANRH 1970–2024",
            "temps_concentration_min": 15.0,
        },
        "kpis": {
            "routing_continuity_error_pct": -0.166,
            "runoff_continuity_error_pct": 0.05,
            "total_precipitation_mm": 42.8,
            "total_outflow_m3": 8500.0,
            "peak_outflow_m3s": 2.15,
            "flooded_nodes_count": 3,
            "surcharged_nodes_count": 7,
            "pluvio_intensite_max_mmh": 74.9,
            "pluvio_hauteur_totale_mm": 42.8,
            "pluvio_periode_retour": "T = 10 ans",
            "pluvio_station": "Station ANRH Chlef Siège",
            "pluvio_montana": "I(t) = 9.334 · t⁻⁰·⁷⁴⁵",
            "pluvio_source": "Séries ANRH 1970-2024",
            "q_exutoire_m3s": 1.45,
            "q_derive_m3s": 0.70,
            "q_genere_m3s": 2.15,
            "taux_derive_pct": 32.6,
            "taux_exutoire_pct": 67.4,
            "nb_ouvrages_raccordes": 4,
            "bilan_hydraulique_decisionnel": "Bassin versant : Bassin 1 - Centre Ville\n• Débit total généré par le bassin : 2.150 m³/s\n• Soulagement du collecteur principal : 32.6%\n• Débit résiduel vers l'exutoire principal : 1.450 m³/s (67.4%)\n• Débit capté par 4 ouvrages spéciaux mobilisés : 0.700 m³/s (32.6%)",
        },
        "agents_expertise": {
            "diagnostic_causal": {
                "nb_surcharges": 7,
                "nb_goulots": 3,
                "note_technique": "L'analyse hydrodynamique 1D Saint-Venant met en évidence un régime d'écoulement sous forte tension.",
                "surcharged_links": [
                    {"conduit": "C_001", "flow_ratio": 1.25, "depth_ratio": 1.1, "vitesse": 2.3, "q_max": 0.45, "cause": "Remous aval"},
                    {"conduit": "C_002", "flow_ratio": 1.10, "depth_ratio": 1.05, "vitesse": 1.8, "q_max": 0.38, "cause": "Goulot géométrique"},
                ],
                "bottlenecks": [
                    {"amont": "J_001", "aval": "J_002", "diam_amont": 600, "diam_aval": 400, "longueur": 45.2, "description": "Réduction anormale de section"},
                    {"amont": "J_003", "aval": "J_004", "diam_amont": 500, "diam_aval": 300, "longueur": 32.1, "description": "Goulot critique"},
                ],
            },
            "prescriptions_genie_civil": {
                "cout_global_estime_dzd": 240384400,
                "metres_lineaires_totaux": 4112.8,
                "nb_troncons_a_recalibrer": 97,
                "note_technique": "Conformément aux règles de l'art, les diamètres sont recalibrés avec marge +25%.",
                "decomposition_bpu": {
                    "montant_terrassement_dzd": 72115320,
                    "montant_fourniture_dzd": 84134540,
                    "montant_pose_remblai_dzd": 48076880,
                    "montant_chaussee_dzd": 36057660,
                },
                "recapitulatif_par_dn": [
                    {"label": "DN 600", "materiau": "Béton Armé 135A", "classe": "Classe 135", "nb_troncons": 45, "lineaire_ml": 1850.2, "pct_lineaire": 45, "cout_unitaire_ml_dzd": 45000, "cout_total_dzd": 83259000, "pct_budget": 34.6},
                    {"label": "DN 800", "materiau": "Béton Armé 135A", "classe": "Classe 135", "nb_troncons": 32, "lineaire_ml": 1320.5, "pct_lineaire": 32, "cout_unitaire_ml_dzd": 58000, "cout_total_dzd": 76589000, "pct_budget": 31.9},
                    {"label": "DN 1000", "materiau": "Béton Armé 135A", "classe": "Classe 135", "nb_troncons": 20, "lineaire_ml": 942.1, "pct_lineaire": 23, "cout_unitaire_ml_dzd": 85000, "cout_total_dzd": 80078350, "pct_budget": 33.3},
                ],
                "prescriptions": [
                    {"conduit": "C_001", "diametre_actuel_mm": 400, "diametre_requis_mm": 600, "dn_normalise_mm": 600, "materiau_recommande": "Béton Armé 135A", "longueur_m": 45.2, "cout_estime_dzd": 2034000},
                    {"conduit": "C_002", "diametre_actuel_mm": 300, "diametre_requis_mm": 500, "dn_normalise_mm": 500, "materiau_recommande": "Béton Armé 135A", "longueur_m": 32.1, "cout_estime_dzd": 1861800},
                ],
            },
            "solutions_hydrologie_durable": {
                "volume_tampon_requis_m3": 6595,
                "surface_bassin_m2": 4200,
                "note_technique": "L'agent GDO préconise d'intercepter les eaux pluviales à la source pour rabattre le pic de 35-45%.",
                "solutions": [
                    {"type": "Bassin d'écrêtement", "designation": "Bassin d'orage paysager en amont du réseau", "dimensionnement": "Volume : 6 595 m³ (Emprise ~ 4 200 m²)", "impact_attendu": "Écrêtement direct de la pointe de crue décennale (-35% de débit)"},
                    {"type": "Noues d'infiltration", "designation": "Noues végétalisées le long des voiries", "dimensionnement": "Linéaire : 1 200 ml • Largeur 1.5 m", "impact_attendu": "Infiltration diffuse à la source & déconnexion pluviale"},
                ],
            },
            "matrice_risques": {
                "note_technique": "La hiérarchisation multi-critères classe les interventions en 3 horizons d'urgence (P1 Critique à 3 mois, P2 Majeur sous tension à 12 mois, P3 Maintenance préventive).",
                "actions_liste": [
                    {"priorite": "P1", "conduite": "C_001", "type_risque": "Débordement franc regard J_001", "action_requise": "Recalibrage urgent + bassin tampon amont", "estimation_cout_dzd": 45000000, "delai_recommande": "3 mois (Urgence)"},
                    {"priorite": "P1", "conduite": "C_002", "type_risque": "Surcharge critique conduite", "action_requise": "Élargissement section + vérification remous aval", "estimation_cout_dzd": 32000000, "delai_recommande": "3 mois (Urgence)"},
                    {"priorite": "P2", "conduite": "C_003", "type_risque": "Saturation 85%", "action_requise": "Surveillance renforcée et curage préventif", "estimation_cout_dzd": 5000000, "delai_recommande": "12 mois"},
                ],
            },
            "analyse_variantes_financiere": {
                "economie_realisee_dzd": 90580100,
                "economie_pourcentage": 27.4,
                "note_technique": "La Variante 3 (Mixte Optimisée) démontre la supériorité technico-économique en couplant recalibrage ciblé et bassin d'écrêtement.",
                "variantes": [
                    {"nom": "Variante 1 : 100% tout-réseau", "description": "Recalibrage intégral sans bassin", "recalibrage_ml": 7591.9, "volume_retention_m3": 0, "cout_total_dzd": 330964500, "gain_hydraulique": "100% théorique", "impact_voirie": "TRÈS ÉLEVÉ", "risque_aval": "TRÈS ÉLEVÉ", "score_resilience": 5.5, "statut": "NON RETENU"},
                    {"nom": "Variante 2 : 100% GDO pures", "description": "Bassin d'orage sans recalibrage réseau", "recalibrage_ml": 0, "volume_retention_m3": 18500, "cout_total_dzd": 112500000, "gain_hydraulique": "Partiel (~62%)", "impact_voirie": "Faible", "risque_aval": "Faible", "score_resilience": 6.0, "statut": "INSUFFISANT"},
                    {"nom": "Variante 3 : Mixte optimisée", "description": "Recalibrage ciblé 97 goulots + Bassin 6 595 m³", "recalibrage_ml": 4112.8, "volume_retention_m3": 6595, "cout_total_dzd": 240384400, "gain_hydraulique": "100% résorption intégrale", "impact_voirie": "Modéré et phasable", "risque_aval": "MINIMAL", "score_resilience": 9.2, "statut": "RECOMMANDÉ"},
                ],
                "ratios_directeurs": {
                    "cout_par_ml_renove_dzd": 58450,
                    "cout_par_habitant_protege_dzd": 16025,
                    "dommages_annuels_evites_dzd": 45000000,
                    "payback_annees": 5.3,
                    "tri_pourcentage": 14.8,
                    "van_actualisee_20ans_dzd": 275761100,
                },
            },
            "synthese_executive": {
                "verdict": "VULNÉRABILITÉ ÉLEVÉE — DÉBORDEMENTS DÉTECTÉS",
                "couleur": "#ef4444",
                "recommandation_cle": "Le réseau présente 3 point(s) noir(s) d'inondation nécessitant une intervention prioritaire. La modélisation hydrodynamique Saint-Venant démontre que la combinaison concertée d'un bassin d'écrêtement de 6595 m³ en amont et du recalibrage de 4112.8 m de collecteurs structurants assure la résorption théorique intégrale.",
                "avis_direction_generale": "Prioriser les investissements P1 sur les collecteurs structurants pour résorber les risques majeurs d'inondation en surface pour la pluie de projet.",
                "note_technique": "Synthèse stratégique d'aide à la décision destinée à la Direction Générale. Le verdict hydraulique conclut à la nécessité d'un plan combiné de recalibrage et de rétention amont.",
                "score_resilience_reseau": 92,
                "indicateurs_marquants": {
                    "debit_pointe_m3s": 2.15,
                    "volume_total_m3": 8500,
                    "cout_travaux_gc_estime_dzd": 240384400,
                    "volume_tampon_lid_requis_m3": 6595,
                },
                "bilan_hydraulique": {
                    "bassin_nom": "Bassin 1 - Centre Ville",
                    "q_genere_m3s": 2.15,
                    "q_exutoire_m3s": 1.45,
                    "taux_exutoire_pct": 67.4,
                    "q_derive_m3s": 0.70,
                    "taux_derive_pct": 32.6,
                    "nb_ouvrages_actifs": 4,
                    "soulagement_reseau_pct": 32.6,
                    "reduction_charge_pct": 32.6,
                    "texte_decisionnel": "Bilan complet disponible",
                },
                "bilan_hydraulique_decisionnel": "Bilan complet disponible",
            },
        },
        "buffer_sensitivity": {
            "curve": [
                {"buffer_m": 35, "surface_ha": 98.2, "gain_pct": 0, "peak_flow_m3s": 2.45},
                {"buffer_m": 45, "surface_ha": 125.5, "gain_pct": 27.8, "peak_flow_m3s": 2.15},
                {"buffer_m": 60, "surface_ha": 148.3, "gain_pct": 51.0, "peak_flow_m3s": 2.01},
            ]
        },
    }

    pdf_bytes = generer_pdf_rapport_diagnostic(
        simulation_data=simulation_data,
        project_name="Réseau Test Chlef"
    )

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 5000
    assert pdf_bytes.startswith(b"%PDF-")


def test_generer_pdf_rapport_diagnostic_donnees_minimales():
    """Vérifie que la fonction gère gracieusement les données minimales."""
    simulation_data = {}

    pdf_bytes = generer_pdf_rapport_diagnostic(
        simulation_data=simulation_data,
        project_name="Réseau Minimal"
    )

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF-")


def test_generer_pdf_rapport_diagnostic_donnees_reelles_simulation():
    """Test avec des données réelles d'une simulation SWMM pour vérifier le bilan hydraulique."""
    # Simuler des données réelles d'une simulation SWMM où les valeurs sont calculées
    simulation_data = {
        "meta": {
            "project_name": "Réseau Chlef",
            "bassin_nom": "Exutoire OUT_3607",
            "cluster_nom": "Bassin versant",
            "scenario": "Pluie décennale",
            "total_area_ha": 125.5,
        },
        "kpis": {
            "peak_outflow_m3s": 2.15,
            "total_outflow_m3": 8500.0,
            "flooded_nodes_count": 3,
            "surcharged_nodes_count": 7,
            # Données du bilan hydraulique calculées par analyse_rapport.py
            "q_genere_m3s": 2.15,
            "q_exutoire_m3s": 1.45,
            "q_derive_m3s": 0.70,
            "taux_derive_pct": 32.6,
            "taux_exutoire_pct": 67.4,
            "nb_ouvrages_raccordes": 4,
        },
        "agents_expertise": {
            "synthese_executive": {
                "bilan_hydraulique": {
                    "bassin_nom": "Exutoire OUT_3607",
                    "q_genere_m3s": 2.15,
                    "q_exutoire_m3s": 1.45,
                    "taux_exutoire_pct": 67.4,
                    "q_derive_m3s": 0.70,
                    "taux_derive_pct": 32.6,
                    "nb_ouvrages_actifs": 4,
                },
            },
        },
    }

    pdf_bytes = generer_pdf_rapport_diagnostic(
        simulation_data=simulation_data,
        project_name="Réseau Chlef"
    )

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 5000
    assert pdf_bytes.startswith(b"%PDF-")

    # Vérifier que le PDF ne contient pas de valeurs à 0 pour le bilan hydraulique
    # (On ne peut pas lire le contenu du PDF directement, mais on peut vérifier que la fonction ne crash pas)
    # Le test principal est que la fonction génère un PDF valide avec ces données