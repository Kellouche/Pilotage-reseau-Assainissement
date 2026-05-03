"""
Worker Celery pour exécuter les simulations SWMM en arrière-plan.
Pour POC : peut aussi fonctionner en threading simple si Celery non dispo.
"""

import os
import subprocess
import json
from pathlib import Path
from datetime import datetime

import logging

logger = logging.getLogger(__name__)


def run_swmm_simulation(job_id: str, cluster_id: int, parameters: dict = None):
    """
    Exécute une simulation SWMM pour un cluster donné.

    Args:
        job_id: identifiant unique du job
        cluster_id: ID du cluster dans la DB
        parameters: dict avec options SWMM (start_time, end_time, etc.)

    Returns:
        dict avec résultats synthétiques
    """
    try:
        logger.info(f"[SWMM Worker] Job {job_id}: démarrage pour cluster {cluster_id}")

        # 1. Charger données cluster depuis GeoPackage (ou DB)
        #    Pour POC : appel direct à chargeur_geopackage
        from src.infrastructure.chargeur_geopackage import charger_donnees
        from src.domain.graphe_reseau import construire_graphe
        from src.domain.detecteur_clusters import tracer_cluster_depuis_exutoire

        # 2. Construire graphe + retrouver cluster
        G = construire_graphe()
        # Obtention exutoires
        from src.domain.graphe_reseau import trouver_exutoires
        exutoires = trouver_exutoires(G)

        # Trouver exutoire correspondant au cluster_id (approximatif)
        # Pour POC on simule
        cluster_edges = []
        if exutoires:
            # Prendre le premier exutoire pour test
            exutoire = exutoires[0]
            cluster_edges = tracer_cluster_depuis_exutoire(G, exutoire["noeud"])

        # 3. Générer fichier .inp pour SWMM
        inp_path = f"/tmp/swmm_{job_id}.inp"
        generate_swmm_inp(cluster_edges, inp_path, parameters or {})

        # 4. Exécuter SWMM (subprocess)
        out_path = f"/tmp/swmm_{job_id}.out"
        rpt_path = f"/tmp/swmm_{job_id}.rpt"

        swmm_exe = parameters.get("swmm_path", "swmm5") if parameters else "swmm5"
        cmd = [swmm_exe, inp_path, out_path, rpt_path]

        logger.info(f"[SWMM Worker] Exécution: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            raise RuntimeError(f"SWMM failed: {result.stderr}")

        # 5. Parser output
        results = parse_swmm_output(out_path, rpt_path)

        # 6. Nettoyer fichiers temporaires
        for f in [inp_path, out_path, rpt_path]:
            try:
                os.remove(f)
            except:
                pass

        logger.info(f"[SWMM Worker] Job {job_id}: terminé avec succès")
        return {
            "status": "COMPLETED",
            "results": results
        }

    except subprocess.TimeoutExpired:
        logger.error(f"[SWMM Worker] Job {job_id}: timeout après 300s")
        return {
            "status": "FAILED",
            "error": "Simulation timeout (>5min)"
        }
    except Exception as e:
        logger.exception(f"[SWMM Worker] Job {job_id}: erreur - {e}")
        return {
            "status": "FAILED",
            "error": str(e)
        }


def generate_swmm_inp(cluster_edges, output_path: str, parameters: dict):
    """
    Génère un fichier d'entrée SWMM minimal pour le cluster.
    POC : version ultra-simplifiée.
    """
    with open(output_path, "w") as f:
        f.write("""[TITLE]
SWMM Platform POC - Cluster Simulation

[OPTIONS]
FLOW_UNITS CMS
INFILTRATION NONE
FLOW_ROUTING DYNWAVE
START_DATE 01/01/2026
START_TIME 00:00:00
END_DATE 01/01/2026
END_TIME 24:00:00
REPORT_STEP 00:15:00
WET_STEP 00:05:00
DRY_STEP 01:00:00
ROUTING_STEP 00:05:00
ALLOW_PONDING YES
SKIP_STEADY NO

[SUBCATCHMENTS]
; Sous-bassin dummy (car pas de MNT)
S1 1000 0 0 0

[SUBAREAS]
; (non utilisé)

[INFILTRATION]
; (non utilisé)

[JUNCTIONS]
""")

        # Ajouter regards comme nœuds (junctions)
        nodes_written = set()
        for idx, (amont, aval) in enumerate(cluster_edges):
            # Write outflow node (aval) as junction
            if aval not in nodes_written:
                x, y = aval
                f.write(f"J{idx} {x:.3f} {y:.3f} 0\n")  # elevation réelle à remplir
                nodes_written.add(aval)

        f.write("""
[OUTFALLS]
""")
        # Exutoire (dernier nœud)
        if cluster_edges:
            last_node = list(cluster_edges)[-1][1]  # dernier aval
            x, y = last_node
            f.write(f"OUT1 {x:.3f} {y:.3f} 0 FREE\n")

        f.write("""
[CONDUITS]
""")
        # Toutes les conduites
        for idx, (amont, aval) in enumerate(cluster_edges):
            x1, y1 = amont
            x2, y2 = aval
            length = ((x2-x1)**2 + (y2-y1)**2)**0.5
            f.write(f"C{idx} J{idx} J{idx+1} {length:.2f} 0.5 0 0\n")

        f.write("""
[XSECTIONS]
""")
        for idx in range(len(cluster_edges)):
            f.write(f"C{idx} CIRCULAR 0.5\n")

        f.write("""
[REPORT]
INPUT NO
CONTINUITY YES
FLOWSTATS YES
CONTROL NO

[COORDINATES]
""")
        for idx, (amont, aval) in enumerate(cluster_edges):
            x, y = amont
            f.write(f"J{idx} {x:.3f} {y:.3f}\n")
        # dernier nœud
        if cluster_edges:
            last_node = list(cluster_edges)[-1][1]
            x, y = last_node
            f.write(f"OUT1 {x:.3f} {y:.3f}\n")

        f.write("""
[VERTICES]
""")
        # Pas de vertices pour POC

        f.write("""
[PATTERNS]
; Default pattern
1 1.0 1.0 1.0 1.0 1.0 1.0

[INFLOWS]
""")
        # Inflow factice en tête (pour test)
        f.write("; INFLOW Dummy\n")

        f.write("""
[TAGS]
[END]
""")


def parse_swmm_output(out_path: str, rpt_path: str) -> dict:
    """
    Parse les fichiers de sortie SWMM.
    Retourne un dict avec résultats agrégés.
    """
    results = {
        "simulation_time": None,
        "total_inflow": 0,
        "total_outflow": 0,
        "peak_flow": 0,
        "nodes": [],
        "links": []
    }

    # Parser le rapport (.rpt) - plus facile
    try:
        with open(rpt_path, "r") as f:
            content = f.read()

        # Extraire valeurs depuis sections SWMM
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if "Total Inflow" in line:
                try:
                    # Format typique: "Total Inflow ........... 123.456"
                    val = float(line.split()[-1])
                    results["total_inflow"] = val
                except:
                    pass
            if "Total Outflow" in line:
                try:
                    val = float(line.split()[-1])
                    results["total_outflow"] = val
                except:
                    pass
            if "Maximum Flow" in line:
                try:
                    val = float(line.split()[-1])
                    results["peak_flow"] = val
                except:
                    pass

        results["report_parsed"] = True

    except FileNotFoundError:
        results["error"] = f"Rapport non trouvé: {rpt_path}"
    except Exception as e:
        results["error"] = f"Erreur parsing: {str(e)}"

    return results
