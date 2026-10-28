# -*- coding: utf-8 -*-
"""
Module api.crud : Opérations CRUD (Create, Read, Update, Delete) multi-tenant pour SWMM Platform SaaS.
Garantit l'isolation stricte par org_id (Section 3 & ADR 0002) tout en conservant la compatibilité
avec les appels historiques sans org_id.

Auteur : Dr Abdelhakim Kellouche / Antigravity
Date : Octobre 2026
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, select, func
from datetime import datetime, timezone

from api.models import (
    Regard,
    Canalisation,
    Rejet,
    Cluster,
    Simulation,
    AuditLog,
    Project,
)


def _utc_now():
    return datetime.now(timezone.utc)


def log_audit(
    db: Session,
    action: str,
    org_id: Optional[str] = None,
    user_id: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Enregistre une trace d'audit immuable et cloisonnée."""
    try:
        log = AuditLog(
            org_id=org_id or "system",
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id else None,
            details=details or {},
        )
        db.add(log)
        db.commit()
    except Exception:
        db.rollback()


# ============================================================
# REGARDS (NŒUDS DU RÉSEAU)
# ============================================================

def get_regard(db: Session, regard_id: Any, org_id: Optional[str] = None) -> Optional[Regard]:
    """Récupère un regard par son identifiant unique, avec filtre org_id si spécifié."""
    query = db.query(Regard).filter(Regard.id == regard_id)
    if org_id:
        query = query.filter(Regard.org_id == org_id)
    return query.first()


def get_regard_by_code(db: Session, code: str, org_id: Optional[str] = None) -> Optional[Regard]:
    """Récupère un regard par son code métier."""
    query = db.query(Regard).filter(Regard.code == code)
    if org_id:
        query = query.filter(Regard.org_id == org_id)
    return query.first()


def get_regards(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    commune: Optional[str] = None,
    cluster_id: Optional[Any] = None,
    org_id: Optional[str] = None,
    network_id: Optional[str] = None,
) -> List[Regard]:
    """Liste les regards avec pagination et filtres spatiaux/tenant."""
    query = db.query(Regard)
    if org_id:
        query = query.filter(Regard.org_id == org_id)
    if network_id:
        query = query.filter(Regard.network_id == network_id)
    if commune:
        query = query.filter(Regard.commune.ilike(f"%{commune}%"))
    if cluster_id:
        query = query.filter(Regard.cluster_id == cluster_id)
    return query.offset(skip).limit(limit).all()


def create_regard(
    db: Session,
    regard_data: Dict[str, Any],
    user_id: Optional[str] = None,
    org_id: Optional[str] = None,
) -> Regard:
    """Crée un nouveau regard dans l'organisation active."""
    existing = get_regard_by_code(db, regard_data["code"], org_id=org_id)
    if existing:
        raise ValueError(f"Un regard avec le code '{regard_data['code']}' existe déjà.")

    valid_keys = [c.key for c in Regard.__table__.columns]
    filtered_data = {k: v for k, v in regard_data.items() if k in valid_keys}

    if org_id and "org_id" in valid_keys:
        filtered_data["org_id"] = org_id

    regard = Regard(**filtered_data)
    db.add(regard)
    db.commit()
    db.refresh(regard)

    log_audit(
        db=db,
        action="regard.create",
        org_id=org_id,
        user_id=user_id,
        target_type="regard",
        target_id=regard.id,
        details={"code": regard.code, "commune": getattr(regard, "commune", None)},
    )
    return regard


def update_regard(
    db: Session,
    regard_id: Any,
    update_data: Dict[str, Any],
    user_id: Optional[str] = None,
    org_id: Optional[str] = None,
) -> Optional[Regard]:
    """Met à jour un regard existant."""
    regard = None
    if isinstance(regard_id, (int, str)):
        regard = get_regard(db, regard_id, org_id=org_id)
    if not regard:
        regard = get_regard_by_code(db, str(regard_id), org_id=org_id)

    if not regard:
        return None

    old_values = regard.to_dict() if hasattr(regard, "to_dict") else {}

    for field, value in update_data.items():
        if hasattr(regard, field) and value is not None and field not in ("id", "org_id"):
            setattr(regard, field, value)

    if hasattr(regard, "version"):
        regard.version = (regard.version or 0) + 1
    if hasattr(regard, "last_modified"):
        regard.last_modified = _utc_now()
    if hasattr(regard, "modified_by"):
        regard.modified_by = user_id

    db.commit()
    db.refresh(regard)

    log_audit(
        db=db,
        action="regard.update",
        org_id=org_id or getattr(regard, "org_id", None),
        user_id=user_id,
        target_type="regard",
        target_id=regard.id,
        details={"updates": update_data, "old": old_values},
    )
    return regard


def delete_regard(
    db: Session,
    regard_id: Any,
    user_id: Optional[str] = None,
    org_id: Optional[str] = None,
) -> bool:
    """Supprime un regard."""
    regard = get_regard(db, regard_id, org_id=org_id)
    if not regard:
        return False

    old_id = regard.id
    db.delete(regard)
    db.commit()

    log_audit(
        db=db,
        action="regard.delete",
        org_id=org_id,
        user_id=user_id,
        target_type="regard",
        target_id=old_id,
    )
    return True


# ============================================================
# CANALISATIONS (CONDUITES DU RÉSEAU)
# ============================================================

def get_canalisation(db: Session, canalisation_id: Any, org_id: Optional[str] = None) -> Optional[Canalisation]:
    """Récupère une canalisation par ID."""
    query = db.query(Canalisation).filter(Canalisation.id == canalisation_id)
    if org_id:
        query = query.filter(Canalisation.org_id == org_id)
    return query.first()


def get_canalisation_by_fid(db: Session, fid: str, org_id: Optional[str] = None) -> Optional[Canalisation]:
    """Récupère une conduite par son identifiant SIG / FID."""
    query = db.query(Canalisation).filter(Canalisation.fid == fid)
    if org_id:
        query = query.filter(Canalisation.org_id == org_id)
    return query.first()


def get_canalisations(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    cluster_id: Optional[Any] = None,
    org_id: Optional[str] = None,
    network_id: Optional[str] = None,
) -> List[Canalisation]:
    """Liste les canalisations avec pagination et filtres."""
    query = db.query(Canalisation)
    if org_id:
        query = query.filter(Canalisation.org_id == org_id)
    if network_id:
        query = query.filter(Canalisation.network_id == network_id)
    if cluster_id:
        query = query.filter(Canalisation.cluster_id == cluster_id)
    return query.offset(skip).limit(limit).all()


def create_canalisation(
    db: Session,
    canalisation_data: Dict[str, Any],
    user_id: Optional[str] = None,
    org_id: Optional[str] = None,
) -> Canalisation:
    """Crée une nouvelle canalisation."""
    existing = get_canalisation_by_fid(db, canalisation_data["fid"], org_id=org_id)
    if existing:
        raise ValueError(f"Une canalisation avec le fid '{canalisation_data['fid']}' existe déjà.")

    valid_keys = [c.key for c in Canalisation.__table__.columns]
    filtered_data = {k: v for k, v in canalisation_data.items() if k in valid_keys}

    if org_id and "org_id" in valid_keys:
        filtered_data["org_id"] = org_id

    canalisation = Canalisation(**filtered_data)
    db.add(canalisation)
    db.commit()
    db.refresh(canalisation)

    log_audit(
        db=db,
        action="canalisation.create",
        org_id=org_id,
        user_id=user_id,
        target_type="canalisation",
        target_id=canalisation.id,
        details={"fid": canalisation.fid},
    )
    return canalisation


def update_canalisation(
    db: Session,
    canalisation_id: Any,
    update_data: Dict[str, Any],
    user_id: Optional[str] = None,
    org_id: Optional[str] = None,
) -> Optional[Canalisation]:
    """Met à jour une canalisation."""
    canalisation = get_canalisation(db, canalisation_id, org_id=org_id)
    if not canalisation:
        canalisation = get_canalisation_by_fid(db, str(canalisation_id), org_id=org_id)

    if not canalisation:
        return None

    old_values = canalisation.to_dict() if hasattr(canalisation, "to_dict") else {}

    for field, value in update_data.items():
        if hasattr(canalisation, field) and value is not None and field not in ("id", "org_id"):
            setattr(canalisation, field, value)

    if hasattr(canalisation, "version"):
        canalisation.version = (canalisation.version or 0) + 1
    if hasattr(canalisation, "last_modified"):
        canalisation.last_modified = _utc_now()
    if hasattr(canalisation, "modified_by"):
        canalisation.modified_by = user_id

    db.commit()
    db.refresh(canalisation)

    log_audit(
        db=db,
        action="canalisation.update",
        org_id=org_id or getattr(canalisation, "org_id", None),
        user_id=user_id,
        target_type="canalisation",
        target_id=canalisation.id,
        details={"updates": update_data, "old": old_values},
    )
    return canalisation


def delete_canalisation(
    db: Session,
    canalisation_id: Any,
    user_id: Optional[str] = None,
    org_id: Optional[str] = None,
) -> bool:
    """Supprime une canalisation."""
    canalisation = get_canalisation(db, canalisation_id, org_id=org_id)
    if not canalisation:
        return False

    old_id = canalisation.id
    db.delete(canalisation)
    db.commit()

    log_audit(
        db=db,
        action="canalisation.delete",
        org_id=org_id,
        user_id=user_id,
        target_type="canalisation",
        target_id=old_id,
    )
    return True


# ============================================================
# CLUSTERS & SOUS-BASSINS TOPOLOGIQUES
# ============================================================

def get_cluster(db: Session, cluster_id: Any, org_id: Optional[str] = None) -> Optional[Cluster]:
    """Récupère un cluster par ID."""
    query = db.query(Cluster).filter(Cluster.id == cluster_id)
    if org_id:
        query = query.filter(Cluster.org_id == org_id)
    return query.first()


def get_clusters(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    org_id: Optional[str] = None,
    network_id: Optional[str] = None,
) -> List[Cluster]:
    """Liste les clusters."""
    query = db.query(Cluster)
    if org_id:
        query = query.filter(Cluster.org_id == org_id)
    if network_id:
        query = query.filter(Cluster.network_id == network_id)
    return query.offset(skip).limit(limit).all()


def create_cluster(
    db: Session,
    cluster_data: Dict[str, Any],
    org_id: Optional[str] = None,
) -> Cluster:
    """Enregistre un cluster/sous-bassin."""
    if org_id:
        cluster_data["org_id"] = org_id
    cluster = Cluster(**cluster_data)
    db.add(cluster)
    db.commit()
    db.refresh(cluster)
    return cluster


# ============================================================
# SIMULATIONS HYDRAULIQUES SWMM 5.2
# ============================================================

def get_simulation(db: Session, simulation_id: Any, org_id: Optional[str] = None) -> Optional[Simulation]:
    """Récupère une simulation par son ID."""
    query = db.query(Simulation).filter(Simulation.id == simulation_id)
    if org_id:
        query = query.filter(Simulation.org_id == org_id)
    return query.first()


def get_simulations(
    db: Session,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    org_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> List[Simulation]:
    """Liste les simulations de l'organisation."""
    query = db.query(Simulation)
    if org_id:
        query = query.filter(Simulation.org_id == org_id)
    if project_id:
        query = query.filter(Simulation.project_id == project_id)
    if status:
        query = query.filter(Simulation.status == status)
    return query.order_by(Simulation.created_at.desc()).offset(skip).limit(limit).all()


def create_simulation(
    db: Session,
    cluster_id: Optional[int] = None,
    job_id: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
    created_by: Optional[str] = None,
    org_id: Optional[str] = None,
    project_id: Optional[str] = None,
    name: Optional[str] = None,
    scenario_pluie: str = "pluie_decennale",
    duree_heures: float = 24.0,
) -> Simulation:
    """Crée un enregistrement de simulation."""
    import uuid
    sim = Simulation(
        id=job_id or str(uuid.uuid4()),
        org_id=org_id,
        project_id=project_id,
        name=name or f"Simulation {scenario_pluie}",
        status="pending",
        scenario_pluie=scenario_pluie,
        duree_heures=duree_heures,
        summary_kpis={"cluster_id": cluster_id, "parameters": parameters or {}},
    )
    db.add(sim)
    db.commit()
    db.refresh(sim)
    return sim


def get_simulation_by_job_id(
    db: Session,
    job_id: str,
    org_id: Optional[str] = None,
) -> Optional[Simulation]:
    """Récupère une simulation par son job_id."""
    query = db.query(Simulation).filter(Simulation.id == job_id)
    if org_id:
        query = query.filter(Simulation.org_id == org_id)
    return query.first()


# ============================================================
# SYNCHRONISATION DELTA & VERSIONING
# ============================================================

def get_max_version(db: Session, table_name: str, org_id: Optional[str] = None) -> int:
    """Retourne la version maximale d'une couche pour le calcul du delta."""
    table_map = {
        "regards": Regard,
        "conduites": Canalisation,
        "rejets": Rejet,
    }
    model = table_map.get(table_name)
    if not model or not hasattr(model, "version"):
        return 0

    query = db.query(func.max(model.version))
    if org_id and hasattr(model, "org_id"):
        query = query.filter(model.org_id == org_id)
    result = query.scalar()
    return result or 0


def get_changes_since(
    db: Session,
    table_name: str,
    since_version: int,
    limit: int = 1000,
    org_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Récupère les objets modifiés depuis since_version."""
    table_map = {
        "regards": Regard,
        "conduites": Canalisation,
        "rejets": Rejet,
    }
    model = table_map.get(table_name)
    if not model:
        return []

    query = db.query(model).filter(model.version > since_version)
    if org_id and hasattr(model, "org_id"):
        query = query.filter(model.org_id == org_id)

    records = query.order_by(model.version).limit(limit).all()
    return [record.to_dict() if hasattr(record, "to_dict") else {} for record in records]
