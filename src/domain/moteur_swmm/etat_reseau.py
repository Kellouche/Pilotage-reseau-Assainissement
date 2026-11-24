# -*- coding: utf-8 -*-
"""
================================================================================
Module : État physique du réseau (Colmatage & Vieillissement)
Objet  : Calcule les ajustements hydrauliques SWMM 5.2 (section FILLED_CIRCULAR,
         hauteur de sédiment au radier, rugosité de Manning vieillie/composite)
         sans jamais altérer les simulations en état nominal.
================================================================================
"""

import re
from typing import Any, Dict, Optional, Tuple


PRESETS_ETAT_RESEAU: Dict[str, Dict[str, Any]] = {
    "nominal": {
        "scenario_nom": "nominal",
        "colmatage_pct": 0.0,
        "facteur_vieillissement": 1.0,
        "cible_colmatage": "tout_reseau",
        "seuil_pente_pct": 0.5,
        "appliquer_depots_sig": False,
    },
    "exploite": {
        "scenario_nom": "exploite",
        "colmatage_pct": 10.0,
        "facteur_vieillissement": 1.20,
        "cible_colmatage": "faibles_pentes",
        "seuil_pente_pct": 0.5,
        "appliquer_depots_sig": False,
    },
    "critique": {
        "scenario_nom": "critique",
        "colmatage_pct": 25.0,
        "facteur_vieillissement": 1.45,
        "cible_colmatage": "faibles_pentes",
        "seuil_pente_pct": 0.5,
        "appliquer_depots_sig": False,
    },
}


def normaliser_etat_reseau(etat_reseau: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalise et sécurise la configuration d'état du réseau."""
    if not etat_reseau or not isinstance(etat_reseau, dict):
        return dict(PRESETS_ETAT_RESEAU["nominal"])

    nom = str(etat_reseau.get("scenario_nom") or "personnalise").strip()
    cible = str(etat_reseau.get("cible_colmatage") or "tout_reseau").strip()
    if cible not in ("tout_reseau", "faibles_pentes"):
        cible = "tout_reseau"

    colmatage = float(etat_reseau.get("colmatage_pct") if etat_reseau.get("colmatage_pct") is not None else 0.0)
    vieillissement = float(etat_reseau.get("facteur_vieillissement") if etat_reseau.get("facteur_vieillissement") is not None else 1.0)
    seuil_pente = float(etat_reseau.get("seuil_pente_pct") if etat_reseau.get("seuil_pente_pct") is not None else 0.5)

    return {
        "scenario_nom": nom,
        "colmatage_pct": max(0.0, min(90.0, colmatage)),
        "facteur_vieillissement": max(1.0, min(2.5, vieillissement)),
        "cible_colmatage": cible,
        "seuil_pente_pct": max(0.0, min(10.0, seuil_pente)),
        "appliquer_depots_sig": bool(etat_reseau.get("appliquer_depots_sig", False)),
    }


def est_etat_nominal(etat_norm: Dict[str, Any]) -> bool:
    """Retourne True si l'état est strictement nominal (aucune altération du .inp)."""
    return (
        etat_norm.get("colmatage_pct", 0.0) <= 0.0
        and abs(etat_norm.get("facteur_vieillissement", 1.0) - 1.0) < 1e-6
        and not etat_norm.get("appliquer_depots_sig", False)
    )


def extraire_depot_sig_pct(row: Any, diam_mm: float) -> Optional[float]:
    """
    Extrait le pourcentage de colmatage depuis les champs SIG (POURCDEPO, NIV_DEPOT).
    Règle prudente pour valeurs hétérogènes :
    - '100%', '20', '35' (<= 100) -> interprété en % de hauteur au radier.
    - > 100 sans '%' (ex. '200', '300') -> interprété en mm de dépôt, converti en % via diam_mm.
    Plafonné à 90 % pour éviter une section nulle bloquante dans Saint-Venant.
    """
    for col in ("POURCDEPO", "pourcdepo", "NIV_DEPOT", "niv_depot"):
        val = row.get(col) if hasattr(row, "get") else getattr(row, col, None)
        if val is None:
            continue
        s = str(val).strip()
        if not s or s.lower() in ("nan", "none", "null", ""):
            continue
        has_pct = "%" in s
        m = re.search(r"[-+]?\d*\.?\d+", s.replace(",", "."))
        if not m:
            continue
        num = float(m.group(0))
        if num <= 0:
            continue
        if has_pct or num <= 100.0:
            return min(90.0, num)
        if diam_mm > 0:
            return min(90.0, (num / diam_mm) * 100.0)
    return None


def appliquer_etat_conduite(
    row: Any,
    diam_m: float,
    shape: str,
    geom1: float,
    geom2: float,
    rough_base: float,
    pente_conduite_pct: Optional[float],
    etat_norm: Dict[str, Any],
) -> Tuple[str, float, float, float, float, Dict[str, Any]]:
    """
    Calcule les paramètres hydrauliques ajustés d'une conduite selon l'état du réseau.
    Retourne: (xsec_shape, geom1_adj, geom2_adj, sed_depth_m, rough_adj, info_meta)
    """
    if est_etat_nominal(etat_norm):
        xsec_shape = "RECT_CLOSED" if shape == "RECTANGULAR" else "CIRCULAR"
        return xsec_shape, geom1, geom2, 0.0, rough_base, {"colmate": False, "pct_colmatage": 0.0}

    pct_colmatage = 0.0
    source_depot = None

    if etat_norm["colmatage_pct"] > 0.0:
        if etat_norm["cible_colmatage"] == "faibles_pentes":
            if pente_conduite_pct is not None and pente_conduite_pct <= etat_norm["seuil_pente_pct"]:
                pct_colmatage = etat_norm["colmatage_pct"]
                source_depot = "scenario_faible_pente"
        else:
            pct_colmatage = etat_norm["colmatage_pct"]
            source_depot = "scenario_global"

    if etat_norm["appliquer_depots_sig"]:
        sig_pct = extraire_depot_sig_pct(row, diam_m * 1000.0)
        if sig_pct is not None and sig_pct > pct_colmatage:
            pct_colmatage = sig_pct
            source_depot = "sig_niv_depot"

    rough_adj = rough_base * etat_norm["facteur_vieillissement"]
    if pct_colmatage > 0.0:
        # Fond envasé : majoration composite de la rugosité de Manning
        rough_adj = rough_adj + (0.006 * (pct_colmatage / 100.0))
    rough_adj = round(min(0.0500, max(0.0090, rough_adj)), 4)

    sed_depth_m = 0.0
    geom1_adj = geom1
    geom2_adj = geom2

    if shape == "RECTANGULAR":
        xsec_shape = "RECT_CLOSED"
        if pct_colmatage > 0.0:
            sed_depth_m = round(min(geom1 * 0.90, geom1 * (pct_colmatage / 100.0)), 3)
            geom1_adj = round(max(0.05, geom1 - sed_depth_m), 3)
    else:
        if pct_colmatage > 0.0:
            xsec_shape = "FILLED_CIRCULAR"
            sed_depth_m = round(min(geom1 * 0.90, geom1 * (pct_colmatage / 100.0)), 3)
            geom2_adj = sed_depth_m
        else:
            xsec_shape = "CIRCULAR"

    info = {
        "colmate": pct_colmatage > 0.0,
        "pct_colmatage": round(pct_colmatage, 1),
        "source_depot": source_depot,
        "sed_depth_m": sed_depth_m,
        "rough_adj": rough_adj,
    }
    return xsec_shape, geom1_adj, geom2_adj, sed_depth_m, rough_adj, info
