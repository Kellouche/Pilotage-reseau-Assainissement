# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Resultats par bassin : simulation, historique, validation buffer, agents, cotes suspectes (extrait de api/routes/simulations.py)
================================================================================
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Any, Dict
import json
import logging

logger = logging.getLogger(__name__)

from pydantic import BaseModel
from api import crud
from api.database import get_db
from api.core.security import get_tenant_context, TenantContext, require_role

router = APIRouter(prefix="/simulations")

from api.services.simulation_service import (
    generer_cle_cache_simulation as _generer_cle_cache_simulation,
    get_cache_simulation_file as _get_cache_simulation_file,
    est_simulation_valide as _est_simulation_valide,
    charger_cache_simulation as _charger_cache_simulation,
    charger_resultat_simulation as _charger_resultat_simulation,
    sauvegarder_simulation as _sauvegarder_simulation,
    charger_derniere_simulation_disque_ou_db as _charger_derniere_simulation_disque_ou_db,
    iter_fichiers_cache_simulation as _iter_fichiers_cache_simulation,
    resoudre_gpkg_effectif_pour_projet as _resoudre_gpkg_effectif_pour_projet,
    construire_reponse_simulation as _construire_reponse_simulation,
    resoudre_contexte_projet as _resoudre_contexte_projet,
    _resoudre_projet_pour_simulation,
    executer_moteur_swmm as _executer_moteur_swmm,
    resoudre_simulation_courante,
    ContexteSimulationIntrouvable,
    ProjetAmbigu,
    ContexteProjetIntrouvable,
)
from api.routes.simulations_contexte import (
    _contexte_simulation_autorise,
    _fichier_cache_appartenant,
    _gpkg_demo_autorise,
    _gpkg_partage_entre_projets,
    _identite_bassin_du_cache,
    _mode_demo_reseau,
    _org_id_requete,
    _projet_pour_export_repli,
    _signaler_mismatch_version_gpkg,
)


class ValidateBufferRequest(BaseModel):
    buffer_m: float = 45.0

ValidateBufferRequest.model_rebuild()

@router.get("/bassin/{cluster_id}")
def get_bassin_simulation(
    cluster_id: str,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context)
):
    """
    Retourne la simulation la plus récente enregistrée pour un bassin versant spécifique.
    Supporte la recherche par cluster_id numérique (ex: 92) ou nom (ex: 25_ouvrages_speciaux_348883).
    """
    from api.services.gpkg_versions import (
        resoudre_gpkg_pour_simulation,
        GpkgSimulationError,
    )
    from api.services.simulation_service import (
        resoudre_simulation_courante,
        _resoudre_projet_pour_simulation,
    )

    org_id = _org_id_requete(tenant)

    # Identité métier stable du bassin demandé : les simulations sont
    # enregistrées sous exutoire_noeud/bassin_ref (ex. « Cite 80 Logts »
    # = cluster 87 mais exutoire 234). Sans ce pont, /bassin/87 ne
    # retrouve jamais sa simulation et des anciennes sims à cluster_id
    # recyclé peuvent être servies à tort.
    identite_bassin = {}
    _cid_txt = str(cluster_id).strip()
    _ref_exutoire = _cid_txt.lower().startswith("exutoire:")
    # « exutoire:<id> » est une référence métier : la clé de recherche
    # dans le cache est le suffixe (exutoire_id ou cluster_id selon
    # l'espace de la référence).
    _cle_recherche = _cid_txt.split(":", 1)[1] if _ref_exutoire else cluster_id
    try:
        proj_identite = _resoudre_projet_pour_simulation(db, org_id, None)
        gpkg_identite = _resoudre_gpkg_effectif_pour_projet(db, proj_identite)
        # _cid_txt conserve le préfixe « exutoire: » : la fonction de cache
        # distingue l'espace exutoire de l'espace positionnel — un suffixe
        # numérique seul (« 12 ») est ambigu entre les deux.
        identite_bassin = _identite_bassin_du_cache(gpkg_identite, _cid_txt)
    except Exception:
        identite_bassin = {}
    exutoire_demande = identite_bassin.get("exutoire_id") or (
        _cle_recherche if _ref_exutoire else None)
    bassin_ref_demande = identite_bassin.get("bassin_ref") or (
        _cid_txt if _ref_exutoire else None)
    nom_demande = identite_bassin.get("nom")

    # 1. Lookup DB-first via le service contextuel : simulation du
    #    projet/tenant correspondant au bassin, plus récente d'abord,
    #    identité = cluster_id/bassin_ref/exutoire_noeud (3D.3).
    ctx = None
    try:
        ctx = resoudre_simulation_courante(
            db, org_id=org_id, cluster_id=cluster_id,
            exutoire_noeud=exutoire_demande, bassin_ref=bassin_ref_demande,
            resoudre_gpkg=True, bassin_nom_attendu=nom_demande)
    except ProjetAmbigu as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContexteSimulationIntrouvable:
        ctx = None
    except GpkgSimulationError as e:
        raise HTTPException(status_code=409, detail=str(e))

    if ctx is not None:
        proj = ctx.project
        project_name = proj.name if proj else None
        data = ctx.data
        gpkg_sim = ctx.gpkg_path
        if gpkg_sim is None:
            gpkg_sim = _resoudre_gpkg_effectif_pour_projet(db, proj)
        if gpkg_sim is None:
            gpkg_sim = _gpkg_demo_autorise()
        if gpkg_sim is not None and gpkg_sim.exists():
            data["source_gpkg"] = str(gpkg_sim.resolve())
            data["project_name"] = project_name or gpkg_sim.stem
            if nom_demande and not str(nom_demande).strip().isdigit():
                _meta = data.setdefault("meta", {})
                _cur_nom = str(_meta.get("bassin_nom") or _meta.get("cluster_nom") or "").strip()
                if not _cur_nom or _cur_nom.isdigit() or _cur_nom == str(exutoire_demande or "").strip():
                    _meta["bassin_nom"] = nom_demande
                    _meta["cluster_nom"] = nom_demande
            _signaler_mismatch_version_gpkg(data, ctx, proj)
            return _construire_reponse_simulation(
                data, cached=True,
                simulation_id=(ctx.simulation.id if ctx.simulation is not None else None))

    # 2. Repli legacy : résolution non ambiguë du projet puis scan disque
    #    sur le GPKG effectif (compatibilité anciennes simulations sans ligne DB).
    proj = None
    project_name = None
    try:
        proj = _resoudre_projet_pour_simulation(db, org_id, None)
    except (ContexteSimulationIntrouvable, ProjetAmbigu):
        proj = None
    if proj is not None:
        project_name = proj.name

    gpkg_effectif = _resoudre_gpkg_effectif_pour_projet(db, proj)
    if gpkg_effectif is None:
        gpkg_effectif = _gpkg_demo_autorise()
        if gpkg_effectif is not None and project_name is None:
            project_name = "demo_reseau"

    # 3. Fallback legacy : scan disque sur le GPKG effectif du projet —
    #    uniquement si le projet est vérifiable (3D.6 : pas de service
    #    d'un résultat sans périmètre d'accès établi).
    if proj is None or gpkg_effectif is None or not gpkg_effectif.exists():
        return {"status": "none", "message": "Aucun réseau actif."}

    gpkg_path = gpkg_effectif

    # Fichiers de cache candidats : content-adressés (SHA-256) + legacy stem
    all_files = list(_iter_fichiers_cache_simulation(gpkg_path))
    if all_files:
        clean_cid = str(cluster_id).strip().lower()

        # Identités acceptées : cluster_id demandé + exutoire/bassin_ref/nom
        # résolus depuis le cache de sectorisation — les simulations sont
        # enregistrées dans l'espace exutoire, pas dans celui du dropdown.
        _cibles_ids = {clean_cid}
        if exutoire_demande:
            _cibles_ids.add(str(exutoire_demande).strip().lower())
        if bassin_ref_demande:
            _br = str(bassin_ref_demande).strip().lower()
            _cibles_ids.add(_br.split(":", 1)[-1] if ":" in _br else _br)
        _cibles_noms = set()
        if nom_demande:
            _cibles_noms.add(str(nom_demande).strip().lower())

        # Filtrage ultra-rapide par nom de fichier (évite la lecture inutile de gros fichiers JSON sur disque)
        matching_files = [
            f for f in all_files
            if any(f"_{cid}_" in f.name.lower() for cid in _cibles_ids if cid)
        ]

        # Si aucune correspondance directe sur le nom de fichier, tenter une correspondance par préfixe
        if not matching_files and clean_cid.isdigit():
            matching_files = [
                f for f in all_files
                if any(f"_{cid}_" in f.name.lower() for cid in _cibles_ids if cid and cid.isdigit())
            ]

        # Recherche de secours par inspection des métadonnées JSON internes (nom ou ID du bassin)
        if not matching_files:
            recent_files = all_files[:35]
            for candidate in recent_files:
                try:
                    with open(candidate, "r", encoding="utf-8") as cf:
                        cd = json.load(cf)
                    cm = cd.get("meta") or {}
                    c_nom = str(cm.get("cluster_nom") or "").strip().lower()
                    c_id = str(cm.get("cluster_id") or "").strip().lower()
                    # Correspondance stricte : jamais de sous-chaîne —
                    # « 1 » ne doit pas matcher « 234 » ou « 10 ».
                    if (clean_cid == c_nom or c_id in _cibles_ids
                            or c_nom in _cibles_noms):
                        matching_files.append(candidate)
                        break
                except Exception:
                    continue

        matching_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        for fpath in matching_files:
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Garde anti-legacy : le nom de fichier peut contenir
                # l'id en sous-chaîne ; meta.cluster_id du résultat
                # doit corroborer le bassin demandé (cluster_id OU
                # exutoire résolu) et, si connu, le nom du bassin.
                _cm = (data.get("meta") or {})
                _meta_cid = str(_cm.get("cluster_id") or "").strip().lower()
                _meta_nom = str(
                    _cm.get("cluster_nom") or _cm.get("bassin_nom") or ""
                ).strip().lower()
                _ok_id = (not _meta_cid) or (_meta_cid in _cibles_ids)
                _ok_nom = (not _cibles_noms) or (not _meta_nom) \
                    or (_meta_nom in _cibles_noms)
                if not (_ok_id and _ok_nom):
                    continue
                # 3D.6 — propriété déclarée vérifiée avant tout service
                from api.services.simulation_service import _resultatdeclare_projet
                if data and _est_simulation_valide(data) \
                        and _resultatdeclare_projet(data, proj):
                    # Même règle 3C.0 : le GPKG affiché = celui de la simulation
                    try:
                        gpkg_sim, _vmeta = resoudre_gpkg_pour_simulation(db, proj, data)
                    except GpkgSimulationError as e:
                        raise HTTPException(status_code=409, detail=str(e))
                    gpkg_aff = gpkg_sim if (gpkg_sim and gpkg_sim.exists()) else gpkg_path
                    data["source_gpkg"] = str(gpkg_aff.resolve())
                    data["project_name"] = project_name or gpkg_aff.stem
                    return _construire_reponse_simulation(data, cached=True)
            except HTTPException:
                raise
            except Exception:
                continue

    return {"status": "none", "message": f"Aucune simulation enregistrée pour le bassin {cluster_id}."}


@router.get("/bassin/{cluster_id}/historique")
def list_bassin_simulations_historique(
    cluster_id: str,
    limit: int = 50,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Liste les simulations enregistrées pour un bassin versant donné
    (historique complet, plus récentes d'abord). Utilisé par la modale
    de gestion des simulations du bassin (exécuter / modifier / supprimer).
    """
    from api.services.simulation_service import _resoudre_projet_pour_simulation

    org_id = _org_id_requete(tenant)

    # Identité métier du bassin : mêmes règles que /bassin/{cluster_id}
    identite_bassin = {}
    _cid_txt = str(cluster_id).strip()
    is_global = _cid_txt.lower() in ("", "tous", "all", "global", "none")
    _ref_exutoire = _cid_txt.lower().startswith("exutoire:")
    _cle_recherche = _cid_txt.split(":", 1)[1] if _ref_exutoire else cluster_id
    proj = None
    try:
        proj = _resoudre_projet_pour_simulation(db, org_id, None)
        if not is_global:
            gpkg_identite = _resoudre_gpkg_effectif_pour_projet(db, proj)
            identite_bassin = _identite_bassin_du_cache(gpkg_identite, _cid_txt)
    except Exception as _e_ident_hist:
        logger.warning("[historique] Identité bassin non résolue pour cluster_id=%s : %s", cluster_id, _e_ident_hist)
        identite_bassin = {}
        proj = None

    # Sans projet résolu, on ne peut pas borner la requête : renvoyer les
    # simulations de TOUTE l'organisation avec des cibles purement
    # positionnelles pourrait exposer le mauvais bassin/projet.
    # Historique vide honnête plutôt que données non fiables.
    if proj is None:
        return {
            "status": "success",
            "cluster_id": cluster_id,
            "nb_simulations": 0,
            "simulations": [],
        }

    exutoire_demande = identite_bassin.get("exutoire_id") or (
        _cle_recherche if _ref_exutoire else None)
    bassin_ref_demande = identite_bassin.get("bassin_ref") or (
        _cid_txt if _ref_exutoire else None)
    nom_demande = identite_bassin.get("nom")

    # Cibles de correspondance d'identifiants
    _cibles_ids = {str(_cid_txt).strip().lower()}
    if _cle_recherche:
        _cibles_ids.add(str(_cle_recherche).strip().lower())
    if exutoire_demande:
        _cibles_ids.add(str(exutoire_demande).strip().lower())
    if bassin_ref_demande:
        _br = str(bassin_ref_demande).strip().lower()
        _cibles_ids.add(_br)
        if ":" in _br:
            _cibles_ids.add(_br.split(":", 1)[1])
    if identite_bassin.get("cluster_id"):
        _cibles_ids.add(str(identite_bassin["cluster_id"]).strip().lower())

    sims = crud.get_simulations(
        db=db, skip=0, limit=500, org_id=org_id,
        project_id=proj.id)

    resultats = []
    for s in sims:
        # Isolation stricte au réseau courant :
        if s.project_id and str(s.project_id) != str(proj.id):
            continue
        if not s.project_id and proj.name:
            nom_proj_norm = proj.name.strip().lower()
            if s.name and not s.name.lower().startswith(f"swmm_{nom_proj_norm}_"):
                continue

        if is_global:
            resultats.append(s.to_dict())
            if len(resultats) >= limit:
                break
            continue

        sk = s.summary_kpis or {}
        params = sk.get("parameters") or {}
        cid_sim = str(sk.get("cluster_id") or "").strip().lower()
        cid_params = (str(params.get("cluster_id") or "").strip().lower()
                      if isinstance(params, dict) else "")
        exo_sim = str(s.exutoire_noeud or "").strip().lower()
        bref_sim = str(s.bassin_ref or "").strip().lower()
        bref_clean = bref_sim.split(":", 1)[1] if ":" in bref_sim else bref_sim

        # Correspondance exacte par identifiant (cluster_id, exutoire_noeud, bassin_ref)
        ok = False
        if cid_sim and cid_sim in _cibles_ids:
            ok = True
        elif cid_params and cid_params in _cibles_ids:
            ok = True
        elif exo_sim and exo_sim in _cibles_ids:
            ok = True
        elif bref_sim and bref_sim in _cibles_ids:
            ok = True
        elif bref_clean and bref_clean in _cibles_ids:
            ok = True
        elif s.name and any(f"_{cid}_" in s.name.lower() or s.name.lower().endswith(f"_{cid}") for cid in _cibles_ids if cid):
            ok = True
        elif nom_demande and not s.exutoire_noeud and not s.bassin_ref:
            if nom_demande.lower() in (s.name or "").lower():
                ok = True

        if ok:
            resultats.append(s.to_dict())
            if len(resultats) >= limit:
                break

    return {
        "status": "success",
        "cluster_id": cluster_id,
        "nb_simulations": len(resultats),
        "simulations": resultats,
    }


@router.post("/validate-buffer")
def validate_simulation_buffer(
    payload: ValidateBufferRequest,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context)
):
    """
    Valide et enregistre le choix du buffer Voronoï (ex. 35m, 45m ou 60m)
    retenu par l'utilisateur suite à l'analyse de sensibilité.

    Étape 3D.4 — le buffer est appliqué à la simulation AUTORISÉE du
    contexte (org/projet) et persisté dans son résultat ; la globale
    `_DERNIERE_SIMULATION` n'est plus mutée ni lue ici.
    """
    from api.services.simulation_service import (
        resoudre_simulation_courante,
        persister_resultat_simulation,
        ContexteSimulationIntrouvable,
        ProjetAmbigu,
    )

    org_id = _org_id_requete(tenant)
    try:
        ctx = resoudre_simulation_courante(db, org_id=org_id, resoudre_gpkg=False)
    except (ContexteSimulationIntrouvable, ProjetAmbigu):
        ctx = None

    if ctx is not None and ctx.data:
        data = ctx.data
        if data.get("buffer_sensitivity"):
            data["buffer_sensitivity"]["active_buffer_m"] = payload.buffer_m
        if data.get("meta"):
            data["meta"]["buffer_m"] = payload.buffer_m
        persister_resultat_simulation(ctx.simulation, data)

    return {
        "status": "success",
        "validated_buffer_m": payload.buffer_m,
        "message": f"Buffer Voronoï {payload.buffer_m}m validé avec succès comme référence du projet."
    }


@router.get("/agents/interpretation")
def get_agents_interpretation(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Retourne le diagnostic causal complet et les prescriptions de l'équipe
    multi-agents d'expertise pour la simulation autorisée du contexte courant.
    """
    _org_id_requete(tenant)
    # 3D.2 — plus de lecture de la globale : simulation résolue par contexte
    ctx = _contexte_simulation_autorise(db, tenant)
    sim_data = ctx.data if ctx else None
    if not sim_data or "agents_expertise" not in sim_data:
        raise HTTPException(
            status_code=404,
            detail="Aucune simulation active disponible pour l'équipe multi-agents. Veuillez lancer une simulation."
        )
    return {
        "status": "success",
        "agents_expertise": sim_data.get("agents_expertise", {}),
        "buffer_sensitivity": sim_data.get("buffer_sensitivity", {}),
        "meta": sim_data.get("meta", {}),
        "kpis": {
            "routing_continuity_error_pct": sim_data.get("routing_continuity_error_pct"),
            "peak_outflow_m3s": sim_data.get("peak_outflow_m3s"),
            "total_outflow_m3": sim_data.get("total_outflow_m3"),
            "flooded_nodes_count": sim_data.get("flooded_nodes_count", 0),
            "surcharged_nodes_count": sim_data.get("surcharged_nodes_count", 0),
        }
    }

# ============================================================
# PROFIL EN LONG HYDRAULIQUE (Phase 6.A)
# ============================================================
# Déplacé dans api/routes/simulations_profil.py (endpoint
# /profil-en-long) et api/services/profil_topo_service.py
# (cache topo GPKG mutualisé avec /recherche-element) —
# découpage module ≤ 600 lignes (docs/CONVENTIONS_CODE.md).


class CoteValidationItem(BaseModel):
    node_id: str
    champ: str = "profondeur"
    action: str = "valider"  # "valider" | "conserve_brut"
    valeur_validee: Optional[float] = None
    commentaire: Optional[str] = None


class CotesValidationPayload(BaseModel):
    validations: List[CoteValidationItem]


@router.get("/cotes-suspectes")
def lister_cotes_suspectes_endpoint(
    statut: Optional[str] = None,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Retourne la liste des cotes nodales suspectes du projet (ex: prof > 15m),
    consignées dans le registre pour validation Human-in-the-Loop.
    """
    org_id = _org_id_requete(tenant)
    try:
        proj = _resoudre_projet_pour_simulation(db, org_id, None)
    except (ProjetAmbigu, ContexteSimulationIntrouvable) as e:
        raise HTTPException(status_code=404, detail=str(e))

    from api.services.cotes_suspectes_service import lister_cotes_suspectes_projet
    suspectes = lister_cotes_suspectes_projet(db, proj, statut=statut)
    return {
        "status": "success",
        "project_id": proj.id,
        "total": len(suspectes),
        "items": [s.to_dict() for s in suspectes],
    }


@router.post("/cotes-suspectes/valider")
def valider_cotes_suspectes_endpoint(
    payload: CotesValidationPayload,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_role("engineer")),
):
    """
    Valide, corrige ou confirme les cotes suspectes du projet.
    Permet à l'hydraulicien de certifier les données avant élaboration du profil ou simulation.
    """
    org_id = _org_id_requete(tenant)
    try:
        proj = _resoudre_projet_pour_simulation(db, org_id, None)
    except (ProjetAmbigu, ContexteSimulationIntrouvable) as e:
        raise HTTPException(status_code=404, detail=str(e))

    from api.services.cotes_suspectes_service import valider_cotes_suspectes_service
    items = [item.model_dump() for item in payload.validations]
    user_id = getattr(tenant, "user_id", None)
    modifies = valider_cotes_suspectes_service(db, proj, items, user_id=user_id)
    return {
        "status": "success",
        "message": f"{len(modifies)} cote(s) validée(s) avec succès.",
        "items": [m.to_dict() for m in modifies],
    }
