"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Tâches asynchrones de simulation hydraulique SWMM
================================================================================
"""

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from sqlalchemy import select

from api.database import SessionLocal
from api.models import Job, Simulation, Regard, Canalisation, Rejet, Project
from api.core.jobs import update_job
from api.core.storage import get_storage, build_swmm_inp_key, build_simulation_result_key
from workers.celery_app import celery_app

logger = logging.getLogger("swmm_platform.workers.swmm")


class SolveurSWMMIndisponible(RuntimeError):
    """
    Levée quand le solveur EPA SWMM ne peut pas produire un résultat réel.

    Distingue explicitement :
    - binaire SWMM absent ou non exécutable ;
    - binaire inaccessible (erreur OS à l'exécution) ;
    - échec d'exécution du solveur (code retour non nul) ;
    - absence ou erreur de lecture du rapport .rpt produit.

    AUCUN repli synthétique : cette exception ne doit jamais être
    transformée en résultat COMPLETED.
    """


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


def _build_swmm_inp_content(
    title: str,
    regards: list,
    conduites: list,
    duree_heures: float,
    parameters: dict,
) -> str:
    """Construit un modèle SWMM .inp valide et structuré."""
    lines = [
        "[TITLE]",
        title,
        "",
        "[OPTIONS]",
        "FLOW_UNITS          CMS",
        "INFILTRATION        HORTON",
        "FLOW_ROUTING        DYNWAVE",
        "START_DATE          01/01/2026",
        "START_TIME          00:00:00",
        "REPORT_START_DATE   01/01/2026",
        "REPORT_START_TIME   00:00:00",
        f"END_DATE            01/{max(1, min(28, int(duree_heures // 24) + 1)):02d}/2026",
        f"END_TIME            {int(duree_heures % 24):02d}:00:00",
        "REPORT_STEP         00:05:00",
        "WET_STEP            00:01:00",
        "DRY_STEP            01:00:00",
        "ROUTING_STEP        00:00:10",
        "ALLOW_PONDING       YES",
        "INERTIAL_DAMPING    PARTIAL",
        "VARIABLE_STEP       0.75",
        "LENGTHENING_STEP    0",
        "MIN_SURFAREA        1.167",
        "NORMAL_FLOW_LIMITED BOTH",
        "SKIP_STEADY_STATE   NO",
        "",
        "[JUNCTIONS]",
        ";;Name           Elevation  MaxDepth   InitDepth  SurDepth   Aponded   ",
    ]

    known_nodes = set()
    for r in regards:
        code = str(r.code).strip()
        known_nodes.add(code)
        elev = float(r.profrad if r.profrad is not None else 0.0)
        max_d = float(r.profondeur if r.profondeur is not None else 2.0)
        lines.append(f"{code:<16} {elev:<10.3f} {max_d:<10.3f} 0.000      0.000      0.000")

    # Si aucune regard n'a été spécifié, créer un nœud factice
    if not regards:
        lines.append(f"{'J1':<16} 10.000     2.500      0.000      0.000      0.000")
        known_nodes.add("J1")

    lines.extend([
        "",
        "[OUTFALLS]",
        ";;Name           Elevation  Type       Stage Data       Gated    Route To",
        f"{'OUT1':<16} 0.000      FREE                        NO",
        "",
        "[CONDUITS]",
        ";;Name           From Node        To Node          Length     Roughness  InOffset   OutOffset  InitFlow   MaxFlow   ",
    ])

    for idx, c in enumerate(conduites):
        cid = str(c.id or f"C{idx+1}").strip()
        amont = str(c.id_amont).strip() if c.id_amont else "J1"
        aval = str(c.id_aval).strip() if c.id_aval else "OUT1"
        length = float(c.longueur if c.longueur is not None else 50.0)
        rugosite = 0.013  # Béton lisse / PVC
        lines.append(f"{cid:<16} {amont:<16} {aval:<16} {length:<10.2f} {rugosite:<10.4f} 0.0000     0.0000     0.0000     0.0000")

    if not conduites:
        lines.append(f"{'C1':<16} {'J1':<16} {'OUT1':<16} 100.00     0.0130     0.0000     0.0000     0.0000     0.0000")

    lines.extend([
        "",
        "[XSECTIONS]",
        ";;Link           Shape        Geom1      Geom2      Geom3      Geom4      Barrels    Culvert   ",
    ])
    for idx, c in enumerate(conduites):
        cid = str(c.id or f"C{idx+1}").strip()
        diam = float(c.diametre if c.diametre is not None else 0.4)
        if diam > 10.0:  # conversion mm -> m si nécessaire
            diam = diam / 1000.0
        lines.append(f"{cid:<16} CIRCULAR     {diam:<10.3f} 0.000      0.000      0.000      1")

    if not conduites:
        lines.append(f"{'C1':<16} CIRCULAR     0.500      0.000      0.000      0.000      1")

    lines.extend([
        "",
        "[REPORT]",
        "INPUT      NO",
        "CONTINUITY YES",
        "FLOWSTATS  YES",
        "NODESTATS  YES",
        "LINKS      ALL",
        "NODES      ALL",
        "",
        "[END]",
    ])

    return "\n".join(lines)


def _execute_swmm_solver(
    inp_content: str,
    regards: list,
    conduites: list,
    duree_heures: float,
    scenario_pluie: str,
    parameters: dict,
) -> tuple[Dict[str, Any], str]:
    """
    Exécute le solveur externe EPA SWMM via le binaire swmm5.

    AUCUN repli synthétique : toute indisponibilité ou erreur du solveur
    lève SolveurSWMMIndisponible — jamais de KPIs ni de RPT fabriqués.
    """
    swmm_bin = parameters.get("swmm_bin") or os.environ.get("SWMM_BINARY_PATH") or "swmm5"
    resolved_bin = shutil.which(swmm_bin)
    if resolved_bin is None:
        raise SolveurSWMMIndisponible(
            f"Binaire SWMM introuvable ou non exécutable : '{swmm_bin}'. "
            "Définissez la variable d'environnement SWMM_BINARY_PATH "
            "ou placez le solveur EPA SWMM dans le PATH."
        )

    with tempfile.TemporaryDirectory() as tmp_dir:
        inp_path = os.path.join(tmp_dir, "model.inp")
        rpt_path = os.path.join(tmp_dir, "model.rpt")
        out_path = os.path.join(tmp_dir, "model.out")

        with open(inp_path, "w", encoding="utf-8") as f:
            f.write(inp_content)

        cmd = [resolved_bin, inp_path, rpt_path, out_path]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
        except subprocess.TimeoutExpired as exc:
            raise SolveurSWMMIndisponible(
                f"Le solveur SWMM a dépassé le délai d'exécution (1200 s) : {resolved_bin}"
            ) from exc
        except OSError as exc:
            raise SolveurSWMMIndisponible(
                f"Binaire SWMM inaccessible à l'exécution : {resolved_bin} ({exc})"
            ) from exc

        if proc.returncode != 0:
            raise SolveurSWMMIndisponible(
                f"Échec d'exécution du solveur SWMM (code retour {proc.returncode}) : "
                f"{(proc.stderr or proc.stdout or '').strip()[:500]}"
            )

        if not os.path.exists(rpt_path):
            raise SolveurSWMMIndisponible(
                "Le solveur SWMM s'est terminé sans produire le rapport .rpt attendu."
            )

        try:
            with open(rpt_path, "r", encoding="utf-8", errors="replace") as f:
                rpt_content = f.read()
        except OSError as exc:
            raise SolveurSWMMIndisponible(
                f"Erreur de lecture du rapport SWMM produit ({rpt_path}) : {exc}"
            ) from exc

        kpis = _parse_swmm_report(rpt_content)
        kpis["provenance"] = {
            "nature": "REAL",
            "engine": "EPA SWMM",
            "engine_version": kpis.get("engine_version"),
            "execution_mode": "celery",
            "executed_at_utc": datetime.now(timezone.utc).isoformat(),
            "swmm_binary": resolved_bin,
            "inp_sha256": hashlib.sha256(inp_content.encode("utf-8")).hexdigest(),
            "inp_size_bytes": len(inp_content.encode("utf-8")),
        }
        return kpis, rpt_content


def _extraire_version_rpt_swmm(report_text: str) -> Optional[str]:
    """Extrait la version EPA SWMM depuis l'en-tête du rapport .rpt."""
    if not report_text:
        return None
    m = re.search(r"VERSION\s+([0-9]+(?:\.[0-9]+)*)", report_text[:2000], re.IGNORECASE)
    return m.group(1) if m else None


def _parse_swmm_report(report_text: str) -> Dict[str, Any]:
    """Parse le rapport .rpt produit par le solveur EPA SWMM."""
    engine_version = _extraire_version_rpt_swmm(report_text)
    kpis = {
        "engine": "EPA SWMM",
        "engine_version": engine_version or "inconnue",
        "total_inflow_m3": 0.0,
        "total_outflow_m3": 0.0,
        "continuity_error_pct": 0.0,
        "peak_flow_m3s": 0.0,
        "flooding_nodes_count": 0,
        "surcharged_pipes_count": 0,
    }

    for line in report_text.splitlines():
        line_clean = line.strip()
        if "Total Inflow" in line_clean:
            parts = line_clean.split()
            try:
                kpis["total_inflow_m3"] = float(parts[-1])
            except (ValueError, IndexError):
                pass
        elif "Total Outflow" in line_clean:
            parts = line_clean.split()
            try:
                kpis["total_outflow_m3"] = float(parts[-1])
            except (ValueError, IndexError):
                pass
        elif "Continuity Error (%)" in line_clean:
            parts = line_clean.split()
            try:
                kpis["continuity_error_pct"] = float(parts[-1])
            except (ValueError, IndexError):
                pass

    return kpis
