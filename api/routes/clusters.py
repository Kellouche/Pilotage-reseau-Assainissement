"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-27
Objet : Endpoints de sectorisation, détection de bassins et sous-bassins
================================================================================
"""

import ast
import json
import logging
import math
import threading
import networkx as nx
from functools import lru_cache
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any

from api.database import get_db
from api import schemas, crud
from api.models import Project
from api.core.security import get_tenant_context, require_role, TenantContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clusters", tags=["Clusters"])

# Cache du graphe et état

_GRAPH_CACHES: Dict[str, nx.DiGraph] = {}
_GRAPH_STATUS = "pending"  # pending | building | ready | error


def _log_cluster(*args, **kwargs):
    """Affiche les logs d'analyse des clusters sauf si le mode silencieux est actif."""
    import os
    if os.getenv("DRAINPILOT_SILENT", "").lower() not in ("1", "true", "yes"):
        print(*args, **kwargs)


def _get_current_user_from_request(request: Request, db: Session):
    """Extrait l'utilisateur authentifié depuis le cookie ou l'en-tête Bearer."""
    if not request:
        return None
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
    if not token:
        return None
    try:
        from api.core.auth import decode_token
        from api.models import User
        payload = decode_token(token)
        if not payload or not payload.get("sub"):
            return None
        user = db.query(User).filter(User.id == payload["sub"], User.is_active.is_(True)).first()
        if not user or not user.email_verified:
            return None
        return user
    except Exception:
        return None


def _json_safe(value):
    """Convertit les valeurs pandas/NumPy non conformes JSON en valeurs sûres."""
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value

def _get_graph(chemin_gpkg: Optional[str] = None):
    """Get cached graph, building it once per GeoPackage content (SHA-256 + chemin)."""
    global _GRAPH_CACHES, _GRAPH_STATUS
    if chemin_gpkg:
        # Clé content-adressée : deux versions GPKG distinctes ne partagent
        # jamais le même graphe, même si le chemin source est réutilisé.
        try:
            from api.services.gpkg_versions import sha256_fichier
            empreinte = sha256_fichier(Path(chemin_gpkg))[:16]
            cache_key = f"{empreinte}|{chemin_gpkg}"
        except Exception:
            cache_key = str(chemin_gpkg)
    else:
        cache_key = "default"
    if cache_key not in _GRAPH_CACHES or _GRAPH_CACHES[cache_key] is None:
        _GRAPH_STATUS = "building"
        try:
            from src.domain.graphe_reseau import construire_graphe
            _log_cluster(f"[clusters] Building graph for {cache_key}...", flush=True)
            G = construire_graphe(chemin_gpkg)
            _GRAPH_CACHES[cache_key] = G
            _GRAPH_STATUS = "ready"
            _log_cluster(f"[clusters] Graph built and cached for {cache_key}.", flush=True)
        except Exception as e:
            _GRAPH_STATUS = "error"
            _log_cluster(f"[clusters] ERROR building graph: {e}", flush=True)
            raise
    return _GRAPH_CACHES[cache_key]

_CLUSTERS_CACHE = {}
_CLUSTERS_LOCK = threading.Lock()


def _get_clusters_disk_cache_path(chemin_gpkg: Optional[str]) -> Optional[Path]:
    if not chemin_gpkg:
        return None
    return Path(chemin_gpkg).with_suffix(".clusters_cache.json")


def _set_graph_status(value: str) -> None:
    """Mutateur du statut graphe — nécessaire car _GRAPH_STATUS est une
    chaîne réassignée : les modules consommateurs ne peuvent pas la
    partager par import (liaison figée à l'import)."""
    global _GRAPH_STATUS
    _GRAPH_STATUS = value


def _reset_graph_cache():
    """Reset the graph cache and clusters cache."""
    global _GRAPH_STATUS
    _GRAPH_CACHES.clear()
    _CLUSTERS_CACHE.clear()
    _set_graph_status("pending")

def get_graph_status():
    """Return current graph cache status."""
    return _GRAPH_STATUS


@router.get("", response_model=schemas.ClusterListResponse)
def list_clusters(
    skip: int = 0,
    limit: int = 100,
    ctx: TenantContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db)
):
    """Liste tous les clusters de l'organisation active."""
    clusters = crud.get_clusters(db=db, skip=skip, limit=limit, org_id=ctx.org_id)
    total = db.query(crud.Cluster).filter(crud.Cluster.org_id == ctx.org_id).count()
    return {"clusters": clusters, "total": total}


@router.get("/status")
def get_cluster_status(ctx: TenantContext = Depends(require_role("viewer"))):
    """Statut du cache du graphe."""
    return {"graph_cache": get_graph_status()}


@router.post("/graph/rebuild")
def rebuild_graph_cache(
    background_tasks: BackgroundTasks,
    ctx: TenantContext = Depends(require_role("admin"))
):
    """Reconstruit le cache du graphe (utile après modification des données)."""
    _reset_graph_cache()
    # Pré-chauffer le graphe en arrière-plan pour ne pas bloquer le client
    background_tasks.add_task(_warm_graph_cache)
    return {"status": "scheduled", "message": "Reconstruction du graphe programmée"}


@router.get("/recalculate-all", include_in_schema=False)
def recalculate_all_clusters_async_precedence(
    background_tasks: BackgroundTasks,
    ctx: TenantContext = Depends(require_role("admin"))
):
    """Schedule recalculation before the generic cluster-id route can match."""
    background_tasks.add_task(_calculate_clusters_background)
    return {"status": "scheduled"}


# ============================================================
# BASSINS MANUELS (CRÉATION / SUPPRESSION / LECTURE)
# Doit être déclaré avant /{cluster_id} pour éviter le piège de routing FastAPI
# ============================================================

@router.post("/manual-basin")
def save_cluster_manual_basin(
    data: Dict[str, Any],
    ctx: TenantContext = Depends(require_role("admin"))
):
    """Enregistre un bassin versant manuel tracé par l'utilisateur pour son organisation."""
    from src.infrastructure.persistance_manuelle import sauvegarder_bassin_manuel
    return sauvegarder_bassin_manuel(data, org_id=ctx.org_id)


@router.delete("/manual-basin/{bassin_id}")
def delete_cluster_manual_basin(
    bassin_id: str,
    ctx: TenantContext = Depends(require_role("admin"))
):
    """Supprime un bassin versant manuel (isolation stricte par organisation)."""
    from src.infrastructure.persistance_manuelle import supprimer_bassin_manuel
    res = supprimer_bassin_manuel(bassin_id, org_id=ctx.org_id)
    if not res:
        raise HTTPException(status_code=404, detail="Ressource introuvable")
    return {"status": "ok"}


@router.get("/manual-basin")
def get_cluster_manual_basins(ctx: TenantContext = Depends(require_role("admin"))):
    """Liste tous les bassins versants manuels enregistrés pour l'organisation courante."""
    from src.infrastructure.persistance_manuelle import charger_bassins_manuels
    return charger_bassins_manuels(org_id=ctx.org_id)


@router.get("/{cluster_id}", response_model=schemas.ClusterResponse)
def get_cluster(
    cluster_id: int,
    ctx: TenantContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db)
):
    """Détail d'un cluster (stealth 404 si hors organisation)."""
    cluster = crud.get_cluster(db, cluster_id, org_id=ctx.org_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Ressource introuvable")
    return cluster


@router.post("/recalculate-all")
def recalculate_all_clusters(
    request: Request,
    background_tasks: BackgroundTasks,
    ctx: TenantContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
    persist: bool = True,
    snapshot: Optional[str] = None
):
    """Reconstruit tous les clusters en bassins exclusifs (sans chevauchement) pour l'organisation.

    Par défaut: exécution synchrone (POST) - retourne le résultat.
    Pour les appels GET (interface/rafraîchissement), voir /recalculate-all (GET) qui programme un job en arrière-plan.
    Le paramètre persist=false permet à l'interface carte de recalculer sans écrire en base, évitant les verrous SQLite.
    """
    chemin_gpkg = None
    from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet
    from api.services.gpkg_versions import (
        resoudre_snapshot_pour_lecture, GpkgSimulationError)
    project = db.query(Project).filter(
        Project.org_id == ctx.org_id,
        Project.is_archived.is_(False)
    ).first()
    if project:
        try:
            snap_ctx = resoudre_snapshot_pour_lecture(db, project, snapshot)
            chemin = snap_ctx["path"]
            # Snapshot archivé = consultation stricte : jamais de purge ni
            # réécriture des clusters du projet (INV-4 lecture seule).
            if snapshot and not snap_ctx.get("est_version_courante"):
                persist = False
        except GpkgSimulationError:
            if snapshot:
                raise HTTPException(status_code=404, detail="Ressource introuvable")
            chemin = resoudre_gpkg_effectif_pour_projet(db, project)
        if chemin is not None:
            chemin_gpkg = str(chemin)

    if not chemin_gpkg:
        raise HTTPException(status_code=404, detail="Ressource introuvable")

    result = _calculate_clusters_sync(db, persist=persist, chemin_gpkg=chemin_gpkg)

    # Préchauffage : la détection d'ouvrages proches relit ~13 Mo de cache
    # clusters + les couches GPKG à chaque nouveau réseau. On la lance en
    # arrière-plan pour que le premier choix de bassin soit quasi instantané.
    try:
        _premier_cluster = ((result.get("resultats") or [{}])[0]
                            .get("cluster", {}) or {}).get("id")
        if _premier_cluster is not None:
            background_tasks.add_task(
                _prechauffer_ouvrages_proches, chemin_gpkg, str(_premier_cluster))
    except Exception:
        pass
    return result


# Helpers


@router.post("/{cluster_id}/recalculate")
def recalculate_cluster(
    cluster_id: int,
    background_tasks: BackgroundTasks,
    ctx: TenantContext = Depends(require_role("engineer")),
    db: Session = Depends(get_db)
):
    """Recalcule un cluster spécifique de l'organisation."""
    cluster = crud.get_cluster(db, cluster_id, org_id=ctx.org_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Ressource introuvable")
    raise HTTPException(status_code=501, detail="À implémenter")


@router.get("/{cluster_id}/geojson")
def export_cluster_geojson(
    cluster_id: int,
    request: Request = None,
    ctx: TenantContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db)
):
    """Export d'un cluster au format GeoJSON avec ordre topologique (stealth 404)."""
    from src.domain.detecteur_clusters import tracer_cluster_depuis_exutoire, construire_geojson_cluster
    from src.domain.graphe_reseau import calculer_ordre_topologique

    cluster = crud.get_cluster(db, cluster_id, org_id=ctx.org_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Ressource introuvable")

    chemin_gpkg = _trouver_chemin_gpkg(db, org_id=ctx.org_id)
    if not chemin_gpkg:
        raise HTTPException(status_code=404, detail="Ressource introuvable")
    G = _get_graph(chemin_gpkg)
    target_node = cluster.exutoire_noeud
    node_tuple = target_node
    if not node_tuple:
        raise HTTPException(status_code=400, detail="Exutoire du bassin absent")
    
    edges = tracer_cluster_depuis_exutoire(G, node_tuple)['edges']
    
    geojson = construire_geojson_cluster(G, edges, {})
    ordre_topologique = calculer_ordre_topologique(G, edges)
    
    return {
        "geojson": geojson,
        "ordre_topologique": ordre_topologique,
        "cluster_id": cluster_id,
        "nb_conduites": len(edges)
    }


def _trouver_chemin_gpkg(db: Session, org_id: Optional[str] = None, request: Optional[Request] = None) -> Optional[str]:
    """
    Résout le chemin du GeoPackage du projet actif de l'organisation :
    snapshot immuable de la version courante si versionné, sinon source_gpkg_key.
    """
    from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet
    if org_id:
        proj = db.query(Project).filter(
            Project.org_id == org_id,
            Project.is_archived.is_(False)
        ).first()
        if proj:
            chemin = resoudre_gpkg_effectif_pour_projet(db, proj)
            if chemin is not None:
                return str(chemin)
    return None


@router.get("/{cluster_id}/ouvrages-proches")
def get_cluster_ouvrages_proches(
    cluster_id: str,
    rayon_m: float = 45.0,
    request: Request = None,
    ctx: TenantContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db)
):
    """
    Retourne la liste des ouvrages spéciaux, stations de relevage, déversoirs d'orage
    et rejets orphelins situés à proximité (< rayon_m) du bassin versant.
    Permet la validation interactive avant simulation hydrodynamique.
    """
    from src.domain.ouvrages_orphelins import detecter_ouvrages_orphelins_proches
    chemin = _trouver_chemin_gpkg(db, org_id=ctx.org_id)
    if not chemin:
        raise HTTPException(status_code=404, detail="Ressource introuvable")
    return detecter_ouvrages_orphelins_proches(chemin, cluster_id, rayon_max_m=rayon_m)


# ---------------------------------------------------------------------------
# Facade de compatibilité — moteur de calcul extrait dans
# api/routes/clusters_calcul.py (règle modularité ≤600 lignes). L'état
# partagé (_GRAPH_CACHES, _CLUSTERS_CACHE, _GRAPH_STATUS…) reste défini
# dans ce module pour préserver les contrats d'import existants.
# ---------------------------------------------------------------------------
from api.routes.clusters_calcul import (  # noqa: F401
    _calculate_clusters,
    _calculate_clusters_background,
    _calculate_clusters_sync,
    _prechauffer_ouvrages_proches,
    _purger_clusters_du_projet,
    _warm_graph_cache,
)
