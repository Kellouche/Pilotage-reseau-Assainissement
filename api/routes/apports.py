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

@router.get("/profils", response_model=list[ProfilDwfInfo])
def lister_profils_dwf(tenant: TenantContext = Depends(get_tenant_context)):
    """Liste les profils temporels DWF prédéfinis (compatibles SWMM [PATTERNS])."""
    from src.domain.apports_dwf import lister_profils_dwf as _lister
    return _lister()


# ---------------------------------------------------------------------------
# CRUD apports
# ---------------------------------------------------------------------------

@router.get("", response_model=list[ApportDwfResponse])
def lister_apports(
    project_id: Optional[str] = Query(None),
    node_id: Optional[str] = Query(None),
    cluster_id: Optional[str] = Query(None),
    actif_seulement: bool = Query(False),
    snapshot: Optional[str] = Query(None),
    reseau_courant_seulement: bool = Query(False),
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Liste les apports DWF du projet (bornés à l'organisation du tenant).
    `cluster_id` (optionnel) : ne retourne que les apports situés sur les
    nœuds appartenant au bassin versant sélectionné.
    """
    proj = _resoudre_projet(db, tenant, project_id)
    snap_vid, snap_sha = _filtre_snapshot_apports(db, proj, snapshot)
    q = db.query(ApportDwf).filter(
        ApportDwf.org_id == tenant.org_id,
        ApportDwf.project_id == proj.id)
    if snap_vid or snap_sha:
        from sqlalchemy import or_
        clauses = []
        if snap_vid:
            clauses.append(ApportDwf.gpkg_version_id == snap_vid)
        if snap_sha:
            clauses.append(ApportDwf.gpkg_sha256 == snap_sha)
        q = q.filter(or_(*clauses))
    elif reseau_courant_seulement and proj.gpkg_version_id:
        q = q.filter(ApportDwf.gpkg_version_id == proj.gpkg_version_id)
    if node_id:
        from src.domain.moteur_swmm.constants import _clean_node_id
        q = q.filter(ApportDwf.node_id == _clean_node_id(node_id))
    if actif_seulement:
        q = q.filter(ApportDwf.actif.is_(True))

    rows = [a.to_dict() for a in q.order_by(ApportDwf.created_at).all()]
    if cluster_id and str(cluster_id).strip().lower() not in ("", "tous", "all", "null", "undefined"):
        gpkg_path, _ = resoudre_gpkg_effectif_pour_projet_avec_meta(db, proj)
        if gpkg_path and Path(gpkg_path).exists():
            c_nodes = _noeuds_cluster_gpkg(Path(gpkg_path), str(cluster_id))
            if c_nodes:
                rows = [
                    r for r in rows
                    if str(r.get("node_id") or "").strip() in c_nodes
                    or str(r.get("node_id") or "").strip().removesuffix(".0") in c_nodes
                ]
            else:
                rows = []
    return rows


@router.get("/noeuds")
def lister_noeuds_disponibles(
    project_id: Optional[str] = Query(None),
    snapshot: Optional[str] = Query(None),
    cluster_id: Optional[str] = Query(None),
    connectes_seulement: bool = Query(True),
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Liste les identifiants de nœuds valides du GPKG du projet (aide à la saisie intelligente).

    - `connectes_seulement` (défaut True) : ne propose que les regards
      raccordés à au moins une canalisation (exclut les regards isolés / orphelins).
    - `cluster_id` : si spécifié, filtre exclusivement les regards appartenant
      au bassin versant sélectionné.
    - `snapshot` : lit les nœuds du snapshot demandé au lieu de la version courante.
    """
    proj = _resoudre_projet(db, tenant, project_id)
    if snapshot and str(snapshot).strip():
        from api.services.gpkg_versions import (
            resoudre_snapshot_pour_lecture, GpkgSimulationError)
        try:
            snap_ctx = resoudre_snapshot_pour_lecture(db, proj, snapshot)
        except GpkgSimulationError:
            raise HTTPException(status_code=404, detail="Ressource introuvable")
        gpkg_path = Path(snap_ctx["path"])
        layers = gpd.list_layers(str(gpkg_path))["name"].tolist()
        regard_layer = next((l for l in layers if "regard" in l.lower()), None)
        if not regard_layer:
            raise HTTPException(status_code=422, detail="Couche 'regards' absente du snapshot.")
        regards = gpd.read_file(str(gpkg_path), layer=regard_layer, columns=["Code"])
        from src.domain.moteur_swmm.constants import _clean_node_id
        tous_noeuds = {_clean_node_id(c) for c in regards.get("Code", [])} - {""}
        connectes = _noeuds_connectes_gpkg(gpkg_path)
        selection = (tous_noeuds & connectes) if (connectes_seulement and connectes) else set(tous_noeuds)
        if cluster_id:
            c_nodes = _noeuds_cluster_gpkg(gpkg_path, cluster_id)
            if c_nodes:
                selection = selection & c_nodes
        noeuds = sorted(list(selection), key=_natural_sort_key)
        return {
            "project_id": proj.id,
            "cluster_id": cluster_id,
            "noeuds": noeuds,
            "count": len(noeuds),
            "total_regards": len(tous_noeuds),
            "nb_connectes": len(tous_noeuds & connectes) if connectes else len(tous_noeuds),
            "snapshot_sha256": snap_ctx.get("sha256"),
        }

    tous_noeuds, gpkg_path, version_meta = _contexte_noeuds(db, proj)
    connectes = _noeuds_connectes_gpkg(gpkg_path)
    selection = (tous_noeuds & connectes) if (connectes_seulement and connectes) else set(tous_noeuds)
    if cluster_id:
        c_nodes = _noeuds_cluster_gpkg(gpkg_path, cluster_id)
        if c_nodes:
            selection = selection & c_nodes
    noeuds = sorted(list(selection), key=_natural_sort_key)
    return {
        "project_id": proj.id,
        "cluster_id": cluster_id,
        "noeuds": noeuds,
        "count": len(noeuds),
        "total_regards": len(tous_noeuds),
        "nb_connectes": len(tous_noeuds & connectes) if connectes else len(tous_noeuds),
        "nb_orphelins": len(tous_noeuds - connectes) if connectes else 0,
    }


@router.get("/a-reconcilier")
def lister_apports_a_reconcilier(
    project_id: Optional[str] = Query(None),
    cluster_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    LOT P1.5.1 — inventaire EXHAUSTIF des apports actifs non admissibles à
    la simulation : tout apport actif dont l'estampillage diffère de la
    version GPKG courante (version_id et/ou sha256), sans estampillage
    (historique non réconcilié) ou sur un nœud absent du réseau courant.

    Strictement en lecture seule : aucun ré-estampillage, aucune
    réconciliation automatique — la seule voie reste
    POST /apports/{id}/revalider. Les apports INACTIFS ne bloquent pas la
    simulation et ne figurent pas dans cette liste (visibles via GET /).

    Contrat :
      - project_id, count : inchangés (count = nb d'apports incompatibles) ;
      - apports : ApportDwfResponse des apports incompatibles ;
      - incompatibles : détail par apport (code motif stable, estampillage
        de l'apport, version/sha du réseau courant, action attendue) ;
      - reseau_courant : version_id / sha256 / storage_kind résolus ;
      - erreur : renseigné si le GPKG courant ne peut pas être résolu —
        dans ce cas TOUS les apports actifs sont signalés
        'gpkg_courant_indisponible' (la simulation échouerait en amont,
        avant même la validation DWF).
    """
    proj = _resoudre_projet(db, tenant, project_id)
    apports = [a.to_dict() for a in db.query(ApportDwf).filter(
        ApportDwf.org_id == tenant.org_id,
        ApportDwf.project_id == proj.id,
        ApportDwf.actif.is_(True),
    ).order_by(ApportDwf.created_at).all()]

    gpkg_path, version_meta = resoudre_gpkg_effectif_pour_projet_avec_meta(
        db, proj)
    version_meta = version_meta or {}
    gpkg_path = Path(gpkg_path) if gpkg_path else None
    reseau_disponible = (
        gpkg_path is not None and gpkg_path.exists())

    if reseau_disponible and cluster_id and str(cluster_id).strip().lower() not in ("", "tous", "all", "null", "undefined"):
        c_nodes = _noeuds_cluster_gpkg(gpkg_path, str(cluster_id))
        if c_nodes:
            apports = [
                a for a in apports
                if str(a.get("node_id") or "").strip() in c_nodes
                or str(a.get("node_id") or "").strip().removesuffix(".0") in c_nodes
            ]
        else:
            apports = []

    incompatibles: list = []
    if not apports:
        pass
    elif not reseau_disponible:
        # Réseau courant irrésolvable : aucune estampille ne peut être
        # vérifiée — chaque apport actif est signalé non vérifiable.
        for a in apports:
            incompatibles.append({
                "code": "gpkg_courant_indisponible",
                "apport_id": a.get("id"),
                "node_id": a.get("node_id"),
                "noeud_present": False,
                "apport_gpkg_version_id": a.get("gpkg_version_id"),
                "apport_gpkg_sha256": a.get("gpkg_sha256"),
                "simulation_gpkg_version_id": version_meta.get("version_id"),
                "simulation_gpkg_sha256": version_meta.get("sha256"),
                "simulation_storage_kind": version_meta.get("storage_kind"),
                "motif": ("réseau GPKG courant indisponible : estampillage "
                          "invérifiable"),
                "action_attendue": ("rendre le GeoPackage du projet accessible "
                                    "puis revalider l'apport"),
            })
    else:
        # Réutilisation STRICTE des règles de validation P1.4 — aucune
        # duplication : valider_apports_pour_version applique exactement
        # les mêmes contrôles (estampillage, version, sha, nœud du snapshot)
        # que preparer_apports_pour_simulation au lancement.
        from api.services.apports_dwf_service import (
            ApportsDwfIncompatiblesError,
            valider_apports_pour_version,
        )
        try:
            valider_apports_pour_version(apports, version_meta, gpkg_path)
        except ApportsDwfIncompatiblesError as e:
            incompatibles = e.details

    ids_incompatibles = {d.get("apport_id") for d in incompatibles}
    noeud_present_map = {d.get("apport_id"): d.get("noeud_present", False) for d in incompatibles}
    apports_enrichis = []
    for a in apports:
        aid = a.get("id")
        if aid in ids_incompatibles:
            a_copy = dict(a)
            a_copy["noeud_present"] = noeud_present_map.get(aid, False)
            apports_enrichis.append(a_copy)

    return {
        "project_id": proj.id,
        "apports": apports_enrichis,
        "incompatibles": incompatibles,
        "count": len(incompatibles),
        "reseau_courant": {
            "gpkg_version_id": version_meta.get("version_id"),
            "gpkg_sha256": version_meta.get("sha256"),
            "storage_kind": version_meta.get("storage_kind"),
            "disponible": reseau_disponible,
        },
        "erreur": (version_meta.get("erreur") if not reseau_disponible
                   else None),
    }


@router.post("", response_model=ApportDwfResponse, status_code=201)
def creer_apport(
    payload: ApportDwfCreate,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_role("engineer")),
):
    """Crée un apport de temps sec sur un nœud du projet."""
    proj = _resoudre_projet(db, tenant, payload.project_id)
    node_id, version_meta = _valider_noeud_et_version(db, proj, payload.node_id)

    code_apport = payload.code_apport
    if code_apport and code_apport.strip():
        code_apport = code_apport.strip()
        existant = db.query(ApportDwf).filter(
            ApportDwf.project_id == proj.id,
            ApportDwf.code_apport == code_apport,
        ).first()
        if existant:
            raise HTTPException(
                status_code=409,
                detail=f"Le code apport '{code_apport}' existe déjà pour ce projet."
            )
    else:
        code_apport = generer_code_apport(db, proj.id)

    apport = ApportDwf(
        org_id=tenant.org_id,
        project_id=proj.id,
        code_apport=code_apport,
        node_id=node_id,
        # LOT P1.4 — estampillage : version exacte du GPKG qui a validé
        # ce nœud (version_id NULL pour les projets legacy : sha seul).
        gpkg_version_id=version_meta.get("version_id"),
        gpkg_sha256=version_meta.get("sha256"),
        nature=payload.nature,
        mode_determination=payload.mode_determination,
        debit_moyen_m3s=(
            payload.debit_moyen_m3s if payload.mode_determination == "debit"
            else None),  # mode 'eh' : dérivé par _calculer_debit
        eh=payload.eh if payload.mode_determination == "eh" else None,
        debit_specifique_l_hab_j=(
            payload.debit_specifique_l_hab_j
            if payload.mode_determination == "eh" else None),
        profile_key=payload.profile_key,
        actif=payload.actif,
        source=payload.source,
        observations=payload.observations,
        created_by_id=getattr(getattr(tenant, "actor", None), "id", None),
    )
    _calculer_debit(apport)
    db.add(apport)
    db.flush()
    enregistrer_historique_apport(
        db=db,
        apport_id=apport.id,
        org_id=tenant.org_id,
        project_id=proj.id,
        action="create",
        changed_by_id=getattr(getattr(tenant, "actor", None), "id", None),
        changed_fields=None,
        previous_state=None,
        new_state=apport.to_dict(),
    )
    db.commit()
    db.refresh(apport)
    return apport.to_dict()


def _calculer_debit(apport: ApportDwf) -> None:
    """Calcule/actualise debit_moyen_m3s selon le mode de détermination."""
    from src.domain.apports_dwf import (
        DEBIT_SPECIFIQUE_DEFAUT_L_HAB_J, eh_vers_debit_m3s)
    if apport.mode_determination == "eh":
        if apport.debit_specifique_l_hab_j is None:
            apport.debit_specifique_l_hab_j = DEBIT_SPECIFIQUE_DEFAUT_L_HAB_J
        apport.debit_moyen_m3s = eh_vers_debit_m3s(
            apport.eh or 0.0, apport.debit_specifique_l_hab_j)
    # mode 'debit' : debit_moyen_m3s est porté par la saisie/validation


# ---------------------------------------------------------------------------
# Consultation de l'historique d'audit DWF (LOT P6.1)
# ---------------------------------------------------------------------------

@router.get("/history", response_model=ApportDwfHistoryPage)
def lister_historique_projet(
    project_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_role("viewer")),
):
    """
    LOT P6.1 — Consulte l'historique d'audit des apports DWF (paginé).
    Borné strictement à l'organisation du tenant, avec filtrage projet optionnel.
    """
    pid = None
    if project_id:
        proj = _resoudre_projet(db, tenant, project_id)
        pid = proj.id

    items, total = lister_historique_apport(
        db=db,
        org_id=tenant.org_id,
        project_id=pid,
        action=action,
        skip=skip,
        limit=limit,
    )
    return {
        "items": [h.to_dict() for h in items],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/{apport_id}/history", response_model=ApportDwfHistoryPage)
def lister_historique_unitaire(
    apport_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_role("viewer")),
):
    """
    LOT P6.1 — Consulte l'historique d'audit d'un apport DWF spécifique.
    Garantit un stealth 404 si l'apport n'appartient pas au tenant ou est introuvable.
    Conserve la traçabilité complète même après suppression de l'apport.
    """
    apport = db.get(ApportDwf, apport_id)
    if apport is not None and apport.org_id != tenant.org_id:
        raise HTTPException(status_code=404, detail="Apport introuvable.")

    items, total = lister_historique_apport(
        db=db,
        org_id=tenant.org_id,
        apport_id=apport_id,
        skip=skip,
        limit=limit,
    )
    if apport is None and total == 0:
        raise HTTPException(status_code=404, detail="Apport introuvable.")

    return {
        "items": [h.to_dict() for h in items],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/{apport_id}", response_model=ApportDwfResponse)
def lire_apport(
    apport_id: str,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    apport = _apport_scoped(db, tenant, apport_id)
    return apport.to_dict()


@router.put("/{apport_id}", response_model=ApportDwfResponse)
def modifier_apport(
    apport_id: str,
    payload: ApportDwfUpdate,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_role("engineer")),
):
    """Mise à jour partielle d'un apport (champs fournis uniquement)."""
    apport = _apport_scoped(db, tenant, apport_id)
    proj = db.get(Project, apport.project_id)
    previous_state = apport.to_dict()

    data = payload.model_dump(exclude_unset=True)

    nouveau_code = data.get("code_apport")
    if nouveau_code is not None:
        nouveau_code = nouveau_code.strip()
        if nouveau_code != (apport.code_apport or ""):
            existant = db.query(ApportDwf).filter(
                ApportDwf.project_id == apport.project_id,
                ApportDwf.code_apport == nouveau_code,
                ApportDwf.id != apport.id,
            ).first()
            if existant:
                raise HTTPException(
                    status_code=409,
                    detail=f"Le code apport '{nouveau_code}' existe déjà pour ce projet."
                )
        data["code_apport"] = nouveau_code

    nouveau_node = data.pop("node_id", None)
    changement_noeud = False
    if nouveau_node is not None and proj is not None and nouveau_node != apport.node_id:
        changement_noeud = True
        # LOT P1.4 — changer de nœud est une REVALIDATION : le nœud est
        # vérifié sur la version courante et l'estampillage est renouvelé.
        # Les autres modifications (débit, profil, nature…) ne touchent
        # JAMAIS l'estampillage.
        apport.node_id, version_meta = _valider_noeud_et_version(
            db, proj, nouveau_node)
        apport.gpkg_version_id = version_meta.get("version_id")
        apport.gpkg_sha256 = version_meta.get("sha256")
    elif nouveau_node is not None and proj is not None and nouveau_node == apport.node_id:
        # Nœud identique : validation éventuelle sans qualifier de node_change
        pass

    # Cohérence mode : si le mode passe à 'eh' sans eh fourni, on conserve
    # l'eh existant ; si 'debit', on purge les champs eh.
    mode = data.get("mode_determination", apport.mode_determination)
    for champ, valeur in data.items():
        setattr(apport, champ, valeur)
    apport.mode_determination = mode
    if apport.mode_determination == "eh":
        if apport.eh is None:
            raise HTTPException(
                status_code=422,
                detail="eh est requis lorsque mode_determination='eh'.")
    else:
        if apport.debit_moyen_m3s is None:
            raise HTTPException(
                status_code=422,
                detail="debit_moyen_m3s est requis lorsque mode_determination='debit'.")
        apport.eh = None
        apport.debit_specifique_l_hab_j = None

    _calculer_debit(apport)
    db.flush()
    new_state = apport.to_dict()

    changed_fields = [
        k for k, v in new_state.items()
        if k not in ("updated_at",) and previous_state.get(k) != v
    ]
    if changed_fields:
        # Qualification canonique de l'événement métier (P6.1)
        if changement_noeud:
            action = "node_change"
        elif previous_state.get("actif") is False and new_state.get("actif") is True:
            action = "activate"
        elif previous_state.get("actif") is True and new_state.get("actif") is False:
            action = "deactivate"
        else:
            action = "update"

        enregistrer_historique_apport(
            db=db,
            apport_id=apport.id,
            org_id=tenant.org_id,
            project_id=apport.project_id,
            action=action,
            changed_by_id=getattr(getattr(tenant, "actor", None), "id", None),
            changed_fields=changed_fields,
            previous_state=previous_state,
            new_state=new_state,
        )

    db.commit()
    db.refresh(apport)
    return apport.to_dict()


@router.post("/{apport_id}/revalider", response_model=ApportDwfResponse)
def revalider_apport(
    apport_id: str,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_role("engineer")),
):
    """
    LOT P1.4 — réconciliation explicite d'un apport sur la version
    COURANTE du GPKG du projet : le nœud est revérifié dans le snapshot
    (422 s'il a disparu) puis l'estampillage (gpkg_version_id /
    gpkg_sha256) est renouvelé. C'est la SEULE voie pour réestampiller
    un apport — les modifications de débit/profil/nature ne le font
    jamais automatiquement.
    """
    apport = _apport_scoped(db, tenant, apport_id)
    proj = db.get(Project, apport.project_id)
    if proj is None:
        raise HTTPException(status_code=404, detail="Projet introuvable.")
    previous_state = apport.to_dict()
    _nid, version_meta = _valider_noeud_et_version(db, proj, apport.node_id)
    apport.gpkg_version_id = version_meta.get("version_id")
    apport.gpkg_sha256 = version_meta.get("sha256")
    db.flush()
    new_state = apport.to_dict()
    changed_fields = [
        k for k in ("gpkg_version_id", "gpkg_sha256")
        if previous_state.get(k) != new_state.get(k)
    ]
    enregistrer_historique_apport(
        db=db,
        apport_id=apport.id,
        org_id=tenant.org_id,
        project_id=apport.project_id,
        action="reconcile",
        changed_by_id=getattr(getattr(tenant, "actor", None), "id", None),
        changed_fields=changed_fields or ["reconcile"],
        previous_state=previous_state,
        new_state=new_state,
    )
    db.commit()
    db.refresh(apport)
    return apport.to_dict()


@router.delete("/{apport_id}", status_code=204)
def supprimer_apport(
    apport_id: str,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_role("engineer")),
):
    """Suppression définitive d'un apport (aucune dépendance : INP non généré au P1.2)."""
    apport = _apport_scoped(db, tenant, apport_id)
    previous_state = apport.to_dict()
    enregistrer_historique_apport(
        db=db,
        apport_id=apport.id,
        org_id=tenant.org_id,
        project_id=apport.project_id,
        action="delete",
        changed_by_id=getattr(getattr(tenant, "actor", None), "id", None),
        changed_fields=None,
        previous_state=previous_state,
        new_state=None,
    )
    db.delete(apport)
    db.commit()
    return None


@router.post("/purger-orphelins")
def purger_apports_orphelins(
    project_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_role("engineer")),
):
    """
    Supprime les apports DWF obsolètes dont le regard n'existe plus
    dans la géométrie du réseau actif (noeud absent du GPKG courant).
    """
    proj = _resoudre_projet(db, tenant, project_id)
    noeuds_valides = _noeuds_valides_projet(db, proj)

    apports = db.query(ApportDwf).filter(
        ApportDwf.org_id == tenant.org_id,
        ApportDwf.project_id == proj.id,
    ).all()

    orphelins = [a for a in apports if a.node_id not in noeuds_valides]
    deleted_info = []
    actor_id = getattr(getattr(tenant, "actor", None), "id", None)

    for a in orphelins:
        prev = a.to_dict()
        deleted_info.append(prev)
        enregistrer_historique_apport(
            db=db,
            apport_id=a.id,
            org_id=tenant.org_id,
            project_id=a.project_id,
            action="delete",
            changed_by_id=actor_id,
            changed_fields=["purge_orphelin"],
            previous_state=prev,
            new_state=None,
        )
        db.delete(a)

    if orphelins:
        db.commit()

    return {
        "status": "success",
        "project_id": proj.id,
        "supprimes_count": len(deleted_info),
        "apports_supprimes": deleted_info,
    }

