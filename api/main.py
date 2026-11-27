"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-24
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
from api.core.security import require_role, TenantContext

from api.routes import network, layers, aide, simulations, simulations_profil, simulations_contexte, simulations_scenarios, simulations_exports, simulations_consultation, sync, clusters, auth_profile, network_datasets, network_geo, qualite, qualite_scores, qualite_conduites, corrections, terrain, mnt, audit, auth, jobs, artifacts, licensing, admin, organization, apports, apports_read, apports_write, corrections_suggestions, garde_fou, aux_layers, extractions

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
    content_type = response.headers.get("content-type", "")
    if (path.startswith("/static/") or path == "/" or path.startswith("/api/")
            or content_type.startswith("text/html")):
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

app.include_router(layers.router, tags=["Couches GeoJSON"])
app.include_router(aide.router, tags=["Aide"])
app.include_router(auth.router, prefix="/api/v1", tags=["Authentification & Multi-Tenant"])
app.include_router(auth_profile.router, prefix="/api/v1", tags=["Authentification — profil & clés API"])
app.include_router(network_datasets.router, prefix="/api/v1", tags=["Réseau — datasets"])
app.include_router(network_geo.router, prefix="/api/v1", tags=["Réseau — geo"])
app.include_router(network.router, prefix="/api/v1", tags=["Réseau"])
app.include_router(simulations.router, prefix="/api/v1", tags=["Simulations"])
app.include_router(simulations_profil.router, prefix="/api/v1", tags=["Simulations"])
app.include_router(simulations_scenarios.router, prefix="/api/v1", tags=["Simulations"])
app.include_router(simulations_exports.router, prefix="/api/v1", tags=["Simulations"])
app.include_router(simulations_consultation.router, prefix="/api/v1", tags=["Simulations"])
app.include_router(sync.router, prefix="/api/v1", tags=["Synchronisation"])
app.include_router(clusters.router, prefix="/api/v1", tags=["Clusters"])
app.include_router(qualite.router, prefix="/api/v1", tags=["Qualité réseau"])
app.include_router(qualite_scores.router, prefix="/api/v1", tags=["Qualité réseau — Scores & exports"])
app.include_router(qualite_conduites.router, prefix="/api/v1", tags=["Qualité réseau — Conduites"])
app.include_router(corrections.router, prefix="/api/v1/corrections", tags=["Corrections"])
app.include_router(corrections_suggestions.router, prefix="/api/v1/corrections", tags=["Corrections — suggestions"])
app.include_router(terrain.router, prefix="/api/v1", tags=["Collecte Terrain"])
app.include_router(mnt.router, prefix="/api/v1", tags=["MNT / DEM"])
app.include_router(audit.router, prefix="/api/v1", tags=["Traçabilité / Audit"])
app.include_router(jobs.router, prefix="/api/v1", tags=["Jobs & Tâches Asynchrones"])
app.include_router(artifacts.router, prefix="/api/v1", tags=["Artefacts & Stockage"])
app.include_router(licensing.router, prefix="/api/v1", tags=["Licences & Facturation B2B/B2G"])
app.include_router(admin.router, prefix="/api/v1", tags=["Console Opérateur SuperAdmin"])
app.include_router(organization.router, prefix="/api/v1", tags=["Gestion d'Organisation & Équipe"])
app.include_router(apports.router, prefix="/api/v1", tags=["Apports de temps sec (DWF)"])
app.include_router(apports_read.router, prefix="/api/v1", tags=["Apports DWF — lecture"])
app.include_router(apports_write.router, prefix="/api/v1", tags=["Apports DWF — écriture"])
app.include_router(garde_fou.router, prefix="/api/v1", tags=["Garde-fou hydraulicien"])
app.include_router(aux_layers.router, prefix="/api/v1", tags=["Couches SIG satellite"])
app.include_router(extractions.router, prefix="/api/v1", tags=["Extraction par pochoir"])

# Compat : reset_layers_cache est defini dans api/routes/layers.py
from api.routes.layers import reset_layers_cache  # noqa: F401,E402

