"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Endpoints de suivi des jobs asynchrones Celery et calculs de fond
================================================================================
"""

import asyncio
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from api.database import get_db, SessionLocal
from api.core.security import get_tenant_context, TenantContext
from api.core.jobs import get_job, list_jobs
from api.models import Job

router = APIRouter(prefix="/jobs", tags=["Jobs & Tâches Asynchrones"])


@router.get("", response_model=List[dict])
def get_jobs_list(
    network_id: Optional[str] = Query(None, description="Filtrer par projet/réseau"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filtrer par statut (pending, running, completed, failed)"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Liste les tâches asynchrones de l'organisation connectée.
    """
    actual_limit = limit if isinstance(limit, int) else 50
    actual_skip = skip if isinstance(skip, int) else 0
    actual_status = status_filter if isinstance(status_filter, str) else None
    actual_network = network_id if isinstance(network_id, str) else None

    jobs = list_jobs(
        db=db,
        org_id=tenant.org.id,
        network_id=actual_network,
        status=actual_status,
        limit=actual_limit,
        skip=actual_skip,
    )
    return [j.to_dict() for j in jobs]


@router.get("/{job_id}", response_model=dict)
def get_job_status(
    job_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Récupère l'état et la progression d'une tâche asynchrone (0 à 100%).
    Cloisonnement strict : renvoie 404 si la tâche appartient à une autre organisation.
    """
    job = get_job(db=db, job_id=job_id, org_id=tenant.org.id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tâche introuvable",
        )
    return job.to_dict()


@router.websocket("/ws/{job_id}")
async def websocket_job_progress(websocket: WebSocket, job_id: str):
    """
    Canal WebSocket temps réel diffusant les mises à jour de progression d'un Job.
    Se ferme automatiquement dès que la tâche est terminée (completed ou failed).
    """
    await websocket.accept()

    try:
        last_progress = -1
        last_status = ""

        # Boucle de notification de progression
        for _ in range(300):  # Maximum 150 secondes de streaming continu
            db = SessionLocal()
            try:
                job = db.query(Job).filter(Job.id == job_id).first()
                if not job:
                    await websocket.send_json({"error": "Job introuvable", "status": "not_found"})
                    break

                if job.progress != last_progress or job.status != last_status:
                    last_progress = job.progress
                    last_status = job.status
                    await websocket.send_json({
                        "job_id": job.id,
                        "status": job.status,
                        "progress": job.progress,
                        "message": job.message,
                        "result": job.result_refs or {},
                        "error": job.error_message,
                    })

                if job.status in ("completed", "failed"):
                    break
            finally:
                db.close()

            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
