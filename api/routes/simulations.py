"""
Routes pour les simulations SWMM.
Lancement asynchrone via Celery, suivi de jobs et récupération des résultats.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.orm import Session
from typing import List, Optional, Any, Dict

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
    cluster_id: Optional[int] = None
    pente_moyenne_pct: Optional[float] = 1.0
    buffer_m: Optional[float] = 35.0


class ValidateBufferRequest(BaseModel):
    buffer_m: float = 45.0


@router.get("/scenarios")
def get_simulation_scenarios():
    """Retourne les scénarios de pluie et de sollicitation disponibles."""
    return {
        "scenarios": [
            {
                "key": k,
                "nom": v["nom"],
                "duree_heures": v["duree_heures"],
                "description": v["description"]
            }
            for k, v in SCENARIOS_PLUIE.items()
        ],
        "default_scenario": "pluie_decennale",
        "solver": "EPA SWMM 5.2 Dynamic Wave (DYNWAVE)",
        "infiltration_method": "Horton (f0=75 mm/h, fc=10 mm/h, k=4.0 1/h)",
    }


@router.post("/run")
def run_native_swmm_simulation(
    payload: SimulationRunRequest,
    db: Session = Depends(get_db),
    tenant: Optional[TenantContext] = Depends(get_tenant_context_optional),
):
    """
    Exécute la simulation hydrodynamique EPA SWMM 5.2 native pour le réseau actif.
    Calcule le ruissellement Voronoï, l'infiltration Horton et les équations de Saint-Venant 1D.
    """
    global _DERNIERE_SIMULATION
    from api.models import Project

    # 1. Identifier le fichier réseau GeoPackage du projet actif
    gpkg_path = None
    if tenant and tenant.org_id:
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

    moteur = MoteurSWMM()
    try:
        resultat = moteur.executer_simulation(
            gpkg_path=gpkg_path,
            scenario_key=payload.scenario_key,
            duree_heures=payload.duree_heures,
            pas_routage_sec=payload.pas_routage_sec,
            pente_moyenne_pct=payload.pente_moyenne_pct,
            cluster_id=payload.cluster_id,
            tampon_buffer_m=payload.buffer_m
        )
        resultat["source_gpkg"] = str(gpkg_path.resolve())
        _DERNIERE_SIMULATION = resultat

        return {
            "status": "success",
            "message": "Simulation hydrodynamique SWMM 5.2 exécutée avec succès.",
            "meta": resultat.get("meta", {}),
            "kpis": {
                "routing_continuity_error_pct": resultat.get("routing_continuity_error_pct"),
                "runoff_continuity_error_pct": resultat.get("runoff_continuity_error_pct"),
                "total_precipitation_mm": resultat.get("total_precipitation_mm"),
                "total_outflow_m3": resultat.get("total_outflow_m3"),
                "peak_outflow_m3s": resultat.get("peak_outflow_m3s"),
                "flooded_nodes_count": resultat.get("flooded_nodes_count"),
                "surcharged_nodes_count": resultat.get("surcharged_nodes_count", 0),
                "flooded_nodes": resultat.get("flooded_nodes", [])[:15],
                "compliance_continuity": resultat.get("compliance_continuity", True),
            },
            "buffer_sensitivity": resultat.get("buffer_sensitivity", {}),
            "agents_expertise": resultat.get("agents_expertise", {}),
            "node_results": resultat.get("node_results", {}),
            "conduit_results": resultat.get("conduit_results", {}),
            "download_inp_url": "/api/v1/simulations/download/inp",
            "download_rpt_url": "/api/v1/simulations/download/rpt",
        }
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
    uniquement si elle correspond au réseau actuellement actif.
    """
    global _DERNIERE_SIMULATION
    if not _DERNIERE_SIMULATION or "node_results" not in _DERNIERE_SIMULATION:
        return {"status": "none", "message": "Aucune simulation enregistrée pour ce réseau."}

    from api.models import Project
    active_gpkg = None
    if tenant and tenant.org_id:
        proj = db.query(Project).filter(
            Project.org_id == tenant.org_id,
            Project.is_archived.is_(False)
        ).first()
        if proj and proj.source_gpkg_key and Path(proj.source_gpkg_key).exists():
            active_gpkg = str(Path(proj.source_gpkg_key).resolve())
    if not active_gpkg:
        proj = db.query(Project).filter(Project.is_archived.is_(False)).first()
        if proj and proj.source_gpkg_key and Path(proj.source_gpkg_key).exists():
            active_gpkg = str(Path(proj.source_gpkg_key).resolve())
        elif Path("data/demo_reseau.gpkg").exists():
            active_gpkg = str(Path("data/demo_reseau.gpkg").resolve())

    sim_gpkg = _DERNIERE_SIMULATION.get("source_gpkg")
    if active_gpkg and sim_gpkg and active_gpkg != sim_gpkg:
        # La simulation en mémoire appartenait à un autre modèle/démo
        _DERNIERE_SIMULATION = {}
        return {"status": "none", "message": "Aucune simulation enregistrée pour le réseau actif."}

    resultat = _DERNIERE_SIMULATION
    return {
        "status": "success",
        "meta": resultat.get("meta", {}),
        "kpis": {
            "routing_continuity_error_pct": resultat.get("routing_continuity_error_pct"),
            "runoff_continuity_error_pct": resultat.get("runoff_continuity_error_pct"),
            "total_precipitation_mm": resultat.get("total_precipitation_mm"),
            "total_outflow_m3": resultat.get("total_outflow_m3"),
            "peak_outflow_m3s": resultat.get("peak_outflow_m3s"),
            "flooded_nodes_count": resultat.get("flooded_nodes_count", 0),
            "surcharged_nodes_count": resultat.get("surcharged_nodes_count", 0),
            "flooded_nodes": resultat.get("flooded_nodes", [])[:15],
            "compliance_continuity": resultat.get("compliance_continuity", True),
        },
        "buffer_sensitivity": resultat.get("buffer_sensitivity", {}),
        "agents_expertise": resultat.get("agents_expertise", {}),
        "node_results": resultat.get("node_results", {}),
        "conduit_results": resultat.get("conduit_results", {}),
        "download_inp_url": "/api/v1/simulations/download/inp",
        "download_rpt_url": "/api/v1/simulations/download/rpt",
    }


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



@router.get("/download/inp")
def download_latest_inp():
    """Télécharge le fichier d'entrée (.inp) généré pour la dernière simulation."""
    content = _DERNIERE_SIMULATION.get("inp_content")
    if not content:
        raise HTTPException(status_code=404, detail="Aucun fichier de modèle disponible. Veuillez d'abord exécuter une simulation.")
    return PlainTextResponse(
        content,
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=modele_swmm_52.inp"}
    )


@router.get("/download/rpt")
def download_latest_rpt():
    """Télécharge le rapport officiel (.rpt) généré par la dernière simulation."""
    content = _DERNIERE_SIMULATION.get("rpt_content")
    if not content:
        raise HTTPException(status_code=404, detail="Aucun rapport de simulation disponible. Veuillez d'abord exécuter une simulation.")
    return PlainTextResponse(
        content,
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=rapport_swmm_52.rpt"}
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


