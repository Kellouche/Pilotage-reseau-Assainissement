# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Profil utilisateur, changement de mot de passe, endpoint /me et gestion
        des cles API (extrait de routes/auth.py)
================================================================================
"""

import logging
from typing import List, Optional

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import User, Organization, Membership, ApiKey
from api.core.security import get_tenant_context, require_role, TenantContext
from api.core.auth import generate_api_key
from api.core.quotas import (
    get_organization_features,
    get_trial_status,
)
from api.schemas_auth import (
    ApiKeyCreateRequest,
    ApiKeySummary,
    ApiKeyCreatedResponse,
    UserMeResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentification & Multi-Tenant"])


class ProfileUpdateRequest(BaseModel):
    full_name: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


@router.patch("/profile")
def update_user_profile(
    payload: ProfileUpdateRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Met à jour les informations du profil utilisateur connecté."""
    user = ctx.user
    if not user:
        raise HTTPException(status_code=401, detail="Non authentifié.")
    if not payload.full_name or not payload.full_name.strip():
        raise HTTPException(status_code=400, detail="Le nom complet ne peut pas être vide.")
    user.full_name = payload.full_name.strip()
    db.commit()
    db.refresh(user)
    return {
        "status": "ok",
        "message": "Profil mis à jour avec succès.",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name
        }
    }


@router.post("/change-password")
def change_user_password(
    payload: PasswordChangeRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Permet à l'utilisateur de modifier son mot de passe de connexion."""
    user = ctx.user
    if not user:
        raise HTTPException(status_code=401, detail="Non authentifié.")
    from api.core.auth import verify_password, hash_password
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Le mot de passe actuel renseigné est incorrect.")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="Le nouveau mot de passe doit comporter au moins 8 caractères.")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"status": "ok", "message": "Votre mot de passe a été modifié avec succès."}


@router.get("/me", response_model=UserMeResponse)
def get_current_user_profile(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Retourne le profil de l'utilisateur connecté, son organisation active,
    la liste de ses adhésions et l'ensemble de ses droits métier SaaS.
    """
    user = ctx.user
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Opération non supportée via clé d'API machine.",
        )

    # Rafraîchir les adhésions
    user_memberships = []
    for m in user.memberships:
        org_rel = db.execute(select(Organization).where(Organization.id == m.org_id)).scalar_one_or_none()
        user_memberships.append({
            "org_id": m.org_id,
            "org_name": org_rel.name if org_rel else "Inconnue",
            "org_slug": org_rel.slug if org_rel else "",
            "role": m.role,
            "billing_plan": org_rel.billing_plan if org_rel else "demo",
        })

    features = get_organization_features(ctx.org)
    trial_status = get_trial_status(ctx.org)

    return UserMeResponse(
        user=UserSummary(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            is_superadmin=user.is_superadmin,
        ),
        active_organization=OrgSummary(
            id=ctx.org.id,
            name=ctx.org.name,
            slug=ctx.org.slug,
            billing_plan=ctx.org.billing_plan,
            billing_status=ctx.org.billing_status,
            org_type=ctx.org.org_type,
            role=ctx.role,
        ),
        memberships=user_memberships,
        features=features,
        trial_status=trial_status,
    )


# ============================================================
# CLÉS D'API MACHINE-TO-MACHINE (M2M)
# ============================================================

@router.get("/api-keys", response_model=List[ApiKeySummary])
def list_api_keys(
    ctx: TenantContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Liste les clés d'API créées pour l'organisation active (réservé admin et owner).
    """
    keys = db.execute(
        select(ApiKey).where(ApiKey.org_id == ctx.org.id).order_by(ApiKey.created_at.desc())
    ).scalars().all()

    return [
        ApiKeySummary(
            id=k.id,
            label=k.label,
            prefix=k.prefix,
            scopes=k.scopes.split(",") if isinstance(k.scopes, str) else k.scopes,
            created_at=k.created_at,
            last_used_at=k.last_used_at,
        )
        for k in keys
    ]


@router.post("/api-keys", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_new_api_key(
    payload: ApiKeyCreateRequest,
    ctx: TenantContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Génère une nouvelle clé d'API Machine-to-Machine pour l'organisation active.
    Attention : la valeur secrète n'est transmise qu'une seule fois dans la réponse !
    """
    raw_key, prefix, key_hash = generate_api_key("sp_live")

    new_key = ApiKey(
        org_id=ctx.org.id,
        user_id=ctx.user.id if ctx.user else None,
        label=payload.label.strip(),
        prefix=prefix,
        key_hash=key_hash,
        scopes=",".join(payload.scopes) if isinstance(payload.scopes, list) else payload.scopes,
    )
    db.add(new_key)
    db.commit()
    db.refresh(new_key)

    scopes_list = new_key.scopes.split(",") if isinstance(new_key.scopes, str) else new_key.scopes

    return ApiKeyCreatedResponse(
        id=new_key.id,
        label=new_key.label,
        prefix=new_key.prefix,
        scopes=scopes_list,
        created_at=new_key.created_at,
        last_used_at=new_key.last_used_at,
        key=raw_key,
    )


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    key_id: str,
    ctx: TenantContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Révoque et supprime définitivement une clé d'API de l'organisation active.
    """
    key = db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.org_id == ctx.org.id)
    ).scalar_one_or_none()

    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clé d'API introuvable.",
        )

    db.delete(key)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
