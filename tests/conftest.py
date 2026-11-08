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
import pytest

os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///./test_swmm_platform.db"

from api.database import Base, engine
from api.models import *  # noqa: F401, F403


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Initialise automatiquement les tables dans la base SQLite de test."""
    Base.metadata.create_all(bind=engine)
    yield



