# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Génération textuelle des blocs et sections de modélisation du fichier .INP
================================================================================
"""

import logging
from typing import Dict, Any, Optional, Tuple, List, Set, Union
import pandas as pd
import geopandas as gpd

from src.domain.moteur_swmm.constants import _clean_node_id
from src.domain.moteur_swmm.assainissement_topologique import _resoudre_altimetrie_noeuds

logger = logging.getLogger("swmm_platform.moteur_swmm.sections_inp")


def generer_lignes_sections_inp(
    regards: gpd.GeoDataFrame,
    canalisations: gpd.GeoDataFrame,
    rejets: gpd.GeoDataFrame,
    sb_gdf: gpd.GeoDataFrame,
    swmm_sec: Dict[str, List[str]],
    scen: Dict[str, Any],
    duree_sim: float,
    pas_routage_sec: int,
    pente_moyenne_pct: Optional[float],
    outfall_code: str,
    target_ex_id: Optional[str],
    exutoires_map: Dict[Any, Any],
    clean_target_nodes: Set[str],
    raccordements_orphelins: Optional[List[Dict[str, Any]]],
    intensite_max_mmh: Optional[float],
    active_imperv: float,
    typ_nom: str,
    typologie_sol: Optional[str],
    st_id: str,
    scenario_key: str,
    cluster_id: Optional[Union[int, str]],
    bassin_nom: Optional[str],
    buf_actuel: float
) -> Tuple[List[str], Dict[str, Any]]:
    """
    Génère la liste de lignes de toutes les sections .inp et le dictionnaire meta.
    """
    h_end = int(duree_sim)
    m_end = int((duree_sim - h_end) * 60)
    end_time_str = f"{h_end:02d}:{m_end:02d}:00"
    routing_step_str = f"00:00:{pas_routage_sec:02d}"

    lines = [
        "[TITLE]",
        ";; SWMM Platform SaaS - Simulation Hydrodynamique Native 5.2",
        f";; Scénario : {scen['nom']}",
        f";; Durée : {duree_sim} heures | Pas de routage : {pas_routage_sec}s",
        "",
        "[OPTIONS]",
        "FLOW_UNITS          CMS",
        "INFILTRATION        HORTON",
        "FLOW_ROUTING        DYNWAVE",
        "START_DATE          01/01/2026",
        "START_TIME          00:00:00",
        "REPORT_START_DATE   01/01/2026",
        "REPORT_START_TIME   00:00:00",
        f"END_DATE            01/01/2026",
        f"END_TIME            {end_time_str}",
        "REPORT_STEP         00:01:00",
        "WET_STEP            00:05:00",
        "DRY_STEP            01:00:00",
        f"ROUTING_STEP        {routing_step_str}",
        "ALLOW_PONDING       NO",
        "INERTIAL_DAMPING    PARTIAL",
        "VARIABLE_STEP       0.75",
        "LENGTHENING_STEP    0",
        "MIN_SURFAREA        1.167",
        "NORMAL_FLOW_LIMITED BOTH",
        "FORCE_MAIN_EQUATION H-W",
        "LINK_OFFSETS        DEPTH",
        "MIN_SLOPE           0",
        "MAX_TRIALS          8",
        "HEAD_TOLERANCE      0.0015",
        "SYS_FLOW_TOL        5",
        "LAT_FLOW_TOL        5",
        "MINIMUM_STEP        0.5",
        "THREADS             1",
        "",
        "[EVAPORATION]",
        "CONSTANT 0.0",
        "DRY_ONLY NO",
        "",
        "[RAINGAGES]",
        ";;Name           Format    Interval SCF      Source",
        "RG1              INTENSITY 0:05     1.0      TIMESERIES TS_SCENARIO",
        "",
        "[TIMESERIES]",
        ";;Name           Date       Time       Value",
    ]

    ts_base = scen.get("timeseries", [("00:00", 0.0), ("04:00", 0.0)])
    max_base = max((v for _, v in ts_base), default=scen.get("intensite_max_defaut", 62.0))

    # Détection BMS : si le scénario vient de scenario_personnalise avec bms_metadata,
    # l'hyétogramme est déjà correctement normalisé (cumul exact + forme dynamique).
    # Ne PAS le rescaler — utiliser tel quel.
    is_bms = bool(scen.get("bms_metadata", {}).get("is_bms"))

    if intensite_max_mmh is not None and intensite_max_mmh >= 0.0 and not is_bms:
        active_i_max = round(float(intensite_max_mmh), 2)
        if max_base > 0:
            scale_factor = active_i_max / max_base
            effective_timeseries = [(t_str, round(val * scale_factor, 2)) for t_str, val in ts_base]
        else:
            if active_i_max > 0:
                effective_timeseries = [
                    ("00:00", 0.0),
                    ("00:15", round(active_i_max * 0.10, 2)),
                    ("00:30", round(active_i_max * 0.25, 2)),
                    ("00:45", round(active_i_max * 0.60, 2)),
                    ("01:00", round(active_i_max, 2)),
                    ("01:15", round(active_i_max * 0.50, 2)),
                    ("01:30", round(active_i_max * 0.22, 2)),
                    ("01:45", round(active_i_max * 0.10, 2)),
                    ("02:00", round(active_i_max * 0.03, 2)),
                    ("03:00", 0.0),
                    ("04:00", 0.0),
                ]
            else:
                effective_timeseries = [("00:00", 0.0), ("04:00", 0.0)]
    else:
        active_i_max = round(float(scen.get("intensite_max_defaut", max_base or 62.0)), 2)
        effective_timeseries = [(t_str, float(val)) for t_str, val in ts_base]

    hauteur_totale_cumul_mm = 0.0
    try:
        def _parse_t_hours(t_str: str) -> float:
            parts = t_str.split(":")
            return float(parts[0]) + float(parts[1]) / 60.0

        for i in range(1, len(effective_timeseries)):
            t_prev = _parse_t_hours(effective_timeseries[i - 1][0])
            t_curr = _parse_t_hours(effective_timeseries[i][0])
            dt_h = max(0.0, t_curr - t_prev)
            v_avg = (effective_timeseries[i - 1][1] + effective_timeseries[i][1]) / 2.0
            hauteur_totale_cumul_mm += v_avg * dt_h
        hauteur_totale_cumul_mm = round(hauteur_totale_cumul_mm, 2)
    except Exception:
        hauteur_totale_cumul_mm = scen.get("hauteur_totale_mm", 36.5)

    for t_str, val in effective_timeseries:
        lines.append(f"TS_SCENARIO                 {t_str:<10} {val:<10.2f}")
    lines.append("")

    for sec_name in ["SUBCATCHMENTS", "SUBAREAS", "INFILTRATION"]:
        lines.append(f"[{sec_name}]")
        lines.extend(swmm_sec[sec_name])
        lines.append("")

    node_elevs, source_alt = _resoudre_altimetrie_noeuds(regards, canalisations, rejets, outfall_code, pente_moyenne_pct)
    outfall_elev = node_elevs.get(outfall_code, 100.0)

    inlet_conduits = [c for _, c in canalisations.iterrows() if _clean_node_id(c.get("ID_AVAL")) == outfall_code]
    inlet_count = len(inlet_conduits)

    conduit_nodes = set()
    upstream_nodes = set()
    downstream_nodes = set()
    for _, c in canalisations.iterrows():
        u = _clean_node_id(c.get("ID_AMONT"))
        d = _clean_node_id(c.get("ID_AVAL"))
        if u and d and u != d:
            conduit_nodes.add(u)
            upstream_nodes.add(u)
            conduit_nodes.add(d)
            downstream_nodes.add(d)

    if inlet_count == 0 and len(canalisations) > 0:
        sinks = downstream_nodes - upstream_nodes
        if sinks:
            outfall_code = list(sinks)[0]
            inlet_conduits = [c for _, c in canalisations.iterrows() if _clean_node_id(c.get("ID_AVAL")) == outfall_code]

    creer_exutoire_dedie = True
    actual_outfall_name = f"OUT_{outfall_code}"
    terminal_outfall_elev = round(outfall_elev - 0.05, 3)

    lines.append("[JUNCTIONS]")
    lines.append(";;Name           Elevation  MaxDepth   InitDepth  SurDepth   Aponded")
    noeuds_traites: Set[str] = set()
    for idx, r in regards.iterrows():
        nid = _clean_node_id(r.get("Code"), fallback=f"REG_{idx+1}")
        if nid == actual_outfall_name or nid in noeuds_traites:
            continue
        prof = float(r["Profondeur"]) if ("Profondeur" in r and r["Profondeur"] > 0) else 2.0
        z_rad = node_elevs.get(nid, 100.0)
        lines.append(f"{nid:<16} {z_rad:<10.3f} {prof:<10.3f} 0.000      0.000      0.000")
        noeuds_traites.add(nid)

    for nid in conduit_nodes:
        if nid == actual_outfall_name or nid in noeuds_traites:
            continue
        z_rad = node_elevs.get(nid, 100.0)
        lines.append(f"{nid:<16} {z_rad:<10.3f} 2.000      0.000      0.000      0.000")
        noeuds_traites.add(nid)

    if outfall_code not in noeuds_traites:
        lines.append(f"{outfall_code:<16} {outfall_elev:<10.3f} 2.000      0.000      0.000      0.000")
        noeuds_traites.add(outfall_code)
    lines.append("")

    lines.append("[OUTFALLS]")
    lines.append(";;Name           Elevation  Type       Stage Data       Gated    Route To")
    lines.append(f"{actual_outfall_name:<16} {terminal_outfall_elev:<10.3f} FREE                        NO")

    racc_orph_valides = []
    seen_outfall_names = {actual_outfall_name}
    if raccordements_orphelins:
        for ro_idx, ro in enumerate(raccordements_orphelins):
            raw_reg_id = _clean_node_id(ro.get("regard_proche_id"))
            ouv_id = _clean_node_id(ro.get("ouvrage_id") or ro.get("id") or f"orph_{ro_idx+1}") or f"orph_{ro_idx+1}"
            reg_id = raw_reg_id
            regard_valide = False

            if reg_id and reg_id in clean_target_nodes and reg_id not in seen_outfall_names:
                regard_valide = True
            elif len(regards) > 0:
                o_pt = ro.get("ouvrage_coord_wgs84") or ro.get("regard_coord_wgs84")
                if o_pt and len(o_pt) == 2:
                    try:
                        from shapely.geometry import Point
                        import pyproj
                        proj_to_utm = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32631", always_xy=True).transform
                        pt_m = Point(proj_to_utm(float(o_pt[1]), float(o_pt[0])))
                        regards_bassin = regards[regards["Code"].apply(_clean_node_id).isin(clean_target_nodes)]
                        if not regards_bassin.empty:
                            dists_r = regards_bassin.geometry.distance(pt_m)
                            min_dist = float(dists_r.min())
                            if min_dist <= 45.0:
                                min_idx = dists_r.idxmin()
                                cand_reg = _clean_node_id(regards_bassin.loc[min_idx].get("Code"), fallback=raw_reg_id)
                                if cand_reg and cand_reg in clean_target_nodes and cand_reg not in seen_outfall_names:
                                    reg_id = cand_reg
                                    regard_valide = True
                                    logger.info(f"Ouvrage orphelin {ouv_id} réassocié au regard {reg_id} ({min_dist:.1f} m)")
                    except Exception as e_remap:
                        logger.warning(f"Contrôle proximité {ouv_id}: {e_remap}")

            if not regard_valide or not reg_id or reg_id in seen_outfall_names:
                continue

            cand_out_name = f"OUT_{ouv_id}"
            if cand_out_name in seen_outfall_names:
                cand_out_name = f"OUT_{ouv_id}_{ro_idx+1}"
            out_orph_name = cand_out_name
            seen_outfall_names.add(out_orph_name)

            z_reg = node_elevs.get(reg_id, 100.0)
            z_out_orph = round(z_reg - 0.20, 3)
            lines.append(f"{out_orph_name:<16} {z_out_orph:<10.3f} FREE                        NO")
            racc_orph_valides.append((ro, out_orph_name, reg_id, z_out_orph, ouv_id, ro_idx + 1))
    lines.append("")

    lines.append("[CONDUITS]")
    lines.append(";;Name           From Node        To Node          Length     Roughness  InOffset   OutOffset  InitFlow   MaxFlow")

    conduit_lines = []
    xsec_lines = []
    conduit_endpoints = {}
    for idx, c in canalisations.iterrows():
        cid = f"C_{idx+1}"
        u_node = _clean_node_id(c.get("ID_AMONT"))
        d_node = _clean_node_id(c.get("ID_AVAL"))
        if not u_node or not d_node or u_node == d_node:
            continue
        length = float(c["Longeur"]) if ("Longeur" in c and pd.notna(c["Longeur"]) and c["Longeur"] > 0) else float(c.geometry.length)
        length = max(1.0, round(length, 2))
        rough = 0.013
        diam_mm = float(c["DIAMETRE"]) if ("DIAMETRE" in c and pd.notna(c["DIAMETRE"]) and c["DIAMETRE"] > 0) else 600.0
        diam_m = max(0.2, diam_mm / 1000.0)
        nom_v = str(c.get("NOM-VOIE") or c.get("NOMVOIE") or c.get("nom_voie") or "").strip()
        if nom_v.lower() in ("nan", "none", "null", ""):
            nom_v = ""

        conduit_endpoints[cid] = {
            "u": u_node,
            "d": d_node,
            "length": length,
            "diam_mm": diam_mm,
            "material": str(c.get("MATERIAU", "Béton")),
            "nom_voie": nom_v
        }
        conduit_lines.append(f"{cid:<16} {u_node:<16} {d_node:<16} {length:<10.2f} {rough:<10.4f} 0.000      0.000      0.000      0.000")
        xsec_lines.append(f"{cid:<16} CIRCULAR     {diam_m:<16.3f} 0.000      0.000      0.000      1")

    if creer_exutoire_dedie:
        cid_out = f"C_OUT_{outfall_code}"
        max_inlet_d = max([float(c.get("DIAMETRE", 600)) for c in inlet_conduits] or [1000.0])
        diam_out_m = max(1.2, max_inlet_d / 1000.0)
        conduit_lines.append(f"{cid_out:<16} {outfall_code:<16} {actual_outfall_name:<16} 5.00       0.0130     0.000      0.000      0.000      0.000")
        xsec_lines.append(f"{cid_out:<16} CIRCULAR     {diam_out_m:<16.3f} 0.000      0.000      0.000      1")

    for item in racc_orph_valides:
        ro, out_orph_name, reg_id, _, ouv_id, r_seq = item
        cid_orph = f"C_RACC_{ouv_id}_{r_seq}"
        dist_orph = max(1.0, float(ro.get("distance_m", 15.0)))
        dn_orph_mm = float(ro.get("diametre_recommande_mm", 600.0))
        dn_orph_m = max(0.3, dn_orph_mm / 1000.0)
        nom_o = ro.get("nom", "Ouvrage spécial")
        conduit_lines.append(f"{cid_orph:<16} {reg_id:<16} {out_orph_name:<16} {dist_orph:<10.2f} 0.0130     0.000      0.000      0.000      0.000")
        xsec_lines.append(f"{cid_orph:<16} CIRCULAR     {dn_orph_m:<16.3f} 0.000      0.000      0.000      1")
        conduit_endpoints[cid_orph] = {
            "u": reg_id,
            "d": out_orph_name,
            "length": dist_orph,
            "diam_mm": dn_orph_mm,
            "material": "Béton armé 135A",
            "nom_voie": f"Raccordement opportuniste ({nom_o})"
        }

    lines.extend(conduit_lines)
    lines.append("")

    lines.append("[XSECTIONS]")
    lines.append(";;Link           Shape        Geom1            Geom2      Geom3      Geom4      Barrels    Culvert")
    lines.extend(xsec_lines)
    lines.append("")

    lines.append("[COORDINATES]")
    coords_traitees: Set[str] = set()
    for idx, r in regards.iterrows():
        nid = _clean_node_id(r.get("Code"), fallback=f"REG_{idx+1}")
        if nid not in coords_traitees:
            lines.append(f"{nid:<16} {r.geometry.x:<18.3f} {r.geometry.y:<18.3f}")
            coords_traitees.add(nid)

    if len(rejets) > 0:
        for idx, rj in rejets.iterrows():
            r_id = _clean_node_id(rj.get("Code") or rj.get("CODE") or rj.get("id") or rj.get("NOM"), fallback=f"REJ_{idx+1}")
            if r_id and r_id not in coords_traitees:
                lines.append(f"{r_id:<16} {rj.geometry.x:<18.3f} {rj.geometry.y:<18.3f}")
                coords_traitees.add(r_id)

    if outfall_code and outfall_code not in coords_traitees and target_ex_id and target_ex_id in exutoires_map:
        ex_geom = exutoires_map[target_ex_id].get("geometry")
        if ex_geom:
            lines.append(f"{outfall_code:<16} {ex_geom.x:<18.3f} {ex_geom.y:<18.3f}")
            coords_traitees.add(outfall_code)

    if creer_exutoire_dedie and actual_outfall_name not in coords_traitees:
        out_coord = None
        noeuds_regards = { _clean_node_id(r.get("Code"), fallback=f"REG_{idx+1}"): r for idx, r in regards.iterrows() }
        if outfall_code in noeuds_regards:
            g = noeuds_regards[outfall_code].geometry
            out_coord = (g.x + 5.0, g.y + 5.0)
        elif target_ex_id and target_ex_id in exutoires_map:
            eg = exutoires_map[target_ex_id].get("geometry")
            if eg:
                out_coord = (eg.x + 5.0, eg.y + 5.0)
        if not out_coord and coords_traitees:
            out_coord = (100.0, 100.0)
        if out_coord:
            lines.append(f"{actual_outfall_name:<16} {out_coord[0]:<18.3f} {out_coord[1]:<18.3f}")
            coords_traitees.add(actual_outfall_name)

    noeuds_regards = { _clean_node_id(r.get("Code"), fallback=f"REG_{idx+1}"): r for idx, r in regards.iterrows() }
    for item in racc_orph_valides:
        ro, out_orph_name, reg_id = item[0], item[1], item[2]
        if out_orph_name not in coords_traitees:
            pt_orph = None
            coords_wgs = ro.get("ouvrage_coord_wgs84")
            if coords_wgs and len(coords_wgs) == 2:
                try:
                    from src.domain.ouvrages_orphelins import _obtenir_reprojecteurs
                    _, to_utm = _obtenir_reprojecteurs("EPSG:32631", "EPSG:4326")
                    if to_utm:
                        pt_orph = to_utm(coords_wgs[1], coords_wgs[0])
                except Exception:
                    pass
            if not pt_orph and reg_id in noeuds_regards:
                g = noeuds_regards[reg_id].geometry
                pt_orph = (g.x + 10.0, g.y + 10.0)
            if not pt_orph:
                pt_orph = (100.0, 100.0)
            lines.append(f"{out_orph_name:<16} {pt_orph[0]:<18.3f} {pt_orph[1]:<18.3f}")
            coords_traitees.add(out_orph_name)
    lines.append("")

    lines.append("[POLYGONS]")
    lines.extend(swmm_sec["POLYGONS"])
    lines.append("")

    try:
        pts_x = []
        pts_y = []
        if not regards.empty:
            pts_x.extend([g.x for g in regards.geometry if g and not g.is_empty])
            pts_y.extend([g.y for g in regards.geometry if g and not g.is_empty])
        if not canalisations.empty:
            for g in canalisations.geometry:
                if g and not g.is_empty:
                    minx_c, miny_c, maxx_c, maxy_c = g.bounds
                    pts_x.extend([minx_c, maxx_c])
                    pts_y.extend([miny_c, maxy_c])

        if pts_x and pts_y:
            min_x = min(pts_x)
            max_x = max(pts_x)
            min_y = min(pts_y)
            max_y = max(pts_y)
            dx = max(max_x - min_x, 50.0) * 0.08
            dy = max(max_y - min_y, 50.0) * 0.08
            lines.append("[MAP]")
            lines.append(f"DIMENSIONS {min_x - dx:<14.3f} {min_y - dy:<14.3f} {max_x + dx:<14.3f} {max_y + dy:<14.3f}")
            lines.append("Units      Meters")
            lines.append("")
    except Exception as e_map:
        logger.warning(f"Impossible de générer la section [MAP] SWMM: {e_map}")

    lines.append("[REPORT]")
    lines.append("INPUT      NO")
    lines.append("CONTROLS   NO")
    lines.append("SUBCATCHMENTS ALL")
    lines.append("NODES ALL")
    lines.append("LINKS ALL")
    lines.append("")

    bbox_wgs84 = None
    try:
        pipes_for_bounds = canalisations if not canalisations.empty else regards
        if not pipes_for_bounds.empty:
            pipes_wgs = pipes_for_bounds.to_crs("EPSG:4326") if pipes_for_bounds.crs and str(pipes_for_bounds.crs).lower() not in ("epsg:4326", "4326", "wgs84") else pipes_for_bounds
            minx, miny, maxx, maxy = pipes_wgs.total_bounds
            bbox_wgs84 = [round(float(miny), 6), round(float(minx), 6), round(float(maxy), 6), round(float(maxx), 6)]
    except Exception as e_bbox:
        logger.warning(f"Impossible de calculer la bbox WGS84: {e_bbox}")

    meta = {
        "scenario": scen["nom"],
        "duree_heures": duree_sim,
        "cluster_id": cluster_id,
        "cluster_nom": bassin_nom,
        "bassin_nom": bassin_nom,
        "subcatchments_count": len(sb_gdf),
        "junctions_count": max(0, len(regards) - 1),
        "outfalls_count": 1,
        "conduits_count": len(canalisations),
        "outfall_code": actual_outfall_name,
        "junction_outfall_code": outfall_code,
        "total_area_ha": round(float(sb_gdf["area_ha"].sum()), 2) if not sb_gdf.empty else 0.0,
        "surface_totale_ha": round(float(sb_gdf["area_ha"].sum()), 2) if not sb_gdf.empty else 0.0,
        "surface_urbaine_ha": getattr(sb_gdf, 'attrs', {}).get("total_urbaine_ha", round(float(sb_gdf["area_ha"].sum()), 2) if not sb_gdf.empty else 0.0),
        "convexe_globale_ha": getattr(sb_gdf, 'attrs', {}).get("convexe_globale_ha", 5430.0),
        "ratio_drainage_pct": getattr(sb_gdf, 'attrs', {}).get("ratio_drainage_pct", 55.0),
        "buffer_m": buf_actuel,
        "source_altimetrique": source_alt,
        "pente_moyenne_pct": pente_moyenne_pct,
        "bbox": bbox_wgs84,
        "simulated_nodes": list(clean_target_nodes),
        "conduit_endpoints": conduit_endpoints,
        "typologie_sol": typologie_sol or "habitat_mixte",
        "typologie_nom": typ_nom,
        "imperv_pct": active_imperv,
        "pluvio_station": scen.get("station", "Station ANRH Chlef Siège (010501)"),
        "pluvio_station_id": st_id,
        "pluvio_code_anrh": scen.get("code_anrh", "010501"),
        "pluvio_wilaya": scen.get("wilaya", "Wilaya de Chlef"),
        "pluvio_scenario_key": scenario_key,
        "pluvio_scenario_nom": scen.get("nom"),
        "pluvio_periode_retour": scen.get("periode_retour", "T = 10 ans"),
        "pluvio_intensite_max_mmh": active_i_max,
        "pluvio_montana": scen.get("formule_montana", ""),
        "pluvio_hauteur_totale_mm": hauteur_totale_cumul_mm,
        "pluvio_p24_mm": scen.get("hauteur_p24_mm", 56.0),
        "pluvio_source": scen.get("source", ""),
        "pluvio_description": scen.get("description", ""),
        "bms_info": scen.get("bms_metadata"),
        "raccordements_orphelins": [item[0] for item in racc_orph_valides],
    }

    return lines, meta

