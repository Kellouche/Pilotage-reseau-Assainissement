# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Schémas Pydantic d'authentification, utilisateurs et organisations
================================================================================
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


class RegisterRequest(BaseModel):
    """Requête de création de compte et de workspace locataire."""
    email: str = Field(..., description="Adresse e-mail professionnelle ou académique")
    password: str = Field(..., min_length=8, description="Mot de passe en clair (minimum 8 caractères)")
    full_name: str = Field(default="", max_length=150, description="Nom et prénom de l'utilisateur")
    org_name: Optional[str] = Field(default=None, max_length=150, description="Nom de l'organisation ou du bureau d'études")
    billing_plan: str = Field(default="demo", description="Plan initial (demo, education, bet, exploitation)")
    org_type: str = Field(default="bet", description="Type d'entité (bet, regie, academie, commune)")

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Format d'adresse e-mail invalide.")
        return v


class LoginRequest(BaseModel):
    """Requête de connexion par identifiant / mot de passe."""
    email: str = Field(..., description="Adresse e-mail")
    password: str = Field(..., description="Mot de passe")

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        return v.strip().lower()


class UserSummary(BaseModel):
    """Résumé du profil utilisateur."""
    id: str
    email: str
    full_name: Optional[str]
    is_active: bool
    is_superadmin: bool
    email_verified: bool = False


class OrgSummary(BaseModel):
    """Résumé de l'organisation active."""
    id: str
    name: str
    slug: str
    billing_plan: str
    billing_status: str
    org_type: str
    role: str


class TokenResponse(BaseModel):
    """Réponse d'authentification complète avec jetons JWT."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    user: UserSummary
    organization: OrgSummary
    requires_verification: bool = False
    dev_code: Optional[str] = None


class VerifyCodeRequest(BaseModel):
    """Requête de vérification du code d'activation reçu par e-mail."""
    email: str = Field(..., description="Adresse email associée au compte")
    code: str = Field(..., min_length=4, max_length=10, description="Code d'activation à 6 chiffres")


class ResendCodeRequest(BaseModel):
    """Requête de réexpédition du code d'activation."""
    email: str = Field(..., description="Adresse email")


class RefreshTokenRequest(BaseModel):
    """Requête de renouvellement de jeton d'accès."""
    refresh_token: Optional[str] = Field(None, description="Jeton de rafraîchissement (si non transmis en cookie)")


class ApiKeyCreateRequest(BaseModel):
    """Création d'une nouvelle clé d'API pour intégration M2M."""
    label: str = Field(..., min_length=1, max_length=100, description="Libellé descriptif (ex: 'Script QGIS terrain')")
    scopes: List[str] = Field(default=["read", "write"], description="Périmètres de droits autorisés")


class ApiKeySummary(BaseModel):
    """Informations publiques d'une clé d'API existante."""
    id: str
    label: str
    prefix: str
    scopes: List[str]
    created_at: datetime
    last_used_at: Optional[datetime] = None


class ApiKeyCreatedResponse(ApiKeySummary):
    """Réponse de création d'une clé d'API (la clé complète n'est affichée qu'une seule fois)."""
    key: str = Field(..., description="Clé complète brute (à copier immédiatement, non ré-affichable)")


class UserMeResponse(BaseModel):
    """Profil complet de l'acteur courant, son organisation et ses droits."""
    user: UserSummary
    active_organization: OrgSummary
    memberships: List[Dict[str, Any]]
    features: Dict[str, Any]
    trial_status: Dict[str, Any]
