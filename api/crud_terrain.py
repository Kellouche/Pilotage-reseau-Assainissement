# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Opérations CRUD pour les relevés terrain et photos géolocalisées
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

def get_inspection(db: Session, inspection_id: int) -> Optional[Inspection]:
    return db.query(Inspection).filter(Inspection.id == inspection_id).first()


def get_inspections(db: Session, skip: int = 0, limit: int = 100) -> List[Inspection]:
    return db.query(Inspection).order_by(Inspection.date_inspection.desc()).offset(skip).limit(limit).all()


def get_inspections_by_object(db: Session, object_type: str, object_id: str) -> List[Inspection]:
    return db.query(Inspection).filter(
        Inspection.object_type == object_type,
        Inspection.object_id == object_id
    ).order_by(Inspection.date_inspection.desc()).all()


def create_inspection(db: Session, inspection_data: Dict[str, Any], user_id: str = None) -> Inspection:
    inspection = Inspection(
        **inspection_data,
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
        new_values=inspection_data,
        user_id=user_id,
        device_id=inspection_data.get("device_id")
    )
    db.add(log)
    db.commit()

    return inspection

# ============================================================
# INCIDENTS GÉOLOCALISÉS
# ============================================================

def get_incident(db: Session, incident_id: int) -> Optional[Incident]:
    return db.query(Incident).filter(Incident.id == incident_id).first()


def get_incidents(db: Session, skip: int = 0, limit: int = 100) -> List[Incident]:
    return db.query(Incident).order_by(Incident.date_signalement.desc()).offset(skip).limit(limit).all()


def create_incident(db: Session, incident_data: Dict[str, Any], user_id: str = None) -> Incident:
    incident = Incident(
        **incident_data
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)

    # Journal d'audit
    log = AuditLog(
        table_name="incidents",
        record_id=incident.id,
        operation="INSERT",
        new_values=incident_data,
        user_id=user_id,
        device_id=incident_data.get("device_id")
    )
    db.add(log)
    db.commit()

    return incident


def update_incident_status(db: Session, incident_id: int, statut: str, user_id: str = None) -> Optional[Incident]:
    incident = get_incident(db, incident_id)
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
