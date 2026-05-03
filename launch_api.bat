@echo off
REM Lancement de la plateforme SWMM POC - API FastAPI

echo.
echo ========================================
echo   SWMM Platform POC - API Server
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
echo [API] Port: 5001
echo [API] Documentation: http://localhost:5001/docs
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
