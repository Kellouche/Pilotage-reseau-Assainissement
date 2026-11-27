"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-27
Objet : Endpoints de lancement de simulation SWMM 5.2 et restitution des résultats
================================================================================
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status, Response
from sqlalchemy.orm import Session
from typing import List, Optional, Any, Dict, Union, Tuple
from pathlib import Path
import logging
import math
import re
import threading
import unicodedata

logger = logging.getLogger(__name__)

from api.database import get_db
from api import schemas, crud
from api.core.security import get_tenant_context, TenantContext, require_role
from api.core.jobs import create_job, update_job
from api.models import Organization, Project

router = APIRouter(prefix="/simulations", tags=["Simulations"])

# ============================================================
# LANCEMENT & STATUT
# ============================================================

@router.get("", response_model=List[schemas.SimulationResponse])
def list_simulations(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Liste les simulations de l'organisation authentifiée (ordre décroissant)."""
    sims = crud.get_simulations(db=db, skip=skip, limit=limit, status=status, org_id=_org_id_requete(tenant))
    return [s.to_dict() for s in sims]

@router.post("", response_model=schemas.SimulationResponse, status_code=status.HTTP_202_ACCEPTED)
def launch_simulation(
    simulation: schemas.SimulationCreate,
    user_id: str = "system",
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Lance une simulation SWMM asynchrone pour un cluster (Phase 2.4).
    Retourne immédiatement avec un job_id pour polling ou WebSocket.

    Identité : l'organisation provient exclusivement du contexte
    d'authentification validé — aucun repli arbitraire.
    `cluster.network_id` est l'identifiant du projet (Network = Project).
    """
    org_id = tenant.org_id

    # Vérifier cluster existe ET appartient à l'organisation authentifiée
    cluster = crud.get_cluster(db, simulation.cluster_id, org_id=org_id)
    if not cluster or getattr(cluster, "org_id", None) != org_id:
        raise HTTPException(status_code=404, detail="Cluster non trouvé")

    # Le projet (alias Network) doit exister et appartenir à la même organisation
    project_id = getattr(cluster, "network_id", None)
    if not project_id:
        raise HTTPException(
            status_code=422,
            detail="Le cluster sélectionné n'est rattaché à aucun projet.",
        )
    project = db.get(Project, project_id)
    if project is None or getattr(project, "org_id", None) != org_id:
        raise HTTPException(status_code=404, detail="Projet introuvable pour ce cluster.")

    scenario_pluie = (simulation.parameters or {}).get("scenario_pluie", "pluie_decennale")
    duree_heures = float((simulation.parameters or {}).get("duree_heures", 24.0))

    # Identifiants explicites transmis au worker pour vérification de cohérence
    parametres_worker = {
        **(simulation.parameters or {}),
        "cluster_id": simulation.cluster_id,
        "project_id": project_id,
        "scenario_pluie": scenario_pluie,
        "duree_heures": duree_heures,
        # LOT P1.4 — champ typé SimulationCreate.dwf_actif : prioritaire
        # sur toute valeur parasite présente dans le dict `parameters`.
        "dwf_actif": simulation.dwf_actif,
    }

    # 1. Créer le Job asynchrone
    job = create_job(
        db=db,
        org_id=org_id,
        job_type="simulation_swmm",
        network_id=project_id,
        payload={
            "cluster_id": simulation.cluster_id,
            "project_id": project_id,
            "parameters": parametres_worker,
            "scenario_pluie": scenario_pluie,
            "duree_heures": duree_heures,
        },
    )

    # 2. Créer l'enregistrement de Simulation
    sim_obj = crud.create_simulation(
        db=db,
        cluster_id=simulation.cluster_id,
        job_id=job.id,
        parameters=simulation.parameters,
        created_by=getattr(getattr(tenant, "actor", None), "id", None) or user_id,
        org_id=org_id,
        project_id=project_id,
        scenario_pluie=scenario_pluie,
        duree_heures=duree_heures,
    )
    parametres_worker["simulation_id"] = sim_obj.id

    # 3. Publier la tâche Celery — JAMAIS d'exécution synchrone de repli
    try:
        from workers.tasks.swmm_tasks import run_swmm_simulation_task
        run_swmm_simulation_task.delay(
            job_id=job.id,
            org_id=org_id,
            network_id=project_id,
            scenario_pluie=scenario_pluie,
            duree_heures=duree_heures,
            parameters=parametres_worker,
        )
    except Exception as exc:
        logger.error(
            "Échec de publication Celery pour job %s (org %s) : %s",
            job.id, org_id, exc,
        )
        update_job(
            db,
            job.id,
            status="failed",
            message="Publication de la tâche asynchrone impossible.",
            error_message=f"Broker Celery indisponible : {exc}",
        )
        sim_obj.status = "failed"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service de calcul asynchrone temporairement indisponible. Réessayez ultérieurement.",
        )

    return sim_obj.to_dict()


# ============================================================
# MOTEUR EPA SWMM 5.2 NATIF & CONFIGURATION (Phase 2bis)
# Placé AVANT /{simulation_id} pour éviter les conflits de routage Starlette
# ============================================================

from pathlib import Path
import json
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from src.domain.moteur_swmm import MoteurSWMM, SCENARIOS_PLUIE

# Étape 3D.5 — `_DERNIERE_SIMULATION` (état global mutable partagé entre
# requêtes/utilisateurs) a été supprimée : toute lecture de résultat passe
# par `resoudre_simulation_courante` (service contextuel, isolation
# org_id/project_id stricte) et la persistance Simulation/GPKG.


class SimulationRunRequest(BaseModel):
    scenario_key: str = "pluie_decennale"
    duree_heures: Optional[float] = None
    pas_routage_sec: int = 5
    cluster_id: Optional[Union[int, str]] = None
    bassin_ref: Optional[str] = None
    pente_moyenne_pct: Optional[float] = 1.0
    buffer_m: Optional[float] = 35.0
    valider_raccordement: Optional[bool] = True
    typologie_sol: Optional[str] = "habitat_mixte"
    imperv_pct: Optional[float] = None
    intensite_max_mmh: Optional[float] = None
    station_id: Optional[str] = "chlef_anrh_siege"
    raccordements_orphelins: Optional[List[Dict[str, Any]]] = None
    force_recalculate: Optional[bool] = False
    # LOT P0.1 — projet explicite (requis si plusieurs projets actifs)
    project_id: Optional[str] = None
    # Paramètres de simulation d'un Bulletin Météorologique Spécial (BMS ONM)
    bms_mode: Optional[bool] = False
    bms_vigilance: Optional[str] = "orange"
    bms_cumul_mm: Optional[float] = 30.0
    bms_heure_debut: Optional[str] = "07:00"
    bms_heure_fin: Optional[str] = "21:00"
    bms_duree_heures: Optional[float] = None
    bms_profil: Optional[str] = "cloche"
    # LOT P1.3 — apports de temps sec (DWF) : injectés par défaut quand le
    # projet en possède d'actifs ; False = désactivation explicite.
    dwf_actif: Optional[bool] = None
    # LOT A3-DWF — simulation flexible : si True, exclut les apports DWF incompatibles
    # au lieu d'interrompre en HTTP 422.
    dwf_compatibles_seulement: Optional[bool] = False
    # Option C (SHP.md §7bis) — altimétrie terrain IDW dans le .inp :
    # opt-in explicite, jamais automatique ; couche optionnelle.
    altimetrie_terrain: Optional[bool] = False
    altimetrie_layer_id: Optional[str] = None
    # État physique du réseau (Colmatage & Vieillissement)
    etat_reseau: Optional[Dict[str, Any]] = None

SimulationRunRequest.model_rebuild()


# Logique métier (cache, persistance, réponse, moteur) extraite dans
# api/services/simulation_service.py — voir SimulationService.
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
from api.services.bassin_reference import resoudre_bassin

class ValidateBufferRequest(BaseModel):
    buffer_m: float = 45.0

ValidateBufferRequest.model_rebuild()

@router.post("/run")
def run_native_swmm_simulation(
    payload: SimulationRunRequest,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Exécute la simulation hydrodynamique EPA SWMM 5.2 native pour le réseau actif.
    Sauvegarde systématiquement les résultats sur disque et en base de données.
    Implémente un cache intelligent : si aucun paramètre de simulation n'a changé
    et que le recalcul n'est pas forcé, restaure instantanément la simulation sauvegardée.

    LOT P0.1 — authentification stricte, organisation et projet résolus
    explicitement dans le périmètre du tenant (jamais de repli global).
    """

    # 1. Résolution du projet et du GeoPackage via le service métier unique
    org_id = _org_id_requete(tenant)
    try:
        contexte = _resoudre_contexte_projet(
            db, org_id,
            project_id=payload.project_id,
            autoriser_demo=_mode_demo_reseau())
    except ProjetAmbigu as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (ContexteProjetIntrouvable, ContexteSimulationIntrouvable):
        raise HTTPException(status_code=404, detail="Réseau hydraulique introuvable pour ce projet.")

    gpkg_path = contexte.gpkg_path
    proj = contexte.project
    project_name = contexte.project_name

    # Règle d'ingénierie hydraulique : la sectorisation préalable est obligatoire avant simulation
    # Étape 3A : `bassin_ref` est la référence métier prioritaire ; `cluster_id`
    # reste accepté en compatibilité legacy (résolution contextuelle du projet).
    cluster_id_effectif = payload.cluster_id
    bassin_ref_persiste = None
    exutoire_persiste = None
    if payload.bassin_ref:
        resolution = resoudre_bassin(
            db=db,
            network_id=proj.id if proj else None,
            ref=payload.bassin_ref,
            gpkg_path=gpkg_path,
        )
        if resolution.statut in ("AMBIGU", "NON_TROUVE"):
            raise HTTPException(
                status_code=422,
                detail=f"Bassin non résolu ({resolution.statut}) : {resolution.detail}"
            )
        if resolution.cluster_id_moteur is not None:
            cluster_id_effectif = resolution.cluster_id_moteur
        bassin_ref_persiste = resolution.bassin_ref or payload.bassin_ref
        exutoire_persiste = resolution.exutoire_noeud
        logger.info(
            "Bassin résolu : ref=%s -> statut=%s source=%s cluster_id=%s",
            payload.bassin_ref, resolution.statut, resolution.source, cluster_id_effectif,
        )
    elif payload.cluster_id is None:
        raise HTTPException(
            status_code=400,
            detail="Règle hydraulique d'ingénierie : La sectorisation préalable en bassins versants d'exutoires est obligatoire avant la simulation SWMM. Veuillez sélectionner un bassin versant à simuler."
        )

    # Garde-fou d'ingénierie hydraulique : un ouvrage isolé sans réseau collecteur ne peut pas être simulé
    identite_bassin = _identite_bassin_du_cache(gpkg_path, cluster_id_effectif)
    if identite_bassin and identite_bassin.get("est_isole"):
        nom_b = identite_bassin.get("nom") or cluster_id_effectif
        raise HTTPException(
            status_code=422,
            detail=f"Le bassin demandé ({nom_b}) est un ouvrage isolé sans réseau collecteur amont. Les simulations dynamiques SWMM 5.2 sont inapplicables."
        )

    # 1bis. LOT P1.3/P1.4 — résolution des apports DWF actifs du projet dans
    #    le périmètre org/projet (proj=None en mode démo → aucun apport),
    #    puis VALIDATION STRICTE contre la version exacte du GPKG résolue
    #    ci-dessus : tout apport non réconcilié → 422 avant cache et moteur.
    #    Leur empreinte entre dans la clé de cache.
    from api.services.apports_dwf_service import (
        ApportsDwfIncompatiblesError,
        preparer_apports_pour_simulation,
    )
    try:
        apports_dwf, info_cache_dwf = preparer_apports_pour_simulation(
            db, proj, dwf_actif=payload.dwf_actif,
            version_meta=contexte.version_meta, gpkg_path=gpkg_path,
            dwf_compatibles_seulement=bool(payload.dwf_compatibles_seulement),
            user_id=getattr(getattr(tenant, "actor", None), "id", None),
            cluster_id=payload.cluster_id)
    except ApportsDwfIncompatiblesError as e:
        raise HTTPException(status_code=422, detail={
            "message": str(e),
            "apports_incompatibles": e.details,
        })

    # 1ter. Option C (SHP.md §7bis) — altimétrie terrain IDW : opt-in
    #    explicite. Résolution des cotes radier AVANT le hash (la couche
    #    entre dans l'empreinte) ; refus 422 explicite si artefact absent,
    #    périmé ou couverture < 95 % — jamais de repli silencieux sur le
    #    datum synthétique quand l'utilisateur a demandé le mode terrain.
    altimetrie_elevations = None
    altimetrie_meta = None
    if payload.altimetrie_terrain:
        if proj is None:
            raise HTTPException(
                status_code=422,
                detail="Mode altimétrie terrain indisponible : aucun projet résolu.")
        from api.services import aux_altimetrie_service as _alt
        _alt_res = _alt.resoudre_elevations_terrain_pour_simulation(
            db, org_id, proj.id, layer_id=payload.altimetrie_layer_id)
        if _alt_res.get("statut") != "ok":
            raise HTTPException(status_code=422, detail={
                "message": f"Altimétrie terrain refusée : {_alt_res.get('raison')}",
                "statut_altimetrie": _alt_res.get("statut"),
            })
        altimetrie_elevations = _alt_res["elevations"]
        altimetrie_meta = _alt_res["meta"]
        logger.info(
            "Altimétrie terrain activée : couche=%s cotes=%s estimées=%s",
            altimetrie_meta.get("layer_nom"), altimetrie_meta.get("nb_cotes"),
            altimetrie_meta.get("nb_profondeurs_estimees"))

    # 2. Empreinte canonique (hash) des paramètres de simulation.
    #    LOT P1.4.1 — le sha256 de la version résolue (déjà calculé à
    #    l'étape 1, frais et vérifié) sert d'identité de contenu pour le
    #    cache : un seul hash par requête, valeur strictement identique.
    _sha_gpkg_connu = (contexte.version_meta or {}).get("sha256")
    param_hash, params_dict = _generer_cle_cache_simulation(
        gpkg_path, payload, extra_params=info_cache_dwf,
        gpkg_sha256=_sha_gpkg_connu)

    # 3. Vérification du cache intelligent (Idempotence & Restauration)
    if not payload.force_recalculate:
        cached_resultat = _charger_cache_simulation(
            gpkg_path, cluster_id_effectif, param_hash,
            gpkg_sha256=_sha_gpkg_connu)
        # 3D.6 — un fichier de cache estampillé pour un AUTRE projet/org
        # n'est jamais servi : traité comme un miss (recalcul propre).
        if cached_resultat and proj is not None:
            from api.services.simulation_service import _resultatdeclare_projet
            if not _resultatdeclare_projet(cached_resultat, proj):
                logger.warning(
                    "Cache simulation ignoré : propriété différente (cluster %s)",
                    cluster_id_effectif)
                cached_resultat = None
        if cached_resultat:
            cached_resultat["source_gpkg"] = str(gpkg_path.resolve())
            cached_resultat["project_name"] = project_name or gpkg_path.stem
            logger.info("Simulation SWMM restaurée depuis la sauvegarde (cluster %s, hash %s)", cluster_id_effectif, param_hash)
            return _construire_reponse_simulation(cached_resultat, cached=True)

    # 3bis. Déduplication métier : le fichier cache peut avoir été purgé
    # alors qu'une simulation 'completed' identique existe en base
    # (result.json / ResultStore). La même empreinte param_hash pour le
    # même cluster effectif = mêmes entrures → restituer le résultat
    # persisté au lieu de recalculer et de créer un doublon d'historique.
    # Le param_hash inclut payload.cluster_id (souvent None) et non le
    # cluster résolu : le match exige donc AUSSI summary_kpis.cluster_id
    # (= cluster_id_effectif) et respecte bassin_ref/exutoire_noeud pour
    # les bassins réattribués après une nouvelle sectorisation.
    if proj is not None and not payload.force_recalculate and cluster_id_effectif is not None:
        try:
            from api.models import Simulation as _SimDedup
            _cands = (db.query(_SimDedup)
                      .filter(_SimDedup.project_id == proj.id,
                              _SimDedup.status == "completed")
                      .order_by(_SimDedup.created_at.desc(), _SimDedup.id.desc())
                      .limit(80).all())
            for _s in _cands:
                _k = _s.summary_kpis or {}
                if _k.get("param_hash") != param_hash:
                    continue
                if str(_k.get("cluster_id")) != str(cluster_id_effectif):
                    continue
                if (bassin_ref_persiste and _s.bassin_ref
                        and str(_s.bassin_ref) != str(bassin_ref_persiste)):
                    continue
                if (exutoire_persiste and _s.exutoire_noeud
                        and str(_s.exutoire_noeud) != str(exutoire_persiste)):
                    continue
                _data = _charger_resultat_simulation(_s)
                if _data and _est_simulation_valide(_data):
                    _data["source_gpkg"] = str(gpkg_path.resolve())
                    _data["project_name"] = project_name or gpkg_path.stem
                    logger.info(
                        "Simulation existante réutilisée (hash %s, sim %s) — aucun recalcul",
                        param_hash, _s.id)
                    try:
                        _ident_nom = (_identite_bassin_du_cache(gpkg_path, str(payload.bassin_ref or payload.cluster_id or cluster_id_effectif)) or {}).get("nom")
                        if _ident_nom and not str(_ident_nom).strip().isdigit():
                            _meta_c = _data.setdefault("meta", {})
                            _cur_c = str(_meta_c.get("bassin_nom") or _meta_c.get("cluster_nom") or "").strip()
                            if not _cur_c or _cur_c.isdigit() or _cur_c == str(exutoire_persiste or "").strip():
                                _meta_c["bassin_nom"] = _ident_nom
                                _meta_c["cluster_nom"] = _ident_nom
                    except Exception:
                        pass
                    return _construire_reponse_simulation(
                        _data, cached=True, simulation_id=_s.id)
        except Exception as _dedup_err:
            logger.warning("Déduplication param_hash impossible : %s", _dedup_err)

    # 4. Exécution via le service métier : scénario BMS + MoteurSWMM (PySWMM) + correction pic
    try:
        params_exec = payload.model_dump()
        params_exec["cluster_id"] = cluster_id_effectif
        params_exec["apports_dwf"] = apports_dwf
        if altimetrie_elevations is not None:
            params_exec["altimetrie_elevations"] = altimetrie_elevations
            params_exec["altimetrie_meta"] = altimetrie_meta
        # Cotes nodales certifiées par l'hydraulicien
        try:
            from api.services.cotes_suspectes_service import obtenir_map_validations_projet
            vmap = obtenir_map_validations_projet(db, proj.id, org_id)
            cotes_validees_dict = {
                nid: ent["profondeur"]["valeur_validee"]
                for nid, ent in vmap.items()
                if "profondeur" in ent and ent["profondeur"].get("statut") == "valide"
                and ent["profondeur"].get("valeur_validee") is not None
            }
            if cotes_validees_dict:
                params_exec["cotes_validations"] = cotes_validees_dict
        except Exception as e_vmap:
            logger.warning("Erreur chargement cotes validées pour simulation: %s", e_vmap)
        resultat = _executer_moteur_swmm(
            gpkg_path, params_exec, execution_mode="sync",
            garde_fou_config=getattr(proj, "garde_fou_config", None))
        resultat["source_gpkg"] = str(gpkg_path.resolve())
        resultat["project_name"] = project_name or gpkg_path.stem
        resultat["param_hash"] = param_hash
        try:
            _ident_nom = (_identite_bassin_du_cache(gpkg_path, str(payload.bassin_ref or payload.cluster_id or cluster_id_effectif)) or {}).get("nom")
            if _ident_nom and not str(_ident_nom).strip().isdigit():
                _meta_res = resultat.setdefault("meta", {})
                _cur_nom_res = str(_meta_res.get("bassin_nom") or _meta_res.get("cluster_nom") or "").strip()
                if not _cur_nom_res or _cur_nom_res.isdigit() or _cur_nom_res == str(exutoire_persiste or "").strip():
                    _meta_res["bassin_nom"] = _ident_nom
                    _meta_res["cluster_nom"] = _ident_nom
        except Exception:
            pass

        # Étape 3B : traçabilité de la version GPKG capturée + cohérence bassin
        vmeta = contexte.version_meta or {}
        if vmeta:
            prov = resultat.setdefault("provenance", {})
            prov["gpkg_version_id"] = vmeta.get("version_id")
            prov["gpkg_sha256"] = vmeta.get("sha256")
            prov["gpkg_storage_kind"] = vmeta.get("storage_kind")
        if info_cache_dwf.get("apports_dwf_ignores"):
            prov = resultat.setdefault("provenance", {})
            prov_dwf = prov.setdefault("apports_dwf", {})
            existing_ignores = prov_dwf.get("ignores", [])
            prov_dwf["ignores"] = existing_ignores + [
                ig for ig in info_cache_dwf["apports_dwf_ignores"]
                if ig.get("id") not in {e.get("id") for e in existing_ignores}
            ]
        if altimetrie_meta is not None:
            prov = resultat.setdefault("provenance", {})
            prov["altimetrie"] = {
                "mode": "terrain_idw",
                **altimetrie_meta,
                # La provenance doit rester visible : ces cotes sont des
                # estimations IDW − profondeur, pas des mesures radier.
                "nature": "estimee_interpolation_idw",
            }
            if exutoire_persiste:
                from api.services.gpkg_versions import exutoire_present_dans_gpkg
                prov["coherence"] = {
                    "exutoire_noeud": exutoire_persiste,
                    "exutoire_present_dans_version": exutoire_present_dans_gpkg(
                        gpkg_path, exutoire_persiste),
                    "bassin_ref": bassin_ref_persiste,
                }

        # 5. Persistance sur disque et en base de données SQLite
        _sauvegarder_simulation(
            db=db,
            gpkg_path=gpkg_path,
            cluster_id=cluster_id_effectif,
            param_hash=param_hash,
            params_dict=params_dict,
            resultat=resultat,
            proj=proj,
            tenant=tenant,
            version_meta=contexte.version_meta,
            bassin_ref=bassin_ref_persiste,
            exutoire_noeud=exutoire_persiste,
        )

        return _construire_reponse_simulation(resultat, cached=False)
    except ValueError as ve:
        logger.warning("Arrêt de la simulation SWMM (altimétrie requise) : %s", ve)
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception("Erreur lors de l'exécution de la simulation SWMM : %s", e)
        raise HTTPException(status_code=500, detail=f"Erreur d'exécution SWMM 5.2 : {str(e)}")

@router.get("/latest")
def get_latest_simulation(
    snapshot: Optional[str] = None,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context)
):
    """
    Retourne les résultats et cartographies thématiques de la dernière simulation exécutée
    pour le réseau actif. Si la mémoire est vide (ex: redémarrage serveur), charge automatiquement
    la dernière simulation sauvegardée sur disque ou en base de données.

    Étape 3D.3/3D.5 — la simulation est résolue par contexte
    organisation/projet via `resoudre_simulation_courante` (DB d'abord).
    La globale `_DERNIERE_SIMULATION` a été supprimée (3D.5).
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

    # Vue archive : `snapshot` = gpkg_version_id ou sha256 d'une version
    # archivée du projet. On sert la dernière simulation DE CE snapshot —
    # jamais la « dernière » globale qui appartient à une autre version
    # réseau (ce serait réintroduire le mélange carte/résultats).
    if snapshot and str(snapshot).strip():
        from api.models import Simulation
        from api.services.gpkg_versions import (
            resoudre_snapshot_pour_lecture, GpkgSimulationError)
        from api.services.simulation_service import (
            ContexteSimulation, charger_resultat_simulation,
            est_simulation_valide)
        from sqlalchemy import or_
        try:
            proj_snap = _resoudre_projet_pour_simulation(db, org_id, None)
        except ProjetAmbigu as _e:
            raise HTTPException(status_code=409, detail=str(_e))
        except ContexteSimulationIntrouvable:
            raise HTTPException(status_code=404, detail="Ressource introuvable")
        try:
            snap_ctx = resoudre_snapshot_pour_lecture(db, proj_snap, snapshot)
        except GpkgSimulationError:
            raise HTTPException(status_code=404, detail="Ressource introuvable")

        q = db.query(Simulation).filter(
            Simulation.project_id == proj_snap.id,
            Simulation.status == "completed",
        )
        if org_id:
            q = q.filter(Simulation.org_id == org_id)
        vid_snap = snap_ctx.get("version_id")
        sha_snap = snap_ctx.get("sha256")
        clauses = []
        if vid_snap:
            clauses.append(Simulation.gpkg_version_id == vid_snap)
        if sha_snap:
            clauses.append(Simulation.gpkg_sha256 == sha_snap)
        if clauses:
            q = q.filter(or_(*clauses))
        sim_snap = q.order_by(
            Simulation.created_at.desc(), Simulation.id.desc()).first()
        if sim_snap is None:
            return {"status": "none",
                    "message": "Aucune simulation enregistrée pour ce snapshot réseau."}
        data_snap = charger_resultat_simulation(sim_snap)
        if not data_snap or not est_simulation_valide(data_snap):
            return {"status": "none",
                    "message": "Résultat de simulation indisponible pour ce snapshot."}
        ctx_snap = ContexteSimulation(
            simulation=sim_snap, project=proj_snap, data=data_snap,
            resolution="snapshot")
        try:
            gpkg_snap, vmeta_snap = resoudre_gpkg_pour_simulation(
                db, proj_snap, data_snap)
        except GpkgSimulationError as e:
            raise HTTPException(status_code=409, detail=str(e))
        ctx_snap.gpkg_path = gpkg_snap
        ctx_snap.meta_version = vmeta_snap
        if gpkg_snap is not None:
            data_snap["source_gpkg"] = str(gpkg_snap.resolve())
            data_snap["project_name"] = (
                proj_snap.name or data_snap.get("project_name")
                or gpkg_snap.stem)
        else:
            data_snap["project_name"] = (
                proj_snap.name or data_snap.get("project_name"))
        _signaler_mismatch_version_gpkg(data_snap, ctx_snap, proj_snap)
        return _construire_reponse_simulation(
            data_snap, cached=True, simulation_id=sim_snap.id)

    ctx = None
    try:
        ctx = resoudre_simulation_courante(db, org_id=org_id, resoudre_gpkg=True)
    except ProjetAmbigu as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContexteSimulationIntrouvable:
        ctx = None
    except GpkgSimulationError as e:
        raise HTTPException(status_code=409, detail=str(e))

    data = ctx.data if ctx else None
    proj = ctx.project if ctx else None
    gpkg_sim = ctx.gpkg_path if ctx else None
    project_name = proj.name if proj else None

    # Repli legacy : simulation sans ligne DB (ancien cache disque), borné
    # au projet résolu de façon non ambiguë.
    if data is None:
        if proj is None:
            try:
                proj = _resoudre_projet_pour_simulation(db, org_id, None)
            except (ContexteSimulationIntrouvable, ProjetAmbigu):
                proj = None
        gpkg_eff = _resoudre_gpkg_effectif_pour_projet(db, proj)
        if gpkg_eff is None:
            gpkg_eff = _gpkg_demo_autorise()
        # 3D.6 — sans projet vérifiable, aucun résultat legacy n'est servi.
        if proj is not None and gpkg_eff and gpkg_eff.exists():
            restored = _charger_derniere_simulation_disque_ou_db(gpkg_eff, db, proj)
            if restored and _est_simulation_valide(restored):
                try:
                    gpkg_rest, _vmeta = resoudre_gpkg_pour_simulation(db, proj, restored)
                except GpkgSimulationError as e:
                    raise HTTPException(status_code=409, detail=str(e))
                data = restored
                gpkg_sim = gpkg_rest if gpkg_rest is not None else gpkg_eff
                if project_name is None and proj is not None:
                    project_name = proj.name

    if data is None:
        return {"status": "none", "message": "Aucune simulation enregistrée pour ce réseau."}

    if gpkg_sim is None:
        gpkg_sim = _resoudre_gpkg_effectif_pour_projet(db, proj)
    if gpkg_sim is None:
        src = data.get("source_gpkg")
        if src and Path(src).exists():
            gpkg_sim = Path(src)
    if gpkg_sim is None:
        gpkg_sim = _gpkg_demo_autorise()

    if gpkg_sim is not None:
        data["source_gpkg"] = str(gpkg_sim.resolve())
        data["project_name"] = project_name or data.get("project_name") or gpkg_sim.stem
    else:
        data["project_name"] = project_name or data.get("project_name")

    _signaler_mismatch_version_gpkg(data, ctx, proj)
    return _construire_reponse_simulation(
        data, cached=True,
        simulation_id=(ctx.simulation.id if ctx is not None and ctx.simulation is not None else None))


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
# ---------------------------------------------------------------------------
# Facade de compatibilité — endpoints et helpers extraits en sous-routeurs
# (règle modularité ≤600 lignes, docs/CONVENTIONS_CODE.md) ; tous les noms
# historiques restent importables depuis `api.routes.simulations`.
# ---------------------------------------------------------------------------
from api.routes.simulations_contexte import (  # noqa: F401
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
from api.routes.simulations_scenarios import (  # noqa: F401
    BMSPreviewRequest,
    get_pluviometrie_referentiel,
    get_pluviometrie_stations,
    get_simulation_ouvrages_proches,
    get_simulation_scenarios,
    get_simulation_typologies_sol,
    preview_bms_scenario,
)
from api.routes.simulations_exports import (  # noqa: F401
    _formater_nom_fichier_export,
    download_latest_inp,
    download_latest_rpt,
    get_simulation_reconciliation,
    telecharger_ordre_mission_bms_pdf,
    telecharger_rapport_diagnostic_pdf,
)
from api.routes.simulations_consultation import (  # noqa: F401
    _injecter_fiabilite_timeseries,
    _result_url_simulation,
    cancel_simulation,
    get_simulation,
    get_simulation_by_job,
    get_simulation_resultat,
    get_simulation_status,
    get_simulation_timeseries,
    list_cluster_simulations,
    rechercher_element_reseau,
)

