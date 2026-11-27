# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Aperçu des cotes terrain projet (constantes, médiane, sanitisation, calcul) (extrait de services/aux_altimetrie_service.py)
================================================================================
"""

import logging
import re

from api.services.aux_altimetrie_regards import charger_regards_terrain, _normaliser_code_regard
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import geopandas as gpd
import numpy as np

logger = logging.getLogger(__name__)


SEUIL_COUVERTURE_INP = 0.95   # garde-fou : ≥95 % des nœuds couverts sinon refus


def _mediane(valeurs) -> Optional[float]:
    vals = sorted(float(v) for v in valeurs
                  if v is not None and np.isfinite(float(v)))
    if not vals:
        return None
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2.0


def _sanitiser_profondeur_m(val) -> Optional[float]:
    """
    Sanitisation des profondeurs radier (spec CQ V2.1 §4.2) :
    - 0,30–10,0 m : accepté en mètres ;
    - 10–12 000 : conversion d'unité suspecte (mm/cm) avec avertissement ;
    - hors limites ou non numérique : rejeté → None (profondeur médiane
      injectée en aval → le tronçon bascule en N3, jamais en anomalie).
    """
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v):
        return None
    if 0.30 <= v <= 10.0:
        return v
    if 10.0 < v <= 12000.0:
        conv = v / 1000.0 if v > 300.0 else v / 100.0
        if 0.30 <= conv <= 10.0:
            _PROFONDEURS_CONVERTIES[0] += 1
            return conv
    return None


_PROFONDEURS_CONVERTIES = [0]  # compteur thread-safe suffisant (usage synchrone)


def calculer_apercu_terrain(regards_gdf, canalisations_gdf, artefact) -> Dict[str, Any]:
    """
    Calcul PUR (sans IO) : pour chaque regard du réseau → z_terrain IDW,
    profondeur réelle ou médiane réseau (flag `profondeur_estimee`),
    z_radier_terrain = z_terrain − profondeur.

    + statistiques de couverture et détection d'inversions amont/aval
    (z_radier amont ≤ z_radier aval) sur les conduites du GPKG.
    """
    import pandas as pd

    profondeurs = []
    regards = {}
    for _, r in regards_gdf.iterrows():
        codes = _normaliser_code_regard([r.get("Code")])
        code = codes[0] if len(codes) else ""
        if not code:
            continue
        try:
            prof = float(r.get("Profondeur")) if pd.notna(r.get("Profondeur")) else None
        except (TypeError, ValueError):
            prof = None
        prof = _sanitiser_profondeur_m(prof) if prof is not None else None
        if prof is not None and prof > 0:
            profondeurs.append(prof)
        regards[code] = {"profondeur": prof}

    med = _mediane(profondeurs)
    par_code = (artefact or {}).get("regards") or {}
    meta = (artefact or {}).get("meta") or {}

    par_regard: Dict[str, Any] = {}
    stats_conf: Dict[str, int] = {"haute": 0, "moyenne": 0, "faible": 0, "aucune": 0}
    nb_terrain = 0
    nb_prof_reelle = 0
    nb_prof_estimee = 0

    for code, info in regards.items():
        rt = par_code.get(code) or {}
        zt = rt.get("z_terrain_m")
        conf = rt.get("confiance") or "aucune"
        stats_conf[conf] = stats_conf.get(conf, 0) + 1
        if zt is None:
            continue
        nb_terrain += 1
        prof = info["profondeur"]
        if prof is not None:
            nb_prof_reelle += 1
            prof_utilisee = prof
            estimee = False
        else:
            nb_prof_estimee += 1
            prof_utilisee = med
            estimee = True
        z_rad = (round(float(zt) - float(prof_utilisee), 3)
                 if prof_utilisee is not None else None)
        par_regard[code] = {
            "z_terrain_m": float(zt),
            "confiance": conf,
            "profondeur_m": round(float(prof_utilisee), 3) if prof_utilisee is not None else None,
            "profondeur_estimee": estimee,
            "z_radier_terrain_m": z_rad,
        }

    # Inversions amont→aval sur les conduites : le radier amont devrait
    # être strictement plus haut que le radier aval (écoulement gravitaire).
    inversions = []
    _lignes_canas = canalisations_gdf.iterrows() if canalisations_gdf is not None else []
    for _, c in _lignes_canas:
        us = _normaliser_code_regard([c.get("ID_AMONT")])
        vs = _normaliser_code_regard([c.get("ID_AVAL")])
        u, v = (us[0] if us else ""), (vs[0] if vs else "")
        ru, rv = par_regard.get(u), par_regard.get(v)
        if not ru or not rv:
            continue
        za, zv = ru.get("z_radier_terrain_m"), rv.get("z_radier_terrain_m")
        if za is None or zv is None:
            continue
        if za <= zv:
            inversions.append({
                "amont": u, "aval": v,
                "z_radier_amont": za, "z_radier_aval": zv,
                "ecart_m": round(zv - za, 3),
            })

    total = len(regards)
    pct = round(100.0 * nb_terrain / total, 1) if total else 0.0

    return {
        "statut": "ok",
        "gpkg_sha256": meta.get("gpkg_sha256"),
        "resolution_m": meta.get("resolution_m"),
        "utm_epsg": meta.get("utm_epsg"),
        "couverture": {
            "total_regards": total,
            "avec_terrain": nb_terrain,
            "pct": pct,
            "par_confiance": stats_conf,
        },
        "profondeur": {
            "nb_reelles": nb_prof_reelle,
            "nb_estimees": nb_prof_estimee,
            "mediane_reseau_m": round(med, 3) if med is not None else None,
            "nb_unites_converties": _PROFONDEURS_CONVERTIES[0],
        },
        "inversions_amont_aval": {
            "nb": len(inversions),
            "echantillon": inversions[:20],
        },
        "eligible_injection_95": bool(total and pct >= SEUIL_COUVERTURE_INP * 100),
        "par_regard": par_regard,
        "avertissement": (
            "Cotes radier estimées = terrain IDW − profondeur (réelle ou médiane "
            "réseau). Terrain interpolé ≠ mesure : à valider avant injection .inp."
        ),
    }


def apercu_elevations_terrain(db, org_id: str, project_id: str, layer_id: str) -> Dict[str, Any]:
    """
    IO : charge l'artefact regards_terrain de la couche, vérifie
    l'estampillage SHA-256 vs le GPKG projet courant, lit regards +
    canalisations et délègue à `calculer_apercu_terrain`.
    """
    from api.models import Project, ProjectAuxLayer
    from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet_avec_meta

    couche = db.query(ProjectAuxLayer).filter(
        ProjectAuxLayer.id == layer_id,
        ProjectAuxLayer.project_id == project_id,
        ProjectAuxLayer.org_id == org_id,
    ).first()
    if couche is None:
        return {"statut": "absent", "raison": "Couche introuvable."}
    if couche.type != "altimetrie_points" or couche.statut != "ok":
        return {"statut": "ignore",
                "raison": "La couche n'est pas une altimétrie opérationnelle."}

    artefact = charger_regards_terrain(org_id, project_id, layer_id)
    if not artefact:
        return {"statut": "absent",
                "raison": "Aucun artefact regards_terrain — lancez le recalcul."}

    project = db.query(Project).filter(
        Project.id == project_id, Project.org_id == org_id
    ).first()
    gpkg_path, meta_v = resoudre_gpkg_effectif_pour_projet_avec_meta(db, project)
    sha_courant = (meta_v or {}).get("sha256")
    if not sha_courant and gpkg_path:
        try:
            from api.services.gpkg_versions import sha256_fichier
            sha_courant = sha256_fichier(Path(gpkg_path))
        except Exception:
            sha_courant = None
    sha_artefact = ((artefact.get("meta") or {}).get("gpkg_sha256"))
    if sha_courant and sha_artefact and sha_courant != sha_artefact:
        return {
            "statut": "perime",
            "raison": "L'artefact a été calculé sur une autre version du réseau "
                       "— recalcul requis avant tout usage.",
            "gpkg_sha256_courant": sha_courant,
            "gpkg_sha256_artefact": sha_artefact,
        }
    if gpkg_path is None:
        return {"statut": "absent", "raison": "Aucun GPKG projet résolu."}

    try:
        couches = gpd.list_layers(str(gpkg_path))["name"].tolist()
        nom_regards = next((l for l in couches if "regard" in l.lower()), None)
        nom_canas = next(
            (l for l in couches
             if any(k in l.lower() for k in ["canalisat", "conduit", "pipe", "troncon"])
             and "désaffect" not in l.lower() and "desaffect" not in l.lower()),
            None,
        )
        if nom_regards is None:
            return {"statut": "absent", "raison": "Couche 'regards' absente du GPKG."}
        regards_gdf = gpd.read_file(str(gpkg_path), layer=nom_regards)
        canas_gdf = (gpd.read_file(str(gpkg_path), layer=nom_canas)
                     if nom_canas else None)
    except Exception as e:
        return {"statut": "erreur", "raison": f"Lecture GPKG impossible : {e}"}

    res = calculer_apercu_terrain(regards_gdf, canas_gdf, artefact)
    res["layer_id"] = layer_id
    res["layer_nom"] = couche.nom
    return res


# ---------------------------------------------------------------------------
# P1 — suspects de sens d'écoulement (SHP.md §8)
# ---------------------------------------------------------------------------
#
# Trois signaux par conduite, jamais de verdict automatique :
#   1. terrain : z_terrain(aval) > z_terrain(amont) → le terrain MONTE le
#      long du sens d'écoulement supposé (pente_contre = écart/longueur) ;
#   2. radier estimé : z_radier_terrain(aval) > z_radier_terrain(amont)
#      (signal plus faible : la profondeur injectée lisse une partie du bruit) ;
#   3. azimut : la plus forte descente du terrain (azimut_pente_deg de
#      l'artefact) s'oppose au cap de la conduite — seulement si la pente
#      locale est significative (sinon le bruit domine).
#
# Le classement alimente une FILE DE REVUE — aucune correction n'est
# appliquée sans validation utilisateur (règle SHP.md : jamais de snap
# automatique).
