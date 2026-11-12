"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Tâches asynchrones de simulation hydraulique SWMM
================================================================================

LOT 3C.7.3/3C.7.5 — ce worker est un simple ADAPTATEUR d'orchestration :
il ne contient aucune logique hydraulique. L'exécution est intégralement
déléguée à `SimulationService.executer_en_async` (même MoteurSWMM/PySWMM,
même constructeur INP, même GPKG versionné, même ResultStore que le
chemin synchrone POST /simulations/run).

Les anciens helpers `_build_swmm_inp_content`, `_execute_swmm_solver`,
`_parse_swmm_report` et `SolveurSWMMIndisponible` ont été supprimés :
ils constituaient une seconde implémentation (INP minimal sans section
pluie, solveur externe swmm5, repli synthétique) incompatible avec le
contrat scientifique du projet.
"""

import logging
from typing import Optional, Dict, Any

from api.database import SessionLocal
from api.core.jobs import update_job
from workers.celery_app import celery_app

logger = logging.getLogger("swmm_platform.workers.swmm")


@celery_app.task(bind=True, name="workers.tasks.swmm_tasks.run_swmm_simulation_task")
def run_swmm_simulation_task(
    self,
    job_id: str,
    org_id: str,
    network_id: Optional[str] = None,
    scenario_pluie: str = "pluie_decennale",
    duree_heures: float = 24.0,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Exécute une simulation SWMM complète en tâche de fond.

    `network_id` = identifiant du projet (Network = Project).
    Toute la logique métier est déléguée à SimulationService ; ce worker
    ne gère que le cycle de vie du Job et la propagation des erreurs.
    """
    params = parameters or {}
    db = SessionLocal()

    logger.info("Démarrage de la simulation SWMM: job_id=%s, org_id=%s, network_id=%s", job_id, org_id, network_id)

    try:
        # Étape 0 : Cohérence des identifiants transmis par la route
        params_project_id = params.get("project_id")
        params_simulation_id = params.get("simulation_id")
        if params_project_id and network_id and str(params_project_id) != str(network_id):
            raise ValueError(
                f"Incohérence d'identité : project_id={params_project_id} "
                f"ne correspond pas à network_id={network_id} (job {job_id})"
            )
        if params_simulation_id and str(params_simulation_id) != str(job_id):
            raise ValueError(
                f"Incohérence d'identité : simulation_id={params_simulation_id} "
                f"ne correspond pas au job {job_id}"
            )

        # Étape 1 : Initialisation
        update_job(
            db,
            job_id,
            progress=10,
            status="running",
            message="Chargement des données du réseau et validation topologique...",
        )

        # Étapes 2 à 5 : DÉLÉGATION au service métier unique.
        # Le worker est un simple adaptateur d'orchestration : identité,
        # GPKG versionné, scénario BMS, MoteurSWMM/PySWMM, cache et
        # ResultStore sont entièrement pris en charge par SimulationService.
        # AUCUNE logique hydraulique, construction INP ou solveur direct
        # ne doit subsister ici.
        params.setdefault("scenario_pluie", scenario_pluie)
        params.setdefault("duree_heures", duree_heures)

        update_job(
            db,
            job_id,
            progress=45,
            message="Résolution du contexte organisation/projet et du GPKG versionné...",
        )

        from api.services.simulation_service import executer_en_async
        update_job(
            db,
            job_id,
            progress=65,
            message="Exécution du moteur EPA SWMM via PySWMM (SimulationService)...",
        )

        execution = executer_en_async(
            db=db,
            org_id=org_id,
            project_id=network_id or params.get("project_id"),
            cluster_id=params.get("cluster_id"),
            parameters=params,
            simulation_id=job_id,
        )

        # Étape 6 : Clôture du Job avec succès
        result_payload = {
            "simulation_id": job_id,
            "project_id": execution.get("project_id"),
            "cluster_id": execution.get("cluster_id"),
            "param_hash": execution.get("param_hash"),
            "gpkg": execution.get("gpkg"),
            "result_key": (execution.get("result_store") or {}).get("result_key"),
            "result_store": execution.get("result_store"),
            "peak_outflow_m3s": execution.get("peak_outflow_m3s"),
            "execution_time_seconds": execution.get("execution_time_seconds"),
        }

        update_job(
            db,
            job_id,
            progress=100,
            status="completed",
            message="Simulation hydraulique SWMM terminée avec succès.",
            result_refs=result_payload,
        )

        logger.info(
            "Simulation SWMM réussie: job_id=%s, durée=%ss",
            job_id, execution.get("execution_time_seconds"),
        )
        return result_payload

    except Exception as e:
        logger.exception("Échec simulation SWMM job_id=%s : %s", job_id, e)
        error_msg = str(e)
        update_job(
            db,
            job_id,
            status="failed",
            message=f"Échec de la simulation SWMM : {error_msg[:200]}",
            error_message=error_msg,
        )
        raise
    finally:
        db.close()
