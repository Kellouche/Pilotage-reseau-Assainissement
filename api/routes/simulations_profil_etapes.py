# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Étapes du profil en long hydraulique (extrait verbatim de
         api/routes/simulations_profil.py)
================================================================================
"""

import logging
import math
from typing import Any, Dict, Optional

import geopandas as gpd
import networkx as nx
import pandas as pd

from src.domain.moteur_swmm.constants import _clean_node_id

logger = logging.getLogger("swmm_platform.routes.simulations_profil")


def _etape_coords_noeuds(ctx):
    """Étape extraite verbatim de get_profil_en_long."""
    _topo = ctx["_topo"]
    base = ctx["base"]
    node_hydraulics = ctx["node_hydraulics"]
    node_index = ctx["node_index"]
    path_nodes = ctx["path_nodes"]
    sim_data = ctx["sim_data"]
    sim_valide = ctx["sim_valide"]

    hgl_source = ("swmm_out_max_head" if (sim_valide and node_hydraulics and base == "max")
                  else "swmm_out_instant" if (sim_valide and node_hydraulics and base == "instant")
                  else "indisponible")

    # P0 — cotes de sommet de regard telles que définies par le modèle
    # SWMM ([JUNCTIONS] : Name Elevation MaxDepth InitDepth SurDepth
    # Aponded). Le sommet = radier + MaxDepth : ce n'est PAS le terrain
    # naturel, c'est le plan de rupture du modèle.
    inp_noeuds: Dict[str, Dict[str, float]] = {}
    inp_content = sim_data.get("inp_content") if sim_valide else None
    if inp_content:
        _sec = None
        for _line in str(inp_content).splitlines():
            _s = _line.strip()
            if _s.startswith("[") and _s.endswith("]"):
                _sec = _s.strip("[]").lower()
                continue
            if _sec in ("junctions", "outfalls", "storage") and _s and not _s.startswith(";"):
                _p = _s.split()
                if len(_p) >= 3:
                    try:
                        inp_noeuds[_p[0]] = {
                            "elevation": float(_p[1]),
                            "maxdepth": float(_p[2]),
                        }
                    except (TypeError, ValueError):
                        pass

    # Construire les séries du profil
    segments = []
    distance_cumulee = 0.0

    # Coordonnées WGS84 des nœuds du chemin (pour la couche d'anomalies
    # sur la carte) — même conversion que /recherche-element, limitée
    # aux nœuds du profil (pas les ~10k du réseau).
    _noeud_wgs = {}
    _crs_topo = _topo.get("crs")
    _tf_wgs = None
    if _crs_topo and "4326" not in str(_crs_topo):
        try:
            from pyproj import Transformer
            _tf_wgs = Transformer.from_crs(str(_crs_topo), "EPSG:4326", always_xy=True)
        except Exception:
            _tf_wgs = None
    for _nid in path_nodes:
        _info = node_index.get(_nid) or {}
        _x, _y = _info.get("x"), _info.get("y")
        if _x is None or _y is None:
            continue
        if _tf_wgs is not None:
            try:
                _x, _y = _tf_wgs.transform(float(_x), float(_y))
            except Exception:
                continue
        _noeud_wgs[_nid] = (_x, _y)
    return (segments, distance_cumulee, hgl_source, inp_noeuds, _noeud_wgs)



def _etape_segments_profil(ctx):
    """Étape extraite verbatim de get_profil_en_long."""
    distance_cumulee = ctx["distance_cumulee"]
    G = ctx["G"]
    _clean_node_id = ctx["_clean_node_id"]
    _flood_reel = ctx["_flood_reel"]
    _head_reel = ctx["_head_reel"]
    _hydrau_noeud = ctx["_hydrau_noeud"]
    _noeud_wgs = ctx["_noeud_wgs"]
    base = ctx["base"]
    inp_noeuds = ctx["inp_noeuds"]
    node_elevs = ctx["node_elevs"]
    node_index = ctx["node_index"]
    path_nodes = ctx["path_nodes"]
    segments = ctx["segments"]
    sim_data = ctx["sim_data"]
    sim_node_results = ctx["sim_node_results"]
    terrain_par_code = ctx["terrain_par_code"]
    validations_map = ctx["validations_map"]

    for i, nid in enumerate(path_nodes):
        info = node_index.get(nid, {})
        profondeur = info.get("profondeur")
        cotrad = info.get("cotrad")
        cotetn = info.get("cotetn")  # cote terrain vérifiée (ou None)

        # Détermination de z_radier — sources réelles uniquement :
        # COTRAD (GPKG) → terrain vérifié − profondeur GPKG réelle →
        # radier .out SWMM (node_elevs). AUCUNE valeur heuristique.
        if cotrad is not None:
            z_rad = cotrad
        elif cotetn is not None and profondeur is not None:
            z_rad = cotetn - profondeur
        elif nid in node_elevs:
            z_rad = float(node_elevs[nid])
        else:
            nc = _clean_node_id(nid)
            z_rad = float(node_elevs.get(nc)) if nc in node_elevs else None
        if z_rad is not None and not math.isfinite(z_rad):
            z_rad = None

        # z_terrain : uniquement une cote altimétrique vérifiée.
        # Absente → None : aucune courbe « MNT » ne sera dessinée.
        z_terrain = cotetn
        terrain_reel = info.get("terrain_reel", False)
        terrain_source = info.get("terrain_source", "absent")

        # P3 — terrain interpolé satellite (affichage seul)
        z_terrain_interp = None
        terrain_confiance = None
        if terrain_par_code:
            _rk = (terrain_par_code.get(nid)
                   or terrain_par_code.get(_clean_node_id(nid) or "")
                   or terrain_par_code.get(str(nid)))
            if _rk and _rk.get("z_terrain_m") is not None:
                z_terrain_interp = float(_rk["z_terrain_m"])
                terrain_confiance = _rk.get("confiance")

        # Sommet de regard SWMM = radier + MaxDepth (.inp) — plan de
        # rupture du modèle, distinct du terrain naturel.
        # Règle Human-in-the-Loop : si l'hydraulicien a validé une profondeur certifiée,
        # celle-ci prévaut sur la valeur brute erronée.
        val_entry = (validations_map.get(str(nid), {}).get("profondeur") or
                     validations_map.get(_clean_node_id(nid), {}).get("profondeur"))
        prof_effectif = profondeur
        cote_est_validee = False
        if val_entry and val_entry.get("statut") == "valide" and val_entry.get("valeur_validee") is not None:
            prof_effectif = float(val_entry["valeur_validee"])
            cote_est_validee = True

        z_sommet = None
        inp_n = inp_noeuds.get(nid) or inp_noeuds.get(_clean_node_id(nid) or "")
        if prof_effectif is not None and z_rad is not None:
            z_sommet = z_rad + prof_effectif
        elif inp_n and inp_n.get("maxdepth") is not None:
            rad_src = z_rad if z_rad is not None else inp_n.get("elevation")
            if rad_src is not None:
                z_sommet = rad_src + inp_n["maxdepth"]

        # Déterminer le diamètre de conduite local pour la génératrice supérieure
        diam_m = 0.6
        if i < len(path_nodes) - 1:
            next_n = path_nodes[i + 1]
            e = G.get_edge_data(nid, next_n) or G.get_edge_data(next_n, nid) or {}
            if e:
                try:
                    _dm_f = float(e.get("diam_mm") or e.get("diametre_mm") or 600.0)
                except (TypeError, ValueError):
                    _dm_f = 600.0
                if not math.isfinite(_dm_f):
                    _dm_f = 600.0
                diam_m = _dm_f / 1000.0
        elif i > 0:
            prev_n = path_nodes[i - 1]
            e = G.get_edge_data(prev_n, nid) or G.get_edge_data(nid, prev_n) or {}
            if e:
                try:
                    _dm_f = float(e.get("diam_mm") or e.get("diametre_mm") or 600.0)
                except (TypeError, ValueError):
                    _dm_f = 600.0
                if not math.isfinite(_dm_f):
                    _dm_f = 600.0
                diam_m = _dm_f / 1000.0

        z_gen_sup = (z_rad + diam_m) if z_rad is not None else None

        # LOT P0 — HGL : maximum .rpt (base=max) ou valeur .out à
        # l'instant demandé. Provenance conservée par nœud.
        hgl, hgl_src = _head_reel(nid)
        if hgl is not None and not math.isfinite(hgl):
            hgl, hgl_src = None, "indisponible"
        hgl_reel = hgl is not None
        nh_entry = _hydrau_noeud(nid) or {}
        simule = bool(nh_entry)
        flooding_max, flood_src = _flood_reel(nid)
        flooding_global_max = float(nh_entry.get("flooding_max_m3s") or 0.0)
        rpt_flood_vol = nh_entry.get("rpt_flood_volume_m3")
        rpt_flood_min = nh_entry.get("rpt_flood_minute")

        node_sim = sim_node_results.get(nid, {})
        status_n = node_sim.get("status", "normal")
        if hgl is not None:
            # CONTRÔLE P0 — distinction stricte :
            #   debordement = flooding RÉEL confirmé par SWMM
            #     (FLOODING_LOSSES > 0, .rpt prioritaire sur .out) ;
            #   inondation = cote ≥ terrain naturel VÉRIFIÉ sans débordement ;
            #   surcharge = mise en charge (cote > génératrice supérieure) ;
            #   libre = écoulement non mis en charge.
            # Sans terrain vérifié, aucune « inondation » ne peut être
            # affirmée : la comparaison se fait sur la génératrice.
            if flooding_max > 0.0:
                hgl_regime = "debordement"
            elif z_terrain is not None and hgl >= z_terrain:
                hgl_regime = "inondation"
            elif z_gen_sup is not None and hgl > z_gen_sup:
                hgl_regime = "surcharge"
            else:
                hgl_regime = "libre"
        else:
            # Donnée hydraulique absente : le statut RPT (donnée SWMM
            # réelle) qualifie le régime, mais aucune cote n'est inventée.
            if status_n == "flooded" and base == "max":
                hgl_regime = "debordement"
            elif status_n == "surcharged":
                hgl_regime = "surcharge"
            else:
                hgl_regime = "inconnu"

        # Trouver la conduite qui sort de ce nœud vers le suivant
        conduit = None
        if i < len(path_nodes) - 1:
            next_nid = path_nodes[i + 1]
            edge_data = G.get_edge_data(nid, next_nid) or G.get_edge_data(next_nid, nid) or {}
            if edge_data:
                geom = edge_data.get("geometry")
                try:
                    length = float(edge_data.get("length") or (geom.length if geom else 15.0))
                except (TypeError, ValueError):
                    length = 15.0
                if not math.isfinite(length):
                    length = float(geom.length) if (geom is not None and math.isfinite(geom.length)) else 15.0
                try:
                    diam_mm = float(edge_data.get("diam_mm") or edge_data.get("diametre_mm") or 600.0)
                except (TypeError, ValueError):
                    diam_mm = 600.0
                if not math.isfinite(diam_mm):
                    diam_mm = 600.0
                conduit = {
                    "cid": edge_data.get("cid") or edge_data.get("id") or f"C_{i+1}",
                    "length": round(length, 2),
                    "diam_mm": diam_mm,
                    "materiau": edge_data.get("materiau", "Béton"),
                    "nom_voie": edge_data.get("nom_voie", ""),
                }
                # Résultats simulation sur cette conduite
                cond_sim = {}
                if sim_data:
                    all_cond = sim_data.get("conduit_results", {})
                    # Trouver la conduite par u_node/d_node
                    for ck, cv in all_cond.items():
                        if cv.get("u_node") == nid and cv.get("d_node") == next_nid:
                            cond_sim = cv
                            break
                if cond_sim:
                    conduit["flow_ratio"] = cond_sim.get("flow_ratio", 0.0)
                    conduit["depth_ratio"] = cond_sim.get("depth_ratio", 0.0)
                    conduit["max_flow_cms"] = cond_sim.get("max_flow_cms", 0.0)
                    conduit["max_velocity_ms"] = cond_sim.get("max_velocity_ms")
                    conduit["status"] = cond_sim.get("status", "normal")
                    conduit["color"] = cond_sim.get("color", "#10b981")
                else:
                    conduit["flow_ratio"] = 0.0
                    conduit["depth_ratio"] = 0.0
                    conduit["max_flow_cms"] = 0.0
                    conduit["max_velocity_ms"] = None
                    conduit["status"] = "inconnu"
                    conduit["color"] = "#64748b"

        # LOT P0.2 — plus de rehaussement heuristique de la HGL depuis le
        # statut de la conduite : la cote .out fait foi. Le statut réel
        # de la conduite reste reporté dans conduit_sortant.

        z_gs = (z_rad + (conduit["diam_mm"] / 1000.0 if conduit else diam_m)) if z_rad is not None else None
        pression_m = (round(max(0.0, hgl - z_gs), 2)
                      if (hgl is not None and z_gs is not None and hgl > z_gs) else 0.0)
        revanche_m = (round(max(0.0, z_terrain - hgl), 2)
                      if (z_terrain is not None and hgl is not None and hgl < z_terrain)
                      else (0.0 if (z_terrain is not None and hgl is not None) else None))

        # Cote du plan d'eau réel dans la conduite (Water Surface Profile - WSP)
        # Si en charge : la conduite est 100% pleine d'eau (z_eau = z_gs)
        # Si écoulement libre : z_eau = min(z_gs, max(z_rad, hgl))
        if hgl is not None and z_gs is not None and z_rad is not None:
            z_eau_conduite = z_gs if hgl >= z_gs else max(z_rad, hgl)
        elif z_rad is not None:
            z_eau_conduite = z_rad
        else:
            z_eau_conduite = None

        _ll_wgs = _noeud_wgs.get(nid)
        segments.append({
            "node_id": nid,
            "lng": _ll_wgs[0] if _ll_wgs else None,
            "lat": _ll_wgs[1] if _ll_wgs else None,
            "distance_m": round(distance_cumulee, 2),
            "z_radier": round(z_rad, 3) if z_rad is not None else None,
            "z_terrain": round(z_terrain, 3) if z_terrain is not None else None,
            "z_terrain_interp": round(z_terrain_interp, 3) if z_terrain_interp is not None else None,
            "terrain_confiance": terrain_confiance,
            "z_sommet_regard": round(z_sommet, 3) if z_sommet is not None else None,
            "terrain_reel": bool(terrain_reel),
            "terrain_source": terrain_source,
            "z_gen_superieure": round(z_gs, 3) if z_gs is not None else None,
            "z_eau_conduite": round(z_eau_conduite, 3) if z_eau_conduite is not None else None,
            "z_hgl": round(hgl, 3) if hgl is not None else None,
            "hgl_reel": hgl_reel,
            "hgl_source": hgl_src,
            "hgl_regime": hgl_regime,
            "simule": simule,
            "atteint_terrain": bool(z_terrain is not None and hgl is not None and hgl >= z_terrain),
            "atteint_sommet": bool(z_sommet is not None and hgl is not None and hgl >= z_sommet - 1e-6),
            "flooding_m3s": round(flooding_max, 6) if hgl_reel else None,
            "flood_source": flood_src,
            "flooding_max_m3s": round(flooding_global_max, 6) if hgl_reel else None,
            "rpt_flood_volume_m3": rpt_flood_vol,
            "flood_volume_estime": bool(nh_entry.get("flood_volume_estime", True)),
            "flood_time_minute": rpt_flood_min,
            "pression_m": pression_m,
            "revanche_m": revanche_m,
            "profondeur_m": round(prof_effectif, 2) if prof_effectif is not None else None,
            "cote_validee": cote_est_validee,
            "node_status": node_sim.get("status", "normal") if node_sim else "normal",
            "node_color": node_sim.get("color", "#10b981") if node_sim else "#10b981",
            "conduit_sortant": conduit,
        })

        if conduit:
            distance_cumulee += conduit.get("length", 0.0)
    return distance_cumulee
