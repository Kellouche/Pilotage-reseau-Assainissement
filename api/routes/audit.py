"""
Routes pour la traçabilité et l'audit des modifications.
Exposition des logs d'audit et de l'historique des versions.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from api.database import get_db
from api import crud, schemas

router = APIRouter(prefix="/audit", tags=["Traçabilité / Audit"])


@router.get("/logs", response_model=List[dict])
def list_audit_logs(
    table_name: Optional[str] = Query(None, description="Filtrer par table (ex: regards, conduites)"),
    record_id: Optional[int] = Query(None, description="Filtrer par ID d'enregistrement"),
    operation: Optional[str] = Query(None, description="Filtrer par opération (INSERT, UPDATE, DELETE)"),
    user_id: Optional[str] = Query(None, description="Filtrer par utilisateur"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """Liste les logs d'audit avec filtres optionnels."""
    query = db.query(crud.AuditLog)

    if table_name:
        query = query.filter(crud.AuditLog.table_name == table_name)
    if record_id:
        query = query.filter(crud.AuditLog.record_id == record_id)
    if operation:
        query = query.filter(crud.AuditLog.operation == operation)
    if user_id:
        query = query.filter(crud.AuditLog.user_id == user_id)

    logs = query.order_by(crud.AuditLog.timestamp.desc()).offset(skip).limit(limit).all()
    return [log.to_dict() for log in logs]


@router.get("/logs/{record_id}", response_model=List[dict])
def get_audit_logs_for_record(
    record_id: int,
    table_name: Optional[str] = Query(None, description="Table concernée"),
    db: Session = Depends(get_db)
):
    """Récupère l'historique complet d'un enregistrement par son ID."""
    query = db.query(crud.AuditLog).filter(crud.AuditLog.record_id == record_id)
    if table_name:
        query = query.filter(crud.AuditLog.table_name == table_name)

    logs = query.order_by(crud.AuditLog.timestamp.desc()).all()
    return [log.to_dict() for log in logs]


@router.get("/regards/{regard_id}/history", response_model=List[dict])
def get_regard_history(regard_id: int, db: Session = Depends(get_db)):
    """Historique des versions d'un regard."""
    regard = crud.get_regard(db, regard_id)
    if not regard:
        raise HTTPException(status_code=404, detail="Regard non trouvé")

    logs = db.query(crud.AuditLog).filter(
        crud.AuditLog.table_name == "regards",
        crud.AuditLog.record_id == regard_id
    ).order_by(crud.AuditLog.timestamp.desc()).all()

    history = []
    for log in logs:
        entry = log.to_dict()
        entry["version"] = regard.version
        entry["current_values"] = regard.to_dict()
        history.append(entry)

    return history


@router.get("/conduites/{conduite_id}/history", response_model=List[dict])
def get_conduite_history(conduite_id: int, db: Session = Depends(get_db)):
    """Historique des versions d'une canalisation."""
    conduite = crud.get_canalisation(db, conduite_id)
    if not conduite:
        raise HTTPException(status_code=404, detail="Canalisation non trouvée")

    logs = db.query(crud.AuditLog).filter(
        crud.AuditLog.table_name == "conduites",
        crud.AuditLog.record_id == conduite_id
    ).order_by(crud.AuditLog.timestamp.desc()).all()

    history = []
    for log in logs:
        entry = log.to_dict()
        entry["version"] = conduite.version
        entry["current_values"] = conduite.to_dict()
        history.append(entry)

    return history
