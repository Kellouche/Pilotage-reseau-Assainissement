# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Enrichissements resultats noeuds : cotes INP, hydrauliques (extrait de moteur_swmm/analyse_rapport.py)
================================================================================
"""

import re
import logging
from typing import Dict, Any

logger = logging.getLogger("swmm_platform.moteur_swmm.analyse_rapport")


def enrichir_hydraulique_noeuds(kpis: Dict[str, Any]) -> None:
    """
    Injecte dans ``timeseries.node_hydraulics`` les maxima calculés par SWMM
    à chaque pas de routage, synthétisés dans le .rpt :

    - ``Node Depth Summary`` → ``rpt_max_head_m`` (HGL max), ``rpt_max_depth_m``,
      ``rpt_reported_max_depth_m`` (max aux instants de rapport),
      ``rpt_max_head_minute`` (précision : la minute) ;
    - ``Node Flooding Summary`` → ``rpt_flood_max_m3s``, ``rpt_flood_minute``,
      ``rpt_flood_volume_m3``.

    Les champs ``.out`` (``max_head_m``, ``flooding_max_m3s``) sont conservés
    tels quels et marqués ``*_source = "out_report_step"`` : ce sont des maxima
    AUX INSTANTS DE RAPPORT, pas nécessairement les pics internes du moteur.
    Aucune valeur n'est estimée : une section .rpt absente laisse les champs
    rpt_* simplement absents.
    """
    ts = kpis.get("timeseries")
    nh = ts.get("node_hydraulics") if isinstance(ts, dict) else None
    if not isinstance(nh, dict) or not nh:
        return
    maxima = kpis.get("node_depth_maxima") or {}
    node_res = kpis.get("node_results") or {}
    for nid, ent in nh.items():
        if not isinstance(ent, dict):
            continue
        ent.setdefault("max_head_source", "out_report_step")
        ent.setdefault("flooding_source", "out_report_step")
        # max_head_m provient du .out : maximum aux instants de rapport,
        # jamais présenté comme exhaustif au pas de routage.
        ent["max_head_exhaustif"] = False
        rpt = maxima.get(nid)
        if rpt:
            ent["rpt_max_head_m"] = rpt.get("max_hgl_m")
            ent["rpt_max_head_minute"] = rpt.get("max_time_minute")
            ent["rpt_max_depth_m"] = rpt.get("max_depth_m")
            ent["rpt_reported_max_depth_m"] = rpt.get("reported_max_depth_m")
            ent["hgl_max_source"] = "rpt_node_depth_summary"
        nr = node_res.get(nid) or {}
        if float(nr.get("hours_flooded") or 0.0) > 0.0 or nr.get("status") == "flooded":
            ent["rpt_flood_max_m3s"] = nr.get("peak_flood_flow_cms")
            ent["rpt_flood_minute"] = nr.get("flood_time_minute")
            ent["rpt_flood_volume_m3"] = nr.get("flood_volume_m3")
            # True = valeur non fiable (estimation historique ou absente) ;
            # False = volume brut rapporté par SWMM (résolution ~1 m³).
            ent["flood_volume_estime"] = bool(nr.get("flood_volume_estime", True))
            ent["flooding_source"] = "rpt_node_flooding_summary"


def extraire_cotes_noeuds_inp(inp_text: str) -> Dict[str, Dict[str, Any]]:
    """
    Extrait les cotes géométriques physiques des nœuds depuis un texte .inp SWMM :
    - [JUNCTIONS] : Elevation (radier), MaxDepth (profondeur) -> rim_elev = Elevation + MaxDepth
    - [OUTFALLS]  : Elevation (radier) -> rim_elev = Elevation
    - [STORAGE]   : Elevation (radier), MaxDepth -> rim_elev = Elevation + MaxDepth
    """
    cotes: Dict[str, Dict[str, Any]] = {}
    if not inp_text:
        return cotes

    sec_courante = None
    for line in inp_text.splitlines():
        s = line.strip()
        if not s or s.startswith(";"):
            continue
        if s.startswith("[") and s.endswith("]"):
            sec_courante = s.upper()
            continue

        if sec_courante == "[JUNCTIONS]":
            parts = s.split()
            if len(parts) >= 2:
                nid = parts[0]
                try:
                    elev = float(parts[1])
                    max_depth = float(parts[2]) if len(parts) >= 3 else 2.0
                    cotes[nid] = {
                        "invert_elev": elev,
                        "max_depth_structure": max_depth,
                        "rim_elev": round(elev + max_depth, 3),
                        "type": "JUNCTION",
                    }
                except (ValueError, TypeError):
                    pass
        elif sec_courante == "[OUTFALLS]":
            parts = s.split()
            if len(parts) >= 2:
                nid = parts[0]
                try:
                    elev = float(parts[1])
                    cotes[nid] = {
                        "invert_elev": elev,
                        "max_depth_structure": 0.0,
                        "rim_elev": elev,
                        "type": "OUTFALL",
                    }
                except (ValueError, TypeError):
                    pass
        elif sec_courante == "[STORAGE]":
            parts = s.split()
            if len(parts) >= 2:
                nid = parts[0]
                try:
                    elev = float(parts[1])
                    max_depth = float(parts[2]) if len(parts) >= 3 else 2.0
                    cotes[nid] = {
                        "invert_elev": elev,
                        "max_depth_structure": max_depth,
                        "rim_elev": round(elev + max_depth, 3),
                        "type": "STORAGE",
                    }
                except (ValueError, TypeError):
                    pass

    return cotes


def enrichir_node_results_cotes_inp(node_results: Dict[str, Any], inp_text: str) -> None:
    """Injecte invert_elev, max_depth_structure et rim_elev dans node_results."""
    if not node_results or not inp_text:
        return
    cotes = extraire_cotes_noeuds_inp(inp_text)
    for nid, nr in node_results.items():
        if not isinstance(nr, dict):
            continue
        c_info = cotes.get(nid) or cotes.get(str(nid).split(".")[0])
        if c_info:
            nr.setdefault("invert_elev", c_info["invert_elev"])
            nr.setdefault("max_depth_structure", c_info["max_depth_structure"])
            nr.setdefault("rim_elev", c_info["rim_elev"])
            if nr.get("type") is None:
                nr["type"] = c_info.get("type", "JUNCTION")
            # Calcul précis de la hauteur de surcharge par rapport au tampon
            if nr.get("max_head_m") is not None and nr.get("rim_elev") is not None:
                h_diff = round(nr["max_head_m"] - nr["rim_elev"], 3)
                if h_diff > 0:
                    nr["surcharge_depth_m"] = h_diff
