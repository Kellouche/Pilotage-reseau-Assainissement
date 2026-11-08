#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Script principal de démarrage du serveur Uvicorn DrainPilot 5.2
================================================================================
"""

import os
import sys
import argparse
import logging

# Prévention des allocations concurrentes OpenBLAS sous Windows
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

import subprocess
import time
import uvicorn
from config.settings import API_HOST, API_PORT

def kill_process_on_port(port, silent=False):
    """Cherche et tue le processus écoutant sur le port donné (Windows)."""
    try:
        output = subprocess.check_output(['netstat', '-ano']).decode('utf-8', errors='ignore')
        killed_pids = set()
        for line in output.splitlines():
            if f":{port}" in line and 'LISTENING' in line:
                parts = line.split()
                pid = parts[-1]
                if pid != "0" and pid not in killed_pids:
                    if not silent:
                        print(f"Port {port} déjà utilisé par le PID {pid}. Fermeture forcée de l'arbre de processus...")
                    subprocess.call(['taskkill', '/F', '/T', '/PID', pid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    killed_pids.add(pid)
        
        if killed_pids:
            time.sleep(2)  # Laisser le temps à l'OS de libérer le port
    except Exception as e:
        if not silent:
            print(f"Impossible de vérifier/tuer le port {port} : {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Serveur API DrainPilot SWMM Platform")
    parser.add_argument("--silent", "-s", "--quiet", "-q", action="store_true",
                        help="Démarrer en mode silencieux (désactive les access logs et le flood console)")
    args, unknown = parser.parse_known_args()

    # Détection mode silencieux via flag ou variable d'environnement
    is_silent = args.silent or (os.getenv("DRAINPILOT_SILENT", "").lower() in ("1", "true", "yes"))
    if is_silent:
        os.environ["DRAINPILOT_SILENT"] = "1"
        # Ajuster les loggers Python
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

    kill_process_on_port(API_PORT, silent=is_silent)

    if is_silent:
        print(f"[DrainPilot] 🚀 Serveur démarré en mode SILENCIEUX sur http://{API_HOST}:{API_PORT} (Ctrl+C pour arrêter)")
    else:
        print("=" * 60)
        print("Démarrage DrainPilot - API Server (Mode Résilient)")
        print(f"  URL: http://{API_HOST}:{API_PORT}")
        print(f"  Docs: http://{API_HOST}:{API_PORT}/docs")
        print("  Mode verbeux actif (utiliser --silent pour le mode silencieux)")
        print("  Appuyez sur Ctrl+C pour arrêter")
        print("=" * 60)

    import contextlib
    @contextlib.contextmanager
    def no_capture():
        yield

    while True:
        try:
            reload_mode = os.getenv("API_RELOAD", "true").lower() in ("true", "1", "yes")
            log_level = "warning" if is_silent else "info"
            access_log = not is_silent

            config = uvicorn.Config(
                "api.main:app",
                host=API_HOST,
                port=API_PORT,
                reload=reload_mode,
                log_level=log_level,
                access_log=access_log
            )
            server = uvicorn.Server(config)
            server.capture_signals = no_capture
            server.run()
            break
        except KeyboardInterrupt:
            print("\n[INFO] Serveur arrêté proprement par l'utilisateur.")
            break
        except Exception as e:
            if not is_silent:
                print(f"\n[WARN] Relance du serveur suite à incident: {e}")
            kill_process_on_port(API_PORT, silent=is_silent)
            time.sleep(1)
