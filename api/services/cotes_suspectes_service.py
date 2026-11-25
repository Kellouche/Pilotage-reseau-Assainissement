"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-21
Date de modification : 2026-11-24
Objet : Service de détection, consignation et validation des cotes nodales suspectes.
Garantit la rigueur des données d'entrée hydrauliques (Human-in-the-Loop).
================================================================================
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from api.models import Project, NodeCoteValidation

logger = logging.getLogger("swmm_platform.services.cotes_suspectes")

SEUIL_PROFONDEUR_MAX_M = 15.0  # Au-delà de 15m dans un réseau d'assainissement standard, suspicion d'erreur cm/mm


def suggerer_correction_profondeur(prof_brute: float) -> Optional[float]:
    """
    Suggère une correction d'échelle (cm ou mm -> mètres) pour une profondeur suspecte.
    Ex : 198.0 -> 1.98 m ; 2600.0 -> 2.60 m.
    """
    if prof_brute is None or prof_brute <= SEUIL_PROFONDEUR_MAX_M:
        return None
    if prof_brute >= 1000.0:
        return round(prof_brute / 1000.0, 3)
    if prof_brute > SEUIL_PROFONDEUR_MAX_M:
        return round(prof_brute / 100.0, 3)
    return None


def synchroniser_cotes_suspectes_projet(db: Session, project: Project) -> List[NodeCoteValidation]:
    """
    Scanne le réseau du projet pour identifier les regards aux cotes/profondeurs suspectes,
    et les consigne dans la table node_cote_validations (statut 'a_valider') sans modifier le GPKG.
    Préserve strictement les validations existantes déjà effectuées par l'utilisateur.
    """
    from api.services.profil_topo_service import _charger_topo_pour_profil
    from pathlib import Path

    if not project or not project.source_gpkg_key:
        return []

    gpkg_path = Path(project.source_gpkg_key)
    if not gpkg_path.exists():
        return []

    try:
        topo = _charger_topo_pour_profil(gpkg_path)
        node_index = topo.get("node_index") or {}
    except Exception as e:
        logger.warning("Impossible de charger la topologie pour audit cotes suspectes: %s", e)
        return []

    # Cotes existantes en base
    existantes = {
        (rec.node_id, rec.champ): rec
        for rec in db.query(NodeCoteValidation).filter(
            NodeCoteValidation.project_id == project.id,
            NodeCoteValidation.org_id == project.org_id,
        ).all()
    }

    nouveaux = []
    for nid, info in node_index.items():
        prof = info.get("profondeur")
        if prof is not None and prof > SEUIL_PROFONDEUR_MAX_M:
            cle = (str(nid), "profondeur")
            if cle not in existantes:
                sugg = suggerer_correction_profondeur(prof)
                unite_suspectee = "millimètres" if prof >= 1000 else "centimètres"
                motif = (
                    f"Profondeur excessive ({prof:.1f} m > {SEUIL_PROFONDEUR_MAX_M:.0f} m) — "
                    f"probable saisie en {unite_suspectee} ({sugg:.2f} m suggéré)"
                )
                rec = NodeCoteValidation(
                    org_id=project.org_id,
                    project_id=project.id,
                    node_id=str(nid),
                    champ="profondeur",
                    valeur_brute=float(prof),
                    valeur_suggeree=float(sugg) if sugg is not None else None,
                    valeur_validee=None,
                    statut="a_valider",
                    motif_suspicion=motif,
                )
                db.add(rec)
                nouveaux.append(rec)
                existantes[cle] = rec

    if nouveaux:
        db.commit()
        for r in nouveaux:
            db.refresh(r)
        logger.info("Projet %s : %d nouvelle(s) cote(s) suspecte(s) consignée(s)", project.id, len(nouveaux))

    return list(existantes.values())


def lister_cotes_suspectes_projet(
    db: Session, project: Project, statut: Optional[str] = None, force_rescan: bool = False
) -> List[NodeCoteValidation]:
    """
    Retourne la liste des cotes suspectes consignées pour un projet.
    Ne déclenche la synchronisation lourde depuis le GPKG que si aucun enregistrement
    n'existe encore en base de données ou si un rescan explicite est demandé.
    """
    if force_rescan:
        synchroniser_cotes_suspectes_projet(db, project)
    else:
        nb_existants = db.query(NodeCoteValidation).filter(
            NodeCoteValidation.project_id == project.id,
            NodeCoteValidation.org_id == project.org_id,
        ).count()
        if nb_existants == 0:
            synchroniser_cotes_suspectes_projet(db, project)

    q = db.query(NodeCoteValidation).filter(
        NodeCoteValidation.project_id == project.id,
        NodeCoteValidation.org_id == project.org_id,
    )
    if statut:
        q = q.filter(NodeCoteValidation.statut == statut)
    return q.order_by(NodeCoteValidation.node_id.asc()).all()


def valider_cotes_suspectes_service(
    db: Session,
    project: Project,
    validations: List[Dict[str, Any]],
    user_id: Optional[str] = None,
) -> List[NodeCoteValidation]:
    """
    Valide ou confirme un ensemble de cotes suspectes de manière instantanée.
    Chaque item : { "node_id": str, "champ": str, "action": "valider"|"conserve_brut", "valeur_validee": float|None }
    """
    modifies = []
    maintenant = datetime.now(timezone.utc)

    for item in validations:
        nid = str(item.get("node_id"))
        champ = str(item.get("champ", "profondeur"))
        action = item.get("action", "valider")

        rec = (
            db.query(NodeCoteValidation)
            .filter(
                NodeCoteValidation.project_id == project.id,
                NodeCoteValidation.org_id == project.org_id,
                NodeCoteValidation.node_id == nid,
                NodeCoteValidation.champ == champ,
            )
            .first()
        )

        if not rec:
            val_brute = float(item.get("valeur_brute", 0.0))
            rec = NodeCoteValidation(
                org_id=project.org_id,
                project_id=project.id,
                node_id=nid,
                champ=champ,
                valeur_brute=val_brute,
                valeur_suggeree=suggerer_correction_profondeur(val_brute),
            )
            db.add(rec)

        if action == "conserve_brut":
            rec.statut = "conserve_brut"
            rec.valeur_validee = rec.valeur_brute
            rec.commentaire = item.get("commentaire") or "Valeur brute confirmée par l'hydraulicien"
        else:
            rec.statut = "valide"
            v = item.get("valeur_validee")
            if v is not None:
                rec.valeur_validee = float(v)
            elif rec.valeur_suggeree is not None:
                rec.valeur_validee = rec.valeur_suggeree
            else:
                rec.valeur_validee = rec.valeur_brute
            rec.commentaire = item.get("commentaire") or f"Cote certifiée à {rec.valeur_validee:.2f} m"

        rec.validated_by_id = user_id
        rec.validated_at = maintenant
        modifies.append(rec)

    db.commit()
    for m in modifies:
        db.refresh(m)

    return modifies


def obtenir_map_validations_projet(db: Session, project_id: str, org_id: str) -> Dict[str, Dict[str, Any]]:
    """
    Retourne {node_id: {champ: {statut, valeur_validee, valeur_brute}}}
    pour intégration directe dans get_profil_en_long et sections_inp.
    """
    recs = (
        db.query(NodeCoteValidation)
        .filter(
            NodeCoteValidation.project_id == project_id,
            NodeCoteValidation.org_id == org_id,
        )
        .all()
    )
    result: Dict[str, Dict[str, Any]] = {}
    for r in recs:
        if r.node_id not in result:
            result[r.node_id] = {}
        result[r.node_id][r.champ] = {
            "statut": r.statut,
            "valeur_validee": r.valeur_validee,
            "valeur_brute": r.valeur_brute,
            "valeur_suggeree": r.valeur_suggeree,
            "motif_suspicion": r.motif_suspicion,
        }
    return result
