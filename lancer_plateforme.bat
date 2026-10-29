@echo off
chcp 65001 > nul
echo ======================================================================
echo          SWMM PLATFORM SAAS - SERVEUR FASTAPI UNIFIÉ
echo ======================================================================
echo.
echo  Interface Cockpit & Cartographie : http://127.0.0.1:5002/
echo  Documentation Swagger interactive : http://127.0.0.1:5002/docs
echo  Audit & Diagnostic Qualité Réseau : http://127.0.0.1:5002/qualite
echo  Visualisation SIG Multi-Couches  : http://127.0.0.1:5002/map
echo  Carte Opérationnelle d'Édition   : http://127.0.0.1:5002/carte
echo  Tunnel de Workflow Guidé          : http://127.0.0.1:5002/tunnel
echo.
echo ======================================================================
echo  Démarrage du serveur Uvicorn... (Ctrl+C pour arrêter)
echo ======================================================================
.venv\Scripts\python.exe run_api.py
pause
