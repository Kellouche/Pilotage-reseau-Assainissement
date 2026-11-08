# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Analyseur et parseur du fichier de rapport officiel EPA SWMM 5.2 (.RPT)
================================================================================
"""

import re
import logging
from typing import Dict, Any

logger = logging.getLogger("swmm_platform.moteur_swmm.analyse_rapport")


def analyser_rapport_swmm_impl(rpt_text: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse et extrait les indicateurs clés (KPIs) et les résultats cartographiques
    détaillés par conduite et par regard depuis le rapport officiel EPA SWMM.
    """
    kpis = {
        "meta": meta,
        "routing_continuity_error_pct": 0.0,
        "runoff_continuity_error_pct": 0.0,
        "total_precipitation_mm": 0.0,
        "total_runoff_volume_m3": 0.0,
        "total_outflow_m3": 0.0,
        "peak_outflow_m3s": 0.0,
        "flooded_nodes_count": 0,
        "surcharged_nodes_count": 0,
        "flooded_nodes": [],
        "node_results": {},
        "conduit_results": {},
        "compliance_continuity": True
    }

    # 1. Continuité routage
    m_routing = re.search(r"Flow Routing Continuity.*?Continuity Error \(%\)\s*[\.]+\s+([\-\d\.]+)", rpt_text, re.DOTALL)
    if m_routing:
        kpis["routing_continuity_error_pct"] = float(m_routing.group(1))

    # 2. Continuité ruissellement
    m_runoff = re.search(r"Runoff Quantity Continuity.*?Continuity Error \(%\)\s*[\.]+\s+([\-\d\.]+)", rpt_text, re.DOTALL)
    if m_runoff:
        kpis["runoff_continuity_error_pct"] = float(m_runoff.group(1))

    # 3. Précipitations, Infiltration et Ruissellement (Bilan Hydrologique Massique)
    m_precip = re.search(r"Total Precipitation\s*[\.]+\s+([\d\.]+)\s+([\d\.]+)", rpt_text)
    if m_precip:
        kpis["total_precipitation_volume_m3"] = round(float(m_precip.group(1)) * 10000.0, 1)
        kpis["total_precipitation_mm"] = float(m_precip.group(2))
    else:
        m_precip_single = re.search(r"Total Precipitation\s*[\.]+\s+[\d\.]+\s+([\d\.]+)", rpt_text)
        if m_precip_single:
            kpis["total_precipitation_mm"] = float(m_precip_single.group(1))

    m_infil = re.search(r"Infiltration Loss\s*[\.]+\s+([\d\.]+)\s+([\d\.]+)", rpt_text)
    if m_infil:
        kpis["total_infiltration_volume_m3"] = round(float(m_infil.group(1)) * 10000.0, 1)
        kpis["total_infiltration_mm"] = float(m_infil.group(2))
    else:
        kpis["total_infiltration_volume_m3"] = 0.0

    m_surf = re.search(r"Surface Runoff\s*[\.]+\s+([\d\.]+)\s+([\d\.]+)", rpt_text)
    if m_surf:
        kpis["total_runoff_volume_m3"] = round(float(m_surf.group(1)) * 10000.0, 1)
        kpis["total_runoff_mm"] = float(m_surf.group(2))
    else:
        kpis["total_runoff_volume_m3"] = 0.0

    # Coefficient de ruissellement effectif (C_eff)
    p_mm = kpis.get("total_precipitation_mm", 0.0)
    r_mm = kpis.get("total_runoff_mm", 0.0)
    c_eff = round(r_mm / p_mm, 2) if p_mm > 0 else 0.70
    kpis["effective_runoff_coeff"] = c_eff

    # 4. Sortie totale à l'exutoire (Outflow)
    m_outflow = re.search(r"(?:External Outflow|Total Outflow)\s*[\.]+\s+([\d\.]+)(?:\s+([\d\.]+))?", rpt_text)
    if m_outflow:
        if m_outflow.group(2):
            kpis["total_outflow_m3"] = round(float(m_outflow.group(1)) * 10000.0, 1)
        else:
            kpis["total_outflow_m3"] = round(float(m_outflow.group(1)) * 1000.0, 1)

    # 5. Débit de pointe à l'exutoire (Outfall Loading Summary)
    if "Outfall Loading Summary" in rpt_text:
        m_out = re.search(r"Outfall Loading Summary.*?\n\s*-+\s*\n(.*?)(?:\n\s*\n|[A-Z][a-z]+ [A-Z]|\Z)", rpt_text, re.DOTALL)
        outfall_lines = m_out.group(1).strip().splitlines() if m_out else rpt_text.split("Outfall Loading Summary")[1].split("\n\n")[0].splitlines()
        for line in outfall_lines:
            parts = line.split()
            if len(parts) >= 4 and not parts[0].startswith("-") and parts[0] not in ("Outfall", "System", "Node"):
                node_name = parts[0]
                target_out = meta.get("outfall_code")
                target_junc = meta.get("junction_outfall_code")
                if (not target_out) or (target_out == node_name) or (target_junc == node_name) or ("OUT_" in node_name) or (kpis["peak_outflow_m3s"] == 0.0):
                    try:
                        kpis["peak_outflow_m3s"] = float(parts[3])
                    except Exception:
                        try:
                            kpis["peak_outflow_m3s"] = float(parts[2])
                        except Exception:
                            pass

    # 6. Surcharge des regards (Node Surcharge Summary)
    if "Node Surcharge Summary" in rpt_text:
        surch_part = rpt_text.split("Node Surcharge Summary")[1].split("Node Flooding Summary")[0].split("\n\n\n")[0]
        for line in surch_part.strip().splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[1] == "JUNCTION":
                nid = parts[0]
                try:
                    h_surch = float(parts[2])
                    kpis["node_results"][nid] = {
                        "node": nid,
                        "hours_surcharged": h_surch,
                        "hours_flooded": 0.0,
                        "peak_flood_flow_cms": 0.0,
                        "flood_volume_m3": 0.0,
                        "status": "surcharged" if h_surch > 0 else "normal",
                        "color": "#f59e0b" if h_surch > 0 else "#3b82f6"
                    }
                except Exception:
                    pass

    # 7. Inondations / Débordements en surface (Node Flooding Summary)
    if "Node Flooding Summary" in rpt_text:
        flood_part = rpt_text.split("Node Flooding Summary")[1].split("Outfall Loading Summary")[0]
        for line in flood_part.strip().splitlines():
            parts = line.split()
            if len(parts) >= 6 and parts[0] != "Node":
                nid = parts[0]
                try:
                    h_flood = float(parts[1])
                    pk_flood = float(parts[2])
                    vol_flood = float(parts[5]) * 1000.0
                    if h_flood > 0:
                        if vol_flood <= 0.0 and pk_flood > 0:
                            vol_estime = round(0.5 * pk_flood * (h_flood * 3600.0), 3)
                            vol_flood = max(vol_estime, 0.05)
                        else:
                            vol_flood = round(vol_flood, 3)

                        if nid not in kpis["node_results"]:
                            kpis["node_results"][nid] = {"node": nid, "hours_surcharged": h_flood}
                        kpis["node_results"][nid].update({
                            "hours_flooded": h_flood,
                            "peak_flood_flow_cms": pk_flood,
                            "flood_volume_m3": vol_flood,
                            "status": "flooded",
                            "color": "#ef4444"
                        })
                        kpis["flooded_nodes"].append(kpis["node_results"][nid])
                except Exception:
                    pass

    kpis["flooded_nodes_count"] = len(kpis["flooded_nodes"])
    kpis["surcharged_nodes_count"] = sum(1 for n in kpis["node_results"].values() if n.get("status") in ("surcharged", "flooded"))

    # 8. Taux de charge des conduites (Link Flow Summary)
    max_vel = 0.0
    peak_time_str = "00:45"
    if "Link Flow Summary" in rpt_text:
        link_part = rpt_text.split("Link Flow Summary")[1].split("Flow Classification Summary")[0].split("Conduit Surcharge Summary")[0]
        for line in link_part.strip().splitlines():
            parts = line.split()
            if len(parts) >= 8 and parts[1] == "CONDUIT":
                cid = parts[0]
                try:
                    flow_cms = float(parts[2])
                    t_occ = parts[4] if len(parts) >= 6 and ":" in parts[4] else parts[3]
                    veloc_ms = float(parts[5]) if len(parts) >= 6 and ":" in parts[4] else float(parts[4])
                    q_ratio = float(parts[6]) if len(parts) >= 8 else 0.5
                    d_ratio = float(parts[7]) if len(parts) >= 8 else 0.5

                    if veloc_ms > max_vel:
                        max_vel = veloc_ms
                    if flow_cms >= (kpis.get("peak_outflow_m3s") or 0.0) * 0.85:
                        peak_time_str = str(t_occ)

                    if q_ratio >= 1.0 or d_ratio >= 1.0:
                        c_status = "surcharge"
                        color = "#ef4444"
                        label = "Surcharge (> 100%)"
                    elif q_ratio >= 0.8 or d_ratio >= 0.8:
                        c_status = "critique"
                        color = "#f97316"
                        label = "Critique (80-100%)"
                    elif q_ratio >= 0.5 or d_ratio >= 0.5:
                        c_status = "moderee"
                        color = "#facc15"
                        label = "Modéré (50-80%)"
                    else:
                        c_status = "normal"
                        color = "#10b981"
                        label = "Normal (< 50%)"

                    c_endpoints = meta.get("conduit_endpoints", {}).get(cid, {})
                    u_str = str(c_endpoints.get("u", "") or "")
                    d_str = str(c_endpoints.get("d", "") or "")
                    cond_name = f"{cid} ({u_str}➔{d_str})" if (u_str and d_str) else cid
                    kpis["conduit_results"][cid] = {
                        "link_id": cid,
                        "conduit": cond_name,
                        "u_node": u_str,
                        "d_node": d_str,
                        "length": c_endpoints.get("length", 45.0),
                        "diam_mm": c_endpoints.get("diam_mm", 600.0),
                        "material": c_endpoints.get("material", "Béton"),
                        "nom_voie": c_endpoints.get("nom_voie", ""),
                        "max_flow_cms": flow_cms,
                        "max_velocity_ms": veloc_ms,
                        "time_of_max": str(t_occ),
                        "flow_ratio": round(q_ratio, 2),
                        "depth_ratio": round(d_ratio, 2),
                        "status": c_status,
                        "label": label,
                        "color": color
                    }
                except Exception:
                    pass

    kpis["max_velocity_ms"] = round(max_vel, 2)
    kpis["peak_time_str"] = peak_time_str

    if max_vel < 0.60:
        kpis["autocurage_statut"] = "Faible (< 0.6 m/s)"
        kpis["autocurage_color"] = "#f59e0b"
        kpis["autocurage_note"] = "Risque d'ensablement ou de décantation dans les conduites."
    elif max_vel <= 4.0:
        kpis["autocurage_statut"] = "Optimal (0.6 - 4.0 m/s)"
        kpis["autocurage_color"] = "#10b981"
        kpis["autocurage_note"] = "Vitesse d'autocurage conforme aux règles de l'art."
    else:
        kpis["autocurage_statut"] = "Excessif (> 4.0 m/s)"
        kpis["autocurage_color"] = "#f87171"
        kpis["autocurage_note"] = "Risque d'abrasion et de dégradation mécanique des parois."

    tot_len = sum(float(c.get("length", 0.0)) for c in kpis["conduit_results"].values())
    surch_len = sum(float(c.get("length", 0.0)) for c in kpis["conduit_results"].values() if c.get("depth_ratio", 0) >= 1.0 or c.get("flow_ratio", 0) >= 1.0)
    kpis["total_network_length_m"] = round(tot_len, 1)
    kpis["surcharged_length_m"] = round(surch_len, 1)
    kpis["surcharged_length_pct"] = round((surch_len / tot_len) * 100.0, 1) if tot_len > 0 else 0.0

    # Cohérence Pluie-Débit (Méthode Rationnelle)
    area_ha = float(meta.get("total_area_ha") or 0.0)
    i_max = float(meta.get("pluvio_intensite_max_mmh") or 62.0)
    c_eff = float(kpis.get("effective_runoff_coeff") or 0.70)
    q_rat = round((c_eff * i_max * area_ha) / 360.0, 3)
    q_sim = round(float(kpis.get("peak_outflow_m3s") or 0.0), 3)
    ratio_coh = round(q_sim / q_rat, 2) if q_rat > 0 else 1.0

    if 0.65 <= ratio_coh <= 1.45:
        coh_st = "COHERENT"
        coh_badge = "✅ Cohérent"
        coh_col = "#10b981"
        coh_msg = f"Le débit de pointe simulé ({q_sim} m³/s) est en étroite cohérence avec le débit rationnel attendu ({q_rat} m³/s) pour une pluie de {i_max} mm/h sur {area_ha} ha (Ceff = {c_eff})."
    elif ratio_coh > 1.45:
        coh_st = "SUR-EVALUE"
        coh_badge = "⚠️ Pic supérieur au rationnel"
        coh_col = "#f59e0b"
        coh_msg = f"Le débit simulé ({q_sim} m³/s) est supérieur au débit théorique direct ({q_rat} m³/s pour Imax = {i_max} mm/h). Ce pic peut provenir d'une concentration d'apports amont ou d'un tronçon raide court."
    else:
        coh_st = "AMORTI"
        coh_badge = "ℹ️ Laminé en réseau"
        coh_col = "#38bdf8"
        coh_msg = f"Le débit simulé ({q_sim} m³/s) est inférieur au débit rationnel brut ({q_rat} m³/s pour Imax = {i_max} mm/h), traduisant un laminage hydraulique important et un stockage temporaire dans les collecteurs."

    kpis["coherence_pluie_debit"] = {
        "q_simule_m3s": q_sim,
        "q_rationnel_m3s": q_rat,
        "ratio": ratio_coh,
        "statut": coh_st,
        "badge": coh_badge,
        "color": coh_col,
        "message": coh_msg
    }

    kpis["typologie_sol"] = meta.get("typologie_sol")
    kpis["typologie_nom"] = meta.get("typologie_nom")
    kpis["imperv_pct"] = meta.get("imperv_pct")

    kpis["pluvio_station"] = meta.get("pluvio_station")
    kpis["pluvio_station_id"] = meta.get("pluvio_station_id")
    kpis["pluvio_code_anrh"] = meta.get("pluvio_code_anrh")
    kpis["pluvio_wilaya"] = meta.get("pluvio_wilaya")
    kpis["pluvio_scenario_nom"] = meta.get("pluvio_scenario_nom")
    kpis["pluvio_periode_retour"] = meta.get("pluvio_periode_retour")
    kpis["pluvio_intensite_max_mmh"] = i_max
    kpis["pluvio_montana"] = meta.get("pluvio_montana")
    kpis["pluvio_hauteur_totale_mm"] = meta.get("pluvio_hauteur_totale_mm")
    kpis["pluvio_p24_mm"] = meta.get("pluvio_p24_mm")
    kpis["pluvio_source"] = meta.get("pluvio_source")

    # Bilan Hydraulique & Débit dérivé par les ouvrages spéciaux
    q_deleste_tot = sum(
        float(c.get("max_flow_cms", 0.0))
        for cid, c in kpis["conduit_results"].items()
        if cid.startswith("C_RACC_") or "RACC" in cid or "orph" in cid.lower()
    )
    racc_list = meta.get("raccordements_orphelins", [])
    nb_ouvrages_actifs = len(racc_list) if racc_list else len([cid for cid in kpis["conduit_results"].keys() if cid.startswith("C_RACC_")])

    q_exutoire_m3s = round(float(kpis.get("peak_outflow_m3s", 0.0)), 3)
    q_derive_m3s = round(q_deleste_tot, 3)

    q_rat_ref = round(float(kpis.get("coherence_pluie_debit", {}).get("q_rationnel_m3s") or ((c_eff * i_max * area_ha) / 360.0)), 3)
    if q_rat_ref > 0:
        q_genere_m3s = q_rat_ref
    else:
        q_genere_m3s = round(max(q_exutoire_m3s + q_derive_m3s, 0.001), 3)

    if q_genere_m3s > 0:
        q_derive_m3s = min(q_derive_m3s, q_genere_m3s)
        taux_derive_pct = round(min(100.0, (q_derive_m3s / q_genere_m3s) * 100.0), 1)
        taux_exutoire_pct = round(max(0.0, 100.0 - taux_derive_pct), 1)
    else:
        taux_derive_pct = 0.0
        taux_exutoire_pct = 100.0

    nom_bv = meta.get("bassin_nom") or meta.get("cluster_nom") or (f"Bassin {meta.get('cluster_id')}" if meta.get("cluster_id") is not None else "Bassin versant")

    texte_decisionnel = (
        f"Bassin versant : {nom_bv}\n"
        f"• Débit total généré par le bassin : {q_genere_m3s:.3f} m³/s\n"
        f"• Soulagement du collecteur principal : {taux_derive_pct:.1f}%\n"
        f"• Débit résiduel vers l'exutoire principal : {q_exutoire_m3s:.3f} m³/s ({taux_exutoire_pct:.1f}%)\n"
        f"• Débit capté par {nb_ouvrages_actifs} ouvrages spéciaux mobilisés : {q_derive_m3s:.3f} m³/s ({taux_derive_pct:.1f}%)"
    )

    kpis["q_deleste_m3s"] = q_derive_m3s
    kpis["q_deleste_ls"] = round(q_derive_m3s * 1000.0, 1)
    kpis["q_derive_m3s"] = q_derive_m3s
    kpis["q_exutoire_m3s"] = q_exutoire_m3s
    kpis["q_genere_m3s"] = q_genere_m3s
    kpis["taux_derive_pct"] = taux_derive_pct
    kpis["taux_exutoire_pct"] = taux_exutoire_pct
    kpis["soulagement_reseau_pct"] = taux_derive_pct
    kpis["reduction_charge_pct"] = taux_derive_pct
    kpis["nb_ouvrages_raccordes"] = nb_ouvrages_actifs
    kpis["bilan_hydraulique"] = {
        "bassin_nom": nom_bv,
        "q_genere_m3s": q_genere_m3s,
        "q_exutoire_m3s": q_exutoire_m3s,
        "taux_exutoire_pct": taux_exutoire_pct,
        "q_derive_m3s": q_derive_m3s,
        "taux_derive_pct": taux_derive_pct,
        "nb_ouvrages_actifs": nb_ouvrages_actifs,
        "soulagement_reseau_pct": taux_derive_pct,
        "reduction_charge_pct": taux_derive_pct,
        "texte_decisionnel": texte_decisionnel
    }
    kpis["bilan_hydraulique_decisionnel"] = texte_decisionnel
    kpis["compliance_continuity"] = abs(kpis["routing_continuity_error_pct"]) <= 5.0
    return kpis
