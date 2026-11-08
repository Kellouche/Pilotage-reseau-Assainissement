"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Endpoints de lancement de simulation SWMM 5.2 et restitution des résultats
================================================================================
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.orm import Session
from typing import List, Optional, Any, Dict, Union, Tuple
from pathlib import Path
import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

from api.database import get_db
from api import schemas, crud
from api.core.security import get_tenant_context_optional, TenantContext
from api.core.jobs import create_job
from api.models import Organization

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
    tenant: Optional[TenantContext] = Depends(get_tenant_context_optional),
):
    """Liste toutes les simulations (ordre décroissant)."""
    org_id = tenant.org.id if tenant else None
    sims = crud.get_simulations(db=db, skip=skip, limit=limit, status=status, org_id=org_id)
    return [s.to_dict() for s in sims]

@router.post("", response_model=schemas.SimulationResponse, status_code=status.HTTP_202_ACCEPTED)
def launch_simulation(
    simulation: schemas.SimulationCreate,
    user_id: str = "system",
    db: Session = Depends(get_db),
    tenant: Optional[TenantContext] = Depends(get_tenant_context_optional),
):
    """
    Lance une simulation SWMM asynchrone pour un cluster (Phase 2.4).
    Retourne immédiatement avec un job_id pour polling ou WebSocket.
    """
    org_id = tenant.org.id if tenant else None
    if not org_id:
        default_org = db.query(Organization).first()
        org_id = default_org.id if default_org else "org_default"

    # Vérifier cluster existe
    cluster = crud.get_cluster(db, simulation.cluster_id, org_id=org_id if tenant else None)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster non trouvé")

    network_id = getattr(cluster, "network_id", None)
    scenario_pluie = (simulation.parameters or {}).get("scenario_pluie", "pluie_decennale")
    duree_heures = float((simulation.parameters or {}).get("duree_heures", 24.0))

    # 1. Créer le Job asynchrone
    job = create_job(
        db=db,
        org_id=org_id,
        job_type="simulation_swmm",
        network_id=network_id,
        payload={
            "cluster_id": simulation.cluster_id,
            "parameters": simulation.parameters or {},
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
        created_by=tenant.user.id if (tenant and tenant.user) else user_id,
        org_id=org_id,
        project_id=network_id,
        scenario_pluie=scenario_pluie,
        duree_heures=duree_heures,
    )

    # 3. Déclencher la tâche Celery asynchrone
    try:
        from workers.tasks.swmm_tasks import run_swmm_simulation_task
        run_swmm_simulation_task.delay(
            job_id=job.id,
            org_id=org_id,
            network_id=network_id,
            scenario_pluie=scenario_pluie,
            duree_heures=duree_heures,
            parameters={"cluster_id": simulation.cluster_id, **(simulation.parameters or {})},
        )
    except Exception:
        # Fallback synchrone propre si Redis / Celery broker non disponible
        from workers.tasks.swmm_tasks import run_swmm_simulation_task
        run_swmm_simulation_task(
            job_id=job.id,
            org_id=org_id,
            network_id=network_id,
            scenario_pluie=scenario_pluie,
            duree_heures=duree_heures,
            parameters={"cluster_id": simulation.cluster_id, **(simulation.parameters or {})},
        )

    return sim_obj.to_dict()


# ============================================================
# MOTEUR EPA SWMM 5.2 NATIF & CONFIGURATION (Phase 2bis)
# Placé AVANT /{simulation_id} pour éviter les conflits de routage Starlette
# ============================================================

from pathlib import Path
import hashlib
import json
import uuid
from datetime import datetime, timezone
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from src.domain.moteur_swmm import MoteurSWMM, SCENARIOS_PLUIE

_DERNIERE_SIMULATION: Dict[str, Any] = {}


def reinitialiser_derniere_simulation():
    """Efface la dernière simulation en cache pour éviter les fuites entre réseaux."""
    global _DERNIERE_SIMULATION
    _DERNIERE_SIMULATION = {}


class SimulationRunRequest(BaseModel):
    scenario_key: str = "pluie_decennale"
    duree_heures: Optional[float] = None
    pas_routage_sec: int = 5
    cluster_id: Optional[Union[int, str]] = None
    pente_moyenne_pct: Optional[float] = 1.0
    buffer_m: Optional[float] = 35.0
    valider_raccordement: Optional[bool] = True
    typologie_sol: Optional[str] = "habitat_mixte"
    imperv_pct: Optional[float] = None
    intensite_max_mmh: Optional[float] = None
    station_id: Optional[str] = "chlef_anrh_siege"
    raccordements_orphelins: Optional[List[Dict[str, Any]]] = None
    force_recalculate: Optional[bool] = False

SimulationRunRequest.model_rebuild()


def _generer_cle_cache_simulation(gpkg_path: Path, payload: SimulationRunRequest) -> Tuple[str, Dict[str, Any]]:
    """
    Génère un dictionnaire canonique normalisé et une empreinte SHA-256
    garantissant l'idempotence exacte de la simulation hydrodynamique.
    Prend en compte l'état physique du GPKG (mtime) et l'intégralité des paramètres d'ingénierie.
    """
    gpkg_stat = gpkg_path.stat() if gpkg_path.exists() else None
    gpkg_mtime = int(gpkg_stat.st_mtime) if gpkg_stat else 0
    gpkg_size = int(gpkg_stat.st_size) if gpkg_stat else 0

    orph_ids = []
    if payload.raccordements_orphelins:
        for item in payload.raccordements_orphelins:
            if isinstance(item, dict):
                orph_ids.append(str(item.get("id", item.get("nom", ""))))
            else:
                orph_ids.append(str(item))
    orph_ids.sort()

    params_dict = {
        "gpkg_name": gpkg_path.name,
        "gpkg_mtime": gpkg_mtime,
        "gpkg_size": gpkg_size,
        "cluster_id": str(payload.cluster_id),
        "scenario_key": str(payload.scenario_key),
        "duree_heures": float(payload.duree_heures) if payload.duree_heures is not None else None,
        "pas_routage_sec": int(payload.pas_routage_sec or 5),
        "pente_moyenne_pct": float(payload.pente_moyenne_pct or 1.0),
        "buffer_m": float(payload.buffer_m or 35.0),
        "valider_raccordement": bool(payload.valider_raccordement if payload.valider_raccordement is not None else True),
        "typologie_sol": str(payload.typologie_sol or "habitat_mixte"),
        "imperv_pct": float(payload.imperv_pct) if payload.imperv_pct is not None else None,
        "intensite_max_mmh": float(payload.intensite_max_mmh) if payload.intensite_max_mmh is not None else None,
        "station_id": str(payload.station_id or "chlef_anrh_siege"),
        "raccordements_orphelins": orph_ids,
    }

    serialized = json.dumps(params_dict, sort_keys=True, ensure_ascii=False)
    param_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
    return param_hash, params_dict


def _get_cache_simulation_file(gpkg_path: Path, cluster_id: Any, param_hash: str) -> Path:
    """Retourne le chemin vers le fichier de persistance de simulation."""
    cache_dir = gpkg_path.parent / ".simulation_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    clean_stem = re.sub(r'[^\w\-]+', '_', gpkg_path.stem)
    return cache_dir / f"sim_{clean_stem}_cluster_{cluster_id}_{param_hash}.json"


def _est_simulation_valide(data: Any) -> bool:
    """Vérifie si les résultats de simulation sont valides et non un artefact corrompu ou factice."""
    if not isinstance(data, dict):
        return False
    if "node_results" not in data or "conduit_results" not in data:
        return False
    meta = data.get("meta") or {}
    bbox = meta.get("bbox")
    if bbox and len(bbox) == 4:
        # Rejeter les coordonnées dummy résiduelles (0, 0) envoyées dans l'océan Atlantique
        if abs(bbox[0]) < 1.0 and abs(bbox[1]) < 2.0:
            return False
    # Valide si des conduits/junctions sont répertoriés dans les métadonnées OU dans les dictionnaires de résultats
    nb_conduits = meta.get("conduits_count", 0) or len(data.get("conduit_results", {}))
    nb_junctions = meta.get("junctions_count", 0) or len(data.get("node_results", {}))
    if nb_conduits <= 0 and nb_junctions <= 0 and not data.get("inp_content"):
        return False
    return True


def _charger_cache_simulation(gpkg_path: Path, cluster_id: Any, param_hash: str) -> Optional[Dict[str, Any]]:
    """Charge les résultats de la simulation si le fichier de cache existe."""
    cache_file = _get_cache_simulation_file(gpkg_path, cluster_id, param_hash)
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data and _est_simulation_valide(data):
                return data
        except Exception as e:
            logger.warning("Échec de lecture du cache simulation %s: %s", cache_file, e)
    return None


def _sauvegarder_simulation(
    db: Session,
    gpkg_path: Path,
    cluster_id: Any,
    param_hash: str,
    params_dict: Dict[str, Any],
    resultat: Dict[str, Any],
    proj: Any = None,
    tenant: Any = None,
) -> Path:
    """Sauvegarde les résultats complets sur disque et référence la simulation dans la base SQLite."""
    from api.models import Simulation

    cache_file = _get_cache_simulation_file(gpkg_path, cluster_id, param_hash)

    # 1. Sauvegarde du JSON complet sur disque
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False)
    except Exception as e:
        logger.error("Erreur lors de l'écriture du cache simulation sur disque: %s", e)

    # 2. Enregistrement en base de données SQLAlchemy
    try:
        org_id = tenant.org_id if (tenant and hasattr(tenant, "org_id")) else None
        project_id = proj.id if proj else None
        project_name = proj.name if proj else gpkg_path.stem

        kpis_summary = {
            "param_hash": param_hash,
            "cluster_id": cluster_id,
            "scenario_key": params_dict.get("scenario_key"),
            "parameters": params_dict,
            "peak_outflow_m3s": resultat.get("peak_outflow_m3s"),
            "routing_continuity_error_pct": resultat.get("routing_continuity_error_pct"),
            "flooded_nodes_count": resultat.get("flooded_nodes_count", 0),
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }

        sim_record = Simulation(
            id=str(uuid.uuid4()),
            org_id=org_id,
            project_id=project_id,
            name=f"SWMM_{project_name}_{cluster_id}_{params_dict.get('scenario_key', 'pluie')}",
            status="completed",
            scenario_pluie=str(params_dict.get("scenario_key", "pluie_decennale")),
            duree_heures=float(params_dict.get("duree_heures") or 4.0),
            results_s3_key=str(cache_file.resolve()),
            summary_kpis=kpis_summary,
            execution_time_seconds=float(resultat.get("meta", {}).get("execution_duration_sec", 0.0)),
        )
        db.add(sim_record)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("Avertissement: enregistrement de la simulation en DB impossible: %s", e)

    return cache_file


def _charger_derniere_simulation_disque_ou_db(gpkg_path: Path, db: Session, proj: Any = None) -> Optional[Dict[str, Any]]:
    """
    Recherche la simulation la plus récente enregistrée pour ce GeoPackage
    en vérifiant d'abord la table `simulations` en DB, puis le dossier `.simulation_cache/`.
    """
    from api.models import Simulation
    # 1. Vérifier la table Simulation
    try:
        query = db.query(Simulation).filter(Simulation.status == "completed")
        if proj:
            query = query.filter(Simulation.project_id == proj.id)
        last_sim = query.order_by(Simulation.created_at.desc()).first()
        if last_sim and last_sim.results_s3_key:
            p = Path(last_sim.results_s3_key)
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data and _est_simulation_valide(data):
                    return data
    except Exception as e:
        logger.warning("Erreur interrogation table simulations: %s", e)

    # 2. Fallback dossier .simulation_cache/
    cache_dir = gpkg_path.parent / ".simulation_cache"
    clean_stem = re.sub(r'[^\w\-]+', '_', gpkg_path.stem)
    if cache_dir.exists():
        files = list(cache_dir.glob(f"sim_{clean_stem}_cluster_*.json"))
        if files:
            files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            for fpath in files:
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data and _est_simulation_valide(data):
                        return data
                except Exception:
                    continue
    return None


def _construire_reponse_simulation(resultat: Dict[str, Any], cached: bool = False) -> Dict[str, Any]:
    """Structure la réponse standardisée renvoyée au frontend."""
    message = (
        "Résultats restaurés instantanément depuis la sauvegarde (paramètres de simulation inchangés)."
        if cached
        else "Simulation hydrodynamique SWMM 5.2 exécutée avec succès."
    )
    return {
        "status": "success",
        "cached": cached,
        "message": message,
        "meta": resultat.get("meta", {}),
        "kpis": {
            "routing_continuity_error_pct": resultat.get("routing_continuity_error_pct"),
            "runoff_continuity_error_pct": resultat.get("runoff_continuity_error_pct"),
            "total_precipitation_mm": resultat.get("total_precipitation_mm"),
            "total_precipitation_volume_m3": resultat.get("total_precipitation_volume_m3"),
            "total_runoff_volume_m3": resultat.get("total_runoff_volume_m3"),
            "total_infiltration_volume_m3": resultat.get("total_infiltration_volume_m3"),
            "total_outflow_m3": resultat.get("total_outflow_m3"),
            "peak_outflow_m3s": resultat.get("peak_outflow_m3s"),
            "effective_runoff_coeff": resultat.get("effective_runoff_coeff"),
            "peak_time_str": resultat.get("peak_time_str"),
            "max_velocity_ms": resultat.get("max_velocity_ms"),
            "autocurage_statut": resultat.get("autocurage_statut"),
            "autocurage_color": resultat.get("autocurage_color"),
            "autocurage_note": resultat.get("autocurage_note"),
            "total_network_length_m": resultat.get("total_network_length_m"),
            "surcharged_length_m": resultat.get("surcharged_length_m"),
            "surcharged_length_pct": resultat.get("surcharged_length_pct"),
            "coherence_pluie_debit": resultat.get("coherence_pluie_debit"),
            "typologie_sol": resultat.get("meta", {}).get("typologie_sol"),
            "typologie_nom": resultat.get("meta", {}).get("typologie_nom"),
            "imperv_pct": resultat.get("meta", {}).get("imperv_pct"),
            "pluvio_station": resultat.get("meta", {}).get("pluvio_station"),
            "pluvio_station_id": resultat.get("meta", {}).get("pluvio_station_id"),
            "pluvio_code_anrh": resultat.get("meta", {}).get("pluvio_code_anrh"),
            "pluvio_wilaya": resultat.get("meta", {}).get("pluvio_wilaya"),
            "pluvio_scenario_nom": resultat.get("meta", {}).get("pluvio_scenario_nom"),
            "pluvio_periode_retour": resultat.get("meta", {}).get("pluvio_periode_retour"),
            "pluvio_intensite_max_mmh": resultat.get("meta", {}).get("pluvio_intensite_max_mmh"),
            "pluvio_montana": resultat.get("meta", {}).get("pluvio_montana"),
            "pluvio_hauteur_totale_mm": resultat.get("meta", {}).get("pluvio_hauteur_totale_mm"),
            "pluvio_p24_mm": resultat.get("meta", {}).get("pluvio_p24_mm"),
            "pluvio_source": resultat.get("meta", {}).get("pluvio_source"),
            "flooded_nodes_count": resultat.get("flooded_nodes_count"),
            "surcharged_nodes_count": resultat.get("surcharged_nodes_count", 0),
            "flooded_nodes": resultat.get("flooded_nodes", [])[:15],
            "q_deleste_m3s": resultat.get("q_deleste_m3s", 0.0),
            "q_deleste_ls": resultat.get("q_deleste_ls", 0.0),
            "q_derive_m3s": resultat.get("q_derive_m3s", resultat.get("q_deleste_m3s", 0.0)),
            "q_exutoire_m3s": resultat.get("q_exutoire_m3s", round(float(resultat.get("peak_outflow_m3s") or 0.0), 3)),
            "q_genere_m3s": resultat.get("q_genere_m3s", round(float(resultat.get("peak_outflow_m3s") or 0.0) + float(resultat.get("q_deleste_m3s") or 0.0), 3)),
            "taux_derive_pct": resultat.get("taux_derive_pct", 0.0),
            "taux_exutoire_pct": resultat.get("taux_exutoire_pct", 100.0),
            "soulagement_reseau_pct": resultat.get("soulagement_reseau_pct", resultat.get("taux_derive_pct", 0.0)),
            "reduction_charge_pct": resultat.get("reduction_charge_pct", resultat.get("taux_derive_pct", 0.0)),
            "nb_ouvrages_raccordes": resultat.get("nb_ouvrages_raccordes", 0),
            "bilan_hydraulique": resultat.get("bilan_hydraulique", {}),
            "bilan_hydraulique_decisionnel": resultat.get("bilan_hydraulique_decisionnel", ""),
            "compliance_continuity": resultat.get("compliance_continuity", True),
        },
        "buffer_sensitivity": resultat.get("buffer_sensitivity", {}),
        "agents_expertise": resultat.get("agents_expertise", {}),
        "node_results": resultat.get("node_results", {}),
        "conduit_results": resultat.get("conduit_results", {}),
        "download_inp_url": "/api/v1/simulations/download/inp",
        "download_rpt_url": "/api/v1/simulations/download/rpt",
    }


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


@router.get("/ouvrages-proches")
def get_simulation_ouvrages_proches(
    cluster_id: str,
    rayon_m: float = 45.0,
    db: Session = Depends(get_db),
    tenant: Optional[TenantContext] = Depends(get_tenant_context_optional),
):
    """
    Retourne les ouvrages spéciaux orphelins (déversoirs d'orage, trop-pleins, stations de relevage)
    détectés à proximité (< rayon_m) du bassin sélectionné pour validation interactive avant simulation.
    """
    from src.domain.ouvrages_orphelins import detecter_ouvrages_orphelins_proches
    from api.models import Project

    gpkg_path = None
    if tenant and hasattr(tenant, "org_id") and tenant.org_id:
        proj = db.query(Project).filter(
            Project.org_id == tenant.org_id,
            Project.is_archived.is_(False)
        ).first()
        if proj and proj.source_gpkg_key and Path(proj.source_gpkg_key).exists():
            gpkg_path = Path(proj.source_gpkg_key)

    if not gpkg_path:
        proj = db.query(Project).filter(Project.is_archived.is_(False)).first()
        if proj and proj.source_gpkg_key and Path(proj.source_gpkg_key).exists():
            gpkg_path = Path(proj.source_gpkg_key)
        else:
            cand = Path("data/demo_reseau.gpkg")
            if cand.exists():
                gpkg_path = cand

    if not gpkg_path or not gpkg_path.exists():
        raise HTTPException(status_code=404, detail="Réseau hydraulique introuvable pour ce projet.")

    return detecter_ouvrages_orphelins_proches(str(gpkg_path), cluster_id, rayon_max_m=rayon_m)


@router.post("/run")
def run_native_swmm_simulation(
    payload: SimulationRunRequest,
    db: Session = Depends(get_db),
    tenant: Optional[TenantContext] = Depends(get_tenant_context_optional),
):
    """
    Exécute la simulation hydrodynamique EPA SWMM 5.2 native pour le réseau actif.
    Sauvegarde systématiquement les résultats sur disque et en base de données.
    Implémente un cache intelligent : si aucun paramètre de simulation n'a changé
    et que le recalcul n'est pas forcé, restaure instantanément la simulation sauvegardée.
    """
    global _DERNIERE_SIMULATION
    from api.models import Project

    # 1. Identifier le fichier réseau GeoPackage du projet actif
    gpkg_path = None
    project_name = None
    proj = None
    if tenant and hasattr(tenant, "org_id") and tenant.org_id:
        proj = db.query(Project).filter(
            Project.org_id == tenant.org_id,
            Project.is_archived.is_(False)
        ).first()
        if proj:
            project_name = proj.name
            if proj.source_gpkg_key and Path(proj.source_gpkg_key).exists():
                gpkg_path = Path(proj.source_gpkg_key)

    if not gpkg_path:
        proj = db.query(Project).filter(Project.is_archived.is_(False)).first()
        if proj:
            if not project_name:
                project_name = proj.name
            if proj.source_gpkg_key and Path(proj.source_gpkg_key).exists():
                gpkg_path = Path(proj.source_gpkg_key)
        else:
            cand = Path("data/demo_reseau.gpkg")
            if cand.exists():
                gpkg_path = cand
                project_name = "demo_reseau"

    if not gpkg_path or not gpkg_path.exists():
        raise HTTPException(status_code=404, detail="Réseau hydraulique introuvable pour ce projet.")

    # Règle d'ingénierie hydraulique : la sectorisation préalable est obligatoire avant simulation
    if payload.cluster_id is None:
        raise HTTPException(
            status_code=400,
            detail="Règle hydraulique d'ingénierie : La sectorisation préalable en bassins versants d'exutoires est obligatoire avant la simulation SWMM. Veuillez sélectionner un bassin versant à simuler."
        )

    # 2. Empreinte canonique (hash) des paramètres de simulation
    param_hash, params_dict = _generer_cle_cache_simulation(gpkg_path, payload)

    # 3. Vérification du cache intelligent (Idempotence & Restauration)
    if not payload.force_recalculate:
        cached_resultat = _charger_cache_simulation(gpkg_path, payload.cluster_id, param_hash)
        if cached_resultat:
            cached_resultat["source_gpkg"] = str(gpkg_path.resolve())
            cached_resultat["project_name"] = project_name or gpkg_path.stem
            _DERNIERE_SIMULATION = cached_resultat
            logger.info("Simulation SWMM restaurée depuis la sauvegarde (cluster %s, hash %s)", payload.cluster_id, param_hash)
            return _construire_reponse_simulation(cached_resultat, cached=True)

    # 4. Exécution de la simulation SWMM 5.2 complète si paramètres modifiés ou non en cache
    moteur = MoteurSWMM()
    try:
        resultat = moteur.executer_simulation(
            gpkg_path=gpkg_path,
            scenario_key=payload.scenario_key,
            duree_heures=payload.duree_heures,
            pas_routage_sec=payload.pas_routage_sec,
            pente_moyenne_pct=payload.pente_moyenne_pct,
            cluster_id=payload.cluster_id,
            tampon_buffer_m=payload.buffer_m,
            valider_raccordement_deporte=payload.valider_raccordement if payload.valider_raccordement is not None else True,
            typologie_sol=payload.typologie_sol,
            imperv_pct=payload.imperv_pct,
            intensite_max_mmh=payload.intensite_max_mmh,
            station_id=payload.station_id,
            raccordements_orphelins=payload.raccordements_orphelins,
        )
        resultat["source_gpkg"] = str(gpkg_path.resolve())
        resultat["project_name"] = project_name or gpkg_path.stem
        resultat["param_hash"] = param_hash
        _DERNIERE_SIMULATION = resultat

        # 5. Persistance sur disque et en base de données SQLite
        _sauvegarder_simulation(
            db=db,
            gpkg_path=gpkg_path,
            cluster_id=payload.cluster_id,
            param_hash=param_hash,
            params_dict=params_dict,
            resultat=resultat,
            proj=proj,
            tenant=tenant
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
    tenant: Optional[TenantContext] = Depends(get_tenant_context_optional)
):
    """
    Retourne les résultats et cartographies thématiques de la dernière simulation exécutée
    pour le réseau actif. Si la mémoire est vide (ex: redémarrage serveur), charge automatiquement
    la dernière simulation sauvegardée sur disque ou en base de données.
    """
    global _DERNIERE_SIMULATION
    from api.models import Project

    active_gpkg = None
    project_name = None
    proj = None
    if tenant and hasattr(tenant, "org_id") and tenant.org_id:
        try:
            proj = db.query(Project).filter(
                Project.org_id == tenant.org_id,
                Project.is_archived.is_(False)
            ).first()
        except Exception:
            proj = None
        if proj and proj.source_gpkg_key and Path(proj.source_gpkg_key).exists():
            active_gpkg = str(Path(proj.source_gpkg_key).resolve())
            project_name = proj.name
    if not active_gpkg:
        try:
            proj = db.query(Project).filter(Project.is_archived.is_(False)).first()
        except Exception:
            proj = None
        if proj and proj.source_gpkg_key and Path(proj.source_gpkg_key).exists():
            active_gpkg = str(Path(proj.source_gpkg_key).resolve())
            project_name = proj.name
        elif Path("data/demo_reseau.gpkg").exists():
            active_gpkg = str(Path("data/demo_reseau.gpkg").resolve())
            project_name = "demo_reseau"

    # Vérification de la cohérence de _DERNIERE_SIMULATION
    sim_gpkg = _DERNIERE_SIMULATION.get("source_gpkg") if _DERNIERE_SIMULATION else None
    norm_active = str(Path(active_gpkg).resolve()).lower() if active_gpkg else ""
    norm_sim = str(Path(sim_gpkg).resolve()).lower() if sim_gpkg else ""

    if not _DERNIERE_SIMULATION or not _est_simulation_valide(_DERNIERE_SIMULATION) or norm_active != norm_sim:
        # Tenter la restauration depuis la base ou le cache disque
        if active_gpkg and Path(active_gpkg).exists():
            restored = _charger_derniere_simulation_disque_ou_db(Path(active_gpkg), db, proj)
            if restored and _est_simulation_valide(restored):
                restored["source_gpkg"] = str(Path(active_gpkg).resolve())
                restored["project_name"] = project_name or Path(active_gpkg).stem
                _DERNIERE_SIMULATION = restored
            else:
                _DERNIERE_SIMULATION = {}
                return {"status": "none", "message": "Aucune simulation enregistrée pour ce réseau."}
        else:
            _DERNIERE_SIMULATION = {}
            return {"status": "none", "message": "Aucune simulation enregistrée pour ce réseau."}

    return _construire_reponse_simulation(_DERNIERE_SIMULATION, cached=True)


@router.get("/bassin/{cluster_id}")
def get_bassin_simulation(
    cluster_id: str,
    db: Session = Depends(get_db),
    tenant: Optional[TenantContext] = Depends(get_tenant_context_optional)
):
    """
    Retourne la simulation la plus récente enregistrée pour un bassin versant spécifique.
    Supporte la recherche par cluster_id numérique (ex: 92) ou nom (ex: 25_ouvrages_speciaux_348883).
    """
    global _DERNIERE_SIMULATION
    from api.models import Project

    active_gpkg = None
    project_name = None
    proj = None
    if tenant and hasattr(tenant, "org_id") and tenant.org_id:
        try:
            proj = db.query(Project).filter(
                Project.org_id == tenant.org_id,
                Project.is_archived.is_(False)
            ).first()
        except Exception:
            proj = None
        if proj and proj.source_gpkg_key and Path(proj.source_gpkg_key).exists():
            active_gpkg = str(Path(proj.source_gpkg_key).resolve())
            project_name = proj.name
    if not active_gpkg:
        try:
            proj = db.query(Project).filter(Project.is_archived.is_(False)).first()
        except Exception:
            proj = None
        if proj and proj.source_gpkg_key and Path(proj.source_gpkg_key).exists():
            active_gpkg = str(Path(proj.source_gpkg_key).resolve())
            project_name = proj.name
        elif Path("data/demo_reseau.gpkg").exists():
            active_gpkg = str(Path("data/demo_reseau.gpkg").resolve())
            project_name = "demo_reseau"

    if not active_gpkg or not Path(active_gpkg).exists():
        return {"status": "none", "message": "Aucun réseau actif."}

    gpkg_path = Path(active_gpkg)
    cache_dir = gpkg_path.parent / ".simulation_cache"
    clean_stem = re.sub(r'[^\w\-]+', '_', gpkg_path.stem)

    if cache_dir.exists():
        clean_cid = str(cluster_id).strip().lower()
        all_files = list(cache_dir.glob(f"sim_{clean_stem}_cluster_*.json"))
        
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
            recent_files = sorted(all_files, key=lambda x: x.stat().st_mtime, reverse=True)[:35]
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
                if data and _est_simulation_valide(data):
                    data["source_gpkg"] = str(gpkg_path.resolve())
                    data["project_name"] = project_name or gpkg_path.stem
                    _DERNIERE_SIMULATION = data
                    return _construire_reponse_simulation(data, cached=True)
            except Exception:
                continue

    return {"status": "none", "message": f"Aucune simulation enregistrée pour le bassin {cluster_id}."}


@router.post("/validate-buffer")
def validate_simulation_buffer(
    payload: ValidateBufferRequest,
    db: Session = Depends(get_db),
    tenant: Optional[TenantContext] = Depends(get_tenant_context_optional)
):
    """
    Valide et enregistre le choix du buffer Voronoï (ex. 35m, 45m ou 60m)
    retenu par l'utilisateur suite à l'analyse de sensibilité.
    """
    global _DERNIERE_SIMULATION
    if _DERNIERE_SIMULATION:
        if "buffer_sensitivity" in _DERNIERE_SIMULATION and _DERNIERE_SIMULATION["buffer_sensitivity"]:
            _DERNIERE_SIMULATION["buffer_sensitivity"]["active_buffer_m"] = payload.buffer_m
        if "meta" in _DERNIERE_SIMULATION:
            _DERNIERE_SIMULATION["meta"]["buffer_m"] = payload.buffer_m

    return {
        "status": "success",
        "validated_buffer_m": payload.buffer_m,
        "message": f"Buffer Voronoï {payload.buffer_m}m validé avec succès comme référence du projet."
    }


@router.get("/agents/interpretation")
def get_agents_interpretation():
    """
    Retourne le diagnostic causal complet et les prescriptions de l'équipe
    multi-agents d'expertise pour la dernière simulation.
    """
    global _DERNIERE_SIMULATION
    if not _DERNIERE_SIMULATION or "agents_expertise" not in _DERNIERE_SIMULATION:
        raise HTTPException(
            status_code=404,
            detail="Aucune simulation active disponible pour l'équipe multi-agents. Veuillez lancer une simulation."
        )
    return {
        "status": "success",
        "agents_expertise": _DERNIERE_SIMULATION.get("agents_expertise", {}),
        "buffer_sensitivity": _DERNIERE_SIMULATION.get("buffer_sensitivity", {}),
        "meta": _DERNIERE_SIMULATION.get("meta", {}),
        "kpis": {
            "routing_continuity_error_pct": _DERNIERE_SIMULATION.get("routing_continuity_error_pct"),
            "peak_outflow_m3s": _DERNIERE_SIMULATION.get("peak_outflow_m3s"),
            "total_outflow_m3": _DERNIERE_SIMULATION.get("total_outflow_m3"),
            "flooded_nodes_count": _DERNIERE_SIMULATION.get("flooded_nodes_count", 0),
            "surcharged_nodes_count": _DERNIERE_SIMULATION.get("surcharged_nodes_count", 0),
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
    db: Session = Depends(get_db),
    tenant: Optional[TenantContext] = Depends(get_tenant_context_optional)
):
    """Télécharge le fichier d'entrée (.inp) généré pour le bassin ou la dernière simulation."""
    from api.models import Project

    content = None
    bassin_nom = None
    nom_reseau = None

    active_gpkg = None
    if db and tenant and hasattr(tenant, "org_id") and tenant.org_id:
        proj = db.query(Project).filter(Project.org_id == tenant.org_id, Project.is_archived.is_(False)).first()
        if proj and proj.source_gpkg_key and Path(proj.source_gpkg_key).exists():
            active_gpkg = Path(proj.source_gpkg_key)
            nom_reseau = proj.name
    if not active_gpkg and db:
        proj = db.query(Project).filter(Project.is_archived.is_(False)).first()
        if proj and proj.source_gpkg_key and Path(proj.source_gpkg_key).exists():
            active_gpkg = Path(proj.source_gpkg_key)
            nom_reseau = proj.name
    if not active_gpkg and Path("data/demo_reseau.gpkg").exists():
        active_gpkg = Path("data/demo_reseau.gpkg")
        nom_reseau = "demo_reseau"

    # 1. Vérifier si _DERNIERE_SIMULATION correspond
    if _DERNIERE_SIMULATION and _est_simulation_valide(_DERNIERE_SIMULATION):
        cur_cid = str(_DERNIERE_SIMULATION.get("meta", {}).get("cluster_id") or "").lower()
        cur_cnom = str(_DERNIERE_SIMULATION.get("meta", {}).get("cluster_nom") or "").lower()
        cur_bnom = str(_DERNIERE_SIMULATION.get("meta", {}).get("bassin_nom") or "").lower()
        target = str(cluster_id).strip().lower() if cluster_id else None

        if not target or target in (cur_cid, cur_cnom, cur_bnom):
            content = _DERNIERE_SIMULATION.get("inp_content")
            bassin_nom = _DERNIERE_SIMULATION.get("meta", {}).get("bassin_nom") or _DERNIERE_SIMULATION.get("meta", {}).get("cluster_nom")
            if not nom_reseau:
                nom_reseau = _DERNIERE_SIMULATION.get("project_name")

    # 2. Si cluster_id demandé mais non dans _DERNIERE_SIMULATION, chercher dans le cache
    if not content and cluster_id and active_gpkg:
        c_dir = active_gpkg.parent / ".simulation_cache"
        clean_stem = re.sub(r'[^\w\-]+', '_', active_gpkg.stem)
        clean_cid = str(cluster_id).strip().lower()
        if c_dir.exists():
            for cand in sorted(c_dir.glob(f"sim_{clean_stem}_cluster_*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
                if f"_{clean_cid}_" in cand.name.lower() or f"_cluster_{clean_cid}_" in cand.name.lower():
                    try:
                        with open(cand, "r", encoding="utf-8") as cf:
                            cd = json.load(cf)
                        if _est_simulation_valide(cd) and cd.get("inp_content"):
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
    db: Session = Depends(get_db),
    tenant: Optional[TenantContext] = Depends(get_tenant_context_optional)
):
    """Télécharge le rapport officiel (.rpt) généré par la simulation."""
    from api.models import Project

    content = None
    bassin_nom = None
    nom_reseau = None

    active_gpkg = None
    if db and tenant and hasattr(tenant, "org_id") and tenant.org_id:
        proj = db.query(Project).filter(Project.org_id == tenant.org_id, Project.is_archived.is_(False)).first()
        if proj and proj.source_gpkg_key and Path(proj.source_gpkg_key).exists():
            active_gpkg = Path(proj.source_gpkg_key)
            nom_reseau = proj.name
    if not active_gpkg and db:
        proj = db.query(Project).filter(Project.is_archived.is_(False)).first()
        if proj and proj.source_gpkg_key and Path(proj.source_gpkg_key).exists():
            active_gpkg = Path(proj.source_gpkg_key)
            nom_reseau = proj.name
    if not active_gpkg and Path("data/demo_reseau.gpkg").exists():
        active_gpkg = Path("data/demo_reseau.gpkg")
        nom_reseau = "demo_reseau"

    # 1. Vérifier si _DERNIERE_SIMULATION correspond
    if _DERNIERE_SIMULATION and _est_simulation_valide(_DERNIERE_SIMULATION):
        cur_cid = str(_DERNIERE_SIMULATION.get("meta", {}).get("cluster_id") or "").lower()
        cur_cnom = str(_DERNIERE_SIMULATION.get("meta", {}).get("cluster_nom") or "").lower()
        cur_bnom = str(_DERNIERE_SIMULATION.get("meta", {}).get("bassin_nom") or "").lower()
        target = str(cluster_id).strip().lower() if cluster_id else None

        if not target or target in (cur_cid, cur_cnom, cur_bnom):
            content = _DERNIERE_SIMULATION.get("rpt_content")
            bassin_nom = _DERNIERE_SIMULATION.get("meta", {}).get("bassin_nom") or _DERNIERE_SIMULATION.get("meta", {}).get("cluster_nom")
            if not nom_reseau:
                nom_reseau = _DERNIERE_SIMULATION.get("project_name")

    # 2. Si cluster_id demandé mais non dans _DERNIERE_SIMULATION, chercher dans le cache
    if not content and cluster_id and active_gpkg:
        c_dir = active_gpkg.parent / ".simulation_cache"
        clean_stem = re.sub(r'[^\w\-]+', '_', active_gpkg.stem)
        clean_cid = str(cluster_id).strip().lower()
        if c_dir.exists():
            for cand in sorted(c_dir.glob(f"sim_{clean_stem}_cluster_*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
                if f"_{clean_cid}_" in cand.name.lower() or f"_cluster_{clean_cid}_" in cand.name.lower():
                    try:
                        with open(cand, "r", encoding="utf-8") as cf:
                            cd = json.load(cf)
                        if _est_simulation_valide(cd) and cd.get("rpt_content"):
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
# ROUTES PARAMÉTRÉES /{simulation_id} (Placées à la fin)
# ============================================================

@router.get("/{simulation_id}", response_model=schemas.SimulationResponse)
def get_simulation(
    simulation_id: str,
    db: Session = Depends(get_db),
    tenant: Optional[TenantContext] = Depends(get_tenant_context_optional),
):
    """Récupère une simulation par ID."""
    org_id = tenant.org.id if tenant else None
    sim = crud.get_simulation(db, simulation_id, org_id=org_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation non trouvée")
    return sim.to_dict()


@router.get("/job/{job_id}", response_model=schemas.SimulationResponse)
def get_simulation_by_job(
    job_id: str,
    db: Session = Depends(get_db),
    tenant: Optional[TenantContext] = Depends(get_tenant_context_optional),
):
    """Récupère une simulation par job_id (Celery)."""
    org_id = tenant.org.id if tenant else None
    sim = crud.get_simulation_by_job_id(db, job_id, org_id=org_id)
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
    tenant: Optional[TenantContext] = Depends(get_tenant_context_optional),
):
    """Liste des simulations d'un cluster."""
    org_id = tenant.org.id if tenant else None
    sims = crud.get_simulations(
        db=db,
        status=status,
        skip=skip,
        limit=limit,
        org_id=org_id,
    )
    return [s.to_dict() for s in sims if (s.summary_kpis or {}).get("cluster_id") == cluster_id]


@router.get("/status/{job_id}", response_model=schemas.SimulationStatusResponse)
def get_simulation_status(
    job_id: str,
    db: Session = Depends(get_db),
    tenant: Optional[TenantContext] = Depends(get_tenant_context_optional),
):
    """Polling du statut d'une simulation."""
    org_id = tenant.org.id if tenant else None
    sim = crud.get_simulation_by_job_id(db, job_id, org_id=org_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Job non trouvé")

    response = {
        "job_id": job_id,
        "status": sim.status
    }

    if sim.status.lower() == "completed":
        response["result_url"] = f"/api/v1/artifacts/download?key={sim.results_s3_key}"
    elif sim.status.lower() == "failed":
        response["error"] = (sim.summary_kpis or {}).get("error", "Simulation failed")

    return response


@router.delete("/{simulation_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_simulation(
    simulation_id: str,
    db: Session = Depends(get_db),
    tenant: Optional[TenantContext] = Depends(get_tenant_context_optional),
):
    """Annule une simulation en attente (pending/running)."""
    org_id = tenant.org.id if tenant else None
    sim = crud.get_simulation(db, simulation_id, org_id=org_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation non trouvée")

    if sim.status.lower() not in ["pending", "running"]:
        raise HTTPException(status_code=400, detail="Impossible d'annuler: statut final")

    sim.status = "cancelled"
    db.commit()

    return None


