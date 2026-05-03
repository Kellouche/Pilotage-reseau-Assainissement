"""
Opérations CRUD (Create, Read, Update, Delete) pour les tables.
Contient la logique d'accès aux données, séparée des routes.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime

from api.models import (
    Regard,
    Canalisation,
    Rejet,
    Cluster,
    Simulation,
    AuditLog
)

# ============================================================
# REGARDS
# ============================================================

def get_regard(db: Session, regard_id: int) -> Optional[Regard]:
    return db.query(Regard).filter(Regard.id == regard_id).first()


def get_regard_by_code(db: Session, code: str) -> Optional[Regard]:
    return db.query(Regard).filter(Regard.code == code).first()


def get_regards(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    commune: Optional[str] = None,
    cluster_id: Optional[int] = None
) -> List[Regard]:
    query = db.query(Regard)
    if commune:
        query = query.filter(Regard.commune.ilike(f"%{commune}%"))
    if cluster_id:
        query = query.filter(Regard.cluster_id == cluster_id)
    return query.offset(skip).limit(limit).all()


def create_regard(db: Session, regard_data: Dict[str, Any], user_id: str = None) -> Regard:
    # Vérifier unicité code
    existing = get_regard_by_code(db, regard_data["code"])
    if existing:
        raise ValueError(f"Un regard avec le code '{regard_data['code']}' existe déjà")

    regard = Regard(
        **regard_data,
        modified_by=user_id
    )
    db.add(regard)
    db.commit()
    db.refresh(regard)

    # Audit
    log = AuditLog(
        table_name="regards",
        record_id=regard.id,
        operation="INSERT",
        new_values=regard_data,
        user_id=user_id
    )
    db.add(log)
    db.commit()

    return regard


def update_regard(
    db: Session,
    regard_id: int,
    update_data: Dict[str, Any],
    user_id: str = None
) -> Optional[Regard]:
    regard = get_regard(db, regard_id)
    if not regard:
        return None

    # Sauvegarde anciennes valeurs pour audit
    old_values = regard.to_dict()

    # Appliquer modifications
    for field, value in update_data.items():
        if hasattr(regard, field) and value is not None:
            setattr(regard, field, value)

    # Incrémenter version
    regard.version += 1
    regard.last_modified = datetime.utcnow()
    regard.modified_by = user_id

    db.commit()
    db.refresh(regard)

    # Audit
    log = AuditLog(
        table_name="regards",
        record_id=regard.id,
        operation="UPDATE",
        old_values=old_values,
        new_values=update_data,
        user_id=user_id
    )
    db.add(log)
    db.commit()

    return regard


def delete_regard(db: Session, regard_id: int, user_id: str = None) -> bool:
    regard = get_regard(db, regard_id)
    if not regard:
        return False

    old_values = regard.to_dict()
    db.delete(regard)
    db.commit()

    # Audit
    log = AuditLog(
        table_name="regards",
        record_id=regard_id,
        operation="DELETE",
        old_values=old_values,
        user_id=user_id
    )
    db.add(log)
    db.commit()

    return True


# ============================================================
# CANALISATIONS
# ============================================================

def get_canalisation(db: Session, canalisation_id: int) -> Optional[Canalisation]:
    return db.query(Canalisation).filter(Canalisation.id == canalisation_id).first()


def get_canalisation_by_fid(db: Session, fid: str) -> Optional[Canalisation]:
    return db.query(Canalisation).filter(Canalisation.fid == fid).first()


def get_canalisations(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    cluster_id: Optional[int] = None
) -> List[Canalisation]:
    query = db.query(Canalisation)
    if cluster_id:
        query = query.filter(Canalisation.cluster_id == cluster_id)
    return query.offset(skip).limit(limit).all()


def create_canalisation(
    db: Session,
    canalisation_data: Dict[str, Any],
    user_id: str = None
) -> Canalisation:
    existing = get_canalisation_by_fid(db, canalisation_data["fid"])
    if existing:
        raise ValueError(f"Une canalisation avec le fid '{canalisation_data['fid']}' existe déjà")

    canalisation = Canalisation(
        **canalisation_data,
        modified_by=user_id
    )
    db.add(canalisation)
    db.commit()
    db.refresh(canalisation)

    # Audit
    log = AuditLog(
        table_name="conduites",
        record_id=canalisation.id,
        operation="INSERT",
        new_values=canalisation_data,
        user_id=user_id
    )
    db.add(log)
    db.commit()

    return canalisation


def update_canalisation(
    db: Session,
    canalisation_id: int,
    update_data: Dict[str, Any],
    user_id: str = None
) -> Optional[Canalisation]:
    canalisation = get_canalisation(db, canalisation_id)
    if not canalisation:
        return None

    old_values = canalisation.to_dict()

    for field, value in update_data.items():
        if hasattr(canalisation, field) and value is not None:
            setattr(canalisation, field, value)

    canalisation.version += 1
    canalisation.last_modified = datetime.utcnow()
    canalisation.modified_by = user_id

    db.commit()
    db.refresh(canalisation)

    log = AuditLog(
        table_name="conduites",
        record_id=canalisation.id,
        operation="UPDATE",
        old_values=old_values,
        new_values=update_data,
        user_id=user_id
    )
    db.add(log)
    db.commit()

    return canalisation


def delete_canalisation(db: Session, canalisation_id: int, user_id: str = None) -> bool:
    canalisation = get_canalisation(db, canalisation_id)
    if not canalisation:
        return False

    old_values = canalisation.to_dict()
    db.delete(canalisation)
    db.commit()

    log = AuditLog(
        table_name="conduites",
        record_id=canalisation_id,
        operation="DELETE",
        old_values=old_values,
        user_id=user_id
    )
    db.add(log)
    db.commit()

    return True


# ============================================================
# CLUSTERS
# ============================================================

def get_cluster(db: Session, cluster_id: int) -> Optional[Cluster]:
    return db.query(Cluster).filter(Cluster.id == cluster_id).first()


def get_clusters(db: Session, skip: int = 0, limit: int = 100) -> List[Cluster]:
    return db.query(Cluster).offset(skip).limit(limit).all()


def create_cluster(db: Session, cluster_data: Dict[str, Any]) -> Cluster:
    cluster = Cluster(**cluster_data)
    db.add(cluster)
    db.commit()
    db.refresh(cluster)
    return cluster


def update_cluster_stats(db: Session, cluster_id: int, stats: Dict[str, Any]) -> Optional[Cluster]:
    cluster = get_cluster(db, cluster_id)
    if not cluster:
        return None

    for key, value in stats.items():
        if hasattr(cluster, key):
            setattr(cluster, key, value)

    cluster.version += 1
    cluster.last_recalculated = datetime.utcnow()
    db.commit()
    db.refresh(cluster)
    return cluster


# ============================================================
# SIMULATIONS
# ============================================================

def get_simulation(db: Session, simulation_id: int) -> Optional[Simulation]:
    return db.query(Simulation).filter(Simulation.id == simulation_id).first()


def get_simulation_by_job_id(db: Session, job_id: str) -> Optional[Simulation]:
    return db.query(Simulation).filter(Simulation.job_id == job_id).first()


def get_simulations(
    db: Session,
    cluster_id: Optional[int] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100
) -> List[Simulation]:
    query = db.query(Simulation)
    if cluster_id:
        query = query.filter(Simulation.cluster_id == cluster_id)
    if status:
        query = query.filter(Simulation.status == status)
    return query.order_by(Simulation.created_at.desc()).offset(skip).limit(limit).all()


def create_simulation(
    db: Session,
    cluster_id: int,
    job_id: str,
    parameters: Dict[str, Any] = None,
    created_by: str = None
) -> Simulation:
    simulation = Simulation(
        cluster_id=cluster_id,
        job_id=job_id,
        status="PENDING",
        parameters=parameters,
        created_by=created_by
    )
    db.add(simulation)
    db.commit()
    db.refresh(simulation)
    return simulation


def update_simulation_status(
    db: Session,
    job_id: str,
    status: str,
    result_summary: Dict[str, Any] = None,
    output_path: str = None,
    error_message: str = None
) -> Optional[Simulation]:
    simulation = get_simulation_by_job_id(db, job_id)
    if not simulation:
        return None

    simulation.status = status
    if result_summary:
        simulation.result_summary = result_summary
    if output_path:
        simulation.output_file_path = output_path
    if error_message:
        simulation.error_message = error_message

    if status in ["RUNNING"] and not simulation.started_at:
        simulation.started_at = datetime.utcnow()
    if status in ["COMPLETED", "FAILED"] and not simulation.completed_at:
        simulation.completed_at = datetime.utcnow()

    db.commit()
    db.refresh(simulation)
    return simulation


# ============================================================
# SYNC - VERSIONING
# ============================================================

def get_max_version(db: Session, table_name: str) -> int:
    """Retourne la version maximale d'une table (pour delta sync)."""
    from sqlalchemy import func
    if table_name == "regards":
        result = db.query(func.max(Regard.version)).scalar()
    elif table_name == "conduites":
        result = db.query(func.max(Canalisation.version)).scalar()
    elif table_name == "rejets":
        result = db.query(func.max(Rejet.version)).scalar()
    else:
        result = 0
    return result or 0


def get_changes_since(
    db: Session,
    table_name: str,
    since_version: int,
    limit: int = 1000
) -> List[Dict[str, Any]]:
    """Récupère les changements depuis une version donnée (pour delta sync)."""
    # Mapping des noms de tables vers modèles
    table_map = {
        "regards": Regard,
        "conduites": Canalisation,
        "rejets": Rejet
    }
    model = table_map.get(table_name)
    if not model:
        return []

    query = db.query(model).filter(model.version > since_version)
    records = query.order_by(model.version).limit(limit).all()
    return [record.to_dict() for record in records]
