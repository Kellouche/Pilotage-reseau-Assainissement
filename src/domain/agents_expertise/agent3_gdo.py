"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Agent Expert 3 : Gestion durable des ouvrages (GDO) et rétention
================================================================================
"""

from typing import Dict, Any, List


class AgentHydrologieDurable:
    """
    Agent expert en gestion de l'eau à la source : calcule les volumes de rétention
    et dimensionne des ouvrages d'écrêtement alternatifs (bassins d'orage, noues).
    """

    def proposer_solutions(
        self,
        diagnostic: Dict[str, Any],
        kpis: Dict[str, Any],
        meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        flooded = diagnostic.get("flooded_nodes", [])
        total_vol_deborde_m3 = sum(f.get("flood_volume_m3", 0.0) for f in flooded)

        # Si pas de débordement direct mais des surcharges, dimensionner sur 10% du volume ruisselé
        total_outflow = kpis.get("total_outflow_m3", 1000.0)
        vol_retention_cible_m3 = max(total_vol_deborde_m3 * 1.3, total_outflow * 0.12)
        vol_retention_cible_m3 = round(vol_retention_cible_m3, 1)

        # Dimensionnement d'un bassin d'orage à ciel ouvert (profondeur utile 1.8 m)
        profondeur_bassin_m = 1.8
        emprise_sol_bassin_m2 = round(vol_retention_cible_m3 / profondeur_bassin_m, 1)

        # Dimensionnement équivalent en noues paysagères végétalisées (largeur 2m, prof 0.5m)
        lineaire_noues_m = round(vol_retention_cible_m3 / (2.0 * 0.4), 1)

        solutions = [
            {
                "solution": "Bassin d'écrêtement et rétention paysager",
                "designation": "Bassin d'écrêtement et rétention paysager",
                "type": "Ouvrage de stockage centralisé en amont",
                "volume_utile_m3": vol_retention_cible_m3,
                "emprise_au_sol_m2": emprise_sol_bassin_m2,
                "dimensionnement": f"Volume : {vol_retention_cible_m3} m³ (Emprise ~ {emprise_sol_bassin_m2} m²)",
                "reduction_debit_pointe_estimee": "35 % à 45 %",
                "impact_attendu": "Abattement pointe : 35 % à 45 %",
                "avantage": "Évite le recalibrage lourd des collecteurs aval en milieu urbain dense"
            },
            {
                "solution": "Noues végétalisées et tranchées d'infiltration",
                "designation": "Noues végétalisées et tranchées d'infiltration",
                "type": "Gestion linéaire le long des délaissés de voirie",
                "lineaire_recommande_m": lineaire_noues_m,
                "dimensionnement": f"Linéaire : {lineaire_noues_m} ml (Largeur 2.0 m)",
                "reduction_debit_pointe_estimee": "20 % à 30 %",
                "impact_attendu": "Abattement pointe : 20 % à 30 %",
                "avantage": "Recharge de la nappe phréatique et îlots de fraîcheur urbains"
            },
            {
                "solution": "Chaussées réservoirs et pavés drainants",
                "designation": "Chaussées réservoirs et pavés drainants",
                "type": "Infiltration directe dans les parkings et voies secondaires",
                "surface_recommandee_m2": round(emprise_sol_bassin_m2 * 2.5, 1),
                "dimensionnement": f"Surface perméable : {round(emprise_sol_bassin_m2 * 2.5, 1)} m²",
                "reduction_debit_pointe_estimee": "15 % à 25 %",
                "impact_attendu": "Abattement pointe : 15 % à 25 %",
                "avantage": "Zéro emprise foncière supplémentaire"
            }
        ]

        note_technique = (
            f"La minéralisation et l'imperméabilisation des sols génèrent un volume de ruissellement direct qui sature rapidement les canalisations aval. "
            f"L'Agent GDO préconise d'intercepter et de temporiser les eaux pluviales à la source par une gestion durable des ouvrages (GDO). "
            f"Un volume tampon de {vol_retention_cible_m3} m³ doit être mobilisé, combinant un bassin d'écrêtement paysager ({emprise_sol_bassin_m2} m² d'emprise) "
            f"et {lineaire_noues_m} ml de noues végétalisées en délaissés de voirie. Cette approche permet de rabattre le pic de débit de 35% à 45% "
            f"et d'éviter le surdimensionnement onéreux des réseaux enterrés en zone urbaine dense."
        )

        return {
            "agent": "Agent 3 : Hydrologie durable & gestion durable des ouvrages (GDO)",
            "statut": "Solutions établies",
            "note_technique": note_technique,
            "volume_tampon_requis_m3": vol_retention_cible_m3,
            "surface_bassin_m2": emprise_sol_bassin_m2,
            "solutions": solutions
        }

