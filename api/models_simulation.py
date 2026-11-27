# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Modele ORM — simulations, versions GPKG, inspections, incidents (extrait de api/models.py)
================================================================================
"""

from datetime import datetime, timezone
import uuid
from typing import List, Optional, Dict, Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.database import Base
from api.models_core import _gen_uuid, _utc_now


class Simulation(Base):
    """Résultat d'une simulation hydraulique dynamique EPA SWMM 5.2."""
    __tablename__ = "simulations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    org_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(120), default="simulation_pluie", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="completed", nullable=False)  # running, completed, failed
    scenario_pluie: Mapped[str] = mapped_column(String(100), default="pluie_decennale", nullable=False)
    duree_heures: Mapped[float] = mapped_column(Float, default=24.0, nullable=False)
    # CONTRAT (3C.7.4) : champ historique à double sémantique —
    #   - nouvelles sims (sync ET celery) : chemin local du cache de
    #     calcul `.simulation_cache` (voie de travail, PAS une clé S3) ;
    #   - sims Celery historiques : clé ArtifactStore `.../summary.json` ;
    #   - l'autorité permanente est ResultStore `simulations/{id}/result.json`.
    # Ne jamais traiter cette valeur comme une clé S3 sans vérifier qu'il
    # s'agit d'une clé ArtifactStore (préfixe `{org_id}/`).
    results_s3_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    gpkg_version_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("gpkg_versions.id"), nullable=True)
    gpkg_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    bassin_ref: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    exutoire_noeud: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    summary_kpis: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    execution_time_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)

    project: Mapped[Optional["Project"]] = relationship("Project", back_populates="simulations")
    gpkg_version: Mapped[Optional["GpkgVersion"]] = relationship("GpkgVersion", foreign_keys=[gpkg_version_id])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "job_id": self.id,
            "org_id": self.org_id,
            "project_id": self.project_id,
            "cluster_id": (self.summary_kpis or {}).get("cluster_id"),
            "bassin_ref": self.bassin_ref,
            "exutoire_noeud": self.exutoire_noeud,
            "name": self.name,
            "status": self.status,
            "scenario_pluie": self.scenario_pluie,
            "duree_heures": self.duree_heures,
            "results_s3_key": self.results_s3_key,
            "summary_kpis": self.summary_kpis or {},
            "result_summary": self.summary_kpis or {},
            "execution_time_seconds": self.execution_time_seconds,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.created_at.isoformat() if self.status == "completed" and self.created_at else None,
        }

    __table_args__ = (
        Index("ix_simulations_org_created", "org_id", "created_at"),
        # Étape 3B : une version GPKG ne peut être référencée sans projet
        CheckConstraint(
            "gpkg_version_id IS NULL OR project_id IS NOT NULL",
            name="ck_sim_gpkg_version_requires_project",
        ),
    )


class GpkgVersion(Base):
    """
    Version immuable d'un GeoPackage projet (étape 3B).

    Une ligne = un contenu exact (sha256) pour un projet donné.
    storage_kind : 'ARTIFACT_STORE' (clé ArtifactStore) ou 'LEGACY_LOCAL'
    (chemin local enregistré sur place lors de la migration).
    Le statut UNAVAILABLE est dérivé à la lecture, jamais persisté.
    """
    __tablename__ = "gpkg_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    storage_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    filename_original: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    nb_regards: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    nb_conduites: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    created_by_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    project: Mapped["Project"] = relationship("Project", foreign_keys=[project_id])
    organization: Mapped["Organization"] = relationship("Organization", foreign_keys=[org_id])

    __table_args__ = (
        # Idempotence : même contenu pour un même projet = même version
        UniqueConstraint("project_id", "sha256", name="uq_gpkgver_project_sha"),
        # Support des FK composites (version_id, project_id) côté PostgreSQL
        UniqueConstraint("id", "project_id", name="uq_gpkgver_id_project"),
        Index("ix_gpkg_versions_sha256", "sha256"),
        Index("ix_gpkg_versions_org_project", "org_id", "project_id"),
    )


# ============================================================
# 3. MODÈLES TERRAIN & MOBILITÉ (Fiches d'Interventions)
# ============================================================

class Inspection(Base):
    """Fiche d'inspection terrain mobile (Offline-First)."""
    __tablename__ = "inspections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    org_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=True)
    network_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=True)
    object_type: Mapped[str] = mapped_column(String(50), nullable=False)  # regard, conduite, station, ouvrage
    object_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    etat: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    niveau_eau: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    obstruction: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    odeur: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    debordement: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    commentaires: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    photos: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    statut: Mapped[str] = mapped_column(String(50), default="À vérifier", nullable=False)
    date_inspection: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, nullable=False)
    inspecteur: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_modified: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, onupdate=_utc_now, nullable=False)

    project: Mapped[Optional["Project"]] = relationship("Project", foreign_keys=[network_id])
    organization: Mapped[Optional["Organization"]] = relationship("Organization", foreign_keys=[org_id])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "etat": self.etat,
            "niveau_eau": self.niveau_eau,
            "obstruction": self.obstruction,
            "odeur": self.odeur,
            "debordement": self.debordement,
            "commentaires": self.commentaires,
            "photos": self.photos,
            "statut": self.statut,
            "date_inspection": self.date_inspection.isoformat() if self.date_inspection else None,
            "inspecteur": self.inspecteur,
            "device_id": self.device_id,
            "version": self.version,
            "last_modified": self.last_modified.isoformat() if self.last_modified else None
        }


class Incident(Base):
    """Signalement d'incident d'assainissement géolocalisé (fuite, refoulement, casse)."""
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    org_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=True)
    network_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=True)
    type_incident: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    gravite: Mapped[str] = mapped_column(String(50), default="Moyenne", nullable=False)
    statut: Mapped[str] = mapped_column(String(50), default="Signalé", nullable=False)
    photos: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    date_signalement: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, nullable=False)
    signale_par: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_modified: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, onupdate=_utc_now, nullable=False)

    project: Mapped[Optional["Project"]] = relationship("Project", foreign_keys=[network_id])
    organization: Mapped[Optional["Organization"]] = relationship("Organization", foreign_keys=[org_id])

    @property
    def date_creation(self) -> datetime:
        return self.date_signalement

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type_incident": self.type_incident,
            "description": self.description,
            "longitude": self.longitude,
            "latitude": self.latitude,
            "gravite": self.gravite,
            "statut": self.statut,
            "photos": self.photos,
            "date_signalement": self.date_signalement.isoformat() if self.date_signalement else None,
            "signale_par": self.signale_par,
            "device_id": self.device_id,
            "version": self.version,
            "last_modified": self.last_modified.isoformat() if self.last_modified else None
        }


# ============================================================
# 3. APPORTS DE TEMPS SEC (DWF) — LOT P1.2
# ============================================================
