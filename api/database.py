"""
Connexion à la base de données.
Priorité: PostgreSQL + PostGIS (production)
Fallback: SQLite (développement/demo si PG non dispo)
"""

from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

from config.settings import DATABASE_URL

# Tenter PostgreSQL, sinon fallback SQLite
try:
    # Essayer PostgreSQL
    engine = create_engine(
        DATABASE_URL,
        echo=os.getenv("SQL_ECHO", "False").lower() == "true",
        future=True,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10
    )

    # Test connexion
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("[DB] PostgreSQL connecté avec succès")

except Exception as e:
    print(f"[DB] PostgreSQL non disponible: {e}")
    print("[DB] Fallback vers SQLite (mode démo)")
    
    # Fallback SQLite local
    SQLITE_URL = "sqlite:///./swmm_platform.db"
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

# Base pour modèles ORM
Base = declarative_base()

def get_db():
    """Dépendance FastAPI pour obtenir une session DB."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Crée les tables si elles n'existent pas."""
    from sqlalchemy import inspect
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    from api.models import Regard, Canalisation, Rejet, Cluster, Simulation, AuditLog

    required_tables = ['regards', 'conduites', 'rejets', 'clusters', 'simulations']
    need_create = any(t not in existing_tables for t in required_tables)

    if need_create:
        Base.metadata.create_all(bind=engine)
        print("[DB] Tables créées avec succès")
    else:
        print("[DB] Tables déjà existantes")
