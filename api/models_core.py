# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Modele ORM — socle SaaS multi-tenant (orgs, users, jobs, audit) (extrait de api/models.py)
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
    verification_code: Mapped[Optional[str]] = mapped_column(String(6), nullable=True)
    verification_code_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
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
    Bon de Commande Administratif B2B/B2G & Marché Public (Entreprises, Régies d'eau, BET).
    Permet la validation des licences SWMM Platform SaaS en Dinar Algérien (DZD) ou Euros (EUR).
    """
    __tablename__ = "purchase_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    order_ref: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)  # ex: "BC-2026-BET-0012"
    client_type: Mapped[str] = mapped_column(String(50), default="bet", nullable=False)  # bet, entreprise, regie, universite, autre
    entity_name: Mapped[str] = mapped_column(String(150), nullable=False)  # ex: "Bureau d'Études VRD Hydraulique"
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "network_id": self.network_id,
            "project_id": self.network_id,
            "job_type": self.job_type,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "error_message": self.error_message,
            "result_refs": self.result_refs or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "user_id": self.user_id,
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "ip_address": self.ip_address,
            "details": self.details or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class UsageCounter(Base):
    """Compteurs d'utilisation mensuels pour le contrôle des quotas."""
    __tablename__ = "usage_counters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    metric: Mapped[str] = mapped_column(String(50), nullable=False)  # simulations_count, storage_bytes...
    value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)

    # Relationship explicite : sans elle, l'unit-of-work SQLAlchemy ignore la
    # FK de colonne et peut insérer avant organizations (violation FK).
    organization: Mapped["Organization"] = relationship("Organization")

    __table_args__ = (
        UniqueConstraint("org_id", "period", "metric", name="uq_usage_counter_org_period_metric"),
    )


# ============================================================
# 2. MODÈLES DU RÉSEAU D'ASSAINISSEMENT (Multi-Tenant)
# ============================================================
