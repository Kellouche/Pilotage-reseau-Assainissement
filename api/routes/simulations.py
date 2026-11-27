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


# Logique métier (cache, persistance, réponse, moteur) : api/services/simulation_service.py
# Endpoints /run et /latest : api/routes/simulations_run.py
# Endpoints /bassin/*, /validate-buffer, /agents, /cotes-suspectes : api/routes/simulations_bassin.py
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


# Endpoints extraits : /run et /latest (simulations_run), /bassin/*,
# /validate-buffer, /agents/interpretation, /cotes-suspectes (simulations_bassin)
from api.routes.simulations_run import (  # noqa: F401
    SimulationRunRequest,
    run_native_swmm_simulation,
    get_latest_simulation,
)
from api.routes.simulations_bassin import (  # noqa: F401
    ValidateBufferRequest,
    CoteValidationItem,
    CotesValidationPayload,
    get_bassin_simulation,
    list_bassin_simulations_historique,
    validate_simulation_buffer,
    get_agents_interpretation,
    lister_cotes_suspectes_endpoint,
    valider_cotes_suspectes_endpoint,
)
# Alias service historiques (tests et imports existants)
from api.services.simulation_service import (  # noqa: F401
    construire_reponse_simulation as _construire_reponse_simulation,
    executer_moteur_swmm as _executer_moteur_swmm,
)
