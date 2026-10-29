# -*- coding: utf-8 -*-
"""
Module api.core.auth : Authentification, hachage Argon2id, clés API et JWT pour SWMM Platform SaaS.
Inspiré et calqué sur l'architecture de sécurité de Pilotage-Réseau-AEP (core.auth).
Conforme à ADR 0001 (Authentification FastAPI, Argon2id et Double Session JWT/Cookie).

Auteur : Dr Abdelhakim Kellouche / Antigravity
Date : Octobre 2026
"""

import os
import sys
import re
import secrets
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Dict, Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.models import User, Organization, Membership, ApiKey, Project

logger = logging.getLogger(__name__)

# Détection de l'environnement de test pour accélérer Argon2id
_is_test = "pytest" in sys.modules or os.environ.get("TESTING") == "true"

# Hasher Argon2id configuré selon la RFC 9106 (profil recommandé)
_ph = PasswordHasher(
    time_cost=1 if _is_test else 2,
    memory_cost=2048 if _is_test else 19456,  # 2 Mio en test, 19 Mio en production
    parallelism=1,
    hash_len=32,
    salt_len=16,
)

# Configuration JWT
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "swmm_platform_jwt_secret_dev_key_2026_super_secure")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30


def hash_password(password: str) -> str:
    """Hache un mot de passe en clair avec Argon2id."""
    if not password:
        raise ValueError("Le mot de passe ne peut pas être vide.")
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Vérifie un mot de passe en clair contre son empreinte Argon2id."""
    if not password_hash or not password:
        return False
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """Indique si l'empreinte nécessite une mise à jour selon les paramètres actuels."""
    try:
        return _ph.check_needs_rehash(password_hash)
    except Exception:
        return True


def slugify(text: str) -> str:
    """Génère un slug URL-safe propre à partir d'un nom d'organisation."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    slug = text.strip('-')
    return slug or f"org-{secrets.token_hex(4)}"


def is_academic_email(email: str) -> bool:
    """
    Vérifie si une adresse e-mail appartient à un domaine académique ou universitaire reconnu.
    Interdit formellement les webmails grand public pour l'offre éducation.
    """
    if not email or "@" not in email:
        return False
    domain = email.strip().lower().split("@")[1]

    generic_domains = (
        "gmail.com", "yahoo.com", "yahoo.fr", "hotmail.com", "hotmail.fr",
        "outlook.com", "outlook.fr", "live.com", "live.fr", "icloud.com",
        "proton.me", "protonmail.com", "yandex.com", "mail.ru", "gmx.com",
        "zoho.com", "aol.com", "free.fr", "orange.fr", "sfr.fr"
    )
    if domain in generic_domains:
        return False

    academic_extensions = (
        ".edu", ".edu.dz", ".ac.dz", ".univ.dz", ".ac.uk", ".edu.fr",
        ".ac.fr", ".edu.ma", ".edu.tn"
    )
    if any(domain.endswith(ext) for ext in academic_extensions):
        return True

    academic_keywords = (
        "univ-", "univ.", "ens-", "ens.", "esi-", "esi.", "polytech", "usthb", "enp-", "enp.",
        "cerist", "cder", "recherche", "algeria-edu"
    )
    return any(kw in domain for kw in academic_keywords)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Génère un jeton JWT d'accès court (60 min par défaut)."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": now, "type": "access"})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Génère un jeton JWT de rafraîchissement long (30 jours par défaut)."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire, "iat": now, "type": "refresh"})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """Décode et valide la signature et l'expiration d'un jeton JWT."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError as e:
        logger.warning(f"Jeton JWT invalide ou expiré : {e}")
        return None


def generate_api_key(prefix_label: str = "sp_live") -> Tuple[str, str, str]:
    """
    Génère une clé d'API machine-to-machine.
    Retourne (full_key, prefix, key_hash).
    """
    token = secrets.token_urlsafe(32).replace('-', '').replace('_', '')[:32]
    full_key = f"{prefix_label}_{token}"
    prefix = full_key[:16]
    key_hash = hash_api_key(full_key)
    return full_key, prefix, key_hash


def hash_api_key(raw_key: str) -> str:
    """Calcule l'empreinte SHA-256 d'une clé d'API pour stockage sécurisé."""
    return hashlib.sha256(raw_key.strip().encode('utf-8')).hexdigest()


def authenticate_api_key(session: Session, raw_key: str) -> Optional[Tuple[ApiKey, Organization]]:
    """Authentifie une clé d'API brute et retourne l'entité ApiKey et son Organisation."""
    if not raw_key or not raw_key.startswith("sp_live_"):
        return None
    key_hash = hash_api_key(raw_key)
    stmt = (
        select(ApiKey, Organization)
        .join(Organization, ApiKey.org_id == Organization.id)
        .where(ApiKey.key_hash == key_hash, Organization.is_active.is_(True))
    )
    result = session.execute(stmt).first()
    if not result:
        return None
    api_key, org = result
    api_key.last_used_at = datetime.now(timezone.utc)
    session.commit()
    return api_key, org


def create_user_with_org(
    session: Session,
    email: str,
    password: str,
    full_name: str = "",
    org_name: str = "",
    org_slug: Optional[str] = None,
    role: str = "owner",
    billing_plan: str = "demo",
    org_type: str = "bet",
    is_active: bool = True,
    email_verified: bool = True,
    is_superadmin: bool = False,
) -> Tuple[User, Organization, Membership]:
    """
    Crée atomiquement un nouvel utilisateur, son organisation et son adhésion (Membership).
    """
    email_clean = email.strip().lower()
    if not email_clean or "@" not in email_clean:
        raise ValueError("Adresse email invalide.")

    # Vérification d'unicité email
    existing = session.execute(select(User).where(User.email == email_clean)).scalar_one_or_none()
    if existing:
        raise ValueError(f"Un compte existe déjà pour l'adresse {email_clean}.")

    # Nom d'organisation par défaut
    if not org_name:
        org_name = f"Workspace {full_name or email_clean.split('@')[0]}"

    slug_base = slugify(org_slug or org_name)
    slug_candidate = slug_base
    counter = 1
    while session.execute(select(Organization).where(Organization.slug == slug_candidate)).scalar_one_or_none():
        slug_candidate = f"{slug_base}-{counter}"
        counter += 1

    org = Organization(
        name=org_name,
        slug=slug_candidate,
        billing_plan=billing_plan,
        org_type=org_type or "bet",
    )
    session.add(org)
    session.flush()

    pwd_hash = hash_password(password)
    user = User(
        email=email_clean,
        password_hash=pwd_hash,
        full_name=full_name.strip(),
        is_active=is_active,
        email_verified=email_verified,
        is_superadmin=is_superadmin,
    )
    session.add(user)
    session.flush()

    membership = Membership(
        org_id=org.id,
        user_id=user.id,
        role=role,
    )
    session.add(membership)

    # Provisioning automatique du projet initial hermétique propre à l'organisation
    initial_project = Project(
        org_id=org.id,
        name="Réseau Pilote - Démonstration",
        description="Espace d'ingénierie et modèle initial préconfiguré pour votre organisation.",
    )
    session.add(initial_project)
    session.commit()

    logger.info("Utilisateur créé : id=%s email=%s org_id=%s slug=%s role=%s", user.id, user.email, org.id, org.slug, role)
    return user, org, membership


def check_user_credentials(session: Session, email: str, password: str) -> Tuple[Optional[User], str]:
    """
    Vérifie les identifiants d'un utilisateur.
    Retourne (user, status) où status vaut :
    - 'ok' : connexion réussie
    - 'not_found' : utilisateur inexistant
    - 'invalid_password' : mot de passe incorrect
    - 'inactive' : compte désactivé
    """
    email_clean = email.strip().lower()
    user = session.execute(select(User).where(User.email == email_clean)).scalar_one_or_none()
    if not user:
        return None, "not_found"

    if not user.is_active:
        return None, "inactive"

    if not verify_password(user.password_hash, password):
        return None, "invalid_password"

    # Mise à niveau transparente de l'empreinte Argon2 si les paramètres ont évolué
    if needs_rehash(user.password_hash):
        try:
            user.password_hash = hash_password(password)
            session.commit()
        except Exception as e:
            logger.warning(f"Échec de mise à jour de l'empreinte Argon2 : {e}")

    return user, "ok"
