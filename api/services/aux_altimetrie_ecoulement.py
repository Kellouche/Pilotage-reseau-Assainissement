# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Analyse écoulement vs terrain : inversions pente, azimut, contexte projet (extrait de services/aux_altimetrie_service.py)
================================================================================
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import geopandas as gpd
import numpy as np

logger = logging.getLogger(__name__)
from api.services.aux_altimetrie_apercu import calculer_apercu_terrain
from api.services.aux_altimetrie_regards import charger_regards_terrain, _normaliser_code_regard


PENTE_INVERSION_FORT_PCT = 1.0     # terrain monte > 1 % le long du flux
PENTE_INVERSION_MOYEN_PCT = 0.3    # ... > 0,3 %
PENTE_LOCALE_MIN_AZIMUT_PCT = 1.0  # en dessous, l'azimut n'est pas probant
ECART_AZIMUT_OPPOSE_DEG = 120.0
SEUIL_CONFIANCE_AZIMUT = {"haute", "moyenne"}


def _longueur_conduite_m(c) -> float:
    """Longueur de la conduite en mètres (attribut SIG prioritaire)."""
    import pandas as pd
    for col in ("Longeur", "LONGUEUR", "Longueur", "LINEAIRE", "length", "Length"):
        if col in c and pd.notna(c.get(col)):
            try:
                v = float(c.get(col))
                if v > 0:
                    return v
            except (TypeError, ValueError):
                continue
    # Repli : distance à vol d'oiseau entre extrémités (approx. locale)
    try:
        geom = c.geometry
        if geom is not None and not geom.is_empty and len(geom.coords) >= 2:
            (x1, y1), (x2, y2) = geom.coords[0], geom.coords[-1]
            lat_m = np.radians((y1 + y2) / 2.0)
            dx = (x2 - x1) * 111320.0 * np.cos(lat_m)
            dy = (y2 - y1) * 110540.0
            return float(np.hypot(dx, dy))
    except Exception:
        pass
    return 0.0


def _cap_conduite_deg(c) -> Optional[float]:
    """Cap (azimut horaire depuis le Nord) de la conduite, ou None."""
    try:
        geom = c.geometry
        if geom is None or geom.is_empty or len(geom.coords) < 2:
            return None
        (x1, y1), (x2, y2) = geom.coords[0], geom.coords[-1]
        dx = (x2 - x1) * np.cos(np.radians((y1 + y2) / 2.0))
        dy = y2 - y1
        if dx == 0 and dy == 0:
            return None
        return float((np.degrees(np.arctan2(dx, dy)) + 360.0) % 360.0)
    except Exception:
        return None


def _ecart_angulaire(a: float, b: float) -> float:
    """Écart angulaire minimal en degrés entre deux azimuts [0,360)."""
    d = abs((a - b) % 360.0)
    return min(d, 360.0 - d)


def _pire_confiance(c1: str, c2: str) -> str:
    ordre = {"haute": 0, "moyenne": 1, "faible": 2, "aucune": 3}
    return c1 if ordre.get(c1, 3) >= ordre.get(c2, 3) else c2


def analyser_ecoulement_terrain(regards_gdf, canalisations_gdf, artefact) -> Dict[str, Any]:
    """
    Calcul PUR : file de revue des conduites dont le sens d'écoulement
    supposé (ID_AMONT → ID_AVAL) est suspect au regard du terrain.
    Réutilise `calculer_apercu_terrain` pour les cotes radier estimées.
    """
    apercu = calculer_apercu_terrain(regards_gdf, canalisations_gdf, artefact)
    par_regard = apercu.get("par_regard") or {}
    par_code_art = (artefact or {}).get("regards") or {}

    suspects = []
    nb_analysées = 0
    _lignes = canalisations_gdf.iterrows() if canalisations_gdf is not None else []
    for _, c in _lignes:
        us = _normaliser_code_regard([c.get("ID_AMONT")])
        vs = _normaliser_code_regard([c.get("ID_AVAL")])
        u = us[0] if us else ""
        v = vs[0] if vs else ""
        if not u or not v or u == v:
            continue
        ru, rv = par_regard.get(u), par_regard.get(v)
        if not ru or not rv:
            continue
        zt_a, zt_v = ru.get("z_terrain_m"), rv.get("z_terrain_m")
        if zt_a is None or zt_v is None:
            continue
        longueur = _longueur_conduite_m(c)
        if longueur <= 0:
            continue
        nb_analysées += 1

        # Signal 1 — terrain : écart positif = le terrain MONTE le long du flux
        dz_terr = round(float(zt_v) - float(zt_a), 3)
        pente_contre = round(100.0 * dz_terr / longueur, 3)

        # Signal 2 — radier estimé (profondeur lisse une partie du bruit)
        zr_a, zr_v = ru.get("z_radier_terrain_m"), rv.get("z_radier_terrain_m")
        dz_rad = round(float(zr_v) - float(zr_a), 3) if (zr_a is not None and zr_v is not None) else None

        # Signal 3 — azimut de plus forte descente vs cap de la conduite
        cap = _cap_conduite_deg(c)
        art_u = par_code_art.get(u) or {}
        art_v = par_code_art.get(v) or {}
        azimut = art_u.get("azimut_pente_deg")
        pente_loc = art_u.get("pente_terrain_pct")
        conf_u, conf_v = ru.get("confiance") or "aucune", rv.get("confiance") or "aucune"
        ecart_azimut = None
        if cap is not None and azimut is not None and conf_u in SEUIL_CONFIANCE_AZIMUT:
            ecart_azimut = round(_ecart_angulaire(cap, float(azimut)), 1)

        motifs = []
        score = 0
        if dz_terr > 0:
            if pente_contre >= PENTE_INVERSION_FORT_PCT:
                motifs.append(f"terrain monte de {dz_terr} m le long du flux "
                              f"({pente_contre} % > {PENTE_INVERSION_FORT_PCT} %)")
                score += 3
            elif pente_contre >= PENTE_INVERSION_MOYEN_PCT:
                motifs.append(f"terrain monte de {dz_terr} m le long du flux "
                              f"({pente_contre} %)")
                score += 2
            else:
                motifs.append(f"léger relèvement terrain ({dz_terr} m, {pente_contre} %) — probable bruit")
                score += 1
        if dz_rad is not None and dz_rad > 0:
            motifs.append(f"radier estimé aval plus haut de {dz_rad} m")
            score += 1
        if (ecart_azimut is not None and ecart_azimut > ECART_AZIMUT_OPPOSE_DEG
                and (pente_loc or 0) >= PENTE_LOCALE_MIN_AZIMUT_PCT):
            motifs.append(f"plus forte descente du terrain à {ecart_azimut:.0f}° "
                          f"du cap de la conduite (pente locale {pente_loc} %)")
            score += 2

        if score <= 0:
            continue

        severite = "fort" if score >= 4 else ("moyen" if score >= 2 else "faible")
        suspects.append({
            "amont": u,
            "aval": v,
            "longueur_m": round(longueur, 1),
            "z_terrain_amont": zt_a,
            "z_terrain_aval": zt_v,
            "ecart_terrain_m": dz_terr,
            "pente_contre_pct": pente_contre,
            "z_radier_amont": zr_a,
            "z_radier_aval": zr_v,
            "ecart_radier_m": dz_rad,
            "cap_conduite_deg": round(cap, 1) if cap is not None else None,
            "azimut_pente_amont_deg": azimut,
            "pente_terrain_amont_pct": pente_loc,
            "ecart_azimut_deg": ecart_azimut,
            "confiance": _pire_confiance(conf_u, conf_v),
            "lng_amont": art_u.get("lng"), "lat_amont": art_u.get("lat"),
            "lng_aval": art_v.get("lng"), "lat_aval": art_v.get("lat"),
            "score": score,
            "severite": severite,
            "motifs": motifs,
        })

    suspects.sort(key=lambda s: (-s["score"], -abs(s["pente_contre_pct"])))
    par_sev = {"fort": 0, "moyen": 0, "faible": 0}
    for s in suspects:
        par_sev[s["severite"]] += 1

    return {
        "statut": "ok",
        "nb_conduites_analysées": nb_analysées,
        "nb_suspects": len(suspects),
        "par_severite": par_sev,
        "suspects": suspects[:300],
        "meta_artefact": {
            "gpkg_sha256": ((artefact or {}).get("meta") or {}).get("gpkg_sha256"),
            "resolution_m": ((artefact or {}).get("meta") or {}).get("resolution_m"),
            "nb_regards": ((artefact or {}).get("meta") or {}).get("nb_regards"),
        },
        "avertissement": (
            "File de revue indicative : le terrain IDW (±1–2 m) produit des "
            "relèvements sur terrain plat — chaque suspect doit être recoupé "
            "avec le sens d'écoulement supposé et les profils radier avant "
            "toute correction. Aucune modification automatique n'est appliquée."
        ),
    }


def _charger_contexte_altimetrie(db, org_id: str, project_id: str, layer_id: str):
    """
    IO commun aux analyses P1/P2 : résout couche + artefact regards_terrain
    (estampillage SHA-256) + GPKG projet. Retourne
    (erreur_dict_ou_None, couche, regards_gdf, canas_gdf, artefact).
    """
    from api.models import Project, ProjectAuxLayer
    from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet_avec_meta

    couche = db.query(ProjectAuxLayer).filter(
        ProjectAuxLayer.id == layer_id,
        ProjectAuxLayer.project_id == project_id,
        ProjectAuxLayer.org_id == org_id,
    ).first()
    if couche is None:
        return {"statut": "absent", "raison": "Couche introuvable."}, None, None, None, None
    if couche.type != "altimetrie_points" or couche.statut != "ok":
        return {"statut": "ignore",
                "raison": "Analyse réservée aux couches altimétrie opérationnelles."}, None, None, None, None

    artefact = charger_regards_terrain(org_id, project_id, layer_id)
    if not artefact:
        return {"statut": "absent",
                "raison": "Aucun artefact regards_terrain — recalcul requis."}, None, None, None, None

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
        return {"statut": "perime",
                "raison": "Artefact calculé sur une autre version du réseau."}, None, None, None, None
    if gpkg_path is None:
        return {"statut": "absent", "raison": "Aucun GPKG projet résolu."}, None, None, None, None

    try:
        couches = gpd.list_layers(str(gpkg_path))["name"].tolist()
        nom_regards = next((l for l in couches if "regard" in l.lower()), None)
        nom_canas = next(
            (l for l in couches
             if any(k in l.lower() for k in ["canalisat", "conduit", "pipe", "troncon"])
             and "désaffect" not in l.lower() and "desaffect" not in l.lower()),
            None,
        )
        if nom_regards is None or nom_canas is None:
            return {"statut": "absent", "raison": "Couches regards/canalisations absentes."}, None, None, None, None
        regards_gdf = gpd.read_file(str(gpkg_path), layer=nom_regards)
        canas_gdf = gpd.read_file(str(gpkg_path), layer=nom_canas)
    except Exception as e:
        return {"statut": "erreur", "raison": f"Lecture GPKG impossible : {e}"}, None, None, None, None

    return None, couche, regards_gdf, canas_gdf, artefact


def analyser_ecoulement_projet(db, org_id: str, project_id: str, layer_id: str) -> Dict[str, Any]:
    """
    IO : charge couche + artefact + GPKG projet, délègue à
    `analyser_ecoulement_terrain`. Mêmes gardes que l'aperçu .inp
    (estampillage SHA-256, statut couche, artefact présent).
    """
    err, couche, regards_gdf, canas_gdf, artefact = _charger_contexte_altimetrie(
        db, org_id, project_id, layer_id)
    if err is not None:
        return err

    res = analyser_ecoulement_terrain(regards_gdf, canas_gdf, artefact)
    res["layer_id"] = layer_id
    res["layer_nom"] = couche.nom
    return res


# ---------------------------------------------------------------------------
# P2 — candidats de raccordement pour regards orphelins (SHP.md §9)
# ---------------------------------------------------------------------------
