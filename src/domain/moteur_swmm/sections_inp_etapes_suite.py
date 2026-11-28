# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Étapes finales de génération des sections .INP (extrait verbatim de
         src/domain/moteur_swmm/sections_inp.py)
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

logger = logging.getLogger("swmm_platform.moteur_swmm.sections_inp")


def _ecrire_conduits_frontieres(ctx):
    """Étape extraite verbatim de generer_lignes_sections_inp."""
    conduit_endpoints = ctx["conduit_endpoints"]
    conduit_lines = ctx["conduit_lines"]
    exutoires_frontiere_info = ctx["exutoires_frontiere_info"]
    racc_orph_valides = ctx["racc_orph_valides"]
    xsec_lines = ctx["xsec_lines"]

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



def _ecrire_apports_dwf(ctx):
    """Étape extraite verbatim de generer_lignes_sections_inp."""
    actual_outfall_name = ctx["actual_outfall_name"]
    apports_dwf = ctx["apports_dwf"]
    conduit_nodes = ctx["conduit_nodes"]
    duree_sim = ctx["duree_sim"]
    lines = ctx["lines"]
    noeuds_traites = ctx["noeuds_traites"]
    outfall_code = ctx["outfall_code"]
    pos_fin_timeseries = ctx["pos_fin_timeseries"]

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

    return apports_meta, apports_ignores



def _ecrire_coordinates(ctx):
    """Étape extraite verbatim de generer_lignes_sections_inp."""
    actual_outfall_name = ctx["actual_outfall_name"]
    coord_noeuds = ctx["coord_noeuds"]
    creer_exutoire_dedie = ctx["creer_exutoire_dedie"]
    exutoires_frontiere_info = ctx["exutoires_frontiere_info"]
    exutoires_map = ctx["exutoires_map"]
    lines = ctx["lines"]
    outfall_code = ctx["outfall_code"]
    racc_orph_valides = ctx["racc_orph_valides"]
    regards = ctx["regards"]
    rejets = ctx["rejets"]
    target_ex_id = ctx["target_ex_id"]

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



def _ecrire_polygones_et_report(ctx):
    """Étape extraite verbatim de generer_lignes_sections_inp."""
    canalisations = ctx["canalisations"]
    lines = ctx["lines"]
    regards = ctx["regards"]

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



def _construire_meta_inp(ctx):
    """Étape extraite verbatim de generer_lignes_sections_inp."""
    _conv = ctx["_conv"]
    _etat_nominal = ctx["_etat_nominal"]
    _etat_norm = ctx["_etat_norm"]
    _nb_conduits_colmates = ctx["_nb_conduits_colmates"]
    _nb_depots_sig = ctx["_nb_depots_sig"]
    active_i_max = ctx["active_i_max"]
    active_imperv = ctx["active_imperv"]
    actual_outfall_name = ctx["actual_outfall_name"]
    apports_ignores = ctx["apports_ignores"]
    apports_meta = ctx["apports_meta"]
    bassin_nom = ctx["bassin_nom"]
    buf_actuel = ctx["buf_actuel"]
    canalisations = ctx["canalisations"]
    clean_target_nodes = ctx["clean_target_nodes"]
    cluster_id = ctx["cluster_id"]
    conduit_endpoints = ctx["conduit_endpoints"]
    deversoirs_traites = ctx["deversoirs_traites"]
    duree_sim = ctx["duree_sim"]
    exutoires_frontiere_info = ctx["exutoires_frontiere_info"]
    hauteur_totale_cumul_mm = ctx["hauteur_totale_cumul_mm"]
    outfall_code = ctx["outfall_code"]
    outfall_demande = ctx["outfall_demande"]
    pente_moyenne_pct = ctx["pente_moyenne_pct"]
    racc_orph_valides = ctx["racc_orph_valides"]
    raccordements_spatiaux = ctx["raccordements_spatiaux"]
    refoulements_traites = ctx["refoulements_traites"]
    regards = ctx["regards"]
    resolution_exutoire = ctx["resolution_exutoire"]
    sb_gdf = ctx["sb_gdf"]
    scen = ctx["scen"]
    scenario_key = ctx["scenario_key"]
    sections_rectangulaires = ctx["sections_rectangulaires"]
    source_alt = ctx["source_alt"]
    st_id = ctx["st_id"]
    typ_nom = ctx["typ_nom"]
    typologie_sol = ctx["typologie_sol"]

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
        "conventions_decouvertes": _conv or None,
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
        "etat_reseau": {
            **_etat_norm,
            "est_nominal": _etat_nominal,
            "nb_conduits_colmates": _nb_conduits_colmates,
            "nb_depots_sig_appliques": _nb_depots_sig,
        },
    }
    return meta



def _finaliser_meta_inp(ctx):
    """Étape extraite verbatim de generer_lignes_sections_inp."""
    conduit_lines = ctx["conduit_lines"]
    deversoirs_traites = ctx["deversoirs_traites"]
    exclusions_conduits = ctx["exclusions_conduits"]
    gpkg_counts = ctx["gpkg_counts"]
    lines = ctx["lines"]
    meta = ctx["meta"]
    raccordements_spatiaux = ctx["raccordements_spatiaux"]
    refoulements_traites = ctx["refoulements_traites"]
    sections_rectangulaires = ctx["sections_rectangulaires"]

    try:
        from src.domain.moteur_swmm.audit_exclusions import generer_bilan_reconciliation
        sections_presents = {l.strip()[1:-1] for l in lines if l.startswith("[") and l.endswith("]")}
        _nb_conduits_synth = len([
            l for l in conduit_lines
            if l.split() and l.split()[0].startswith(("C_OUT_", "C_RACC_", "C_BND_"))
        ])
        inp_counts = {
            "canalisations_gravitaires": len(conduit_lines) - len(refoulements_traites) - _nb_conduits_synth,
            "canalisations_refoulement": len(refoulements_traites),
            "regards": len([l for l in lines if l.startswith(";;") is False and len(l.split()) >= 6 and "[" not in l]),
            "rejets": len([l for l in lines if "FREE" in l and "[" not in l]),
            "stations_relevage": sum(1 for r in refoulements_traites if r.get("tete_refoulement")),
            "deversoirs_orage": len(deversoirs_traites),
        }
        exclusions_audit = [
            {
                "id": e["cid"],
                "type_objet": "canalisation",
                "motif": "id_inconnu",
                "description_motif": "Identifiant de nœud amont/aval non résolu dans le référentiel",
                "detail": f"Nœud amont/aval non résolu (ID_AMONT={e['id_amont']!r}, ID_AVAL={e['id_aval']!r})",
                "attributs": {
                    "id_amont": e["id_amont"],
                    "id_aval": e["id_aval"],
                    "u_node": e["u_node"],
                    "d_node": e["d_node"],
                },
            }
            for e in exclusions_conduits
        ]
        meta["reconciliation"] = generer_bilan_reconciliation(
            gpkg_counts=gpkg_counts or {},
            inp_counts=inp_counts,
            exclusions=exclusions_audit,
            sections_inp_presents=sections_presents,
            hypotheses=[
                {"domaine": "pompes", "detail": "Une pompe par tête de chaîne de refoulement ; courbe Type 3 (débit/hauteur) estimée à partir du diamètre nominal ; marche/arrêt par calage 0.30/0.10 m (attributs de commande absents du SIG)"},
                {"domaine": "rugosite", "detail": "Formulation Manning différenciée selon la colonne MATERIAU"},
                {"domaine": "sections", "detail": f"{len(sections_rectangulaires)} sections rectangulaires prises en compte (FORMESECT, HAUTEUR, GDEBASE)"},
                {"domaine": "deversoirs", "detail": f"{sum(1 for d in deversoirs_traites if d.get('h_seuil_defaut'))} DVO avec seuil par défaut 0.50 m (H_de_Seuil/loSeuil absents du SIG)"},
                {"domaine": "raccordements_spatiaux", "detail": f"{len(raccordements_spatiaux)} tronçons raccordés par tolérance spatiale <= 0.50m"},
            ]
        )
    except Exception as e_rec:
        logger.warning(f"Bilan de réconciliation non calculé: {e_rec}")


def _lignes_entete_inp(ctx):
    """Étape extraite verbatim de generer_lignes_sections_inp."""
    altimetrie_meta = ctx["altimetrie_meta"]
    duree_sim = ctx["duree_sim"]
    end_time_str = ctx["end_time_str"]
    pas_routage_sec = ctx["pas_routage_sec"]
    routing_step_str = ctx["routing_step_str"]
    scen = ctx["scen"]

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
    return lines



def _appliquer_intensite_max(ctx):
    """Étape extraite verbatim de generer_lignes_sections_inp."""
    intensite_max_mmh = ctx["intensite_max_mmh"]
    is_bms = ctx["is_bms"]
    max_base = ctx["max_base"]
    scen = ctx["scen"]
    ts_base = ctx["ts_base"]

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
    return effective_timeseries, active_i_max



def _calculer_pas_raingage(ctx):
    """Étape extraite verbatim de generer_lignes_sections_inp."""
    effective_timeseries = ctx["effective_timeseries"]
    lines = ctx["lines"]
    try:
        def _parse_t_min(t_str: str) -> float:
            parts = t_str.split(":")
            minutes = float(parts[0]) * 60.0 + float(parts[1])
            if len(parts) > 2:
                minutes += float(parts[2]) / 60.0
            return minutes

        ts_triee = sorted(
            effective_timeseries, key=lambda tv: _parse_t_min(tv[0])
        )
        deltas = [
            _parse_t_min(ts_triee[i][0]) - _parse_t_min(ts_triee[i - 1][0])
            for i in range(1, len(ts_triee))
        ]
        deltas_pos = [d for d in deltas if d > 0]
        if deltas_pos:
            # Pas modal : le pas de sondage dominant de la série. Plus robuste
            # qu'un min() aux séries irrégulières (ex. queue à 60 min).
            pas_min = Counter(deltas_pos).most_common(1)[0][0]
            h_i, m_i = divmod(int(round(pas_min)), 60)
            interval_raingage = f"{h_i}:{m_i:02d}"
    except Exception:
        pass
    return interval_raingage
