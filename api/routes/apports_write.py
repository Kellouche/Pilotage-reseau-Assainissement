# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Endpoints ecriture des apports DWF : creation, modification, revalidation, suppression, purge (extrait de routes/apports.py)
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
from api.routes import apports as _apports_core
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
    _apports_core.enregistrer_historique_apport(
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

        _apports_core.enregistrer_historique_apport(
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
    _apports_core.enregistrer_historique_apport(
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
    _apports_core.enregistrer_historique_apport(
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
        _apports_core.enregistrer_historique_apport(
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
