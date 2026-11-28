# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-27
Objet : Génération textuelle des blocs et sections de modélisation du fichier .INP
================================================================================
"""

import math
import logging
from collections import Counter
from typing import Dict, Any, Optional, Tuple, List, Set, Union
import pandas as pd
import geopandas as gpd

from src.domain.moteur_swmm.constants import _clean_node_id
from src.domain.moteur_swmm.assainissement_topologique import _resoudre_altimetrie_noeuds
from src.domain.moteur_swmm.sections_inp_etapes import (
    _ecrire_ouvrages_speciaux, _ecrire_raccordements_orphelins,
    _generer_lignes_conduits, _resoudre_conduits_topologiques,
)
from src.domain.moteur_swmm.sections_inp_etapes_suite import (
    _appliquer_intensite_max, _calculer_pas_raingage, _construire_meta_inp,
    _ecrire_apports_dwf, _ecrire_conduits_frontieres, _ecrire_coordinates,
    _ecrire_polygones_et_report, _finaliser_meta_inp, _lignes_entete_inp,
)

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
    conventions: Optional[Dict[str, Any]] = None,
    etat_reseau: Optional[Dict[str, Any]] = None,
) -> Tuple[List[str], Dict[str, Any]]:
    """
    Génère la liste de lignes de toutes les sections .inp et le dictionnaire meta.
    """
    h_end = int(duree_sim)
    m_end = int((duree_sim - h_end) * 60)
    end_time_str = f"{h_end:02d}:{m_end:02d}:00"
    routing_step_str = f"00:00:{pas_routage_sec:02d}"

    lines = _lignes_entete_inp({
        "altimetrie_meta": altimetrie_meta,
        "duree_sim": duree_sim,
        "end_time_str": end_time_str,
        "pas_routage_sec": pas_routage_sec,
        "routing_step_str": routing_step_str,
        "scen": scen,
    })

    ts_base = scen.get("timeseries", [("00:00", 0.0), ("04:00", 0.0)])
    max_base = max((v for _, v in ts_base), default=scen.get("intensite_max_defaut", 62.0))

    # Détection BMS : si le scénario vient de scenario_personnalise avec bms_metadata,
    # l'hyétogramme est déjà correctement normalisé (cumul exact + forme dynamique).
    # Ne PAS le rescaler — utiliser tel quel.
    is_bms = bool(scen.get("bms_metadata", {}).get("is_bms"))

    effective_timeseries, active_i_max = _appliquer_intensite_max({
        "intensite_max_mmh": intensite_max_mmh,
        "is_bms": is_bms,
        "max_base": max_base,
        "scen": scen,
        "ts_base": ts_base,
    })

    # Intervalle RAINGAGES : pour le format INTENSITY, SWMM intègre chaque
    # valeur de la série sur une durée égale à ce champ. Il doit donc
    # correspondre au pas réel de la série (ex. 0:15 pour un hyétogramme
    # 15 min), sinon la pluie appliquée est diluée/ concentrée (bug constaté :
    # 0:05 codé en dur → ~1/3 de la pluie prévue dans le .rpt).
    interval_raingage = "0:15"
    interval_raingage = _calculer_pas_raingage({
        "effective_timeseries": effective_timeseries,
        "lines": lines,
    })
    for idx, ln in enumerate(lines):
        if ln.startswith("RG1"):
            lines[idx] = (
                f"RG1              INTENSITY {interval_raingage:<9} 1.0      "
                "TIMESERIES TS_SCENARIO"
            )
            break

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

    # Résolveur topologique canonique (ID -> alias -> snap <=0.50 m).
    # Source unique de connectivité partagée avec le graphe de bassins.
    from src.domain.topologie import (
        ResoluteurNoeuds, PROV_ALIAS, PROV_ALIAS_AUTO, PROV_SNAP)
    _conv = conventions or {}
    _alias_noyau = _conv.get('alias_noyau') or {}
    resolveur = ResoluteurNoeuds(
        coord_noeuds,
        tolerance_snap_m=float(_conv.get('snap_tolerance_m') or 0.50),
        correspondance_noyau=bool(_alias_noyau.get('actif')),
        alias_auto_max_dist_m=float(_alias_noyau.get('max_dist_m') or 2.5),
    )

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

    _resoudre_conduits_topologiques({
        "canalisations": canalisations,
        "conduit_nodes": conduit_nodes,
        "conduits_resolus": conduits_resolus,
        "coord_noeuds": coord_noeuds,
        "downstream_nodes": downstream_nodes,
        "noeuds_spatiaux_crees": noeuds_spatiaux_crees,
        "raccordements_spatiaux": raccordements_spatiaux,
        "resolveur": resolveur,
        "upstream_nodes": upstream_nodes,
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
    exutoires_frontiere_info = _ecrire_raccordements_orphelins({
        "canalisations": canalisations,
        "clean_target_nodes": clean_target_nodes,
        "lines": lines,
        "node_elevs": node_elevs,
        "racc_orph_valides": racc_orph_valides,
        "raccordements_orphelins": raccordements_orphelins,
        "regards": regards,
        "seen_outfall_names": seen_outfall_names,
        "sinks_frontiere": sinks_frontiere,
    })
    # Déversoirs d'orage (DVO) issus d'Ouvrages_Speciaux (Chantier 1.5)
    weir_lines = []
    weir_xsec_lines: List[str] = []
    deversoirs_traites = []
    _ecrire_ouvrages_speciaux({
        "conduit_nodes": conduit_nodes,
        "coord_noeuds": coord_noeuds,
        "deversoirs_traites": deversoirs_traites,
        "lines": lines,
        "node_elevs": node_elevs,
        "noeuds_connus_ids": noeuds_connus_ids,
        "ouvrages_speciaux": ouvrages_speciaux,
        "seen_outfall_names": seen_outfall_names,
        "tree_noeuds": tree_noeuds,
        "weir_lines": weir_lines,
        "weir_xsec_lines": weir_xsec_lines,
    })

    lines.append("")

    lines.append("[CONDUITS]")
    lines.append(";;Name           From Node        To Node          Length     Roughness  InOffset   OutOffset  InitFlow   MaxFlow")

    conduit_lines = []
    xsec_lines = list(weir_xsec_lines)
    pump_lines = []
    curve_lines = []
    nref_junction_lines: List[str] = []
    conduit_endpoints = {}
    refoulements_traites = []
    sections_rectangulaires = []
    exclusions_conduits: List[Dict[str, Any]] = []

    from src.domain.moteur_swmm.etat_reseau import (
        normaliser_etat_reseau,
        est_etat_nominal,
        appliquer_etat_conduite,
    )
    _etat_norm = normaliser_etat_reseau(etat_reseau)
    _etat_nominal = est_etat_nominal(_etat_norm)
    _nb_conduits_colmates = 0
    _nb_depots_sig = 0

    # Une pompe par tête de chaîne de refoulement : un tronçon "Refoulement"
    # dont le nœud amont est lui-même l'exutoire d'un autre tronçon de
    # refoulement est un segment de refoulement (conduite sous pression),
    # pas une pompe supplémentaire.
    refoulement_aval: Set[str] = set()
    for cr0 in conduits_resolus:
        _row0 = cr0["row"]
        _f0 = str(_row0.get("FONCTIONMT") or _row0.get("fonctionmt") or "").strip().lower()
        if ("refoul" in _f0 or "pompage" in _f0) and cr0["d_node"]:
            refoulement_aval.add(cr0["d_node"])

    _nb_conduits_colmates, _nb_depots_sig = _generer_lignes_conduits({
        "_etat_nominal": _etat_nominal,
        "_etat_norm": _etat_norm,
        "_nb_conduits_colmates": _nb_conduits_colmates,
        "_nb_depots_sig": _nb_depots_sig,
        "conduit_endpoints": conduit_endpoints,
        "conduit_lines": conduit_lines,
        "conduit_nodes": conduit_nodes,
        "conduits_resolus": conduits_resolus,
        "coord_noeuds": coord_noeuds,
        "curve_lines": curve_lines,
        "exclusions_conduits": exclusions_conduits,
        "node_elevs": node_elevs,
        "noeuds_spatiaux_crees": noeuds_spatiaux_crees,
        "nref_junction_lines": nref_junction_lines,
        "pente_moyenne_pct": pente_moyenne_pct,
        "pump_lines": pump_lines,
        "refoulement_aval": refoulement_aval,
        "refoulements_traites": refoulements_traites,
        "sections_rectangulaires": sections_rectangulaires,
        "xsec_lines": xsec_lines,
    })

    if creer_exutoire_dedie:
        cid_out = f"C_OUT_{outfall_code}"
        max_inlet_d = max([float(c.get("DIAMETRE", 600)) for c in inlet_conduits] or [1000.0])
        diam_out_m = max(1.2, max_inlet_d / 1000.0)
        conduit_lines.append(f"{cid_out:<16} {outfall_code:<16} {actual_outfall_name:<16} 5.00       0.0130     0.000      0.000      0.000      0.000")
        xsec_lines.append(f"{cid_out:<16} CIRCULAR     {diam_out_m:<16.3f} 0.000      0.000      0.000      1")

    _ecrire_conduits_frontieres({
        "conduit_endpoints": conduit_endpoints,
        "conduit_lines": conduit_lines,
        "exutoires_frontiere_info": exutoires_frontiere_info,
        "racc_orph_valides": racc_orph_valides,
        "xsec_lines": xsec_lines,
    })

    if nref_junction_lines:
        _idx_outfalls = lines.index("[OUTFALLS]")
        lines[_idx_outfalls:_idx_outfalls] = nref_junction_lines

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
    apports_meta, apports_ignores = _ecrire_apports_dwf({
        "actual_outfall_name": actual_outfall_name,
        "apports_dwf": apports_dwf,
        "conduit_nodes": conduit_nodes,
        "duree_sim": duree_sim,
        "lines": lines,
        "noeuds_traites": noeuds_traites,
        "outfall_code": outfall_code,
        "pos_fin_timeseries": pos_fin_timeseries,
    })

    _ecrire_coordinates({
        "actual_outfall_name": actual_outfall_name,
        "coord_noeuds": coord_noeuds,
        "creer_exutoire_dedie": creer_exutoire_dedie,
        "exutoires_frontiere_info": exutoires_frontiere_info,
        "exutoires_map": exutoires_map,
        "lines": lines,
        "outfall_code": outfall_code,
        "racc_orph_valides": racc_orph_valides,
        "regards": regards,
        "rejets": rejets,
        "target_ex_id": target_ex_id,
    })
    lines.append("")

    lines.append("[POLYGONS]")
    lines.extend(swmm_sec["POLYGONS"])
    lines.append("")

    _ecrire_polygones_et_report({
        "canalisations": canalisations,
        "lines": lines,
        "regards": regards,
    })

    bbox_wgs84 = None
    meta = _construire_meta_inp({
        "_conv": _conv,
        "_etat_nominal": _etat_nominal,
        "_etat_norm": _etat_norm,
        "_nb_conduits_colmates": _nb_conduits_colmates,
        "_nb_depots_sig": _nb_depots_sig,
        "active_i_max": active_i_max,
        "active_imperv": active_imperv,
        "actual_outfall_name": actual_outfall_name,
        "apports_ignores": apports_ignores,
        "apports_meta": apports_meta,
        "bassin_nom": bassin_nom,
        "buf_actuel": buf_actuel,
        "canalisations": canalisations,
        "clean_target_nodes": clean_target_nodes,
        "cluster_id": cluster_id,
        "conduit_endpoints": conduit_endpoints,
        "deversoirs_traites": deversoirs_traites,
        "duree_sim": duree_sim,
        "exutoires_frontiere_info": exutoires_frontiere_info,
        "hauteur_totale_cumul_mm": hauteur_totale_cumul_mm,
        "outfall_code": outfall_code,
        "outfall_demande": outfall_demande,
        "pente_moyenne_pct": pente_moyenne_pct,
        "racc_orph_valides": racc_orph_valides,
        "raccordements_spatiaux": raccordements_spatiaux,
        "refoulements_traites": refoulements_traites,
        "regards": regards,
        "resolution_exutoire": resolution_exutoire,
        "sb_gdf": sb_gdf,
        "scen": scen,
        "scenario_key": scenario_key,
        "sections_rectangulaires": sections_rectangulaires,
        "source_alt": source_alt,
        "st_id": st_id,
        "typ_nom": typ_nom,
        "typologie_sol": typologie_sol,
    })

    _finaliser_meta_inp({
        "conduit_lines": conduit_lines,
        "deversoirs_traites": deversoirs_traites,
        "exclusions_conduits": exclusions_conduits,
        "gpkg_counts": gpkg_counts,
        "lines": lines,
        "meta": meta,
        "raccordements_spatiaux": raccordements_spatiaux,
        "refoulements_traites": refoulements_traites,
        "sections_rectangulaires": sections_rectangulaires,
    })

    return lines, meta

