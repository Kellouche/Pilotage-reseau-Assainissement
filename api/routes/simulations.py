"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-24
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


def _identite_bassin_du_cache(gpkg_path: Optional[Path], cluster_id: str) -> dict:
    """
    Résout l'identité métier stable d'un bassin depuis le cache de
    sectorisation `<gpkg>.clusters_cache.json` : nom + exutoire_id +
    bassin_ref. Les simulations sont enregistrées dans l'espace
    exutoire_noeud/bassin_ref, alors que le dropdown envoie le
    cluster_id positionnel — ce pont est indispensable pour retrouver
    la bonne simulation (ex. cluster 87 « Cite 80 Logts » → exutoire 234).
    """
    if not gpkg_path or cluster_id is None:
        return {}
    cache = Path(gpkg_path).with_suffix(".clusters_cache.json")
    if not cache.exists():
        return {}
    try:
        import json as _json
        data = _json.loads(cache.read_text(encoding="utf-8"))
    except Exception:
        return {}
    cible = str(cluster_id).strip()
    cible_low = cible.lower()
    prefixed = cible_low.startswith("exutoire:") or cible_low.startswith("bassin:")
    cle = cible.split(":", 1)[1] if prefixed else cible
    cle_low = cle.lower()

    features = [
        f for f in (data.get("bassins_geojson") or {}).get("features", [])
        if (f.get("properties") or {}).get("type") == "bassin_urbain"
    ]

    def _ident(p: dict) -> dict:
        ex = p.get("exutoire_id")
        bref = p.get("bassin_ref") or (f"exutoire:{ex}" if ex else None)
        nb_reg = int(p.get("nb_regards") or 0)
        nb_cond = int(p.get("nb_conduites") or 0)
        surf = float(p.get("surface_ha") or 0.0)
        est_isole = not (nb_reg > 0 or nb_cond > 2 or surf > 0.45)
        return {
            "nom": p.get("nom"),
            "exutoire_id": ex,
            "bassin_ref": bref,
            "nb_regards": nb_reg,
            "nb_conduites": nb_cond,
            "surface_ha": surf,
            "est_isole": est_isole,
            "cluster_id": p.get("cluster_id") or p.get("id_bassin"),
        }

    # EQUIVALENCE DES ESPACES D'IDENTIFIANTS :
    if prefixed:
        for f in features:
            p = f.get("properties") or {}
            bref = str(p.get("bassin_ref") or "").strip().lower()
            ex = str(p.get("exutoire_id") or "").strip().lower()
            if (bref and bref == cible_low) or (ex and ex == cle_low):
                return _ident(p)
            if str(p.get("cluster_id") or "").strip() == cle or str(p.get("id_bassin") or "").strip() == cle:
                return _ident(p)
        return {}

    # 1. Correspondance positionnelle (cluster_id / id_bassin)
    for f in features:
        p = f.get("properties") or {}
        if (str(p.get("cluster_id") or "").strip() == cle
                or str(p.get("id_bassin") or "").strip() == cle):
            return _ident(p)

    # 2. Correspondance exutoire_id ou bassin_ref
    for f in features:
        p = f.get("properties") or {}
        ex = str(p.get("exutoire_id") or "").strip().lower()
        bref = str(p.get("bassin_ref") or "").strip().lower()
        if (ex and ex == cle_low) or (bref and bref == cle_low):
            return _ident(p)

    # 3. Correspondance par nom complet (ex: "Exutoire OUT_55")
    for f in features:
        p = f.get("properties") or {}
        nom = str(p.get("nom") or "").strip().lower()
        nom_ex = str(p.get("nom_exutoire") or "").strip().lower()
        if (nom and nom == cle_low) or (nom_ex and nom_ex == cle_low):
            return _ident(p)

    # 4. Correspondance format "Bassin X" (ex: "Bassin 1")
    if cle_low.startswith("bassin "):
        sub_cle = cle_low.replace("bassin ", "").strip()
        for f in features:
            p = f.get("properties") or {}
            if (str(p.get("cluster_id") or "").strip().lower() == sub_cle
                    or str(p.get("id_bassin") or "").strip().lower() == sub_cle):
                return _ident(p)

    # 5. Correspondance par inclusion de l'exutoire_id (ex: "out_55" dans "exutoire out_55")
    for f in features:
        p = f.get("properties") or {}
        ex = str(p.get("exutoire_id") or "").strip().lower()
        if ex and ex in cle_low.replace(" ", "_").split("_"):
            return _ident(p)
    return {}


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
def get_simulation_typologies_sol(
    ctx: TenantContext = Depends(require_role("viewer"))
):
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
def get_pluviometrie_referentiel(
    ctx: TenantContext = Depends(require_role("viewer"))
):
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
def get_pluviometrie_stations(
    wilaya: Optional[str] = None,
    ctx: TenantContext = Depends(require_role("viewer"))
):
    """Retourne la liste des stations hydro-météorologiques (optionnellement filtrée par wilaya)."""
    from src.domain.referentiel_pluvio import lister_stations
    return {"stations": lister_stations(wilaya_key=wilaya)}


@router.get("/scenarios")
def get_simulation_scenarios(
    station_id: Optional[str] = "chlef_anrh_siege",
    ctx: TenantContext = Depends(require_role("viewer"))
):
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
def preview_bms_scenario(
    payload: BMSPreviewRequest,
    ctx: Optional[TenantContext] = Depends(require_role("viewer"))
):
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


def _signaler_mismatch_version_gpkg(data: Dict[str, Any], ctx: Any, proj: Any) -> None:
    """
    Compare la version GPKG ayant produit la simulation restaurée avec la
    version COURANTE du projet. En cas de divergence, marque
    ``meta.gpkg_version_mismatch`` pour que le frontend puisse avertir
    l'utilisateur : les entités réseau/bassins affichées correspondent à la
    version courante, pas forcément à celle de la simulation.
    """
    try:
        if not isinstance(data, dict):
            return
        vid_sim = None
        if ctx is not None and getattr(ctx, "simulation", None) is not None:
            vid_sim = getattr(ctx.simulation, "gpkg_version_id", None)
        if vid_sim is None and isinstance(getattr(ctx, "meta_version", None), dict):
            vid_sim = ctx.meta_version.get("version_id")
        if vid_sim is None:
            vid_sim = ((data.get("provenance") or {}).get("gpkg_version_id"))
        vid_projet = getattr(proj, "gpkg_version_id", None) if proj is not None else None
        if vid_sim and vid_projet and str(vid_sim) != str(vid_projet):
            meta = data.setdefault("meta", {})
            if isinstance(meta, dict):
                meta["gpkg_version_mismatch"] = True
                meta["gpkg_version_sim_id"] = str(vid_sim)
                meta["gpkg_version_courante_id"] = str(vid_projet)
        # Identité métier stable de la simulation : le frontend doit
        # distinguer les bassins homonymes et les espaces d'identifiants
        # (cluster_id positionnel vs exutoire_noeud / bassin_ref) — sans
        # ces champs, un nom seul ne suffit jamais à identifier un bassin.
        sim = getattr(ctx, "simulation", None) if ctx is not None else None
        if sim is not None:
            meta = data.setdefault("meta", {})
            if isinstance(meta, dict):
                _bref = getattr(sim, "bassin_ref", None)
                _ex = getattr(sim, "exutoire_noeud", None)
                if _bref:
                    meta["bassin_ref"] = str(_bref)
                if _ex:
                    meta["exutoire_noeud"] = str(_ex)
    except Exception:
        pass


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


@router.get("/reconciliation")
def get_simulation_reconciliation(
    cluster_id: Optional[str] = None,
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context)
):
    """
    Bilan de réconciliation 1:1 entre le SIG source (GPKG) et le modèle SWMM (.inp).
    Présente l'inventaire avant/après, la ventilation du parc (matériaux, formes, diamètres),
    la matrice d'écarts type des sections SWMM 5.2 et le registre des exclusions auditées.
    """
    _org_id_requete(tenant)
    ctx = _contexte_simulation_autorise(
        db, tenant, cluster_id=cluster_id, project_id=project_id)
    if not ctx or not ctx.data:
        raise HTTPException(
            status_code=404,
            detail="Aucune simulation disponible pour ce contexte."
        )

    meta = ctx.data.get("meta", {})
    reconciliation = meta.get("reconciliation")
    if not reconciliation:
        raise HTTPException(
            status_code=404,
            detail="Bilan de réconciliation non disponible pour cette simulation."
        )

    return {
        "status": "success",
        "simulation_id": ctx.data.get("simulation_id"),
        "cluster_id": cluster_id,
        "reconciliation": reconciliation
    }


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



# ============================================================
# ANIMATION TEMPORELLE & TIME SLIDER (Phase 6.B)
# ============================================================

def _injecter_fiabilite_timeseries(ts_out: Dict[str, Any], sim_data: Dict[str, Any]) -> Dict[str, Any]:
    """Ajoute le verdict du garde-fou hydraulicien aux séries temporelles
    pour que le time slider affiche l'avertissement de fiabilité."""
    if isinstance(ts_out, dict) and isinstance(sim_data, dict):
        _gf = (sim_data.get("agents_expertise") or {}).get("controle_modele_hydraulique") or {}
        if _gf:
            ts_out["fiabilite_modele"] = _gf.get("fiabilite_modele")
            ts_out["modelisation_anomalies"] = _gf.get("anomalies") or []
    return ts_out


@router.get("/recherche-element")
def rechercher_element_reseau(
    q: str,
    project_id: Optional[str] = None,
    limite: int = 20,
    snapshot: Optional[str] = None,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Recherche un regard (par code) ou un tronçon (par regard amont/aval)
    dans le GPKG du projet — alimente l'outil de recherche du profil en
    long. Lecture seule, isolation org_id stricte (stealth 404).
    """
    org_id = _org_id_requete(tenant)
    requete = (q or "").strip()
    if len(requete) < 2:
        return {"resultats": [], "total": 0}
    limite = max(1, min(int(limite or 20), 50))

    proj = None
    try:
        proj = _resoudre_projet_pour_simulation(db, org_id, project_id)
    except ProjetAmbigu as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContexteSimulationIntrouvable:
        if project_id:
            raise HTTPException(status_code=404, detail="Projet introuvable ou non autorisé.")
        proj = None
    gpkg_effectif = None
    if proj is not None:
        try:
            from api.services.gpkg_versions import (
                resoudre_snapshot_pour_lecture, GpkgSimulationError)
            snap_ctx = resoudre_snapshot_pour_lecture(db, proj, snapshot)
            gpkg_effectif = snap_ctx["path"]
        except GpkgSimulationError:
            if snapshot:
                raise HTTPException(status_code=404, detail="Ressource introuvable")
            gpkg_effectif = _resoudre_gpkg_effectif_pour_projet(db, proj)
    if gpkg_effectif is None:
        gpkg_effectif = _resoudre_gpkg_effectif_pour_projet(db, proj)
    if gpkg_effectif is None:
        gpkg_effectif = _gpkg_demo_autorise()
    if gpkg_effectif is None or not gpkg_effectif.exists():
        raise HTTPException(status_code=404, detail="Réseau introuvable.")

    from api.services.profil_topo_service import _charger_topo_pour_profil
    topo = _charger_topo_pour_profil(gpkg_effectif)
    node_index = topo.get("node_index") or {}
    canalisations = topo.get("canalisations")

    q_low = requete.lower()
    # Recherche numérique tolérante : « 615 » doit trouver « 6152 ».
    q_num = None
    try:
        q_num = float(requete)
    except (TypeError, ValueError):
        pass

    resultats = []

    # --- Regards ---
    for nid, info in node_index.items():
        nid_low = str(nid).lower()
        match = q_low in nid_low
        if not match and q_num is not None:
            try:
                match = float(nid) == q_num
            except (TypeError, ValueError):
                pass
        if match:
            resultats.append({
                "type": "regard",
                "id": nid,
                "libelle": f"Regard {nid}",
                "sous_titre": info.get("nom_voie") or "",
                "lng": info.get("x"),
                "lat": info.get("y"),
            })
            if len([r for r in resultats if r["type"] == "regard"]) >= limite:
                break

    # --- Tronçons (identifiés par le couple amont → aval) ---
    if canalisations is not None and len(resultats) < limite * 2:
        try:
            cols = set(canalisations.columns)
            col_am = next((c for c in ("ID_AMONT", "id_amont", "AMONT") if c in cols), None)
            col_av = next((c for c in ("ID_AVAL", "id_aval", "AVAL") if c in cols), None)
            if col_am and col_av:
                for _, row in canalisations.iterrows():
                    am = str(row.get(col_am) or "").strip()
                    av = str(row.get(col_av) or "").strip()
                    if not am or not av:
                        continue
                    pair = f"{am} → {av}"
                    hay = f"{am} {av} {pair}".lower()
                    match = q_low in hay
                    if not match and q_num is not None:
                        try:
                            match = (float(am) == q_num or float(av) == q_num)
                        except (TypeError, ValueError):
                            pass
                    if match:
                        try:
                            geom = row.geometry
                            cx, cy = (geom.centroid.x, geom.centroid.y) if geom else (None, None)
                        except Exception:
                            cx = cy = None
                        resultats.append({
                            "type": "troncon",
                            "id": pair,
                            "libelle": f"Tronçon {am} → {av}",
                            "sous_titre": str(row.get("NOM-VOIE") or row.get("nom_voie") or ""),
                            "lng": cx,
                            "lat": cy,
                            "amont": am,
                            "aval": av,
                        })
                        if len([r for r in resultats if r["type"] == "troncon"]) >= limite:
                            break
        except Exception as e:
            logger.warning("Recherche tronçons impossible : %s", e)

    # Regards d'abord, tronçons ensuite, plafond global
    regards = [r for r in resultats if r["type"] == "regard"][:limite]
    troncons = [r for r in resultats if r["type"] == "troncon"][:limite]

    # Conversion CRS projet → WGS84 pour le centrage carte Leaflet
    _crs = topo.get("crs")
    if _crs and "4326" not in str(_crs):
        try:
            from pyproj import Transformer
            _tf = Transformer.from_crs(str(_crs), "EPSG:4326", always_xy=True)
            for _r in regards + troncons:
                if _r.get("lng") is not None and _r.get("lat") is not None:
                    try:
                        _r["lng"], _r["lat"] = _tf.transform(_r["lng"], _r["lat"])
                    except Exception:
                        pass
        except Exception as e:
            logger.warning("Transformation CRS recherche impossible : %s", e)

    return {"resultats": regards + troncons, "total": len(regards) + len(troncons)}


@router.get("/timeseries")
def get_simulation_timeseries(
    cluster_id: Optional[Union[int, str]] = None,
    exutoire_noeud: Optional[str] = None,
    bassin_ref: Optional[str] = None,
    simulation_id: Optional[str] = None,
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

    # Simulation autorisée : filtre bassin si fourni, sinon dernière du projet.
    # Le cluster_id du dropdown est positionnel alors que les simulations
    # sont enregistrées sous exutoire_noeud/bassin_ref : résoudre la même
    # identité métier que /bassin/{id} sinon les séries d'un autre bassin
    # seraient servies (link_id sans correspondance → carte toute verte).
    filtres = {}
    if cluster_id is not None:
        filtres["cluster_id"] = cluster_id
    # Identité métier stable transmise directement par le client
    # (dataset.bassinRef / dataset.exutoireId du dropdown) : contourne le
    # pont positionnel→exutoire par cache, fragile si le cache est absent.
    if exutoire_noeud:
        filtres["exutoire_noeud"] = str(exutoire_noeud).strip()
    if bassin_ref:
        filtres["bassin_ref"] = str(bassin_ref).strip()
    if cluster_id is not None or exutoire_noeud or bassin_ref:
        try:
            _cid_txt = str(cluster_id).strip() if cluster_id is not None else ""
            _ref_ex = _cid_txt.lower().startswith("exutoire:")
            _cle = _cid_txt.split(":", 1)[1] if _ref_ex else cluster_id
            proj_id = _resoudre_projet_pour_simulation(db, org_id, None)
            gpkg_id = _resoudre_gpkg_effectif_pour_projet(db, proj_id)
            # _cid_txt conserve « exutoire: » : la fonction de cache
            # distingue les espaces exutoire / positionnel.
            ident = _identite_bassin_du_cache(gpkg_id, _cid_txt) if _cid_txt else {}
            _exo = ident.get("exutoire_id") or (_cle if _ref_ex else None)
            _bref = ident.get("bassin_ref") or (_cid_txt if _ref_ex else None)
            if _exo and "exutoire_noeud" not in filtres:
                filtres["exutoire_noeud"] = _exo
            if _bref and "bassin_ref" not in filtres:
                filtres["bassin_ref"] = _bref
            if ident.get("nom"):
                filtres["bassin_nom_attendu"] = ident["nom"]
        except Exception as _e_ident:
            # Sans ce log, une erreur transitoire (verrou SQLite pendant
            # l'écriture de la simulation, GPKG non résolu…) dégradait
            # silencieusement le filtre au seul cluster_id positionnel,
            # qui ne peut jamais matcher → 404 « aucune simulation active ».
            logger.warning("[timeseries] Identité bassin non résolue pour cluster_id=%s : %s", cluster_id, _e_ident)

    ctx = None
    sim_data: Dict[str, Any] = {}
    # Repli « dernière simulation » UNIQUEMENT sans filtre bassin : avec un
    # filtre demandé, servir les séries d'un autre bassin produirait
    # des link_id sans correspondance (carte entièrement verte).
    # simulation_id explicite = LA simulation affichée par le client :
    # prioritaire sur tout filtre bassin (évite de servir les séries d'une
    # sim d'une autre version réseau que le snapshot affiché).
    if simulation_id:
        try:
            ctx = resoudre_simulation_courante(
                db, org_id=org_id, resoudre_gpkg=False,
                simulation_id=simulation_id)
            sim_data = ctx.data or {}
        except (ContexteSimulationIntrouvable, ProjetAmbigu) as _e_ts:
            raise HTTPException(status_code=404, detail="Ressource introuvable")
    else:
        _a_filtre = bool(cluster_id is not None or exutoire_noeud or bassin_ref)
        _essais = [filtres] if _a_filtre else [filtres, {}]
        for f in _essais:
            try:
                ctx = resoudre_simulation_courante(
                    db, org_id=org_id, resoudre_gpkg=False, **f)
                sim_data = ctx.data or {}
                break
            except (ContexteSimulationIntrouvable, ProjetAmbigu):
                continue

    # 1. Séries temporelles déjà présentes dans le résultat persisté
    if sim_data and _est_simulation_valide(sim_data):
        ts = sim_data.get("timeseries")
        if ts and ts.get("status") == "SUCCESS":
            from src.domain.moteur_swmm.timeseries_extractor import enrichir_timeseries_pluie
            return _injecter_fiabilite_timeseries(enrichir_timeseries_pluie(ts, sim_data), sim_data)

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
                    return _injecter_fiabilite_timeseries(ts_gen, sim_data)
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

@router.get("/{simulation_id}/resultat")
def get_simulation_resultat(
    simulation_id: str,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Retourne le résultat COMPLET sauvegardé d'une simulation précise
    (result.json / cache), pour affichage instantané sur la carte —
    aucun recalcul SWMM, aucune nouvelle simulation créée.
    """
    org_id = _org_id_requete(tenant)
    ctx = None
    try:
        ctx = resoudre_simulation_courante(
            db, org_id=org_id, simulation_id=simulation_id,
            resoudre_gpkg=True)
    except (ContexteSimulationIntrouvable, ProjetAmbigu):
        ctx = None
    except Exception:
        # La résolution GPKG peut échouer sans que le résultat soit perdu
        try:
            ctx = resoudre_simulation_courante(
                db, org_id=org_id, simulation_id=simulation_id,
                resoudre_gpkg=False)
        except Exception:
            ctx = None

    if ctx is None or not ctx.data or not _est_simulation_valide(ctx.data):
        raise HTTPException(
            status_code=404,
            detail="Résultat de simulation introuvable ou invalide pour ce contexte.")

    data = ctx.data
    if ctx.gpkg_path is not None and ctx.gpkg_path.exists():
        data["source_gpkg"] = str(ctx.gpkg_path.resolve())
    if ctx.project is not None and getattr(ctx.project, "name", None):
        data["project_name"] = ctx.project.name
    _signaler_mismatch_version_gpkg(data, ctx, ctx.project)
    return _construire_reponse_simulation(
        data, cached=True,
        simulation_id=(ctx.simulation.id if ctx.simulation is not None else simulation_id))


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
    """
    - pending/running : annule la simulation (statut 'cancelled') ;
    - statut final (completed/failed/cancelled) : suppression définitive
      de la simulation et de ses artefacts (cache disque + ResultStore).
    """
    from api.services.simulation_service import supprimer_simulation

    sim = crud.get_simulation(db, simulation_id, org_id=_org_id_requete(tenant))
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation non trouvée")

    if sim.status.lower() in ["pending", "running"]:
        sim.status = "cancelled"
        db.commit()
        return None

    supprimer_simulation(sim, db)
    return None


