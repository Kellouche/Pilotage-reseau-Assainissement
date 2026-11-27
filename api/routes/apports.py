# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : LOT P1.2 — API CRUD des apports de temps sec (DWF)

Isolation stricte org/projet (stealth 404), validation des nœuds contre le
GPKG versionné du projet, aucune émission INP (lot P1.3).
================================================================================
"""

import logging
from pathlib import Path
from typing import Optional, Set, Any, List, Dict

import geopandas as gpd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import ApportDwf, ApportDwfHistory, Project
from api.core.security import TenantContext, get_tenant_context, require_role
from api.schemas import (
    ApportDwfCreate, ApportDwfUpdate, ApportDwfResponse, ProfilDwfInfo,
    ApportDwfHistoryResponse, ApportDwfHistoryPage,
)
from api.services.apports_dwf_history_service import (
    enregistrer_historique_apport,
    lister_historique_apport,
)
from api.services.apports_dwf_service import generer_code_apport
from api.services.simulation_service import (
    _resoudre_projet_pour_simulation,
    resoudre_gpkg_effectif_pour_projet,
    resoudre_gpkg_effectif_pour_projet_avec_meta,
    ContexteSimulationIntrouvable,
    ProjetAmbigu,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/apports", tags=["Apports de temps sec (DWF)"])


# ---------------------------------------------------------------------------
# Résolution projet (mêmes règles strictes que P0.1 : jamais de .first()
# arbitraire, cross-org → stealth 404, multi-projets → 409)
# ---------------------------------------------------------------------------

def _resoudre_projet(db: Session, tenant: TenantContext,
                     project_id: Optional[str]) -> Project:
    try:
        return _resoudre_projet_pour_simulation(db, tenant.org_id, project_id)
    except ProjetAmbigu as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContexteSimulationIntrouvable:
        raise HTTPException(
            status_code=404, detail="Projet introuvable ou non autorisé.")


def _apport_scoped(db: Session, tenant: TenantContext, apport_id: str) -> ApportDwf:
    """Charge un apport strictement dans le périmètre org du tenant (stealth 404)."""
    apport = db.get(ApportDwf, apport_id)
    if apport is None or apport.org_id != tenant.org_id:
        raise HTTPException(status_code=404, detail="Apport introuvable.")
    return apport


# ---------------------------------------------------------------------------
# Validation des nœuds contre le GPKG versionné du projet
# ---------------------------------------------------------------------------

def _contexte_noeuds(db: Session, proj: Project):
    """
    LOT P1.4 — résout (noeuds_valides, gpkg_path, version_meta) en une
    seule passe : le jeu de nœuds et l'estampillage (version_id + sha256)
    proviennent TOUJOURS de la même version du GPKG.
    """
    gpkg_path, version_meta = resoudre_gpkg_effectif_pour_projet_avec_meta(db, proj)
    if gpkg_path is None or not Path(gpkg_path).exists():
        raise HTTPException(
            status_code=422,
            detail="Réseau GeoPackage indisponible pour ce projet : "
                   "la validation des nœuds est impossible.")
    try:
        layers = gpd.list_layers(str(gpkg_path))["name"].tolist()
        regard_layer = next(
            (l for l in layers if "regard" in l.lower()), None)
        if not regard_layer:
            raise HTTPException(
                status_code=422,
                detail="Couche 'regards' absente du GeoPackage du projet.")
        regards = gpd.read_file(str(gpkg_path), layer=regard_layer,
                                columns=["Code"])
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Lecture GPKG impossible pour validation apports: %s", e)
        raise HTTPException(
            status_code=422,
            detail="GeoPackage du projet illisible : validation impossible.")

    from src.domain.moteur_swmm.constants import _clean_node_id
    noeuds = {_clean_node_id(c) for c in regards.get("Code", [])}
    noeuds.discard("")
    return noeuds, gpkg_path, version_meta


def _natural_sort_key(s: Any) -> list:
    import re
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(s))]


def _noeuds_connectes_gpkg(gpkg_path: Path) -> Set[str]:
    """Extrait l'ensemble des identifiants de nœuds connectés à au moins une canalisation."""
    from src.domain.moteur_swmm.constants import _clean_node_id
    try:
        layers = gpd.list_layers(str(gpkg_path))["name"].tolist()
        canal_layer = next((l for l in layers if any(k in l.lower() for k in ("canal", "troncon", "pipe"))), None)
        if not canal_layer:
            return set()
        gdf_c = gpd.read_file(str(gpkg_path), layer=canal_layer)
        connectes = set()
        for col in ("ID_AMONT", "ID_AVAL", "amont", "aval", "id_amont", "id_aval", "u", "d", "U", "D"):
            if col in gdf_c.columns:
                for val in gdf_c[col].dropna():
                    clean = _clean_node_id(val)
                    if clean:
                        connectes.add(clean)
        return connectes
    except Exception as e:
        logger.warning("Extraction des nœuds connectés impossible: %s", e)
        return set()


def _noeuds_cluster_gpkg(gpkg_path: Path, cluster_id: str) -> Set[str]:
    """
    Résout l'ensemble EXACT des nœuds amont drainant vers l'exutoire d'un cluster
    (cohérence stricte avec extraire_sous_reseau_bassin du moteur SWMM).
    """
    if not cluster_id or not str(cluster_id).strip():
        return set()
    cid = str(cluster_id).strip()
    try:
        import sqlite3
        from api.routes.clusters import _get_graph
        from src.domain.moteur_swmm.constants import _clean_node_id
        from src.domain.moteur_swmm.filtrage_bassin import _EXUTOIRES_MAP_CACHE
        from src.domain.detecteur_clusters import trouver_exutoires_physiques

        G = _get_graph(str(gpkg_path))
        cache_key = str(gpkg_path)
        exutoires_map = _EXUTOIRES_MAP_CACHE.get(cache_key)
        if not exutoires_map:
            exutoires_map = trouver_exutoires_physiques(G, inclure_exutoires_implicites=True)
            _EXUTOIRES_MAP_CACHE[cache_key] = exutoires_map

        target = None
        cid_int = None
        try:
            cid_int = int(cid)
        except ValueError:
            pass

        # 1. Résolution via .clusters_cache.json (source canonique des cluster_id UI)
        cache_file = Path(gpkg_path).with_suffix(".clusters_cache.json")
        if cache_file.exists():
            try:
                import json
                with open(cache_file, "r", encoding="utf-8") as fc:
                    cdata = json.load(fc)
                feats = cdata.get("bassins_geojson", {}).get("features", [])
                matched_fp = None
                for f in feats:
                    fp = f.get("properties", {})
                    fnom = str(fp.get("nom", "")).strip()
                    fcid = fp.get("cluster_id")
                    if fnom.lower() == cid.lower() or (cid_int is not None and fcid == cid_int) or fnom.lower().startswith(f"{cid.lower()}_"):
                        matched_fp = fp
                        break
                if matched_fp:
                    for cand in (matched_fp.get("exutoire_id"), matched_fp.get("regard_proche_id"), matched_fp.get("nom_exutoire"), matched_fp.get("nom")):
                        if not cand:
                            continue
                        cand_str = str(cand).strip()
                        if cand_str in exutoires_map or G.has_node(cand_str):
                            target = cand_str
                            break
                        if cand_str.endswith(".0") and G.has_node(cand_str[:-2]):
                            target = cand_str[:-2]
                            break
                        if G.has_node(f"{cand_str}.0"):
                            target = f"{cand_str}.0"
                            break
            except Exception:
                pass

        # 1bis. Résolution via la table de métadonnées bassins_versants_79 du GPKG
        if not target:
            try:
                con_meta = sqlite3.connect(str(gpkg_path))
                cur_meta = con_meta.cursor()
                cur_meta.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bassins_versants_79'")
                if cur_meta.fetchone():
                    row_b = None
                    if cid_int is not None:
                        cur_meta.execute("SELECT exutoire_id FROM bassins_versants_79 WHERE id_bassin = ? LIMIT 1", (cid_int,))
                        row_b = cur_meta.fetchone()
                    if not row_b:
                        cur_meta.execute("SELECT exutoire_id FROM bassins_versants_79 WHERE LOWER(nom_exutoire) = LOWER(?) OR exutoire_id = ? LIMIT 1", (cid, cid))
                        row_b = cur_meta.fetchone()
                    if row_b and row_b[0]:
                        cand = str(row_b[0]).strip()
                        if G.has_node(cand):
                            target = cand
                        elif cand.endswith(".0") and G.has_node(cand[:-2]):
                            target = cand[:-2]
                        elif G.has_node(f"{cand}.0"):
                            target = f"{cand}.0"
                con_meta.close()
            except Exception:
                pass

        # 2. Résolution via exutoires_map (exacte ou index positionnel 1-based)
        if not target:
            if cid in exutoires_map:
                target = cid
            else:
                for ex_k, ex_v in exutoires_map.items():
                    if str(ex_v.get("nom", "")).strip().lower() == cid.lower() or str(ex_k).strip().lower() == cid.lower():
                        target = ex_k
                        break
        ex_list = list(exutoires_map.items())
        if not target and cid_int is not None and 1 <= cid_int <= len(ex_list):
            target = ex_list[cid_int - 1][0]

        # 3. Fallback si cid est directement un ID de nœud dans G
        if not target:
            if G.has_node(cid):
                target = cid
            elif cid.startswith("OUT_") and G.has_node(cid[4:]):
                target = cid[4:]
            elif G.has_node(f"OUT_{cid}"):
                target = f"OUT_{cid}"

        if not target or not G.has_node(target):
            return set()

        # 4. Parcours amont borné aux frontières d'exutoires (identique à filtrage_bassin.py)
        ex_set = set(exutoires_map.keys())
        ex_set_frontiere = {
            e for e in ex_set
            if not (G.has_node(e) and G.in_degree(e) == 0 and G.out_degree(e) > 0)
        }
        ex_info = exutoires_map.get(target, {})
        regard_proche = ex_info.get("regard_proche_id")
        est_deporte = bool(ex_info.get("est_deporte", False))

        target_nodes = {target}
        queue = [target]
        if regard_proche and G.has_node(regard_proche) and (est_deporte or G.in_degree(target) == 0):
            target_nodes.add(regard_proche)
            queue.append(regard_proche)

        while queue:
            curr = queue.pop(0)
            for pred in G.predecessors(curr):
                if pred not in ex_set_frontiere and pred not in target_nodes:
                    target_nodes.add(pred)
                    queue.append(pred)

        clean_nodes = {_clean_node_id(x) for x in target_nodes}
        clean_nodes.add(_clean_node_id(target))
        if est_deporte and regard_proche:
            clean_nodes.add(_clean_node_id(regard_proche))
        return clean_nodes
    except Exception as e:
        logger.warning("Résolution des nœuds du cluster %s impossible: %s", cluster_id, e)
    return set()


def _noeuds_valides_projet(db: Session, proj: Project) -> Set[str]:
    """Ensemble des identifiants de nœuds valides du GPKG effectif du projet."""
    return _contexte_noeuds(db, proj)[0]


def _filtre_snapshot_apports(db: Session, proj: Project, snapshot: Optional[str]):
    """
    Retourne (version_id, sha256) du snapshot demandé, ou (None, None) si
    `snapshot` est absent (comportement historique : tous les apports du
    projet). Snapshot explicite introuvable -> GpkgSimulationError.
    """
    if not snapshot or not str(snapshot).strip():
        return None, None
    from api.services.gpkg_versions import (
        resoudre_snapshot_pour_lecture, GpkgSimulationError)
    try:
        ctx = resoudre_snapshot_pour_lecture(db, proj, snapshot)
    except GpkgSimulationError as e:
        raise HTTPException(status_code=404, detail="Ressource introuvable") from e
    return ctx.get("version_id"), ctx.get("sha256")


def _valider_noeud(db: Session, proj: Project, node_id: str) -> str:
    """Normalise et valide node_id contre le GPKG du projet. Retourne l'id canonique."""
    from src.domain.moteur_swmm.constants import _clean_node_id
    nid = _clean_node_id(node_id)
    if not nid:
        raise HTTPException(status_code=422, detail="Identifiant de nœud invalide.")
    noeuds, gpkg_path, _ = _contexte_noeuds(db, proj)
    if nid not in noeuds:
        raise HTTPException(
            status_code=422,
            detail=f"Nœud '{nid}' inexistant dans le réseau du projet.")
    connectes = _noeuds_connectes_gpkg(gpkg_path)
    if connectes and nid not in connectes:
        raise HTTPException(
            status_code=422,
            detail=(f"Le regard '{nid}' existe dans le fichier SIG mais n'est raccordé "
                    f"à aucune canalisation du réseau hydraulique (regard orphelin). "
                    f"Veuillez sélectionner un regard connecté au réseau pour y injecter un débit."))
    return nid


def _valider_noeud_et_version(db: Session, proj: Project, node_id: str):
    """
    LOT P1.4 — valide le nœud ET retourne l'estampillage (version_id,
    sha256) de la version exacte du GPKG qui l'a validé. Les deux
    proviennent de la même lecture : impossible de valider sur V1 et
    estampiller V2.
    """
    from src.domain.moteur_swmm.constants import _clean_node_id
    nid = _clean_node_id(node_id)
    if not nid:
        raise HTTPException(status_code=422, detail="Identifiant de nœud invalide.")
    noeuds, gpkg_path, version_meta = _contexte_noeuds(db, proj)
    if nid not in noeuds:
        raise HTTPException(
            status_code=422,
            detail=f"Nœud '{nid}' inexistant dans le réseau du projet.")
    connectes = _noeuds_connectes_gpkg(gpkg_path)
    if connectes and nid not in connectes:
        raise HTTPException(
            status_code=422,
            detail=(f"Le regard '{nid}' existe dans le fichier SIG mais n'est raccordé "
                    f"à aucune canalisation du réseau hydraulique (regard orphelin). "
                    f"Veuillez sélectionner un regard connecté au réseau pour y injecter un débit."))
    return nid, version_meta


# ---------------------------------------------------------------------------
# Profils temporels prédéfinis
# ---------------------------------------------------------------------------
