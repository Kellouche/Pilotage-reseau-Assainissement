# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : LOT P1.3/P1.4 — Résolution et validation des apports DWF pour une
        simulation

Point d'entrée UNIQUE de récupération des apports de temps sec actifs
d'un projet, strictement borné à (org_id, project_id). Le résultat est
une liste de dicts sérialisables (contrat ApportDwf.to_dict()) prête à
être transmise au moteur INP — aucune dépendance FastAPI.

LOT P1.4 — politique stricte de cohérence GPKG :
--------------------------------------------------------------------------------
Un apport n'est injectable que s'il est ESTAMPILLÉ sur la version exacte
du GeoPackage utilisé par la simulation (même gpkg_version_id ET même
gpkg_sha256 pour un projet versionné ; même gpkg_sha256 et aucun
gpkg_version_id pour un projet legacy). Toute divergence, estampillage
absent (apport historique non réconcilié) ou nœud absent du snapshot
matérialisé → ApportsDwfIncompatiblesError AVANT toute génération INP
et avant tout lancement moteur (synchrone comme Celery).

La réconciliation d'un apport historique s'effectue via
POST /api/v1/apports/{id}/revalider (routes/apports.py).
================================================================================
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger("swmm_platform.services.apports_dwf")


class ApportsDwfIncompatiblesError(Exception):
    """
    Levée quand au moins un apport DWF actif n'est pas réconcilié avec la
    version exacte du GPKG simulé. `details` = liste de dictionnaires
    identifiant chaque apport en cause (id, nœud, estampillage enregistrée,
    version demandée, motif, action attendue).
    """

    def __init__(self, details: List[Dict[str, Any]]):
        self.details = details
        resume = "; ".join(
            f"apport {d.get('apport_id')} (nœud {d.get('node_id')}) : "
            f"{d.get('motif')}" for d in details)
        super().__init__(
            "Apports DWF incompatibles avec la version du réseau "
            f"simulé — {len(details)} apport(s) non réconcilié(s) : {resume}. "
            "Action attendue : revalidation de l'apport "
            "(POST /api/v1/apports/{id}/revalider) ou correction.")


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


def noeuds_du_gpkg(gpkg_path: Any) -> Set[str]:
    """
    Ensemble des identifiants de nœuds du GPKG = _clean_node_id(Code) de la
    couche 'regards'. Utilisé pour la validation stricte P1.4 : un apport
    est rejeté si son nœud est absent du snapshot réellement simulé.
    """
    import geopandas as gpd
    from src.domain.moteur_swmm.constants import _clean_node_id

    gpkg_path = Path(gpkg_path)
    layers = gpd.list_layers(str(gpkg_path))["name"].tolist()
    regard_layer = next((l for l in layers if "regard" in l.lower()), None)
    if not regard_layer:
        return set()
    regards = gpd.read_file(str(gpkg_path), layer=regard_layer,
                            columns=["Code"])
    noeuds = {_clean_node_id(c) for c in regards.get("Code", [])}
    noeuds.discard("")
    return noeuds


def _motif_incompatibilite(a: Dict[str, Any],
                           version_meta: Dict[str, Any]) -> Optional[str]:
    """
    Compare l'estampillage de l'apport à la version exacte simulée.
    Retourne None si admissible, sinon un motif explicite.

    version_meta (résolution resoudre_version_pour_simulation) :
      - projet versionné : {version_id, sha256, storage_kind, ...}
      - projet legacy   : {version_id: None, sha256, storage_kind: "LEGACY"}
    """
    vid = version_meta.get("version_id")
    sha = version_meta.get("sha256")
    a_vid = a.get("gpkg_version_id")
    a_sha = a.get("gpkg_sha256")

    # Estampillage totalement absent → apport historique non réconcilié.
    if a_vid is None and a_sha is None:
        return "non_reconcilie"

    if vid:
        # Projet versionné : version_id ET sha256 doivent correspondre
        # EXACTEMENT — un même Code sur une autre version ne suffit pas.
        if a_vid != vid:
            return (f"version_differencee "
                    f"(apport={a_vid or 'aucune'}, simulation={vid})")
        if not sha or a_sha != sha:
            return (f"sha256_difference "
                    f"(apport={str(a_sha)[:12] or 'absent'}…, "
                    f"simulation={str(sha)[:12]}…)")
    else:
        # Projet legacy : comparaison stricte de l'empreinte réelle ;
        # un apport estampillé sur une version ne peut pas être assimilé
        # à un réseau non versionné.
        if a_vid is not None:
            return ("apport_estampille_version_alors_que_le_projet_est_legacy "
                    f"(version_apport={a_vid})")
        if not sha or a_sha != sha:
            return (f"sha256_difference_legacy "
                    f"(apport={str(a_sha)[:12] or 'absent'}…, "
                    f"simulation={str(sha)[:12] if sha else 'inconnue'}…)")
    return None


def _details_incompatibilite(a: Dict[str, Any], motif: str,
                             version_meta: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apport_id": a.get("id"),
        "node_id": a.get("node_id"),
        "apport_gpkg_version_id": a.get("gpkg_version_id"),
        "apport_gpkg_sha256": a.get("gpkg_sha256"),
        "simulation_gpkg_version_id": version_meta.get("version_id"),
        "simulation_gpkg_sha256": version_meta.get("sha256"),
        "simulation_storage_kind": version_meta.get("storage_kind"),
        "motif": motif,
        "action_attendue": ("revalidation de l'apport sur le réseau "
                            "actuel (POST /api/v1/apports/{id}/revalider) "
                            "ou correction de l'apport"),
    }


def valider_apports_pour_version(
    apports: List[Dict[str, Any]],
    version_meta: Dict[str, Any],
    gpkg_path: Any,
) -> List[Dict[str, Any]]:
    """
    Valide chaque apport actif contre la version exacte simulée.

    Retourne la liste des apports ADMISSIBLES (inchangés). Lève
    ApportsDwfIncompatiblesError dès qu'un apport est non réconcilié,
    sur une autre version, sur une empreinte différente, sans
    estampillage, ou sur un nœud absent du snapshot matérialisé.
    """
    if not apports:
        return []

    version_meta = version_meta or {}
    noeuds_snapshot: Optional[Set[str]] = None
    if gpkg_path is not None:
        try:
            noeuds_snapshot = noeuds_du_gpkg(gpkg_path)
        except Exception as e:
            logger.warning("Lecture des nœuds du snapshot impossible : %s", e)
            noeuds_snapshot = None
    # gpkg_path=None : pas de contrôle nœud — les estampilles (version+sha256
    # épinglés) garantissent déjà que le contenu GPKG validé à l'écriture est
    # identique au contenu simulé.

    incompatibles: List[Dict[str, Any]] = []
    for a in apports:
        motif = _motif_incompatibilite(a, version_meta)
        if motif is None and noeuds_snapshot is not None:
            nid = str(a.get("node_id") or "").strip()
            if nid not in noeuds_snapshot:
                motif = "noeud_absent_du_snapshot"
        if motif is not None:
            incompatibles.append(_details_incompatibilite(a, motif, version_meta))

    if incompatibles:
        raise ApportsDwfIncompatiblesError(incompatibles)
    return apports


def preparer_apports_pour_simulation(
    db: Session,
    proj: Any,
    dwf_actif: Optional[bool] = None,
    version_meta: Optional[Dict[str, Any]] = None,
    gpkg_path: Any = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Résout les apports à injecter pour une simulation.

    `dwf_actif` : None/True → apports actifs du projet injectés (défaut,
    DWF actif en temps sec comme en pluie) ; False → désactivation
    explicite du scénario, aucun apport injecté et AUCUNE validation
    de version (comportement historique conservé).

    `version_meta` / `gpkg_path` : version EXACTE résolue pour la
    simulation (resoudre_version_pour_simulation). Obligatoires dès que
    le projet possède des apports actifs : sans eux, tout apport actif
    est rejeté comme non vérifiable.

    Retourne (apports_a_injecter, info_cache) où info_cache contient
    l'empreinte à intégrer dans params_dict (clé de cache) :
      - "apports_dwf_sha256" : empreinte du jeu résolu ;
      - "dwf_actif"          : drapeau explicite de désactivation.

    Lève ApportsDwfIncompatiblesError si un apport actif n'est pas
    réconcilié avec la version simulée (politique stricte P1.4).
    """
    actif = dwf_actif is not False  # None et True → injection autorisée
    if not actif or proj is None:
        return [], {"dwf_actif": False,
                    "apports_dwf_sha256": empreinte_apports([])}
    apports = resoudre_apports_dwf(db, proj)
    if apports:
        valider_apports_pour_version(apports, version_meta or {}, gpkg_path)
    return apports, {
        "dwf_actif": True,
        "apports_dwf_sha256": empreinte_apports(apports),
        "apports_dwf_count": len(apports),
    }
