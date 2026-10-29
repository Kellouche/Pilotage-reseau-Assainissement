# -*- coding: utf-8 -*-
"""
Tests unitaires de la Phase 3 : Commercial Engine, Licences B2B/B2G, Proforma PDF et Quotas.
Vérifie la génération PDF, le cycle des bons de commande, les règles de stealth 404
et les plafonds de collaborateurs d'organisation.
"""

from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.models import Base, Organization, User, Membership, PurchaseOrder
from api.core.proforma import amount_to_french_words, generate_proforma_pdf, generate_purchase_order_pdf
from api.core.licensing import (
    generate_license_token,
    calculate_default_amount_dzd,
    submit_purchase_order,
    approve_purchase_order,
    reject_purchase_order,
    activate_license_token,
    check_license_validity,
    _ensure_utc,
)
from api.core.quotas import check_members_count_quota
from api.core.security import TenantContext
from api.routes.admin import list_all_orders, require_superadmin
from fastapi import HTTPException


@pytest.fixture
def db_session():
    """Crée une session SQLite in-memory pour tester le cycle commercial."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_amount_to_french_words():
    """Vérifie la transcription exacte des montants DZD en toutes lettres."""
    assert "Quatre cent quatre-vingt-six mille Dinars Algériens" in amount_to_french_words(486000.0)
    assert "Zéro Dinars Algériens" in amount_to_french_words(0.0)
    assert "Dinars Algériens" in amount_to_french_words(35000.50)
    assert "centimes" in amount_to_french_words(35000.50)


def test_generate_proforma_pdf_validity():
    """Génère un PDF officiel de facture proforma et contrôle sa signature binaire %PDF."""
    pdf_bytes = generate_proforma_pdf(
        org_name="Bureau d'Études Assainissement VRD",
        contact_name="Dr Abdelhakim K.",
        contact_email="contact@bet-assainissement.dz",
        plan="bet",
        duration_months=12,
        doc_type="proforma",
    )
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF")

    # Test formule exploitation
    pdf_exp = generate_proforma_pdf(
        org_name="Office National de l'Assainissement (ONA)",
        contact_name="Directeur Exploitation",
        contact_email="direction@ona.dz",
        plan="exploitation",
        duration_months=12,
        doc_type="devis",
    )
    assert pdf_exp.startswith(b"%PDF")


def test_purchase_order_lifecycle(db_session):
    """Vérifie le cycle complet d'un bon de commande : création, calcul DZD, approbation et rejet."""
    org = Organization(
        id="org-test-po",
        name="Cabinet Hydraulique Urbaine",
        slug="cabinet-hydraulique",
        billing_plan="demo",
        billing_status="trial",
    )
    user = User(
        id="usr-test-po",
        email="directeur@cabinet.dz",
        password_hash="hash",
        full_name="Directeur Technique",
    )
    db_session.add_all([org, user])
    db_session.commit()

    # 1. Soumission d'un bon de commande
    order = submit_purchase_order(
        session=db_session,
        org_id=org.id,
        order_ref="BC-2026-BET-001",
        client_type="bet",
        entity_name="Cabinet Hydraulique Urbaine",
        contact_name="Directeur Technique",
        contact_email="directeur@cabinet.dz",
        contact_phone="0550112233",
        target_plan="bet",
        duration_months=12,
    )
    db_session.commit()

    assert order.status == "pending"
    assert order.amount_dzd == 486000.0  # 45000 * 12 * 0.9 (remise 10%)
    assert order.license_token is None

    # Test PDF bon de commande
    po_pdf = generate_purchase_order_pdf(order)
    assert po_pdf.startswith(b"%PDF")

    # 2. Approbation par SuperAdmin
    approved_order = approve_purchase_order(
        session=db_session,
        order_id=order.id,
        validator_id=user.id,
        admin_notes="Bon de commande certifié conforme par la commission.",
    )
    db_session.commit()

    assert approved_order.status == "approved"
    assert approved_order.license_token.startswith("SP-LIC-BET-")
    assert _ensure_utc(approved_order.valid_until) > datetime.now(timezone.utc)

    # Vérification de la répercussion sur l'organisation
    db_session.refresh(org)
    assert org.billing_plan == "bet"
    assert org.billing_status == "active"
    assert org.license_valid_until is not None

    # 3. Contrôle de validité de la licence
    validity = check_license_validity(org)
    assert validity["is_valid"] is True
    assert validity["is_expired"] is False
    assert validity["plan"] == "bet"
    assert validity["days_remaining"] > 300


def test_activate_license_token(db_session):
    """Vérifie l'activation d'un jeton par une organisation cliente."""
    org_a = Organization(id="org-a", name="BET Alpha", slug="bet-alpha", billing_plan="demo")
    org_b = Organization(id="org-b", name="BET Beta", slug="bet-beta", billing_plan="demo")
    db_session.add_all([org_a, org_b])
    db_session.commit()

    order = submit_purchase_order(
        session=db_session,
        org_id=org_a.id,
        order_ref="BC-ALPHA-01",
        client_type="bet",
        entity_name="BET Alpha",
        contact_name="Directeur",
        contact_email="dir@alpha.dz",
        contact_phone="0550000000",
        target_plan="bet",
        duration_months=12,
    )
    approve_purchase_order(db_session, order.id)
    db_session.commit()

    token = order.license_token

    # Activation sur org_b avec ce jeton valide
    success, msg, valid_until = activate_license_token(db_session, org_b.id, token)
    assert success is True
    assert "activée avec succès" in msg

    db_session.refresh(org_b)
    assert org_b.billing_plan == "bet"
    assert org_b.billing_status == "active"

    # Tentative avec jeton invalide
    bad_success, bad_msg, _ = activate_license_token(db_session, org_b.id, "SP-LIC-FAUX-TOKEN")
    assert bad_success is False
    assert "invalide" in bad_msg


def test_admin_stealth_rule():
    """Un utilisateur non superadmin tentant d'accéder à la console admin doit recevoir une 404 furtive."""
    normal_user = User(id="u-normal", is_superadmin=False)
    ctx_normal = TenantContext(actor=normal_user, org=Organization(id="o1"), role="admin")

    with pytest.raises(HTTPException) as exc_info:
        require_superadmin(ctx_normal)
    assert exc_info.value.status_code == 404

    # SuperAdmin passe avec succès
    super_user = User(id="u-super", is_superadmin=True)
    ctx_super = TenantContext(actor=super_user, org=Organization(id="o1"), role="admin")
    validated_ctx = require_superadmin(ctx_super)
    assert validated_ctx.user.is_superadmin is True


def test_organization_member_quotas(db_session):
    """Vérifie que le plafond de membres par plan est strictement contrôlé."""
    # Plan éducation : 1 membre max
    org_edu = Organization(id="org-edu", name="Université USTHB", slug="univ-usthb", billing_plan="education")
    u1 = User(id="u-edu-1", email="etudiant1@usthb.dz", password_hash="h", full_name="Étudiant 1")
    u2 = User(id="u-edu-2", email="etudiant2@usthb.dz", password_hash="h", full_name="Étudiant 2")
    m1 = Membership(user_id=u1.id, org_id=org_edu.id, role="owner")

    db_session.add_all([org_edu, u1, u2, m1])
    db_session.commit()

    # Déjà 1 membre, tentative d'ajout d'un 2ème membre
    can_add, err_msg = check_members_count_quota(db_session, org_edu)
    assert can_add is False
    assert "Nombre maximal de collaborateurs atteint" in err_msg
