# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Parseurs .rpt SWMM : Node Depth Summary, maxima noeuds, coherence pluie/debit (extrait de moteur_swmm/analyse_rapport.py)
================================================================================
"""

import re
import logging
from typing import Dict, Any

logger = logging.getLogger("swmm_platform.moteur_swmm.analyse_rapport")


def _lire_node_depth_summary(rpt_text: str):
    """Parse la section « Node Depth Summary » du .rpt.

    Retourne (dict nodé par identifiant SWMM exact, statut) où statut vaut
    'ok', 'illisible' ou 'absent'. Aucune correspondance approximative :
    seuls les identifiants littéraux du rapport sont retenus.
    """
    if "Node Depth Summary" not in rpt_text:
        return {}, "absent"
    try:
        depth_part = rpt_text.split("Node Depth Summary", 1)[1]
        out = {}
        parsed = 0
        for line in depth_part.splitlines():
            # Fin de section : ligne de séparation ou titre de section
            # suivante (les lignes « *** » d'en-tête précèdent les données).
            if parsed > 0 and ("***" in line or "Summary" in line):
                break
            parts = line.split()
            if len(parts) >= 8 and parts[1] in ("JUNCTION", "OUTFALL", "STORAGE", "DIVIDER"):
                try:
                    _hm = str(parts[6]).split(":")
                    out[parts[0]] = {
                        "node": parts[0],
                        "type": parts[1],
                        "avg_depth_m": float(parts[2]),
                        "max_depth_m": float(parts[3]),
                        "max_hgl_m": float(parts[4]),
                        "max_time_minute": int(parts[5]) * 1440 + int(_hm[0]) * 60 + int(_hm[1]),
                        "max_time_str": str(parts[6]),
                        "reported_max_depth_m": float(parts[7]),
                    }
                    parsed += 1
                except Exception:
                    pass
        return out, ("ok" if parsed > 0 else "illisible")
    except Exception as e_depth:
        logger.warning("Node Depth Summary illisible: %s", e_depth)
        return {}, f"erreur: {e_depth}"


def extraire_maxima_noeuds_rpt(rpt_text: str) -> Dict[str, Dict[str, Any]]:
    """Maxima nodaux SWMM (pas de routage) depuis un .rpt persisté.
    Retourne {} si la section est absente ou illisible — jamais
    d'estimation de remplacement."""
    maxima, status = _lire_node_depth_summary(rpt_text or "")
    if status != "ok":
        return {}
    return maxima


def calculer_coherence_pluie_debit(kpis: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Évalue ou réévalue la cohérence pluie-débit (méthode rationnelle Q = C*I*A / 360)
    en comparant le débit rationnel attendu sur le bassin au débit de pointe simulé.
    """
    area_ha = float(meta.get("total_area_ha") or kpis.get("total_area_ha") or 0.0)
    i_max = float(meta.get("pluvio_intensite_max_mmh") or kpis.get("pluvio_intensite_max_mmh") or 62.0)
    c_eff = float(kpis.get("effective_runoff_coeff") or meta.get("effective_runoff_coeff") or 0.70)
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

    coh = {
        "q_simule_m3s": q_sim,
        "q_rationnel_m3s": q_rat,
        "ratio": ratio_coh,
        "statut": coh_st,
        "badge": coh_badge,
        "color": coh_col,
        "message": coh_msg
    }
    kpis["coherence_pluie_debit"] = coh
    return coh
