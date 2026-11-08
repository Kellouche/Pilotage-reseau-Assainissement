"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Agent Expert 4 : Cartographie et évaluation multidimensionnelle des risques
================================================================================
"""

from typing import Dict, Any, List
from .common import formater_cout_dzd


class AgentGestionRisques:
    """
    Agent chargé de hiérarchiser les urgences d'intervention en 3 classes de priorité
    (P1 Critique sous 3 mois, P2 Majeur sous 12 mois, P3 Maintenance préventive)
    pour orienter la décision d'investissement sur des bases technico-économiques réelles.
    """

    def prioriser(
        self,
        diagnostic: Dict[str, Any],
        genie_civil: Dict[str, Any],
        solutions_durables: Dict[str, Any]
    ) -> Dict[str, Any]:
        actions_p1 = []  # Urgence absolue (Inondation & Débordement de voirie)
        actions_p2 = []  # Alerte majeure (Mise sous pression continue sans inondation)
        actions_p3 = []  # Maintenance & confort (Ensablement / vitesse < 0.6 m/s)

        flooded = diagnostic.get("flooded_nodes", [])
        flooded_map = {str(fn.get("node_id", "")).strip(): fn for fn in flooded if fn.get("node_id")}
        bottlenecks = diagnostic.get("bottlenecks", [])
        bottleneck_cids = {b.get("aval_cid") for b in bottlenecks if b.get("aval_cid")} | {b.get("amont_cid") for b in bottlenecks if b.get("amont_cid")}

        prescriptions = genie_civil.get("prescriptions", [])
        regards_traites_par_conduite = set()

        # 1. Classification P1 vs P2 des conduites de génie civil (Métrés réels & BPU)
        for prescr in prescriptions:
            cid = prescr.get("cid", "")
            u_node = str(prescr.get("upstream", "")).strip()
            d_node = str(prescr.get("downstream", "")).strip()
            c_lbl = prescr.get("conduit", cid)
            flow_ratio = float(prescr.get("flow_ratio", 1.0) or 1.0)
            cout_dzd = float(prescr.get("cout_estime_dzd", 0.0))

            # Est-ce une conduite critique P1 (contact avec regard inondé, goulot géométrique ou saturation extrême >= 1.5) ?
            fn_u = flooded_map.get(u_node)
            fn_d = flooded_map.get(d_node)
            is_bottleneck = cid in bottleneck_cids

            if fn_u or fn_d or is_bottleneck or flow_ratio >= 1.5:
                # P1 - Critique
                if fn_u:
                    regards_traites_par_conduite.add(u_node)
                    motif = f"Submersion voirie au Regard {u_node} ({fn_u.get('flood_volume_m3', 0.0)} m³)"
                    prob = f"Refoulement en amont vers Regard {u_node} ({fn_u.get('hours_flooded', 0.0)} h d'inondation)"
                elif fn_d:
                    regards_traites_par_conduite.add(d_node)
                    motif = f"Submersion voirie au Regard {d_node} ({fn_d.get('flood_volume_m3', 0.0)} m³)"
                    prob = f"Goulot refoulant vers le Regard {d_node} ({fn_d.get('hours_flooded', 0.0)} h d'inondation)"
                elif is_bottleneck:
                    motif = "Étranglement géométrique majeur & mise en charge"
                    prob = f"Rupture brutale de section générant un remous amont critique"
                else:
                    motif = f"Surcharge extrême ({int(flow_ratio*100)}% de capacité)"
                    prob = f"Collecteur sous pression maximale avec risque de refoulement en surface"

                actions_p1.append({
                    "priorite": "P1",
                    "cible": c_lbl,
                    "conduite": c_lbl,
                    "type_element": "Conduite",
                    "urgence": "P1 - CRITIQUE",
                    "type_risque": motif,
                    "probleme": prob,
                    "action": f"Recalibrage d'urgence en {prescr['materiau']} Ø{prescr['diam_prescrit_mm']} mm ({prescr['longueur_m']} m)",
                    "action_requise": f"Recalibrage d'urgence en {prescr['materiau']} Ø{prescr['diam_prescrit_mm']} mm ({prescr['longueur_m']} m)",
                    "estimation_cout_dzd": cout_dzd,
                    "delai_recommande": "3 mois (Urgence)"
                })
            else:
                # P2 - Majeur (Mise en charge continue sans inondation de surface immédiate)
                actions_p2.append({
                    "priorite": "P2",
                    "cible": c_lbl,
                    "conduite": c_lbl,
                    "type_element": "Conduite",
                    "urgence": "P2 - MAJEUR",
                    "type_risque": "Mise en pression continue (saturation 100%)",
                    "probleme": f"Conduite en charge à {int(flow_ratio*100)}% (Ø{prescr['diam_actuel_mm']} mm saturé)",
                    "action": f"Remplacement programmé par {prescr['materiau']} Ø{prescr['diam_prescrit_mm']} mm ({prescr['longueur_m']} m)",
                    "action_requise": f"Remplacement programmé par {prescr['materiau']} Ø{prescr['diam_prescrit_mm']} mm ({prescr['longueur_m']} m)",
                    "estimation_cout_dzd": cout_dzd,
                    "delai_recommande": "12 mois (Programmation)"
                })

        # 2. Regards inondés résiduels (points bas / cuvettes sans collecteur recalibré rattaché)
        for fn in flooded:
            nid = str(fn.get("node_id", "")).strip()
            if nid and nid not in regards_traites_par_conduite:
                vol_m3 = float(fn.get("flood_volume_m3", 0.0) or 0.0)
                cout_avaloir = round(380000.0 + min(vol_m3 * 1500.0, 320000.0), 0)
                actions_p1.append({
                    "priorite": "P1",
                    "cible": f"Regard {nid}",
                    "conduite": f"Regard {nid}",
                    "type_element": "Regard",
                    "urgence": "P1 - CRITIQUE",
                    "type_risque": f"Point bas / Cuvette voirie ({vol_m3:.1f} m³)",
                    "probleme": f"Débordement de surface ({vol_m3:.1f} m³ pendant {fn.get('hours_flooded', 0.0)} h)",
                    "action": "Pose d'avaloir siphoïde double à grand débit C250 & clapet anti-reflux ONA",
                    "action_requise": "Pose d'avaloir siphoïde double à grand débit C250 & clapet anti-reflux ONA",
                    "estimation_cout_dzd": cout_avaloir,
                    "delai_recommande": "3 mois (Urgence)"
                })

        # 3. P3 : Maintenance préventive (Curage hydrodynamique haute pression BPU ONA 1800 DZD/ml)
        for lv in diagnostic.get("low_velocity_links", []):
            c_lbl = lv.get("conduit", lv["cid"])
            l_m = float(lv.get("longueur_m") or lv.get("longueur") or 45.0)
            cout_curage = round(l_m * 1800.0, 0)
            actions_p3.append({
                "priorite": "P3",
                "cible": c_lbl,
                "conduite": c_lbl,
                "type_element": "Conduite",
                "urgence": "P3 - ENTRETIEN",
                "type_risque": "Dépôt & ensablement",
                "probleme": f"Vitesse {lv['velocity_ms']:.2f} m/s insuffisante (< 0.60 m/s)",
                "action": f"Curage hydrodynamique haute pression ({l_m:.1f} ml) et inspection ITV",
                "action_requise": f"Curage hydrodynamique haute pression ({l_m:.1f} ml) et inspection ITV",
                "estimation_cout_dzd": cout_curage,
                "delai_recommande": "Entretien régulier"
            })

        # Totaux budgétaires par niveau d'urgence
        cout_p1 = sum(a["estimation_cout_dzd"] for a in actions_p1)
        cout_p2 = sum(a["estimation_cout_dzd"] for a in actions_p2)
        cout_p3 = sum(a["estimation_cout_dzd"] for a in actions_p3)

        fmt_p1 = formater_cout_dzd(cout_p1)
        fmt_p2 = formater_cout_dzd(cout_p2)
        fmt_p3 = formater_cout_dzd(cout_p3)

        note_technique = (
            f"La hiérarchisation multi-critères classe les interventions en 3 horizons d'urgence : "
            f"{len(actions_p1)} action(s) P1 - Critique ({fmt_p1} sous 3 mois pour résorption des débordements et points noirs), "
            f"{len(actions_p2)} action(s) P2 - Majeur ({fmt_p2} sous 12 mois pour suppression des mises en charge continues), et "
            f"{len(actions_p3)} action(s) P3 - Maintenance ({fmt_p3} pour curage préventif des zones de sédimentation V < 0.60 m/s). "
            f"Cette priorisation optimise l'allocation budgétaire et assure la cohérence avec le programme de travaux de génie civil."
        )

        # Pour la liste récapitulative (rapport d'expertise et tableau de bord) :
        # Présentation équilibrée des 3 horizons d'urgence (P1, P2, P3)
        actions_liste = actions_p1[:15] + actions_p2[:10] + actions_p3[:6]

        return {
            "agent": "Agent 4 : Priorisation des Risques",
            "statut": "Priorisation établie",
            "note_technique": note_technique,
            "synthese": {
                "nb_p1_critique": len(actions_p1),
                "nb_p2_majeur": len(actions_p2),
                "nb_p3_maintenance": len(actions_p3),
                "cout_p1_dzd": cout_p1,
                "cout_p2_dzd": cout_p2,
                "cout_p3_dzd": cout_p3,
                "cout_total_dzd": cout_p1 + cout_p2 + cout_p3
            },
            "actions_priorisees": {
                "P1": actions_p1[:10],
                "P2": actions_p2[:10],
                "P3": actions_p3[:10]
            },
            "actions_liste": actions_liste
        }

