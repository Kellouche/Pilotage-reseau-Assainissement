# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Catalogue de jeux de donnees et chargement reseau (demo, master, benchmark) (extrait de routes/network.py)
================================================================================
"""

import json
import logging
import re
from pathlib import Path
from typing import List, Optional

import geopandas as gpd
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from api import schemas, crud
from api.database import get_db
from api.models import Project, Organization
from api.core.security import (
    get_tenant_context,
    get_tenant_context_optional,
    require_role,
    TenantContext,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/network", tags=["Réseau"])

from api.routes.network import _enregistrer_version_gpkg


AVAILABLE_DATASETS = [
    {
        "id": "epa_example1",
        "title": "Drainage de Site",
        "short_name": "Drainage de Site",
        "category": "epa_certified",
        "badge": "EPA Certifié",
        "badge_color": "#10b981",
        "icon": "fa-tint",
        "icon_color": "#38bdf8",
        "description": "Modèle standard officiel US EPA 5.2. Drainage pluvial direct avec cotes de radier et écoulement gravitaire.",
        "nodes_count": 7,
        "pipes_count": 6,
        "gpkg_path": "data/benchmarks/epa_example1_drainage.gpkg",
        "is_official": True
    },
    {
        "id": "epa_example3",
        "title": "Réseau Unitaire & Déversoirs",
        "short_name": "Réseau Unitaire",
        "category": "epa_certified",
        "badge": "EPA Certifié",
        "badge_color": "#10b981",
        "icon": "fa-water",
        "icon_color": "#a855f7",
        "description": "Modèle de référence EPA pour l'analyse des surcharges, déversoirs d'orage (weir) et refoulements.",
        "nodes_count": 9,
        "pipes_count": 8,
        "gpkg_path": "data/benchmarks/epa_example3_combined.gpkg",
        "is_official": True
    },
    {
        "id": "epa_example4",
        "title": "Bassin de Rétention & Stockage",
        "short_name": "Bassin de Rétention",
        "category": "epa_certified",
        "badge": "EPA Certifié",
        "badge_color": "#10b981",
        "icon": "fa-database",
        "icon_color": "#f59e0b",
        "description": "Modèle officiel de stockage / rétention (Storage Unit) avec régulation de débit par orifice de vidange.",
        "nodes_count": 4,
        "pipes_count": 2,
        "gpkg_path": "data/benchmarks/epa_example4_storage.gpkg",
        "is_official": True
    },
    {
        "id": "epa_example5",
        "title": "Station de Pompage & Refoulement",
        "short_name": "Station de Pompage",
        "category": "epa_certified",
        "badge": "EPA Certifié",
        "badge_color": "#10b981",
        "icon": "fa-bolt",
        "icon_color": "#ef4444",
        "description": "Station de relevage équipée de pompes avec courbe caractéristique et conduite de refoulement sous pression.",
        "nodes_count": 4,
        "pipes_count": 2,
        "gpkg_path": "data/benchmarks/epa_example5_pumping.gpkg",
        "is_official": True
    },
    {
        "id": "epa_example6",
        "title": "Techniques Alternatives LID",
        "short_name": "Techniques LID",
        "category": "epa_certified",
        "badge": "EPA Certifié",
        "badge_color": "#10b981",
        "icon": "fa-leaf",
        "icon_color": "#22c55e",
        "description": "Infrastructures vertes et noues végétalisées (Low Impact Development) pour la temporisation des crues à la source.",
        "nodes_count": 14,
        "pipes_count": 13,
        "gpkg_path": "data/benchmarks/epa_example6_lid.gpkg",
        "is_official": True
    },
    {
        "id": "demo_temoin",
        "title": "Quartier Témoin (Démo Pratique)",
        "short_name": "Quartier Témoin",
        "category": "demo",
        "badge": "Échantillon Démo",
        "badge_color": "#0284c7",
        "icon": "fa-city",
        "icon_color": "#38bdf8",
        "description": "Quartier urbain de 59 regards et 58 canalisations. Découpage hydrologique en sous-bassins Voronoï.",
        "nodes_count": 59,
        "pipes_count": 58,
        "gpkg_path": "data/demo_reseau.gpkg",
        "is_official": False
    },
    {
        "id": "ville_complete",
        "title": "Réseau Réel Ville (Master Métropole)",
        "short_name": "Métropole Chlef",
        "category": "master",
        "badge": "Réseau Réel Complet",
        "badge_color": "#8b5cf6",
        "icon": "fa-sitemap",
        "icon_color": "#8b5cf6",
        "description": "Patrimoine réel complet de la métropole (+11 000 canalisations et regards, STEP, stations de pompage).",
        "nodes_count": 11000,
        "pipes_count": 11000,
        "gpkg_path": r"D:\IA Water Data Analysis\Assainissement\Assainissement_Ville.gpkg",
        "is_official": False
    }
]


@router.get("/datasets")
def list_available_datasets(
    response: Response,
    tenant_ctx: Optional[TenantContext] = Depends(get_tenant_context_optional),
    db: Session = Depends(get_db)
):
    """Retourne la liste des jeux de données et modèles de référence disponibles ainsi que le projet en cours."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    active_project = None
    try:
        if tenant_ctx and tenant_ctx.org_id:
            proj = db.query(Project).filter(Project.org_id == tenant_ctx.org_id, Project.is_archived.is_(False)).first()
            if proj:
                from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet
                chemin_eff = resoudre_gpkg_effectif_pour_projet(db, proj)
                if chemin_eff is not None:
                    active_project = {
                        "id": proj.id,
                        "name": proj.name or "Projet Réseau Actif",
                        "pipes_count": proj.pipes_count or 0,
                        "nodes_count": proj.nodes_count or 0,
                        "gpkg_path": str(chemin_eff)
                    }
    except Exception as e:
        print(f"[datasets] Erreur extraction projet actif: {e}", flush=True)

    return {"status": "ok", "datasets": AVAILABLE_DATASETS, "active_project": active_project}


@router.post("/load-dataset/{dataset_id}")
def load_benchmark_dataset(
    dataset_id: str,
    ctx: TenantContext = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    """Charge l'un des jeux de données officiels EPA ou de démonstration pour l'organisation active."""
    ds = next((d for d in AVAILABLE_DATASETS if d["id"] == dataset_id), None)
    if not ds:
        raise HTTPException(status_code=404, detail="Jeu de données introuvable.")

    target_path = Path(ds["gpkg_path"])
    if not target_path.exists():
        raise HTTPException(status_code=500, detail=f"Fichier réseau introuvable : {ds['gpkg_path']}")

    if ds["id"] == "ville_complete" and not (ctx.user and ctx.user.is_superadmin):
        raise HTTPException(status_code=403, detail="Seul un SuperAdmin peut charger le réseau réel complet de la ville.")

    org_id = ctx.org_id

    project = db.query(Project).filter(
        Project.org_id == org_id,
        Project.is_archived.is_(False)
    ).first()

    if not project:
        project = Project(
            org_id=org_id,
            name=ds["title"],
            description=ds["description"],
        )
        db.add(project)
        db.flush()

    project.name = ds["title"]
    project.source_gpkg_key = str(target_path)
    _enregistrer_version_gpkg(db, project, target_path, filename_original=target_path.name)
    project.nodes_count = ds["nodes_count"]
    project.pipes_count = ds["pipes_count"]
    db.commit()

    # Les résultats de simulation sont isolés par org/projet (3D.5) :
    # plus d'état global à effacer lors d'un rechargement de réseau.
    try:
        from api.routes.qualite import reinitialiser_cache_qualite
        reinitialiser_cache_qualite()
    except Exception:
        pass
    try:
        from api.routes.qualite import reinitialiser_cache_qualite
        reinitialiser_cache_qualite()
    except Exception:
        pass
    try:
        from api.main import reset_layers_cache
        reset_layers_cache()
    except Exception:
        pass
    try:
        from api.routes.clusters import _reset_graph_cache
        _reset_graph_cache()
    except Exception:
        pass

    return {
        "status": "ok",
        "message": f"Jeu de données '{ds['title']}' chargé avec succès.",
        "project": {
            "id": project.id,
            "name": project.name,
            "badge": ds["badge"],
            "nodes_count": project.nodes_count,
            "pipes_count": project.pipes_count
        }
    }


@router.post("/load-demo")
def load_demo_network(
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Charge le réseau d'exemple Démo (échantillon isolé et sécurisé) pour le projet actif."""
    demo_path = Path("data/demo_reseau.gpkg")
    if not demo_path.exists():
        raise HTTPException(status_code=500, detail="Fichier démo introuvable sur le serveur.")

    project = db.query(Project).filter(
        Project.org_id == tenant_ctx.org_id,
        Project.is_archived.is_(False)
    ).first()

    if not project:
        project = Project(
            org_id=tenant_ctx.org_id,
            name="Projet Démo — Quartier Témoin",
            description="Échantillon de démonstration préconfiguré.",
        )
        db.add(project)
        db.flush()

    project.name = "Projet Démo — Quartier Témoin"
    project.source_gpkg_key = str(demo_path)
    _enregistrer_version_gpkg(db, project, demo_path, filename_original=demo_path.name)
    project.nodes_count = 59
    project.pipes_count = 58
    project.outfalls_count = 1
    db.commit()


    try:
        from api.routes.qualite import reinitialiser_cache_qualite
        reinitialiser_cache_qualite()
    except Exception:
        pass
    try:
        from api.main import reset_layers_cache
        reset_layers_cache()
    except Exception:
        pass
    try:
        from api.routes.clusters import _reset_graph_cache
        _reset_graph_cache()
    except Exception:
        pass

    return {
        "status": "ok",
        "message": "Réseau d'exemple Démo chargé avec succès.",
        "project": {
            "id": project.id,
            "name": project.name,
            "nodes_count": project.nodes_count,
            "pipes_count": project.pipes_count,
        }
    }


@router.post("/load-master")
def load_master_network(
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Charge le réseau complet réel (Réservé au SuperAdmin / Direction de projet)."""
    user = tenant_ctx.user
    if not user or not user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès restreint. Seul le SuperAdmin peut charger le réseau réel complet de la ville."
        )

    master_path = Path(r"D:\IA Water Data Analysis\Assainissement\Assainissement_Ville.gpkg")
    if not master_path.exists():
        raise HTTPException(status_code=500, detail="Fichier maître introuvable sur le serveur.")

    project = db.query(Project).filter(
        Project.org_id == tenant_ctx.org_id,
        Project.is_archived.is_(False)
    ).first()

    if not project:
        project = Project(
            org_id=tenant_ctx.org_id,
            name="Réseau Ville (Projet Réel)",
            description="Réseau complet d'assainissement.",
        )
        db.add(project)
        db.flush()

    project.name = "Réseau Ville (Projet Réel)"
    project.source_gpkg_key = str(master_path)
    _enregistrer_version_gpkg(db, project, master_path, filename_original=master_path.name)
    project.nodes_count = 11000
    project.pipes_count = 11000
    db.commit()


    try:
        from api.routes.qualite import reinitialiser_cache_qualite
        reinitialiser_cache_qualite()
    except Exception:
        pass
    try:
        from api.main import reset_layers_cache
        reset_layers_cache()
    except Exception:
        pass
    try:
        from api.routes.clusters import _reset_graph_cache
        _reset_graph_cache()
    except Exception:
        pass

    return {
        "status": "ok",
        "message": "Réseau réel complet de la ville chargé pour votre session administrateur.",
        "project": {
            "id": project.id,
            "name": project.name,
        }
    }
