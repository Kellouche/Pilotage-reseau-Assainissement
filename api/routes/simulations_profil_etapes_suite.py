# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Étapes anomalies/alertes/HGL du profil en long (extrait verbatim de
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


def _etape_anomalies_resume(ctx):
    """Étape extraite verbatim de get_profil_en_long."""
    _n_liens_radier = ctx["_n_liens_radier"]
    _n_contre_pentes = ctx["_n_contre_pentes"]
    _jalon = ctx["_jalon"]
    anomalies_liste = ctx["anomalies_liste"]
    distance_cumulee = ctx["distance_cumulee"]
    segments = ctx["segments"]

    for _i, _s in enumerate(segments):
        _cond = _s.get("conduit_sortant")
        # --- anomalies sur la conduite sortante (nœud i → i+1) ---
        if _cond and _i + 1 < len(segments):
            _long = _cond.get("length") or 0.0
            _sn = segments[_i + 1]
            _zr_a = _s.get("z_radier")
            _zr_b = _sn.get("z_radier")
            if _zr_a is not None and _zr_b is not None and _long > 0:
                _n_liens_radier += 1
                _dz = _zr_b - _zr_a
                _pente_pct = round(-100.0 * _dz / _long, 2)
                _cond["slope_pct"] = _pente_pct
                _cond["dz_radier_m"] = round(_dz, 3)
                if _dz > 0.02:
                    _n_contre_pentes += 1
                    _sev = "fort" if _dz > 0.30 else "moyen"
                    _jalon(
                        _sn, "contre_pente", _sev,
                        f"Contre-pente radier : +{_dz:.2f} m sur {_long:.0f} m "
                        f"(pente {_pente_pct:.1f} %) — l'eau doit remonter, "
                        f"vérifier le sens ou la cote aval",
                        valeur_m=_dz, unite="m",
                    )
                elif _pente_pct > 8.0:
                    _jalon(
                        _sn, "pente_forte", "moyen",
                        f"Pente radier forte : {_pente_pct:.1f} % "
                        f"({_zr_a:.2f} → {_zr_b:.2f} m sur {_long:.0f} m) — "
                        f"risque d'érosion / vitesse excessive",
                        valeur_pct=_pente_pct, unite="%",
                    )
                # vitesse d'autocurage (SWMM réel, jamais estimée)
                _v = _cond.get("max_velocity_ms")
                _q = _cond.get("max_flow_cms") or 0.0
                if _v is not None:
                    if _v >= 4.0:
                        _jalon(
                            _sn, "vitesse_autocurage", "fort",
                            f"Vitesse max {_v:.2f} m/s ≥ 4 m/s — risque "
                            f"d'érosion et de mise en charge brutal",
                            valeur_ms=_v, unite="m/s",
                        )
                    elif _v >= 3.0:
                        _jalon(
                            _sn, "vitesse_autocurage", "moyen",
                            f"Vitesse max {_v:.2f} m/s ≥ 3 m/s — vérifier "
                            f"l'absence d'érosion et la tenue du radier",
                            valeur_ms=_v, unite="m/s",
                        )
                    elif _v < 0.6 and _q > 0.005:
                        _jalon(
                            _sn, "autocurage_insuffisant", "faible",
                            f"Vitesse max {_v:.2f} m/s < 0,6 m/s avec "
                            f"écoulement ({_q:.3f} m³/s) — risque de dépôt",
                            valeur_ms=_v, unite="m/s",
                        )
            # terrain interpolé qui remonte (info — bruit IDW possible)
            _zt_a = _s.get("z_terrain_interp")
            _zt_b = _sn.get("z_terrain_interp")
            if (_zt_a is not None and _zt_b is not None
                    and (_zt_b - _zt_a) > 0.5):
                _jalon(
                    _sn, "terrain_remonte", "info",
                    f"Terrain interpolé remonte de {_zt_b - _zt_a:.2f} m "
                    f"— probable bruit IDW, pas une anomalie hydraulique",
                    valeur_m=round(_zt_b - _zt_a, 2), unite="m",
                )
        # --- anomalies au nœud lui-même (hydraulique) ---
        _statut = _s.get("node_status") or ""
        _regime = _s.get("hgl_regime") or ""
        if _statut == "flooded" or _regime in ("inondation", "debordement"):
            _jalon(
                _s, "hydraulique", "fort",
                "Nœud inondé / débordement confirmé par SWMM — "
                "intervention hydraulique requise",
                flooding_m3s=_s.get("flooding_max_m3s"), unite="m³/s",
            )
        elif _statut == "surcharged" or _regime == "surcharge":
            _jalon(
                _s, "hydraulique", "moyen",
                "Conduite ou nœud en surcharge — HGL au-dessus de la "
                "génératrice supérieure",
                pression_m=_s.get("pression_m"), unite="m",
            )
        elif _s.get("atteint_sommet"):
            _jalon(
                _s, "hydraulique", "faible",
                "Plan d'eau atteint le sommet du regard — marge "
                "quasi nulle",
            )

    _par_sev = {}
    _par_type = {}
    for _a in anomalies_liste:
        _par_sev[_a["severite"]] = _par_sev.get(_a["severite"], 0) + 1
        _par_type[_a["type"]] = _par_type.get(_a["type"], 0) + 1
    resume_anomalies = {
        "total": len(anomalies_liste),
        "par_severite": _par_sev,
        "par_type": _par_type,
        "orientation_suspecte": bool(
            _n_liens_radier >= 3
            and _n_contre_pentes > 0.5 * _n_liens_radier
        ),
        "liens_avec_radier": _n_liens_radier,
        "contre_pentes": _n_contre_pentes,
    }

    # Statistiques du profil — uniquement sur les cotes réellement
    # disponibles (aucune valeur nulle n'est comptée comme une altitude).
    _z_rad_vals = [s["z_radier"] for s in segments if s.get("z_radier") is not None]
    _z_ref_vals = ([s["z_terrain"] for s in segments if s.get("z_terrain") is not None]
                   + [s["z_sommet_regard"] for s in segments if s.get("z_sommet_regard") is not None])
    z_min = min(_z_rad_vals) if _z_rad_vals else 0.0
    z_max = max(_z_ref_vals) if _z_ref_vals else (max(_z_rad_vals) if _z_rad_vals else 0.0)
    longueur_totale = distance_cumulee
    conduites_en_charge = sum(
        1 for s in segments
        if s.get("conduit_sortant") and s["conduit_sortant"].get("status") in ("surcharge", "critique")
    )

    # Diagnostic automatique et recommandations expertes
    alerts = []
    return (resume_anomalies, conduites_en_charge, longueur_totale, z_min, z_max, alerts)



def _etape_alertes(ctx):
    """Étape extraite verbatim de get_profil_en_long."""
    alerts = ctx["alerts"]
    base = ctx["base"]
    segments = ctx["segments"]

    for s in segments:
        cond = s.get("conduit_sortant")
        pression = s.get("pression_m") or 0.0
        regime = s.get("hgl_regime", "libre")
        flood_same = s.get("flooding_m3s") or 0.0
        flood_global = s.get("flooding_max_m3s") or 0.0
        z_hgl_s = s.get("z_hgl")
        z_sommet_s = s.get("z_sommet_regard")

        if regime == "debordement" or (base == "max" and s["node_status"] == "flooded"):
            reco = "Rehaussement du tampon, création d'un bassin de rétention amont ou surcalibrage de la conduite aval."
            if cond and cond.get("diam_mm"):
                next_diam = int(cond["diam_mm"] * 1.35 // 100 * 100) or int(cond["diam_mm"] + 200)
                reco = f"Préconisation : recalibrage conduite aval Ø{cond['diam_mm']:.0f} mm → Ø{next_diam} mm ou bassin tampon amont."
            # Observations construites UNIQUEMENT sur des faits SWMM :
            # jamais de « HGL ≥ Terrain » si la cote affichée est sous
            # le terrain (ou si aucun terrain vérifié n'existe).
            obs_parts = []
            if flood_same > 0.0:
                obs_parts.append(f"Débordement SWMM : {flood_same:.3f} m³/s")
                _fv = s.get("rpt_flood_volume_m3")
                if _fv is not None and not s.get("flood_volume_estime", True):
                    if _fv > 0:
                        obs_parts.append(f"volume total débordé rapporté : {_fv:.2f} m³")
                    else:
                        obs_parts.append(
                            "volume total débordé < 0,5 m³ (valeur arrondie par "
                            "SWMM — volume exact non déterminable)")
                else:
                    obs_parts.append(
                        "volume total débordé non déterminable depuis le rapport")
                fm = s.get("flood_time_minute")
                if fm is not None:
                    obs_parts.append(f"max vers {fm // 60:02d}:{fm % 60:02d}")
            elif flood_global > 0.0:
                obs_parts.append(
                    "Débordement confirmé par SWMM — pic non visible dans la "
                    "série temporelle enregistrée (événement plus court que "
                    "le pas de rapport).")
            if z_hgl_s is not None:
                if z_sommet_s is not None:
                    obs_parts.append(f"HGL max {z_hgl_s} m / plan de surverse {z_sommet_s} m")
                    obs_parts.append(f"Écart HGL / plan de surverse : {z_hgl_s - z_sommet_s:+.3f} m")
                else:
                    obs_parts.append(f"HGL max {z_hgl_s} m")
                if s.get("atteint_sommet"):
                    obs_parts.append("la cote a atteint le plan de surverse")
                if s.get("atteint_terrain"):
                    obs_parts.append(f"et dépasse le terrain naturel ({s['z_terrain']} m)")
            if pression:
                _diam_ob = f" (Ø{cond['diam_mm']:.0f} mm)" if (cond and cond.get("diam_mm")) else ""
                obs_parts.append(
                    "charge au-dessus de la génératrice supérieure de la "
                    f"conduite sortante{_diam_ob} : +{pression} m")
            if not obs_parts:
                obs_parts.append("Débordement confirmé par le rapport SWMM.")
            alerts.append({
                "type": "debordement",
                "node": s["node_id"],
                "message": f"🔴 Regard {s['node_id']} : Débordement confirmé par SWMM (eau déversée en surface)",
                "observations": ". ".join(obs_parts) + ".",
                "recommandation": reco
            })
        elif base == "instant" and s["node_status"] == "flooded":
            # base=instant : le statut flooded est un maximum GLOBAL —
            # présenté comme alerte distincte, jamais comme un état
            # observé à l'instant affiché.
            fm = s.get("flood_time_minute")
            when = f" vers {fm // 60:02d}:{fm % 60:02d}" if fm is not None else ""
            alerts.append({
                "type": "info",
                "node": s["node_id"],
                "message": f"ℹ️ Regard {s['node_id']} : pic de débordement ailleurs dans la simulation{when} — non observé à l'instant affiché",
                "observations": f"Maximum global de débordement : {flood_global:.3f} m³/s (agrégé par SWMM, hors pas de rapport).",
                "recommandation": "Consulter le profil en mode enveloppe (maxima) pour la vision complète."
            })
        elif regime == "inondation":
            alerts.append({
                "type": "inondation",
                "node": s["node_id"],
                "message": f"🟠 Regard {s['node_id']} : niveau ≥ terrain naturel (sans débordement mesuré)",
                "observations": f"HGL {z_hgl_s} m ≥ terrain {s['z_terrain']} m — mise en eau de surface ou stockage, à confirmer sur le MNT.",
                "recommandation": "Vérifier la capacité de stockage superficiel et le point bas du secteur."
            })
        elif regime == "surcharge" or s["node_status"] == "surcharged" or (cond and cond.get("flow_ratio", 0) >= 1.0):
            flow_txt = f" (Q/Qmax = {cond['flow_ratio']:.0%})" if cond and cond.get("flow_ratio") else ""
            alerts.append({
                "type": "surcharge",
                "node": s["node_id"],
                "message": f"🟡 Regard {s['node_id']} : Surcharge hydraulique en cheminée{flow_txt}",
                "observations": f"Conduite en charge sous pression (+{pression} m au-dessus de la génératrice sup).",
                "recommandation": f"Vérifier l'effet de remous aval et tester un élargissement de section."
            })
        elif cond and cond.get("flow_ratio", 0) >= 0.8:
            alerts.append({
                "type": "critique",
                "node": s["node_id"],
                "message": f"🟠 Conduite {cond['cid']} proche de la saturation ({cond['flow_ratio']:.0%})",
                "observations": "Capacité résiduelle inférieure à 20%.",
                "recommandation": "Surveiller lors d'épisodes orageux de période de retour supérieure à T10."
            })



def _etape_hgl_altimetrie(ctx):
    """Étape extraite verbatim de get_profil_en_long."""
    alerts = ctx["alerts"]
    base = ctx["base"]
    cotes_suspectes_bloquantes = ctx["cotes_suspectes_bloquantes"]
    forcer_brut = ctx["forcer_brut"]
    hgl_source = ctx["hgl_source"]
    segments = ctx["segments"]
    sim_data = ctx["sim_data"]

    if forcer_brut and cotes_suspectes_bloquantes:
        for cs in cotes_suspectes_bloquantes:
            alerts.append({
                "type": "cote_suspecte_non_validee",
                "node": cs["node_id"],
                "message": f"⚠️ Regard {cs['node_id']} : Tracé avec cote brute non certifiée ({cs['valeur_brute']} m)",
                "observations": "Cette valeur brute déforme l'échelle géométrique du profil.",
                "recommandation": f"Validation recommandée à {cs['valeur_suggeree']} m.",
            })

    _hgl_max_srcs = {s.get("hgl_source") for s in segments if s.get("hgl_source")}
    _a_rpt = "rpt_max_head" in _hgl_max_srcs
    _a_out = "swmm_out_max_head" in _hgl_max_srcs
    hgl_source_global = (
        "swmm_rpt_max_head" if (base == "max" and _a_rpt and not _a_out)
        else "swmm_rpt_max_head_partiel" if (base == "max" and _a_rpt and _a_out)
        else hgl_source
    )

    # Fiabilité du modèle de la simulation sous-jacente (agent
    # garde-fou hydraulicien) : le profil affiche un avertissement
    # quand le modèle est dégradé.
    _gf_prof = ((sim_data.get("agents_expertise") or {}).get("controle_modele_hydraulique") or {}) if sim_data else {}

    # Provenance altimétrique des cotes radier : le profil déclare si le
    # modèle a été résolu sur altimétrie SIG réelle, terrain interpolé
    # (IDW) ou cotes synthétiques — indispensable pour interpréter tout
    # écart radier/terrain (ex. radier ~40 m sous le sol réel).
    _meta_alt = (sim_data.get("meta") or {}) if sim_data else {}
    _prov_alt = ((sim_data.get("provenance") or {}).get("altimetrie") or {}) if sim_data else {}
    _src_alt = str(_meta_alt.get("source_altimetrique") or "")
    _src_low = _src_alt.lower()

    # Écart médian radier ↔ terrain interpolé : quantifie le décalage de
    # datum. Calculé AVANT la détection du mode car il sert de repli pour
    # les anciennes simulations sans provenance enregistrée.
    _ecarts = [
        abs(s["z_radier"] - s["z_terrain_interp"])
        for s in segments
        if s.get("z_radier") is not None and s.get("z_terrain_interp") is not None
    ]
    if _ecarts:
        import statistics as _st
        _ecarts_tri = sorted(_ecarts)
        _ecart_med = round(_st.median(_ecarts_tri), 2)
        _ecart_max = round(_ecarts_tri[-1], 2)
    else:
        _ecart_med = _ecart_max = None

    if _prov_alt.get("mode") == "terrain_idw" or "terrain" in _src_low or "idw" in _src_low:
        _alt_mode, _alt_fiable = "terrain_idw", "estimee"
        _alt_label = "Altimétrie : terrain interpolé (IDW)"
    elif "réelles" in _src_low or "reelles" in _src_low or "sig" in _src_low:
        _alt_mode, _alt_fiable = "sig_reel", "reelle"
        _alt_label = "Altimétrie : SIG réelle"
    elif _src_alt:
        _alt_mode, _alt_fiable = "synthetique", "synthetique"
        _alt_label = "Altimétrie : synthétique"
    elif _ecart_med is not None and _ecart_med > 8.0:
        # Repli (anciennes simulations non estampillées) : un écart médian
        # radier↔terrain > 8 m trahit des cotes synthétiques sur un datum
        # fictif (ex. exutoire 100 m + pente) — jamais un vrai relief.
        _alt_mode, _alt_fiable = "synthetique", "synthetique"
        _alt_label = "Altimétrie : synthétique (inférée)"
    else:
        _alt_mode, _alt_fiable = "indisponible", "inconnue"
        _alt_label = "Altimétrie : source non tracée"

    _altimetrie_info = {
        "mode": _alt_mode,
        "fiable": _alt_fiable,
        "label": _alt_label,
        "source": _src_alt or None,
        "ecart_radier_terrain_med_m": _ecart_med,
        "ecart_radier_terrain_max_m": _ecart_max,
        "avertissement": (
            "Cotes radier synthétiques : exutoire de référence + pente "
            "moyenne, sans lien avec le terrain réel. Les écarts radier/"
            "terrain ne sont pas des anomalies hydrauliques mais un "
            "défaut de données altimétriques."
            if _alt_mode == "synthetique" else
            "Cotes radier dérivées du terrain interpolé (IDW ±1–2 m) : "
            "estimations, pas des mesures de radier."
            if _alt_mode == "terrain_idw" else
            "Cotes radier issues du SIG (relevés altimétriques)."
            if _alt_mode == "sig_reel" else
            "Provenance altimétrique non enregistrée pour cette simulation."
        ),
    }

    # Synthèse des anomalies hydrauliques du profil : indépendante de la
    # fiabilité du modèle (un modèle SAIN peut présenter des contre-pentes,
    # débordements ou dépôts). Compteurs par sévérité et types majeurs.
    _anoms_prof = [a for s in segments for a in (s.get("anomalies") or [])]
    _par_sev = {}
    _par_type = {}
    for _a in _anoms_prof:
        _sev = _a.get("severite") or "info"
        _par_sev[_sev] = _par_sev.get(_sev, 0) + 1
        if _sev in ("fort", "moyen"):
            _t = _a.get("type") or "autre"
            _par_type[_t] = _par_type.get(_t, 0) + 1
    _synthese_anomalies = {
        "total": len(_anoms_prof),
        "forts": _par_sev.get("fort", 0),
        "moyens": _par_sev.get("moyen", 0),
        "faibles": _par_sev.get("faible", 0),
        "types_majeurs": _par_type,
        "messages_forts": [
            _a.get("message") for _a in _anoms_prof
            if _a.get("severite") == "fort" and _a.get("message")
        ][:3],
    }
    return (_altimetrie_info, _gf_prof, _synthese_anomalies, hgl_source_global)


def _etape_sim_data_hydraulique(ctx):
    """Étape extraite verbatim de get_profil_en_long."""
    _clean_node_id = ctx["_clean_node_id"]
    node_elevs = ctx["node_elevs"]
    node_hydraulics = ctx["node_hydraulics"]
    sim_data = ctx["sim_data"]
    sim_meta = ctx["sim_meta"]
    sim_node_results = ctx["sim_node_results"]
    sim_valide = ctx["sim_valide"]

    if sim_valide:
        sim_node_results = sim_data.get("node_results", {})
        sim_meta = sim_data.get("meta", {})
        ts_data = sim_data.get("timeseries") or {}
        node_hydraulics = ts_data.get("node_hydraulics") or sim_data.get("node_hydraulics") or {}
        # Élévations depuis le meta de la simulation (node_elevs injecté dans meta)
        meta_node_elevs = sim_meta.get("node_elevs", {})
        if meta_node_elevs:
            node_elevs.update(meta_node_elevs)
        # Cotes d'invert réellement utilisées par SWMM (section .inp)
        for nh_nid, nh in node_hydraulics.items():
            inv = nh.get("invert_m")
            if inv is not None:
                node_elevs.setdefault(str(nh_nid), float(inv))

        # P0 — enrichissement à la volée pour les simulations persistées
        # AVANT le lot P0 : node_hydraulics sans champs rpt_*, mais le
        # .rpt et node_results sont conservés dans le résultat → les
        # maxima au pas de routage et le débordement réel restent
        # accessibles sans relancer SWMM. Lecture seule, jamais
        # d'estimation : section .rpt absente → champs simplement absents.
        try:
            _besoin_rpt = any(
                isinstance(_nh, dict) and _nh.get("rpt_max_head_m") is None
                for _nh in node_hydraulics.values()
            )
            if _besoin_rpt and sim_data.get("rpt_content"):
                from src.domain.moteur_swmm.analyse_rapport import (
                    extraire_maxima_noeuds_rpt,
                )
                _maxima_rpt = extraire_maxima_noeuds_rpt(sim_data["rpt_content"])
                for _mnid, _mm in (_maxima_rpt or {}).items():
                    _ent = node_hydraulics.get(_mnid)
                    if isinstance(_ent, dict) and _ent.get("rpt_max_head_m") is None:
                        _ent["rpt_max_head_m"] = _mm.get("max_hgl_m")
                        _ent["rpt_max_head_minute"] = _mm.get("max_time_minute")
                        _ent["rpt_max_depth_m"] = _mm.get("max_depth_m")
                        _ent["rpt_reported_max_depth_m"] = _mm.get("reported_max_depth_m")
                        _ent["hgl_max_source"] = "rpt_node_depth_summary"
            # Synthèses .rpt complètes (Node Flooding Summary) : volume
            # brut SWMM et instant du pic — source d'autorité, prioritaire
            # sur node_results persisté (qui peut contenir l'ancienne
            # estimation de volume).
            if sim_data.get("rpt_content"):
                try:
                    from src.domain.moteur_swmm.analyse_rapport import (
                        analyser_rapport_swmm_impl,
                    )
                    _kpis_rpt = analyser_rapport_swmm_impl(
                        rpt_text=sim_data["rpt_content"], meta={})
                    for _mnid, _nr in (_kpis_rpt.get("node_results") or {}).items():
                        if not isinstance(_nr, dict):
                            continue
                        if float(_nr.get("hours_flooded") or 0.0) <= 0.0 and _nr.get("status") != "flooded":
                            continue
                        _ent = node_hydraulics.get(_mnid)
                        if _ent is None:
                            _ent = node_hydraulics.get(_clean_node_id(_mnid))
                        if isinstance(_ent, dict) and _ent.get("rpt_flood_max_m3s") is None:
                            _ent["rpt_flood_max_m3s"] = _nr.get("peak_flood_flow_cms")
                            _ent["rpt_flood_minute"] = _nr.get("flood_time_minute")
                            _ent["rpt_flood_volume_m3"] = _nr.get("flood_volume_m3")
                            _ent["flood_volume_estime"] = bool(_nr.get("flood_volume_estime", True))
                            _ent["flooding_source"] = "rpt_node_flooding_summary"
                except Exception as e_flood:
                    logger.warning("Synthèse flooding .rpt illisible: %s", e_flood)
            # Repli : node_results persisté (volume possiblement estimé
            # par une version antérieure → marqué non fiable).
            for _mnid, _nr in sim_node_results.items():
                if not isinstance(_nr, dict):
                    continue
                if float(_nr.get("hours_flooded") or 0.0) <= 0.0 and _nr.get("status") != "flooded":
                    continue
                _ent = node_hydraulics.get(_mnid)
                if _ent is None:
                    _nc = _clean_node_id(_mnid)
                    _ent = node_hydraulics.get(_nc)
                if isinstance(_ent, dict) and _ent.get("rpt_flood_max_m3s") is None:
                    _ent["rpt_flood_max_m3s"] = _nr.get("peak_flood_flow_cms")
                    _ent["rpt_flood_minute"] = _nr.get("flood_time_minute")
                    _ent["rpt_flood_volume_m3"] = _nr.get("flood_volume_m3")
                    _ent["flood_volume_estime"] = bool(_nr.get("flood_volume_estime", True))
                    _ent["flooding_source"] = "rpt_node_flooding_summary"
        except Exception as e_lazy:
            logger.warning("Enrichissement .rpt à la volée impossible: %s", e_lazy)
    return node_hydraulics, sim_meta, sim_node_results



def _etape_defs_hydraulique(ctx):
    """Définitions de closures hydrauliques (verbatim)."""
    _clean_node_id = ctx["_clean_node_id"]
    base = ctx["base"]
    instant_minute = ctx["instant_minute"]
    node_hydraulics = ctx["node_hydraulics"]

    def _hydrau_noeud(nid: str) -> Optional[Dict[str, Any]]:
        """Entrée node_hydraulics pour un nœud du graphe (clés = noms .out/INP)."""
        if nid in node_hydraulics:
            return node_hydraulics[nid]
        nc = _clean_node_id(nid)
        if nc in node_hydraulics:
            return node_hydraulics[nc]
        for k, v in node_hydraulics.items():
            if _clean_node_id(k) == nc:
                return v
        return None

    def _head_reel(nid: str):
        """(cote, source) — base='max' privilégie le maximum .rpt
        (pas de routage, source d'autorité) ; base='instant' utilise
        le .out à l'instant demandé. (None, 'indisponible') sinon."""
        nh = _hydrau_noeud(nid)
        if not nh:
            return None, "indisponible"
        if base == "instant":
            pairs = nh.get("heads") or []
            if not pairs:
                v = nh.get("max_head_m")
                return (float(v), "swmm_out_max_head") if v is not None else (None, "indisponible")
            best = min(pairs, key=lambda p: abs(p[0] - (instant_minute or 0)))
            return float(best[1]), "swmm_out_instant"
        rpt_h = nh.get("rpt_max_head_m")
        if rpt_h is not None:
            return float(rpt_h), "rpt_max_head"
        v = nh.get("max_head_m")
        return (float(v), "swmm_out_max_head") if v is not None else (None, "indisponible")

    def _flood_reel(nid: str):
        """(débit, source) au même référentiel temporel que la cote.
        base='max' : maximum .rpt (Node Flooding Summary) prioritaire ;
        base='instant' : débordement au pas échantillonné le plus proche,
        jamais le maximum global."""
        nh = _hydrau_noeud(nid)
        if not nh:
            return 0.0, "indisponible"
        if base == "instant":
            heads_pairs = nh.get("heads") or []
            if not heads_pairs:
                return 0.0, "out_report_step"
            m_cible = min(heads_pairs,
                          key=lambda p: abs(p[0] - (instant_minute or 0)))[0]
            for m, v in (nh.get("floods") or []):
                if m == m_cible:
                    return float(v), "swmm_out_instant"
            return 0.0, "swmm_out_instant"
        rpt_f = nh.get("rpt_flood_max_m3s")
        if rpt_f is not None:
            return float(rpt_f), "rpt_node_flooding_summary"
        return float(nh.get("flooding_max_m3s") or 0.0), "out_report_step"
    return _hydrau_noeud, _head_reel, _flood_reel
