# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Étapes de génération des sections .INP (extrait verbatim de
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


def _resoudre_conduits_topologiques(ctx):
    """Étape extraite verbatim de generer_lignes_sections_inp."""
    from src.domain.topologie import PROV_ALIAS, PROV_ALIAS_AUTO, PROV_SNAP  # noqa: E402 (anti-cycle)
    canalisations = ctx["canalisations"]
    conduit_nodes = ctx["conduit_nodes"]
    conduits_resolus = ctx["conduits_resolus"]
    coord_noeuds = ctx["coord_noeuds"]
    downstream_nodes = ctx["downstream_nodes"]
    noeuds_spatiaux_crees = ctx["noeuds_spatiaux_crees"]
    raccordements_spatiaux = ctx["raccordements_spatiaux"]
    resolveur = ctx["resolveur"]
    upstream_nodes = ctx["upstream_nodes"]

    for idx, c in canalisations.iterrows():
        cid = f"C_{idx+1}"

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

        # Résolution canonique : ID -> alias (RJ<n>) -> snap <= 0.50 m.
        # Le snap n'est jamais tenté quand l'ID est présent et valide.
        res_u = resolveur.resoudre(c.get("ID_AMONT"), pt_start)
        res_d = resolveur.resoudre(c.get("ID_AVAL"), pt_end)

        for ext, res in (("amont", res_u), ("aval", res_d)):
            if res.provenance == PROV_SNAP and res.noeud:
                raccordements_spatiaux.append({
                    "cid": cid, "extremite": ext, "noeud": res.noeud,
                    "distance_m": round(res.distance_m, 3), "provenance": "snap"})
            elif res.provenance == PROV_ALIAS and res.noeud:
                raccordements_spatiaux.append({
                    "cid": cid, "extremite": ext, "noeud": res.noeud,
                    "distance_m": 0.0, "provenance": "alias"})
            elif res.provenance == PROV_ALIAS_AUTO and res.noeud:
                raccordements_spatiaux.append({
                    "cid": cid, "extremite": ext, "noeud": res.noeud,
                    "distance_m": round(res.distance_m, 3),
                    "provenance": "alias_auto"})

        # Filet de sécurité : nœud spatial à la coordonnée réelle
        # (uniquement si ni ID/alias ni snap n'ont résolu l'extrémité).
        u_node = res_u.noeud
        if not u_node and pt_start:
            u_node = f"N_{cid}_U"
            coord_noeuds[u_node] = pt_start
            noeuds_spatiaux_crees[u_node] = pt_start

        d_node = res_d.noeud
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



def _ecrire_raccordements_orphelins(ctx):
    """Étape extraite verbatim de generer_lignes_sections_inp."""
    canalisations = ctx["canalisations"]
    clean_target_nodes = ctx["clean_target_nodes"]
    lines = ctx["lines"]
    node_elevs = ctx["node_elevs"]
    racc_orph_valides = ctx["racc_orph_valides"]
    raccordements_orphelins = ctx["raccordements_orphelins"]
    regards = ctx["regards"]
    seen_outfall_names = ctx["seen_outfall_names"]
    sinks_frontiere = ctx["sinks_frontiere"]

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
    return exutoires_frontiere_info


def _ecrire_ouvrages_speciaux(ctx):
    """Étape extraite verbatim de generer_lignes_sections_inp."""
    conduit_nodes = ctx["conduit_nodes"]
    coord_noeuds = ctx["coord_noeuds"]
    deversoirs_traites = ctx["deversoirs_traites"]
    lines = ctx["lines"]
    node_elevs = ctx["node_elevs"]
    noeuds_connus_ids = ctx["noeuds_connus_ids"]
    ouvrages_speciaux = ctx["ouvrages_speciaux"]
    seen_outfall_names = ctx["seen_outfall_names"]
    tree_noeuds = ctx["tree_noeuds"]
    weir_lines = ctx["weir_lines"]
    weir_xsec_lines = ctx["weir_xsec_lines"]

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
                    h_seuil_defaut = True
                    try:
                        h_seuil = float(h_seuil_raw) if pd.notna(h_seuil_raw) and float(h_seuil_raw) > 0 else 0.50
                        h_seuil_defaut = not (pd.notna(h_seuil_raw) and float(h_seuil_raw) > 0)
                    except Exception:
                        h_seuil = 0.50
                    # Largeur de seuil : LaSeuil/loSeuil si renseigné, sinon 1.00 m (hypothèse)
                    la_seuil_raw = ouv.get("LaSeuil") or ouv.get("loSeuil")
                    largeur_defaut = True
                    try:
                        largeur_seuil = float(la_seuil_raw) if pd.notna(la_seuil_raw) and float(la_seuil_raw) > 0 else 1.00
                        largeur_defaut = not (pd.notna(la_seuil_raw) and float(la_seuil_raw) > 0)
                    except Exception:
                        largeur_seuil = 1.00
                    weir_lines.append(f"{wid:<16} {u_weir:<16} {w_out:<16} TRANSVERSE   {h_seuil:<10.3f} 1.800      NO       0        0.000    NO")
                    # Section [XSECTIONS] obligatoire pour tout lien [WEIRS] :
                    # Geom1 = hauteur de l'ouverture (2.00 m, hypothèse), Geom2 = largeur du seuil.
                    weir_xsec_lines.append(f"{wid:<16} RECT_OPEN     {2.0:<16.3f} {largeur_seuil:<10.3f} 0.000      0.000      1")
                    coord_noeuds[w_out] = (o_pt[0] + 5.0, o_pt[1] + 5.0) if o_pt else (100.0, 100.0)
                    deversoirs_traites.append({"wid": wid, "u_node": u_weir, "outfall": w_out, "h_seuil": h_seuil, "h_seuil_defaut": h_seuil_defaut, "largeur_seuil_m": largeur_seuil, "largeur_defaut": largeur_defaut})



def _generer_lignes_conduits(ctx):
    """Étape extraite verbatim de generer_lignes_sections_inp."""
    from src.domain.moteur_swmm.sections_inp import _determiner_forme_section, _determiner_rugosite  # noqa: E402 (anti-cycle)
    _etat_nominal = ctx["_etat_nominal"]
    _etat_norm = ctx["_etat_norm"]
    conduit_endpoints = ctx["conduit_endpoints"]
    conduit_lines = ctx["conduit_lines"]
    conduit_nodes = ctx["conduit_nodes"]
    conduits_resolus = ctx["conduits_resolus"]
    coord_noeuds = ctx["coord_noeuds"]
    curve_lines = ctx["curve_lines"]
    exclusions_conduits = ctx["exclusions_conduits"]
    node_elevs = ctx["node_elevs"]
    noeuds_spatiaux_crees = ctx["noeuds_spatiaux_crees"]
    nref_junction_lines = ctx["nref_junction_lines"]
    pente_moyenne_pct = ctx["pente_moyenne_pct"]
    pump_lines = ctx["pump_lines"]
    refoulement_aval = ctx["refoulement_aval"]
    refoulements_traites = ctx["refoulements_traites"]
    sections_rectangulaires = ctx["sections_rectangulaires"]
    xsec_lines = ctx["xsec_lines"]

    for cr in conduits_resolus:
        cid = cr["cid"]
        u_node = cr["u_node"]
        d_node = cr["d_node"]
        c = cr["row"]
        if not u_node or not d_node or u_node == d_node:
            exclusions_conduits.append({
                "cid": cid,
                "id_amont": str(c.get("ID_AMONT", "")),
                "id_aval": str(c.get("ID_AVAL", "")),
                "u_node": u_node,
                "d_node": d_node,
            })
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

        # État physique du réseau (Colmatage & Vieillissement)
        rough_eff = rough
        xsec_shape_eff = "RECT_CLOSED" if shape == "RECTANGULAR" else "CIRCULAR"
        geom1_eff, geom2_eff = geom1, geom2
        if not _etat_nominal:
            _zu = node_elevs.get(u_node)
            _zd = node_elevs.get(d_node)
            if _zu is not None and _zd is not None and length > 0:
                _pente_c = ((_zu - _zd) / length) * 100.0
            else:
                _p_attr = c.get("PENTE")
                _pente_c = float(_p_attr) if (_p_attr is not None and pd.notna(_p_attr)) else pente_moyenne_pct
            xsec_shape_eff, geom1_eff, geom2_eff, _sed_m, rough_eff, _info_etat = appliquer_etat_conduite(
                row=c,
                diam_m=diam_m,
                shape=shape,
                geom1=geom1,
                geom2=geom2,
                rough_base=rough,
                pente_conduite_pct=_pente_c,
                etat_norm=_etat_norm,
            )
            if _info_etat.get("colmate"):
                _nb_conduits_colmates += 1
                if _info_etat.get("source_depot") == "sig_niv_depot":
                    _nb_depots_sig += 1

        # Détection de refoulement (Chantier 1.1)
        fct = str(c.get("FONCTIONMT") or c.get("fonctionmt") or "").strip().lower()
        is_refoulement = ("refoul" in fct or "pompage" in fct)

        nom_v = str(c.get("NOM-VOIE") or c.get("NOMVOIE") or c.get("nom_voie") or "").strip()
        if nom_v.lower() in ("nan", "none", "null", ""):
            nom_v = ""

        is_tete_refoulement = is_refoulement and u_node not in refoulement_aval
        if is_tete_refoulement:
            # Modélisation physique SWMM 5.2 : [PUMPS] alimentée par courbe [CURVES] Type 3 + conduite en charge aval
            n_ref_node = f"N_REF_{cid}"
            coord_u = coord_noeuds.get(u_node, (100.0, 100.0))
            coord_noeuds[n_ref_node] = (coord_u[0] + 1.0, coord_u[1] + 1.0)
            noeuds_spatiaux_crees[n_ref_node] = coord_noeuds[n_ref_node]
            conduit_nodes.add(n_ref_node)
            z_nref = node_elevs.get(d_node, node_elevs.get(u_node, 100.0))
            nref_junction_lines.append(f"{n_ref_node:<16} {z_nref:<10.3f} 2.000      0.000      0.000      0.000")

            pump_id = f"PMP_{cid}"
            curve_id = f"CURV_PMP_{cid}"
            # Contrôle intrinsèque SWMM : démarrage à 0.30 m de calage au nœud
            # d'aspiration, arrêt à 0.10 m (hypothèse documentée — les attributs
            # de commande réels des stations ne sont pas renseignés dans le SIG).
            pump_lines.append(f"{pump_id:<16} {u_node:<16} {n_ref_node:<16} {curve_id:<16} ON       0.300      0.100")

            # Courbe de pompe caractéristique Type 3 (débit/hauteur) selon diamètre nominal
            q_nom = round(math.pi * (diam_m / 2.0)**2 * 1.5, 4)
            curve_lines.append(f"{curve_id:<16} PUMP3      0.000      35.00")
            curve_lines.append(f"{curve_id:<16}            {q_nom:<10.4f} 25.00")
            curve_lines.append(f"{curve_id:<16}            {round(q_nom * 1.5, 4):<10.4f} 10.00")

            conduit_lines.append(f"{cid:<16} {n_ref_node:<16} {d_node:<16} {length:<10.2f} {rough_eff:<10.4f} 0.000      0.000      0.000      0.000")
            if xsec_shape_eff == "RECT_CLOSED":
                xsec_lines.append(f"{cid:<16} RECT_CLOSED   {geom1_eff:<16.3f} {geom2_eff:<10.3f} 0.000      0.000      {barrels}")
            elif xsec_shape_eff == "FILLED_CIRCULAR":
                xsec_lines.append(f"{cid:<16} FILLED_CIRCULAR {geom1_eff:<16.3f} {geom2_eff:<10.3f} 0.000      0.000      {barrels}")
            else:
                xsec_lines.append(f"{cid:<16} CIRCULAR     {geom1_eff:<16.3f} 0.000      0.000      0.000      {barrels}")

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
                "debit_nominal_m3s": q_nom,
                "tete_refoulement": True
            })
        else:
            # Segment aval d'une chaîne de refoulement : conduite sous pression
            # alimentée par la pompe de tête (pas de pompe supplémentaire).
            conduit_lines.append(f"{cid:<16} {u_node:<16} {d_node:<16} {length:<10.2f} {rough_eff:<10.4f} 0.000      0.000      0.000      0.000")
            if xsec_shape_eff == "RECT_CLOSED":
                xsec_lines.append(f"{cid:<16} RECT_CLOSED   {geom1_eff:<16.3f} {geom2_eff:<10.3f} 0.000      0.000      {barrels}")
            elif xsec_shape_eff == "FILLED_CIRCULAR":
                xsec_lines.append(f"{cid:<16} FILLED_CIRCULAR {geom1_eff:<16.3f} {geom2_eff:<10.3f} 0.000      0.000      {barrels}")
            else:
                xsec_lines.append(f"{cid:<16} CIRCULAR     {geom1_eff:<16.3f} 0.000      0.000      0.000      {barrels}")

            conduit_endpoints[cid] = {
                "u": u_node,
                "d": d_node,
                "length": length,
                "diam_mm": diam_mm,
                "material": str(c.get("MATERIAU", "Béton")),
                "nom_voie": nom_v,
                "fonction": "refoulement" if is_refoulement else "gravitaire"
            }
            if is_refoulement:
                refoulements_traites.append({
                    "cid": cid,
                    "pompe": None,
                    "station_amont": u_node,
                    "exutoire_aval": d_node,
                    "diametre_mm": diam_mm,
                    "longueur_m": length,
                    "debit_nominal_m3s": None,
                    "tete_refoulement": False
                })
