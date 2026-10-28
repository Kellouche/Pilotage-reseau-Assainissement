# -*- coding: utf-8 -*-
"""
Modèles de données SQLAlchemy 2.0 pour SWMM Platform SaaS.
Architecture multi-tenant avec isolation stricte par org_id et modèles du réseau d'assainissement.
Inspiré de l'architecture HydroPilot AEP (Phase 1 — Tenancy & Persistance).

Auteur : Dr Abdelhakim Kellouche / Antigravity
Date : Octobre 2026
"""

from datetime import datetime, timezone
import uuid
from typing import List, Optional, Dict, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.database import Base


def _gen_uuid() -> str:
    """Génère un UUID v4 standard sous forme de chaîne."""
    return str(uuid.uuid4())


def _utc_now() -> datetime:
    """Retourne l'horodatage UTC actuel compatible Python 3.12+."""
    return datetime.now(timezone.utc)


# ============================================================
# 1. SOCLE SAAS MULTI-TENANT & GOUVERNANCE (Inspiré AEP)
# ============================================================

class Organization(Base):
    """Organisation cliente ou collectivité abonnée (Tenant racine)."""
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    billing_plan: Mapped[str] = mapped_column(String(50), default="demo", nullable=False)  # demo, education, bet, exploitation
    billing_status: Mapped[str] = mapped_column(String(50), default="trial", nullable=False)  # trial, active, suspended, expired
    license_valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    org_type: Mapped[str] = mapped_column(String(50), default="bet", nullable=False)  # bet, exploitation, education
    billing_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)

    # Relations
    memberships: Mapped[List["Membership"]] = relationship("Membership", back_populates="organization", cascade="all, delete-orphan")
    projects: Mapped[List["Project"]] = relationship("Project", back_populates="organization", cascade="all, delete-orphan")
    api_keys: Mapped[List["ApiKey"]] = relationship("ApiKey", back_populates="organization", cascade="all, delete-orphan")
    jobs: Mapped[List["Job"]] = relationship("Job", back_populates="organization", cascade="all, delete-orphan")
    purchase_orders: Mapped[List["PurchaseOrder"]] = relationship("PurchaseOrder", back_populates="organization", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Organization {self.slug} (plan={self.billing_plan})>"


class User(Base):
    """Compte utilisateur applicatif avec authentification Argon2id."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locale: Mapped[str] = mapped_column(String(10), default="fr", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)

    # Relations
    memberships: Mapped[List["Membership"]] = relationship("Membership", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User {self.email} (superadmin={self.is_superadmin})>"


class Membership(Base):
    """Liaison Utilisateur <-> Organisation avec rôle RBAC."""
    __tablename__ = "memberships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="engineer", nullable=False)  # owner, admin, engineer, field_operator, viewer
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="memberships")
    user: Mapped["User"] = relationship("User", back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("org_id", "user_id", name="uq_membership_org_user"),
    )

    def __repr__(self) -> str:
        return f"<Membership user={self.user_id} org={self.org_id} role={self.role}>"


class ApiKey(Base):
    """Clé d'API d'organisation pour accès programmatique ou machine-to-machine."""
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)  # ex: sp_live_a1b2...
    name: Mapped[str] = mapped_column(String(120), default="Default Key", nullable=False)
    scopes: Mapped[str] = mapped_column(String(255), default="read", nullable=False)  # read, write, admin
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="api_keys")

    @property
    def label(self) -> str:
        return self.name

    @label.setter
    def label(self, val: str) -> None:
        self.name = val


class PurchaseOrder(Base):
    """
    Bon de Commande Administratif B2B/B2G & Marché Public (ONA, Régies d'eau, BET).
    Permet la validation des licences SWMM Platform SaaS en Dinar Algérien (DZD) ou Euros (EUR).
    """
    __tablename__ = "purchase_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    order_ref: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)  # ex: "BC-2026-ONA-0012"
    client_type: Mapped[str] = mapped_column(String(50), default="bet", nullable=False)  # ona, seaal, ade, bet, universite, autre
    entity_name: Mapped[str] = mapped_column(String(150), nullable=False)  # ex: "Office National de l'Assainissement - Zone Centre"
    contact_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    target_plan: Mapped[str] = mapped_column(String(50), default="bet", nullable=False)  # bet, exploitation, education
    duration_months: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    amount_dzd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True, nullable=False)  # pending, approved, rejected, expired
    po_document_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)  # Clé S3 du document scanné
    license_token: Mapped[Optional[str]] = mapped_column(String(128), unique=True, index=True, nullable=True)  # ex: SP-LIC-BET-...
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    validated_by_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="purchase_orders")
    validator: Mapped[Optional["User"]] = relationship("User", foreign_keys=[validated_by_id])

    __table_args__ = (
        Index("ix_purchase_order_org_status", "org_id", "status"),
    )


class Job(Base):
    """Tâche d'arrière-plan asynchrone Celery (simulation SWMM 5.2, analyse MNT, ingestion)."""
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    network_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)  # simulation_swmm, analyse_mnt, audit_qualite, export_pdf
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)  # pending, running, completed, failed
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0 à 100%
    message: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_refs: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="jobs")


class AuditLog(Base):
    """Journal d'audit pour traçabilité légale, sécurité et conformité."""
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    org_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)  # network.import, anomaly.correct, terrain.sync, user.login
    target_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # regard, conduite, simulation, network
    target_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, index=True, nullable=False)


class UsageCounter(Base):
    """Compteurs d'utilisation mensuels pour le contrôle des quotas."""
    __tablename__ = "usage_counters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    metric: Mapped[str] = mapped_column(String(50), nullable=False)  # simulations_count, storage_bytes...
    value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("org_id", "period", "metric", name="uq_usage_counter_org_period_metric"),
    )


# ============================================================
# 2. MODÈLES DU RÉSEAU D'ASSAINISSEMENT (Multi-Tenant)
# ============================================================

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
    nodes_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pipes_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    outfalls_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="projects")
    simulations: Mapped[List["Simulation"]] = relationship("Simulation", back_populates="project", cascade="all, delete-orphan")

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

    __table_args__ = (
        Index("ix_regards_org_code", "org_id", "code"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
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

    __table_args__ = (
        Index("ix_conduites_org_amont_aval", "org_id", "id_amont", "id_aval"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "nom": self.nom,
            "exutoire_noeud": self.exutoire_noeud,
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
    results_s3_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    summary_kpis: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    execution_time_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)

    project: Mapped[Optional["Project"]] = relationship("Project", back_populates="simulations")

    __table_args__ = (
        Index("ix_simulations_org_created", "org_id", "created_at"),
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
