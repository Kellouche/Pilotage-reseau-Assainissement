"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Paramètres d'environnement, configuration base de données et flags applicatifs
================================================================================
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Répertoire racine du projet
ROOT_DIR = Path(__file__).parent.parent

# Charger le fichier .env si présent
load_dotenv(dotenv_path=ROOT_DIR / ".env")

# Application
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "5002"))
API_RELOAD = os.getenv("API_RELOAD", "true").lower() == "true"
LEGACY_FLASK_PORT = int(os.getenv("LEGACY_FLASK_PORT", "5000"))
EXPO_WEB_PORT = int(os.getenv("EXPO_WEB_PORT", "19006"))

# GeoPackage source (données initiales)
GPKG_PATH = Path(
    os.getenv(
        "GPKG_PATH",
        r"D:\IA Water Data Analysis\Assainissement\Assainissement_Ville.gpkg",
    )
)

# Base de données PostgreSQL
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "swmm_platform")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

# Connexion SQLAlchemy
DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Redis (cache + Celery)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

# Celery
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL

# Swagger
APP_NAME = "SWMM Platform POC"
APP_VERSION = "0.1.0"
APP_DESCRIPTION = "Plateforme collaborative de gestion du réseau d'assainissement"

# Projections
TARGET_CRS = "EPSG:32631"  # UTM Zone 31N
WGS84_CRS = "EPSG:4326"

# Clusters (précalculés)
MAX_CLUSTERS = 79  # nombre d'exutoires

# Synchronisation
SYNC_DELTA_MAX_DAYS = 30  # delta max en jours
VERSION_INCREMENT_ON_UPDATE = True  # incrémenter version à chaque modification

# Mode démo explicite (LOT P0.1) : autorise le repli sur data/demo_reseau.gpkg
# pour une organisation AUTHENTIFIÉE ne possédant aucun projet actif.
# Désactivé par défaut : jamais de contournement de l'authentification.
MODE_DEMO_RESEAU = os.getenv("DRAINPILOT_MODE_DEMO_RESEAU", "false").lower() == "true"
