# -*- coding: utf-8 -*-
"""
Module api.routes.licensing : Endpoints de gestion des licences, bons de commande et factures proforma (DZD).
Conforme à ADR 0006 et Roadmap SaaS Phase 3.
Isolation stricte par org_id et validation RBAC.

Auteur : Dr Abdelhakim Kellouche / Antigravity
Date : Octobre 2026
"""

from datetime import datetime
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, UploadFile, File, Form, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import Organization, PurchaseOrder, User
from api.core.security import get_tenant_context, require_role, TenantContext
from api.core.licensing import (
    submit_purchase_order,
    activate_license_token,
    check_license_validity,
    calculate_default_amount_dzd,
)
from api.core.proforma import generate_proforma_pdf, generate_purchase_order_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/license", tags=["Licences & Facturation B2B/B2G"])


# ============================================================
# SCHÉMAS PYDANTIC
# ============================================================

class LicenseStatusResponse(BaseModel):
    is_valid: bool
    is_expired: bool
    days_remaining: Optional[int]
    plan: str
    valid_until: Optional[str]
    message: str


class ActivateTokenRequest(BaseModel):
    license_token: str = Field(..., min_length=10, description="Clé d'activation SP-LIC-...")


class PurchaseOrderSummary(BaseModel):
    id: str
    order_ref: str
    client_type: str
    entity_name: str
    contact_name: str
    target_plan: str
    duration_months: int
    amount_dzd: float
    status: str
    license_token: Optional[str] = None
    created_at: datetime
    valid_until: Optional[datetime] = None


# ============================================================
# ENDPOINTS
# ============================================================

@router.get("/status", response_model=LicenseStatusResponse)
def get_license_status(
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Retourne l'état de validité de la licence de l'organisation connectée."""
    info = check_license_validity(ctx.org)
    return LicenseStatusResponse(**info)


@router.get("/orders", response_model=List[PurchaseOrderSummary])
def list_organization_orders(
    ctx: TenantContext = Depends(require_role("engineer")),
    db: Session = Depends(get_db),
):
    """Liste tous les bons de commande de l'organisation active (cloisonnement strict par org_id)."""
    orders = db.execute(
        select(PurchaseOrder)
        .where(PurchaseOrder.org_id == ctx.org_id)
        .order_by(desc(PurchaseOrder.created_at))
    ).scalars().all()

    return [
        PurchaseOrderSummary(
            id=o.id,
            order_ref=o.order_ref,
            client_type=o.client_type,
            entity_name=o.entity_name,
            contact_name=o.contact_name,
            target_plan=o.target_plan,
            duration_months=o.duration_months,
            amount_dzd=o.amount_dzd,
            status=o.status,
            license_token=o.license_token,
            created_at=o.created_at,
            valid_until=o.valid_until,
        )
        for o in orders
    ]


@router.post("/order", response_model=PurchaseOrderSummary, status_code=status.HTTP_201_CREATED)
async def create_purchase_order(
    order_ref: str = Form(..., description="Référence du Bon de Commande (ex: BC-2026-BET-01)"),
    entity_name: str = Form(..., description="Raison sociale ou dénomination de l'organisme"),
    client_type: str = Form("bet", description="bet, entreprise, regie, universite, etc."),
    contact_name: str = Form(""),
    contact_email: str = Form(""),
    contact_phone: str = Form(""),
    target_plan: str = Form("bet"),
    duration_months: int = Form(12),
    notes: Optional[str] = Form(None),
    document: Optional[UploadFile] = File(None),
    ctx: TenantContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Enregistre un Bon de Commande officiel avec dépôt éventuel du scan justificatif.
    Réservé aux administrateurs ou gestionnaires de l'organisation.
    """
    doc_bytes = None
    doc_filename = None
    if document:
        doc_bytes = await document.read()
        doc_filename = document.filename

    c_email = contact_email or (ctx.user.email if ctx.user else "")
    c_name = contact_name or (ctx.user.full_name if ctx.user else "")

    try:
        order = submit_purchase_order(
            session=db,
            org_id=ctx.org_id,
            order_ref=order_ref,
            client_type=client_type,
            entity_name=entity_name,
            contact_name=c_name,
            contact_email=c_email,
            contact_phone=contact_phone,
            target_plan=target_plan,
            duration_months=duration_months,
            document_bytes=doc_bytes,
            document_filename=doc_filename,
            notes=notes,
        )
        db.commit()
        db.refresh(order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return PurchaseOrderSummary(
        id=order.id,
        order_ref=order.order_ref,
        client_type=order.client_type,
        entity_name=order.entity_name,
        contact_name=order.contact_name,
        target_plan=order.target_plan,
        duration_months=order.duration_months,
        amount_dzd=order.amount_dzd,
        status=order.status,
        license_token=order.license_token,
        created_at=order.created_at,
        valid_until=order.valid_until,
    )


@router.post("/activate")
def activate_license(
    payload: ActivateTokenRequest,
    ctx: TenantContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Active une clé de licence officielle sur l'organisation en cours.
    Réservé aux administrateurs ou propriétaires de l'organisation.
    """
    success, msg, valid_until = activate_license_token(
        session=db,
        org_id=ctx.org_id,
        token_str=payload.license_token,
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    db.commit()
    return {
        "status": "success",
        "message": msg,
        "valid_until": valid_until.isoformat() if valid_until else None,
        "active_plan": ctx.org.billing_plan,
    }


@router.get("/proforma")
def download_proforma_pdf(
    plan: str = Query("bet", description="Formule demandée : bet ou exploitation"),
    duration_months: int = Query(12, description="Durée de l'engagement en mois (6, 12, 24, 36)"),
    doc_type: str = Query("proforma", description="proforma ou devis"),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Génère et télécharge le document PDF officiel d'un Devis ou d'une Facture Proforma
    en Dinars Algériens (DZD) pour l'organisation connectée.
    """
    contact_name = ctx.user.full_name if ctx.user else ""
    contact_email = ctx.user.email if ctx.user else ""

    pdf_bytes = generate_proforma_pdf(
        org_name=ctx.org.name,
        contact_name=contact_name,
        contact_email=contact_email,
        plan=plan,
        duration_months=duration_months,
        doc_type=doc_type,
    )

    clean_slug = ctx.org.slug or "swmm"
    filename = f"proforma_{clean_slug}_{plan}_{duration_months}m.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Cache-Control": "no-cache",
        },
    )
