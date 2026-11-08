"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Application FastAPI principale, middlewares, CORS et montage des routeurs
================================================================================
"""

import os
import sys

# Stabilisation mémoire OpenBLAS / OpenMP sur Windows
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import asyncio
import jinja2
from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from config.settings import APP_NAME, APP_VERSION, APP_DESCRIPTION
from api.database import init_db, get_db, SessionLocal
from sqlalchemy.orm import Session
from api.models import Project
from api import schemas, crud

from api.routes import network, simulations, sync, clusters, qualite, corrections, terrain, mnt, audit, auth, jobs, artifacts, licensing, admin, organization

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
                demo_path = Path("data/demo_reseau.gpkg")
                if demo_path.exists():
                    print("[API] Données de démonstration prêtes ✓")
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

@app.middleware("http")
async def catch_cancelled_error_middleware(request: Request, call_next):
    """Intercepte proprement l'annulation des requêtes HTTP en cours lors d'un arrêt Ctrl+C."""
    try:
        return await call_next(request)
    except (asyncio.CancelledError, KeyboardInterrupt):
        return Response(status_code=503)


@app.middleware("http")
async def anti_cache_static_middleware(request: Request, call_next):
    """
    Désactive strictement la mise en cache navigateur sur les assets statiques (/static/),
    les pages HTML et les endpoints de données pour garantir une fraîcheur temps réel immédiate.
    """
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/") or path == "/" or path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# ============================================================
# ROOT & HEALTH
# ============================================================

# ============================================================
# AUTH HELPER FOR WEB VIEWS
# ============================================================

def _get_authenticated_user(request: Request, db):
    """Extrait l'utilisateur connecté via cookie ou Bearer token (sans lever d'exception)."""
    from api.core.auth import decode_token
    from api.models import User

    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()

    # 1. Tenter avec access_token
    if token:
        try:
            payload = decode_token(token)
            if payload and payload.get("sub"):
                user = db.query(User).filter(User.id == payload["sub"], User.is_active.is_(True)).first()
                if user and user.email_verified:
                    return user
        except Exception:
            pass

    # 2. Fallback avec refresh_token (pour maintenir la session active sur F5 / réouverture)
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        try:
            payload = decode_token(refresh_token)
            if payload and payload.get("sub"):
                user = db.query(User).filter(User.id == payload["sub"], User.is_active.is_(True)).first()
                if user and user.email_verified:
                    return user
        except Exception:
            pass

    return None


# ============================================================
# ROOT, AUTH & MARKETING PAGES
# ============================================================

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request, db=Depends(get_db)):
    """
    Page d'accueil : vitrine SaaS publique pour les visiteurs,
    redirection automatique vers le cockpit /cockpit pour les utilisateurs connectés.
    """
    user = _get_authenticated_user(request, db)
    if user:
        return RedirectResponse(url="/cockpit", status_code=302)

    landing_path = Path("templates/landing.html")
    if landing_path.exists():
        with open(landing_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())

_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader("templates"),
    autoescape=False
)

def _render_cockpit_html(template_name: str = "index.html") -> str:
    template = _jinja_env.get_template(template_name)
    return template.render()

    index_path = Path("templates/index.html")
    if index_path.exists():
        try:
            return HTMLResponse(content=_render_cockpit_html("index.html"))
        except Exception:
            with open(index_path, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())

    return HTMLResponse("<h1>SWMM Platform</h1><p>Consultez la <a href='/docs'>Documentation API Swagger</a>.</p>")


@app.get("/login", response_class=HTMLResponse)
def page_login(request: Request, db=Depends(get_db)):
    """Page de connexion utilisateur."""
    user = _get_authenticated_user(request, db)
    if user:
        return RedirectResponse(url="/cockpit", status_code=302)
    path = Path("templates/auth/login.html")
    if path.exists():
        return HTMLResponse(content=path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Page de connexion introuvable</h1>", status_code=404)


@app.get("/register", response_class=HTMLResponse)
def page_register(request: Request, db=Depends(get_db)):
    """Page d'inscription et de création d'organisation."""
    user = _get_authenticated_user(request, db)
    if user:
        return RedirectResponse(url="/cockpit", status_code=302)
    path = Path("templates/auth/register.html")
    if path.exists():
        return HTMLResponse(content=path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Page d'inscription introuvable</h1>", status_code=404)


@app.get("/logout")
def page_logout():
    """Déconnexion de session et suppression des cookies."""
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")
    return response


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/pricing", response_class=HTMLResponse)
@app.get("/tarifs", response_class=HTMLResponse)
def page_pricing():
    """Grille des tarifs et offres en Dinars Algériens (DZD)."""
    landing_path = Path("templates/landing.html")
    if landing_path.exists():
        return HTMLResponse(content=landing_path.read_text(encoding="utf-8"))
    return RedirectResponse(url="/#tarifs", status_code=302)


# ============================================================
# COCKPIT & PAGES TECHNIQUES
# ============================================================

@app.get("/cockpit", response_class=HTMLResponse)
@app.get("/map", response_class=HTMLResponse)
def get_cockpit(request: Request, db=Depends(get_db)):
    """Cockpit hydraulique et cartographie interactive Leaflet (réservé aux membres authentifiés)."""
    user = _get_authenticated_user(request, db)
    if not user:
        return RedirectResponse(url="/login?next=/cockpit", status_code=302)

    template_path = Path("templates/index.html")
    if not template_path.exists():
        template_path = Path("templates/map.html")
    if template_path.exists():
        try:
            return HTMLResponse(content=_render_cockpit_html(template_path.name))
        except Exception:
            with open(template_path, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Erreur: Template cockpit non trouvé</h1>", status_code=404)


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
# API ENDPOINTS
# ============================================================

_LAYERS_CACHE = {}
_GDF_CACHE = {}
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

def reset_layers_cache():
    global _LAYERS_CACHE, _GDF_CACHE
    _LAYERS_CACHE = {}
    _GDF_CACHE = {}

@app.get("/api/v1/layers")
def get_layers(
    request: Request,
    ne_lat: Optional[float] = None,
    ne_lng: Optional[float] = None,
    sw_lat: Optional[float] = None,
    sw_lng: Optional[float] = None,
    db: Session = Depends(get_db),
):
    """
    Retourne les données GeoJSON des couches du réseau pour le projet actif de l'utilisateur.
    Si aucun fichier de réseau n'est associé au projet, retourne un espace vierge (Option B).
    """
    global _LAYERS_CACHE, _GDF_CACHE
    has_bounds = _has_bounds(ne_lat, ne_lng, sw_lat, sw_lng)

    empty_response = {
        "statut": "ok",
        "is_empty": True,
        "project_name": "Nouveau Projet (Espace vierge)",
        "compteurs": {
            "conduites": 0, "regards": 0, "stations": 0, "step": 0, "ouvrages": 0, "rejets": 0
        },
        "couches": {
            "conduites": {"type": "FeatureCollection", "features": []},
            "regards": {"type": "FeatureCollection", "features": []},
            "stations": {"type": "FeatureCollection", "features": []},
            "step": {"type": "FeatureCollection", "features": []},
            "ouvrages": {"type": "FeatureCollection", "features": []},
            "rejets": {"type": "FeatureCollection", "features": []}
        }
    }

    user = None
    if request and db:
        user = _get_authenticated_user(request, db)

    # Détermination du fichier GeoPackage pour le projet actif
    gpkg_target = None
    project_name = "Nouveau Projet"

    if user and db:
        primary_membership = user.memberships[0] if user.memberships else None
        if primary_membership:
            project = db.query(Project).filter(
                Project.org_id == primary_membership.org_id,
                Project.is_archived.is_(False)
            ).first()
            if project:
                project_name = project.name
                if project.source_gpkg_key:
                    cand = Path(project.source_gpkg_key)
                    if cand.exists():
                        gpkg_target = cand

    # Si aucun réseau n'est chargé et qu'aucun utilisateur n'est connecté -> Fallback projet actif local ou démo
    if not gpkg_target and not user and db:
        project = db.query(Project).filter(Project.is_archived.is_(False)).first()
        if project:
            project_name = project.name
            if project.source_gpkg_key:
                cand = Path(project.source_gpkg_key)
                if cand.exists():
                    gpkg_target = cand
        if not gpkg_target:
            cand = Path("data/demo_reseau.gpkg")
            if cand.exists():
                gpkg_target = cand
                project_name = "Quartier Témoin (Démo)"

    if not gpkg_target:
        empty_response["project_name"] = project_name
        return empty_response

    cache_key = str(gpkg_target)

    if cache_key in _LAYERS_CACHE and not has_bounds:
        res = dict(_LAYERS_CACHE[cache_key])
        res["project_name"] = project_name
        res["is_empty"] = False
        return res

    if cache_key in _GDF_CACHE and has_bounds:
        result = {"statut": "ok", "is_empty": False, "project_name": project_name, "couches": {}, "compteurs": {}}
        for key, gdf in _GDF_CACHE[cache_key].items():
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

    # Construction du cache pour ce GeoPackage
    import geopandas as gpd

    result = {"statut": "ok", "is_empty": False, "project_name": project_name, "couches": {}, "compteurs": {}}
    gdf_cache_temp = {}
    WGS84 = "EPSG:4326"

    KEYWORDS = {
        'conduites': 'canalisations',
        'regards': 'regards',
        'stations': 'station_de_relevage',
        'step': 'step',
        'ouvrages': 'ouvrages_speciaux',
        'rejets': 'rejets'
    }

    try:
        layers = gpd.list_layers(gpkg_target)['name'].tolist()
    except Exception as e:
        print(f"[ERROR] Impossible de lister les couches de {gpkg_target}: {e}")
        return empty_response

    for key, motcle in KEYWORDS.items():
        layer_name = next((l for l in layers if motcle.lower() in l.lower()), None)
        if not layer_name:
            result["couches"][key] = {"type": "FeatureCollection", "features": []}
            result["compteurs"][key] = 0
            gdf_cache_temp[key] = gpd.GeoDataFrame()
            continue

        try:
            gdf = gpd.read_file(gpkg_target, layer=layer_name)
            if gdf.crs and gdf.crs != WGS84:
                gdf = gpd.GeoDataFrame(gdf, geometry=gdf.geometry.to_crs(WGS84))

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

    _GDF_CACHE[cache_key] = gdf_cache_temp
    if not has_bounds:
        _LAYERS_CACHE[cache_key] = result

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
async def page_qualite(request: Request, db=Depends(get_db)):
    """Page de visualisation de la qualité du réseau."""
    user = _get_authenticated_user(request, db)
    if not user:
        return RedirectResponse(url="/login?next=/qualite", status_code=302)
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
async def page_carte(request: Request, db=Depends(get_db)):
    """Page de la carte opérationnelle pour visualiser et corriger les anomalies."""
    user = _get_authenticated_user(request, db)
    if not user:
        return RedirectResponse(url="/login?next=/carte", status_code=302)
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
async def page_tunnel(request: Request, db=Depends(get_db)):
    """Page du tunnel de workflow en 4 étapes."""
    user = _get_authenticated_user(request, db)
    if not user:
        return RedirectResponse(url="/login?next=/tunnel", status_code=302)
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
app.include_router(licensing.router, prefix="/api/v1", tags=["Licences & Facturation B2B/B2G"])
app.include_router(admin.router, prefix="/api/v1", tags=["Console Opérateur SuperAdmin"])
app.include_router(organization.router, prefix="/api/v1", tags=["Gestion d'Organisation & Équipe"])


# ============================================================
# ALIASES BASSINS MANUELS (COMPATIBILITÉ CARTE & COCKPIT)
# ============================================================

@app.post("/api/v1/manual-basin")
def api_save_manual_basin_alias(data: dict):
    from src.infrastructure.persistance_manuelle import sauvegarder_bassin_manuel
    return sauvegarder_bassin_manuel(data)


@app.delete("/api/v1/manual-basin/{bassin_id}")
def api_delete_manual_basin_alias(bassin_id: str):
    from src.infrastructure.persistance_manuelle import supprimer_bassin_manuel
    res = supprimer_bassin_manuel(bassin_id)
    return {"status": "ok" if res else "error"}


@app.get("/api/v1/manual-basin")
def api_get_manual_basins_alias():
    from src.infrastructure.persistance_manuelle import charger_bassins_manuels
    return charger_bassins_manuels()



@app.websocket("/ws/jobs/{job_id}")
async def ws_jobs_alias(websocket: WebSocket, job_id: str):
    """Alias racine pour le flux WebSocket de suivi des jobs en temps réel."""
    await jobs.websocket_job_progress(websocket, job_id)
