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
from api.models import AuditLog


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
    log = AuditLog(
        table_name="inspections",
        record_id=inspection.id,
        operation="INSERT",
        new_values=data,
        user_id=user_id,
        device_id=data.get("device_id")
    )
    db.add(log)
    db.commit()

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
    log = AuditLog(
        table_name="incidents",
        record_id=incident.id,
        operation="INSERT",
        new_values=data,
        user_id=user_id,
        device_id=data.get("device_id")
    )
    db.add(log)
    db.commit()

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
    log = AuditLog(
        table_name="incidents",
        record_id=incident.id,
        operation="UPDATE",
        old_values=old_values,
        new_values={"statut": statut},
        user_id=user_id
    )
    db.add(log)
    db.commit()

    return incident
