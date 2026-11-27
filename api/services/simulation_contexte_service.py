# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Résolution du contexte de simulation : projet explicite, dernier résultat, sélection par bassin, reprise.
================================================================================
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from api.services.simulation_cache_service import est_simulation_valide
from api.services.simulation_execution_service import (
    ContexteSimulation,
    ContexteSimulationIntrouvable,
    ProjetAmbigu,
)
from api.services.simulation_resultat_service import charger_resultat_simulation

logger = logging.getLogger("swmm_platform.services.simulation_contexte_service")


def _resoudre_projet_pour_simulation(db: Session, org_id: Optional[str],
                                    project_id: Optional[str]) -> Any:
    """
    LOT P0.1 — résolution de projet SANS sélection arbitraire et STRICTEMENT
    bornée à l'organisation authentifiée :
      - org_id OBLIGATOIRE : aucun contexte → ContexteSimulationIntrouvable
        (plus de scan de toute la base pour un contexte anonyme) ;
      - project_id explicite → doit exister et appartenir à org_id ;
      - sinon, les projets actifs de l'org : exactement UN seul est
        toléré ; plusieurs → ProjetAmbigu ; zéro → ContexteSimulationIntrouvable.
    """
    from api.models import Project

    if not org_id:
        raise ContexteSimulationIntrouvable("Contexte d'organisation requis.")

    if project_id:
        proj = db.get(Project, project_id)
        if proj is None or proj.is_archived:
            raise ContexteSimulationIntrouvable("Projet introuvable ou archivé.")
        if proj.org_id != org_id:
            raise ContexteSimulationIntrouvable(
                "Le projet demandé n'appartient pas à l'organisation.")
        return proj

    q = db.query(Project).filter(
        Project.is_archived.is_(False), Project.org_id == org_id)
    projets = q.order_by(Project.id).all()
    if not projets:
        raise ContexteSimulationIntrouvable("Aucun projet actif pour ce contexte.")
    if len(projets) > 1:
        raise ProjetAmbigu(
            "Plusieurs projets actifs : un project_id explicite est requis.")
    return projets[0]


def _simulation_correspond_a_bassin(sim: Any, cluster_id: Any = None,
                                    bassin_ref: Optional[str] = None,
                                    exutoire_noeud: Optional[str] = None) -> bool:
    """
    Identité de bassin d'une simulation : bassin_ref > exutoire_noeud >
    cluster_id persisté (summary_kpis) > nom (dernier recours).
    """
    if bassin_ref is not None:
        cible_bassin = str(bassin_ref).strip().lower()
        if sim.bassin_ref and str(sim.bassin_ref).strip().lower() == cible_bassin:
            return True
    if exutoire_noeud is not None:
        cible_ex = str(exutoire_noeud).strip().lower()
        if sim.exutoire_noeud and str(sim.exutoire_noeud).strip().lower() == cible_ex:
            return True
    if cluster_id is None:
        return False
    cible = str(cluster_id).strip().lower()
    if sim.bassin_ref and str(sim.bassin_ref).strip().lower() == cible:
        return True
    if sim.exutoire_noeud and str(sim.exutoire_noeud).strip().lower() == cible:
        return True
    kpis = sim.summary_kpis or {}
    if str(kpis.get("cluster_id", "")).strip().lower() == cible:
        return True
    params = kpis.get("parameters") or {}
    if isinstance(params, dict) and str(params.get("cluster_id", "")).strip().lower() == cible:
        return True
    nom = str(sim.name or "").lower()
    # Correspondance stricte : le cluster_id doit être un segment entier
    # du nom (« _<id>_ »), jamais une sous-chaîne — sinon « 4 » matcherait
    # « _234_ » et « 1 »/« 0 » matcheraient « _10_ » (ex. bassin Ovoide).
    if not (nom and cible):
        return False
    _nom_borne = "_" + nom.strip("_") + "_"
    return f"_{cible}_" in _nom_borne


def resoudre_simulation_courante(
    db: Session,
    org_id: Optional[str] = None,
    project_id: Optional[str] = None,
    simulation_id: Optional[str] = None,
    cluster_id: Any = None,
    bassin_ref: Optional[str] = None,
    exutoire_noeud: Optional[str] = None,
    resoudre_gpkg: bool = True,
    bassin_nom_attendu: Optional[str] = None,
) -> ContexteSimulation:
    """
    Étape 3D.1 — point d'entrée unique de résolution d'une simulation
    AUTORISÉE pour un contexte organisation/projet.

    - `simulation_id` explicite : lookup direct, garde org/projet stricte.
    - sinon : simulation `completed` la plus récente du projet résolu
      (ORDER BY created_at DESC, id DESC — déterministe).
    - filtres de bassin : cluster_id / bassin_ref / exutoire_noeud.
    - le JSON est chargé via `charger_resultat_simulation` (chemin local
      puis clé ArtifactStore — compatible Celery/S3).
    - `resoudre_gpkg=True` résout le snapshot exact via
      `resoudre_gpkg_pour_simulation` (3C.0) ; les erreurs de provenance
      explicite remontent telles quelles (GpkgSimulationError).

    Lève ContexteSimulationIntrouvable / ProjetAmbigu — jamais de
    substitution silencieuse par une simulation d'un autre périmètre.
    """
    from api.models import Simulation

    # Compatibilité : « cluster_id » peut être une référence métier
    # « exutoire:<id> » (anciens appels /bassin/exutoire:NNN). La
    # normaliser en bassin_ref/exutoire_noeud pour que les gardes
    # d'identité comparent dans le bon espace.
    if cluster_id is not None:
        _cid_txt = str(cluster_id).strip()
        if _cid_txt.lower().startswith("exutoire:"):
            _suffixe = _cid_txt.split(":", 1)[1]
            if bassin_ref is None:
                bassin_ref = _cid_txt
            if exutoire_noeud is None:
                exutoire_noeud = _suffixe
            cluster_id = None

    proj = _resoudre_projet_pour_simulation(db, org_id, project_id)
    org_effectif = org_id or proj.org_id

    if simulation_id:
        sim = db.get(Simulation, simulation_id)
        if (sim is None or sim.project_id != proj.id
                or (org_effectif and sim.org_id != org_effectif)):
            raise ContexteSimulationIntrouvable(
                "Simulation introuvable pour ce contexte.")
        data = charger_resultat_simulation(sim)
        if not data or not est_simulation_valide(data):
            raise ContexteSimulationIntrouvable(
                "Résultat de simulation indisponible ou invalide.")
        ctx = ContexteSimulation(simulation=sim, project=proj, data=data,
                                 resolution="simulation_id")
        if resoudre_gpkg:
            _joindre_gpkg(db, proj, ctx)
        return ctx

    q = db.query(Simulation).filter(
        Simulation.project_id == proj.id,
        Simulation.status == "completed",
    )
    if org_effectif:
        q = q.filter(Simulation.org_id == org_effectif)
    candidats = q.order_by(
        Simulation.created_at.desc(), Simulation.id.desc()).limit(80).all()

    # Préférer les simulations produites par la version GPKG courante du
    # projet : même identité de bassin mais provenance la plus fraîche —
    # une sim d'une version antérieure n'est servie qu'à défaut de
    # simulation sur la version affichée (tri stable : created_at DESC
    # reste l'ordre à l'intérieur de chaque groupe).
    _vid_courante = getattr(proj, "gpkg_version_id", None)
    if _vid_courante is not None:
        _vid_txt = str(_vid_courante)
        candidats = sorted(
            candidats,
            key=lambda s: str(getattr(s, "gpkg_version_id", "") or "") == _vid_txt,
            reverse=True)

    for sim in candidats:
        if (cluster_id is not None or bassin_ref is not None
                or exutoire_noeud is not None):
            if not _simulation_correspond_a_bassin(
                    sim, cluster_id=cluster_id, bassin_ref=bassin_ref,
                    exutoire_noeud=exutoire_noeud):
                continue
        # results_s3_key peut être vide pour une sim dont seul ResultStore
        # porte le résultat (identité complète) — ne pas exclure a priori.
        if not sim.results_s3_key and _ref_pour_simulation(sim) is None:
            continue
        data = charger_resultat_simulation(sim)
        if not data or not est_simulation_valide(data):
            continue
        # Garde anti-legacy : d'anciennes simulations portent un
        # cluster_id placeholder (ex. 1 = réseau complet) dans leurs
        # kpis alors que meta.cluster_id du résultat identifie le vrai
        # bassin simulé. Quand un bassin est demandé, le meta du résultat
        # doit corroborer l'identité — sinon le résultat d'un autre
        # bassin serait servi (ex. bassin 1 → sim du bassin 234).
        # Les identités acceptées couvrent les DEUX espaces : cluster_id
        # du dropdown et exutoire_noeud/bassin_ref (espace d'enregistrement
        # des simulations). Le nom du bassin, quand il est connu, doit
        # aussi correspondre : les cluster_id sont réattribués à chaque
        # sectorisation et une ancienne sim peut porter un id recyclé.
        #
        # EXCEPTION identités stables : quand la ligne Simulation porte
        # EXACTEMENT le bassin_ref ou l'exutoire_noeud demandé, la base
        # fait foi — les garde-fous meta (cluster_id positionnel recyclé,
        # nom de bassin) ne s'appliquent qu'aux correspondances faibles.
        # Le même exutoire peut être renommé entre versions du réseau
        # (« Chorfa » vs « Chorfa zone 2 (STEP) ») sans changer d'identité.
        if (cluster_id is not None or exutoire_noeud is not None
                or bassin_ref is not None):
            _match_stable = False
            if (bassin_ref is not None and sim.bassin_ref
                    and str(sim.bassin_ref).strip().lower()
                    == str(bassin_ref).strip().lower()):
                _match_stable = True
            if (exutoire_noeud is not None and sim.exutoire_noeud
                    and str(sim.exutoire_noeud).strip().lower()
                    == str(exutoire_noeud).strip().lower()):
                _match_stable = True
        else:
            _match_stable = False
        if (cluster_id is not None or exutoire_noeud is not None
                or bassin_ref is not None) and not _match_stable:
            _meta = data.get("meta") or {}
            _meta_cid = str(_meta.get("cluster_id") or "").strip().lower()
            _cibles_cid = set()
            for _x in (cluster_id, exutoire_noeud):
                if _x is not None and str(_x).strip():
                    _cibles_cid.add(str(_x).strip().lower())
            if bassin_ref:
                _br = str(bassin_ref).strip().lower()
                _cibles_cid.add(_br.split(":", 1)[-1] if ":" in _br else _br)
            _meta_nom = str(
                _meta.get("cluster_nom") or _meta.get("bassin_nom") or ""
            ).strip().lower()
            _nom_att = str(bassin_nom_attendu or "").strip().lower()
            # meta.cluster_id peut être dans l'un OU l'autre espace
            # d'identifiants : on ne l'exige que pour une requête par
            # cluster_id (espace dropdown). Pour une requête purement
            # exutoire/bassin_ref, l'identité DB exacte fait foi et le
            # nom reste le garde-fou.
            _check_cid = cluster_id is not None
            _identite_ok = (
                (not _check_cid or not _meta_cid or not _cibles_cid
                 or _meta_cid in _cibles_cid)
                and (not _nom_att or not _meta_nom or _meta_nom == _nom_att)
            )
            if not _identite_ok:
                continue
        ctx = ContexteSimulation(
            simulation=sim, project=proj, data=data,
            resolution="bassin" if (
                cluster_id is not None or bassin_ref is not None
                or exutoire_noeud is not None) else "derniere")
        if resoudre_gpkg:
            _joindre_gpkg(db, proj, ctx)
        return ctx

    raise ContexteSimulationIntrouvable(
        "Aucune simulation autorisée pour ce contexte.")


def _joindre_gpkg(db: Session, proj: Any, ctx: ContexteSimulation) -> None:
    """Résout le snapshot GPKG exact de la simulation (étape 3C.0)."""
    from api.services.gpkg_versions import resoudre_gpkg_pour_simulation
    gpkg, meta = resoudre_gpkg_pour_simulation(db, proj, ctx.data)
    ctx.gpkg_path = gpkg
    ctx.meta_version = meta or {}


# ============================================================
# Étape 3C.4 — Intégrité, manifeste, diagnostic et reprise
# ============================================================

def _ref_pour_simulation(simulation: Any):
    """ResultRef depuis la ligne Simulation, ou None si identité incomplète."""
    from api.services.result_store import ResultRef, ResultStoreError
    try:
        return ResultRef.depuis_simulation(simulation)
    except ResultStoreError:
        return None


def diagnostiquer_resultats_store(simulation: Any) -> Dict[str, Any]:
    """
    Diagnostic d'intégrité complet d'une simulation côté ResultStore :
      - `execution` : EXECUTED si la ligne ORM existe (toujours vrai ici) ;
      - `manifeste` : ABSENT / PARTIAL / DEGRADED / VERIFIED (manifeste
        confronté aux artefacts réellement relus, SHA-256 inclus) ;
      - `persistance_complete` : True uniquement si le manifeste est
        VERIFIED — un manifeste présent ne suffit JAMAIS.
    Lève ResultStoreError si l'identité est incomplète.
    """
    from api.services.result_store import (
        ResultRef, ResultStore, ResultStoreError,
    )
    ref = _ref_pour_simulation(simulation)
    if ref is None:
        raise ResultStoreError(
            "Identité incomplète : diagnostic ResultStore impossible.")
    store = ResultStore()
    verification = store.verifier_manifeste(ref)
    return {
        "simulation_id": ref.simulation_id,
        "org_id": ref.org_id,
        "project_id": ref.project_id,
        "execution": "EXECUTED",
        "manifeste": verification.get("etat", "ABSENT"),
        "persistance_complete": verification.get("etat") == "VERIFIED",
        "details": verification.get("details") or {},
        "attendus_manquants": verification.get("attendus_manquants") or [],
    }


def reprise_resultat_simulation(simulation: Any,
                                resultat: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reprise IDEMPOTANTE d'une persistance interrompue, SANS relancer SWMM.

    `resultat` = données disponibles (typiquement relues depuis le cache
    de calcul ou un artefact existant). Pour chaque artefact :
      - absent            → dépôt conditionnel (save_idempotent) ;
      - présent identique → succès idempotent ;
      - présent divergent → anomalie explicite, JAMAIS écrasé ;
      - altéré (SHA-256 ≠ manifeste) → signalé dans le diagnostic, non
        écrasé automatiquement.
    Le manifeste est réécrit en fin d'opération. Retourne le statut
    détaillé ; ne lève pas d'exception métier (erreurs backend → statut).
    """
    from api.services.result_store import (
        ArtifactKind, ResultAlreadyExists, ResultStore, ResultStoreError,
    )

    statut: Dict[str, Any] = {"simulation_id": getattr(simulation, "id", None),
                              "artefacts": {}, "anomalies": [],
                              "persistance_complete": False}
    ref = _ref_pour_simulation(simulation)
    if ref is None:
        statut["erreur"] = "identite_incomplete"
        return statut

    store = ResultStore()
    # Diagnostic préalable : altérations par rapport au manifeste
    try:
        diag = store.verifier_manifeste(ref)
        if diag.get("etat") in ("DEGRADED",):
            for nom, det in (diag.get("details") or {}).items():
                if det.get("present") and not det.get("intègre"):
                    statut["anomalies"].append(
                        f"artefact_altéré:{nom}")
    except Exception as e:
        logger.warning("Diagnostic manifeste impossible avant reprise : %s", e)

    taches = [(ArtifactKind.RESULT_JSON, resultat, "application/json")]
    if isinstance(resultat, dict):
        for cle_src, kind in (("inp_content", ArtifactKind.INP),
                              ("rpt_content", ArtifactKind.RPT)):
            contenu = resultat.get(cle_src)
            if contenu:
                taches.append((kind, contenu, "text/plain; charset=utf-8"))

    for kind, contenu, content_type in taches:
        try:
            _, cree = store.save_idempotent(
                ref, contenu, kind=kind, content_type=content_type)
            statut["artefacts"][kind.value] = "created" if cree else "identical"
        except ResultAlreadyExists as e:
            statut["artefacts"][kind.value] = "error:divergence"
            statut["anomalies"].append(f"divergence:{kind.value}")
            logger.error("Reprise : divergence refusée sur %s : %s", kind.value, e)
        except ResultStoreError as e:
            statut["artefacts"][kind.value] = f"error:{e}"
            statut["anomalies"].append(f"stockage:{kind.value}")
            logger.error("Reprise : dépôt %s impossible : %s", kind.value, e)
        except Exception as e:
            statut["artefacts"][kind.value] = f"error:{e}"
            statut["anomalies"].append(f"stockage:{kind.value}")
            logger.exception("Reprise : erreur inattendue sur %s", kind.value)

    try:
        manifeste = store.ecrire_manifeste(
            ref, etat_execution="EXECUTED",
            artefacts_attendus=[kind for kind, _, _ in taches])
        statut["manifeste"] = manifeste.get("etat")
    except Exception as e:
        statut["manifeste"] = f"erreur:{e}"
        logger.error("Reprise : écriture manifeste impossible : %s", e)

    statut["persistance_complete"] = (
        statut["manifeste"] == "PERSISTED" and not statut["anomalies"])
    return statut
