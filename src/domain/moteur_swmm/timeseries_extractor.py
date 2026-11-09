# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-09
Objet : Extracteur de séries temporelles depuis le fichier binaire SWMM .out (Phase 6.B)
================================================================================
"""

import os
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("swmm_platform.moteur_swmm.timeseries_extractor")

try:
    from pyswmm import Output
    from swmm.toolkit.shared_enum import LinkAttribute, NodeAttribute
except ImportError:
    Output = None
    LinkAttribute = None
    NodeAttribute = None


def extraire_series_temporelles(out_path: str, max_steps: int = 60) -> Dict[str, Any]:
    """
    Extrait les séries temporelles pour l'animation de l'onde de crue (Time Slider).
    Lit le fichier binaire SWMM .out via pyswmm.Output et compile un profil temporel
    échantillonné fluide (jusqu'à max_steps pas de temps).

    Retourne :
      - duration_hours : durée totale simulée (heures)
      - total_steps : nombre total de pas enregistrés
      - sampled_count : nombre de pas échantillonnés
      - peak_outflow_m3s : débit de pointe global à l'exutoire (m3/s)
      - peak_time : heure du débit de pointe (ex: '01:45')
      - steps : liste des états à chaque pas de temps échantillonné
    """
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        logger.warning("Fichier .out introuvable ou vide: %s", out_path)
        return {"status": "NO_DATA", "steps": []}

    if Output is None or LinkAttribute is None or NodeAttribute is None:
        logger.warning("pyswmm.Output non disponible dans cet environnement.")
        return {"status": "UNAVAILABLE", "steps": []}

    try:
        with Output(out_path) as out:
            times = out.times
            if not times:
                logger.warning("Aucun pas de temps dans le fichier .out: %s", out_path)
                return {"status": "EMPTY", "steps": []}

            n_times = len(times)
            # Échantillonnage régulier pour ne pas dépasser max_steps
            step_skip = max(1, n_times // max_steps)
            sampled_indices = list(range(0, n_times, step_skip))
            if (n_times - 1) not in sampled_indices:
                sampled_indices.append(n_times - 1)

            # Identification des exutoires (nœuds dont le nom contient 'out', 'exut', ou identifiés)
            outfall_nodes = [nid for nid in out.nodes.keys() if any(k in nid.lower() for k in ("out", "exut", "rejet", "step"))]
            if not outfall_nodes and out.nodes:
                # Fallback : prendre les derniers nœuds
                outfall_nodes = list(out.nodes.keys())[-2:]

            # Pré-chargement des séries temporelles
            # 1. Conduites : Taux de charge (CAPACITY = Q/Qmax)
            link_caps: Dict[str, Dict[Any, float]] = {}
            for lid in out.links.keys():
                try:
                    link_caps[lid] = out.link_series(lid, LinkAttribute.CAPACITY)
                except Exception:
                    pass

            # 2. Regards : Débordement en surface (FLOODING_LOSSES)
            node_floods: Dict[str, Dict[Any, float]] = {}
            for nid in out.nodes.keys():
                try:
                    node_floods[nid] = out.node_series(nid, NodeAttribute.FLOODING_LOSSES)
                except Exception:
                    pass

            # 3. Exutoires : Débit entrant total (TOTAL_INFLOW)
            outfall_flows: Dict[str, Dict[Any, float]] = {}
            for nid in outfall_nodes:
                try:
                    outfall_flows[nid] = out.node_series(nid, NodeAttribute.TOTAL_INFLOW)
                except Exception:
                    pass

            # Compilation des pas temporels échantillonnés
            steps_data: List[Dict[str, Any]] = []
            peak_outflow = 0.0
            peak_time_str = "00:00"

            start_dt = times[0]
            end_dt = times[-1]
            total_duration_minutes = (end_dt - start_dt).total_seconds() / 60.0

            for idx in sampled_indices:
                t = times[idx]
                delta_min = int((t - start_dt).total_seconds() / 60.0)
                hh = delta_min // 60
                mm = delta_min % 60
                time_str = f"{hh:02d}:{mm:02d}"

                # Débit total exutoire
                cur_outflow = 0.0
                for s in outfall_flows.values():
                    cur_outflow += s.get(t, 0.0)
                cur_outflow = round(cur_outflow, 3)

                if cur_outflow > peak_outflow:
                    peak_outflow = cur_outflow
                    peak_time_str = time_str

                # Conduites actives (ne conserver que les valeurs significatives > 0.02 pour alléger le JSON)
                active_links: Dict[str, float] = {}
                surcharged_pipes = 0
                for lid, s in link_caps.items():
                    val = s.get(t, 0.0)
                    if val >= 0.02:
                        active_links[lid] = round(val, 2)
                    if val >= 0.8:
                        surcharged_pipes += 1

                # Regards débordants à cet instant
                flooded_nodes: List[str] = []
                for nid, s in node_floods.items():
                    if s.get(t, 0.0) > 0.0005:  # débit de débordement > 0.5 L/s
                        flooded_nodes.append(nid)

                steps_data.append({
                    "step_index": len(steps_data),
                    "original_index": idx,
                    "time_str": time_str,
                    "minute": delta_min,
                    "outflow_m3s": cur_outflow,
                    "surcharged_pipes_count": surcharged_pipes,
                    "flooded_nodes_count": len(flooded_nodes),
                    "flooded_nodes": flooded_nodes,
                    "links": active_links
                })

            return {
                "status": "SUCCESS",
                "duration_hours": round(total_duration_minutes / 60.0, 2),
                "duration_minutes": int(total_duration_minutes),
                "total_steps": n_times,
                "sampled_count": len(steps_data),
                "peak_outflow_m3s": peak_outflow,
                "peak_time": peak_time_str,
                "outfall_nodes": outfall_nodes,
                "time_labels": [s["time_str"] for s in steps_data],
                "outflow_series": [s["outflow_m3s"] for s in steps_data],
                "steps": steps_data
            }

    except Exception as e:
        logger.exception("Erreur lors de l'extraction des séries temporelles depuis %s: %s", out_path, e)
        return {
            "status": "ERROR",
            "error": str(e),
            "steps": []
        }
