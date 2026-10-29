# -*- coding: utf-8 -*-
"""
Module api.routes.auth : Routes d'authentification, de gestion de session et de clés d'API.
Inspiré et calqué sur l'architecture de Pilotage-Réseau-AEP.
Conforme à ADR 0001 (Authentification FastAPI, Argon2id et Double Session JWT/Cookie).

Auteur : Dr Abdelhakim Kellouche / Antigravity
Date : Octobre 2026
"""

from datetime import datetime, timezone, timedelta
import os
import secrets
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Query
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import User, Organization, Membership, ApiKey
from api.core.mailer import send_activation_email
from api.core.auth import (
    create_user_with_org,
    check_user_credentials,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_api_key,
    is_academic_email,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
from api.core.security import get_tenant_context, require_role, TenantContext
from api.core.quotas import (
    normalize_plan_name,
    get_organization_features,
    get_trial_status,
)
from api.schemas_auth import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    RefreshTokenRequest,
    UserSummary,
    OrgSummary,
    ApiKeyCreateRequest,
    ApiKeySummary,
    ApiKeyCreatedResponse,
    UserMeResponse,
    VerifyCodeRequest,
    ResendCodeRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentification & Multi-Tenant"])


def _set_auth_cookies(response: Response, access_token: str, refresh_token: Optional[str] = None):
    """Injecte les cookies de session HTTP-Only sécurisés."""
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=False,  # Permet le test sur HTTP localement, activé par proxy TLS en production
    )
    if refresh_token:
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
            httponly=True,
            samesite="lax",
            secure=False,
        )


def _clear_auth_cookies(response: Response):
    """Supprime les cookies de session."""
    response.delete_cookie(key="access_token")
    response.delete_cookie(key="refresh_token")


@router.get("/check-email")
def check_email(
    email: str = Query(..., description="Adresse email à vérifier"),
    db: Session = Depends(get_db),
):
    """Vérifie si une adresse email est déjà enregistrée en base de données."""
    clean_email = email.strip().lower()
    if not clean_email or "@" not in clean_email:
        return {"exists": False}
    user = db.execute(select(User).where(User.email == clean_email)).scalar_one_or_none()
    return {"exists": user is not None}


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Crée un nouvel utilisateur et son organisation locataire (Workspace).
    Attribution automatique du rôle 'owner' sur la nouvelle organisation.
    """
    clean_plan = normalize_plan_name(payload.billing_plan)

    # Règle d'éligibilité stricte pour l'offre éducation
    if clean_plan == "education" and not is_academic_email(payload.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "L'offre Académique & Recherche requiert impérativement une adresse e-mail institutionnelle "
                "universitaire reconnue (.univ.dz, .edu, polytech...). "
                "Pour les adresses professionnelles ou de bureaux d'études, veuillez sélectionner la formule BET ou Démo."
            ),
        )

    code = f"{secrets.randbelow(1000000):06d}"

    try:
        user, org, membership = create_user_with_org(
            session=db,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            org_name=payload.org_name or "",
            role="owner",
            billing_plan=clean_plan,
            org_type=payload.org_type,
            is_active=True,
            email_verified=False,
        )
        user.verification_code = code
        user.verification_code_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        db.commit()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Expédition de l'email d'activation (réel ou simulé)
    send_activation_email(user.email, code, user.full_name)

    token_data = {"sub": user.id, "email": user.email, "org_id": org.id, "role": membership.role}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    _set_auth_cookies(response, access_token, refresh_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserSummary(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            is_superadmin=user.is_superadmin,
            email_verified=user.email_verified,
        ),
        organization=OrgSummary(
            id=org.id,
            name=org.name,
            slug=org.slug,
            billing_plan=org.billing_plan,
            billing_status=org.billing_status,
            org_type=org.org_type,
            role=membership.role,
        ),
        requires_verification=True,
        dev_code=code,
    )


@router.post("/verify-email", response_model=TokenResponse)
def verify_email_code(
    payload: VerifyCodeRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Vérifie le code d'activation à 6 chiffres reçu par e-mail.
    Active le compte utilisateur et délivre les jetons de session.
    """
    clean_email = payload.email.strip().lower()
    user = db.execute(select(User).where(User.email == clean_email)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")

    if not user.email_verified:
        now = datetime.now(timezone.utc)
        if not user.verification_code or user.verification_code != payload.code.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Code d'activation incorrect. Veuillez vérifier votre boîte de réception.",
            )
        # Note : en sqlite datetime peut être naïf ou conscient, gestion robuste :
        exp = user.verification_code_expires_at
        if exp and exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp and exp < now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ce code d'activation a expiré. Veuillez demander un nouveau code.",
            )

        user.email_verified = True
        user.verification_code = None
        user.verification_code_expires_at = None
        db.commit()

    # Récupération de l'organisation
    memberships = user.memberships
    if not memberships:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Aucune organisation active rattachée.")
    primary_membership = memberships[0]
    org = db.execute(select(Organization).where(Organization.id == primary_membership.org_id)).scalar_one()

    token_data = {"sub": user.id, "email": user.email, "org_id": org.id, "role": primary_membership.role}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    _set_auth_cookies(response, access_token, refresh_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserSummary(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            is_superadmin=user.is_superadmin,
            email_verified=user.email_verified,
        ),
        organization=OrgSummary(
            id=org.id,
            name=org.name,
            slug=org.slug,
            billing_plan=org.billing_plan,
            billing_status=org.billing_status,
            org_type=org.org_type,
            role=primary_membership.role,
        ),
        requires_verification=False,
    )


@router.post("/resend-code")
def resend_verification_code(
    payload: ResendCodeRequest,
    db: Session = Depends(get_db),
):
    """Génère et renvoie un nouveau code d'activation par e-mail."""
    clean_email = payload.email.strip().lower()
    user = db.execute(select(User).where(User.email == clean_email)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")

    if user.email_verified:
        return {"status": "already_verified", "message": "Cette adresse email est déjà validée."}

    code = f"{secrets.randbelow(1000000):06d}"
    user.verification_code = code
    user.verification_code_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    db.commit()

    send_activation_email(user.email, code, user.full_name)

    return {
        "status": "ok",
        "message": "Un nouveau code d'activation a été envoyé par email.",
        "dev_code": code,
    }


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Authentifie l'utilisateur par e-mail et mot de passe (vérification Argon2id).
    Génère les jetons JWT et configure la session HTTP-Only.
    """
    user, auth_status = check_user_credentials(db, payload.email, payload.password)
    if auth_status in ("not_found", "invalid_password"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants incorrects.",
        )
    if auth_status == "inactive":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ce compte utilisateur est inactif ou désactivé.",
        )

    # Récupération de l'adhésion par défaut
    memberships = user.memberships
    if not memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Aucune organisation active rattachée à cet utilisateur.",
        )

    primary_membership = memberships[0]
    org = db.execute(select(Organization).where(Organization.id == primary_membership.org_id)).scalar_one_or_none()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organisation principale introuvable.",
        )

    token_data = {"sub": user.id, "email": user.email, "org_id": org.id, "role": primary_membership.role}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    _set_auth_cookies(response, access_token, refresh_token)

    dev_code = None
    if not user.email_verified:
        if not user.verification_code:
            code = f"{secrets.randbelow(1000000):06d}"
            user.verification_code = code
            user.verification_code_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
            db.commit()
            send_activation_email(user.email, code, user.full_name)
        dev_code = user.verification_code

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserSummary(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            is_superadmin=user.is_superadmin,
            email_verified=user.email_verified,
        ),
        organization=OrgSummary(
            id=org.id,
            name=org.name,
            slug=org.slug,
            billing_plan=org.billing_plan,
            billing_status=org.billing_status,
            org_type=org.org_type,
            role=primary_membership.role,
        ),
        requires_verification=not user.email_verified,
        dev_code=dev_code,
    )


@router.post("/refresh")
def refresh_token(
    request: Request,
    response: Response,
    payload: Optional[RefreshTokenRequest] = None,
    db: Session = Depends(get_db),
):
    """
    Renouvelle un jeton d'accès expiré à partir d'un jeton de rafraîchissement valide.
    """
    raw_refresh = None
    if payload and payload.refresh_token:
        raw_refresh = payload.refresh_token
    elif "refresh_token" in request.cookies:
        raw_refresh = request.cookies.get("refresh_token")

    if not raw_refresh:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Jeton de rafraîchissement manquant.",
        )

    decoded = decode_token(raw_refresh)
    if not decoded or decoded.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Jeton de rafraîchissement invalide ou expiré.",
        )

    user_id = decoded.get("sub")
    user = db.execute(select(User).where(User.id == user_id, User.is_active.is_(True))).scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur inactif ou introuvable.",
        )

    # Réémission d'un jeton d'accès court
    new_data = {
        "sub": user.id,
        "email": user.email,
        "org_id": decoded.get("org_id"),
        "role": decoded.get("role", "viewer"),
    }
    new_access_token = create_access_token(new_data)
    _set_auth_cookies(response, new_access_token)

    return {
        "access_token": new_access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/logout")
def logout(response: Response):
    """Déconnecte l'utilisateur et détruit les cookies de session."""
    _clear_auth_cookies(response)
    return {"status": "ok", "message": "Déconnexion réussie."}


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
