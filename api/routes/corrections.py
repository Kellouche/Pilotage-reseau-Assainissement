"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-27
Objet : Endpoints de validation et d'application des correctifs topologiques
================================================================================
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import Canalisation, Regard
from api.core.security import get_tenant_context, require_role, TenantContext

router = APIRouter()


def _round_or_none(value, digits=2):
    return round(value, digits) if value is not None else None


def _observed_slope(conduite: Canalisation):
    if (
        conduite.prof_fe_am is None
        or conduite.prof_fe_av is None
        or conduite.longueur is None
        or conduite.longueur <= 0
    ):
        return None
    return (conduite.prof_fe_am - conduite.prof_fe_av) / conduite.longueur


def _median(values):
    ordered = sorted(values)
    count = len(ordered)
    if count == 0:
        return None
    middle = count // 2
    if count % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _representative_slope(db: Session, conduite: Canalisation):
    """
    Compute an observed representative slope from already documented conduites.
    Priority: same diameter/material/function, then same diameter, then global sample.
    """
    base_query = db.query(Canalisation).filter(
        Canalisation.id != conduite.id,
        Canalisation.longueur != None,
        Canalisation.longueur > 0,
        Canalisation.prof_fe_am != None,
        Canalisation.prof_fe_av != None,
    )

    query = base_query
    if conduite.diametre:
        query = query.filter(Canalisation.diametre == conduite.diametre)
    if conduite.materiau:
        query = query.filter(Canalisation.materiau == conduite.materiau)
    if conduite.fonction_mt:
        query = query.filter(Canalisation.fonction_mt == conduite.fonction_mt)

    candidates = query.limit(300).all()
    if len(candidates) < 5 and conduite.diametre:
        candidates = base_query.filter(Canalisation.diametre == conduite.diametre).limit(300).all()
    if len(candidates) < 5:
        candidates = base_query.limit(500).all()

    slopes = []
    for candidate in candidates:
        slope = _observed_slope(candidate)
        if slope is None:
            continue
        # Keep plausible gravity slopes only. This is not a fixed design slope.
        if 0 < slope <= 0.05:
            slopes.append(slope)

    return _median(slopes), len(slopes)


def _unavailable_suggestion(message, source_count=0, slope=None):
    return {
        "available": False,
        "confidence": "indisponible",
        "prof_fe_am": None,
        "prof_fe_av": None,
        "pente_pourcent": _round_or_none(slope * 100 if slope is not None else None, 3),
        "source_count": source_count,
        "message": message,
    }


@router.post("/manuel/{fid}")
def correction_manuelle(
    fid: str,
    data: Dict[str, Any],
    ctx: TenantContext = Depends(require_role("engineer")),
    db: Session = Depends(get_db)
):
    """
    Apply a manual correction to a conduite (stealth 404 si hors organisation).
    """
    conduite = db.query(Canalisation).filter(
        Canalisation.fid == fid,
        Canalisation.org_id == ctx.org_id
    ).first()
    if not conduite:
        raise HTTPException(status_code=404, detail="Ressource introuvable")

    modifications = 0
    if "prof_fe_am" in data:
        conduite.prof_fe_am = data["prof_fe_am"]
        modifications += 1
    if "prof_fe_av" in data:
        conduite.prof_fe_av = data["prof_fe_av"]
        modifications += 1
    if "id_amont" in data:
        conduite.id_amont = data["id_amont"]
        modifications += 1
    if "id_aval" in data:
        conduite.id_aval = data["id_aval"]
        modifications += 1

    if modifications > 0:
        db.commit()
        return {"status": "success", "message": f"{modifications} champ(s) mis a jour pour {fid}"}
    return {"status": "info", "message": "Aucune modification apportee"}




@router.post("/automatique")
def correction_automatique(
    ctx: TenantContext = Depends(require_role("engineer")),
    db: Session = Depends(get_db)
):
    """
    Batch repair for obvious topology issues for the active organization.
    """
    conduites = db.query(Canalisation).filter(
        Canalisation.org_id == ctx.org_id,
        (Canalisation.id_amont == None) | (Canalisation.id_amont == "")
    ).limit(50).all()

    corrections_faites = 0
    for conduite in conduites:
        conduite.id_amont = "FIX_AUTO_AMONT"
        corrections_faites += 1

    db.commit()
    return {"status": "success", "message": f"{corrections_faites} conduites corrigees automatiquement."}