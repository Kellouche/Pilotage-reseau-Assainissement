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
            "CREATE TABLE IF NOT EXISTS gpkg_versions (id VARCHAR(36) PRIMARY KEY, org_id VARCHAR(36) NOT NULL, project_id VARCHAR(36) NOT NULL, sha256 VARCHAR(64) NOT NULL, size_bytes BIGINT NOT NULL, storage_kind VARCHAR(16) NOT NULL, storage_ref VARCHAR(512) NOT NULL, filename_original VARCHAR(255), nb_regards INTEGER, nb_conduites INTEGER, created_at DATETIME NOT NULL, created_by_id VARCHAR(36), CONSTRAINT uq_gpkgver_project_sha UNIQUE (project_id, sha256), CONSTRAINT uq_gpkgver_id_project UNIQUE (id, project_id))",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_gpkgver_project_sha ON gpkg_versions (project_id, sha256)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_gpkgver_id_project ON gpkg_versions (id, project_id)",
            "ALTER TABLE projects ADD COLUMN gpkg_version_id VARCHAR(36)",
            "ALTER TABLE simulations ADD COLUMN gpkg_version_id VARCHAR(36)",
            "ALTER TABLE simulations ADD COLUMN gpkg_sha256 VARCHAR(64)",
            "ALTER TABLE simulations ADD COLUMN bassin_ref VARCHAR(120)",
            "ALTER TABLE simulations ADD COLUMN exutoire_noeud VARCHAR(100)",
            # LOT P1.4 — estampillage GPKG des apports DWF
            "ALTER TABLE apports_dwf ADD COLUMN gpkg_version_id VARCHAR(36)",
            "ALTER TABLE apports_dwf ADD COLUMN gpkg_sha256 VARCHAR(64)",
        ):
            try:
                conn.execute(text(ddl))
                conn.commit()
            except Exception:
                pass
    yield



