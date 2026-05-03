"""
Routes pour les simulations SWMM.
Lancement asynchrone, récupération résultats, statuts.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.orm import Session
from typing import List, Optional

from api.database import get_db
from api import schemas, crud

router = APIRouter(prefix="/simulations", tags=["Simulations"])


# ============================================================
# LANCEMENT & STATUT
# ============================================================

@router.get("", response_model=List[schemas.SimulationResponse])
def list_simulations(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Liste toutes les simulations (ordre décroissant)."""
    sims = crud.get_simulations(db=db, skip=skip, limit=limit, status=status)
    return sims

@router.post("", response_model=schemas.SimulationResponse, status_code=status.HTTP_202_ACCEPTED)
def launch_simulation(
    simulation: schemas.SimulationCreate,
    user_id: str = "system",
    db: Session = Depends(get_db)
):
    """
    Lance une simulation SWMM pour un cluster.
    Retourne immédiatement avec un job_id pour polling.
    """
    # Vérifier cluster existe
    cluster = crud.get_cluster(db, simulation.cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster non trouvé")

    # Générer job_id (UUID)
    import uuid
    job_id = str(uuid.uuid4())

    # Créer enregistrement simulation
    sim_obj = crud.create_simulation(
        db=db,
        cluster_id=simulation.cluster_id,
        job_id=job_id,
        parameters=simulation.parameters,
        created_by=user_id
    )

    # TODO: déclencher Celery worker
    # from workers.swmm_worker import run_simulation_task
    # run_simulation_task.delay(job_id, simulation.cluster_id, simulation.parameters)

    # Pour POC : retourner sans lancer (simulation fictive)
    return sim_obj.to_dict()


@router.get("/{simulation_id}", response_model=schemas.SimulationResponse)
def get_simulation(simulation_id: int, db: Session = Depends(get_db)):
    """Récupère une simulation par ID."""
    sim = crud.get_simulation(db, simulation_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation non trouvée")
    return sim.to_dict()


@router.get("/job/{job_id}", response_model=schemas.SimulationResponse)
def get_simulation_by_job(job_id: str, db: Session = Depends(get_db)):
    """Récupère une simulation par job_id (Celery)."""
    sim = crud.get_simulation_by_job_id(db, job_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Job non trouvé")
    return sim.to_dict()


@router.get("/cluster/{cluster_id}", response_model=List[schemas.SimulationResponse])
def list_cluster_simulations(
    cluster_id: int,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Liste des simulations d'un cluster."""
    sims = crud.get_simulations(
        db=db,
        cluster_id=cluster_id,
        status=status,
        skip=skip,
        limit=limit
    )
    return [s.to_dict() for s in sims]


@router.get("/status/{job_id}", response_model=schemas.SimulationStatusResponse)
def get_simulation_status(job_id: str, db: Session = Depends(get_db)):
    """Polling du statut d'une simulation (pour mobile)."""
    sim = crud.get_simulation_by_job_id(db, job_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Job non trouvé")

    response = {
        "job_id": job_id,
        "status": sim.status
    }

    if sim.status == "COMPLETED":
        response["result_url"] = f"/api/v1/simulations/job/{job_id}/download"
    elif sim.status == "FAILED":
        response["error"] = sim.error_message

    return response


@router.delete("/{simulation_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_simulation(simulation_id: int, db: Session = Depends(get_db)):
    """Annule une simulation en attente (PENDING/RUNNING)."""
    sim = crud.get_simulation(db, simulation_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation non trouvée")

    if sim.status not in ["PENDING", "RUNNING"]:
        raise HTTPException(status_code=400, detail="Impossible d'annuler: statut final")

    # TODO: Celery revoke si possible
    sim.status = "CANCELLED"
    db.commit()

    return None
