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
from typing import Optional, Set

import geopandas as gpd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import ApportDwf, Project
from api.core.security import TenantContext, get_tenant_context, require_role
from api.schemas import (
    ApportDwfCreate, ApportDwfUpdate, ApportDwfResponse, ProfilDwfInfo,
)
from api.services.simulation_service import (
    _resoudre_projet_pour_simulation,
    resoudre_gpkg_effectif_pour_projet,
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

def _noeuds_valides_projet(db: Session, proj: Project) -> Set[str]:
    """
    Ensemble des identifiants de nœuds valides = _clean_node_id(Code) de la
    couche 'regards' du GPKG effectif du projet (versionné si applicable).
    Lève HTTPException 422 si le réseau est indisponible ou illisible :
    sans référentiel, aucun rattachement ne peut être validé.
    """
    gpkg_path = resoudre_gpkg_effectif_pour_projet(db, proj)
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
    return noeuds


def _valider_noeud(db: Session, proj: Project, node_id: str) -> str:
    """Normalise et valide node_id contre le GPKG du projet. Retourne l'id canonique."""
    from src.domain.moteur_swmm.constants import _clean_node_id
    nid = _clean_node_id(node_id)
    if not nid:
        raise HTTPException(status_code=422, detail="Identifiant de nœud invalide.")
    if nid not in _noeuds_valides_projet(db, proj):
        raise HTTPException(
            status_code=422,
            detail=f"Nœud '{nid}' inexistant dans le réseau du projet.")
    return nid


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
    actif_seulement: bool = Query(False),
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Liste les apports DWF du projet (bornés à l'organisation du tenant)."""
    proj = _resoudre_projet(db, tenant, project_id)
    q = db.query(ApportDwf).filter(
        ApportDwf.org_id == tenant.org_id,
        ApportDwf.project_id == proj.id)
    if node_id:
        from src.domain.moteur_swmm.constants import _clean_node_id
        q = q.filter(ApportDwf.node_id == _clean_node_id(node_id))
    if actif_seulement:
        q = q.filter(ApportDwf.actif.is_(True))
    return [a.to_dict() for a in q.order_by(ApportDwf.created_at).all()]


@router.get("/noeuds")
def lister_noeuds_disponibles(
    project_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Liste les identifiants de nœuds valides du GPKG du projet (aide à la saisie)."""
    proj = _resoudre_projet(db, tenant, project_id)
    noeuds = sorted(_noeuds_valides_projet(db, proj))
    return {"project_id": proj.id, "noeuds": noeuds, "count": len(noeuds)}


@router.post("", response_model=ApportDwfResponse, status_code=201)
def creer_apport(
    payload: ApportDwfCreate,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_role("engineer")),
):
    """Crée un apport de temps sec sur un nœud du projet."""
    proj = _resoudre_projet(db, tenant, payload.project_id)
    node_id = _valider_noeud(db, proj, payload.node_id)

    apport = ApportDwf(
        org_id=tenant.org_id,
        project_id=proj.id,
        node_id=node_id,
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
        created_by_id=getattr(tenant.user, "id", None) if tenant.user else None,
    )
    _calculer_debit(apport)
    db.add(apport)
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

    data = payload.model_dump(exclude_unset=True)
    nouveau_node = data.pop("node_id", None)
    if nouveau_node is not None and proj is not None:
        apport.node_id = _valider_noeud(db, proj, nouveau_node)

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
    db.delete(apport)
    db.commit()
    return None
