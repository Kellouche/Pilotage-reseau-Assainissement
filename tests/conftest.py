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
    # Migration douce : colonnes ajoutées après la création initiale de la base de test
    from sqlalchemy import text
    with engine.connect() as conn:
        for ddl in (
            "ALTER TABLE clusters ADD COLUMN bassin_ref VARCHAR(120)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_cluster_network_bassin_ref ON clusters (network_id, bassin_ref)",
        ):
            try:
                conn.execute(text(ddl))
                conn.commit()
            except Exception:
                pass
    yield



