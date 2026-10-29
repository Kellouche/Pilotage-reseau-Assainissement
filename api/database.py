"""
Connexion à la base de données.
Priorité: PostgreSQL + PostGIS (production)
Fallback: SQLite (développement/demo si PG non dispo)
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

# Fallback SQLite local par défaut en test ou si PG non disponible
SQLITE_URL = "sqlite:///./swmm_platform.db"

if _is_test:
    engine = create_engine(
        SQLITE_URL,
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
        Inspection, Incident, Job, AuditLog, UsageCounter
    )

    Base.metadata.create_all(bind=engine)
    print("[DB] Tables initialisées avec succès")
