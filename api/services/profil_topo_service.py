"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-24
Date de modification : 2026-11-24
Objet : Chargement topo GPKG mutualisé (graphe + index regards) pour le profil
        en long hydraulique et la recherche d'éléments réseau — cache LRU
================================================================================
"""

import threading
from pathlib import Path
from typing import Any, Dict


# ---------------------------------------------------------------------------
# Cache mémoire « graphe + index regards » pour le profil en long.
#
# Sans cache, chaque appel à /profil-en-long reconstruisait le graphe
# topologique complet depuis le GPKG (~10 s pour 10k nœuds) — plus lent que
# la sectorisation des 122 bassins. Les GPKG du cache sont immuables
# (nom = SHA-256) : la clé inclut néanmoins mtime+taille par sécurité.
# Le graphe retourné est une copie indépendante (G.copy()) : l'endpoint
# peut ajouter des arêtes en repli sans polluer le cache.
# ---------------------------------------------------------------------------
_PROFIL_TOPO_CACHE: Dict[str, Dict[str, Any]] = {}
_PROFIL_TOPO_CACHE_LOCK = threading.Lock()
_PROFIL_TOPO_CACHE_MAX = 3


def _col_val_profil(r, name):
    """Extrait une cote numérique > 0 d'une ligne GeoDataFrame (ou None)."""
    import pandas as pd
    if name not in r or r[name] is None or pd.isna(r[name]):
        return None
    try:
        v = float(r[name])
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _index_regards_profil(regards) -> Dict[str, Dict[str, Any]]:
    """Construit l'index Code → attributs/position des regards (lecture seule)."""
    from src.domain.moteur_swmm.constants import _clean_node_id
    node_index: Dict[str, Any] = {}
    for _, r in regards.iterrows():
        nid = _clean_node_id(r.get("Code"), fallback=str(r.name))
        if nid:
            prof = _col_val_profil(r, "Profondeur")
            cotetn = _col_val_profil(r, "COTETN")
            cottn = _col_val_profil(r, "COTTN")
            coordz = _col_val_profil(r, "COORDZ")
            cotrad = _col_val_profil(r, "COTRAD")
            # Cote terrain vérifiée : première source altimétrique réelle.
            terrain_val, terrain_src = None, "absent"
            for cand, src in ((cotetn, "COTETN"), (cottn, "COTTN"), (coordz, "COORDZ")):
                if cand is not None:
                    terrain_val, terrain_src = cand, src
                    break
            node_index[nid] = {
                "code": nid,
                "x": r.geometry.x if r.geometry else 0.0,
                "y": r.geometry.y if r.geometry else 0.0,
                "profondeur": prof,
                "cotetn": terrain_val,
                "cotrad": cotrad,
                "terrain_reel": terrain_val is not None,
                "terrain_source": terrain_src,
            }
    return node_index


def _charger_topo_pour_profil(gpkg_path: Path) -> Dict[str, Any]:
    """
    Retourne {node_index, G (copie), canalisations} pour un GPKG donné.
    Construit une fois par version de GPKG (~10 s) puis sert depuis le cache.
    """
    try:
        st = gpkg_path.stat()
        cle = f"{gpkg_path}|{st.st_mtime_ns}|{st.st_size}"
    except OSError:
        cle = str(gpkg_path)

    with _PROFIL_TOPO_CACHE_LOCK:
        entree = _PROFIL_TOPO_CACHE.get(cle)
    if entree is not None:
        return {
            "node_index": entree["node_index"],
            "G": entree["G"].copy(),
            "canalisations": entree["canalisations"],
            "gpkg_sha": entree.get("gpkg_sha"),
            "crs": entree.get("crs"),
        }

    import hashlib
    try:
        _h = hashlib.sha256()
        with open(gpkg_path, "rb") as _fh:
            for _bloc in iter(lambda: _fh.read(1 << 20), b""):
                _h.update(_bloc)
        gpkg_sha = _h.hexdigest()
    except OSError:
        gpkg_sha = None

    import geopandas as gpd
    from src.domain.graphe_reseau import construire_graphe

    layers = gpd.list_layers(str(gpkg_path))["name"].tolist()
    regard_layer = next((l for l in layers if "regard" in l.lower()), "regards")
    pipe_layer = next((l for l in layers if any(k in l.lower() for k in ["canalisat", "conduit", "pipe", "troncon"]) and "désaffect" not in l.lower() and "desaffect" not in l.lower()), "canalisations")

    regards = gpd.read_file(str(gpkg_path), layer=regard_layer)
    canalisations = gpd.read_file(str(gpkg_path), layer=pipe_layer)
    node_index = _index_regards_profil(regards)
    G = construire_graphe(str(gpkg_path))

    with _PROFIL_TOPO_CACHE_LOCK:
        if len(_PROFIL_TOPO_CACHE) >= _PROFIL_TOPO_CACHE_MAX:
            _PROFIL_TOPO_CACHE.pop(next(iter(_PROFIL_TOPO_CACHE)))
        _PROFIL_TOPO_CACHE[cle] = {
            "node_index": node_index,
            "G": G,
            "canalisations": canalisations,
            "gpkg_sha": gpkg_sha,
            "crs": str(regards.crs) if getattr(regards, "crs", None) else None,
        }

    return {
        "node_index": node_index,
        "G": G.copy(),
        "canalisations": canalisations,
        "gpkg_sha": gpkg_sha,
        "crs": str(regards.crs) if getattr(regards, "crs", None) else None,
    }
