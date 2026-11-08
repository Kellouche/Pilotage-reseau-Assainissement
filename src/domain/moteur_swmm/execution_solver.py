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


def executer_solver_swmm(inp_content: str) -> Tuple[str, str]:
    """
    Écrit le fichier .inp temporaire, invoque pyswmm.Simulation et lit le rapport .rpt.
    Retourne (rpt_content, tmp_inp_path).
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

        return rpt_text, tmp_inp

    finally:
        for p in [tmp_inp, rpt_path, out_path]:
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except Exception:
                    pass

