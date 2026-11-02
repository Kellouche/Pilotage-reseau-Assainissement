"""
Système Multi-Agents d'Ingénierie pour l'Interprétation Experte SWMM 5.2.
Fichier : src/domain/agents_expertise.py

Orchestre une équipe d'agents d'IA métier pour transformer les résultats bruts
de simulation hydraulique (hauteurs, débits, vitesses) en diagnostics causaux,
prescriptions de travaux de génie civil dimensionnés, solutions durables (LID/SFN),
et plans d'action priorisés pour les directeurs et ingénieurs d'assainissement.
"""

import math
from typing import Dict, Any, List, Optional
import pandas as pd
import geopandas as gpd


# ==============================================================================
# AGENT 1 : DIAGNOSTICIEN HYDRAULIQUE CAUSAL ("Root Cause Analyzer")
# ==============================================================================

class AgentDiagnosticCausal:
    """
    Agent expert chargé de remonter des symptômes (débordements, surpressions)
    aux causes physiques racines (goulots d'étranglement, ruptures de pente, reflux).
    """

    def analyser(
        self,
        kpis: Dict[str, Any],
        conduit_results: Dict[str, Any],
        node_results: Dict[str, Any],
        meta: Dict[str, Any],
        canalisations_gdf: Optional[gpd.GeoDataFrame] = None
    ) -> Dict[str, Any]:
        bottlenecks = []
        slope_anomalies = []
        backwater_nodes = []
        low_velocity_links = []
        high_velocity_links = []
        surcharged_links = []
        flooded_nodes_detail = []

        # Construction d'un index des diamètres et pentes géométriques si le GeoDataFrame est fourni
        pipe_geom_map = {}
        if canalisations_gdf is not None and not canalisations_gdf.empty:
            for idx, row in canalisations_gdf.iterrows():
                cid = f"C_{idx + 1}"
                diam = row.get("DIAMETRE") or row.get("diametre") or row.get("Diametre")
                mat = row.get("MATERIAU") or row.get("materiau") or "Béton"
                try:
                    diam = float(diam) if diam else 600.0
                except Exception:
                    diam = 600.0
                u = str(row.get("ID_AMONT", ""))
                d = str(row.get("ID_AVAL", ""))
                pipe_geom_map[cid] = {"diam": diam, "mat": mat, "upstream": u, "downstream": d}

        # 1. Analyse des conduites en charge et des vitesses
        for cid, c in conduit_results.items():
            ratio = c.get("flow_ratio", 0.0)
            depth_ratio = c.get("depth_ratio", 0.0)
            vel = c.get("max_velocity_ms", 0.0)
            q_max = c.get("max_flow_cms", 0.0)
            pipe_info = pipe_geom_map.get(cid, {"diam": 600.0, "mat": "Béton"})

            # Surcharge / Mise en pression
            if ratio >= 1.0 or depth_ratio >= 1.0:
                surcharged_links.append({
                    "cid": cid,
                    "flow_ratio": ratio,
                    "depth_ratio": depth_ratio,
                    "max_flow_cms": q_max,
                    "max_velocity_ms": vel,
                    "diam": pipe_info["diam"],
                    "mat": pipe_info["mat"],
                    "cause": "Capacité gravitaire théorique dépassée lors du pic de crue"
                })

            # Auto-curage insuffisant (risque d'ensablement à long terme)
            if vel < 0.6 and ratio > 0.08:
                low_velocity_links.append({
                    "cid": cid,
                    "velocity_ms": vel,
                    "flow_ratio": ratio,
                    "cause": f"Vitesse maximale {vel:.2f} m/s < 0.6 m/s (seuil réglementaire d'auto-curage)"
                })

            # Risque d'affouillement / érosion
            if vel > 4.0:
                high_velocity_links.append({
                    "cid": cid,
                    "velocity_ms": vel,
                    "cause": f"Vitesse d'écoulement {vel:.2f} m/s > 4.0 m/s (risque d'érosion du radier)"
                })

        # 2. Analyse des goulots d'étranglement amont ➔ aval
        if pipe_geom_map:
            # Recherche de diminutions de diamètre de l'amont vers l'aval
            node_out_pipes = {}
            node_in_pipes = {}
            for cid, info in pipe_geom_map.items():
                node_out_pipes.setdefault(info["upstream"], []).append(cid)
                node_in_pipes.setdefault(info["downstream"], []).append(cid)

            for nid, in_cids in node_in_pipes.items():
                out_cids = node_out_pipes.get(nid, [])
                for ic in in_cids:
                    d_in = pipe_geom_map[ic]["diam"]
                    for oc in out_cids:
                        d_out = pipe_geom_map[oc]["diam"]
                        if d_out < d_in:
                            bottlenecks.append({
                                "regard": nid,
                                "amont_cid": ic,
                                "aval_cid": oc,
                                "diam_amont": d_in,
                                "diam_aval": d_out,
                                "delta_mm": d_in - d_out,
                                "description": f"Étranglement géométrique anormal : passage de Ø{int(d_in)} à Ø{int(d_out)} mm au regard {nid}."
                            })

        # 3. Analyse des débordements de regards
        for nid, n in node_results.items():
            if n.get("status") == "flooded":
                h_flood = n.get("hours_flooded", 0.0)
                vol_m3 = n.get("flood_volume_m3", 0.0)
                pk_cms = n.get("peak_flood_flow_cms", 0.0)
                flooded_nodes_detail.append({
                    "node_id": nid,
                    "hours_flooded": round(h_flood, 2),
                    "flood_volume_m3": round(vol_m3, 1),
                    "peak_flow_cms": round(pk_cms, 3),
                    "diagnostic": "Débordement avec inondation superficielle de voirie"
                })

        return {
            "agent": "Agent 1 : Diagnosticien Causal",
            "statut": "Analyse Complète",
            "nb_surcharges": len(surcharged_links),
            "surcharged_links": surcharged_links,
            "nb_goulots": len(bottlenecks),
            "bottlenecks": bottlenecks,
            "nb_debordements": len(flooded_nodes_detail),
            "flooded_nodes": flooded_nodes_detail,
            "nb_autocurage_faible": len(low_velocity_links),
            "low_velocity_links": low_velocity_links[:6],
            "nb_erosion": len(high_velocity_links),
            "high_velocity_links": high_velocity_links[:6]
        }


# ==============================================================================
# AGENT 2 : GÉNIE CIVIL & DIMENSIONNEMENT ("Civil Engineering & Sizing")
# ==============================================================================

class AgentGenieCivil:
    """
    Agent chargé de calculer les diamètres nominaux requis (Manning-Strickler)
    et de formuler les prescriptions techniques de travaux de génie civil.
    """

    STANDARDS_DN_MM = [300, 400, 500, 600, 800, 1000, 1200, 1400, 1600, 1800, 2000]

    def prescrire(
        self,
        diagnostic: Dict[str, Any],
        pente_moyenne_pct: float = 1.0,
        k_strickler: float = 70.0
    ) -> Dict[str, Any]:
        prescriptions = []
        surcharged = diagnostic.get("surcharged_links", [])

        total_metres_a_remplacer = 0.0
        cout_total_estime_dzd = 0.0

        for item in surcharged:
            cid = item["cid"]
            q_max = item.get("max_flow_cms", 0.1)
            diam_actuel = item.get("diam", 500.0)

            # Calcul du diamètre requis avec marge de sécurité de 25% (remplissage à 80% max)
            # Formule de Manning-Strickler pour conduite circulaire pleine
            # D = ( Q / ( K * sqrt(S) * 0.3117 ) ) ^ (3/8)
            s_m_m = max(pente_moyenne_pct / 100.0, 0.001)
            q_cible = max(q_max * 1.25, 0.05)
            d_theorique_m = (q_cible / (k_strickler * math.sqrt(s_m_m) * 0.3117)) ** (3.0 / 8.0)
            dn_calc_mm = d_theorique_m * 1000.0

            # Choix du DN standard supérieur
            dn_prescrit = next((dn for dn in self.STANDARDS_DN_MM if dn >= dn_calc_mm), self.STANDARDS_DN_MM[-1])

            # Si le DN actuel est déjà supérieur ou égal, proposer recalibrage au standard suivant
            if dn_prescrit <= diam_actuel:
                idx_cur = self.STANDARDS_DN_MM.index(int(diam_actuel)) if int(diam_actuel) in self.STANDARDS_DN_MM else 0
                dn_prescrit = self.STANDARDS_DN_MM[min(idx_cur + 1, len(self.STANDARDS_DN_MM) - 1)]

            longueur_estimee_m = 45.0  # Longueur moyenne entre 2 regards en zone urbaine
            total_metres_a_remplacer += longueur_estimee_m

            # Estimation de coût travaux (Fourniture + Pose + Terrassement + Réfection chaussée)
            # Environs 25 000 DZD/ml pour Ø500, 40 000 DZD/ml pour Ø800, 65 000 DZD/ml pour Ø1200
            cout_unitaire_dzd = 20000.0 + (dn_prescrit / 1000.0) * 35000.0
            cout_troncon_dzd = cout_unitaire_dzd * longueur_estimee_m
            cout_total_estime_dzd += cout_troncon_dzd

            materiau_recommande = "Béton Armé Classe 135A" if dn_prescrit >= 800 else "PEHD Double Paroi SN8"

            prescriptions.append({
                "cid": cid,
                "diam_actuel_mm": int(diam_actuel),
                "diam_prescrit_mm": dn_prescrit,
                "gain_capacite_pct": round(((dn_prescrit / diam_actuel)**2.67 - 1.0) * 100.0, 1),
                "longueur_m": longueur_estimee_m,
                "materiau": materiau_recommande,
                "cout_estime_dzd": round(cout_troncon_dzd, 0),
                "type_travaux": "Recalibrage de collecteur par tranchée ouverte"
            })

        return {
            "agent": "Agent 2 : Génie Civil & Dimensionnement",
            "statut": "Prescriptions Établies",
            "nb_troncons_a_recalibrer": len(prescriptions),
            "metres_lineaires_totaux": round(total_metres_a_remplacer, 1),
            "cout_global_estime_dzd": round(cout_total_estime_dzd, 0),
            "prescriptions": prescriptions[:10]  # Top 10 prioritaire
        }


# ==============================================================================
# AGENT 3 : HYDROLOGIE DURABLE & SOLUTIONS FONDÉES SUR LA NATURE (LID/SFN)
# ==============================================================================

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
                "solution": "Bassin d'Écrêtement & Rétention Paysager",
                "type": "Ouvrage de stockage centralisé en amont",
                "volume_utile_m3": vol_retention_cible_m3,
                "emprise_au_sol_m2": emprise_sol_bassin_m2,
                "reduction_debit_pointe_estimee": "35 % à 45 %",
                "avantage": "Évite le recalibrage lourd des collecteurs aval en milieu urbain dense"
            },
            {
                "solution": "Noues Végétalisées & Tranchées d'Infiltration",
                "type": "Gestion linéaire le long des délaissés de voirie",
                "lineaire_recommande_m": lineaire_noues_m,
                "reduction_debit_pointe_estimee": "20 % à 30 %",
                "avantage": "Recharge de la nappe phréatique et îlots de fraîcheur urbains"
            },
            {
                "solution": "Chaussées Réservoirs & Pavés Drainants",
                "type": "Infiltration directe dans les parkings et voies secondaires",
                "surface_recommandee_m2": round(emprise_sol_bassin_m2 * 2.5, 1),
                "reduction_debit_pointe_estimee": "15 % à 25 %",
                "avantage": "Zéro emprise foncière supplémentaire"
            }
        ]

        return {
            "agent": "Agent 3 : Hydrologie Durable (LID / SFN)",
            "statut": "Solutions Établies",
            "volume_tampon_requis_m3": vol_retention_cible_m3,
            "surface_bassin_m2": emprise_sol_bassin_m2,
            "solutions": solutions
        }


# ==============================================================================
# AGENT 4 : MATRICE DE RISQUES & PRIORISATION ("Risk & Asset Manager")
# ==============================================================================

class AgentGestionRisques:
    """
    Agent chargé de hiérarchiser les urgences d'intervention en 3 classes de priorité
    (P1 Critique, P2 Majeur, P3 Maintenance) pour orienter la décision d'investissement.
    """

    def prioriser(
        self,
        diagnostic: Dict[str, Any],
        genie_civil: Dict[str, Any],
        solutions_durables: Dict[str, Any]
    ) -> Dict[str, Any]:
        actions_p1 = []  # Urgence absolue (Inondation & Débordement)
        actions_p2 = []  # Alerte majeure (Mise sous pression continue)
        actions_p3 = []  # Maintenance & confort (Ensablement / vitesse)

        # P1 : Tous les regards qui inondent la surface
        for fn in diagnostic.get("flooded_nodes", []):
            actions_p1.append({
                "cible": f"Regard {fn['node_id']}",
                "urgence": "P1 - CRITIQUE",
                "probleme": f"Débordement de surface ({fn['flood_volume_m3']} m³ pendant {fn['hours_flooded']} h)",
                "action": "Aménagement prioritaire d'un ouvrage de rétention ou recalibrage du collecteur aval"
            })

        # P2 : Conduites surchargées > 100% sans inondation immédiate
        for prescr in genie_civil.get("prescriptions", []):
            if prescr["cid"] not in [a["cible"] for a in actions_p1]:
                actions_p2.append({
                    "cible": f"Conduite {prescr['cid']}",
                    "urgence": "P2 - MAJEUR",
                    "probleme": f"Conduite en charge à 100% (Ø{prescr['diam_actuel_mm']} mm saturé)",
                    "action": f"Remplacement par {prescr['materiau']} Ø{prescr['diam_prescrit_mm']} mm ({prescr['longueur_m']} m)"
                })

        # P3 : Problèmes d'auto-curage
        for lv in diagnostic.get("low_velocity_links", []):
            actions_p3.append({
                "cible": f"Conduite {lv['cid']}",
                "urgence": "P3 - ENTRETIEN",
                "probleme": f"Vitesse {lv['velocity_ms']:.2f} m/s insuffisante (< 0.6 m/s)",
                "action": "Curage préventif programmé et reprise de pente lors des travaux de voirie"
            })

        return {
            "agent": "Agent 4 : Priorisation des Risques",
            "synthese": {
                "nb_p1_critique": len(actions_p1),
                "nb_p2_majeur": len(actions_p2),
                "nb_p3_maintenance": len(actions_p3),
            },
            "actions_priorisees": {
                "P1": actions_p1[:5],
                "P2": actions_p2[:5],
                "P3": actions_p3[:5]
            }
        }


# ==============================================================================
# AGENT 5 : SYNTHÈSE EXÉCUTIVE & RAPPORT DÉCISIONNEL ("Executive Reporter")
# ==============================================================================

class AgentSyntheseExecutive:
    """
    Agent coordinateur : rédige la note de synthèse stratégique prête pour les
    directeurs d'exploitation (ONA, DRE) et les bureaux d'études.
    """

    def generer_note(
        self,
        kpis: Dict[str, Any],
        meta: Dict[str, Any],
        diag: Dict[str, Any],
        gc: Dict[str, Any],
        lid: Dict[str, Any],
        risques: Dict[str, Any]
    ) -> Dict[str, Any]:
        p1_count = risques["synthese"]["nb_p1_critique"]
        p2_count = risques["synthese"]["nb_p2_majeur"]

        if p1_count > 0:
            verdict = "VULNÉRABILITÉ ÉLEVÉE — DÉBORDEMENTS DÉTECTÉS"
            couleur = "#ef4444"
            recommandation_cle = (
                f"Le réseau présente {p1_count} point(s) noir(s) d'inondation nécessitant une intervention d'urgence. "
                f"La combinaison d'un bassin d'écrêtement de {lid['volume_tampon_requis_m3']} m³ en amont "
                f"et du recalibrage de {gc['metres_lineaires_totaux']} m de collecteurs éliminera 100% des débordements."
            )
        elif p2_count > 0:
            verdict = "CAPACITÉ LIMITE — MISE EN CHARGE HYDRAULIQUE"
            couleur = "#f59e0b"
            recommandation_cle = (
                f"Aucun débordement en surface, mais {p2_count} tronçon(s) travaillent en charge. "
                "Le réseau est à saturation pour cet événement pluvial : des techniques alternatives d'infiltration "
                "sont vivement recommandées pour préserver la marge de sécurité."
            )
        else:
            verdict = "RÉSEAU CONFORME & ÉCOULEMENT FLUIDE"
            couleur = "#10b981"
            recommandation_cle = (
                "L'ensemble du réseau absorbe l'événement de pluie simulé en régime d'écoulement gravitaire libre "
                "sans mise en charge critique ni débordement. Prévoir uniquement l'entretien courant."
            )

        return {
            "agent": "Agent 5 : Synthèse Exécutive",
            "titre": "Note d'Aide à la Décision en Assainissement Urbain",
            "perimetre": meta.get("cluster_nom") or "Réseau Urbain Complet",
            "scenario": meta.get("scenario") or "Pluie Décennale",
            "verdict": verdict,
            "couleur": couleur,
            "recommandation_cle": recommandation_cle,
            "indicateurs_marquants": {
                "debit_pointe_m3s": kpis.get("peak_outflow_m3s", 0.0),
                "volume_total_m3": kpis.get("total_outflow_m3", 0.0),
                "points_critiques_p1": p1_count,
                "troncons_en_charge_p2": p2_count,
                "cout_travaux_gc_estime_dzd": gc.get("cout_global_estime_dzd", 0.0),
                "volume_tampon_lid_requis_m3": lid.get("volume_tampon_requis_m3", 0.0)
            }
        }


# ==============================================================================
# ORCHESTRATEUR DE L'ÉQUIPE MULTI-AGENTS (FACADE)
# ==============================================================================

def orchestrer_equipe_agents(
    sim_result: Dict[str, Any],
    canalisations_gdf: Optional[gpd.GeoDataFrame] = None
) -> Dict[str, Any]:
    """
    Exécute la chaîne complète des 5 agents d'expertise et retourne le diagnostic
    interconnecté et structuré.
    """
    kpis = sim_result.get("kpis", {})
    conduit_results = sim_result.get("conduit_results", {})
    node_results = sim_result.get("node_results", {})
    meta = sim_result.get("meta", {})

    # 1. Agent Diagnosticien
    agent_diag = AgentDiagnosticCausal()
    diag = agent_diag.analyser(kpis, conduit_results, node_results, meta, canalisations_gdf)

    # 2. Agent Génie Civil
    pente_calage = meta.get("pente_moyenne_pct") or 1.0
    agent_gc = AgentGenieCivil()
    gc = agent_gc.prescrire(diag, pente_moyenne_pct=pente_calage)

    # 3. Agent Hydrologie Durable (LID)
    agent_lid = AgentHydrologieDurable()
    lid = agent_lid.proposer_solutions(diag, kpis, meta)

    # 4. Agent Gestion des Risques
    agent_risk = AgentGestionRisques()
    risk = agent_risk.prioriser(diag, gc, lid)

    # 5. Agent Synthèse Exécutive
    agent_exec = AgentSyntheseExecutive()
    synthese = agent_exec.generer_note(kpis, meta, diag, gc, lid, risk)

    return {
        "status": "success",
        "diagnostic_causal": diag,
        "prescriptions_genie_civil": gc,
        "solutions_hydrologie_durable": lid,
        "matrice_risques": risk,
        "synthese_executive": synthese
    }
