"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Point d'entrée du package API DrainPilot
================================================================================
"""

# API package
from .main import app
from . import database, models, schemas, crud, routes

__all__ = ["app", "database", "models", "schemas", "crud", "routes"]
