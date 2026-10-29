# -*- coding: utf-8 -*-
"""
Module api.routes.organization : Gestion des membres, collaborateurs et invitations au sein du locataire.
Conforme à ADR 0001, ADR 0002 et Roadmap SaaS Phase 3.6.
Contrôle strict des quotas de collaborateurs autorisés selon le plan d'activité.

Auteur : Dr Abdelhakim Kellouche / Antigravity
Date : Octobre 2026
"""

from datetime import datetime
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, func, delete
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import Organization, Membership, User
from api.core.security import get_tenant_context, require_role, TenantContext
from api.core.quotas import get_plan_limits, check_members_count_quota, can_access_collaborators
from api.core.auth import hash_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/organization", tags=["Gestion d'Organisation & Équipe"])


# ============================================================
# SCHÉMAS
# ============================================================

class MemberSummary(BaseModel):
    user_id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    joined_at: datetime


class AddMemberRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=2)
    role: str = Field("engineer", description="owner, admin, engineer, field_operator, viewer")
    temp_password: Optional[str] = Field(None, min_length=8)


class UpdateRoleRequest(BaseModel):
    role: str = Field(..., description="owner, admin, engineer, field_operator, viewer")


# ============================================================
# ENDPOINTS
# ============================================================

@router.get("/collaborators", response_model=List[MemberSummary])
def list_collaborators(
    ctx: TenantContext = Depends(require_role("engineer")),
    db: Session = Depends(get_db),
):
    """Liste tous les membres rattachés à l'organisation active (isolation stricte par org_id)."""
    memberships = db.execute(
        select(Membership)
        .where(Membership.org_id == ctx.org_id)
        .order_by(Membership.created_at)
    ).scalars().all()

    results = []
    for m in memberships:
        user = db.get(User, m.user_id)
        if user:
            results.append(
                MemberSummary(
                    user_id=user.id,
                    email=user.email,
                    full_name=user.full_name,
                    role=m.role,
                    is_active=user.is_active,
                    joined_at=m.created_at,
                )
            )
    return results


@router.post("/collaborators", response_model=MemberSummary, status_code=status.HTTP_201_CREATED)
def add_collaborator(
    payload: AddMemberRequest,
    ctx: TenantContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Ajoute un nouveau collaborateur au sein de l'organisation.
    Vérifie le respect du quota d'utilisateurs autorisés par le plan de souscription.
    """
    # 1. Vérification du quota du plan
    can_add, err_msg = check_members_count_quota(db, ctx.org)
    if not can_add:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=err_msg or "Plafond de membres atteint pour cette organisation.",
        )

    clean_email = payload.email.strip().lower()

    # 2. Recherche ou création de l'utilisateur
    user = db.execute(select(User).where(User.email == clean_email)).scalar_one_or_none()
    if not user:
        initial_pwd = payload.temp_password or "SwmmPass2026!"
        user = User(
            email=clean_email,
            password_hash=hash_password(initial_pwd),
            full_name=payload.full_name.strip(),
            is_active=True,
            email_verified=True,
        )
        db.add(user)
        db.flush()

    # 3. Vérification de l'adhésion existante
    existing_mem = db.execute(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.org_id == ctx.org_id,
        )
    ).scalar_one_or_none()
    if existing_mem:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cet utilisateur est déjà membre de votre organisation.",
        )

    # 4. Création de l'adhésion
    valid_role = payload.role.lower()
    if valid_role not in ("owner", "admin", "engineer", "field_operator", "viewer"):
        valid_role = "engineer"

    membership = Membership(
        user_id=user.id,
        org_id=ctx.org_id,
        role=valid_role,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)

    return MemberSummary(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=membership.role,
        is_active=user.is_active,
        joined_at=membership.created_at,
    )


@router.delete("/collaborators/{user_id}")
def remove_collaborator(
    user_id: str,
    ctx: TenantContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Révoque un collaborateur de l'organisation.
    Empêche le propriétaire de se révoquer lui-même s'il est le seul gestionnaire.
    """
    if ctx.user and ctx.user.id == user_id:
        # Vérifier s'il reste d'autres admins ou owners
        other_admins = db.execute(
            select(func.count(Membership.id)).where(
                Membership.org_id == ctx.org_id,
                Membership.user_id != user_id,
                Membership.role.in_(["owner", "admin"]),
            )
        ).scalar() or 0
        if other_admins == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vous ne pouvez pas révoquer votre propre accès tant qu'aucun autre administrateur n'est désigné.",
            )

    membership = db.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.org_id == ctx.org_id,
        )
    ).scalar_one_or_none()

    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membre introuvable.")

    db.delete(membership)
    db.commit()
    return {"status": "ok", "message": "Collaborateur révoqué avec succès."}
