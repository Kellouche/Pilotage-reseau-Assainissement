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

import math
import logging
from typing import Dict, Any, Optional, Tuple, List, Set, Union
import pandas as pd
import geopandas as gpd

from src.domain.moteur_swmm.constants import _clean_node_id
from src.domain.moteur_swmm.assainissement_topologique import _resoudre_altimetrie_noeuds

logger = logging.getLogger("swmm_platform.moteur_swmm.sections_inp")


def _determiner_rugosite(materiau: Any) -> float:
    """Détermine le coefficient de Manning n en fonction du matériau réel du SIG (Chantier 1.4)."""
    mat = str(materiau or "").strip().lower()
    if any(k in mat for k in ("pehd", "polyethyl", "polyéthyl")):
        return 0.010
    elif "pvc" in mat:
        return 0.011
    elif any(k in mat for k in ("prv", "resine", "résine")):
        return 0.011
    elif any(k in mat for k in ("acier", "fonte")):
        return 0.012
    elif any(k in mat for k in ("beton", "béton")):
        return 0.013
    elif any(k in mat for k in ("maconnerie", "maçonnerie")):
        return 0.015
    return 0.013  # Défaut documenté comme hypothèse


def _determiner_forme_section(c: pd.Series, diam_m: float) -> Tuple[str, float, float, int]:
    """Détermine la forme géométrique transversale dans [XSECTIONS] (Chantier 1.3)."""
    forme_str = str(c.get("FORMESECT") or c.get("forme_sect") or c.get("FORME") or "").strip().lower()
    if any(k in forme_str for k in ("rect", "carr")):
        h_raw = c.get("HAUTEUR") or c.get("hauteur")
        b_raw = c.get("GDEBASE") or c.get("gdebase") or c.get("largeur") or c.get("BASE")
        try:
            h_m = float(h_raw) / 1000.0 if pd.notna(h_raw) and float(h_raw) > 0 else diam_m
        except Exception:
            h_m = diam_m
        try:
            b_m = float(b_raw) / 1000.0 if pd.notna(b_raw) and float(b_raw) > 0 else diam_m
        except Exception:
            b_m = diam_m
        h_m = max(0.2, round(h_m, 3))
        b_m = max(0.2, round(b_m, 3))
        return ("RECTANGULAR", h_m, b_m, 1)
    return ("CIRCULAR", max(0.2, round(diam_m, 3)), 0.0, 1)


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
    buf_actuel: float,
    apports_dwf: Optional[List[Dict[str, Any]]] = None,
    elevations_terrain: Optional[Dict[str, float]] = None,
    altimetrie_meta: Optional[Dict[str, Any]] = None,
    cotes_validations: Optional[Dict[str, float]] = None,
    stations_relevage: Optional[gpd.GeoDataFrame] = None,
    ouvrages_speciaux: Optional[gpd.GeoDataFrame] = None,
    gpkg_counts: Optional[Dict[str, Any]] = None,
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
        *([f";; Altimétrie : terrain IDW — couche {altimetrie_meta.get('layer_nom') or altimetrie_meta.get('layer_id')}, "
           f"résolution {altimetrie_meta.get('resolution_m')} m, "
           f"artefact sha {str(altimetrie_meta.get('gpkg_sha256') or '')[:8]}… "
           f"(cotes estimées — ≠ mesures radier)"
          ] if altimetrie_meta else []),
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
    # Position d'insertion des séries [TIMESERIES] DWF (LOT P1.3) : juste
    # avant la ligne vide qui clôt la section, après TS_SCENARIO.
    pos_fin_timeseries = len(lines)
    lines.append("")

    for sec_name in ["SUBCATCHMENTS", "SUBAREAS", "INFILTRATION"]:
        lines.append(f"[{sec_name}]")
        lines.extend(swmm_sec[sec_name])
        lines.append("")

    # ── Résolution de l'exutoire physique du modèle ──────────────────────
    # Le cluster_id peut désigner un ouvrage spécial (déversoir d'orage,
    # rejet) qui n'est pas une extrémité de conduit : dans ce cas la
    # propagation altimétrique depuis l'exutoire est impossible et
    # produirait un réseau plat (tous radier à la même cote). On résout
    # alors le nœud d'exutoire réel = le sink du sous-réseau le plus
    # proche de l'ouvrage demandé (choix déterministe).
    # ── Résolution de l'exutoire physique et topologie du modèle ────────
    coord_noeuds: Dict[str, Tuple[float, float]] = {}
    for _, r in regards.iterrows():
        _nid = _clean_node_id(r.get("Code"))
        if _nid and hasattr(r, "geometry") and r.geometry is not None and not r.geometry.is_empty:
            try:
                coord_noeuds[_nid] = (float(r.geometry.x), float(r.geometry.y))
            except Exception:
                pass

    if rejets is not None and not rejets.empty:
        for idx, rj in rejets.iterrows():
            _rid = _clean_node_id(rj.get("Code") or rj.get("CODE") or rj.get("id") or rj.get("NOM"), fallback=f"REJ_{idx+1}")
            if _rid and hasattr(rj, "geometry") and rj.geometry is not None and not rj.geometry.is_empty:
                try:
                    coord_noeuds[_rid] = (float(rj.geometry.x), float(rj.geometry.y))
                except Exception:
                    pass

    if stations_relevage is not None and not stations_relevage.empty:
        for idx, st in stations_relevage.iterrows():
            _sid = _clean_node_id(st.get("Code") or st.get("CODEPRR") or st.get("NOMOUVR") or st.get("id"), fallback=f"SR_{idx+1}")
            if _sid and hasattr(st, "geometry") and st.geometry is not None and not st.geometry.is_empty:
                try:
                    coord_noeuds[_sid] = (float(st.geometry.x), float(st.geometry.y))
                except Exception:
                    pass

    # Index spatial KD-Tree pour le raccordement ciblé des orphelins résiduels (Chantier 3)
    tree_noeuds = None
    noeuds_connus_ids: List[str] = []
    if coord_noeuds:
        noeuds_connus_ids = list(coord_noeuds.keys())
        try:
            from scipy.spatial import cKDTree
            tree_noeuds = cKDTree([coord_noeuds[nid] for nid in noeuds_connus_ids])
        except Exception:
            tree_noeuds = None

    raccordements_spatiaux: List[Dict[str, Any]] = []
    noeuds_spatiaux_crees: Dict[str, Tuple[float, float]] = {}

    conduit_nodes = set()
    upstream_nodes = set()
    downstream_nodes = set()
    conduits_resolus: List[Dict[str, Any]] = []

    for idx, c in canalisations.iterrows():
        cid = f"C_{idx+1}"
        u_node = _clean_node_id(c.get("ID_AMONT"))
        d_node = _clean_node_id(c.get("ID_AVAL"))

        pt_start, pt_end = None, None
        geom = c.geometry if hasattr(c, "geometry") else None
        if geom is not None and not geom.is_empty:
            try:
                if geom.geom_type == "LineString":
                    coords = list(geom.coords)
                    pt_start = (float(coords[0][0]), float(coords[0][1]))
                    pt_end = (float(coords[-1][0]), float(coords[-1][1]))
                elif geom.geom_type == "MultiLineString" and len(geom.geoms) > 0:
                    c_first = list(geom.geoms[0].coords)
                    c_last = list(geom.geoms[-1].coords)
                    pt_start = (float(c_first[0][0]), float(c_first[0][1]))
                    pt_end = (float(c_last[-1][0]), float(c_last[-1][1]))
            except Exception:
                pass

        # Filet de sécurité spatial amont (Chantier 3)
        if not u_node:
            if pt_start and tree_noeuds is not None:
                d_c, i_c = tree_noeuds.query(pt_start)
                if d_c <= 0.50:
                    u_node = noeuds_connus_ids[i_c]
                    raccordements_spatiaux.append({"cid": cid, "extremite": "amont", "noeud": u_node, "distance_m": round(float(d_c), 3)})
            if not u_node and pt_start:
                u_node = f"N_{cid}_U"
                coord_noeuds[u_node] = pt_start
                noeuds_spatiaux_crees[u_node] = pt_start

        # Filet de sécurité spatial aval (Chantier 3)
        if not d_node:
            if pt_end and tree_noeuds is not None:
                d_c, i_c = tree_noeuds.query(pt_end)
                if d_c <= 0.50:
                    d_node = noeuds_connus_ids[i_c]
                    raccordements_spatiaux.append({"cid": cid, "extremite": "aval", "noeud": d_node, "distance_m": round(float(d_c), 3)})
            if not d_node and pt_end:
                d_node = f"N_{cid}_D"
                coord_noeuds[d_node] = pt_end
                noeuds_spatiaux_crees[d_node] = pt_end

        if u_node and d_node and u_node == d_node:
            d_node = f"N_{cid}_D"
            if pt_end:
                coord_noeuds[d_node] = pt_end
                noeuds_spatiaux_crees[d_node] = pt_end

        if u_node and d_node:
            conduit_nodes.add(u_node)
            upstream_nodes.add(u_node)
            conduit_nodes.add(d_node)
            downstream_nodes.add(d_node)

        conduits_resolus.append({
            "idx": idx,
            "cid": cid,
            "u_node": u_node,
            "d_node": d_node,
            "row": c,
            "pt_start": pt_start,
            "pt_end": pt_end,
        })

    outfall_demande = outfall_code
    noeuds_conduits = upstream_nodes | downstream_nodes
    sinks_disponibles = downstream_nodes - upstream_nodes

    pt_exutoire_demande = None
    if target_ex_id and exutoires_map:
        _ex_info = exutoires_map.get(target_ex_id) or {}
        _geom = _ex_info.get("geometry")
        if _geom is not None and not getattr(_geom, "is_empty", True):
            try:
                pt_exutoire_demande = (float(_geom.x), float(_geom.y))
            except Exception:
                pt_exutoire_demande = None
        if pt_exutoire_demande is None and _ex_info.get("x") is not None and _ex_info.get("y") is not None:
            try:
                pt_exutoire_demande = (float(_ex_info["x"]), float(_ex_info["y"]))
            except Exception:
                pt_exutoire_demande = None

    def _cle_sans_exutoire(nid: str):
        """Tri déterministe : proximité à l'ouvrage demandé puis nom."""
        if pt_exutoire_demande is not None and nid in coord_noeuds:
            dx = coord_noeuds[nid][0] - pt_exutoire_demande[0]
            dy = coord_noeuds[nid][1] - pt_exutoire_demande[1]
            return (dx * dx + dy * dy, nid)
        return (float("inf"), nid)

    inlet_conduits = [c for _, c in canalisations.iterrows() if _clean_node_id(c.get("ID_AVAL")) == outfall_code]
    resolution_exutoire = "directe"
    if (outfall_code not in noeuds_conduits or len(inlet_conduits) == 0) and sinks_disponibles:
        outfall_code = min(sinks_disponibles, key=_cle_sans_exutoire)
        inlet_conduits = [c for _, c in canalisations.iterrows() if _clean_node_id(c.get("ID_AVAL")) == outfall_code]
        resolution_exutoire = ("sink_proche_ouvrage" if outfall_demande != outfall_code
                               else "sink_sans_entree")

    # Sinks restants = frontières du sous-réseau tronqué : chacun reçoit
    # un exutoire libre dédié pour ne pas produire d'inondation artificielle.
    sinks_frontiere = sorted(
        (sinks_disponibles - {outfall_code}) - {""},
        key=lambda n: (n.isdigit() is False, n)
    )

    node_elevs, source_alt = _resoudre_altimetrie_noeuds(
        regards, canalisations, rejets, outfall_code, pente_moyenne_pct,
        elevations_terrain=elevations_terrain, altimetrie_meta=altimetrie_meta)
    outfall_elev = node_elevs.get(outfall_code, 100.0)

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
        # Règle de validation des cotes nodales (Human-in-the-Loop) :
        if cotes_validations:
            code_brut = str(r.get("Code", ""))
            if nid in cotes_validations:
                prof = float(cotes_validations[nid])
            elif code_brut in cotes_validations:
                prof = float(cotes_validations[code_brut])
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

    # Exutoires frontières : chaque sink résiduel du sous-réseau tronqué
    # déverse librement vers un exutoire dédié — sinon ce nœud, privé de
    # toute issue, produit une inondation artificielle garantie.
    reg_ids_orphelins = {item[2] for item in racc_orph_valides}
    exutoires_frontiere_info = []
    for _sink in sinks_frontiere:
        if _sink in reg_ids_orphelins:
            continue
        _z_sink = node_elevs.get(_sink, 100.0)
        _out_bnd = f"OUT_BND_{_sink}"
        if _out_bnd in seen_outfall_names:
            _out_bnd = f"OUT_BND_{_sink}_{len(exutoires_frontiere_info) + 1}"
        seen_outfall_names.add(_out_bnd)
        _z_out_bnd = round(_z_sink - 0.05, 3)
        lines.append(f"{_out_bnd:<16} {_z_out_bnd:<10.3f} FREE                        NO")
        _inlets_sink = [c for _, c in canalisations.iterrows()
                        if _clean_node_id(c.get("ID_AVAL")) == _sink]
        _d_sink_mm = max([float(c.get("DIAMETRE", 600)) for c in _inlets_sink] or [600.0])
        exutoires_frontiere_info.append({
            "node": _sink, "outfall": _out_bnd,
            "elev_node": _z_sink, "diam_mm": _d_sink_mm,
        })
    # Déversoirs d'orage (DVO) issus d'Ouvrages_Speciaux (Chantier 1.5)
    weir_lines = []
    deversoirs_traites = []
    if ouvrages_speciaux is not None and not ouvrages_speciaux.empty:
        import unicodedata
        for o_idx, ouv in ouvrages_speciaux.iterrows():
            raw_t = str(ouv.get("TYPEOUVR") or ouv.get("Type") or "")
            norm_t = "".join(ch for ch in unicodedata.normalize("NFD", raw_t) if unicodedata.category(ch) != "Mn").lower()
            if "deversoir" in norm_t or "dvo" in norm_t:
                wid = f"W_{_clean_node_id(ouv.get('Code'), fallback=f'DVO_{o_idx+1}')}"
                o_pt = None
                if hasattr(ouv, "geometry") and ouv.geometry is not None and not ouv.geometry.is_empty:
                    o_pt = (float(ouv.geometry.x), float(ouv.geometry.y))

                u_weir = None
                if o_pt and tree_noeuds is not None:
                    d_w, i_w = tree_noeuds.query(o_pt)
                    if d_w <= 45.0:
                        u_weir = noeuds_connus_ids[i_w]

                if u_weir and u_weir in conduit_nodes:
                    w_out = f"OUT_{wid}"
                    if w_out in seen_outfall_names:
                        w_out = f"OUT_{wid}_{o_idx+1}"
                    seen_outfall_names.add(w_out)
                    z_reg = node_elevs.get(u_weir, 100.0)
                    z_w_out = round(z_reg - 0.20, 3)
                    lines.append(f"{w_out:<16} {z_w_out:<10.3f} FREE                        NO")
                    h_seuil_raw = ouv.get("H_de_Seuil") or ouv.get("loSeuil")
                    try:
                        h_seuil = float(h_seuil_raw) if pd.notna(h_seuil_raw) and float(h_seuil_raw) > 0 else 0.50
                    except Exception:
                        h_seuil = 0.50
                    weir_lines.append(f"{wid:<16} {u_weir:<16} {w_out:<16} TRANSVERSE   {h_seuil:<10.3f} 1.800      NO       0        0.000    NO")
                    coord_noeuds[w_out] = (o_pt[0] + 5.0, o_pt[1] + 5.0) if o_pt else (100.0, 100.0)
                    deversoirs_traites.append({"wid": wid, "u_node": u_weir, "outfall": w_out, "h_seuil": h_seuil})

    lines.append("")

    lines.append("[CONDUITS]")
    lines.append(";;Name           From Node        To Node          Length     Roughness  InOffset   OutOffset  InitFlow   MaxFlow")

    conduit_lines = []
    xsec_lines = []
    pump_lines = []
    curve_lines = []
    conduit_endpoints = {}
    refoulements_traites = []
    sections_rectangulaires = []

    for cr in conduits_resolus:
        cid = cr["cid"]
        u_node = cr["u_node"]
        d_node = cr["d_node"]
        c = cr["row"]
        if not u_node or not d_node or u_node == d_node:
            continue
        length = float(c["Longeur"]) if ("Longeur" in c and pd.notna(c["Longeur"]) and c["Longeur"] > 0) else float(c.geometry.length)
        length = max(1.0, round(length, 2))
        
        # Rugosité dynamique par matériau réel (Chantier 1.4)
        rough = _determiner_rugosite(c.get("MATERIAU"))
        
        diam_mm = float(c["DIAMETRE"]) if ("DIAMETRE" in c and pd.notna(c["DIAMETRE"]) and c["DIAMETRE"] > 0) else 600.0
        diam_m = max(0.2, diam_mm / 1000.0)

        # Forme géométrique transversale (Chantier 1.3)
        shape, geom1, geom2, barrels = _determiner_forme_section(c, diam_m)
        if shape == "RECTANGULAR":
            sections_rectangulaires.append({"cid": cid, "hauteur_m": geom1, "largeur_m": geom2})

        # Détection de refoulement (Chantier 1.1)
        fct = str(c.get("FONCTIONMT") or c.get("fonctionmt") or "").strip().lower()
        is_refoulement = ("refoul" in fct or "pompage" in fct)

        nom_v = str(c.get("NOM-VOIE") or c.get("NOMVOIE") or c.get("nom_voie") or "").strip()
        if nom_v.lower() in ("nan", "none", "null", ""):
            nom_v = ""

        if is_refoulement:
            # Modélisation physique SWMM 5.2 : [PUMPS] alimentée par courbe [CURVES] + conduite en charge aval
            n_ref_node = f"N_REF_{cid}"
            coord_u = coord_noeuds.get(u_node, (100.0, 100.0))
            coord_noeuds[n_ref_node] = (coord_u[0] + 1.0, coord_u[1] + 1.0)
            noeuds_spatiaux_crees[n_ref_node] = coord_noeuds[n_ref_node]
            conduit_nodes.add(n_ref_node)

            pump_id = f"PMP_{cid}"
            curve_id = f"CURV_PMP_{cid}"
            pump_lines.append(f"{pump_id:<16} {u_node:<16} {n_ref_node:<16} {curve_id:<16} ON       0.000      0.000")

            # Courbe de pompe caractéristique Type 1 débit/hauteur selon diamètre nominal
            q_nom = round(math.pi * (diam_m / 2.0)**2 * 1.5, 4)
            curve_lines.append(f"{curve_id:<16} PUMP       0.000      35.00")
            curve_lines.append(f"{curve_id:<16}            {q_nom:<10.4f} 25.00")
            curve_lines.append(f"{curve_id:<16}            {round(q_nom * 1.5, 4):<10.4f} 10.00")

            conduit_lines.append(f"{cid:<16} {n_ref_node:<16} {d_node:<16} {length:<10.2f} {rough:<10.4f} 0.000      0.000      0.000      0.000")
            if shape == "RECTANGULAR":
                xsec_lines.append(f"{cid:<16} RECTANGULAR  {geom1:<16.3f} {geom2:<10.3f} 0.000      0.000      {barrels}")
            else:
                xsec_lines.append(f"{cid:<16} CIRCULAR     {geom1:<16.3f} 0.000      0.000      0.000      {barrels}")

            conduit_endpoints[cid] = {
                "u": n_ref_node,
                "d": d_node,
                "length": length,
                "diam_mm": diam_mm,
                "material": str(c.get("MATERIAU", "PEHD")),
                "nom_voie": nom_v,
                "fonction": "refoulement",
                "pompe": pump_id
            }
            refoulements_traites.append({
                "cid": cid,
                "pompe": pump_id,
                "station_amont": u_node,
                "exutoire_aval": d_node,
                "diametre_mm": diam_mm,
                "longueur_m": length,
                "debit_nominal_m3s": q_nom
            })
        else:
            conduit_lines.append(f"{cid:<16} {u_node:<16} {d_node:<16} {length:<10.2f} {rough:<10.4f} 0.000      0.000      0.000      0.000")
            if shape == "RECTANGULAR":
                xsec_lines.append(f"{cid:<16} RECTANGULAR  {geom1:<16.3f} {geom2:<10.3f} 0.000      0.000      {barrels}")
            else:
                xsec_lines.append(f"{cid:<16} CIRCULAR     {geom1:<16.3f} 0.000      0.000      0.000      {barrels}")

            conduit_endpoints[cid] = {
                "u": u_node,
                "d": d_node,
                "length": length,
                "diam_mm": diam_mm,
                "material": str(c.get("MATERIAU", "Béton")),
                "nom_voie": nom_v,
                "fonction": "gravitaire"
            }

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

    for _bnd in exutoires_frontiere_info:
        _cid_bnd = f"C_BND_{_bnd['node']}"
        _d_bnd_m = max(0.3, _bnd["diam_mm"] / 1000.0)
        conduit_lines.append(f"{_cid_bnd:<16} {_bnd['node']:<16} {_bnd['outfall']:<16} 5.00       0.0130     0.000      0.000      0.000      0.000")
        xsec_lines.append(f"{_cid_bnd:<16} CIRCULAR     {_d_bnd_m:<16.3f} 0.000      0.000      0.000      1")
        conduit_endpoints[_cid_bnd] = {
            "u": _bnd["node"],
            "d": _bnd["outfall"],
            "length": 5.0,
            "diam_mm": _bnd["diam_mm"],
            "material": "Frontière de sous-réseau",
            "nom_voie": "Exutoire frontière (tronçon coupé)"
        }

    lines.extend(conduit_lines)
    lines.append("")

    if pump_lines:
        lines.append("[PUMPS]")
        lines.append(";;Name           From Node        To Node          Pump Curve       Status   Startup  Shutoff")
        lines.extend(pump_lines)
        lines.append("")

    if weir_lines:
        lines.append("[WEIRS]")
        lines.append(";;Name           From Node        To Node          Type         CrestHt    Cd         Gated    EndCon   EndCoeff Surcharge")
        lines.extend(weir_lines)
        lines.append("")

    lines.append("[XSECTIONS]")
    lines.append(";;Link           Shape        Geom1            Geom2      Geom3      Geom4      Barrels    Culvert")
    lines.extend(xsec_lines)
    lines.append("")

    if curve_lines:
        lines.append("[CURVES]")
        lines.append(";;Name           Type       X-Value    Y-Value")
        lines.extend(curve_lines)
        lines.append("")

    # ------------------------------------------------------------------
    # LOT P1.3 — Apports de temps sec (DWF)
    # [PATTERNS] / [DWF] / [INFLOWS] + lignes [TIMESERIES] dédiées.
    # Sans apports actifs, aucune section n'est émise : le .inp produit
    # est strictement identique à l'historique.
    # ------------------------------------------------------------------
    apports_meta: List[Dict[str, Any]] = []
    apports_ignores: List[Dict[str, Any]] = []
    if apports_dwf:
        from src.domain.moteur_swmm.dwf_injection import construire_injection_dwf
        from datetime import datetime as _dt, timedelta as _td
        # Nœuds injectables = JUNCTIONS réellement émises (regards +
        # nœuds topologiques + exutoire), jamais l'OUTFALL dédié.
        noeuds_injectables = set(noeuds_traites) | set(conduit_nodes) | {outfall_code}
        noeuds_injectables.discard(actual_outfall_name)
        noeuds_injectables.discard("")
        # Fenêtre absolue = START_DATE/START_TIME → END_DATE/END_TIME du .inp
        _debut = _dt(2026, 1, 1, 0, 0, 0)
        _fin = _debut + _td(hours=int(duree_sim), minutes=int((duree_sim - int(duree_sim)) * 60))
        _inj = construire_injection_dwf(apports_dwf, noeuds_injectables, _debut, _fin)
        apports_meta = _inj["apports_meta"]
        apports_ignores = _inj["ignores"]
        if _inj["timeseries_lines"]:
            lines[pos_fin_timeseries:pos_fin_timeseries] = _inj["timeseries_lines"]
            pos_fin_timeseries += len(_inj["timeseries_lines"])
        if _inj["pattern_lines"]:
            lines.append("[PATTERNS]")
            lines.append(";;Name           Type       Multipliers")
            lines.extend(_inj["pattern_lines"])
            lines.append("")
        if _inj["dwf_lines"]:
            lines.append("[DWF]")
            lines.append(";;Node           Parameter   Value        Pattern1   Pattern2   Pattern3   Pattern4")
            lines.extend(_inj["dwf_lines"])
            lines.append("")
        if _inj["inflow_lines"]:
            lines.append("[INFLOWS]")
            lines.append(";;Node           Constituent  Time Series  Type     Mfactor  Sfactor  Baseline Pattern")
            lines.extend(_inj["inflow_lines"])
            lines.append("")
        if apports_ignores:
            logger.info("Apports DWF ignorés à l'injection : %s", apports_ignores)

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

    for _bnd in exutoires_frontiere_info:
        _out_bnd = _bnd["outfall"]
        if _out_bnd not in coords_traitees:
            _pt = coord_noeuds.get(_bnd["node"])
            if _pt is not None:
                _pt = (float(_pt[0]) + 5.0, float(_pt[1]) + 5.0)
            if _pt is None and _bnd["node"] in noeuds_regards:
                _g = noeuds_regards[_bnd["node"]].geometry
                _pt = (float(_g.x) + 5.0, float(_g.y) + 5.0)
            if _pt is None and coords_traitees:
                _pt = (100.0, 100.0)
            if _pt is not None:
                lines.append(f"{_out_bnd:<16} {float(_pt[0]):<18.3f} {float(_pt[1]):<18.3f}")
                coords_traitees.add(_out_bnd)

    # Complétude spatiale : garantir que chaque nœud présent dans le modèle a ses coordonnées dans [COORDINATES]
    for nid, pt in coord_noeuds.items():
        if nid not in coords_traitees:
            lines.append(f"{nid:<16} {pt[0]:<18.3f} {pt[1]:<18.3f}")
            coords_traitees.add(nid)
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
        "outfall_demande": outfall_demande,
        "resolution_exutoire": resolution_exutoire,
        "exutoires_frontiere": [b["node"] for b in exutoires_frontiere_info],
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
        "apports_dwf": apports_meta,
        "apports_dwf_ignores": apports_ignores,
        "raccordements_orphelins": [item[0] for item in racc_orph_valides],
        "refoulements_traites": refoulements_traites,
        "raccordements_spatiaux": raccordements_spatiaux,
        "sections_rectangulaires": sections_rectangulaires,
        "deversoirs_traites": deversoirs_traites,
    }

    try:
        from src.domain.moteur_swmm.audit_exclusions import generer_bilan_reconciliation
        sections_presents = {l.strip()[1:-1] for l in lines if l.startswith("[") and l.endswith("]")}
        inp_counts = {
            "canalisations_gravitaires": len(conduit_lines) - len(refoulements_traites),
            "canalisations_refoulement": len(refoulements_traites),
            "regards": len([l for l in lines if l.startswith(";;") is False and len(l.split()) >= 6 and "[" not in l]),
            "rejets": len([l for l in lines if "FREE" in l and "[" not in l]),
            "stations_relevage": len(refoulements_traites),
            "deversoirs_orage": len(deversoirs_traites),
        }
        meta["reconciliation"] = generer_bilan_reconciliation(
            gpkg_counts=gpkg_counts or {},
            inp_counts=inp_counts,
            exclusions=[],
            sections_inp_presents=sections_presents,
            hypotheses=[
                {"domaine": "pompes", "detail": "Courbe caractéristique Type 1 estimée à partir du diamètre nominal"},
                {"domaine": "rugosite", "detail": "Formulation Manning différenciée selon la colonne MATERIAU"},
                {"domaine": "sections", "detail": f"{len(sections_rectangulaires)} sections rectangulaires prises en compte (FORMESECT, HAUTEUR, GDEBASE)"},
                {"domaine": "raccordements_spatiaux", "detail": f"{len(raccordements_spatiaux)} tronçons raccordés par tolérance spatiale <= 0.50m"},
            ]
        )
    except Exception as e_rec:
        logger.warning(f"Bilan de réconciliation non calculé: {e_rec}")

    return lines, meta

