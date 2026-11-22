@echo off
chcp 65001 > nul
echo ======================================================================
echo          DRAINPILOT 5.2 - PLATEFORME FASTAPI UNIFIEE
echo ======================================================================
echo.
echo  Port definie par API_PORT (config/settings.py).
echo  Documentation Swagger : http://127.0.0.1:<API_PORT>/docs
echo.
echo ======================================================================
echo  Demarrage du serveur Uvicorn... (Ctrl+C pour arreter)
echo ======================================================================
.venv\Scripts\python.exe run_api.py
pause
