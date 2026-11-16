# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : Paramétrage du garde-fou hydraulicien (Agent 0) par projet.

GET  /projets/{project_id}/garde-fou          → config + catalogue
PUT  /projets/{project_id}/garde-fou          → enregistre seuils/preset/profil
POST /projets/{project_id}/garde-fou/reaudit  → ré-évalue l'historique du projet

Isolation stricte org/projet (stealth 404), mêmes règles de résolution que
les apports DWF : jamais de `.first()` arbitraire, multi-projets → 409.
================================================================================
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.core.security import TenantContext, get_tenant_context, require_role
from api.database import get_db
from api.models import Project
from api.services.garde_fou_service import (
    config_bare,
    config_effective,
    decrire_catalogue,
    reevaluer_garde_fou_projet,
)
from api.services.simulation_service import (
    ContexteSimulationIntrouvable,
    ProjetAmbigu,
    _resoudre_projet_pour_simulation,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projets", tags=["Garde-fou hydraulicien"])


class GardeFouConfigRequete(BaseModel):
    """Corps PUT : uniquement les champs connus sont persistés."""
    preset: Optional[str] = None
    profil_reseau: Optional[str] = None
    seuils: Optional[Dict[str, Any]] = None
    checks_actives: Optional[Dict[str, Any]] = None


class GardeFouReauditRequete(BaseModel):
    appliquer: bool = True


def _resoudre_projet(db: Session, tenant: TenantContext,
                     project_id: str) -> Project:
    try:
        return _resoudre_projet_pour_simulation(db, tenant.org_id, project_id)
    except ProjetAmbigu as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContexteSimulationIntrouvable:
        raise HTTPException(
            status_code=404, detail="Projet introuvable ou non autorisé.")


@router.get("/{project_id}/garde-fou")
def lire_config_garde_fou(
    project_id: str,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Configuration effective + catalogue (seuils, presets, profils)."""
    proj = _resoudre_projet(db, tenant, project_id)
    brut = proj.garde_fou_config or {}
    return {
        "project_id": proj.id,
        "project_name": proj.name,
        "config_brute": brut,
        "config_effective": config_effective(brut),
        "catalogue": decrire_catalogue(),
    }


@router.put("/{project_id}/garde-fou")
def ecrire_config_garde_fou(
    project_id: str,
    payload: GardeFouConfigRequete,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_role("engineer")),
):
    """Enregistre le paramétrage garde-fou du projet (seuils, preset, profil)."""
    proj = _resoudre_projet(db, tenant, project_id)
    # model_dump() complet (pas d'exclude_none) : un profil_reseau=null doit
    # pouvoir EFFACER la valeur précédente, pas être ignoré.
    brut = config_bare(payload.model_dump())
    proj.garde_fou_config = brut or None
    db.commit()
    db.refresh(proj)
    return {
        "status": "success",
        "project_id": proj.id,
        "config_brute": proj.garde_fou_config,
        "config_effective": config_effective(proj.garde_fou_config),
    }


@router.post("/{project_id}/garde-fou/reaudit")
def reaudit_garde_fou(
    project_id: str,
    payload: Optional[GardeFouReauditRequete] = None,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_role("engineer")),
):
    """
    Ré-évalue les simulations `completed` du projet avec la configuration
    courante. `appliquer=false` = dry-run (rapport sans écriture).
    """
    proj = _resoudre_projet(db, tenant, project_id)
    appliquer = payload.appliquer if payload else True
    resultat = reevaluer_garde_fou_projet(db, proj, appliquer=appliquer)
    resultat["applique"] = appliquer
    return resultat
