"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Endpoints de lancement de simulation SWMM 5.2 et restitution des résultats
================================================================================
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status, Response
from sqlalchemy.orm import Session
from typing import List, Optional, Any, Dict, Union, Tuple
from pathlib import Path
import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

from api.database import get_db
from api import schemas, crud
from api.core.security import get_tenant_context, TenantContext
from api.core.jobs import create_job, update_job
from api.models import Organization, Project

router = APIRouter(prefix="/simulations", tags=["Simulations"])


def _org_id_requete(tenant) -> str:
    """
    LOT P0.1 — organisation obligatoire pour toute route sensible de
    simulation. `tenant` est résolu par `get_tenant_context` (401 HTTP
    avant d'atteindre la route) ; ce garde-fou couvre aussi les appels
    internes directs sans contexte authentifié.
    """
    org_id = getattr(tenant, "org_id", None)
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise.")
    return org_id


def _mode_demo_reseau() -> bool:
    """
    LOT P0.1 — mode démo explicitement activé via DRAINPILOT_MODE_DEMO_RESEAU.
    Désactivé par défaut : le repli data/demo_reseau.gpkg n'est JAMAIS
    un contournement de l'authentification ni une substitution inter-projets.
    """
    try:
        from config.settings import MODE_DEMO_RESEAU
        return bool(MODE_DEMO_RESEAU)
    except Exception:
        return False


def _gpkg_demo_autorise() -> Optional[Path]:
    """GPKG de démonstration si et seulement si le mode démo est activé."""
    if _mode_demo_reseau():
        cand = Path("data/demo_reseau.gpkg")
        if cand.exists():
            return cand
    return None


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
        created_by=tenant.user.id if tenant.user else user_id,
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

SimulationRunRequest.model_rebuild()


# Logique métier (cache, persistance, réponse, moteur) extraite dans
# api/services/simulation_service.py — voir SimulationService.
from api.services.simulation_service import (
    generer_cle_cache_simulation as _generer_cle_cache_simulation,
    get_cache_simulation_file as _get_cache_simulation_file,
    est_simulation_valide as _est_simulation_valide,
    charger_cache_simulation as _charger_cache_simulation,
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


def _contexte_simulation_autorise(db: Session, tenant, cluster_id=None,
                                  simulation_id=None, project_id=None):
    """
    Étape 3D.2 — résout la simulation AUTORISÉE pour le tenant courant via
    le service contextuel (org_id/project_id stricts, jamais la globale
    _DERNIERE_SIMULATION). Retourne un ContexteSimulation ou None si aucune
    simulation n'est autorisée pour ce périmètre.
    """
    if db is None:
        return None
    org_id = tenant.org_id if (tenant and hasattr(tenant, "org_id") and tenant.org_id) else None
    try:
        return resoudre_simulation_courante(
            db,
            org_id=org_id,
            project_id=project_id,
            simulation_id=simulation_id,
            cluster_id=cluster_id,
            resoudre_gpkg=False,
        )
    except (ContexteSimulationIntrouvable, ProjetAmbigu) as e:
        logger.info("Aucune simulation autorisée pour ce contexte : %s", e)
        return None


def _projet_pour_export_repli(db: Session, tenant, project_id: Optional[str] = None):
    """
    Correctif 3C/R2 — résolution stricte du projet pour les replis disque
    des téléchargements INP/RPT : jamais de `.first()` ; plusieurs projets
    possibles → 409 explicite ; `project_id` explicite invalide ou hors
    organisation → 404 ; aucun projet → None (repli démo uniquement).
    """
    from api.services.simulation_service import _resoudre_projet_pour_simulation
    org_id = tenant.org_id if (tenant and hasattr(tenant, "org_id") and tenant.org_id) else None
    try:
        return _resoudre_projet_pour_simulation(db, org_id, project_id)
    except ProjetAmbigu as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContexteSimulationIntrouvable:
        if project_id:
            raise HTTPException(
                status_code=404, detail="Projet introuvable ou non autorisé.")
        return None


def _gpkg_partage_entre_projets(db: Session, gpkg_path: Path, proj) -> bool:
    """
    Correctif 3C/R1 — True si un AUTRE projet actif peut résoudre le même
    contenu GPKG (snapshot matérialisé identique ou SHA-256 identique).
    Dans ce cas, un fichier `.simulation_cache` non estampillé a un
    propriétaire ambigu et ne doit pas être servi.
    """
    from api.models import Project
    from api.services.gpkg_versions import GPKG_CACHE_DIR, sha256_fichier

    def _sha_effectif(p: Path) -> Optional[str]:
        try:
            if p.parent == Path(GPKG_CACHE_DIR):
                return p.stem  # snapshot matérialisé : nom de fichier = sha256
            return sha256_fichier(p)
        except Exception:
            return None

    sha_cible = _sha_effectif(gpkg_path)
    if not sha_cible:
        return True  # unicité invérifiable → prudence
    for autre in db.query(Project).filter(
            Project.is_archived.is_(False), Project.id != proj.id).all():
        try:
            p2 = _resoudre_gpkg_effectif_pour_projet(db, autre)
        except Exception:
            continue
        if p2 is None:
            continue
        if _sha_effectif(p2) == sha_cible:
            return True
    return False


def _fichier_cache_appartenant(db: Session, proj, gpkg_path: Path,
                               data: Dict[str, Any]) -> bool:
    """
    Correctif 3C/R1 — propriété d'un fichier `.simulation_cache` avant tout
    service dans les téléchargements :
      - `proj` résolu : estampille project_id/org_id contradictoire → refus ;
        estampille conforme → accepté ; non estampillé (legacy) → accepté
        seulement si le GPKG n'est pas partagé avec un autre projet ;
      - `proj` absent (mode démo sans projet) : seuls les fichiers SANS
        estampille sont admissibles — une estampille vers un projet ne
        peut pas être vérifiée → refus par prudence.
    Le nom de fichier et `cluster_id` ne sont JAMAIS une preuve de propriété.
    """
    from api.services.simulation_service import _resultatdeclare_projet
    if not isinstance(data, dict):
        return False
    meta = data.get("meta") or {}
    estampille = bool(
        meta.get("project_id") or meta.get("org_id")
        or data.get("project_id") or data.get("org_id"))
    if proj is None:
        return not estampille
    if not _resultatdeclare_projet(data, proj):
        return False
    if estampille:
        return True
    return not _gpkg_partage_entre_projets(db, gpkg_path, proj)



class ValidateBufferRequest(BaseModel):
    buffer_m: float = 45.0

ValidateBufferRequest.model_rebuild()


@router.get("/typologies-sol")
def get_simulation_typologies_sol():
    """Retourne la liste des typologies d'occupation du sol et leurs paramètres d'imperméabilisation."""
    from src.domain.moteur_swmm import TYPOLOGIES_OCCUPATION_SOL
    return {
        "typologies": [
            {
                "key": k,
                "nom": v["nom"],
                "description": v["description"],
                "imperv_pct": v["imperv_pct"],
                "c_ruissellement_ref": v["c_ruissellement_ref"]
            }
            for k, v in TYPOLOGIES_OCCUPATION_SOL.items()
        ],
        "default": "habitat_mixte"
    }


@router.get("/pluviometrie/referentiel")
def get_pluviometrie_referentiel():
    """Retourne le référentiel pluviométrique complet certifié (Wilayas, Stations, Métadonnées)."""
    from src.domain.referentiel_pluvio import charger_referentiel, lister_wilayas, lister_stations
    ref = charger_referentiel()
    return {
        "metadata": ref.get("metadata", {}),
        "wilaya_active_recommandee": ref.get("wilaya_active_recommandee", "Chlef"),
        "wilayas": lister_wilayas(),
        "stations_chlef": lister_stations("Chlef"),
        "total_stations": len(lister_stations()),
    }


@router.get("/pluviometrie/stations")
def get_pluviometrie_stations(wilaya: Optional[str] = None):
    """Retourne la liste des stations hydro-météorologiques (optionnellement filtrée par wilaya)."""
    from src.domain.referentiel_pluvio import lister_stations
    return {"stations": lister_stations(wilaya_key=wilaya)}


@router.get("/scenarios")
def get_simulation_scenarios(station_id: Optional[str] = "chlef_anrh_siege"):
    """Retourne les scénarios de pluie et de sollicitation disponibles pour une station donnée."""
    from src.domain.referentiel_pluvio import generer_scenarios_swmm_pour_station, obtenir_station
    st_id = station_id or "chlef_anrh_siege"
    scenarios_dict = generer_scenarios_swmm_pour_station(st_id)
    if not scenarios_dict:
        scenarios_dict = SCENARIOS_PLUIE

    st_info = obtenir_station(st_id) or {}
    default_i_max = scenarios_dict.get("pluie_decennale", {}).get("intensite_max_defaut", 74.9)

    return {
        "station": st_info,
        "station_id": st_id,
        "scenarios": [
            {
                "key": k,
                "nom": v["nom"],
                "station": v.get("station", "Station Hydro-Météo"),
                "station_id": v.get("station_id", st_id),
                "code_anrh": v.get("code_anrh", ""),
                "wilaya": v.get("wilaya", "Wilaya de Chlef"),
                "periode_retour": v.get("periode_retour", "T = 10 ans"),
                "intensite_max_defaut": v.get("intensite_max_defaut", default_i_max),
                "duree_heures": v["duree_heures"],
                "formule_montana": v.get("formule_montana", ""),
                "hauteur_p24_mm": v.get("hauteur_p24_mm", 0.0),
                "hauteur_totale_mm": v.get("hauteur_totale_mm", 0.0),
                "source": v.get("source", ""),
                "description": v["description"]
            }
            for k, v in scenarios_dict.items()
        ],
        "default_scenario": "pluie_decennale",
        "default_intensite_max": default_i_max,
        "solver": "EPA SWMM 5.2 Dynamic Wave (DYNWAVE)",
        "infiltration_method": "Horton (f0=75 mm/h, fc=10 mm/h, k=4.0 1/h)",
    }


class BMSPreviewRequest(BaseModel):
    cumul_pluie_mm: float = 30.0
    duree_heures: Optional[float] = None
    heure_debut: str = "07:00"
    heure_fin: str = "21:00"
    niveau_vigilance: str = "orange"
    type_profil: str = "cloche"
    wilaya: str = "Chlef"
    station_id: str = "chlef_anrh_siege"


@router.post("/pluviometrie/bms-preview")
def preview_bms_scenario(payload: BMSPreviewRequest):
    """Génère l'hyétogramme prévisionnel et les indicateurs clés d'un BMS pour aperçu instantané."""
    from src.domain.bms_module import creer_scenario_bms
    scen = creer_scenario_bms(
        cumul_pluie_mm=payload.cumul_pluie_mm,
        duree_heures=payload.duree_heures,
        heure_debut=payload.heure_debut,
        heure_fin=payload.heure_fin,
        niveau_vigilance=payload.niveau_vigilance,
        type_profil=payload.type_profil,
        wilaya=payload.wilaya,
        station_id=payload.station_id,
    )
    return scen


@router.get("/ouvrages-proches")
def get_simulation_ouvrages_proches(
    cluster_id: str,
    rayon_m: float = 45.0,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Retourne les ouvrages spéciaux orphelins (déversoirs d'orage, trop-pleins, stations de relevage)
    détectés à proximité (< rayon_m) du bassin sélectionné pour validation interactive avant simulation.
    """
    from src.domain.ouvrages_orphelins import detecter_ouvrages_orphelins_proches
    from api.models import Project
    from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet

    org_id = _org_id_requete(tenant)
    gpkg_path = None
    try:
        proj = _resoudre_projet_pour_simulation(db, org_id, None)
    except ProjetAmbigu as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContexteSimulationIntrouvable:
        proj = None
    if proj is not None:
        gpkg_path = resoudre_gpkg_effectif_pour_projet(db, proj)
    if gpkg_path is None:
        gpkg_path = _gpkg_demo_autorise()

    if not gpkg_path or not gpkg_path.exists():
        raise HTTPException(status_code=404, detail="Réseau hydraulique introuvable pour ce projet.")

    return detecter_ouvrages_orphelins_proches(str(gpkg_path), cluster_id, rayon_max_m=rayon_m)


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
            version_meta=contexte.version_meta, gpkg_path=gpkg_path)
    except ApportsDwfIncompatiblesError as e:
        raise HTTPException(status_code=422, detail={
            "message": str(e),
            "apports_incompatibles": e.details,
        })

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

    # 4. Exécution via le service métier : scénario BMS + MoteurSWMM (PySWMM) + correction pic
    try:
        params_exec = payload.model_dump()
        params_exec["cluster_id"] = cluster_id_effectif
        params_exec["apports_dwf"] = apports_dwf
        resultat = _executer_moteur_swmm(gpkg_path, params_exec, execution_mode="sync")
        resultat["source_gpkg"] = str(gpkg_path.resolve())
        resultat["project_name"] = project_name or gpkg_path.stem
        resultat["param_hash"] = param_hash

        # Étape 3B : traçabilité de la version GPKG capturée + cohérence bassin
        vmeta = contexte.version_meta or {}
        if vmeta:
            prov = resultat.setdefault("provenance", {})
            prov["gpkg_version_id"] = vmeta.get("version_id")
            prov["gpkg_sha256"] = vmeta.get("sha256")
            prov["gpkg_storage_kind"] = vmeta.get("storage_kind")
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

    return _construire_reponse_simulation(data, cached=True)


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

    # 1. Lookup DB-first via le service contextuel : simulation du
    #    projet/tenant correspondant au bassin, plus récente d'abord,
    #    identité = cluster_id/bassin_ref/exutoire_noeud (3D.3).
    ctx = None
    try:
        ctx = resoudre_simulation_courante(
            db, org_id=org_id, cluster_id=cluster_id, resoudre_gpkg=True)
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
            return _construire_reponse_simulation(data, cached=True)

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

        # Filtrage ultra-rapide par nom de fichier (évite la lecture inutile de gros fichiers JSON sur disque)
        matching_files = [
            f for f in all_files
            if f"_cluster_{clean_cid}_" in f.name.lower() or f"_{clean_cid}_" in f.name.lower()
        ]

        # Si aucune correspondance directe sur le nom de fichier, tenter une correspondance par préfixe
        if not matching_files and clean_cid.isdigit():
            matching_files = [
                f for f in all_files
                if f"_cluster_{clean_cid}_" in f.name.lower() or f"_{clean_cid}_ouvrages_" in f.name.lower() or f"_{clean_cid}_rejets_" in f.name.lower()
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
                    if clean_cid in (c_nom, c_id) or (c_nom and clean_cid in c_nom) or (c_id and clean_cid == c_id):
                        matching_files.append(candidate)
                        break
                except Exception:
                    continue

        matching_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        for fpath in matching_files:
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
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



def _formater_nom_fichier_export(nom_reseau: Optional[str], nom_bassin: Optional[str] = None, ext: str = "inp") -> str:
    """Génère un nom de fichier normalisé et compatible pour EPA SWMM 5.2."""
    if nom_bassin:
        base = str(nom_bassin).strip()
    elif nom_reseau:
        base = re.sub(r'\.(gpkg|inp)$', '', str(nom_reseau).strip(), flags=re.I)
    else:
        base = "modele_swmm"

    sans_accent = unicodedata.normalize('NFKD', base).encode('ASCII', 'ignore').decode('utf-8')
    clean = re.sub(r'[^\w\-_.]+', '_', sans_accent)
    clean = re.sub(r'_+', '_', clean).strip('_')
    if not clean:
        clean = "modele_swmm"
    return f"{clean}.{ext.lstrip('.')}"


@router.get("/download/inp")
def download_latest_inp(
    cluster_id: Optional[str] = None,
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context)
):
    """Télécharge le fichier d'entrée (.inp) généré pour le bassin ou la dernière simulation."""

    _org_id_requete(tenant)
    content = None
    bassin_nom = None
    nom_reseau = None

    # 3D.2 — priorité : INP de la simulation AUTORISÉE du contexte courant
    # (org_id/project_id vérifiés), jamais la globale partagée.
    ctx = _contexte_simulation_autorise(
        db, tenant, cluster_id=cluster_id, project_id=project_id)
    if ctx and ctx.data:
        content = ctx.data.get("inp_content")
        if content:
            meta = ctx.data.get("meta") or {}
            bassin_nom = meta.get("bassin_nom") or meta.get("cluster_nom")
            nom_reseau = (ctx.project.name if ctx.project else None) \
                or ctx.data.get("project_name")

    # 3C.5/R2 — résolution stricte du projet (jamais de .first()).
    proj = _projet_pour_export_repli(db, tenant, project_id=project_id)
    active_gpkg = None
    if proj is not None:
        active_gpkg = _resoudre_gpkg_effectif_pour_projet(db, proj)
        nom_reseau = proj.name
    if active_gpkg is None and proj is None:
        active_gpkg = _gpkg_demo_autorise()
        if active_gpkg is not None:
            nom_reseau = "demo_reseau"

    # 2. Si cluster_id demandé sans simulation autorisée correspondante,
    # chercher dans le cache content-adressé du GPKG effectif du projet —
    # 3C.5/R1 : propriété vérifiée pour chaque fichier avant service.
    if not content and cluster_id and active_gpkg:
        clean_cid = str(cluster_id).strip().lower()
        for cand in _iter_fichiers_cache_simulation(active_gpkg):
            if f"_{clean_cid}_" in cand.name.lower() or f"_cluster_{clean_cid}_" in cand.name.lower():
                try:
                    with open(cand, "r", encoding="utf-8") as cf:
                        cd = json.load(cf)
                    if _est_simulation_valide(cd) and cd.get("inp_content") \
                            and _fichier_cache_appartenant(db, proj, active_gpkg, cd):
                        content = cd["inp_content"]
                        bassin_nom = cd.get("meta", {}).get("bassin_nom") or cd.get("meta", {}).get("cluster_nom") or cluster_id
                        break
                except Exception:
                    continue

    # 3. Si toujours pas de contenu et cluster_id demandé : assembler le modèle INP à la volée !
    if not content and cluster_id and active_gpkg and active_gpkg.exists():
        try:
            from src.domain.moteur_swmm import MoteurSWMM
            moteur = MoteurSWMM()
            content, meta = moteur.assembler_modele_inp(
                gpkg_path=active_gpkg,
                cluster_id=cluster_id,
                pente_moyenne_pct=1.0
            )
            bassin_nom = meta.get("bassin_nom") or meta.get("cluster_nom") or cluster_id
        except Exception as e:
            logger.warning("Échec assemblage INP à la volée pour cluster %s: %s", cluster_id, e)

    if not content:
        raise HTTPException(
            status_code=404,
            detail="Aucun fichier de modèle disponible. Veuillez d'abord exécuter une simulation ou sélectionner un bassin versant."
        )

    filename = _formater_nom_fichier_export(nom_reseau, nom_bassin=bassin_nom, ext="inp")

    return PlainTextResponse(
        content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/download/rpt")
def download_latest_rpt(
    cluster_id: Optional[str] = None,
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context)
):
    """Télécharge le rapport officiel (.rpt) généré par la simulation."""

    _org_id_requete(tenant)
    content = None
    bassin_nom = None
    nom_reseau = None

    # 3D.2 — priorité : RPT de la simulation AUTORISÉE du contexte courant.
    ctx = _contexte_simulation_autorise(
        db, tenant, cluster_id=cluster_id, project_id=project_id)
    if ctx and ctx.data:
        content = ctx.data.get("rpt_content")
        if content:
            meta = ctx.data.get("meta") or {}
            bassin_nom = meta.get("bassin_nom") or meta.get("cluster_nom")
            nom_reseau = (ctx.project.name if ctx.project else None) \
                or ctx.data.get("project_name")

    # 3C.5/R2 — résolution stricte du projet (jamais de .first()).
    proj = _projet_pour_export_repli(db, tenant, project_id=project_id)
    active_gpkg = None
    if proj is not None:
        active_gpkg = _resoudre_gpkg_effectif_pour_projet(db, proj)
        nom_reseau = proj.name
    if active_gpkg is None and proj is None:
        active_gpkg = _gpkg_demo_autorise()
        if active_gpkg is not None:
            nom_reseau = "demo_reseau"

    # 2. Si cluster_id demandé sans simulation autorisée correspondante,
    # chercher dans le cache content-adressé du GPKG effectif du projet —
    # 3C.5/R1 : propriété vérifiée pour chaque fichier avant service.
    if not content and cluster_id and active_gpkg:
        clean_cid = str(cluster_id).strip().lower()
        for cand in _iter_fichiers_cache_simulation(active_gpkg):
            if f"_{clean_cid}_" in cand.name.lower() or f"_cluster_{clean_cid}_" in cand.name.lower():
                try:
                    with open(cand, "r", encoding="utf-8") as cf:
                        cd = json.load(cf)
                    if _est_simulation_valide(cd) and cd.get("rpt_content") \
                            and _fichier_cache_appartenant(db, proj, active_gpkg, cd):
                        content = cd["rpt_content"]
                        bassin_nom = cd.get("meta", {}).get("bassin_nom") or cd.get("meta", {}).get("cluster_nom") or cluster_id
                        break
                except Exception:
                    continue

    if not content:
        raise HTTPException(
            status_code=404,
            detail="Aucun rapport de simulation disponible. Veuillez d'abord exécuter une simulation pour ce bassin."
        )

    filename = _formater_nom_fichier_export(nom_reseau, nom_bassin=bassin_nom, ext="rpt")

    return PlainTextResponse(
        content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# ============================================================
# ORDRE DE MISSION TERRAIN BMS (PDF POUR ÉQUIPES D'ASTREINTE ONA)
# ============================================================

@router.get("/bms/ordre-mission-pdf")
def telecharger_ordre_mission_bms_pdf(
    cluster_id: Optional[str] = None,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Génère et télécharge l'ordre de mission terrain officiel (PDF)
    pour les équipes d'intervention de l'ONA en cas d'alerte météo BMS.
    Identifie la liste prioritaire des regards et collecteurs à curer et sécuriser.
    """
    from src.domain.bms_ordre_mission import generer_pdf_ordre_mission_bms

    _org_id_requete(tenant)

    # 3D.2 — simulation AUTORISÉE du contexte courant, jamais la globale.
    # Contrat historique préservé : PDF générique (données vides) si aucune
    # simulation autorisée — jamais les données d'un autre tenant.
    ctx = _contexte_simulation_autorise(db, tenant)
    sim_data = ctx.data if ctx else {}
    bms_info = sim_data.get("bms_info")

    nom_bassin = (
        sim_data.get("meta", {}).get("bassin_nom")
        or sim_data.get("meta", {}).get("cluster_nom")
        or "Bassin versant urbain"
    )

    pdf_bytes = generer_pdf_ordre_mission_bms(
        simulation_data=sim_data,
        bms_info=bms_info,
        nom_bassin=nom_bassin
    )

    bassin_slug = re.sub(r'[^\w\-]+', '_', nom_bassin)[:30].strip('_') or "reseau"
    filename = f"Ordre_Mission_Terrain_BMS_{bassin_slug}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'}
    )





# ============================================================
# RAPPORT D'EXPERTISE HYDRAULIQUE COMPLET (Phase 6.C)
# ============================================================

@router.get("/rapport-diagnostic-pdf")
def telecharger_rapport_diagnostic_pdf(
    cluster_id: Optional[str] = None,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Génère et télécharge le rapport d'expertise hydraulique complet (PDF)
    conforme aux standards ONA / ANRH pour transmission à la direction technique.
    Contient : cartographie du réseau, liste des contre-pentes, anomalies critiques,
    bilan de continuité massique, volumes inondés, durées de submersion,
    estimation financière des travaux prioritaires.
    """
    from src.domain.rapport_diagnostic import generer_pdf_rapport_diagnostic

    _org_id_requete(tenant)

    # 3D.2 — simulation AUTORISÉE du contexte courant (filtre cluster_id
    # éventuel), jamais la globale partagée ni une restauration non filtrée.
    ctx = _contexte_simulation_autorise(db, tenant, cluster_id=cluster_id)
    sim_data = ctx.data if ctx else None

    if not sim_data or not _est_simulation_valide(sim_data):
        raise HTTPException(
            status_code=404,
            detail="Aucune simulation active disponible pour générer le rapport. Veuillez lancer une simulation SWMM au préalable."
        )

    nom_bassin = (
        sim_data.get("meta", {}).get("bassin_nom")
        or sim_data.get("meta", {}).get("cluster_nom")
        or "Bassin versant urbain"
    )
    project_name = sim_data.get("project_name") or "Réseau Urbain"

    pdf_bytes = generer_pdf_rapport_diagnostic(
        simulation_data=sim_data,
        project_name=project_name
    )

    bassin_slug = re.sub(r'[^\w\-]+', '_', nom_bassin)[:30].strip('_') or "reseau"
    filename = f"Rapport_Expertise_Hydraulique_{bassin_slug}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# ============================================================
# PROFIL EN LONG HYDRAULIQUE (Phase 6.A)
# ============================================================

@router.get("/profil-en-long")
def get_profil_en_long(
    node_amont: str,
    node_aval: str,
    base: str = "max",
    instant_minute: Optional[int] = None,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Calcule et retourne le profil en long hydraulique entre deux regards.
    Chemin topologique amont→aval avec cotes géométriques (radiers, terrain naturel,
    génératrices supérieures) et ligne de charge HGL.

    LOT P0.2 — la HGL provient EXCLUSIVEMENT des cotes hydrauliques réelles
    extraites du fichier .out SWMM (HYDRAULIC_HEAD / INVERT_DEPTH /
    FLOODING_LOSSES) et persistées dans la simulation (`timeseries.
    node_hydraulics`) :
      - base="max" (défaut) : enveloppe des cotes maximales atteintes ;
      - base="instant" + instant_minute : cote à l'instant demandé ;
      - sans données .out (simulation historique) : z_hgl=None et
        hgl_source="indisponible" — aucune valeur estimée n'est présentée
        comme un résultat SWMM.
    """
    if base not in ("max", "instant"):
        raise HTTPException(status_code=422, detail="base doit être 'max' ou 'instant'.")
    if base == "instant" and instant_minute is None:
        raise HTTPException(status_code=422, detail="instant_minute requis avec base='instant'.")

    # 3D.3 — le profil est tracé sur le GPKG DE LA SIMULATION autorisée du
    # contexte (org/projet), jamais sur le fichier mutable ni la globale.
    from api.services.gpkg_versions import (
        resoudre_gpkg_pour_simulation,
        GpkgSimulationError,
    )
    from api.services.simulation_service import (
        resoudre_simulation_courante,
        _resoudre_projet_pour_simulation,
    )

    org_id = _org_id_requete(tenant)

    # Projet résolu de façon non ambiguë + GPKG courant (fallback lecture seule)
    proj = None
    try:
        proj = _resoudre_projet_pour_simulation(db, org_id, None)
    except ProjetAmbigu as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContexteSimulationIntrouvable:
        proj = None
    gpkg_effectif = _resoudre_gpkg_effectif_pour_projet(db, proj)
    if gpkg_effectif is None:
        gpkg_effectif = _gpkg_demo_autorise()

    # Simulation autorisée du contexte : données HGL + snapshot GPKG exact
    sim_data: Dict[str, Any] = {}
    active_gpkg = None
    ctx = None
    try:
        ctx = resoudre_simulation_courante(db, org_id=org_id, resoudre_gpkg=True)
    except ProjetAmbigu as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContexteSimulationIntrouvable:
        ctx = None
    except GpkgSimulationError as e:
        raise HTTPException(status_code=409, detail=str(e))

    if ctx is not None:
        sim_data = ctx.data or {}
        active_gpkg = ctx.gpkg_path if (ctx.gpkg_path and ctx.gpkg_path.exists()) else None
    elif proj is not None and gpkg_effectif and gpkg_effectif.exists():
        # Repli legacy : simulation sans ligne DB (ancien cache disque) —
        # uniquement si le projet est vérifiable (3D.6).
        try:
            restored = _charger_derniere_simulation_disque_ou_db(gpkg_effectif, db, proj)
            if restored and _est_simulation_valide(restored):
                gpkg_rest, _vmeta = resoudre_gpkg_pour_simulation(db, proj, restored)
                sim_data = restored
                active_gpkg = gpkg_rest if (gpkg_rest and gpkg_rest.exists()) else gpkg_effectif
        except GpkgSimulationError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except Exception as e_rest:
            logger.warning("Échec restauration simulation pour profil en long: %s", e_rest)

    # Sans simulation autorisée : lecture seule du réseau courant du projet
    if active_gpkg is None:
        active_gpkg = gpkg_effectif

    if not active_gpkg or not active_gpkg.exists():
        raise HTTPException(status_code=404, detail="Aucun réseau actif chargé.")

    try:
        import geopandas as gpd
        import pandas as pd
        from src.domain.moteur_swmm.constants import _clean_node_id

        layers = gpd.list_layers(str(active_gpkg))["name"].tolist()
        regard_layer = next((l for l in layers if "regard" in l.lower()), "regards")
        pipe_layer = next((l for l in layers if any(k in l.lower() for k in ["canalisat", "conduit", "pipe", "troncon"]) and "désaffect" not in l.lower() and "desaffect" not in l.lower()), "canalisations")

        regards = gpd.read_file(str(active_gpkg), layer=regard_layer)
        canalisations = gpd.read_file(str(active_gpkg), layer=pipe_layer)

        # Construire un index regard Code→géométrie+attributs
        node_index: Dict[str, Any] = {}
        for _, r in regards.iterrows():
            nid = _clean_node_id(r.get("Code"), fallback=str(r.name))
            if nid:
                prof = float(r["Profondeur"]) if ("Profondeur" in r and r["Profondeur"] is not None and not pd.isna(r["Profondeur"]) and float(r["Profondeur"]) > 0) else 2.0
                cotetn = float(r["COTETN"]) if ("COTETN" in r and r["COTETN"] is not None and not pd.isna(r["COTETN"]) and float(r["COTETN"]) > 0) else None
                cotrad = float(r["COTRAD"]) if ("COTRAD" in r and r["COTRAD"] is not None and not pd.isna(r["COTRAD"]) and float(r["COTRAD"]) > 0) else None
                node_index[nid] = {
                    "code": nid,
                    "x": r.geometry.x if r.geometry else 0.0,
                    "y": r.geometry.y if r.geometry else 0.0,
                    "profondeur": prof,
                    "cotetn": cotetn,
                    "cotrad": cotrad,
                }

        # Construire le graphe amont→aval pour trouver le chemin
        import networkx as nx
        from src.domain.graphe_reseau import construire_graphe

        G = construire_graphe(str(active_gpkg))
        if len(G.edges) == 0:
            for idx, c in canalisations.iterrows():
                u = _clean_node_id(c.get("ID_AMONT"))
                v = _clean_node_id(c.get("ID_AVAL"))
                if u and v and u != v:
                    length = float(c["Longeur"]) if ("Longeur" in c and c["Longeur"] > 0) else float(c.geometry.length)
                    diam_mm = float(c["DIAMETRE"]) if ("DIAMETRE" in c and c["DIAMETRE"] > 0) else 600.0
                    cid = f"C_{idx+1}"
                    G.add_edge(u, v, cid=cid, length=length, diam_mm=diam_mm,
                               materiau=str(c.get("MATERIAU", "Béton") or "Béton"),
                               nom_voie=str(c.get("NOM-VOIE", "") or ""))

        # Chercher le nœud dans le réseau
        def find_node(partial: str) -> Optional[str]:
            p_str = str(partial).strip()
            p_clean = _clean_node_id(p_str)
            if p_clean in G.nodes:
                return p_clean
            if p_str in G.nodes:
                return p_str
            for n in G.nodes:
                if p_clean == _clean_node_id(n) or p_str.lower() == str(n).lower():
                    return n
            if len(p_str) >= 3:
                for n in G.nodes:
                    if p_str.lower() in str(n).lower():
                        return n
            return None

        src = find_node(node_amont)
        dst = find_node(node_aval)

        if not src:
            raise HTTPException(status_code=404, detail=f"Regard amont '{node_amont}' introuvable dans le réseau.")
        if not dst:
            raise HTTPException(status_code=404, detail=f"Regard aval '{node_aval}' introuvable dans le réseau.")

        # Trouver le plus court chemin
        try:
            path_nodes = nx.shortest_path(G, src, dst, weight="length")
        except nx.NetworkXNoPath:
            # Essai inverse : si l'utilisateur a sélectionné l'aval avant l'amont
            try:
                path_nodes = nx.shortest_path(G, dst, src, weight="length")
                # Rétablir le sens naturel amont -> aval
                path_nodes = path_nodes[::-1]
                src, dst = dst, src
            except nx.NetworkXNoPath:
                # Tentative en non orienté si des conduites sont numérisées à contre-sens
                try:
                    G_undir = G.to_undirected()
                    path_nodes = nx.shortest_path(G_undir, src, dst, weight="length")
                    # Réaligner le chemin pour qu'il commence toujours par l'amont (src)
                    if path_nodes and path_nodes[0] != src:
                        path_nodes = path_nodes[::-1]
                except nx.NetworkXNoPath:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Aucun chemin hydraulique entre '{node_amont}' et '{node_aval}'. "
                               "Vérifiez que les deux regards appartiennent au même réseau connecté."
                    )

        # Récupérer les élévations nodales depuis la simulation ou le MNT
        node_elevs: Dict[str, float] = {}
        sim_node_results: Dict[str, Any] = {}
        sim_meta: Dict[str, Any] = {}
        # LOT P0.2 — cotes hydrauliques RÉELLES (.out SWMM) persistées dans
        # timeseries.node_hydraulics ; absentes pour les simulations
        # historiques → HGL signalée indisponible, jamais estimée.
        node_hydraulics: Dict[str, Any] = {}
        sim_valide = bool(sim_data and _est_simulation_valide(sim_data))
        if sim_valide:
            sim_node_results = sim_data.get("node_results", {})
            sim_meta = sim_data.get("meta", {})
            ts_data = sim_data.get("timeseries") or {}
            node_hydraulics = ts_data.get("node_hydraulics") or sim_data.get("node_hydraulics") or {}
            # Élévations depuis le meta de la simulation (node_elevs injecté dans meta)
            meta_node_elevs = sim_meta.get("node_elevs", {})
            if meta_node_elevs:
                node_elevs.update(meta_node_elevs)
            # Cotes d'invert réellement utilisées par SWMM (section .inp)
            for nh_nid, nh in node_hydraulics.items():
                inv = nh.get("invert_m")
                if inv is not None:
                    node_elevs.setdefault(str(nh_nid), float(inv))

        def _hydrau_noeud(nid: str) -> Optional[Dict[str, Any]]:
            """Entrée node_hydraulics pour un nœud du graphe (clés = noms .out/INP)."""
            if nid in node_hydraulics:
                return node_hydraulics[nid]
            nc = _clean_node_id(nid)
            if nc in node_hydraulics:
                return node_hydraulics[nc]
            for k, v in node_hydraulics.items():
                if _clean_node_id(k) == nc:
                    return v
            return None

        def _head_reel(nid: str) -> Optional[float]:
            """Cote hydraulique réelle SWMM pour le nœud (max ou instant)."""
            nh = _hydrau_noeud(nid)
            if not nh:
                return None
            if base == "instant":
                pairs = nh.get("heads") or []
                if not pairs:
                    return nh.get("max_head_m")
                best = min(pairs, key=lambda p: abs(p[0] - (instant_minute or 0)))
                return best[1]
            return nh.get("max_head_m")

        def _flood_reel(nid: str) -> float:
            """Débit de débordement RÉEL au même référentiel temporel que la
            cote : à l'instant demandé (base="instant") ou maximum global
            (base="max", enveloppe — instants potentiellement différents)."""
            nh = _hydrau_noeud(nid)
            if not nh:
                return 0.0
            if base == "instant":
                # Même pas échantillonné que la cote : on retient la minute
                # la plus proche dans `heads` puis le débordement à CETTE
                # minute (0 si aucun événement à ce pas). Un débordement à
                # un autre moment n'est jamais imputé à l'instant demandé.
                heads_pairs = nh.get("heads") or []
                if not heads_pairs:
                    return 0.0
                m_cible = min(heads_pairs,
                              key=lambda p: abs(p[0] - (instant_minute or 0)))[0]
                for m, v in (nh.get("floods") or []):
                    if m == m_cible:
                        return float(v)
                return 0.0
            return float(nh.get("flooding_max_m3s") or 0.0)

        hgl_source = ("swmm_out_max_head" if (sim_valide and node_hydraulics and base == "max")
                      else "swmm_out_instant" if (sim_valide and node_hydraulics and base == "instant")
                      else "indisponible")

        # Construire les séries du profil
        segments = []
        distance_cumulee = 0.0

        for i, nid in enumerate(path_nodes):
            info = node_index.get(nid, {})
            profondeur = info.get("profondeur", 2.0)
            cotrad = info.get("cotrad")
            cotetn = info.get("cotetn")

            # Détermination de z_radier
            if cotrad is not None:
                z_rad = cotrad
            elif cotetn is not None:
                z_rad = cotetn - profondeur
            elif nid in node_elevs:
                z_rad = float(node_elevs[nid])
            else:
                z_rad = 100.0 - (distance_cumulee * 0.01)

            # Détermination de z_terrain
            if cotetn is not None:
                z_terrain = cotetn
            else:
                z_terrain = z_rad + profondeur

            # Déterminer le diamètre de conduite local pour la génératrice supérieure
            diam_m = 0.6
            if i < len(path_nodes) - 1:
                next_n = path_nodes[i + 1]
                e = G.get_edge_data(nid, next_n) or G.get_edge_data(next_n, nid) or {}
                if e:
                    diam_m = float(e.get("diam_mm") or e.get("diametre_mm") or 600.0) / 1000.0
            elif i > 0:
                prev_n = path_nodes[i - 1]
                e = G.get_edge_data(prev_n, nid) or G.get_edge_data(nid, prev_n) or {}
                if e:
                    diam_m = float(e.get("diam_mm") or e.get("diametre_mm") or 600.0) / 1000.0

            z_gen_sup = z_rad + diam_m

            # LOT P0.2 — HGL = cote hydraulique RÉELLE du .out SWMM.
            # Aucune reconstruction heuristique : si la cote n'est pas
            # disponible, z_hgl reste None et hgl_reel=False.
            hgl = _head_reel(nid)
            hgl_reel = hgl is not None
            nh_entry = _hydrau_noeud(nid) or {}
            # CONTRÔLE P0.2/A — débordement au MÊME référentiel temporel
            # que la cote (instant exact ou enveloppe max documentée).
            flooding_max = _flood_reel(nid)
            flooding_global_max = float(nh_entry.get("flooding_max_m3s") or 0.0)

            node_sim = sim_node_results.get(nid, {})
            status_n = node_sim.get("status", "normal")
            if hgl is not None:
                # CONTRÔLE P0.2 — distinction stricte :
                #   debordement = débit de débordement RÉELLEMENT calculé par
                #     SWMM (FLOODING_LOSSES > 0) ;
                #   inondation = cote ≥ terrain naturel sans perte de surface
                #     (eau stockée à la parcelle, ex. ALLOW_PONDING) ;
                #   surcharge = mise en charge (cote > génératrice supérieure) ;
                #   libre = écoulement non mis en charge.
                if flooding_max > 0.0:
                    hgl_regime = "debordement"
                elif hgl >= z_terrain:
                    hgl_regime = "inondation"
                elif hgl > z_gen_sup:
                    hgl_regime = "surcharge"
                else:
                    hgl_regime = "libre"
            else:
                # Donnée .out absente : le statut RPT (donnée SWMM réelle)
                # qualifie le régime, mais aucune cote n'est inventée.
                if status_n == "flooded":
                    hgl_regime = "debordement"
                elif status_n == "surcharged":
                    hgl_regime = "surcharge"
                else:
                    hgl_regime = "inconnu"

            # Trouver la conduite qui sort de ce nœud vers le suivant
            conduit = None
            if i < len(path_nodes) - 1:
                next_nid = path_nodes[i + 1]
                edge_data = G.get_edge_data(nid, next_nid) or G.get_edge_data(next_nid, nid) or {}
                if edge_data:
                    geom = edge_data.get("geometry")
                    length = float(edge_data.get("length") or (geom.length if geom else 15.0))
                    diam_mm = float(edge_data.get("diam_mm") or edge_data.get("diametre_mm") or 600.0)
                    conduit = {
                        "cid": edge_data.get("cid") or edge_data.get("id") or f"C_{i+1}",
                        "length": round(length, 2),
                        "diam_mm": diam_mm,
                        "materiau": edge_data.get("materiau", "Béton"),
                        "nom_voie": edge_data.get("nom_voie", ""),
                    }
                    # Résultats simulation sur cette conduite
                    cond_sim = {}
                    if sim_data:
                        all_cond = sim_data.get("conduit_results", {})
                        # Trouver la conduite par u_node/d_node
                        for ck, cv in all_cond.items():
                            if cv.get("u_node") == nid and cv.get("d_node") == next_nid:
                                cond_sim = cv
                                break
                    if cond_sim:
                        conduit["flow_ratio"] = cond_sim.get("flow_ratio", 0.0)
                        conduit["depth_ratio"] = cond_sim.get("depth_ratio", 0.0)
                        conduit["max_flow_cms"] = cond_sim.get("max_flow_cms", 0.0)
                        conduit["status"] = cond_sim.get("status", "normal")
                        conduit["color"] = cond_sim.get("color", "#10b981")
                    else:
                        conduit["flow_ratio"] = 0.0
                        conduit["depth_ratio"] = 0.0
                        conduit["status"] = "inconnu"
                        conduit["color"] = "#64748b"

            # LOT P0.2 — plus de rehaussement heuristique de la HGL depuis le
            # statut de la conduite : la cote .out fait foi. Le statut réel
            # de la conduite reste reporté dans conduit_sortant.

            z_gs = z_rad + (conduit["diam_mm"] / 1000.0 if conduit else diam_m)
            pression_m = round(max(0.0, hgl - z_gs), 2) if (hgl and hgl > z_gs) else 0.0
            revanche_m = round(max(0.0, z_terrain - hgl), 2) if (hgl and hgl < z_terrain) else 0.0

            # Cote du plan d'eau réel dans la conduite (Water Surface Profile - WSP)
            # Si en charge : la conduite est 100% pleine d'eau (z_eau = z_gs)
            # Si écoulement libre : z_eau = min(z_gs, max(z_rad, hgl))
            if hgl is not None:
                z_eau_conduite = z_gs if hgl >= z_gs else max(z_rad, hgl)
            else:
                z_eau_conduite = z_rad

            segments.append({
                "node_id": nid,
                "distance_m": round(distance_cumulee, 2),
                "z_radier": round(z_rad, 3),
                "z_terrain": round(z_terrain, 3),
                "z_gen_superieure": round(z_gs, 3),
                "z_eau_conduite": round(z_eau_conduite, 3),
                "z_hgl": round(hgl, 3) if hgl is not None else None,
                "hgl_reel": hgl_reel,
                "hgl_regime": hgl_regime,
                "atteint_terrain": bool(hgl is not None and hgl >= z_terrain),
                "flooding_m3s": round(flooding_max, 6) if hgl_reel else None,
                "flooding_max_m3s": round(flooding_global_max, 6) if hgl_reel else None,
                "pression_m": pression_m,
                "revanche_m": revanche_m,
                "profondeur_m": round(profondeur, 2),
                "node_status": node_sim.get("status", "normal") if node_sim else "normal",
                "node_color": node_sim.get("color", "#10b981") if node_sim else "#10b981",
                "conduit_sortant": conduit,
            })

            if conduit:
                distance_cumulee += conduit.get("length", 0.0)

        # Ajouter le dernier nœud (aval) sans conduit sortant
        # (il est déjà ajouté dans la boucle)

        # Statistiques du profil
        z_min = min(s["z_radier"] for s in segments)
        z_max = max(s["z_terrain"] for s in segments)
        longueur_totale = distance_cumulee
        conduites_en_charge = sum(
            1 for s in segments
            if s.get("conduit_sortant") and s["conduit_sortant"].get("status") in ("surcharge", "critique")
        )

        # Diagnostic automatique et recommandations expertes
        alerts = []
        for s in segments:
            cond = s.get("conduit_sortant")
            pression = s.get("pression_m", 0.0)
            regime = s.get("hgl_regime", "libre")

            if regime in ("debordement", "inondation") or s["node_status"] == "flooded":
                reco = "Rehaussement du tampon, création d'un bassin de rétention amont ou surcalibrage de la conduite aval."
                if cond and cond.get("diam_mm"):
                    next_diam = int(cond["diam_mm"] * 1.35 // 100 * 100) or int(cond["diam_mm"] + 200)
                    reco = f"Préconisation : recalibrage conduite aval Ø{cond['diam_mm']:.0f} mm → Ø{next_diam} mm ou bassin tampon amont."
                alerts.append({
                    "type": "debordement",
                    "node": s["node_id"],
                    "message": f"🔴 Regard {s['node_id']} en DÉBORDEMENT CRITIQUE (HGL ≥ Terrain)",
                    "observations": f"Niveau d'eau atteignant le tampon (HGL {s['z_hgl']} m). Charge au-dessus voûte : +{pression} m.",
                    "recommandation": reco
                })
            elif regime == "surcharge" or s["node_status"] == "surcharged" or (cond and cond.get("flow_ratio", 0) >= 1.0):
                flow_txt = f" (Q/Qmax = {cond['flow_ratio']:.0%})" if cond and cond.get("flow_ratio") else ""
                alerts.append({
                    "type": "surcharge",
                    "node": s["node_id"],
                    "message": f"🟡 Regard {s['node_id']} : Surcharge hydraulique en cheminée{flow_txt}",
                    "observations": f"Conduite en charge sous pression (+{pression} m au-dessus de la génératrice sup).",
                    "recommandation": f"Vérifier l'effet de remous aval et tester un élargissement de section."
                })
            elif cond and cond.get("flow_ratio", 0) >= 0.8:
                alerts.append({
                    "type": "critique",
                    "node": s["node_id"],
                    "message": f"🟠 Conduite {cond['cid']} proche de la saturation ({cond['flow_ratio']:.0%})",
                    "observations": "Capacité résiduelle inférieure à 20%.",
                    "recommandation": "Surveiller lors d'épisodes orageux de période de retour supérieure à T10."
                })

        return {
            "status": "success",
            "node_amont": src,
            "node_aval": dst,
            "longueur_totale_m": round(longueur_totale, 2),
            "nb_troncons": len(path_nodes) - 1,
            "z_min": round(z_min, 3),
            "z_max": round(z_max, 3),
            "conduites_en_charge": conduites_en_charge,
            "simulation_active": bool(sim_valide),
            "hgl_source": hgl_source,
            "hgl_base": base,
            "hgl_base_label": (
                "enveloppe des cotes maximales individuelles — instants "
                "potentiellement differents par noeud ; la classification "
                "(surcharge/inondation/debordement) porte sur ces memes "
                "maxima individuels, pas sur un instant unique" if base == "max"
                else "profil instantane a l'instant demande — cote, "
                     "debordement et classification au meme pas de temps"),
            "instant_minute": instant_minute,
            "segments": segments,
            "alertes": alerts,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Erreur calcul profil en long: %s", e)
        raise HTTPException(status_code=500, detail=f"Erreur calcul profil en long : {e}")


# ============================================================
# ANIMATION TEMPORELLE & TIME SLIDER (Phase 6.B)
# ============================================================

@router.get("/timeseries")
def get_simulation_timeseries(
    cluster_id: Optional[Union[int, str]] = None,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Retourne les séries temporelles extraites du fichier binaire .out de SWMM
    pour animer la propagation de l'onde de crue (Time Slider).

    Étape 3D.4 — séries lues depuis la simulation AUTORISÉE du contexte
    (org/projet), plus jamais depuis la globale `_DERNIERE_SIMULATION`.
    """
    org_id = _org_id_requete(tenant)

    # Simulation autorisée : filtre bassin si fourni, sinon dernière du projet
    ctx = None
    sim_data: Dict[str, Any] = {}
    for filtres in (({"cluster_id": cluster_id} if cluster_id is not None else {}), {}):
        try:
            ctx = resoudre_simulation_courante(
                db, org_id=org_id, resoudre_gpkg=False, **filtres)
            sim_data = ctx.data or {}
            break
        except (ContexteSimulationIntrouvable, ProjetAmbigu):
            continue

    # 1. Séries temporelles déjà présentes dans le résultat persisté
    if sim_data and _est_simulation_valide(sim_data):
        ts = sim_data.get("timeseries")
        if ts and ts.get("status") == "SUCCESS":
            from src.domain.moteur_swmm.timeseries_extractor import enrichir_timeseries_pluie
            return enrichir_timeseries_pluie(ts, sim_data)

        # Génération à la volée si l'INP est disponible
        inp_content = sim_data.get("inp_content")
        if inp_content:
            logger.info("Génération à la volée des séries temporelles (Phase 6.B)...")
            try:
                from src.domain.moteur_swmm.execution_solver import executer_solver_swmm
                _, _, ts_gen = executer_solver_swmm(inp_content, return_timeseries=True)
                if ts_gen and ts_gen.get("status") == "SUCCESS":
                    sim_data["timeseries"] = ts_gen
                    # Persister dans le résultat de LA simulation (fichier local
                    # ou clé store), jamais dans un cache anonyme.
                    if ctx is not None and ctx.simulation is not None:
                        from api.services.simulation_service import persister_resultat_simulation
                        persister_resultat_simulation(ctx.simulation, sim_data)
                    return ts_gen
            except Exception as e_calc:
                logger.warning("Erreur calcul à la volée timeseries: %s", e_calc)

    # 2. Si aucune simulation autorisée avec séries temporelles
    if not sim_data or not _est_simulation_valide(sim_data):
        raise HTTPException(
            status_code=404,
            detail="Aucune simulation active disponible. Veuillez lancer une simulation SWMM au préalable pour activer l'animation temporelle."
        )

    raise HTTPException(
        status_code=404,
        detail="Séries temporelles non disponibles pour cette simulation. Relancez la simulation pour générer les données dynamiques."
    )


# ============================================================
# ROUTES PARAMÉTRÉES /{simulation_id} (Placées à la fin)
# ============================================================

@router.get("/{simulation_id}", response_model=schemas.SimulationResponse)
def get_simulation(
    simulation_id: str,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Récupère une simulation par ID (périmètre organisation strict)."""
    if simulation_id in ("profil-en-long", "timeseries", "latest", "run", "recalculate", "export", "bassin"):
        raise HTTPException(status_code=404, detail=f"Endpoint '{simulation_id}' non trouvé")
    sim = crud.get_simulation(db, simulation_id, org_id=_org_id_requete(tenant))
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation non trouvée")
    return sim.to_dict()


@router.get("/job/{job_id}", response_model=schemas.SimulationResponse)
def get_simulation_by_job(
    job_id: str,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Récupère une simulation par job_id (Celery)."""
    sim = crud.get_simulation_by_job_id(db, job_id, org_id=_org_id_requete(tenant))
    if not sim:
        raise HTTPException(status_code=404, detail="Job non trouvé")
    return sim.to_dict()


@router.get("/cluster/{cluster_id}", response_model=List[schemas.SimulationResponse])
def list_cluster_simulations(
    cluster_id: int,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Liste des simulations d'un cluster (périmètre organisation strict)."""
    sims = crud.get_simulations(
        db=db,
        status=status,
        skip=skip,
        limit=limit,
        org_id=_org_id_requete(tenant),
    )
    return [s.to_dict() for s in sims if (s.summary_kpis or {}).get("cluster_id") == cluster_id]


def _result_url_simulation(sim) -> Optional[str]:
    """
    URL de téléchargement du résultat d'une simulation.

    Priorité absolue : l'artefact permanent ResultStore `result.json`
    (clé ArtifactStore `{org}/{projet}/simulations/{id}/result.json`,
    compatible `/api/v1/artifacts/download`). Repli : `results_s3_key`
    legacy — qui peut être une clé ArtifactStore (anciennes sims Celery)
    ou un chemin local historique (auquel cas l'URL reste impropre au
    téléchargement, comportement inchangé).
    """
    try:
        from api.services.result_store import (
            ArtifactKind, ResultRef, ResultStore,
        )
        ref = ResultRef.depuis_simulation(sim)
        store = ResultStore()
        key = store.cle(ref, ArtifactKind.RESULT_JSON)
        if store.store.exists(key):
            return (f"/api/v1/artifacts/download?key={key}"
                    f"&project_id={ref.project_id}")
    except Exception:
        pass
    cle = getattr(sim, "results_s3_key", None)
    if cle:
        projet = getattr(sim, "project_id", None)
        suffix = f"&project_id={projet}" if projet else ""
        return f"/api/v1/artifacts/download?key={cle}{suffix}"
    return None


@router.get("/status/{job_id}", response_model=schemas.SimulationStatusResponse)
def get_simulation_status(
    job_id: str,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Polling du statut d'une simulation."""
    sim = crud.get_simulation_by_job_id(db, job_id, org_id=_org_id_requete(tenant))
    if not sim:
        raise HTTPException(status_code=404, detail="Job non trouvé")

    response = {
        "job_id": job_id,
        "status": sim.status
    }

    if sim.status.lower() == "completed":
        response["result_url"] = _result_url_simulation(sim)
    elif sim.status.lower() == "failed":
        response["error"] = (sim.summary_kpis or {}).get("error", "Simulation failed")

    return response


@router.delete("/{simulation_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_simulation(
    simulation_id: str,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Annule une simulation en attente (pending/running)."""
    sim = crud.get_simulation(db, simulation_id, org_id=_org_id_requete(tenant))
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation non trouvée")

    if sim.status.lower() not in ["pending", "running"]:
        raise HTTPException(status_code=400, detail="Impossible d'annuler: statut final")

    sim.status = "cancelled"
    db.commit()

    return None


