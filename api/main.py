"""
Point d'entrée principal de l'API FastAPI.
Configure l'application, les routes, le middleware CORS, etc.
"""

import os
import sys
import asyncio
from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from config.settings import APP_NAME, APP_VERSION, APP_DESCRIPTION
from api.database import init_db, get_db
from api import schemas, crud

from api.routes import network, simulations, sync, clusters, qualite, corrections, terrain, mnt, audit, auth, jobs, artifacts

# ============================================================
# LIFESPAN (démarrage/arrêt)
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    import sys
    _is_test = "pytest" in sys.modules or os.getenv("TESTING") == "true" or os.getenv("PYTEST_CURRENT_TEST") is not None

    if not _is_test:
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

        # Warm-up asynchrone des couches GeoJSON
        async def warmup_layers():
            try:
                print("[API] Warm-up du cache des couches GeoJSON...")
                await asyncio.to_thread(get_layers)
                print("[API] Cache des couches GeoJSON prêt ✓")
            except Exception as e:
                print(f"[API] ERREUR warmup couches: {e}")

        asyncio.create_task(warmup_graph())
        asyncio.create_task(warmup_layers())

    yield
    if not _is_test:
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
# Montage des fichiers statiques (JS, CSS, Images)
app.mount("/static", StaticFiles(directory="static"), name="static")

# CORS
origins = [
    "http://localhost:5000",
    "http://localhost:3000",
    "http://localhost:19006",
    "http://localhost:5002",
    "http://127.0.0.1:5002",
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

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    """Page d'accueil - Cockpit hydraulique et cartographie Leaflet."""
    template_path = Path("templates/index.html")
    if template_path.exists():
        with open(template_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>SWMM Platform</h1><p>Consultez la <a href='/docs'>Documentation API Swagger</a>.</p>")


@app.get("/api/info")
def get_api_info():
    """Métadonnées JSON de l'application."""
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
            "jobs": "/api/v1/jobs",
            "artifacts": "/api/v1/artifacts",
            "sync": "/api/v1/sync",
            "visualisation": "/map",
            "qualite": "/qualite",
            "carte": "/carte",
            "tunnel": "/tunnel"
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

_LAYERS_CACHE = None
_GDF_CACHE = None
import math

def clean_nan(obj):
    if isinstance(obj, float) and math.isnan(obj):
        return None
    elif isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan(v) for v in obj]
    elif isinstance(obj, tuple):
        return tuple(clean_nan(v) for v in obj)
    return obj

def _has_bounds(ne_lat, ne_lng, sw_lat, sw_lng):
    return None not in (ne_lat, ne_lng, sw_lat, sw_lng)

@app.get("/api/v1/layers")
def get_layers(
    ne_lat: Optional[float] = None,
    ne_lng: Optional[float] = None,
    sw_lat: Optional[float] = None,
    sw_lng: Optional[float] = None,
):
    """Retourne les données GeoJSON des couches du réseau (avec cache optimisé par index spatial)."""
    global _LAYERS_CACHE, _GDF_CACHE
    has_bounds = _has_bounds(ne_lat, ne_lng, sw_lat, sw_lng)
    
    if _LAYERS_CACHE is not None and not has_bounds:
        return _LAYERS_CACHE
        
    if _GDF_CACHE is not None and has_bounds:
        # Filtrage ultra-rapide via index spatial GeoPandas (.cx)
        result = {"statut": "ok", "couches": {}, "compteurs": {}}
        for key, gdf in _GDF_CACHE.items():
            if not gdf.empty:
                filtered_gdf = gdf.cx[sw_lng:ne_lng, sw_lat:ne_lat]
                import json
                geojson = json.loads(filtered_gdf.to_json(na="drop"))
                result["couches"][key] = geojson
                result["compteurs"][key] = len(geojson.get('features', []))
            else:
                result["couches"][key] = {"type": "FeatureCollection", "features": []}
                result["compteurs"][key] = 0
        return result

    # Construction du cache (première fois)
    from pathlib import Path
    import geopandas as gpd

    GPKG_PATH = Path(r"D:\IA Water Data Analysis\Assainissement\Assainissement_Ville.gpkg")
    WGS84 = "EPSG:4326"

    result = {"statut": "ok", "couches": {}, "compteurs": {}}
    gdf_cache_temp = {}

    KEYWORDS = {
        'conduites': 'canalisations',
        'regards': 'regards',
        'stations': 'station_de_relevage',
        'step': 'step',
        'ouvrages': 'ouvrages_speciaux',
        'rejets': 'rejets'
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
            gdf_cache_temp[key] = gpd.GeoDataFrame()
            continue

        try:
            gdf = gpd.read_file(GPKG_PATH, layer=layer_name)
            if gdf.crs and gdf.crs != WGS84:
                gdf = gpd.GeoDataFrame(gdf, geometry=gdf.geometry.to_crs(WGS84))
            
            # Construire explicitement l'index spatial (R-tree) pour de meilleures perfs
            _ = gdf.sindex
            
            gdf_cache_temp[key] = gdf
            
            if has_bounds and not gdf.empty:
                gdf_to_export = gdf.cx[sw_lng:ne_lng, sw_lat:ne_lat]
            else:
                gdf_to_export = gdf

            import json
            geojson = json.loads(gdf_to_export.to_json(na="drop"))
            result["couches"][key] = geojson
            result["compteurs"][key] = len(geojson.get('features', []))
        except Exception as e:
            print(f"[ERROR] {key}: {e}")
            result["couches"][key] = {"type": "FeatureCollection", "features": []}
            result["compteurs"][key] = 0
            gdf_cache_temp[key] = gpd.GeoDataFrame()

    _GDF_CACHE = gdf_cache_temp
    if not has_bounds:
        _LAYERS_CACHE = result

    return result


# ============================================================
# WEBSOCKET POUR SYNCHRONISATION
# ============================================================

from api.websocket import manager

@app.websocket("/ws/sync")
async def websocket_sync(websocket: WebSocket):
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

@app.get("/tunnel", response_class=HTMLResponse)
async def page_tunnel():
    """Page du tunnel de workflow en 4 étapes."""
    try:
        with open("templates/tunnel.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse("""
        <h1>Erreur</h1>
        <p>Le template tunnel.html est introuvable.</p>
        <a href="/docs">Retour à la documentation API</a>
        """, status_code=404)


# ============================================================
# INCLUSION DES ROUTES
# ============================================================

app.include_router(auth.router, prefix="/api/v1", tags=["Authentification & Multi-Tenant"])
app.include_router(network.router, prefix="/api/v1", tags=["Réseau"])
app.include_router(simulations.router, prefix="/api/v1", tags=["Simulations"])
app.include_router(sync.router, prefix="/api/v1", tags=["Synchronisation"])
app.include_router(clusters.router, prefix="/api/v1", tags=["Clusters"])
app.include_router(qualite.router, prefix="/api/v1", tags=["Qualité réseau"])
app.include_router(corrections.router, prefix="/api/v1/corrections", tags=["Corrections"])
app.include_router(terrain.router, prefix="/api/v1", tags=["Collecte Terrain"])
app.include_router(mnt.router, prefix="/api/v1", tags=["MNT / DEM"])
app.include_router(audit.router, prefix="/api/v1", tags=["Traçabilité / Audit"])
app.include_router(jobs.router, prefix="/api/v1", tags=["Jobs & Tâches Asynchrones"])
app.include_router(artifacts.router, prefix="/api/v1", tags=["Artefacts & Stockage"])


@app.websocket("/ws/jobs/{job_id}")
async def ws_jobs_alias(websocket: WebSocket, job_id: str):
    """Alias racine pour le flux WebSocket de suivi des jobs en temps réel."""
    await jobs.websocket_job_progress(websocket, job_id)
