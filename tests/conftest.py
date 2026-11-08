# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Fixtures Pytest globales, base de données de test et client HTTP
================================================================================
"""

import os
import sys

os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///./test_swmm_platform.db"

