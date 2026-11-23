# -*- coding: utf-8 -*-
"""
================================================================================
Module : Découverte automatique des conventions de nommage et de snap
Objet : Le système découvre SEUL les alias d'identifiants (ex. 'RJ_12' -> '12')
         et la tolérance de snap pertinente pour un GeoPackage donné, sans
         aucune configuration utilisateur. Chaque convention découverte est
         fondée sur une preuve géométrique (distance mesurée) et persistée
         dans `<reseau>.conventions.json` pour être partagée par le graphe de
         bassins, le générateur .inp SWMM et l'audit qualité.

         Garde-fous :
         - une correspondance par noyau n'est retenue que si l'extrémité est
           à <= SEUIL_CONFIRMATION_ALIAS_M du nœud cible (preuve spatiale) ;
         - au moins MIN_OCCURRENCES_ALIAS occurrences validées ;
         - ambiguïté (plusieurs nœuds candidats valides) -> jamais de lien ;
         - la tolérance de snap n'augmente que sur cluster statistique net,
           plafonnée à SNAP_TOLERANCE_MAX_M.
================================================================================
"""

import json
import logging
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

from src.domain.moteur_swmm.constants import _clean_node_id

logger = logging.getLogger("swmm_platform.topologie.decouverte")

# ---------------------------------------------------------------------------
# Paramètres conservateurs de la découverte
# ---------------------------------------------------------------------------
SEUIL_CONFIRMATION_ALIAS_M = 2.0   # distance max pour valider une occurrence d'alias
MIN_OCCURRENCES_ALIAS = 3          # occurrences minimales pour activer la règle
SNAP_TOLERANCE_BASE_M = 0.50       # tolérance historique (jamais réduite)
SNAP_TOLERANCE_MAX_M = 3.0         # plafond absolu — au-delà c'est de la donnée, pas du snap
SNAP_CANDIDAT_MAX_M = 5.0          # distance max considérée comme candidat snap
SNAP_MIN_ECHANTILLONS = 8          # échantillons minimaux pour ajuster la tolérance
ALIAS_AUTO_MAX_DIST_M = 2.5        # distance max acceptée à la résolution ( Alias auto )

_CACHE_SUFFIXE = ".conventions.json"


# ---------------------------------------------------------------------------
# Extraction des noyaux candidats
# ---------------------------------------------------------------------------

def _tokens_alnum(nid: str) -> List[str]:
    return [t for t in re.split(r"[^A-Za-z0-9]+", nid or "") if t]


def noyaux_candidats(nid: str) -> List[str]:
    """
    Retourne les noyaux candidats pour la correspondance par alias automatique.

    Ordre de tentative (du plus spécifique au plus générique) :
      1. dernier token alphanumérique contenant au moins un chiffre
         ('EX_12' -> '12', 'A12_B' -> 'B' ignoré car sans chiffre -> 'A12') ;
      2. chaque groupe de chiffres pur par longueur décroissante
         ('RJ_2024_12' -> '2024', '12').
    """
    tokens = _tokens_alnum(nid)
    cands: List[str] = []

    # 1. Tokens contenant un chiffre, du dernier vers le premier
    for tok in reversed(tokens):
        if any(ch.isdigit() for ch in tok):
            cands.append(tok)

    # 2. Groupes de chiffres purs (complément : 'RJ_02' -> '02', 'X1Y2' -> '2')
    for m in re.finditer(r"\d+", nid or ""):
        cands.append(m.group(0))

    # Dédupliquer en conservant l'ordre
    vus = set()
    out = []
    for c in cands:
        if c and c not in vus:
            vus.add(c)
            out.append(c)
    return out


def index_noeuds_numeriques(noeuds: Dict[str, Tuple[float, float]]) -> Dict[int, str]:
    """
    Index {valeur_entière: nid} pour les nœuds à identifiant purement numérique.
    Permet 'RJ_02' -> nœud '2' et 'EX_2' -> nœud '02' (égalité numérique).
    """
    idx: Dict[int, str] = {}
    for nid in noeuds:
        txt = str(nid).strip()
        if txt.isdigit():
            v = int(txt)
            idx.setdefault(v, nid)
    return idx


def resoudre_noyau(
    noeuds: Dict[str, Tuple[float, float]],
    index_num: Dict[int, str],
    core: str,
) -> Optional[str]:
    """Résout un noyau candidat vers un identifiant de nœud existant."""
    if core in noeuds:
        return core
    if core.isdigit():
        return index_num.get(int(core))
    return None


# ---------------------------------------------------------------------------
# Découverte
# ---------------------------------------------------------------------------

def _distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _resoudre_alias_auto(
    nid: str,
    point: Optional[Tuple[float, float]],
    noeuds: Dict[str, Tuple[float, float]],
    index_num: Dict[int, str],
    max_dist_m: float,
) -> Optional[Tuple[str, float]]:
    """
    Correspondance par noyau avec confirmation spatiale.
    Retourne (nid_noeud, distance) si exactement UN nœud candidat est valide ;
    None si aucun ou si ambiguïté (plusieurs nœuds distincts valides).
    """
    if point is None:
        return None
    valides = {}
    for core in noyaux_candidats(nid):
        cible = resoudre_noyau(noeuds, index_num, core)
        if cible is None or cible in valides:
            continue
        d = _distance(point, noeuds[cible])
        if d <= max_dist_m:
            valides[cible] = d
    if len(valides) == 1:
        cible, d = next(iter(valides.items()))
        return cible, d
    return None


def decouvrir_conventions(
    noeuds: Dict[str, Tuple[float, float]],
    echecs: List[Tuple[str, Optional[Tuple[float, float]]]],
    tolerance_snap_base_m: float = SNAP_TOLERANCE_BASE_M,
) -> Dict[str, Any]:
    """
    Analyse les extrémités non résolues et découvre les conventions du jeu
    de données. `echecs` = liste de (identifiant_brut, point_xy_m).

    Retourne le dict de conventions (persistable en JSON) :
      alias_noyau : {actif, max_dist_m, occurrences}
      snap_tolerance_m : tolérance ajustée sur preuve statistique
      statistiques : compteurs de la découverte
    """
    index_num = index_noeuds_numeriques(noeuds)
    noeuds_list = list(noeuds.values())
    tree = None
    if noeuds_list:
        try:
            from scipy.spatial import cKDTree
            tree = cKDTree(np.array(noeuds_list, dtype=float))
        except Exception:
            tree = None

    stats = {
        "extremites_evaluees": len(echecs),
        "echecs_avec_point": 0,
        "alias_valides": 0,
        "alias_ambigus": 0,
        "snap_candidats": 0,
    }
    distances_plus_proche: List[float] = []
    alias_distances: List[float] = []

    for nid, pt in echecs:
        if pt is None:
            continue
        stats["echecs_avec_point"] += 1

        # Distance au nœud le plus proche (toutes catégories) -> snap adaptatif
        if tree is not None:
            try:
                d_min, _ = tree.query(np.array(pt, dtype=float))
                distances_plus_proche.append(float(d_min))
                if float(d_min) <= SNAP_CANDIDAT_MAX_M:
                    stats["snap_candidats"] += 1
            except Exception:
                pass

        # Validation de la correspondance par noyau
        hit = _resoudre_alias_auto(
            nid, pt, noeuds, index_num, SEUIL_CONFIRMATION_ALIAS_M)
        if hit is not None:
            stats["alias_valides"] += 1
            alias_distances.append(hit[1])
        elif noyaux_candidats(nid):
            # Des noyaux existaient mais validation ambiguë ou hors distance
            pass

    # Ambiguïtés : endpoints avec noyaux candidats mais aucune validation
    # (approximation : on ne les compte pas séparément, la règle reste OFF
    #  si le seuil d'occurrences n'est pas atteint — conservateur).

    # --- Règle alias par noyau ---
    nb_alias = stats["alias_valides"]
    alias_actif = nb_alias >= MIN_OCCURRENCES_ALIAS
    alias_max_dist = ALIAS_AUTO_MAX_DIST_M
    if alias_actif and alias_distances:
        alias_max_dist = min(
            ALIAS_AUTO_MAX_DIST_M,
            max(1.0, math.ceil((max(alias_distances) + 0.5) * 10) / 10),
        )

    # --- Tolérance de snap adaptative ---
    snap_tol = max(tolerance_snap_base_m, SNAP_TOLERANCE_BASE_M)
    ds = sorted(d for d in distances_plus_proche if d <= SNAP_CANDIDAT_MAX_M)
    if len(ds) >= SNAP_MIN_ECHANTILLONS:
        p75 = ds[min(len(ds) - 1, int(0.75 * (len(ds) - 1)))]
        if p75 <= 2.5:
            snap_tol = min(SNAP_TOLERANCE_MAX_M, max(SNAP_TOLERANCE_BASE_M,
                                                    math.ceil(p75 * 10) / 10))

    conventions = {
        "version": 1,
        "alias_noyau": {
            "actif": alias_actif,
            "max_dist_m": round(alias_max_dist, 2),
            "occurrences": nb_alias,
        },
        "snap_tolerance_m": round(snap_tol, 2),
        "statistiques": stats,
        "decouvert_le": datetime.now(timezone.utc).isoformat(),
    }
    if alias_actif:
        logger.info(
            "[conventions] Alias par noyau DÉCOUVERT : %d occurrences, "
            "distance max %.2f m", nb_alias, alias_max_dist)
    if snap_tol > SNAP_TOLERANCE_BASE_M:
        logger.info(
            "[conventions] Snap ajusté : %.2f m -> %.2f m (%d candidats)",
            SNAP_TOLERANCE_BASE_M, snap_tol, stats["snap_candidats"])
    return conventions


# ---------------------------------------------------------------------------
# Persistance par GeoPackage (<fichier>.conventions.json)
# ---------------------------------------------------------------------------

def chemin_cache_conventions(gpkg_path: Any) -> Path:
    p = Path(gpkg_path)
    return p.with_name(p.stem + _CACHE_SUFFIXE)


def _signature_fichier(path: Path) -> Dict[str, Any]:
    try:
        st = path.stat()
        return {"taille": st.st_size, "mtime": st.st_mtime}
    except OSError:
        return {}


def conventions_par_defaut() -> Dict[str, Any]:
    return {
        "version": 1,
        "alias_noyau": {"actif": False, "max_dist_m": ALIAS_AUTO_MAX_DIST_M, "occurrences": 0},
        "snap_tolerance_m": SNAP_TOLERANCE_BASE_M,
        "statistiques": {},
        "decouvert_le": None,
    }


def charger_conventions(gpkg_path: Any) -> Optional[Dict[str, Any]]:
    """Charge les conventions persistées si le cache est valide pour ce fichier."""
    cache = chemin_cache_conventions(gpkg_path)
    if not cache.exists():
        return None
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
    except Exception:
        return None
    sig = _signature_fichier(Path(gpkg_path))
    conv = data.get("conventions") or {}
    file_sig = data.get("fichier") or {}
    if (sig and file_sig.get("taille") == sig.get("taille")
            and abs(float(file_sig.get("mtime", -1)) - sig.get("mtime", 0)) < 2.0):
        return conv
    return None


def _enregistrer_conventions(gpkg_path: Any, conventions: Dict[str, Any]) -> None:
    cache = chemin_cache_conventions(gpkg_path)
    try:
        payload = {
            "fichier": _signature_fichier(Path(gpkg_path)),
            "conventions": conventions,
        }
        cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    except Exception as e:
        logger.warning("[conventions] Persistance impossible (%s) : %s", cache, e)


# ---------------------------------------------------------------------------
# Découverte depuis un GeoPackage (index de nœuds + extrémités complets)
# ---------------------------------------------------------------------------

def _index_noeuds_depuis_gpkg(gpkg_path: Path) -> Tuple[Dict[str, Tuple[float, float]], Any]:
    """Construit l'index {nid: (x,y)} en CRS métrique depuis les couches de nœuds."""
    import geopandas as gpd
    from src.infrastructure.config import TARGET_CRS

    layers = gpd.list_layers(str(gpkg_path))["name"].tolist()

    def _couche(mots: List[str], exclusions: Optional[List[str]] = None) -> Optional[str]:
        exclusions = exclusions or []
        for nom in layers:
            bas = nom.lower()
            if any(e in bas for e in exclusions):
                continue
            if any(m in bas for m in mots):
                return nom
        return None

    noeuds: Dict[str, Tuple[float, float]] = {}

    def _ajouter(gdf: Any):
        if gdf is None or gdf.empty:
            return
        try:
            if gdf.crs is not None and gdf.crs.is_geographic:
                gdf = gdf.to_crs(TARGET_CRS)
        except Exception:
            pass
        for _, r in gdf.iterrows():
            nid = _clean_node_id(
                r.get("Code") or r.get("CODE") or r.get("id") or r.get("ID")
                or r.get("swmm_id") or r.get("SWMM_ID") or r.get("NOM") or r.get("nom"))
            if not nid or nid in noeuds:
                continue
            geom = getattr(r, "geometry", None)
            try:
                pt = geom if geom is not None and geom.geom_type == "Point" else (
                    geom.centroid if geom is not None and not geom.is_empty else None)
                if pt is not None:
                    noeuds[nid] = (float(pt.x), float(pt.y))
            except Exception:
                continue

    for mots in (["regard"], ["rejet", "outfall", "exutoire"],
                 ["station", "pompage", "relevage"], ["step", "epuration"],
                 ["ouvrage"]):
        lyr = _couche(mots)
        if lyr:
            try:
                _ajouter(gpd.read_file(str(gpkg_path), layer=lyr))
            except Exception:
                continue
    return noeuds, layers


def _extremites_conduites(gdf: Any) -> List[Tuple[str, Optional[Tuple[float, float]]]]:
    """Extrait (id_amont, pt) + (id_aval, pt) de chaque conduit."""
    out: List[Tuple[str, Optional[Tuple[float, float]]]] = []
    for _, c in gdf.iterrows():
        geom = getattr(c, "geometry", None)
        pts: List[Tuple[float, float]] = []
        try:
            if geom is not None and not geom.is_empty:
                if geom.geom_type == "LineString":
                    coords = list(geom.coords)
                    if coords:
                        pts = [(float(coords[0][0]), float(coords[0][1])),
                               (float(coords[-1][0]), float(coords[-1][1]))]
                elif geom.geom_type == "MultiLineString" and geom.geoms:
                    g0 = max(geom.geoms, key=lambda s: s.length)
                    coords = list(g0.coords)
                    if coords:
                        pts = [(float(coords[0][0]), float(coords[0][1])),
                               (float(coords[-1][0]), float(coords[-1][1]))]
        except Exception:
            pts = []
        for col, pt in (("ID_AMONT", pts[0] if len(pts) > 0 else None),
                        ("ID_AVAL", pts[1] if len(pts) > 1 else None)):
            nid = _clean_node_id(c.get(col) or c.get(col.lower())
                                 or c.get(col.title()) or c.get("amont" if col == "ID_AMONT" else "aval"))
            out.append((nid, pt))
    return out


def _decouvrir_depuis_gpkg(gpkg_path: Path) -> Dict[str, Any]:
    """Découverte complète : index de nœuds + extrémités -> conventions."""
    import geopandas as gpd

    noeuds, layers = _index_noeuds_depuis_gpkg(gpkg_path)
    if not noeuds:
        return conventions_par_defaut()

    def _couche(mots: List[str], exclusions: Optional[List[str]] = None) -> Optional[str]:
        exclusions = exclusions or []
        for nom in layers:
            bas = nom.lower()
            if any(e in bas for e in exclusions):
                continue
            if any(m in bas for m in mots):
                return nom
        return None

    lyr_cana = _couche(["canalisat", "conduit", "pipe", "troncon"],
                       ["désaffect", "desaffect"])
    if not lyr_cana:
        return conventions_par_defaut()
    try:
        cana = gpd.read_file(str(gpkg_path), layer=lyr_cana)
    except Exception:
        return conventions_par_defaut()

    # CRS métrique pour les extrémités (cohérent avec l'index de nœuds)
    try:
        if cana.crs is not None and cana.crs.is_geographic:
            from src.infrastructure.config import TARGET_CRS
            cana = cana.to_crs(TARGET_CRS)
    except Exception:
        pass

    extremites = _extremites_conduites(cana)

    # Résolution de base (ID + alias codé en dur + snap 0,50 m) pour isoler
    # les vrais échecs — même chaîne que les consommateurs.
    from src.domain.topologie import ResoluteurNoeuds
    base = ResoluteurNoeuds(noeuds, tolerance_snap_m=SNAP_TOLERANCE_BASE_M)
    echecs: List[Tuple[str, Optional[Tuple[float, float]]]] = []
    for nid, pt in extremites:
        res = base.resoudre(nid, pt)
        if not res.resolu:
            echecs.append((nid, pt))

    return decouvrir_conventions(noeuds, echecs)


def obtenir_conventions(gpkg_path: Any) -> Dict[str, Any]:
    """
    Point d'entrée unique : retourne les conventions du GeoPackage,
    depuis le cache si valide, sinon les découvre et les persiste.
    Ne lève jamais d'exception (repli sur les défauts).
    """
    try:
        cached = charger_conventions(gpkg_path)
        if cached:
            return cached
        conv = _decouvrir_depuis_gpkg(Path(gpkg_path))
        _enregistrer_conventions(gpkg_path, conv)
        return conv
    except Exception as e:
        logger.warning("[conventions] Découverte impossible pour %s : %s",
                       gpkg_path, e)
        return conventions_par_defaut()
