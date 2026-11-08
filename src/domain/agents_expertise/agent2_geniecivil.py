"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Hakim / Équipe DrainPilot
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Agent 2 - Génie civil, dimensionnement Manning-Strickler et BPU Algérie
================================================================================
"""

import math
from typing import Dict, Any, List, Optional
from .common import formater_cout_dzd


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
                "upstream": str(item.get("upstream", "")),
                "downstream": str(item.get("downstream", "")),
                "flow_ratio": flow_ratio,
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
                f"{formater_cout_dzd(cout_total_estime_dzd)} (décomposé en terrassement/blindage 30%, fourniture 35%, pose/remblai 20%, et réfection chaussée 15%)."
            )
        else:
            note_technique = (
                "L'évaluation de la capacité gravitaire confirme que les collecteurs existants présentent un gabarit hydraulique suffisant. "
                "Aucun recalibrage structurel lourd n'est requis sous cette intensité de pluie."
            )

        return {
            "agent": "Agent 2 : Génie Civil & Dimensionnement",
            "statut": "Prescriptions établies",
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
