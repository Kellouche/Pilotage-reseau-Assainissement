# -*- coding: utf-8 -*-
"""
Tests unitaires des routes web de l'application SaaS (ADR 0001, ADR 0008).
Vérifie la vitrine SaaS (/), les pages d'authentification (/login, /register, /logout)
et l'accès au cockpit hydraulique (/cockpit).
"""

from unittest.mock import MagicMock
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from api.main import read_root, page_login, page_register, page_logout, get_cockpit, page_pricing
from api.models import User, Organization, Membership
from api.core.auth import create_access_token


def test_public_landing_page_unauthenticated():
    """Un visiteur non connecté accédant à / doit recevoir la landing page SaaS."""
    req = MagicMock(spec=Request)
    req.cookies = {}
    req.headers = {}
    db = MagicMock()

    resp = read_root(req, db)
    assert isinstance(resp, HTMLResponse)
    assert resp.status_code == 200
    assert "DrainPilot" in resp.body.decode("utf-8")
    assert "Fascicule 70" in resp.body.decode("utf-8")
    assert "NP 650" in resp.body.decode("utf-8")


def test_authenticated_user_redirects_to_cockpit():
    """Un utilisateur connecté avec un cookie access_token valide doit être redirigé vers /cockpit."""
    user = User(
        id="usr-test-web",
        email="ingenieur@bet.dz",
        full_name="Ingénieur VRD",
        is_active=True,
        email_verified=True,
    )
    token = create_access_token({"sub": user.id, "email": user.email, "org_id": "org-test", "role": "engineer"})

    req = MagicMock(spec=Request)
    req.cookies = {"access_token": token}
    req.headers = {}

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user

    resp = read_root(req, db)
    assert isinstance(resp, RedirectResponse)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/cockpit"


def test_login_and_register_pages():
    """Les pages /login et /register doivent être rendues pour les visiteurs non connectés."""
    req = MagicMock(spec=Request)
    req.cookies = {}
    req.headers = {}
    db = MagicMock()

    resp_login = page_login(req, db)
    assert isinstance(resp_login, HTMLResponse)
    assert resp_login.status_code == 200
    assert "Connexion" in resp_login.body.decode("utf-8")

    resp_reg = page_register(req, db)
    assert isinstance(resp_reg, HTMLResponse)
    assert resp_reg.status_code == 200
    assert "DrainPilot" in resp_reg.body.decode("utf-8")


def test_logout_clears_cookies_and_redirects():
    """La route /logout doit détruire les cookies de session et rediriger vers /login."""
    resp = page_logout()
    assert isinstance(resp, RedirectResponse)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"
    # Vérifier que les en-têtes set-cookie contiennent l'expiration des tokens
    cookies = [h for k, h in resp.raw_headers if k.lower() == b"set-cookie"]
    assert any(b"access_token" in c for c in cookies)


def test_cockpit_unauthenticated_redirects_to_login():
    """Un visiteur non connecté accédant à /cockpit doit être refoulé vers /login."""
    req = MagicMock(spec=Request)
    req.cookies = {}
    req.headers = {}
    db = MagicMock()

    resp = get_cockpit(req, db)
    assert isinstance(resp, RedirectResponse)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login?next=/cockpit"


def test_cockpit_authenticated_serves_html():
    """Un membre connecté accédant à /cockpit accède à son espace de travail avec la topbar SaaS."""
    user = User(
        id="usr-cockpit-test",
        email="ingenieur@bet.dz",
        full_name="Ingénieur VRD",
        is_active=True,
        email_verified=True,
    )
    token = create_access_token({"sub": user.id, "email": user.email, "org_id": "org-test", "role": "engineer"})

    req = MagicMock(spec=Request)
    req.cookies = {"access_token": token}
    req.headers = {}

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user

    resp = get_cockpit(req, db)
    assert isinstance(resp, HTMLResponse)


def test_unverified_user_cannot_access_cockpit():
    """Un utilisateur dont l'email n'a pas été validé par code ne peut pas accéder au cockpit."""
    user = User(
        id="usr-unverified",
        email="nouveau@bet.dz",
        full_name="Non Vérifié",
        is_active=True,
        email_verified=False,
    )
    token = create_access_token({"sub": user.id, "email": user.email, "org_id": "org-test", "role": "engineer"})

    req = MagicMock(spec=Request)
    req.cookies = {"access_token": token}
    req.headers = {}

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user

    resp = get_cockpit(req, db)
    assert isinstance(resp, RedirectResponse)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login?next=/cockpit"
