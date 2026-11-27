# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Modele ORM — projet et reseau physique (regards, conduites, rejets, clusters) (extrait de api/models.py)
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


class Project(Base):
    """Projet ou Réseau d'assainissement cloisonné par organisation (Tenant)."""
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(120), default=lambda: f"net-{uuid.uuid4().hex[:8]}", nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    commune: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_gpkg_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)  # Clé S3 du GeoPackage
    source_dem_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)   # Clé S3 du MNT raster
    # Pointeur souple vers gpkg_versions : PAS de ForeignKey ici — le cycle
    # projects <-> gpkg_versions (gpkg_versions.project_id -> projects.id)
    # rend le tri topologique SQLAlchemy impossible et produit des INSERT
    # dans le désordre (violation FK). L'intégrité est garantie côté service
    # et par les FK composites PostgreSQL (migration b2c3d4e5f6a7).
    gpkg_version_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)  # Version GPKG courante (étape 3B)
    nodes_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pipes_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    outfalls_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Paramétrage du garde-fou hydraulicien (seuils, preset, profil réseau)
    # — politique d'acceptation propre au projet, nullable = défauts.
    garde_fou_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_by_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="projects")
    simulations: Mapped[List["Simulation"]] = relationship("Simulation", back_populates="project", cascade="all, delete-orphan")
    apports_dwf: Mapped[List["ApportDwf"]] = relationship("ApportDwf", back_populates="project", cascade="all, delete-orphan")
    apports_dwf_history: Mapped[List["ApportDwfHistory"]] = relationship("ApportDwfHistory", back_populates="project")
    cotes_validations: Mapped[List["NodeCoteValidation"]] = relationship("NodeCoteValidation", back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_project_org_slug"),
        Index("ix_project_org_archived", "org_id", "is_archived"),
    )

    def __repr__(self) -> str:
        return f"<Project {self.slug} (org={self.org_id})>"


# Alias de compatibilité
Network = Project


class Regard(Base):
    """Nœud / Regard d'assainissement avec cotes et géométrie."""
    __tablename__ = "regards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    org_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=True)
    network_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    nom_voie: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    commune: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    profondeur: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    diametre: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    type_res: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    profrad: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hfermsol: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cluster_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("clusters.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_modified: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, onupdate=_utc_now, nullable=False)
    modified_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, nullable=False)

    cluster: Mapped[Optional["Cluster"]] = relationship("Cluster", back_populates="regards")
    project: Mapped[Optional["Project"]] = relationship("Project", foreign_keys=[network_id])
    organization: Mapped[Optional["Organization"]] = relationship("Organization", foreign_keys=[org_id])

    __table_args__ = (
        Index("ix_regards_org_code", "org_id", "code"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "code": self.code,
            "nom_voie": self.nom_voie,
            "commune": self.commune,
            "profondeur": self.profondeur,
            "diametre": self.diametre,
            "longitude": self.longitude,
            "latitude": self.latitude,
            "cluster_id": self.cluster_id,
            "version": self.version,
            "last_modified": self.last_modified.isoformat() if self.last_modified else None,
            "modified_by": self.modified_by
        }


class Conduite(Base):
    """Canalisation / Tronçon gravitaire reliant deux regards."""
    __tablename__ = "conduites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    org_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=True)
    network_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=True)
    fid: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    nom_voie: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    diametre: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    materiau: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    longueur: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prof_fe_am: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prof_fe_av: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fonction_mt: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    id_amont: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True)
    id_aval: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True)
    forme_sect: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    hauteur: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gdebase: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    geometry_wkt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cluster_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("clusters.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_modified: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, onupdate=_utc_now, nullable=False)
    modified_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, nullable=False)

    cluster: Mapped[Optional["Cluster"]] = relationship("Cluster", back_populates="conduites")
    project: Mapped[Optional["Project"]] = relationship("Project", foreign_keys=[network_id])
    organization: Mapped[Optional["Organization"]] = relationship("Organization", foreign_keys=[org_id])

    __table_args__ = (
        Index("ix_conduites_org_amont_aval", "org_id", "id_amont", "id_aval"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "fid": self.fid,
            "nom_voie": self.nom_voie,
            "diametre": self.diametre,
            "materiau": self.materiau,
            "longueur": self.longueur,
            "prof_fe_am": self.prof_fe_am,
            "prof_fe_av": self.prof_fe_av,
            "fonction_mt": self.fonction_mt,
            "id_amont": self.id_amont,
            "id_aval": self.id_aval,
            "cluster_id": self.cluster_id,
            "version": self.version,
            "last_modified": self.last_modified.isoformat() if self.last_modified else None,
            "modified_by": self.modified_by
        }


# Alias officiel de compatibilité
Canalisation = Conduite


class Rejet(Base):
    """Exutoire naturel ou point de décharge du réseau (Outfall)."""
    __tablename__ = "rejets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    org_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=True)
    network_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=True)
    nom: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    commune: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    nom_voie: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cluster_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("clusters.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_modified: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, onupdate=_utc_now, nullable=False)
    modified_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, nullable=False)

    cluster: Mapped[Optional["Cluster"]] = relationship("Cluster", back_populates="rejets")
    project: Mapped[Optional["Project"]] = relationship("Project", foreign_keys=[network_id])
    organization: Mapped[Optional["Organization"]] = relationship("Organization", foreign_keys=[org_id])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "nom": self.nom,
            "commune": self.commune,
            "nom_voie": self.nom_voie,
            "longitude": self.longitude,
            "latitude": self.latitude,
            "cluster_id": self.cluster_id,
            "version": self.version,
            "last_modified": self.last_modified.isoformat() if self.last_modified else None,
            "modified_by": self.modified_by
        }


class Cluster(Base):
    """Bassin versant ou sous-réseau connexe gravitaire."""
    __tablename__ = "clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    org_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=True)
    network_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=True)
    nom: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    exutoire_noeud: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bassin_ref: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)  # Référence métier stable : "exutoire:<node_id>"
    nb_conduites: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)
    nb_noeuds: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)
    longueur_totale: Mapped[Optional[float]] = mapped_column(Float, default=0.0, nullable=True)
    diametre_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    diametre_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    diametre_moy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    nb_regards: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)
    nb_stations: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)
    nb_ouvrages: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)
    geometry_wkt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_recalculated: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, nullable=False)

    regards: Mapped[List["Regard"]] = relationship("Regard", back_populates="cluster")
    conduites: Mapped[List["Conduite"]] = relationship("Conduite", back_populates="cluster")
    rejets: Mapped[List["Rejet"]] = relationship("Rejet", back_populates="cluster")
    project: Mapped[Optional["Project"]] = relationship("Project", foreign_keys=[network_id])
    organization: Mapped[Optional["Organization"]] = relationship("Organization", foreign_keys=[org_id])

    __table_args__ = (
        Index("uq_cluster_network_bassin_ref", "network_id", "bassin_ref", unique=True),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "nom": self.nom,
            "exutoire_noeud": self.exutoire_noeud,
            "bassin_ref": self.bassin_ref,
            "nb_conduites": self.nb_conduites,
            "nb_noeuds": self.nb_noeuds,
            "longueur_totale": self.longueur_totale,
            "diametre_min": self.diametre_min,
            "diametre_max": self.diametre_max,
            "diametre_moy": self.diametre_moy,
            "geometry_wkt": self.geometry_wkt,
            "version": self.version,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
