# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Contrôle de validité des licences et vérification des droits d'accès
================================================================================
"""

from datetime import datetime, timezone, timedelta
import logging
import os
import secrets
from typing import Optional, Dict, Any, Tuple, List
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from api.models import Organization, PurchaseOrder, User
from api.core.quotas import normalize_plan_name
from api.core.storage import get_artifact_store

logger = logging.getLogger("swmm.licensing")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def generate_license_token(plan: str, duration_months: int = 12) -> str:
    """
    Génère un jeton d'activation de licence officiel et unique.
    Format : SP-LIC-{PLAN}-{YEAR}-{RANDOM}
    Exemple : SP-LIC-BET-2026-A8F2K9M4
    """
    clean_plan = normalize_plan_name(plan).upper()
    year = datetime.now(timezone.utc).year
    rand_part = secrets.token_hex(4).upper()
    return f"SP-LIC-{clean_plan}-{year}-{rand_part}"


def calculate_default_amount_dzd(plan: str, duration_months: int = 12) -> float:
    """
    Calcule le montant indicatif en Dinars Algériens (DZD) selon la grille tarifaire officielle.
    - BET : 45 000 DZD / mois (ou 450 000 DZD / an pour 12 mois, soit 2 mois offerts)
    - Exploitation : Tarif de référence conventionnel 180 000 DZD / mois (ou convention annuelle)
    - Education : Gratuit (0 DZD)
    """
    canonical = normalize_plan_name(plan)
    if canonical == "education":
        return 0.0
    elif canonical == "bet":
        monthly_rate = 45000.0
        if duration_months >= 12:
            years = duration_months // 12
            remainder = duration_months % 12
            return round(years * 450000.0 + remainder * monthly_rate, 2)
        return round(monthly_rate * duration_months, 2)
    elif canonical == "exploitation":
        monthly_rate = 180000.0
        return round(monthly_rate * duration_months, 2)
    return 0.0


def submit_purchase_order(
    session: Session,
    org_id: str,
    order_ref: str,
    client_type: str,
    entity_name: str,
    contact_name: str,
    contact_email: str,
    contact_phone: str,
    target_plan: str,
    duration_months: int = 12,
    amount_dzd: Optional[float] = None,
    document_bytes: Optional[bytes] = None,
    document_filename: Optional[str] = None,
    notes: Optional[str] = None,
) -> PurchaseOrder:
    """
    Crée un Bon de Commande / Engagement en attente de validation administrative.
    Stocke le document justificatif scanné dans ArtifactStore si fourni.
    """
    clean_plan = normalize_plan_name(target_plan)
    clean_ref = order_ref.strip().upper()

    # Vérification d'unicité de la référence de bon de commande
    existing = session.execute(
        select(PurchaseOrder).where(PurchaseOrder.order_ref == clean_ref)
    ).scalar_one_or_none()
    if existing:
        raise ValueError(f"La référence de bon de commande '{clean_ref}' existe déjà dans le système.")

    calculated_amount = amount_dzd if amount_dzd is not None else calculate_default_amount_dzd(clean_plan, duration_months)

    # Sauvegarde du document scanné dans ArtifactStore si fourni
    doc_key = None
    if document_bytes and document_filename:
        storage = get_artifact_store()
        clean_filename = os.path.basename(document_filename).replace(" ", "_")
        doc_key = f"{org_id}/licences/bc_{clean_ref}_{clean_filename}"
        storage.put_bytes(doc_key, document_bytes)
        logger.info("Justificatif bon de commande sauvegardé dans store : %s", doc_key)

    order = PurchaseOrder(
        org_id=org_id,
        order_ref=clean_ref,
        client_type=client_type,
        entity_name=entity_name.strip(),
        contact_name=contact_name.strip(),
        contact_email=contact_email.strip().lower(),
        contact_phone=contact_phone.strip(),
        target_plan=clean_plan,
        duration_months=duration_months,
        amount_dzd=calculated_amount,
        status="pending",
        po_document_key=doc_key,
        admin_notes=notes,
    )
    session.add(order)
    session.flush()

    logger.info("Bon de commande enregistré : %s pour org=%s (plan=%s, montant=%.2f DZD)", clean_ref, org_id, clean_plan, calculated_amount)
    return order


def approve_purchase_order(
    session: Session,
    order_id: str,
    validator_id: Optional[str] = None,
    admin_notes: Optional[str] = None,
) -> PurchaseOrder:
    """
    Approuve un Bon de Commande :
    1. Génère la clé de licence cryptographique officielle.
    2. Calcule la période de validité (valid_from et valid_until).
    3. Met à jour l'Organisation locataire (plan actif, statut 'active', date d'expiration).
    """
    order = session.get(PurchaseOrder, order_id)
    if not order:
        raise ValueError("Bon de commande introuvable.")

    if order.status == "approved":
        return order

    now = _utc_now()
    valid_until = now + timedelta(days=order.duration_months * 30)
    token = generate_license_token(order.target_plan, order.duration_months)

    order.status = "approved"
    order.license_token = token
    order.valid_from = now
    order.valid_until = valid_until
    order.validated_by_id = validator_id
    order.validated_at = now
    if admin_notes:
        order.admin_notes = admin_notes

    # Activation directe sur l'organisation
    org = session.get(Organization, order.org_id)
    if org:
        org.billing_plan = order.target_plan
        org.billing_status = "active"
        org.license_valid_until = valid_until

    session.flush()
    logger.info("Bon de commande %s validé avec succès. Jeton émis : %s (validité jusqu'au %s)", order.order_ref, token, valid_until.isoformat())
    return order


def reject_purchase_order(
    session: Session,
    order_id: str,
    reason: str,
    validator_id: Optional[str] = None,
) -> PurchaseOrder:
    """Rejette un Bon de Commande avec un motif administratif clair."""
    order = session.get(PurchaseOrder, order_id)
    if not order:
        raise ValueError("Bon de commande introuvable.")

    order.status = "rejected"
    order.admin_notes = reason
    order.validated_by_id = validator_id
    order.validated_at = _utc_now()

    session.flush()
    logger.info("Bon de commande %s rejeté. Motif : %s", order.order_ref, reason)
    return order


def activate_license_token(
    session: Session,
    org_id: str,
    token_str: str,
) -> Tuple[bool, str, Optional[datetime]]:
    """
    Active une clé de licence officielle sur une organisation.
    Vérifie la correspondance et applique les privilèges du plan souscrit.
    """
    clean_token = token_str.strip().upper()
    order = session.execute(
        select(PurchaseOrder).where(
            PurchaseOrder.license_token == clean_token,
            PurchaseOrder.status == "approved"
        )
    ).scalar_one_or_none()

    if not order:
        return False, "Jeton de licence invalide ou non reconnu.", None

    org = session.get(Organization, org_id)
    if not org:
        return False, "Organisation introuvable.", None

    now = _utc_now()
    if order.valid_until and _ensure_utc(order.valid_until) < now:
        return False, "Ce jeton de licence a expiré.", None

    # Application du plan et extension de validité
    org.billing_plan = order.target_plan
    org.billing_status = "active"
    org.license_valid_until = order.valid_until

    session.flush()
    logger.info("Jeton %s activé pour l'organisation %s (Plan : %s)", clean_token, org.name, org.billing_plan)
    return True, f"Licence activée avec succès pour la formule {org.billing_plan.upper()}.", order.valid_until


def check_license_validity(org: Organization) -> Dict[str, Any]:
    """
    Contrôle la validité de la licence d'une organisation.
    Retourne l'état précis (actif, expiré, jours restants).
    """
    now = _utc_now()
    plan = normalize_plan_name(org.billing_plan or "demo")

    if plan == "education":
        return {
            "is_valid": True,
            "is_expired": False,
            "days_remaining": None,
            "plan": "education",
            "message": "Licence académique permanente active."
        }

    expiry = _ensure_utc(org.license_valid_until)
    if not expiry:
        # En mode démo par défaut sans date explicite -> calcul basé sur created_at
        created = _ensure_utc(org.created_at) or now
        expiry = created + timedelta(days=14)

    delta = expiry - now
    days = delta.days

    if days < 0:
        return {
            "is_valid": False,
            "is_expired": True,
            "days_remaining": 0,
            "plan": plan,
            "valid_until": expiry.isoformat(),
            "message": "Licence ou période d'évaluation expirée."
        }

    return {
        "is_valid": True,
        "is_expired": False,
        "days_remaining": days,
        "plan": plan,
        "valid_until": expiry.isoformat(),
        "message": f"Licence active ({days} jours restants)."
    }
