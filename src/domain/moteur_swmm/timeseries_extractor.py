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


def _extraire_hyetogramme_depuis_inp(inp_path: Optional[str]) -> List[tuple]:
    """Extrait les couples (minute, intensite_mmh) depuis la section [TIMESERIES] d'un fichier .inp."""
    if not inp_path or not os.path.exists(inp_path):
        return []
    ts_points = []
    in_ts = False
    try:
        with open(inp_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith(";"):
                    continue
                if s.startswith("["):
                    in_ts = (s.upper() == "[TIMESERIES]")
                    continue
                if in_ts:
                    parts = s.split()
                    if len(parts) >= 3:
                        t_str = parts[1]
                        val_str = parts[2]
                        try:
                            t_parts = t_str.split(":")
                            m = int(t_parts[0]) * 60 + int(t_parts[1])
                            val = float(val_str)
                            ts_points.append((m, val))
                        except Exception:
                            pass
        ts_points.sort(key=lambda x: x[0])
    except Exception as e:
        logger.warning("Erreur lecture [TIMESERIES] depuis %s: %s", inp_path, e)
    return ts_points


def _extraire_surface_totale_inp(inp_path: Optional[str]) -> float:
    """Extrait la surface totale du bassin versant (ha) depuis la section [SUBCATCHMENTS] d'un .inp."""
    if not inp_path or not os.path.exists(inp_path):
        return 0.0
    tot_area = 0.0
    in_sub = False
    try:
        with open(inp_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith(";"):
                    continue
                if s.startswith("["):
                    in_sub = (s.upper() == "[SUBCATCHMENTS]")
                    continue
                if in_sub:
                    parts = s.split()
                    if len(parts) >= 4:
                        try:
                            tot_area += float(parts[3])
                        except Exception:
                            pass
    except Exception:
        pass
    return round(tot_area, 2)


def _interpoler_pluie(ts_points: List[tuple], minute: int) -> float:
    """Interpole l'intensité pluvieuse (mm/h) à la minute donnée."""
    if not ts_points:
        return 0.0
    if minute <= ts_points[0][0]:
        return float(ts_points[0][1])
    if minute >= ts_points[-1][0]:
        return float(ts_points[-1][1])
    for i in range(len(ts_points) - 1):
        m0, v0 = ts_points[i]
        m1, v1 = ts_points[i + 1]
        if m0 <= minute <= m1:
            if m1 == m0:
                return float(v0)
            ratio = (minute - m0) / float(m1 - m0)
            return round(v0 + ratio * (v1 - v0), 2)
    return 0.0


def enrichir_timeseries_pluie(ts: Dict[str, Any], sim_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Garantit que l'objet timeseries contient la série de précipitation (rainfall_series)
    et les métriques hydrologiques (peak_rainfall_mmh, lag_time_minutes, volumes, runoff_coefficient).
    Si ces données sont absentes (cas des simulations en cache historique), elles sont reconstituées
    dynamiquement à partir du scénario de pluie et de la surface du bassin versant.
    """
    if not ts or ts.get("status") != "SUCCESS" or not ts.get("steps"):
        return ts

    # Si la série de pluie est déjà présente et non nulle, rien à faire
    rf_series = ts.get("rainfall_series")
    peak_rf = ts.get("peak_rainfall_mmh")
    if rf_series and len(rf_series) > 0 and peak_rf and peak_rf > 0:
        return ts

    meta = sim_data.get("meta", {}) if isinstance(sim_data, dict) else {}
    from src.domain.moteur_swmm.constants import SCENARIOS_PLUIE

    # 1. Identifier le scénario et l'intensité maximale de référence
    scen_key = meta.get("pluvio_scenario_key") or "pluie_decennale"
    if scen_key not in SCENARIOS_PLUIE:
        scen_key = "pluie_decennale"
    scen = SCENARIOS_PLUIE[scen_key]

    intensite_max = float(meta.get("pluvio_intensite_max_mmh") or meta.get("intensite_max_mmh") or scen.get("intensite_max_defaut", 62.0))
    ts_base = scen.get("timeseries", [("00:00", 0.0), ("01:00", 62.0), ("04:00", 0.0)])
    max_base = max((v for _, v in ts_base), default=62.0)
    scale = (intensite_max / max_base) if max_base > 0 else 1.0

    # Construire la liste de points (minute, intensite_mmh)
    ts_points = []
    for t_str, v in ts_base:
        try:
            parts = t_str.split(":")
            m = int(parts[0]) * 60 + int(parts[1])
            ts_points.append((m, round(float(v) * scale, 2)))
        except Exception:
            pass
    ts_points.sort(key=lambda x: x[0])

    # 2. Remplir rainfall_mmh pour chaque pas échantillonné
    steps = ts["steps"]
    peak_rain_found = 0.0
    peak_rain_time = "01:00"
    peak_rain_min = 60

    peak_outflow_found = 0.0
    peak_outflow_min = 60

    for s in steps:
        m = s.get("minute", 0)
        r = _interpoler_pluie(ts_points, m)
        s["rainfall_mmh"] = r
        if r > peak_rain_found:
            peak_rain_found = r
            peak_rain_time = s.get("time_str", "01:00")
            peak_rain_min = m

        q = s.get("outflow_m3s", 0.0)
        if q > peak_outflow_found:
            peak_outflow_found = q
            peak_outflow_min = m

    new_rainfall_series = [s.get("rainfall_mmh", 0.0) for s in steps]

    # 3. Calcul des volumes
    # Volume d'eau écoulé à l'exutoire (m3)
    total_outflow_vol_m3 = 0.0
    for i in range(1, len(steps)):
        dt_sec = (steps[i]["minute"] - steps[i - 1]["minute"]) * 60.0
        q_avg = (steps[i].get("outflow_m3s", 0.0) + steps[i - 1].get("outflow_m3s", 0.0)) / 2.0
        total_outflow_vol_m3 += q_avg * dt_sec
    total_outflow_vol_m3 = round(total_outflow_vol_m3, 1)

    # Surface et pluie totale
    total_surface_ha = float(meta.get("total_area_ha") or meta.get("surface_totale_ha") or 117.67)
    total_precip_mm = float(meta.get("pluvio_hauteur_totale_mm") or 53.23)
    total_rain_vol_m3 = round(total_surface_ha * total_precip_mm * 10.0, 1)
    runoff_coef = round(total_outflow_vol_m3 / total_rain_vol_m3, 2) if total_rain_vol_m3 > 0 else 0.65
    lag_time_min = max(0, peak_outflow_min - peak_rain_min)

    ts["rainfall_series"] = new_rainfall_series
    ts["peak_rainfall_mmh"] = round(peak_rain_found or intensite_max, 1)
    ts["peak_rainfall_time"] = peak_rain_time
    ts["lag_time_minutes"] = lag_time_min
    ts["total_precipitation_mm"] = total_precip_mm
    ts["total_surface_ha"] = total_surface_ha
    ts["total_rain_volume_m3"] = total_rain_vol_m3
    ts["total_outflow_volume_m3"] = total_outflow_vol_m3
    ts["runoff_coefficient"] = runoff_coef

    return ts


def extraire_series_temporelles(out_path: str, max_steps: int = 60, inp_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Extrait les séries temporelles pour l'animation de l'onde de crue (Time Slider)
    et le double-graphique Hyétogramme (pluie) ↔ Hydrogramme (crue).
    Lit le fichier binaire SWMM .out via pyswmm.Output et compile un profil temporel
    échantillonné fluide (jusqu'à max_steps pas de temps).
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

            # Extraction des données de pluie et de surface du bassin depuis le .inp
            hyeto_points = _extraire_hyetogramme_depuis_inp(inp_path)
            total_surface_ha = _extraire_surface_totale_inp(inp_path)

            # Compilation des pas temporels échantillonnés
            steps_data: List[Dict[str, Any]] = []
            peak_outflow = 0.0
            peak_time_str = "00:00"
            peak_outflow_minute = 0

            peak_rain = 0.0
            peak_rain_time_str = "00:00"
            peak_rain_minute = 0

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
                    peak_outflow_minute = delta_min

                # Intensité de précipitation (mm/h)
                cur_rain = _interpoler_pluie(hyeto_points, delta_min)
                if cur_rain > peak_rain:
                    peak_rain = cur_rain
                    peak_rain_time_str = time_str
                    peak_rain_minute = delta_min

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
                    "rainfall_mmh": cur_rain,
                    "outflow_m3s": cur_outflow,
                    "surcharged_pipes_count": surcharged_pipes,
                    "flooded_nodes_count": len(flooded_nodes),
                    "flooded_nodes": flooded_nodes,
                    "links": active_links
                })

            # Calcul des bilans volumiques et hydrologiques globaux
            # 1. Volume d'eau écoulé à l'exutoire (m3) par intégration trapézoïdale
            total_outflow_vol_m3 = 0.0
            for i in range(1, len(steps_data)):
                dt_sec = (steps_data[i]["minute"] - steps_data[i - 1]["minute"]) * 60.0
                q_avg = (steps_data[i]["outflow_m3s"] + steps_data[i - 1]["outflow_m3s"]) / 2.0
                total_outflow_vol_m3 += q_avg * dt_sec
            total_outflow_vol_m3 = round(total_outflow_vol_m3, 1)

            # 2. Hauteur de pluie totale et volume précipité brut (m3)
            total_precip_mm = 0.0
            if hyeto_points:
                for i in range(1, len(hyeto_points)):
                    dt_h = (hyeto_points[i][0] - hyeto_points[i - 1][0]) / 60.0
                    i_avg = (hyeto_points[i][1] + hyeto_points[i - 1][1]) / 2.0
                    total_precip_mm += i_avg * dt_h
            total_precip_mm = round(total_precip_mm, 2)

            total_rain_vol_m3 = round(total_surface_ha * total_precip_mm * 10.0, 1) if total_surface_ha > 0 else 0.0
            runoff_coef = round(total_outflow_vol_m3 / total_rain_vol_m3, 2) if total_rain_vol_m3 > 0 else 0.65
            lag_time_min = max(0, peak_outflow_minute - peak_rain_minute)

            return {
                "status": "SUCCESS",
                "duration_hours": round(total_duration_minutes / 60.0, 2),
                "duration_minutes": int(total_duration_minutes),
                "total_steps": n_times,
                "sampled_count": len(steps_data),
                "peak_outflow_m3s": peak_outflow,
                "peak_time": peak_time_str,
                "peak_rainfall_mmh": peak_rain,
                "peak_rainfall_time": peak_rain_time_str,
                "lag_time_minutes": lag_time_min,
                "total_precipitation_mm": total_precip_mm,
                "total_surface_ha": total_surface_ha,
                "total_rain_volume_m3": total_rain_vol_m3,
                "total_outflow_volume_m3": total_outflow_vol_m3,
                "runoff_coefficient": runoff_coef,
                "outfall_nodes": outfall_nodes,
                "time_labels": [s["time_str"] for s in steps_data],
                "rainfall_series": [s["rainfall_mmh"] for s in steps_data],
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

