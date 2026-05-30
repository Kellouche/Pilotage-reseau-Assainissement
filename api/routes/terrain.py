# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : Plateforme de Pilotage du Réseau d'Assainissement
Numéro version : 1.0.0
Date de création : 30-05-2026
Date de modification : 30-05-2026

Objectif du module :
Routeur FastAPI exposant les points d'accès (endpoints) pour la gestion 
des fiches d'inspections terrain et des incidents géolocalisés.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from api.database import get_db
from api import schemas_terrain, crud_terrain
from api.websocket import manager

router = APIRouter(prefix="/terrain", tags=["Collecte Terrain"])

# ============================================================
# INSPECTIONS TERRAIN
# ============================================================

@router.post("/inspections", response_model=schemas_terrain.InspectionResponse, status_code=status.HTTP_201_CREATED)
async def create_inspection(
    inspection: schemas_terrain.InspectionCreate,
    user_id: Optional[str] = "agent_terrain",
    db: Session = Depends(get_db)
):
    """Crée une nouvelle fiche d'inspection pour un équipement."""
    try:
        inspect_obj = crud_terrain.create_inspection(
            db=db,
            inspection_data=inspection.dict(),
            user_id=user_id
        )
        
        # Diffuser une alerte de modification via WebSocket
        msg = f"Nouvelle inspection : {inspection.object_type.upper()} {inspection.object_id} - État: {inspection.etat or 'N/A'}"
        await manager.broadcast(msg)
        
        return inspect_obj
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/inspections", response_model=List[schemas_terrain.InspectionResponse])
def list_inspections(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """Récupère la liste de toutes les inspections terrain."""
    return crud_terrain.get_inspections(db=db, skip=skip, limit=limit)


@router.get("/inspections/{object_type}/{object_id}", response_model=List[schemas_terrain.InspectionResponse])
def get_inspections_for_object(
    object_type: str,
    object_id: str,
    db: Session = Depends(get_db)
):
    """Récupère l'historique des inspections pour un équipement donné."""
    return crud_terrain.get_inspections_by_object(
        db=db,
        object_type=object_type,
        object_id=object_id
    )

# ============================================================
# INCIDENTS GÉOLOCALISÉS
# ============================================================

@router.post("/incidents", response_model=schemas_terrain.IncidentResponse, status_code=status.HTTP_201_CREATED)
async def create_incident(
    incident: schemas_terrain.IncidentCreate,
    user_id: Optional[str] = "agent_terrain",
    db: Session = Depends(get_db)
):
    """Signale un nouvel incident géolocalisé."""
    try:
        inc_obj = crud_terrain.create_incident(
            db=db,
            incident_data=incident.dict(),
            user_id=user_id
        )
        
        # Diffuser une alerte d'incident via WebSocket
        msg = f"Incident signalé ! Type: {incident.type_incident} [Gravité: {incident.gravite}] à [{incident.longitude:.4f}, {incident.latitude:.4f}]"
        await manager.broadcast(msg)
        
        return inc_obj
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/incidents", response_model=List[schemas_terrain.IncidentResponse])
def list_incidents(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """Récupère la liste des incidents géolocalisés."""
    return crud_terrain.get_incidents(db=db, skip=skip, limit=limit)


@router.patch("/incidents/{incident_id}", response_model=schemas_terrain.IncidentResponse)
def update_incident_status(
    incident_id: int,
    statut: str = Query(..., description="Nouveau statut de l'incident"),
    user_id: Optional[str] = "bureau",
    db: Session = Depends(get_db)
):
    """Met à jour le statut d'un incident géolocalisé (À traiter, En cours, Résolu)."""
    updated = crud_terrain.update_incident_status(
        db=db,
        incident_id=incident_id,
        statut=statut,
        user_id=user_id
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Incident non trouvé")
    return updated
