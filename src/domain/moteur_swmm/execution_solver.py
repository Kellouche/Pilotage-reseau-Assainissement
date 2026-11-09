# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Exécution du solveur hydrodynamique EPA SWMM 5.2 via pyswmm
================================================================================
"""

import os
import tempfile
import logging
from typing import Tuple

try:
    from pyswmm import Simulation
except ImportError:
    Simulation = None

logger = logging.getLogger("swmm_platform.moteur_swmm.execution_solver")


def executer_solver_swmm(inp_content: str, return_timeseries: bool = False):
    """
    Écrit le fichier .inp temporaire, invoque pyswmm.Simulation et lit le rapport .rpt.
    Si return_timeseries=True, extrait également les données dynamiques du .out pour le Time Slider.
    Retourne (rpt_content, tmp_inp_path) ou (rpt_content, tmp_inp_path, timeseries_data).
    Nettoie les fichiers temporaires associés (.inp, .rpt, .out).
    """
    with tempfile.NamedTemporaryFile(suffix=".inp", mode="w", delete=False, encoding="utf-8") as f:
        f.write(inp_content)
        tmp_inp = f.name

    rpt_path = tmp_inp.replace(".inp", ".rpt")
    out_path = tmp_inp.replace(".inp", ".out")

    if Simulation is None:
        raise RuntimeError(
            "Le solveur EPA SWMM 5.2 requiert le package 'pyswmm'. "
            "Veuillez lancer le serveur avec l'environnement virtuel du projet : "
            ".venv\\Scripts\\python.exe run_server.py (ou run_api.py)."
        )

    timeseries_data = None
    try:
        logger.info("Lancement du moteur EPA SWMM 5.2 via pyswmm sur %s", tmp_inp)
        with Simulation(tmp_inp) as sim:
            try:
                sim.execute()
            except Exception:
                for _ in sim:
                    pass

        rpt_text = ""
        if os.path.exists(rpt_path):
            with open(rpt_path, "r", encoding="utf-8", errors="ignore") as rf:
                rpt_text = rf.read()

        # Extraction des séries temporelles (Phase 6.B) avant suppression du fichier binaire .out
        if return_timeseries and os.path.exists(out_path):
            try:
                from src.domain.moteur_swmm.timeseries_extractor import extraire_series_temporelles
                timeseries_data = extraire_series_temporelles(out_path)
            except Exception as e_ts:
                logger.warning("Impossible d'extraire les séries temporelles: %s", e_ts)
                timeseries_data = {"status": "ERROR", "error": str(e_ts), "steps": []}

        if return_timeseries:
            return rpt_text, tmp_inp, timeseries_data
        return rpt_text, tmp_inp

    finally:
        for p in [tmp_inp, rpt_path, out_path]:
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except Exception:
                    pass

