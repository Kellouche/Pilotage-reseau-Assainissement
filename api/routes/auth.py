# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-27
Objet : Endpoints d'authentification JWT, inscription, connexion et sessions
================================================================================
"""

from datetime import datetime, timezone, timedelta
import os
import secrets
import logging
from typing import List, Optional
from pydantic import BaseModel
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
    """Injecte les cookies de session sécurisés (valides 7 jours)."""
    cookie_max_age = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=cookie_max_age,
        httponly=False,  # Permet la synchronisation avec le JavaScript client
        samesite="lax",
        secure=False,
        path="/"
    )
    if refresh_token:
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            max_age=cookie_max_age,
            httponly=True,
            samesite="lax",
            secure=False,
            path="/"
        )


def _clear_auth_cookies(response: Response):
    """Supprime les cookies de session."""
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")


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

    # NOTE DE SÉCURITÉ : Aucun cookie de session ni jeton valide tant que l'email n'est pas activé
    _clear_auth_cookies(response)

    return TokenResponse(
        access_token="",
        refresh_token="",
        expires_in=0,
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
            detail="Identifiants incorrects. Veuillez vérifier vos accès ou créer un compte si ce n'est pas déjà fait.",
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

    # SÉCURITÉ : Si l'utilisateur n'a pas validé son email, bloquer tout jeton de session et exiger le code
    if not user.email_verified:
        now = datetime.now(timezone.utc)
        code = f"{secrets.randbelow(1000000):06d}"
        user.verification_code = code
        user.verification_code_expires_at = now + timedelta(minutes=15)
        db.commit()
        send_activation_email(user.email, code, user.full_name)

        # Détruire tout cookie résiduel dans le navigateur
        _clear_auth_cookies(response)

        return TokenResponse(
            access_token="",
            refresh_token="",
            expires_in=0,
            user=UserSummary(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                is_active=user.is_active,
                is_superadmin=user.is_superadmin,
                email_verified=False,
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
            requires_verification=True,
            dev_code=code,
        )

    # Utilisateur vérifié : émission des jetons de session et cookies sécurisés
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
            email_verified=True,
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
        dev_code=None,
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


