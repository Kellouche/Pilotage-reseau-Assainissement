# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-19
Objet : Opérations CRUD pour les relevés terrain et photos géolocalisées (Multi-Tenant)
================================================================================
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime

from api.models_terrain import Inspection, Incident
from api.crud import log_audit


# ============================================================
# INSPECTIONS TERRAIN
# ============================================================

def get_inspection(db: Session, inspection_id: int, org_id: Optional[str] = None) -> Optional[Inspection]:
    query = db.query(Inspection).filter(Inspection.id == inspection_id)
    if org_id:
        query = query.filter(Inspection.org_id == org_id)
    return query.first()


def get_inspections(db: Session, skip: int = 0, limit: int = 100, org_id: Optional[str] = None) -> List[Inspection]:
    query = db.query(Inspection)
    if org_id:
        query = query.filter(Inspection.org_id == org_id)
    return query.order_by(Inspection.date_inspection.desc()).offset(skip).limit(limit).all()


def get_inspections_by_object(
    db: Session, object_type: str, object_id: str, org_id: Optional[str] = None
) -> List[Inspection]:
    query = db.query(Inspection).filter(
        Inspection.object_type == object_type,
        Inspection.object_id == object_id
    )
    if org_id:
        query = query.filter(Inspection.org_id == org_id)
    return query.order_by(Inspection.date_inspection.desc()).all()


def create_inspection(
    db: Session,
    inspection_data: Dict[str, Any],
    user_id: Optional[str] = None,
    org_id: Optional[str] = None
) -> Inspection:
    data = dict(inspection_data)
    if org_id and "org_id" not in data:
        data["org_id"] = org_id
    inspection = Inspection(
        **data,
        inspecteur=user_id
    )
    db.add(inspection)
    db.commit()
    db.refresh(inspection)

    # Journal d'audit
    log_audit(
        db=db,
        action="terrain.inspection.create",
        org_id=inspection.org_id,
        user_id=user_id,
        target_type="inspection",
        target_id=str(inspection.id),
        details={"object_type": inspection.object_type, "object_id": inspection.object_id}
    )

    return inspection


# ============================================================
# INCIDENTS GÉOLOCALISÉS
# ============================================================

def get_incident(db: Session, incident_id: int, org_id: Optional[str] = None) -> Optional[Incident]:
    query = db.query(Incident).filter(Incident.id == incident_id)
    if org_id:
        query = query.filter(Incident.org_id == org_id)
    return query.first()


def get_incidents(db: Session, skip: int = 0, limit: int = 100, org_id: Optional[str] = None) -> List[Incident]:
    query = db.query(Incident)
    if org_id:
        query = query.filter(Incident.org_id == org_id)
    return query.order_by(Incident.date_signalement.desc()).offset(skip).limit(limit).all()


def create_incident(
    db: Session,
    incident_data: Dict[str, Any],
    user_id: Optional[str] = None,
    org_id: Optional[str] = None
) -> Incident:
    data = dict(incident_data)
    if org_id and "org_id" not in data:
        data["org_id"] = org_id
    incident = Incident(
        **data
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)

    # Journal d'audit
    log_audit(
        db=db,
        action="terrain.incident.create",
        org_id=incident.org_id,
        user_id=user_id,
        target_type="incident",
        target_id=str(incident.id),
        details={"type_incident": incident.type_incident, "gravite": incident.gravite}
    )

    return incident


def update_incident_status(
    db: Session,
    incident_id: int,
    statut: str,
    user_id: Optional[str] = None,
    org_id: Optional[str] = None
) -> Optional[Incident]:
    incident = get_incident(db, incident_id, org_id=org_id)
    if not incident:
        return None

    old_values = incident.to_dict()
    incident.statut = statut
    incident.version += 1
    incident.last_modified = datetime.utcnow()

    db.commit()
    db.refresh(incident)

    # Journal d'audit
    log_audit(
        db=db,
        action="terrain.incident.update_status",
        org_id=incident.org_id,
        user_id=user_id,
        target_type="incident",
        target_id=str(incident.id),
        details={"old_status": old_values.get("statut"), "new_status": statut}
    )

    return incident
