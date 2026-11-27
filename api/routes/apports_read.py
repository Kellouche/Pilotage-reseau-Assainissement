# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Endpoints lecture des apports DWF : profils, liste, noeuds, a-reconcilier, historique (extrait de routes/apports.py)
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
from api.routes.apports import (
    _apport_scoped,
    _contexte_noeuds,
    _filtre_snapshot_apports,
    _natural_sort_key,
    _noeuds_cluster_gpkg,
    _noeuds_connectes_gpkg,
    _noeuds_valides_projet,
    _resoudre_projet,
    _valider_noeud,
    _valider_noeud_et_version,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/apports", tags=["Apports de temps sec (DWF)"])


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
