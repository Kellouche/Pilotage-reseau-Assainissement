# -*- coding: utf-8 -*-
"""
Module api.routes.admin : Console Opérateur SuperAdmin pour la supervision des abonnés et validation des licences.
Réservé aux super-administrateurs de la plateforme (règle furtive 404 pour les utilisateurs non autorisés).
Conforme à ADR 0006 et Roadmap SaaS Phase 3.5.

Auteur : Dr Abdelhakim Kellouche / Antigravity
Date : Octobre 2026
"""

from datetime import datetime, timezone, timedelta
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, func
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import Organization, PurchaseOrder, User, Membership, Network
from api.core.security import get_tenant_context, TenantContext
from api.core.licensing import approve_purchase_order, reject_purchase_order

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Console Opérateur SuperAdmin"])


def require_superadmin(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    """Vérifie que l'utilisateur est superadmin. Règle furtive 404 en cas de refus."""
    user = ctx.user
    if not user or not getattr(user, "is_superadmin", False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ressource non trouvée.",
        )
    return ctx


# ============================================================
# SCHÉMAS
# ============================================================

class AdminOrderSummary(BaseModel):
    id: str
    org_id: str
    org_name: str
    order_ref: str
    client_type: str
    entity_name: str
    contact_name: str
    contact_email: str
    target_plan: str
    duration_months: int
    amount_dzd: float
    status: str
    license_token: Optional[str] = None
    created_at: datetime
    valid_until: Optional[datetime] = None


class ApproveOrderRequest(BaseModel):
    admin_notes: Optional[str] = Field(None, description="Observations administratives")


class RejectOrderRequest(BaseModel):
    reason: str = Field(..., min_length=3, description="Motif officiel de rejet")


class AdminOrgSummary(BaseModel):
    id: str
    name: str
    slug: str
    billing_plan: str
    billing_status: str
    org_type: str
    created_at: datetime
    license_valid_until: Optional[datetime] = None
    member_count: int
    network_count: int


# ============================================================
# ENDPOINTS SUPERADMIN
# ============================================================

@router.get("/orders", response_model=List[AdminOrderSummary])
def list_all_orders(
    status_filter: Optional[str] = None,
    ctx: TenantContext = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """Supervise l'ensemble des bons de commande administratifs soumis sur la plateforme."""
    query = select(PurchaseOrder).order_by(desc(PurchaseOrder.created_at))
    if status_filter:
        query = query.where(PurchaseOrder.status == status_filter.lower())

    orders = db.execute(query).scalars().all()
    results = []
    for o in orders:
        org = db.get(Organization, o.org_id)
        results.append(
            AdminOrderSummary(
                id=o.id,
                org_id=o.org_id,
                org_name=org.name if org else "Organisation inconnue",
                order_ref=o.order_ref,
                client_type=o.client_type,
                entity_name=o.entity_name,
                contact_name=o.contact_name,
                contact_email=o.contact_email,
                target_plan=o.target_plan,
                duration_months=o.duration_months,
                amount_dzd=o.amount_dzd,
                status=o.status,
                license_token=o.license_token,
                created_at=o.created_at,
                valid_until=o.valid_until,
            )
        )
    return results


@router.post("/orders/{order_id}/approve", response_model=AdminOrderSummary)
def approve_order_endpoint(
    order_id: str,
    payload: Optional[ApproveOrderRequest] = None,
    ctx: TenantContext = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """
    Valide un bon de commande : émet le jeton SP-LIC et active le plan de l'organisation.
    """
    notes = payload.admin_notes if payload else None
    validator_id = ctx.user.id if ctx.user else None

    try:
        order = approve_purchase_order(
            session=db,
            order_id=order_id,
            validator_id=validator_id,
            admin_notes=notes,
        )
        db.commit()
        db.refresh(order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    org = db.get(Organization, order.org_id)
    return AdminOrderSummary(
        id=order.id,
        org_id=order.org_id,
        org_name=org.name if org else "",
        order_ref=order.order_ref,
        client_type=order.client_type,
        entity_name=order.entity_name,
        contact_name=order.contact_name,
        contact_email=order.contact_email,
        target_plan=order.target_plan,
        duration_months=order.duration_months,
        amount_dzd=order.amount_dzd,
        status=order.status,
        license_token=order.license_token,
        created_at=order.created_at,
        valid_until=order.valid_until,
    )


@router.post("/orders/{order_id}/reject", response_model=AdminOrderSummary)
def reject_order_endpoint(
    order_id: str,
    payload: RejectOrderRequest,
    ctx: TenantContext = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """Rejette un bon de commande avec motif officiel."""
    validator_id = ctx.user.id if ctx.user else None
    try:
        order = reject_purchase_order(
            session=db,
            order_id=order_id,
            reason=payload.reason,
            validator_id=validator_id,
        )
        db.commit()
        db.refresh(order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    org = db.get(Organization, order.org_id)
    return AdminOrderSummary(
        id=order.id,
        org_id=order.org_id,
        org_name=org.name if org else "",
        order_ref=order.order_ref,
        client_type=order.client_type,
        entity_name=order.entity_name,
        contact_name=order.contact_name,
        contact_email=order.contact_email,
        target_plan=order.target_plan,
        duration_months=order.duration_months,
        amount_dzd=order.amount_dzd,
        status=order.status,
        license_token=order.license_token,
        created_at=order.created_at,
        valid_until=order.valid_until,
    )


@router.get("/organizations", response_model=List[AdminOrgSummary])
def list_all_organizations(
    ctx: TenantContext = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """Liste exhaustive des organisations locataires, leurs quotas et leur statut."""
    orgs = db.execute(select(Organization).order_by(desc(Organization.created_at))).scalars().all()
    results = []
    for org in orgs:
        member_cnt = db.execute(select(func.count(Membership.id)).where(Membership.org_id == org.id)).scalar() or 0
        net_cnt = db.execute(select(func.count(Network.id)).where(Network.org_id == org.id)).scalar() or 0
        results.append(
            AdminOrgSummary(
                id=org.id,
                name=org.name,
                slug=org.slug,
                billing_plan=org.billing_plan,
                billing_status=org.billing_status,
                org_type=org.org_type,
                created_at=org.created_at,
                license_valid_until=org.license_valid_until,
                member_count=member_cnt,
                network_count=net_cnt,
            )
        )
    return results


@router.post("/organizations/{org_id}/extend-trial")
def extend_trial_period(
    org_id: str,
    days: int = 14,
    ctx: TenantContext = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """Prolonge la période d'évaluation ou de licence d'une organisation."""
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation introuvable.")

    now = datetime.now(timezone.utc)
    base_date = org.license_valid_until if org.license_valid_until and org.license_valid_until > now else now
    org.license_valid_until = base_date + timedelta(days=days)
    org.billing_status = "active"

    db.commit()
    return {
        "status": "success",
        "message": f"Période prolongée de {days} jours pour l'organisation {org.name}.",
        "new_valid_until": org.license_valid_until.isoformat(),
    }
