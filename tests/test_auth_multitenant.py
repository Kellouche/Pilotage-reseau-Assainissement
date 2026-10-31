# -*- coding: utf-8 -*-
"""
Tests unitaires et d'intégration pour l'authentification et l'isolation multi-tenant SaaS.
Conforme à ADR 0001 (Authentification FastAPI, Argon2id et Double Session JWT/Cookie)
et ADR 0002 (Isolation Multi-Tenant par Base Partagée avec org_id et Règle d'or de cloisonnement).

Auteur : Dr Abdelhakim Kellouche / Antigravity
Date : Octobre 2026
"""

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request
from starlette.datastructures import Headers
from fastapi import Response, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from api.database import Base
from api.models import User, Organization, Membership, Network, ApiKey
from api.core.auth import (
    hash_password,
    verify_password,
    is_academic_email,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_api_key,
    check_user_credentials,
)
from api.core.security import (
    get_tenant_context,
    require_role,
    require_superadmin,
    require_feature,
    require_network_access,
    TenantContext,
)
from api.core.quotas import (
    check_network_size_quota,
    check_projects_count_quota,
    get_trial_status,
    get_organization_features,
    normalize_plan_name,
)
from api.routes.auth import (
    register,
    login,
    refresh_token,
    get_current_user_profile,
    create_new_api_key,
    list_api_keys,
    revoke_api_key,
    verify_email_code,
    resend_verification_code,
)
from api.schemas_auth import (
    RegisterRequest,
    LoginRequest,
    RefreshTokenRequest,
    ApiKeyCreateRequest,
    VerifyCodeRequest,
    ResendCodeRequest,
)

# Base SQLite en mémoire isolée pour les tests
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=test_engine)


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """Crée les tables en mémoire pour la suite de tests."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db():
    """Fournit une session de base de données de test."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def make_request(headers_dict=None, cookies_dict=None, query_string=b""):
    """Construit un objet Request Starlette minimal pour tester les dépendances."""
    raw_headers = []
    if headers_dict:
        for k, v in headers_dict.items():
            raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))
    if cookies_dict:
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())
        raw_headers.append((b"cookie", cookie_str.encode("latin-1")))

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "raw_path": b"/",
        "query_string": query_string,
        "headers": raw_headers,
    }
    return Request(scope)


# ============================================================
# 1. HACHAGE ARGON2ID & ADRESSES ACADÉMIQUES
# ============================================================

def test_argon2_hashing_and_verification():
    """Vérifie le fonctionnement cryptographique du hasher Argon2id."""
    password = "SuperPassword2026!"
    pwd_hash = hash_password(password)

    assert pwd_hash.startswith("$argon2id$")
    assert verify_password(pwd_hash, password) is True
    assert verify_password(pwd_hash, "MauvaisMotDePasse") is False
    assert verify_password("", password) is False
    assert verify_password(pwd_hash, "") is False

    with pytest.raises(ValueError):
        hash_password("")


def test_academic_email_detection():
    """Vérifie la détection stricte des domaines universitaires vs webmails grand public."""
    # Universités reconnues
    assert is_academic_email("chercheur@univ-alger.dz") is True
    assert is_academic_email("etudiant@usthb.dz") is True
    assert is_academic_email("labo@enp.edu.dz") is True
    assert is_academic_email("prof@polytech-marseille.fr") is True
    assert is_academic_email("phd@mit.edu") is True

    # Webmails grand public interdits pour la formule Académique
    assert is_academic_email("bet.contact@gmail.com") is False
    assert is_academic_email("expert@yahoo.fr") is False
    assert is_academic_email("ingenieur@hotmail.com") is False
    assert is_academic_email("consultant@outlook.fr") is False


# ============================================================
# 2. INSCRIPTION & CRÉATION ATOMIQUE DE TENANT WORKSPACE
# ============================================================

def test_register_user_and_org_success(db):
    """Vérifie qu'un nouvel utilisateur crée son compte et son organisation (ADR-0001)."""
    payload = RegisterRequest(
        email="amine.hydraulique@bet-conseil.dz",
        password="Password12345!",
        full_name="Amine Benali",
        org_name="Cabinet Ingénierie Eau & Assainissement",
        billing_plan="bet",
        org_type="bet",
    )
    resp = Response()
    token_resp = register(payload, resp, db)

    assert token_resp.access_token is not None
    assert token_resp.refresh_token is not None
    assert token_resp.user.email == "amine.hydraulique@bet-conseil.dz"
    assert token_resp.organization.billing_plan == "bet"
    assert token_resp.organization.role == "owner"

    # Vérification présence en base
    user = db.query(User).filter_by(email="amine.hydraulique@bet-conseil.dz").first()
    assert user is not None
    assert verify_password(user.password_hash, "Password12345!") is True
    assert len(user.memberships) == 1
    assert user.memberships[0].role == "owner"


def test_register_education_requires_academic_email(db):
    """Vérifie que la formule Académique & Recherche rejette les webmails grand public."""
    bad_payload = RegisterRequest(
        email="etudiant.test@gmail.com",
        password="Password12345!",
        full_name="Karim GrandPublic",
        billing_plan="education",
    )
    resp = Response()
    with pytest.raises(HTTPException) as exc_info:
        register(bad_payload, resp, db)
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "universitaire reconnue" in exc_info.value.detail

    # Inscription avec email académique valide
    good_payload = RegisterRequest(
        email="karim.recherche@usthb.dz",
        password="Password12345!",
        full_name="Dr Karim Chercheur",
        billing_plan="education",
    )
    ok_resp = register(good_payload, resp, db)
    assert ok_resp.organization.billing_plan == "education"


# ============================================================
# 3. CONNEXION & GESTION DE SESSION JWT
# ============================================================

def test_login_success_and_invalid_credentials(db):
    """Vérifie l'authentification par identifiant/mot de passe."""
    # Connexion valide
    resp = Response()
    login_payload = LoginRequest(
        email="amine.hydraulique@bet-conseil.dz",
        password="Password12345!",
    )
    res = login(login_payload, resp, db)
    assert res.access_token is not None
    assert res.user.email == "amine.hydraulique@bet-conseil.dz"

    # Mauvais mot de passe
    bad_pwd_payload = LoginRequest(
        email="amine.hydraulique@bet-conseil.dz",
        password="WrongPassword!",
    )
    with pytest.raises(HTTPException) as exc_info:
        login(bad_pwd_payload, resp, db)
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    # Email inconnu
    unknown_payload = LoginRequest(
        email="inconnu@bet-conseil.dz",
        password="Password12345!",
    )
    with pytest.raises(HTTPException) as exc_info2:
        login(unknown_payload, resp, db)
    assert exc_info2.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_refresh_token_rotation(db):
    """Vérifie le rafraîchissement d'un jeton d'accès via son refresh_token."""
    resp = Response()
    login_res = login(
        LoginRequest(email="amine.hydraulique@bet-conseil.dz", password="Password12345!"),
        resp,
        db,
    )
    old_refresh = login_res.refresh_token

    req = make_request()
    new_token_data = refresh_token(req, resp, RefreshTokenRequest(refresh_token=old_refresh), db)
    assert "access_token" in new_token_data
    decoded = decode_token(new_token_data["access_token"])
    assert decoded["email"] == "amine.hydraulique@bet-conseil.dz"


# ============================================================
# 4. CONTEXTE TENANT & PROFIL /ME
# ============================================================

def test_tenant_context_resolution(db):
    """Vérifie la résolution de l'acteur et de son organisation active."""
    user = db.query(User).filter_by(email="amine.hydraulique@bet-conseil.dz").first()
    org_id = user.memberships[0].org_id

    token = create_access_token({"sub": user.id, "email": user.email, "org_id": org_id, "role": "owner"})
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    req = make_request()

    ctx = get_tenant_context(req, creds, db)
    assert ctx.user.id == user.id
    assert ctx.org.id == org_id
    assert ctx.role == "owner"
    assert ctx.is_api_key is False

    # Consultation profil /me
    me = get_current_user_profile(ctx, db)
    assert me.user.email == user.email
    assert me.active_organization.billing_plan == "bet"
    assert me.features["has_mnt_analysis"] is True


# ============================================================
# 5. CLÉS D'API MACHINE-TO-MACHINE (M2M)
# ============================================================

def test_api_key_lifecycle_and_m2m_auth(db):
    """Vérifie la création, l'utilisation et la révocation des clés d'API sp_live_..."""
    user = db.query(User).filter_by(email="amine.hydraulique@bet-conseil.dz").first()
    org = user.memberships[0].organization

    ctx = TenantContext(actor=user, org=org, role="owner")

    # 1. Création d'une clé d'API
    key_payload = ApiKeyCreateRequest(label="Scada IoT Outfall Sensor", scopes=["read", "write"])
    created_key = create_new_api_key(key_payload, ctx, db)
    raw_key = created_key.key
    key_id = created_key.id

    assert raw_key.startswith("sp_live_")

    # 2. Authentification via la clé M2M brute
    m2m_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=raw_key)
    req = make_request()
    m2m_ctx = get_tenant_context(req, m2m_creds, db)

    assert m2m_ctx.is_api_key is True
    assert m2m_ctx.org.id == org.id

    # 3. Liste des clés de l'organisation
    keys_list = list_api_keys(ctx, db)
    assert len(keys_list) >= 1
    assert any(k.id == key_id for k in keys_list)

    # 4. Révocation de la clé
    revoke_api_key(key_id, ctx, db)

    # 5. Appel après révocation -> 401
    with pytest.raises(HTTPException) as exc_info:
        get_tenant_context(req, m2m_creds, db)
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================
# 6. RÈGLE D'OR DE CLOISONNEMENT & INVISIBILITÉ STRICTE (ADR-0001, ADR-0002)
# ============================================================

def test_multitenant_isolation_and_stealth_rule(db):
    """
    Règle d'or de cloisonnement (Section 3) :
    Si l'organisation A tente d'accéder à un réseau appartenant à l'organisation B,
    l'API répond impérativement 404 (non 403), pour masquer totalement son existence.
    """
    # Création du locataire B (Régie d'Oran)
    resp = Response()
    reg_b = register(
        RegisterRequest(
            email="contact@regie-oranais.dz",
            password="Password12345!",
            full_name="Régie Municipale d'Assainissement",
            org_name="Régie Assainissement Oran",
            billing_plan="exploitation",
        ),
        resp,
        db,
    )
    user_b = db.query(User).filter_by(email="contact@regie-oranais.dz").first()
    org_b = user_b.memberships[0].organization

    # Création d'un réseau appartenant au locataire B
    net_b = Network(
        org_id=org_b.id,
        name="Collecteur Principal Front de Mer Oran",
        commune="Oran",
    )
    db.add(net_b)
    db.commit()

    # Locataire B accède à son propre réseau -> SUCCÈS
    ctx_b = TenantContext(actor=user_b, org=org_b, role="owner")
    network_guard = require_network_access("viewer")
    _, resolved_net = network_guard(net_b.id, ctx_b, db)
    assert resolved_net.id == net_b.id

    # Locataire A (Bureau d'études) tente d'accéder au réseau du locataire B -> 404 STRICT
    user_a = db.query(User).filter_by(email="amine.hydraulique@bet-conseil.dz").first()
    org_a = user_a.memberships[0].organization
    ctx_a = TenantContext(actor=user_a, org=org_a, role="owner")

    with pytest.raises(HTTPException) as exc_info:
        network_guard(net_b.id, ctx_a, db)

    # Règle d'invisibilité : 404 strict, jamais de fuite d'information 403 !
    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "Réseau ou projet introuvable."


def test_superadmin_stealth_invisibility(db):
    """Vérifie que toute tentative d'accès non-superadmin renvoie une 404 stricte."""
    user = db.query(User).filter_by(email="amine.hydraulique@bet-conseil.dz").first()
    org = user.memberships[0].organization
    ctx = TenantContext(actor=user, org=org, role="owner")

    # Amine n'est pas superadmin de la plateforme -> 404
    with pytest.raises(HTTPException) as exc_info:
        require_superadmin(ctx)
    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "Ressource introuvable."


def test_quotas_and_feature_gating_logic():
    """Vérifie les quotas et indicateurs de fonctionnalités par formule métier."""
    org_edu = Organization(name="USTHB Hydraulique", slug="usthb-hydro", billing_plan="education", billing_status="active")
    org_bet = Organization(name="BET Conseil", slug="bet-conseil", billing_plan="bet", billing_status="active")

    # Formule Académique : plafonnée à 500 regards
    ok_edu, _ = check_network_size_quota(org_edu, 450)
    assert ok_edu is True
    ko_edu, msg_edu = check_network_size_quota(org_edu, 600)
    assert ko_edu is False
    assert "500 regards" in msg_edu

    # Formule BET : accepte 600 regards (plafond 15 000)
    ok_bet, _ = check_network_size_quota(org_bet, 600)
    assert ok_bet is True

    # Feature gating MNT : Non disponible en Académique, inclus en BET
    feat_edu = get_organization_features(org_edu)
    assert feat_edu["has_mnt_analysis"] is False

    feat_bet = get_organization_features(org_bet)
    assert feat_bet["has_mnt_analysis"] is True

    # Statut d'évaluation (Version Démo)
    org_demo = Organization(name="Cabinet Test", slug="cabinet-test", billing_plan="demo", billing_status="trial")
    trial_status = get_trial_status(org_demo)
    assert trial_status["is_trial"] is True
    assert trial_status["total_days"] == 14


def test_email_verification_flow(db):
    """Vérifie la génération et validation du code d'activation par e-mail (Option B)."""
    resp = Response()
    reg_payload = RegisterRequest(
        email="nabil.ingenieur@alger-vrd.dz",
        password="SecuredPassword2026!",
        full_name="Nabil Ingénieur",
        org_name="Cabinet VRD Alger",
        billing_plan="demo",
    )
    reg_resp = register(reg_payload, resp, db)
    assert reg_resp.requires_verification is True
    assert reg_resp.dev_code is not None
    assert len(reg_resp.dev_code) == 6

    user = db.query(User).filter_by(email="nabil.ingenieur@alger-vrd.dz").first()
    assert user.email_verified is False
    assert user.verification_code == reg_resp.dev_code

    # 1. Échec avec code erroné
    bad_code_req = VerifyCodeRequest(email="nabil.ingenieur@alger-vrd.dz", code="000000")
    with pytest.raises(HTTPException) as exc:
        verify_email_code(bad_code_req, resp, db)
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST

    # 2. Réexpédition d'un nouveau code
    resend_req = ResendCodeRequest(email="nabil.ingenieur@alger-vrd.dz")
    resend_resp = resend_verification_code(resend_req, db)
    assert resend_resp["status"] == "ok"
    new_code = resend_resp["dev_code"]
    assert len(new_code) == 6

    # 3. Validation avec le bon code
    good_code_req = VerifyCodeRequest(email="nabil.ingenieur@alger-vrd.dz", code=new_code)
    verify_resp = verify_email_code(good_code_req, resp, db)
    assert verify_resp.requires_verification is False
    assert verify_resp.access_token is not None

    # L'utilisateur est désormais validé en base
    db.refresh(user)
    assert user.email_verified is True
    assert user.verification_code is None


def test_expired_code_renewal_on_login(db):
    """Vérifie qu'un code expiré (> 15 minutes) est automatiquement renouvelé lors de la connexion."""
    resp = Response()
    reg_payload = RegisterRequest(
        email="expert.expiration@alger-vrd.dz",
        password="SecuredPassword2026!",
        full_name="Expert Expiration",
        org_name="Bureau Test Expire",
        billing_plan="demo",
    )
    reg_resp = register(reg_payload, resp, db)
    old_code = reg_resp.dev_code

    user = db.query(User).filter_by(email="expert.expiration@alger-vrd.dz").first()
    assert user.email_verified is False

    # Simuler le passage de plus de 15 minutes (code expiré dans le passé)
    user.verification_code_expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.commit()

    # 1. Tentative de validation avec l'ancien code expiré -> Doit échouer avec message clair
    bad_verify_req = VerifyCodeRequest(email="expert.expiration@alger-vrd.dz", code=old_code)
    with pytest.raises(HTTPException) as exc:
        verify_email_code(bad_verify_req, resp, db)
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "expiré" in exc.value.detail.lower()

    # 2. Re-connexion par identifiants -> Le système doit régénérer automatiquement un nouveau code valide
    login_req = LoginRequest(email="expert.expiration@alger-vrd.dz", password="SecuredPassword2026!")
    login_resp = login(login_req, resp, db)
    assert login_resp.requires_verification is True
    assert login_resp.dev_code is not None
    assert login_resp.dev_code != old_code

    # 3. Validation avec le nouveau code régénéré
    ok_verify_req = VerifyCodeRequest(email="expert.expiration@alger-vrd.dz", code=login_resp.dev_code)
    ok_resp = verify_email_code(ok_verify_req, resp, db)
    assert ok_resp.requires_verification is False
    assert ok_resp.access_token is not None

