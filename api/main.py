"""
Point d'entrée principal de l'API FastAPI.
Configure l'application, les routes, le middleware CORS, etc.
"""

import asyncio
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from config.settings import APP_NAME, APP_VERSION, APP_DESCRIPTION
from api.database import init_db, get_db
from api import schemas, crud

# Import des routes
from api.routes import network, simulations, sync, clusters  # clusters réactivé avec lazy loading

# ============================================================
# LIFESPAN (démarrage/arrêt)
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Démarrage
    print("[API] Initialisation de la base de données...")
    try:
        init_db()
        print("[API] Base de données prête")
    except Exception as e:
        print(f"[API] ERREUR DB: {e}")
        print("[API] L'API démarrera sans DB (mode démo)")

    # Warm-up asynchrone du graphe (sans bloquer le démarrage)
    async def warmup_graph():
        try:
            from api.routes.clusters import _get_graph
            await asyncio.to_thread(_get_graph)
            print("[API] Cache graphe prêt ✓")
        except Exception as e:
            print(f"[API] ERREUR warmup graphe: {e}")

    asyncio.create_task(warmup_graph())

    yield  # L'application tourne

    # Arrêt
    print("[API] Arrêt de l'API...")


# ============================================================
# APPLICATION FASTAPI
# ============================================================

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=APP_DESCRIPTION,
    lifespan=lifespan
)

# CORS (pour mobile + frontend)
origins = [
    "http://localhost:5000",      # serveur original (legacy)
    "http://localhost:3000",      # frontend React (dev)
    "http://localhost:19006",     # Expo web
    "*"  # Pour POC, on permet tout (à restreindre en prod)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# ROOT & HEALTH
# ============================================================

@app.get("/")
def read_root():
    """Page d'accueil avec infos de l'API."""
    return {
        "application": APP_NAME,
        "version": APP_VERSION,
        "status": "running",
        "documentation": "/docs",
        "endpoints": {
            "regards": "/api/v1/regards",
            "conduites": "/api/v1/conduites",
            "clusters": "/api/v1/clusters",
            "simulations": "/api/v1/simulations",
            "sync": "/api/v1/sync"
        }
    }


@app.get("/health")
def health_check(db=Depends(get_db)):
    """Vérifie la santé de l'API et de la base de données."""
    # Inclure le statut du cache graphe dans health
    try:
        from api.routes.clusters import get_graph_status
        graph_status = get_graph_status()
    except:
        graph_status = "unknown"

    try:
        # Test simple DB
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "graph_cache": graph_status,
        "api": "ok"
    }


# ============================================================
# INCLUSION DES ROUTES
# ============================================================

# Montage des routers
app.include_router(network.router, prefix="/api/v1", tags=["Réseau"])
app.include_router(simulations.router, prefix="/api/v1", tags=["Simulations"])
app.include_router(sync.router, prefix="/api/v1", tags=["Synchronisation"])
app.include_router(clusters.router, prefix="/api/v1", tags=["Clusters"])