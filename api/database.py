"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Gestionnaire de connexions PostgreSQL / PostGIS et SQLite local
================================================================================
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from config.settings import DATABASE_URL

_is_test = (
    "pytest" in sys.modules
    or any("pytest" in arg for arg in sys.argv)
    or os.getenv("TESTING") == "true"
    or os.getenv("PYTEST_CURRENT_TEST") is not None
)

# Bases de données SQLite locales : isolation stricte entre tests et développement
SQLITE_URL = "sqlite:///./swmm_platform.db"
TEST_SQLITE_URL = "sqlite:///./test_swmm_platform.db"

if _is_test:
    # Les tests automatiques utilisent exclusivement la base de test éphémère
    engine = create_engine(
        TEST_SQLITE_URL,
        echo=False,
        future=True,
        connect_args={"check_same_thread": False}
    )
else:
    # Tenter PostgreSQL avec un timeout court (2s), sinon fallback SQLite
    try:
        engine = create_engine(
            DATABASE_URL,
            echo=os.getenv("SQL_ECHO", "False").lower() == "true",
            future=True,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            connect_args={"connect_timeout": 2} if "postgres" in DATABASE_URL else {}
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("[DB] PostgreSQL connecté avec succès")
    except Exception as e:
        engine = create_engine(
            SQLITE_URL,
            echo=False,
            future=True,
            connect_args={"check_same_thread": False}
        )

# Session locale
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True
)

# Base déclarative SQLAlchemy 2.0
class Base(DeclarativeBase):
    """Classe de base déclarative pour SWMM Platform SaaS."""
    pass

def get_db():
    """Dépendance FastAPI pour obtenir une session DB."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Crée les tables si elles n'existent pas."""
    from api.models import (
        Organization, User, Membership, ApiKey, PurchaseOrder,
        Project, Regard, Canalisation, Rejet, Cluster, Simulation,
        Inspection, Incident, Job, AuditLog, UsageCounter, ApportDwf
    )

    Base.metadata.create_all(bind=engine)

    # Migration douce pour les colonnes de code de vérification (SQLite & PG)
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN verification_code VARCHAR(6)"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN verification_code_expires_at TIMESTAMP"))
            conn.commit()
        except Exception:
            pass
        # Migration douce : référence métier stable des bassins (étape 3A)
        try:
            conn.execute(text("ALTER TABLE clusters ADD COLUMN bassin_ref VARCHAR(120)"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_cluster_network_bassin_ref ON clusters (network_id, bassin_ref)"))
            conn.commit()
        except Exception:
            pass
        # Migration douce : versionnement immuable des GPKG (étape 3B)
        # SQLite : FK composites non enforceables sur tables existantes →
        # garantie tenant applicative (service) + index/contraintes simples.
        for ddl in (
            """CREATE TABLE IF NOT EXISTS gpkg_versions (
                id VARCHAR(36) PRIMARY KEY,
                org_id VARCHAR(36) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                sha256 VARCHAR(64) NOT NULL,
                size_bytes BIGINT NOT NULL,
                storage_kind VARCHAR(16) NOT NULL,
                storage_ref VARCHAR(512) NOT NULL,
                filename_original VARCHAR(255),
                nb_regards INTEGER,
                nb_conduites INTEGER,
                created_at DATETIME NOT NULL,
                created_by_id VARCHAR(36),
                CONSTRAINT uq_gpkgver_project_sha UNIQUE (project_id, sha256),
                CONSTRAINT uq_gpkgver_id_project UNIQUE (id, project_id)
            )""",
            "CREATE INDEX IF NOT EXISTS ix_gpkg_versions_org_id ON gpkg_versions (org_id)",
            "CREATE INDEX IF NOT EXISTS ix_gpkg_versions_project_id ON gpkg_versions (project_id)",
            "CREATE INDEX IF NOT EXISTS ix_gpkg_versions_sha256 ON gpkg_versions (sha256)",
            "CREATE INDEX IF NOT EXISTS ix_gpkg_versions_org_project ON gpkg_versions (org_id, project_id)",
            "ALTER TABLE projects ADD COLUMN gpkg_version_id VARCHAR(36)",
            "ALTER TABLE simulations ADD COLUMN gpkg_version_id VARCHAR(36)",
            "ALTER TABLE simulations ADD COLUMN gpkg_sha256 VARCHAR(64)",
            "ALTER TABLE simulations ADD COLUMN bassin_ref VARCHAR(120)",
            "ALTER TABLE simulations ADD COLUMN exutoire_noeud VARCHAR(100)",
        ):
            try:
                conn.execute(text(ddl))
                conn.commit()
            except Exception:
                pass
        try:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_gpkgver_project_sha ON gpkg_versions (project_id, sha256)"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_gpkgver_id_project ON gpkg_versions (id, project_id)"))
            conn.commit()
        except Exception:
            pass

    print("[DB] Tables initialisées avec succès")
