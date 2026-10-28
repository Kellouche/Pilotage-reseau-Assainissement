# -*- coding: utf-8 -*-
"""
Module api.core.security : Dépendances de sécurité FastAPI, authentification et contrôle d'accès RBAC multi-tenant.
Inspiré et calqué sur l'architecture de Pilotage-Réseau-AEP (core.auth_decorators).
Conforme à ADR 0001 (Authentification & Isolation Multi-Tenant) et Section 3 (Règle d'or de cloisonnement).

Auteur : Dr Abdelhakim Kellouche / Antigravity
Date : Octobre 2026
"""

import logging
from typing import Optional, Tuple, Any, Callable
from fastapi import Request, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import User, Organization, Membership, Network, ApiKey
from api.core.auth import decode_token, authenticate_api_key
from api.core.quotas import check_feature_access

logger = logging.getLogger(__name__)

security_bearer = HTTPBearer(auto_error=False)

# Hiérarchie des rôles RBAC SWMM Platform
ROLE_HIERARCHY = {
    "viewer": 10,
    "field_operator": 15,
    "engineer": 20,
    "admin": 30,
    "owner": 40,
    "super_admin": 40,
}


def has_sufficient_role(current_role: str, required_role: str) -> bool:
    """Vérifie si current_role dispose d'au moins les privilèges de required_role."""
    curr = ROLE_HIERARCHY.get((current_role or "").lower(), 0)
    req = ROLE_HIERARCHY.get((required_role or "viewer").lower(), 10)
    return curr >= req


class TenantContext:
    """Contexte d'exécution multi-tenant pour la requête en cours."""
    def __init__(
        self,
        actor: Any,
        org: Organization,
        role: str,
        is_api_key: bool = False,
    ):
        self.actor = actor
        self.org = org
        self.role = role
        self.is_api_key = is_api_key

    @property
    def user(self) -> Optional[User]:
        return self.actor if isinstance(self.actor, User) else None

    @property
    def org_id(self) -> str:
        return self.org.id


def get_tenant_context(
    request: Request,
    auth_creds: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: Session = Depends(get_db),
) -> TenantContext:
    """
    Dépendance FastAPI principale qui résout l'acteur, l'organisation active et le rôle RBAC.
    Priorités :
    1. Header Authorization Bearer (clé API `sp_live_...` ou JWT).
    2. Cookie de session `access_token`.
    """
    token: Optional[str] = None
    if auth_creds and auth_creds.credentials:
        token = auth_creds.credentials.strip()
    elif "access_token" in request.cookies:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Non authentifié. Clé API Bearer ou jeton JWT requis.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 1. Cas Clé d'API Machine-to-Machine (sp_live_...)
    if token.startswith("sp_live_"):
        res = authenticate_api_key(db, token)
        if not res:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Clé d'API invalide ou révoquée.",
            )
        api_key, org = res
        role = "admin" if "admin" in api_key.scopes else "engineer" if "write" in api_key.scopes else "viewer"
        return TenantContext(actor=api_key, org=org, role=role, is_api_key=True)

    # 2. Cas Jeton JWT Utilisateur
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Jeton JWT invalide ou expiré.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Jeton invalide (identifiant utilisateur manquant).",
        )

    user = db.execute(select(User).where(User.id == user_id, User.is_active.is_(True))).scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur introuvable ou compte désactivé.",
        )

    # Résolution de l'organisation active et du rôle
    memberships = user.memberships
    if not memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cet utilisateur n'appartient à aucune organisation.",
        )

    requested_org_id = request.headers.get("X-Organization-Id") or request.query_params.get("org_id")
    target_membership = None
    if requested_org_id:
        target_membership = next((m for m in memberships if m.org_id == requested_org_id), None)

    if not target_membership:
        target_membership = memberships[0]

    org = db.execute(
        select(Organization).where(Organization.id == target_membership.org_id, Organization.is_active.is_(True))
    ).scalar_one_or_none()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organisation inactive ou inaccessible.",
        )

    return TenantContext(actor=user, org=org, role=target_membership.role, is_api_key=False)


def get_tenant_context_optional(
    request: Request,
    auth_creds: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: Session = Depends(get_db),
) -> Optional[TenantContext]:
    """
    Variante optionnelle : résout le TenantContext si les identifiants sont fournis,
    sinon retourne None (permet la transition progressive des endpoints existants).
    """
    token: Optional[str] = None
    if auth_creds and auth_creds.credentials:
        token = auth_creds.credentials.strip()
    elif "access_token" in request.cookies:
        token = request.cookies.get("access_token")

    if not token:
        return None

    try:
        return get_tenant_context(request, auth_creds, db)
    except HTTPException:
        return None


def require_role(min_role: str = "viewer"):
    """
    Générateur de dépendance vérifiant que l'utilisateur possède au moins min_role.
    """
    def role_checker(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        if not has_sufficient_role(ctx.role, min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Privilèges insuffisants. Rôle minimum requis : {min_role}.",
            )
        return ctx
    return role_checker


def require_superadmin(
    ctx: TenantContext = Depends(get_tenant_context),
) -> TenantContext:
    """
    Dépendance stricte pour les routes d'administration globale de la plateforme.
    Règle d'invisibilité : renvoie un code 404 strict si l'acteur n'est pas superadmin.
    """
    is_super = getattr(ctx.user, "is_superadmin", False) if ctx.user else False
    if not is_super:
        logger.warning(f"Tentative d'accès superadmin non autorisé par {getattr(ctx.user, 'id', 'api_key')}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ressource introuvable.",
        )
    return ctx


def require_feature(feature_name: str):
    """
    Générateur de dépendance vérifiant l'accès à une fonctionnalité selon le plan tarifaire.
    Règle d'invisibilité : renvoie 404 strict si la fonctionnalité n'est pas incluse dans le plan.
    """
    def feature_checker(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        allowed, _ = check_feature_access(ctx.org, feature_name)
        if not allowed:
            logger.info(
                "Accès masqué (404) à la feature '%s' pour org=%s (plan=%s)",
                feature_name, ctx.org.id, ctx.org.billing_plan
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ressource introuvable.",
            )
        return ctx
    return feature_checker


def require_network_access(min_role: str = "viewer"):
    """
    Dépendance garantissant l'isolation multi-tenant stricte sur un réseau/projet donné.
    Vérifie que network_id existe ET appartient à ctx.org.id.
    Si le réseau appartient à une autre organisation, renvoie 404 strict (invisibilité).
    """
    def network_checker(
        network_id: str,
        ctx: TenantContext = Depends(require_role(min_role)),
        db: Session = Depends(get_db),
    ) -> Tuple[TenantContext, Network]:
        network = db.execute(
            select(Network).where(Network.id == network_id, Network.org_id == ctx.org.id)
        ).scalar_one_or_none()
        if not network:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Réseau ou projet introuvable.",
            )
        return ctx, network
    return network_checker
