@echo off
chcp 65001 > nul
cd /d "%~dp0"

title Reseau d'Assainissement

echo.
echo ╔════════════════════════════════════════════════════════╗
echo ║  SERVEUR RESEAU D'ASSAINISSEMENT                     ║
echo ╚════════════════════════════════════════════════════════╝
echo.
echo   URL : http://localhost:5000
echo   Ctrl+C pour arreter
echo.

python server.py

pause
