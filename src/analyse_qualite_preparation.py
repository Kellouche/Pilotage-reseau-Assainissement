# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Preparation vectorisee des troncons pour la boucle audit qualite
         (extrait de src/analyse_qualite_gpkg.py)
================================================================================
"""

from typing import Any, Dict
import pandas as pd

from src.analyse_qualite_helpers import _clean_id, _resoudre_colonne


def _preparer_troncs(pipes, pipes_m, wgs_pipes, map_pipes, resolveur_noeuds):
    """Pré-extraction vectorisée des tronçons (listes nues + connexités).

    Extrait tel quel de analyser_qualite_gpkg : résout les colonnes une
    fois, lit les valeurs en listes, calcule géométries/longueurs/
    centroïdes et ensembles de connexité amont/aval.
    Retourne un tuple de 14 éléments consommé par la boucle d'audit.
    """
    # ── Pré-extraction vectorisée des tronçons ──────────────────────────
    # Les colonnes candidates sont résolues UNE fois (_resoudre_colonne) puis
    # lues en listes nues : fini les ~10 itérations pandas/ligne (iterrows +
    # _col_val) qui dominaient le temps d'audit (~90 % du coût mesuré).
    n_pipes = len(pipes)
    cols_pipes = pipes.columns

    def _vals_col(*names):
        cn = _resoudre_colonne(map_pipes, cols_pipes, *names)
        return pipes[cn].tolist() if cn is not None else [None] * n_pipes

    u_l = [_clean_id(v) for v in _vals_col("ID_AMONT", "id_amont", "amont", "AMONT", "NOEUD_AMONT")]
    d_l = [_clean_id(v) for v in _vals_col("ID_AVAL", "id_aval", "aval", "AVAL", "NOEUD_AVAL")]
    diam_l = _vals_col("DIAMETRE", "diametre", "Diamètre", "DIAMETER", "diameter")
    mat_l = _vals_col("MATERIAU", "materiau", "Matériau", "MATERIAL", "material")
    long_attrib_l = _vals_col("LONGUEUR", "Longeur", "longueur", "Length", "length")
    prof_am_l = _vals_col("PROF_FE_AM", "prof_fe_am", "PROFFEA")
    prof_av_l = _vals_col("PROF_FE_AV", "prof_fe_av", "PROFFEAV")

    # Refoulement (spec V2.1 §4.4) : même jointure de textes que _est_refoulement
    _GROUPES_REF = (("FONCTIONMT",), ("fonctionmt",), ("Type d'eau",), ("type_eau",),
                    ("Section",), ("TYPEEFFL",))
    ref_cols_vals = [_vals_col(*grp) for grp in _GROUPES_REF]
    refoulement_l = [
        any(k in " ".join(str(ref_cols_vals[g][i] or "") for g in range(len(_GROUPES_REF))).lower()
            for k in ("refoulement", "refoul", "pression", "rejet"))
        for i in range(n_pipes)
    ]

    # Géométries en listes nues + longueurs métriques fiables
    geoms_orig = list(pipes.geometry.values) if n_pipes else []
    geoms_m = (list(pipes_m.geometry.values)
               if (resolveur_noeuds is not None and not pipes_m.empty) else [])
    long_m_l = []
    for i in range(n_pipes):
        gm = geoms_m[i] if i < len(geoms_m) else None
        if gm is not None and gm.length > 0:
            long_m_l.append(float(gm.length))
            continue
        # Repli historique : aboutissait toujours à None (c.crs inaccessible
        # sur une Series → AttributeError → except) — comportement conservé.
        long_m_l.append(None)

    # Centroïdes WGS84 vectorisés pour le centrage carte
    lat_l = [None] * n_pipes
    lon_l = [None] * n_pipes
    if not wgs_pipes.empty:
        try:
            _cent = wgs_pipes.geometry.centroid
            _xs = list(_cent.x)
            _ys = list(_cent.y)
            for i in range(min(n_pipes, len(_xs))):
                if pd.notna(_xs[i]) and pd.notna(_ys[i]):
                    lat_l[i] = round(float(_ys[i]), 6)
                    lon_l[i] = round(float(_xs[i]), 6)
        except Exception:
            pass

    upstream_connections = set()
    downstream_connections = set()
    for _u, _d in zip(u_l, d_l):
        if _u:
            upstream_connections.add(_u)
        if _d:
            downstream_connections.add(_d)
    return (u_l, d_l, diam_l, mat_l, long_attrib_l, prof_am_l, prof_av_l,
            refoulement_l, geoms_orig, geoms_m, long_m_l, lat_l, lon_l,
            upstream_connections, downstream_connections)
