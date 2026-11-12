# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : LOT P1.3 — Résolution des apports DWF pour une simulation

Point d'entrée UNIQUE de récupération des apports de temps sec actifs
d'un projet, strictement borné à (org_id, project_id). Le résultat est
une liste de dicts sérialisables (contrat ApportDwf.to_dict()) prête à
être transmise au moteur INP — aucune dépendance FastAPI.

La liaison aux versions GPKG exactes (snapshot simulé vs nœuds des
apports) est déléguée à P1.4 : la fonction `resoudre_apports_dwf`
est isolée pour permettre cette évolution sans refonte. En attendant,
sections_inp filtre les apports sur les nœuds réellement émis dans le
.inp (un apport orphelin d'une version ultérieure est ignoré, tracé
dans la provenance).
================================================================================
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger("swmm_platform.services.apports_dwf")


def resoudre_apports_dwf(db: Session, proj: Any) -> List[Dict[str, Any]]:
    """
    Retourne les apports DWF actifs du projet, STRICTEMENT dans le
    périmètre organisation/projet (org_id ET project_id du projet résolu).
    Aucun `.first()` arbitraire : filtrage explicite sur les deux clés.
    """
    from api.models import ApportDwf

    if proj is None:
        return []
    rows = (
        db.query(ApportDwf)
        .filter(
            ApportDwf.org_id == proj.org_id,
            ApportDwf.project_id == proj.id,
            ApportDwf.actif.is_(True),
        )
        .order_by(ApportDwf.created_at, ApportDwf.id)
        .all()
    )
    return [r.to_dict() for r in rows]


def empreinte_apports(apports: List[Dict[str, Any]]) -> str:
    """Empreinte canonique du jeu d'apports (pour la clé de cache)."""
    from src.domain.moteur_swmm.dwf_injection import empreinte_apports_dwf
    return empreinte_apports_dwf(apports or [])


def preparer_apports_pour_simulation(
    db: Session,
    proj: Any,
    dwf_actif: Optional[bool] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Résout les apports à injecter pour une simulation.

    `dwf_actif` : None/True → apports actifs du projet injectés (défaut,
    DWF actif en temps sec comme en pluie) ; False → désactivation
    explicite du scénario, aucun apport injecté.

    Retourne (apports_a_injecter, info_cache) où info_cache contient
    l'empreinte à intégrer dans params_dict (clé de cache) :
      - "apports_dwf_sha256" : empreinte du jeu résolu ;
      - "dwf_actif"          : drapeau explicite de désactivation.
    """
    actif = dwf_actif is not False  # None et True → injection autorisée
    if not actif or proj is None:
        return [], {"dwf_actif": False,
                    "apports_dwf_sha256": empreinte_apports([])}
    apports = resoudre_apports_dwf(db, proj)
    return apports, {
        "dwf_actif": True,
        "apports_dwf_sha256": empreinte_apports(apports),
        "apports_dwf_count": len(apports),
    }
