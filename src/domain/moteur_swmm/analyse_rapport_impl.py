# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Implementation principale de analyse_rapport_swmm_impl (.rpt SWMM 5.2) (extrait de moteur_swmm/analyse_rapport.py)
================================================================================
"""

import re
import logging
from typing import Dict, Any

logger = logging.getLogger("swmm_platform.moteur_swmm.analyse_rapport")
from src.domain.moteur_swmm.analyse_rapport_parseurs import (
    _lire_node_depth_summary,
    calculer_coherence_pluie_debit,
)
from src.domain.moteur_swmm.analyse_rapport_enrichissements import (
    enrichir_node_results_cotes_inp,
)


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
        "node_depth_maxima": {},
        "node_depth_maxima_status": "absent",
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
    #    Priorité au pic global du système (System) pour les bilans multi-exutoires
    #    ou à l'exutoire principal du modèle s'il est isolé.
    if "Outfall Loading Summary" in rpt_text:
        m_out = re.search(r"Outfall Loading Summary\s*\n\s*\*+\s*\n(.*?)(?=\n\s*\*+\s*\n|\n\s*Link Flow Summary|\n\s*Subcatchment|\Z)", rpt_text, re.DOTALL)
        table_block = m_out.group(1) if m_out else rpt_text.split("Outfall Loading Summary")[1].split("\n\n\n")[0]
        outfall_lines = table_block.strip().splitlines()
        _lignes_exutoire = []
        _outfalls_dict = {}
        _system_peak = 0.0
        _system_vol = 0.0

        for line in outfall_lines:
            parts = line.split()
            if not parts or parts[0].startswith("-") or parts[0] in ("Flow", "Freq", "Outfall", "Node"):
                continue
            if parts[0] == "System":
                if len(parts) >= 4:
                    try:
                        _system_peak = float(parts[3])
                    except Exception:
                        pass
                if len(parts) >= 5:
                    try:
                        _system_vol = float(parts[4])
                    except Exception:
                        pass
            elif len(parts) >= 4:
                # La 2e colonne est le "Flow Freq. (%)" : les lignes d'en-tête
                # du tableau (ex. "%  CMS  CMS  10^6 ltr") ne sont pas des exutoires.
                try:
                    float(parts[1])
                except Exception:
                    continue
                _lignes_exutoire.append((parts[0], parts))
                try:
                    _outfalls_dict[parts[0]] = {
                        "freq_pct": float(parts[1]) if len(parts) >= 2 else 0.0,
                        "avg_cms": float(parts[2]),
                        "max_cms": float(parts[3]),
                        "vol_10e6_ltr": float(parts[4]) if len(parts) >= 5 else 0.0
                    }
                except Exception:
                    pass

        _cibles = {str(meta.get("outfall_code") or ""), str(meta.get("junction_outfall_code") or "")}
        _principal = [lp for nm, lp in _lignes_exutoire if nm in _cibles]
        if not _principal:
            # Repli : exutoire principal = OUT_* hors frontières/orphelins
            _principal = [lp for nm, lp in _lignes_exutoire
                          if nm.startswith("OUT_") and "OUT_BND_" not in nm and "OUT_orph_" not in nm]
        if not _principal:
            _principal = [lp for nm, lp in _lignes_exutoire if "OUT_" in nm]
        if not _principal and _lignes_exutoire:
            _principal = [_lignes_exutoire[0][1]]

        # Débit de pointe du système / bassin
        if _system_peak > 0:
            kpis["peak_outflow_m3s"] = _system_peak
        elif _principal:
            for parts in _principal[:1]:
                try:
                    kpis["peak_outflow_m3s"] = float(parts[3])
                except Exception:
                    try:
                        kpis["peak_outflow_m3s"] = float(parts[2])
                    except Exception:
                        pass
        kpis["outfall_loading_summary"] = _outfalls_dict
        if _system_vol > 0 and not kpis.get("total_outflow_m3"):
            kpis["total_outflow_m3"] = round(_system_vol * 1000.0, 1)

    # 6. Surcharge des regards (Node Surcharge Summary)
    if "Node Surcharge Summary" in rpt_text:
        surch_part = rpt_text.split("Node Surcharge Summary")[1].split("Node Flooding Summary")[0].split("\n\n\n")[0]
        for line in surch_part.strip().splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[1] == "JUNCTION":
                nid = parts[0]
                try:
                    h_surch = float(parts[2])
                    max_height_crown = float(parts[3]) if len(parts) >= 4 else 0.0
                    min_depth_rim = float(parts[4]) if len(parts) >= 5 else 0.0
                    kpis["node_results"][nid] = {
                        "node": nid,
                        "hours_surcharged": h_surch,
                        "surcharge_depth_m": max_height_crown,
                        "min_depth_below_rim_m": min_depth_rim,
                        "hours_flooded": 0.0,
                        "peak_flood_flow_cms": 0.0,
                        "flood_volume_m3": 0.0,
                        "status": "surcharged" if h_surch > 0 else "normal",
                        "color": "#f97316" if h_surch > 0 else "#3b82f6"
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
                    # Volume TOTAL débordé rapporté par SWMM (.rpt, unité
                    # 10^6 l). Aucune estimation de remplacement : une valeur
                    # nulle signifie « arrondi par le rapport », pas « mesuré ».
                    vol_flood = round(float(parts[5]) * 1000.0, 3)
                    # Instant du maximum de débordement (précision : la minute,
                    # convention .rpt « days hr:min ») — jamais extrapolé.
                    flood_time_minute = None
                    try:
                        _hm = str(parts[4]).split(":")
                        flood_time_minute = int(parts[3]) * 1440 + int(_hm[0]) * 60 + int(_hm[1])
                    except Exception:
                        pass
                    ponded_depth_m = None
                    try:
                        ponded_depth_m = float(parts[6]) if len(parts) >= 7 else 0.0
                    except Exception:
                        ponded_depth_m = 0.0
                    if h_flood > 0:
                        if nid not in kpis["node_results"]:
                            kpis["node_results"][nid] = {"node": nid, "hours_surcharged": h_flood}
                        kpis["node_results"][nid].update({
                            "hours_flooded": h_flood,
                            "peak_flood_flow_cms": pk_flood,
                            "flood_volume_m3": vol_flood,
                            "flood_time_minute": flood_time_minute,
                            "ponded_depth_m": ponded_depth_m,
                            # flood_volume_m3 = valeur BRUTE du .rpt (unité
                            # 10^6 l, 3 décimales → résolution ~1 m³). Une
                            # valeur nulle n'est PAS une mesure nulle : le
                            # volume exact n'est pas déterminable.
                            "flood_volume_estime": False,
                            "status": "flooded",
                            "color": "#dc2626"
                        })
                        kpis["flooded_nodes"].append(kpis["node_results"][nid])
                except Exception:
                    pass

    # 7b. Maxima nodaux au pas de calcul (Node Depth Summary)
    # Source d'autorité pour la HGL maximale : ces valeurs sont des maxima
    # calculés par SWMM à CHAQUE pas de routage, contrairement au .out qui
    # n'échantillonne qu'aux instants de rapport (REPORT_STEP).
    _depth_maxima, _depth_status = _lire_node_depth_summary(rpt_text)
    kpis["node_depth_maxima"] = _depth_maxima
    kpis["node_depth_maxima_status"] = _depth_status

    # 7c. Maxima hydrauliques au pas de routage consolidés pour tous les nœuds simulés
    for nid, d_info in _depth_maxima.items():
        if nid not in kpis["node_results"]:
            kpis["node_results"][nid] = {
                "node": nid,
                "type": d_info.get("type", "JUNCTION"),
                "hours_surcharged": 0.0,
                "surcharge_depth_m": 0.0,
                "hours_flooded": 0.0,
                "peak_flood_flow_cms": 0.0,
                "flood_volume_m3": 0.0,
                "status": "normal",
                "color": "#10b981",
                "max_depth_m": d_info.get("max_depth_m"),
                "max_head_m": d_info.get("max_hgl_m"),
                "max_hgl_m": d_info.get("max_hgl_m"),
                "avg_depth_m": d_info.get("avg_depth_m"),
                "reported_max_depth_m": d_info.get("reported_max_depth_m"),
                "max_time_minute": d_info.get("max_time_minute"),
            }
        else:
            kpis["node_results"][nid].update({
                "type": d_info.get("type", "JUNCTION"),
                "max_depth_m": d_info.get("max_depth_m"),
                "max_head_m": d_info.get("max_hgl_m"),
                "max_hgl_m": d_info.get("max_hgl_m"),
                "avg_depth_m": d_info.get("avg_depth_m"),
                "reported_max_depth_m": d_info.get("reported_max_depth_m"),
                "max_time_minute": d_info.get("max_time_minute"),
            })

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
                        color = "#eab308"
                        label = "Critique (80-100%)"
                    elif q_ratio >= 0.5 or d_ratio >= 0.5:
                        c_status = "moderee"
                        color = "#22c55e"
                        label = "Modéré (50-80%)"
                    else:
                        c_status = "normal"
                        color = "#3b82f6"
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
    calculer_coherence_pluie_debit(kpis, meta)

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
    if meta.get("inp_content"):
        try:
            enrichir_node_results_cotes_inp(kpis["node_results"], meta["inp_content"])
        except Exception as e_inp_c:
            logger.warning("Enrichissement cotes INP dans analyse_rapport impossible: %s", e_inp_c)
    return kpis
