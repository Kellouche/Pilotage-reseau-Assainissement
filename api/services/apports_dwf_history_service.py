# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : LOT P6.1 — Service d'historisation métier atomique des apports DWF

Garantit la traçabilité immuable (append-only) de chaque mutation
(création, modification, changement de nœud, réconciliation, activation,
désactivation, suppression, exclusion de simulation) au sein de la même
transaction de base de données.
================================================================================
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from api.models import ApportDwfHistory

logger = logging.getLogger(__name__)

# Nomenclature canonique P6 des événements métier d'apports DWF
ACTIONS_AUTORISEES = {
    "create",
    "update",
    "node_change",
    "reconcile",
    "revalidate",  # Alias de compatibilité pour reconcile
    "activate",
    "deactivate",
    "delete",
    "sim_exclusion",
}


def enregistrer_historique_apport(
    db: Session,
    apport_id: str,
    org_id: str,
    project_id: str,
    action: str,
    changed_by_id: Optional[str] = None,
    changed_fields: Optional[Any] = None,
    previous_state: Optional[Dict[str, Any]] = None,
    new_state: Optional[Dict[str, Any]] = None,
) -> ApportDwfHistory:
    """
    Enregistre une entrée d'historique de mutation d'apport DWF.

    IMPORTANT : Cette fonction s'exécute dans la transaction courante
    de la session `db` sans appeler `db.commit()`. L'appelant est
    responsable du commit atomique afin de garantir qu'aucune mutation
    n'est persistée sans son historique (et vice-versa).
    """
    action_clean = str(action or "").strip().lower()
    if action_clean not in ACTIONS_AUTORISEES:
        raise ValueError(
            f"Action '{action}' non reconnue pour l'historique DWF. "
            f"Actions autorisées : {sorted(ACTIONS_AUTORISEES)}"
        )

    # Normalisation : revalidate -> reconcile
    action_canonique = "reconcile" if action_clean == "revalidate" else action_clean

    hist = ApportDwfHistory(
        org_id=org_id,
        project_id=project_id,
        apport_id=apport_id,
        action=action_canonique,
        changed_fields=changed_fields,
        previous_state=previous_state,
        new_state=new_state,
        changed_by_id=changed_by_id,
    )
    db.add(hist)
    return hist


def enregistrer_exclusion_simulation(
    db: Session,
    apport_id: str,
    org_id: str,
    project_id: str,
    simulation_id: Optional[str],
    motif: str,
    details: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
) -> ApportDwfHistory:
    """
    LOT P6.1 — Enregistre l'exclusion d'un apport DWF lors d'une simulation (action: sim_exclusion).
    """
    return enregistrer_historique_apport(
        db=db,
        apport_id=apport_id,
        org_id=org_id,
        project_id=project_id,
        action="sim_exclusion",
        changed_by_id=user_id,
        changed_fields=["simulation_exclusion"],
        previous_state=None,
        new_state={
            "simulation_id": simulation_id,
            "motif": motif,
            "details": details or {},
        },
    )


def lister_historique_apport(
    db: Session,
    org_id: str,
    project_id: Optional[str] = None,
    apport_id: Optional[str] = None,
    action: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> Tuple[List[ApportDwfHistory], int]:
    """
    Consulte l'historique paginé des apports DWF filtré par organisation.

    Isolation multi-tenant stricte : seuls les enregistrements de `org_id`
    sont retournés.
    """
    q = db.query(ApportDwfHistory).filter(ApportDwfHistory.org_id == org_id)

    if project_id:
        q = q.filter(ApportDwfHistory.project_id == project_id)
    if apport_id:
        q = q.filter(ApportDwfHistory.apport_id == apport_id)
    if action:
        act = action.strip().lower()
        if act in ("reconcile", "revalidate"):
            q = q.filter(ApportDwfHistory.action.in_(["reconcile", "revalidate"]))
        else:
            q = q.filter(ApportDwfHistory.action == act)

    total = q.count()
    items = (
        q.order_by(ApportDwfHistory.created_at.desc(), ApportDwfHistory.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return items, total
