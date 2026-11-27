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

from api.routes import network, simulations, simulations_profil, simulations_contexte, simulations_scenarios, simulations_exports, simulations_consultation, sync, clusters, network_datasets, network_geo, qualite, qualite_scores, qualite_conduites, corrections, terrain, mnt, audit, auth, jobs, artifacts, licensing, admin, organization, apports, apports_read, apports_write, corrections_suggestions, garde_fou, aux_layers, extractions

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
    snapshot: Optional[str] = None,
    project_id: Optional[str] = None,
    ctx: TenantContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db),
):
    """
    Retourne les données GeoJSON des couches du réseau pour le projet actif de l'organisation.
    Si aucun fichier de réseau n'est associé au projet, retourne un espace vierge (Option B).

    `snapshot` (optionnel) : gpkg_version_id ou préfixe sha256 d'une version
    archivée du MÊME projet — permet de consulter une simulation sur le réseau
    qui l'a produite (jamais de substitution silencieuse : snapshot inconnu
    → 404). Absent → version courante, comportement historique inchangé.
    `project_id` (optionnel) : explicite le projet quand l'organisation en a
    plusieurs (sinon repli sur le comportement historique).
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

    # Détermination du fichier GeoPackage pour le projet actif (strictement cloisonné par org_id)
    from api.services.gpkg_versions import (
        resoudre_snapshot_pour_lecture, GpkgSimulationError)
    gpkg_target = None
    snap_meta = None
    project_name = "Nouveau Projet"
    cache_org_id = ctx.org_id
    cache_project_id = "none"

    query = db.query(Project).filter(
        Project.org_id == ctx.org_id,
        Project.is_archived.is_(False)
    )
    if project_id:
        query = query.filter(Project.id == project_id)
    project = query.first()

    if project:
        project_name = project.name
        cache_project_id = project.id
        try:
            snap_ctx = resoudre_snapshot_pour_lecture(db, project, snapshot)
            gpkg_target = snap_ctx["path"]
            snap_meta = snap_ctx
        except GpkgSimulationError:
            # Snapshot explicite demandé mais introuvable/hors projet :
            # stealth 404, jamais de repli sur la version courante.
            if snapshot:
                raise HTTPException(status_code=404, detail="Ressource introuvable")
            # Aucun fichier associé au projet courant -> espace vierge (Option B)
            gpkg_target = None

    # Le client reçoit toujours la métadonnée du snapshot réellement servi :
    # c'est la clé de vérification INV-2 (sha256) côté frontend.
    snap_payload = None
    if snap_meta:
        snap_payload = {
            "version_id": snap_meta.get("version_id"),
            "sha256": snap_meta.get("sha256"),
            "est_version_courante": snap_meta.get("est_version_courante"),
            "libelle": snap_meta.get("libelle"),
            "nb_regards": snap_meta.get("nb_regards"),
            "nb_conduites": snap_meta.get("nb_conduites"),
        }

    def _with_snapshot(payload: dict) -> dict:
        if snap_payload:
            return {**payload, "snapshot": snap_payload}
        return payload

    if not gpkg_target:
        empty_response["project_name"] = project_name
        return _with_snapshot(empty_response)

    # Clé de cache content-adressée : org + projet + SHA-256 du GPKG —
    # deux versions ne partagent jamais leurs données cartographiques.
    cache_key = str(gpkg_target)
    try:
        from api.services.gpkg_versions import sha256_fichier
        empreinte = sha256_fichier(gpkg_target)[:16]
        cache_key = f"{cache_org_id}|{cache_project_id}|{empreinte}"
    except Exception:
        pass

    if cache_key in _LAYERS_CACHE and not has_bounds:
        res = dict(_LAYERS_CACHE[cache_key])
        res["project_name"] = project_name
        res["is_empty"] = False
        return _with_snapshot(res)

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
        return _with_snapshot(result)

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
        return _with_snapshot(empty_response)

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

    # Calcul de la bounding box globale du réseau (WGS84 [lat_min, lon_min], [lat_max, lon_max])
    total_bounds = None
    for gdf in gdf_cache_temp.values():
        if not gdf.empty:
            b = gdf.total_bounds
            if total_bounds is None:
                total_bounds = [float(b[0]), float(b[1]), float(b[2]), float(b[3])]
            else:
                total_bounds[0] = min(total_bounds[0], float(b[0]))
                total_bounds[1] = min(total_bounds[1], float(b[1]))
                total_bounds[2] = max(total_bounds[2], float(b[2]))
                total_bounds[3] = max(total_bounds[3], float(b[3]))
    if total_bounds:
        result["bbox"] = [[total_bounds[1], total_bounds[0]], [total_bounds[3], total_bounds[2]]]

    _GDF_CACHE[cache_key] = gdf_cache_temp
    if not has_bounds:
        _LAYERS_CACHE[cache_key] = result

    return _with_snapshot(result)




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
# CENTRE D'AIDE — documentation Markdown rendue en HTML
# ============================================================

_AIDE_DOCS_ROOT = Path("docs")


def _aide_doc_titre(chemin: Path) -> str:
    try:
        for ligne in chemin.read_text(encoding="utf-8").splitlines():
            if ligne.startswith("# "):
                return ligne[2:].strip()
    except Exception:
        pass
    return chemin.stem


def _aide_docs_listing() -> list:
    """Liste des documents normatifs exposés dans le centre d'aide.

    Seuls les .md de premier niveau de docs/ et docs/adr/ sont exposés ;
    _archive_historique/ reste consultable dans le dépôt mais n'est pas
    servi (contenu non normatif).
    """
    items = []
    root = _AIDE_DOCS_ROOT
    if not root.is_dir():
        return items
    for p in sorted(root.glob("*.md")):
        items.append({"id": p.name, "titre": _aide_doc_titre(p), "groupe": "Documents de référence"})
    adr = root / "adr"
    if adr.is_dir():
        for p in sorted(adr.glob("*.md")):
            items.append({"id": f"adr/{p.name}", "titre": _aide_doc_titre(p), "groupe": "Architecture Decision Records"})
    return items


@app.get("/aide", response_class=HTMLResponse)
async def page_aide(request: Request, db=Depends(get_db)):
    """Centre d'aide : documentation produit/technique rendue pour les utilisateurs."""
    user = _get_authenticated_user(request, db)
    if not user:
        return RedirectResponse(url="/login?next=/aide", status_code=302)
    try:
        with open("templates/aide.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse("""
        <h1>Erreur</h1>
        <p>Le centre d'aide n'est pas disponible.</p>
        <a href="/">Retour au cockpit</a>
        """, status_code=404)


@app.get("/aide/docs")
async def aide_docs_index(request: Request, db=Depends(get_db)):
    """Index JSON des documents exposés dans le centre d'aide."""
    user = _get_authenticated_user(request, db)
    if not user:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"detail": "Non authentifié"})
    return {"documents": _aide_docs_listing()}


@app.get("/aide/doc/{doc_path:path}", response_class=HTMLResponse)
async def aide_doc_render(doc_path: str, request: Request, db=Depends(get_db)):
    """Rend un document Markdown normatif en fragment HTML.

    Whitelist stricte : uniquement docs/*.md et docs/adr/*.md.
    Les archives (_archive_historique/) et tout chemin traversant
    (..) sont refusés en stealth 404.
    """
    import re
    import markdown as _md

    user = _get_authenticated_user(request, db)
    if not user:
        return RedirectResponse(url="/login?next=/aide", status_code=302)

    doc_path = doc_path.strip().lstrip("/")
    if not doc_path.lower().endswith(".md") or ".." in doc_path.split("/"):
        raise HTTPException(status_code=404, detail="Ressource introuvable")

    root = _AIDE_DOCS_ROOT.resolve()
    cible = (root / doc_path).resolve()
    try:
        cible.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=404, detail="Ressource introuvable")
    if "_archive_historique" in cible.parts or not cible.is_file():
        raise HTTPException(status_code=404, detail="Ressource introuvable")

    try:
        texte = cible.read_text(encoding="utf-8")
    except Exception:
        raise HTTPException(status_code=404, detail="Ressource introuvable")

    html = _md.markdown(
        texte,
        extensions=["tables", "fenced_code", "toc", "sane_lists", "attr_list"],
    )

    # Réécrit les liens relatifs *.md vers le routeur /aide/doc/ pour que la
    # navigation interne reste dans le centre d'aide (le HTML rendu contient
    # des href="...", plus la syntaxe Markdown d'origine).
    def _lien(m):
        cible_lien = m.group(1)
        if cible_lien.startswith(("http://", "https://", "/", "#", "mailto:")):
            return m.group(0)
        return f'href="/aide/doc/{cible_lien}{m.group(2) or ""}"'

    html = re.sub(r'href="([^"\s]+?\.md)(#[^"\s]*)?"', _lien, html)
    return HTMLResponse(
        f'<article class="aide-doc">{html}</article>',
        headers={"Cache-Control": "no-cache"},
    )


# ============================================================
# INCLUSION DES ROUTES
# ============================================================

app.include_router(auth.router, prefix="/api/v1", tags=["Authentification & Multi-Tenant"])
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



