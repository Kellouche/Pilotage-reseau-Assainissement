"""
Configuration centralisée de la plateforme SWMM.
Paramètres d'environnement, chemins, connexions DB.
"""

import os
from pathlib import Path

# Répertoire racine du projet
ROOT_DIR = Path(__file__).parent.parent

# Application
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "5001"))
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
