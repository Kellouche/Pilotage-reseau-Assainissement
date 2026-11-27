# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Détection raccordements orphelins, résolution elevations pour simulation (extrait de services/aux_altimetrie_service.py)
================================================================================
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import geopandas as gpd
import numpy as np

logger = logging.getLogger(__name__)
from scipy.spatial import cKDTree

from api.services.aux_altimetrie_apercu import calculer_apercu_terrain
from api.services.aux_altimetrie_ecoulement import (
    SEUIL_CONFIANCE_AZIMUT,
    _ecart_angulaire,
    _charger_contexte_altimetrie,
)
from api.services.aux_altimetrie_regards import _normaliser_code_regard


RACCORDEMENT_RAYON_DEFAUT_M = 50.0
RACCORDEMENT_TOP_K = 3
RACCORDEMENT_MAX_ORPHELINS = 800


def _coordonnees_regards_m(regards_gdf, artefact) -> Dict[str, Tuple[float, float]]:
    """
    code normalisé → (x, y) en mètres. Réutilise le CRS de la couche ;
    si la couche est en degrés (EPSG:4326), projette vers l'UTM de
    l'artefact (`meta.utm_epsg`).
    """
    epsg_cible = None
    try:
        epsg_cible = int(((artefact or {}).get("meta") or {}).get("utm_epsg") or 0) or None
    except (TypeError, ValueError):
        epsg_cible = None

    src_crs = getattr(regards_gdf, "crs", None)
    g = regards_gdf
    if src_crs is not None and epsg_cible:
        try:
            if src_crs.to_epsg() == 4326 and src_crs.to_epsg() != epsg_cible:
                g = regards_gdf.to_crs(epsg_cible)
        except Exception:
            pass

    out: Dict[str, Tuple[float, float]] = {}
    for _, r in g.iterrows():
        codes = _normaliser_code_regard([r.get("Code")])
        code = codes[0] if codes else ""
        if not code:
            continue
        geom = r.geometry
        if geom is None:
            continue
        try:
            out[code] = (float(geom.x), float(geom.y))
        except Exception:
            continue
    return out


def _azimut_vers(x1: float, y1: float, x2: float, y2: float) -> float:
    """Azimut horaire depuis le Nord [0,360) du segment p1 → p2 (plan UTM)."""
    dx, dy = x2 - x1, y2 - y1
    return (np.degrees(np.arctan2(dx, dy)) + 360.0) % 360.0


def _score_raccordement(dist_m: float, rayon_m: float, zt_o, zt_c,
                        zr_o, zr_c, cap_azimut: Optional[float],
                        azimut_descente, conf_orphelin: str) -> Tuple[float, List[str]]:
    """
    Score 0–100 + motifs explicites pour un candidat orphelin → cible
    (sens proposé : l'orphelin se raccorde EN AMONT de la cible).
    """
    motifs: List[str] = []
    score = 40.0 * max(0.0, 1.0 - dist_m / rayon_m)  # proximité : 0–40
    motifs.append(f"distance {dist_m:.1f} m")

    # Terrain : le flux proposé orphelin→cible exige z_terrain qui descend
    if zt_o is not None and zt_c is not None:
        dz = zt_c - zt_o
        if dz < -0.3:
            score += 30.0
            motifs.append(f"terrain descend de {-dz:.2f} m vers la cible")
        elif dz <= 0.3:
            score += 5.0
            motifs.append("terrain quasi horizontal (±0,3 m)")
        else:
            score -= 25.0
            motifs.append(f"terrain remonte de {dz:.2f} m vers la cible — sens à vérifier")

    # Radier estimé : gravitaire exige radier amont > radier aval
    if zr_o is not None and zr_c is not None:
        dzr = zr_c - zr_o
        if dzr < 0:
            score += 20.0
            motifs.append(f"radier estimé cohérent ({-dzr:.2f} m de chute)")
        else:
            score -= 20.0
            motifs.append(f"radier estimé aval plus haut de {dzr:.2f} m — contre-pente probable")

    # Azimut : la cible devrait se situer vers la descente du terrain
    if (cap_azimut is not None and azimut_descente is not None
            and conf_orphelin in SEUIL_CONFIANCE_AZIMUT):
        ecart = _ecart_angulaire(cap_azimut, float(azimut_descente))
        if ecart <= 60.0:
            score += 10.0
            motifs.append(f"cible dans l'axe de descente du terrain (écart {ecart:.0f}°)")
        elif ecart >= 120.0:
            score -= 10.0
            motifs.append(f"cible opposée à la descente du terrain (écart {ecart:.0f}°)")

    return max(0.0, min(100.0, score)), motifs


def analyser_raccordements_terrain(regards_gdf, canalisations_gdf, artefact,
                                   rayon_max_m: float = RACCORDEMENT_RAYON_DEFAUT_M,
                                   top_k: int = RACCORDEMENT_TOP_K) -> Dict[str, Any]:
    """
    Calcul PUR : pour chaque regard orphelin (aucune conduite amont/aval),
    propose les `top_k` nœuds connectés les plus proches dans `rayon_max_m`
    et les classe par score altimétrique. File de revue — aucune écriture.
    """
    from scipy.spatial import cKDTree
    import pandas as pd

    apercu = calculer_apercu_terrain(regards_gdf, canalisations_gdf, artefact)
    par_regard = apercu.get("par_regard") or {}
    par_code_art = (artefact or {}).get("regards") or {}

    # Ensemble des codes connectés (extrémités de conduites)
    connectes = set()
    for _, c in (canalisations_gdf.iterrows() if canalisations_gdf is not None else []):
        for col in ("ID_AMANT", "ID_AVAL"):
            codes = _normaliser_code_regard([c.get(col)])
            if codes:
                connectes.update(codes)

    coords = _coordonnees_regards_m(regards_gdf, artefact)

    # Infos par code : coords + cotes issues de l'aperçu + azimut artefact
    infos: Dict[str, Dict[str, Any]] = {}
    for code, xy in coords.items():
        rt = par_regard.get(code)
        if not rt or rt.get("z_terrain_m") is None:
            continue
        art = par_code_art.get(code) or {}
        infos[code] = {
            "x": xy[0], "y": xy[1],
            "z_terrain_m": rt.get("z_terrain_m"),
            "z_radier_terrain_m": rt.get("z_radier_terrain_m"),
            "confiance": rt.get("confiance") or "aucune",
            "azimut_pente_deg": art.get("azimut_pente_deg"),
            "pente_terrain_pct": art.get("pente_terrain_pct"),
            "lng": art.get("lng"), "lat": art.get("lat"),
        }

    orphelins = {c: i for c, i in infos.items() if c not in connectes}
    cibles = {c: i for c, i in infos.items() if c in connectes}

    if not orphelins or not cibles:
        return {
            "statut": "ok",
            "nb_orphelins": len(orphelins),
            "nb_candidats": 0,
            "orphelins": [],
            "avertissement": "Aucun regard orphelin exploitable ou aucune cible connectée.",
        }

    # Arbre spatial sur les cibles connectées
    codes_cibles = sorted(cibles.keys())
    xy_cibles = np.array([[cibles[c]["x"], cibles[c]["y"]] for c in codes_cibles])
    arbre = cKDTree(xy_cibles)

    resultats = []
    nb_analyses = 0
    codes_orphelins = sorted(orphelins.keys())
    for code in codes_orphelins[:RACCORDEMENT_MAX_ORPHELINS]:
        o = orphelins[code]
        dist, idx = arbre.query([o["x"], o["y"]], k=min(top_k * 4, len(codes_cibles)))
        candidats = []
        for d, i in zip(np.atleast_1d(dist), np.atleast_1d(idx)):
            if d > rayon_max_m:
                continue
            cible = codes_cibles[int(i)]
            ci = cibles[cible]
            azimut_cap = _azimut_vers(o["x"], o["y"], ci["x"], ci["y"])
            score, motifs = _score_raccordement(
                float(d), rayon_max_m,
                o["z_terrain_m"], ci["z_terrain_m"],
                o["z_radier_terrain_m"], ci["z_radier_terrain_m"],
                azimut_cap, o.get("azimut_pente_deg"), o.get("confiance") or "aucune")
            candidats.append({
                "cible": cible,
                "distance_m": round(float(d), 1),
                "score": round(score, 1),
                "z_terrain_cible_m": ci["z_terrain_m"],
                "ecart_terrain_m": (round(ci["z_terrain_m"] - o["z_terrain_m"], 3)
                                    if ci["z_terrain_m"] is not None and o["z_terrain_m"] is not None else None),
                "confiance_cible": ci.get("confiance"),
                "lng_cible": ci.get("lng"), "lat_cible": ci.get("lat"),
                "motifs": motifs,
            })
            if len(candidats) >= top_k:
                break
        nb_analyses += 1
        resultats.append({
            "orphelin": code,
            "lng": o.get("lng"), "lat": o.get("lat"),
            "z_terrain_m": o.get("z_terrain_m"),
            "confiance": o.get("confiance"),
            "candidats": sorted(candidats, key=lambda x: -x["score"]),
        })

    resultats.sort(key=lambda r: (
        -(r["candidats"][0]["score"] if r["candidats"] else -1)))
    avec_candidats = sum(1 for r in resultats if r["candidats"])

    return {
        "statut": "ok",
        "nb_orphelins": len(orphelins),
        "nb_orphelins_analyses": nb_analyses,
        "nb_avec_candidats": avec_candidats,
        "rayon_max_m": rayon_max_m,
        "orphelins": resultats[:RACCORDEMENT_MAX_ORPHELINS],
        "avertissement": (
            "Propositions indicatives classées par cohérence altimétrique "
            "(proximité, descente du terrain, radier estimé, azimut). "
            "Aucune connexion n'est créée automatiquement — validation "
            "hydraulique requise avant toute modification du réseau."
        ),
    }


def analyser_raccordements_projet(db, org_id: str, project_id: str, layer_id: str,
                                  rayon_max_m: float = RACCORDEMENT_RAYON_DEFAUT_M) -> Dict[str, Any]:
    """IO : même contexte que P1, délègue à `analyser_raccordements_terrain`."""
    err, couche, regards_gdf, canas_gdf, artefact = _charger_contexte_altimetrie(
        db, org_id, project_id, layer_id)
    if err is not None:
        return err

    res = analyser_raccordements_terrain(regards_gdf, canas_gdf, artefact,
                                         rayon_max_m=rayon_max_m)
    res["layer_id"] = layer_id
    res["layer_nom"] = couche.nom
    return res


# ---------------------------------------------------------------------------
# Option C — résolution des cotes radier « terrain » pour injection .inp
# ---------------------------------------------------------------------------

def resoudre_elevations_terrain_pour_simulation(
    db, org_id: str, project_id: str, layer_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Option C (SHP.md §7bis) — produit le dict {nid: z_radier} injectable
    dans le .inp quand l'utilisateur demande explicitement le mode
    « altimétrie terrain ». Garde-fous actés :
      - artefact présent et NON périmé (SHA-256 GPKG)
      - couverture ≥ 95 % (eligible_injection_95) sinon refus explicite
      - profondeurs manquantes → médiane réseau (flag provenance)
      - exutoire traité comme les autres nœuds
    Retourne {"statut": "ok", "elevations": {...}, "meta": {...}} ou
    {"statut": <raison>, ...} — l'appelant décide du refus (422).
    """
    from api.models import ProjectAuxLayer
    from src.domain.moteur_swmm.constants import _clean_node_id

    if layer_id:
        couche = db.query(ProjectAuxLayer).filter(
            ProjectAuxLayer.id == layer_id,
            ProjectAuxLayer.project_id == project_id,
            ProjectAuxLayer.org_id == org_id,
        ).first()
        if couche is None:
            return {"statut": "absent", "raison": "Couche altimétrie introuvable."}
    else:
        couche = db.query(ProjectAuxLayer).filter(
            ProjectAuxLayer.project_id == project_id,
            ProjectAuxLayer.org_id == org_id,
            ProjectAuxLayer.type == "altimetrie_points",
            ProjectAuxLayer.statut == "ok",
        ).order_by(ProjectAuxLayer.created_at.desc()).first()
        if couche is None:
            return {"statut": "absent",
                    "raison": "Aucune couche altimétrie opérationnelle sur ce projet."}

    err, _couche, regards_gdf, canas_gdf, artefact = _charger_contexte_altimetrie(
        db, org_id, project_id, couche.id)
    if err is not None:
        return err

    apercu = calculer_apercu_terrain(regards_gdf, canas_gdf, artefact)
    if not apercu.get("eligible_injection_95"):
        return {
            "statut": "couverture_insuffisante",
            "raison": (f"Couverture terrain {apercu.get('couverture', {}).get('pct', 0)} % "
                       f"< 95 % requis — repli sur le datum synthétique."),
            "apercu": apercu,
        }

    elevations: Dict[str, float] = {}
    nb_estimees = 0
    bruts: Dict[str, Tuple[float, bool]] = {}
    for code, info in (apercu.get("par_regard") or {}).items():
        zr = info.get("z_radier_terrain_m")
        if zr is None:
            continue
        nid = _clean_node_id(code)
        if not nid:
            continue
        bruts[nid] = (round(float(zr), 3), bool(info.get("profondeur_estimee")))

    # Garde-fou plausibilité : l'IDW peut extrapoler des cotes aberrantes
    # en bordure d'emprise (ex. z_radier < 0 ou > 3×MAD du médian).
    # Ces nœuds sont traités comme « non couverts » → estimation par
    # voisinage dans _resoudre_altimetrie_noeuds, jamais injectés tels quels.
    nb_hors_plage = 0
    if bruts:
        _vals = np.array([v[0] for v in bruts.values()], dtype="float64")
        _med = float(np.median(_vals))
        _mad = float(np.median(np.abs(_vals - _med))) or 1.0
        _seuil = max(80.0, 6.0 * _mad)
        for nid, (z, estimee) in bruts.items():
            if z < 0.0 or abs(z - _med) > _seuil:
                nb_hors_plage += 1
                continue
            elevations[nid] = z
            if estimee:
                nb_estimees += 1

    if not elevations:
        return {"statut": "absent", "raison": "Aucune cote radier terrain exploitable."}

    meta_art = (artefact or {}).get("meta") or {}
    return {
        "statut": "ok",
        "elevations": elevations,
        "meta": {
            "layer_id": couche.id,
            "layer_nom": couche.nom,
            "resolution_m": meta_art.get("resolution_m"),
            "gpkg_sha256": meta_art.get("gpkg_sha256"),
            "couverture_pct": (apercu.get("couverture") or {}).get("pct"),
            "nb_cotes": len(elevations),
            "nb_profondeurs_estimees": nb_estimees,
            "nb_hors_plage_terrain": nb_hors_plage,
            "profondeur_mediane_m": (apercu.get("profondeur") or {}).get("mediane_reseau_m"),
        },
    }
