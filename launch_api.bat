@echo off
REM Lancement de la plateforme DrainPilot - API FastAPI

echo.
echo ========================================
echo   DrainPilot 5.2 - API Server
echo ========================================
echo.

REM Vérifier Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python non trouve dans PATH
    pause
    exit /b 1
)

echo [API] Demarrage du serveur FastAPI...
echo [API] Port: definie par API_PORT (config/settings.py)
echo.

python run_api.py

if errorlevel 1 (
    echo.
    echo [ERREUR] Le serveur s'est arrete avec une erreur.
    echo Verifiez que toutes les dependances sont installees:
    echo   pip install -r requirements.txt
    echo.
)

pause
