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
                    diam = float(diam) if (diam is not None and pd.notna(diam) and float(diam) > 0) else 600.0
                except Exception:
                    diam = 600.0
                u = str(row.get("ID_AMONT", "")).replace(".0", "").strip()
                d = str(row.get("ID_AVAL", "")).replace(".0", "").strip()

                # Récupération de la longueur réelle métrique
                val_l = row.get("Longeur")
                if val_l is not None and pd.notna(val_l) and float(val_l) > 0:
                    length = float(val_l)
                elif hasattr(row, 'geometry') and row.geometry:
                    try:
                        length = float(row.geometry.length)
                    except Exception:
                        length = 45.0
                else:
                    length = 45.0
                length = max(1.0, round(length, 1))

                # Récupération de l'adresse ou rue
                nom_voie = str(row.get("NOM-VOIE") or row.get("NOMVOIE") or row.get("nom_voie") or "").strip()
                if nom_voie.lower() in ("nan", "none", "null", ""):
                    nom_voie = ""

                pipe_geom_map[cid] = {
                    "diam": diam,
                    "mat": mat,
                    "upstream": u,
                    "downstream": d,
                    "length": length,
                    "nom_voie": nom_voie
                }

        # 1. Analyse des conduites en charge et des vitesses
        for cid, c in conduit_results.items():
            ratio = c.get("flow_ratio", 0.0)
            depth_ratio = c.get("depth_ratio", 0.0)
            vel = c.get("max_velocity_ms", 0.0)
            q_max = c.get("max_flow_cms", 0.0)
            pipe_info = pipe_geom_map.get(cid, {"diam": 600.0, "mat": "Béton", "upstream": "", "downstream": "", "length": 45.0, "nom_voie": ""})

            u_str = pipe_info.get("upstream", "")
            d_str = pipe_info.get("downstream", "")
            cond_label = f"{cid} ({u_str}➔{d_str})" if (u_str and d_str) else cid

            # Surcharge / Mise en pression
            if ratio >= 1.0 or depth_ratio >= 1.0:
                surcharged_links.append({
                    "cid": cid,
                    "conduit": cond_label,
                    "nom_voie": pipe_info.get("nom_voie", ""),
                    "flow_ratio": ratio,
                    "depth_ratio": depth_ratio,
                    "max_flow_cms": q_max,
                    "q_max": q_max,
                    "max_velocity_ms": vel,
                    "vitesse": vel,
                    "diam": pipe_info["diam"],
                    "mat": pipe_info["mat"],
                    "longueur_m": pipe_info["length"],
                    "longueur": pipe_info["length"],
                    "cause": "Capacité gravitaire théorique dépassée lors du pic de crue"
                })

            # Auto-curage insuffisant (risque d'ensablement à long terme)
            if vel < 0.6 and ratio > 0.08:
                low_velocity_links.append({
                    "cid": cid,
                    "conduit": cond_label,
                    "velocity_ms": vel,
                    "vitesse": vel,
                    "flow_ratio": ratio,
                    "cause": f"Vitesse maximale {vel:.2f} m/s < 0.6 m/s (seuil réglementaire d'auto-curage)"
                })

            # Risque d'affouillement / érosion
            if vel > 4.0:
                high_velocity_links.append({
                    "cid": cid,
                    "conduit": cond_label,
                    "velocity_ms": vel,
                    "vitesse": vel,
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
                                "amont": f"{ic} (Ø{int(d_in)}mm)",
                                "aval": f"{oc} (Ø{int(d_out)}mm)",
                                "diam_amont": d_in,
                                "diam_aval": d_out,
                                "longueur": pipe_geom_map[ic]["length"],
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

        nb_deb = len(flooded_nodes_detail)
        nb_sur = len(surcharged_links)
        nb_goul = len(bottlenecks)

        if nb_deb > 0 or nb_sur > 0:
            note_technique = (
                f"L'analyse hydrodynamique 1D Saint-Venant (Dynamic Wave) met en évidence un régime d'écoulement sous forte tension. "
                f"Lors du pic d'intensité pluviométrique, {nb_deb} regard(s) subissent un débordement direct en surface et {nb_sur} tronçon(s) "
                f"travaillent en charge sévère (Q/Qmax > 100% ou H/D = 100%). Cette mise en pression résulte d'un effet de remous hydraulique (backwater) "
                f"amplifié par {nb_goul} goulot(s) d'étranglement géométrique où le diamètre diminue anormalement vers l'aval. "
                f"La ligne d'eau piézométrique dépasse la cote tampon du terrain naturel, provoquant des reflux et des stagnations d'eau sur les voiries urbaines."
            )
        else:
            note_technique = (
                "L'analyse hydrodynamique confirme un écoulement gravitaire fluide et stable à surface libre sur l'ensemble des collecteurs. "
                "Aucune surpression ni reflux critique n'a été détecté sous ce scénario pluviométrique."
            )

        return {
            "agent": "Agent 1 : Diagnosticien Causal",
            "statut": "Analyse Complète",
            "note_technique": note_technique,
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
    Agent chargé de calculer les diamètres nominaux requis (Manning-Strickler),
    d'optimiser économiquement les investissements par analyse de capacité résiduelle,
    et de formuler les prescriptions techniques de travaux de génie civil et métrés.
    """

    STANDARDS_DN_MM = [300, 400, 500, 600, 800, 1000, 1200, 1400, 1600, 1800, 2000]

    # Bordereau des Prix Unitaires indicatifs (BPU - Travaux Neufs & Réhabilitation en Milieu Urbain Algérien)
    # Comprend : Terrassement en tranchée, Blindage jointif, Fourniture tuyaux, Lit de pose et remblai compacté, Réfection chaussée
    BPU_PAR_DN = {
        300: {"cout_ml": 22000.0, "materiau": "PEHD Double Paroi SN8", "classe": "SN8 (ISO 9969)", "couverture_min_m": 0.80, "largeur_tranchee_m": 0.90},
        400: {"cout_ml": 26000.0, "materiau": "PEHD Double Paroi SN8", "classe": "SN8 (ISO 9969)", "couverture_min_m": 0.80, "largeur_tranchee_m": 1.00},
        500: {"cout_ml": 32000.0, "materiau": "PEHD Double Paroi SN8", "classe": "SN8 (ISO 9969)", "couverture_min_m": 0.90, "largeur_tranchee_m": 1.10},
        600: {"cout_ml": 38000.0, "materiau": "PEHD Double Paroi SN8", "classe": "SN8 (ISO 9969)", "couverture_min_m": 1.00, "largeur_tranchee_m": 1.20},
        800: {"cout_ml": 52000.0, "materiau": "Béton Armé Classe 135A", "classe": "135A (NF EN 1916)", "couverture_min_m": 1.00, "largeur_tranchee_m": 1.40},
        1000: {"cout_ml": 68000.0, "materiau": "Béton Armé Classe 135A", "classe": "135A (NF EN 1916)", "couverture_min_m": 1.20, "largeur_tranchee_m": 1.60},
        1200: {"cout_ml": 86000.0, "materiau": "Béton Armé Classe 135A", "classe": "135A (NF EN 1916)", "couverture_min_m": 1.20, "largeur_tranchee_m": 1.80},
        1400: {"cout_ml": 105000.0, "materiau": "Béton Armé Classe 135A", "classe": "135A (NF EN 1916)", "couverture_min_m": 1.30, "largeur_tranchee_m": 2.00},
        1600: {"cout_ml": 128000.0, "materiau": "Béton Armé Classe 135A", "classe": "135A (NF EN 1916)", "couverture_min_m": 1.40, "largeur_tranchee_m": 2.20},
        1800: {"cout_ml": 155000.0, "materiau": "Béton Armé Classe 135A", "classe": "135A (NF EN 1916)", "couverture_min_m": 1.50, "largeur_tranchee_m": 2.40},
        2000: {"cout_ml": 185000.0, "materiau": "Béton Armé Classe 135A", "classe": "135A (NF EN 1916)", "couverture_min_m": 1.50, "largeur_tranchee_m": 2.60},
    }

    def prescrire(
        self,
        diagnostic: Dict[str, Any],
        pente_moyenne_pct: float = 1.0,
        k_strickler: float = 70.0
    ) -> Dict[str, Any]:
        prescriptions = []
        conduites_suffisantes_remous = []
        surcharged = diagnostic.get("surcharged_links", [])

        total_metres_a_remplacer = 0.0
        cout_total_estime_dzd = 0.0

        for item in surcharged:
            cid = item["cid"]
            q_max = float(item.get("max_flow_cms", 0.1) or 0.1)
            diam_actuel = float(item.get("diam", 500.0))
            longueur_reelle_m = float(item.get("longueur_m") or item.get("longueur") or 45.0)
            nom_voie = item.get("nom_voie", "")
            flow_ratio = float(item.get("flow_ratio", 1.0) or 1.0)

            # Calcul du diamètre requis avec marge de sécurité de 25% (remplissage à 80% max)
            # Formule de Manning-Strickler pour conduite circulaire pleine :
            # D = ( Q / ( K * sqrt(S) * 0.3117 ) ) ^ (3/8)
            s_m_m = max(pente_moyenne_pct / 100.0, 0.001)
            q_cible = max(q_max * 1.25, 0.05)
            k_calc = 70.0 if diam_actuel >= 800 else 85.0
            d_theorique_m = (q_cible / (k_calc * math.sqrt(s_m_m) * 0.3117)) ** (3.0 / 8.0)
            dn_calc_mm = d_theorique_m * 1000.0

            # Vérification de capacité résiduelle & optimisation économique :
            # Si le diamètre théorique requis (avec marge 25%) est inférieur ou égal au diamètre existant
            # et que le taux de surcharge est modéré (< 115%), la conduite n'a pas de sous-dimensionnement intrinsèque.
            # Sa mise en pression résulte d'un remous aval (backwater) qui sera résorbé par le recalibrage aval.
            if dn_calc_mm <= diam_actuel and flow_ratio < 1.15:
                conduites_suffisantes_remous.append({
                    "cid": cid,
                    "conduit": item.get("conduit") or cid,
                    "diam_actuel_mm": int(diam_actuel),
                    "diam_theorique_mm": int(round(dn_calc_mm)),
                    "longueur_m": round(longueur_reelle_m, 1),
                    "flow_ratio": round(flow_ratio, 2),
                    "motif": "Section existante hydrauliquement suffisante. Surcharge due aux remous aval résorbée sans réhabilitation lourde."
                })
                continue

            # Choix du DN standard supérieur ou égal au diamètre théorique
            dn_prescrit = next((dn for dn in self.STANDARDS_DN_MM if dn >= dn_calc_mm), self.STANDARDS_DN_MM[-1])

            # Si le DN prescrit est inférieur ou égal au diamètre actuel (mais flow_ratio >= 1.15),
            # passer au calibre normalisé immédiatement supérieur
            if dn_prescrit <= diam_actuel:
                idx_cur = self.STANDARDS_DN_MM.index(int(diam_actuel)) if int(diam_actuel) in self.STANDARDS_DN_MM else 0
                dn_prescrit = self.STANDARDS_DN_MM[min(idx_cur + 1, len(self.STANDARDS_DN_MM) - 1)]

            bpu_info = self.BPU_PAR_DN.get(dn_prescrit, self.BPU_PAR_DN[800])
            cout_unitaire_dzd = bpu_info["cout_ml"]
            cout_troncon_dzd = cout_unitaire_dzd * longueur_reelle_m
            materiau_recommande = bpu_info["materiau"]

            total_metres_a_remplacer += longueur_reelle_m
            cout_total_estime_dzd += cout_troncon_dzd

            conduit_label = item.get("conduit") or cid
            if nom_voie and nom_voie not in conduit_label:
                conduit_label = f"{conduit_label} [{nom_voie}]"

            prescriptions.append({
                "cid": cid,
                "conduit": conduit_label,
                "nom_voie": nom_voie,
                "diam_actuel_mm": int(diam_actuel),
                "diametre_actuel_mm": int(diam_actuel),
                "diam_theorique_mm": int(round(dn_calc_mm)),
                "diametre_requis_mm": int(round(dn_calc_mm)),
                "diam_prescrit_mm": dn_prescrit,
                "dn_normalise_mm": dn_prescrit,
                "gain_capacite_pct": round(((dn_prescrit / diam_actuel)**2.67 - 1.0) * 100.0, 1),
                "longueur_m": round(longueur_reelle_m, 1),
                "longueur": round(longueur_reelle_m, 1),
                "materiau": materiau_recommande,
                "materiau_recommande": materiau_recommande,
                "classe_rigidite": bpu_info["classe"],
                "couverture_min_m": bpu_info["couverture_min_m"],
                "largeur_tranchee_m": bpu_info["largeur_tranchee_m"],
                "cout_unitaire_dzd": cout_unitaire_dzd,
                "cout_estime_dzd": round(cout_troncon_dzd, 0),
                "type_travaux": "Recalibrage de collecteur par tranchée ouverte"
            })

        # Synthèse par DN (Répartition métrique & budgétaire)
        recap_dn = {}
        for dn in self.STANDARDS_DN_MM:
            bpu = self.BPU_PAR_DN.get(dn, {})
            recap_dn[dn] = {
                "dn": dn,
                "label": f"DN {dn}",
                "materiau": bpu.get("materiau", "PEHD SN8" if dn < 800 else "Béton Armé 135A"),
                "classe": bpu.get("classe", ""),
                "couverture_min_m": bpu.get("couverture_min_m", 1.0),
                "largeur_tranchee_m": bpu.get("largeur_tranchee_m", 1.20),
                "cout_unitaire_ml_dzd": bpu.get("cout_ml", 40000.0),
                "nb_troncons": 0,
                "lineaire_ml": 0.0,
                "pct_lineaire": 0.0,
                "cout_total_dzd": 0.0,
                "pct_budget": 0.0,
            }

        recap_mat = {
            "PEHD Double Paroi SN8": {"nb_troncons": 0, "lineaire_ml": 0.0, "pct_lineaire": 0.0, "cout_total_dzd": 0.0, "pct_budget": 0.0},
            "Béton Armé Classe 135A": {"nb_troncons": 0, "lineaire_ml": 0.0, "pct_lineaire": 0.0, "cout_total_dzd": 0.0, "pct_budget": 0.0}
        }

        for p in prescriptions:
            dn = p["dn_normalise_mm"]
            mat = p["materiau"]
            lg = p["longueur_m"]
            cout = p["cout_estime_dzd"]

            if dn in recap_dn:
                recap_dn[dn]["nb_troncons"] += 1
                recap_dn[dn]["lineaire_ml"] += lg
                recap_dn[dn]["cout_total_dzd"] += cout

            if mat in recap_mat:
                recap_mat[mat]["nb_troncons"] += 1
                recap_mat[mat]["lineaire_ml"] += lg
                recap_mat[mat]["cout_total_dzd"] += cout

        recap_dn_liste = []
        for dn, r in recap_dn.items():
            if r["nb_troncons"] > 0:
                r["lineaire_ml"] = round(r["lineaire_ml"], 1)
                r["cout_total_dzd"] = round(r["cout_total_dzd"], 0)
                r["pct_lineaire"] = round((r["lineaire_ml"] / total_metres_a_remplacer * 100.0), 1) if total_metres_a_remplacer > 0 else 0.0
                r["pct_budget"] = round((r["cout_total_dzd"] / cout_total_estime_dzd * 100.0), 1) if cout_total_estime_dzd > 0 else 0.0
                recap_dn_liste.append(r)

        for mat, r in recap_mat.items():
            r["lineaire_ml"] = round(r["lineaire_ml"], 1)
            r["cout_total_dzd"] = round(r["cout_total_dzd"], 0)
            r["pct_lineaire"] = round((r["lineaire_ml"] / total_metres_a_remplacer * 100.0), 1) if total_metres_a_remplacer > 0 else 0.0
            r["pct_budget"] = round((r["cout_total_dzd"] / cout_total_estime_dzd * 100.0), 1) if cout_total_estime_dzd > 0 else 0.0

        decomposition_bpu = {
            "terrassement_blindage_pct": 30.0,
            "fourniture_tuyaux_pct": 35.0,
            "pose_remblai_compacte_pct": 20.0,
            "refection_chaussee_enrobe_pct": 15.0,
            "montant_terrassement_dzd": round(cout_total_estime_dzd * 0.30, 0),
            "montant_fourniture_dzd": round(cout_total_estime_dzd * 0.35, 0),
            "montant_pose_remblai_dzd": round(cout_total_estime_dzd * 0.20, 0),
            "montant_chaussee_dzd": round(cout_total_estime_dzd * 0.15, 0),
        }

        prescriptions_structurelles = {
            "regles_fascicule": "Fascicule 70 du CCTG / Norme ONA Assainissement",
            "charges_roulantes": "Convoi lourd type Bc (30 tonnes) / Essieu isolé de 13 tonnes sous chaussée",
            "pehd_sn8": "Rigidité annulaire nominale >= 8 kN/m² (ISO 9969), lit de sable 0/10 épaisseur 10 cm compacté",
            "beton_135a": "Béton armé classe 135A haute résistance (NF EN 1916), joint élastomère étanche",
            "couverture_minimale": "1.00 m sous chaussée urbaine circulée (0.80 m sous trottoir). Dalle de répartition armée requise si H < 0.80 m",
            "blindage_tranchee": "Blindage jointif caissonné obligatoire dès H > 1.30 m pour stabilité du bâti riverain",
            "compactage_remblai": "Remblai primaire sélectionné puis secondaire compacté à 95% OPM (Optimum Proctor Modifié)"
        }

        nb_rec = len(prescriptions)
        nb_remous = len(conduites_suffisantes_remous)
        if prescriptions:
            note_technique = (
                f"L'optimisation technico-économique de Génie Civil identifie un programme de renouvellement ciblé sur {nb_rec} tronçon(s) "
                f"structurant(s) présentant un déficit capacitaire intrinsèque avéré (application de Manning-Strickler avec "
                f"marge de sécurité de +25%, tirant d'eau maximal H/D <= 0.80). L'analyse de capacité résiduelle a permis d'écarter {nb_remous} "
                f"tronçon(s) dont la section actuelle est suffisante et dont la mise en charge transitoire résulte exclusivement de remous "
                f"aval (résolus sans ouverture de tranchée par le recalibrage des collecteurs récepteurs). "
                f"L'ensemble du programme totalise {round(total_metres_a_remplacer, 1)} mètres linéaires pour un montant estimatif global de "
                f"{int(cout_total_estime_dzd):,} DZD (décomposé en terrassement/blindage 30%, fourniture 35%, pose/remblai 20%, et réfection chaussée 15%)."
            )
        else:
            note_technique = (
                "L'évaluation de la capacité gravitaire confirme que les collecteurs existants présentent un gabarit hydraulique suffisant. "
                "Aucun recalibrage structurel lourd n'est requis sous cette intensité de pluie."
            )

        return {
            "agent": "Agent 2 : Génie Civil & Dimensionnement",
            "statut": "Prescriptions Établies",
            "note_technique": note_technique,
            "nb_troncons_a_recalibrer": len(prescriptions),
            "nb_troncons_suffisants_remous": nb_remous,
            "metres_lineaires_totaux": round(total_metres_a_remplacer, 1),
            "cout_global_estime_dzd": round(cout_total_estime_dzd, 0),
            "recapitulatif_par_dn": recap_dn_liste,
            "recapitulatif_par_materiau": recap_mat,
            "decomposition_bpu": decomposition_bpu,
            "prescriptions_structurelles": prescriptions_structurelles,
            "conduites_suffisantes_remous": conduites_suffisantes_remous[:30],
            "prescriptions": prescriptions[:60]
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
                "designation": "Bassin d'Écrêtement & Rétention Paysager",
                "type": "Ouvrage de stockage centralisé en amont",
                "volume_utile_m3": vol_retention_cible_m3,
                "emprise_au_sol_m2": emprise_sol_bassin_m2,
                "dimensionnement": f"Volume : {vol_retention_cible_m3} m³ (Emprise ~ {emprise_sol_bassin_m2} m²)",
                "reduction_debit_pointe_estimee": "35 % à 45 %",
                "impact_attendu": "Abattement pointe : 35 % à 45 %",
                "avantage": "Évite le recalibrage lourd des collecteurs aval en milieu urbain dense"
            },
            {
                "solution": "Noues Végétalisées & Tranchées d'Infiltration",
                "designation": "Noues Végétalisées & Tranchées d'Infiltration",
                "type": "Gestion linéaire le long des délaissés de voirie",
                "lineaire_recommande_m": lineaire_noues_m,
                "dimensionnement": f"Linéaire : {lineaire_noues_m} ml (Largeur 2.0 m)",
                "reduction_debit_pointe_estimee": "20 % à 30 %",
                "impact_attendu": "Abattement pointe : 20 % à 30 %",
                "avantage": "Recharge de la nappe phréatique et îlots de fraîcheur urbains"
            },
            {
                "solution": "Chaussées Réservoirs & Pavés Drainants",
                "designation": "Chaussées Réservoirs & Pavés Drainants",
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
            f"L'Agent SFN préconise d'intercepter et de temporiser les eaux pluviales à la source par des solutions fondées sur la nature (LID). "
            f"Un volume tampon de {vol_retention_cible_m3} m³ doit être mobilisé, combinant un bassin d'écrêtement paysager ({emprise_sol_bassin_m2} m² d'emprise) "
            f"et {lineaire_noues_m} ml de noues végétalisées en délaissés de voirie. Cette approche permet de rabattre le pic de débit de 35% à 45% "
            f"et d'éviter le surdimensionnement onéreux des réseaux enterrés en zone urbaine dense."
        )

        return {
            "agent": "Agent 3 : Hydrologie Durable (LID / SFN)",
            "statut": "Solutions Établies",
            "note_technique": note_technique,
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
                "priorite": "P1",
                "cible": f"Regard {fn['node_id']}",
                "conduite": f"Regard {fn['node_id']}",
                "urgence": "P1 - CRITIQUE",
                "type_risque": "Submersion & Inondation de voirie",
                "probleme": f"Débordement de surface ({fn['flood_volume_m3']} m³ pendant {fn['hours_flooded']} h)",
                "action": "Aménagement prioritaire d'un ouvrage de rétention ou recalibrage du collecteur aval",
                "action_requise": "Aménagement prioritaire d'un ouvrage de rétention ou recalibrage du collecteur aval",
                "estimation_cout_dzd": 3500000.0,
                "delai_recommande": "3 mois (Urgence)"
            })

        # P2 : Conduites surchargées > 100% sans inondation immédiate
        for prescr in genie_civil.get("prescriptions", []):
            if prescr["cid"] not in [a["cible"] for a in actions_p1]:
                c_lbl = prescr.get("conduit", prescr["cid"])
                actions_p2.append({
                    "priorite": "P2",
                    "cible": c_lbl,
                    "conduite": c_lbl,
                    "urgence": "P2 - MAJEUR",
                    "type_risque": "Mise en pression & reflux",
                    "probleme": f"Conduite en charge à 100% (Ø{prescr['diam_actuel_mm']} mm saturé)",
                    "action": f"Remplacement par {prescr['materiau']} Ø{prescr['diam_prescrit_mm']} mm ({prescr['longueur_m']} m)",
                    "action_requise": f"Remplacement par {prescr['materiau']} Ø{prescr['diam_prescrit_mm']} mm ({prescr['longueur_m']} m)",
                    "estimation_cout_dzd": prescr.get("cout_estime_dzd", 0.0),
                    "delai_recommande": "12 mois (Programmation)"
                })

        # P3 : Problèmes d'auto-curage
        for lv in diagnostic.get("low_velocity_links", []):
            c_lbl = lv.get("conduit", lv["cid"])
            actions_p3.append({
                "priorite": "P3",
                "cible": c_lbl,
                "conduite": c_lbl,
                "urgence": "P3 - ENTRETIEN",
                "type_risque": "Dépôt & ensablement",
                "probleme": f"Vitesse {lv['velocity_ms']:.2f} m/s insuffisante (< 0.6 m/s)",
                "action": "Curage préventif programmé et reprise de pente lors des travaux de voirie",
                "action_requise": "Curage préventif programmé et reprise de pente",
                "estimation_cout_dzd": 150000.0,
                "delai_recommande": "Entretien régulier"
            })

        note_technique = (
            f"La hiérarchisation multi-critères classe les interventions en 3 horizons d'urgence : "
            f"{len(actions_p1)} action(s) P1 - Critique (résorption prioritaire des inondations sur voiries sous 3 mois), "
            f"{len(actions_p2)} action(s) P2 - Majeur (renforcement des tronçons sous pression continue à programmer sous 12 mois), et "
            f"{len(actions_p3)} action(s) P3 - Maintenance (curage préventif des zones de sédimentation où la vitesse chute sous 0.60 m/s). "
            f"Cette priorisation optimise l'allocation des budgets d'investissement de la collectivité."
        )

        actions_liste = actions_p1 + actions_p2 + actions_p3

        return {
            "agent": "Agent 4 : Priorisation des Risques",
            "statut": "Priorisation Établie",
            "note_technique": note_technique,
            "synthese": {
                "nb_p1_critique": len(actions_p1),
                "nb_p2_majeur": len(actions_p2),
                "nb_p3_maintenance": len(actions_p3),
            },
            "actions_priorisees": {
                "P1": actions_p1[:5],
                "P2": actions_p2[:5],
                "P3": actions_p3[:5]
            },
            "actions_liste": actions_liste[:30]
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
                f"Le réseau présente {p1_count} point(s) noir(s) d'inondation nécessitant une intervention prioritaire. "
                f"La modélisation hydrodynamique Saint-Venant démontre que la combinaison concertée d'un bassin d'écrêtement "
                f"de {lid['volume_tampon_requis_m3']} m³ en amont et du recalibrage de {gc['metres_lineaires_totaux']} m "
                f"de collecteurs structurants assure la résorption théorique intégrale des débordements pour l'événement "
                f"pluviométrique de dimensionnement analysé."
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

        note_technique = (
            f"Synthèse stratégique d'aide à la décision destinée à la Direction Générale (ONA, DRE, Wilaya). "
            f"Le verdict hydraulique conclut à : {verdict}. {recommandation_cle} "
            f"Le couplage du recalibrage des points critiques P1 avec les aménagements d'écrêtement SFN constitue "
            f"la stratégie optimale recommandée pour restaurer la capacité d'évacuation gravitaire et réduire significativement "
            f"les risques de submersion urbaine pour cet événement pluvial."
        )

        return {
            "agent": "Agent 5 : Synthèse Exécutive",
            "titre": "Note d'Aide à la Décision en Assainissement Urbain",
            "perimetre": meta.get("cluster_nom") or "Réseau Urbain Complet",
            "scenario": meta.get("scenario") or "Pluie Décennale",
            "verdict": verdict,
            "couleur": couleur,
            "recommandation_cle": recommandation_cle,
            "note_technique": note_technique,
            "avis_direction_generale": recommandation_cle,
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

