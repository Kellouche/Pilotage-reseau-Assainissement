#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Lancement du serveur FastAPI pour la plateforme SWMM POC.
"""

import os
import sys
from pathlib import Path
import subprocess

# Auto-redirection vers le virtualenv .venv si exécuté avec le Python système global
venv_python = Path(__file__).parent / ".venv" / "Scripts" / "python.exe"
if venv_python.exists() and Path(sys.executable).resolve() != venv_python.resolve():
    print(f"[Launcher] Environnement virtuel (.venv) détecté. Redirection automatique...")
    sys.exit(subprocess.call([str(venv_python)] + sys.argv))

import uvicorn
from config.settings import API_HOST, API_PORT, API_RELOAD
import time

def kill_process_on_port(port):
    """Cherche et tue le processus écoutant sur le port donné (Windows)."""
    try:
        output = subprocess.check_output(['netstat', '-ano']).decode('utf-8', errors='ignore')
        killed_pids = set()
        for line in output.splitlines():
            if f":{port}" in line and 'LISTENING' in line:
                parts = line.split()
                pid = parts[-1]
                if pid != "0" and pid not in killed_pids:
                    print(f"Port {port} deja utilise par le PID {pid}. Fermeture forcée de l'arbre de processus...")
                    subprocess.call(['taskkill', '/F', '/T', '/PID', pid])
                    killed_pids.add(pid)
        
        if killed_pids:
            time.sleep(2)
    except Exception as e:
        pass

if __name__ == "__main__":
    kill_process_on_port(API_PORT)
    uvicorn.run(
        "api.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=API_RELOAD,
        log_level="info"
    )
