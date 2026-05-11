"""
Point d'entrée principal de l'API FastAPI.
Configure l'application, les routes, le middleware CORS, etc.
"""

import asyncio
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path

from config.settings import APP_NAME, APP_VERSION, APP_DESCRIPTION
from api.database import init_db, get_db
from api import schemas, crud

# Import des routes
from api.routes import network, simulations, sync, clusters, qualite

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

    # Warm-up asynchrone du graphe
    async def warmup_graph():
        try:
            from api.routes.clusters import _get_graph
            await asyncio.to_thread(_get_graph)
            print("[API] Cache graphe prêt ✓")
        except Exception as e:
            print(f"[API] ERREUR warmup graphe: {e}")

    asyncio.create_task(warmup_graph())
    yield
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

# Montage des fichiers statiques (JS, CSS, Images)
app.mount("/static", StaticFiles(directory="static"), name="static")

# CORS
origins = [
    "http://localhost:5000",
    "http://localhost:3000",
    "http://localhost:19006",
    "*"
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
    return {
        "application": APP_NAME,
        "version": APP_VERSION,
        "status": "running",
        "documentation": "/docs",
        "endpoints": {
            "regards": "/api/v1/network/regards",
            "conduites": "/api/v1/network/conduites",
            "rejets": "/api/v1/network/rejets",
            "clusters": "/api/v1/clusters",
            "simulations": "/api/v1/simulations",
            "sync": "/api/v1/sync",
            "visualisation": "/map"
        }
    }


@app.get("/health")
def health_check(db=Depends(get_db)):
    try:
        from api.routes.clusters import get_graph_status
        graph_status = get_graph_status()
    except:
        graph_status = "unknown"

    try:
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
# PAGES HTML
# ============================================================

@app.get("/map", response_class=HTMLResponse)
def get_map():
    """Interface de visualisation des couches du réseau."""
    template_path = Path("templates/map.html")
    if template_path.exists():
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    else:
        return HTMLResponse(content="<h1>Erreur: Template map.html non trouvé</h1>", status_code=404)


# ============================================================
# API ENDPOINTS
# ============================================================

@app.get("/api/v1/layers")
def get_layers():
    """Retourne les données GeoJSON des couches du réseau."""
    from pathlib import Path
    import geopandas as gpd

    GPKG_PATH = Path(r"D:\IA Water Data Analysis\Assainissement\Assainissement_Ville.gpkg")
    WGS84 = "EPSG:4326"

    result = {"statut": "ok", "couches": {}, "compteurs": {}}

    KEYWORDS = {
        'conduites': 'canalisations',
        'regards': 'regards',
        'stations': 'station_de_relevage',
        'step': 'step',
        'ouvrages': 'ouvrages_speciaux'
    }

    try:
        layers = gpd.list_layers(GPKG_PATH)['name'].tolist()
    except Exception as e:
        print(f"[ERROR] Impossible de lister les couches: {e}")
        return result

    for key, motcle in KEYWORDS.items():
        layer_name = next((l for l in layers if motcle.lower() in l.lower()), None)
        if not layer_name:
            result["couches"][key] = {"type": "FeatureCollection", "features": []}
            result["compteurs"][key] = 0
            continue

        try:
            gdf = gpd.read_file(GPKG_PATH, layer=layer_name)
            if gdf.crs and gdf.crs != WGS84:
                gdf = gpd.GeoDataFrame(gdf, geometry=gdf.geometry.to_crs(WGS84))

            geojson = gdf.__geo_interface__
            result["couches"][key] = geojson
            result["compteurs"][key] = len(geojson.get('features', []))
        except Exception as e:
            print(f"[ERROR] {key}: {e}")
            result["couches"][key] = {"type": "FeatureCollection", "features": []}
            result["compteurs"][key] = 0

    return result


# ============================================================
# WEBSOCKET POUR SYNCHRONISATION
# ============================================================

from api.websocket import manager

@app.websocket("/ws/sync")
async def websocket_sync(websocket):
    """WebSocket pour notifications temps réel des modifications."""
    await websocket.accept()
    await manager.connect(websocket)
    try:
        while True:
            # Garder la connexion ouverte
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        manager.disconnect(websocket)


# ============================================================
# PAGES HTML
# ============================================================

@app.get("/qualite", response_class=HTMLResponse)
async def page_qualite():
    """Page de visualisation de la qualité du réseau."""
    try:
        with open("templates/qualite.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse("""
        <h1>Erreur</h1>
        <p>La page de qualité réseau n'est pas disponible.</p>
        <a href="/docs">Retour à la documentation API</a>
        """, status_code=404)


@app.get("/carte", response_class=HTMLResponse)
async def page_carte():
    """Page de la carte opérationnelle pour visualiser et corriger les anomalies."""
    try:
        with open("templates/carte.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse("""
        <h1>Erreur</h1>
        <p>La page de carte opérationnelle n'est pas disponible.</p>
        <a href="/docs">Retour à la documentation API</a>
        """, status_code=404)


# ============================================================
# INCLUSION DES ROUTES
# ============================================================

app.include_router(network.router, prefix="/api/v1", tags=["Réseau"])
app.include_router(simulations.router, prefix="/api/v1", tags=["Simulations"])
app.include_router(sync.router, prefix="/api/v1", tags=["Synchronisation"])
app.include_router(clusters.router, prefix="/api/v1", tags=["Clusters"])
app.include_router(qualite.router, prefix="/api/v1", tags=["Qualité réseau"])
