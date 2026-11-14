# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-14
Objet : Journal d'audit des actions utilisateurs, modifications et traçabilité
================================================================================
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional, Any, Dict

from api.database import get_db
from api.models import AuditLog
from api import crud, schemas
from api.core.security import get_tenant_context, require_role, TenantContext

router = APIRouter(prefix="/audit", tags=["Traçabilité / Audit"])


@router.get("/logs", response_model=List[schemas.AuditLogResponse])
def list_audit_logs(
    action: Optional[str] = Query(None, description="Filtrer par action (ex: network.import, anomaly.correct)"),
    target_type: Optional[str] = Query(None, description="Filtrer par type de cible (ex: regard, conduite)"),
    target_id: Optional[str] = Query(None, description="Filtrer par ID d'enregistrement cible"),
    user_id: Optional[str] = Query(None, description="Filtrer par utilisateur"),
    # Paramètres de rétrocompatibilité :
    operation: Optional[str] = Query(None, description="Alias rétrocompatible pour action"),
    table_name: Optional[str] = Query(None, description="Alias rétrocompatible pour target_type"),
    record_id: Optional[str] = Query(None, description="Alias rétrocompatible pour target_id"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_role("viewer")),
):
    """
    Liste les logs d'audit avec filtres optionnels, strictement cloisonnés par organisation.
    Requiert au minimum le rôle 'viewer' au sein de l'organisation active.
    """
    query = db.query(AuditLog).filter(AuditLog.org_id == ctx.org_id)

    effective_action = action or operation
    if effective_action:
        query = query.filter(AuditLog.action == effective_action)

    effective_target_type = target_type or table_name
    if effective_target_type:
        query = query.filter(AuditLog.target_type == effective_target_type)

    effective_target_id = target_id or (str(record_id) if record_id is not None else None)
    if effective_target_id:
        query = query.filter(AuditLog.target_id == effective_target_id)

    if user_id:
        query = query.filter(AuditLog.user_id == user_id)

    logs = query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()
    return logs


@router.get("/logs/{record_id}", response_model=List[schemas.AuditLogResponse])
def get_audit_logs_for_record(
    record_id: str,
    target_type: Optional[str] = Query(None, description="Type de cible (ex: regard, conduite)"),
    table_name: Optional[str] = Query(None, description="Alias rétrocompatible pour target_type"),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_role("viewer")),
):
    """
    Récupère l'historique d'un enregistrement par son identifiant ou identifiant cible,
    strictement cloisonné à l'organisation active.
    """
    effective_target_type = target_type or table_name
    query = db.query(AuditLog).filter(
        AuditLog.org_id == ctx.org_id,
        (AuditLog.target_id == str(record_id)) | (AuditLog.id == str(record_id))
    )
    if effective_target_type:
        query = query.filter(AuditLog.target_type == effective_target_type)

    logs = query.order_by(AuditLog.created_at.desc()).all()
    return logs


@router.get("/regards/{regard_id}/history", response_model=List[dict])
def get_regard_history(
    regard_id: Any,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_role("viewer")),
):
    """
    Historique des versions d'un regard au sein de l'organisation.
    Applique la règle de 404 furtive si le regard n'appartient pas à l'organisation.
    """
    regard = crud.get_regard(db, regard_id, org_id=ctx.org_id)
    if not regard:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regard non trouvé."
        )

    logs = db.query(AuditLog).filter(
        AuditLog.org_id == ctx.org_id,
        AuditLog.target_type.in_(["regard", "regards"]),
        AuditLog.target_id == str(regard_id)
    ).order_by(AuditLog.created_at.desc()).all()

    history = []
    for log in logs:
        entry = log.to_dict()
        entry["version"] = getattr(regard, "version", 1)
        entry["current_values"] = regard.to_dict() if hasattr(regard, "to_dict") else {}
        history.append(entry)

    return history


@router.get("/conduites/{conduite_id}/history", response_model=List[dict])
def get_conduite_history(
    conduite_id: Any,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_role("viewer")),
):
    """
    Historique des versions d'une canalisation au sein de l'organisation.
    Applique la règle de 404 furtive si la canalisation n'appartient pas à l'organisation.
    """
    conduite = crud.get_canalisation(db, conduite_id, org_id=ctx.org_id)
    if not conduite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Canalisation non trouvée."
        )

    logs = db.query(AuditLog).filter(
        AuditLog.org_id == ctx.org_id,
        AuditLog.target_type.in_(["conduite", "conduites"]),
        AuditLog.target_id == str(conduite_id)
    ).order_by(AuditLog.created_at.desc()).all()

    history = []
    for log in logs:
        entry = log.to_dict()
        entry["version"] = getattr(conduite, "version", 1)
        entry["current_values"] = conduite.to_dict() if hasattr(conduite, "to_dict") else {}
        history.append(entry)

    return history
