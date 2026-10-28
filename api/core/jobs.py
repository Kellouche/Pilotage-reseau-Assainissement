"""
Module api.core.jobs : Gestionnaire unifié du cycle de vie des Jobs asynchrones.
Conforme à la Roadmap SaaS Phase 2.3 & 2.6 (ADR-0003 : File de Jobs & Suivi).
"""

from datetime import datetime, timezone
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from api.models import Job

logger = logging.getLogger("swmm_platform.jobs")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_job(
    db: Session,
    org_id: str,
    job_type: str,
    network_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Job:
    """
    Crée et enregistre un nouveau Job dans la base de données.
    """
    job = Job(
        org_id=org_id,
        network_id=network_id,
        job_type=job_type,
        status="pending",
        progress=0,
        message="En attente de prise en charge par un worker...",
        result_refs=payload or {},
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info("Job créé : id=%s type=%s network=%s org=%s", job.id, job_type, network_id, org_id)
    return job


def update_job(
    db: Session,
    job_id: str,
    progress: Optional[int] = None,
    message: Optional[str] = None,
    status: Optional[str] = None,
    result_refs: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
) -> Optional[Job]:
    """
    Met à jour la progression et l'état d'un Job en base de données.
    """
    job = db.execute(select(Job).where(Job.id == job_id)).scalar_one_or_none()
    if not job:
        logger.warning("Tentative de mise à jour d'un job introuvable : %s", job_id)
        return None

    if status is not None:
        job.status = status

    if progress is not None:
        job.progress = max(0, min(100, int(progress)))

    if message is not None:
        job.message = str(message)

    if error_message is not None:
        job.error_message = str(error_message)

    if result_refs is not None:
        merged_results = dict(job.result_refs or {})
        merged_results.update(result_refs)
        job.result_refs = merged_results

    job.updated_at = _utc_now()
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: str, org_id: Optional[str] = None) -> Optional[Job]:
    """
    Récupère un Job par son ID.
    Si org_id est spécifié, applique une isolation stricte (None si autre tenant).
    """
    stmt = select(Job).where(Job.id == job_id)
    if org_id is not None:
        stmt = stmt.where(Job.org_id == org_id)
    return db.execute(stmt).scalar_one_or_none()


def list_jobs(
    db: Session,
    org_id: str,
    network_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
) -> List[Job]:
    """
    Liste les Jobs appartenant à une organisation, triés du plus récent au plus ancien.
    """
    stmt = select(Job).where(Job.org_id == org_id)
    if network_id is not None:
        stmt = stmt.where(Job.network_id == network_id)
    if status is not None:
        stmt = stmt.where(Job.status == status)

    stmt = stmt.order_by(desc(Job.created_at)).offset(skip).limit(limit)
    return list(db.execute(stmt).scalars().all())
