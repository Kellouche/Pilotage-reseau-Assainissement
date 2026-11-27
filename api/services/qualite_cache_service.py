# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Cache qualite (rapport + topologie) et helpers de resolution projet/GPKG pour les endpoints qualite (extraits de routes/qualite.py).
================================================================================
"""

import hashlib
import json
import os
import sqlite3
import csv
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import Project
from api.core.security import require_role, TenantContext, get_tenant_context


_cache_qualite = {
    "gpkg_path": None,
    "rapport": None,
    "timestamp": None,
    "empreinte_aux": None,
    "duree_validite": 3600  # 1 heure en secondes
}

# Cache topologique pour requêtes rapides de snapping et raccordement
_cache_topologie = {
    "gpkg_path": None,
    "mtime": None,
    "resolveur": None,
    "pipes": None,
    "regards": None,
    "rejets": None,
    "pipes_m": None,
    "regards_m": None,
    "rejets_m": None
}


def _empreinte_couches_aux(db: Session, ctx: TenantContext) -> str:
    """
    Empreinte des couches auxiliaires du projet (spec §6 : le cache doit
    être invalidé par le mtime GPKG ET les versions des couches aux).
    """
    try:
        from api.models import Project, ProjectAuxLayer

        project = db.query(Project).filter(
            Project.org_id == ctx.org_id,
            Project.is_archived.is_(False),
        ).first()
        if project is None:
            return ""
        layers = db.query(ProjectAuxLayer).filter(
            ProjectAuxLayer.project_id == project.id,
            ProjectAuxLayer.org_id == ctx.org_id,
        ).order_by(ProjectAuxLayer.id).all()
        brut = "|".join(
            f"{l.id}:{l.type}:{l.statut}:{l.storage_key}:{l.nb_features}:{l.gpkg_version_id}"
            for l in layers
        )
        return hashlib.sha1(brut.encode("utf-8")).hexdigest() if brut else ""
    except Exception:
        return ""


def _get_disk_cache_path(gpkg_path: Path) -> Path:
    return gpkg_path.with_suffix(".qualite_cache.json")


def _charger_cache_disque(gpkg_path: Path, empreinte_aux: str = "") -> Optional[Dict[str, Any]]:
    try:
        cache_file = _get_disk_cache_path(gpkg_path)
        if cache_file.exists():
            if cache_file.stat().st_mtime >= gpkg_path.stat().st_mtime:
                with open(cache_file, "r", encoding="utf-8") as f:
                    rapport = json.load(f)
                # Invalider les rapports produits par un ancien moteur
                # ou par d'autres versions des couches auxiliaires.
                if (rapport.get("moteur") == "v2.1"
                        and rapport.get("_empreinte_aux", "") == empreinte_aux):
                    return rapport
    except Exception as e:
        print(f"[CACHE QUALITE] Erreur lecture cache disque: {e}")
    return None


# ---------------------------------------------------------------------------
# Cycle de vie des anomalies (spec V2.1 §5) — table qualite_anomalie_statuts
# ---------------------------------------------------------------------------

STATUTS_ANOMALIE_VALIDES = {"a_traiter", "revu", "corrige"}


def _projet_et_version(db: Session, ctx: TenantContext) -> Tuple[Optional[Any], str]:
    """Retourne (project, gpkg_version_id) du projet actif du tenant."""
    from api.models import Project
    from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet_avec_meta

    project = db.query(Project).filter(
        Project.org_id == ctx.org_id,
        Project.is_archived.is_(False),
    ).first()
    if project is None:
        return None, ""
    _chemin, meta = resoudre_gpkg_effectif_pour_projet_avec_meta(db, project)
    return project, (meta or {}).get("version_id") or ""


def _cle_anomalie(categorie: str, anomalie: Dict[str, Any], version_id: str) -> str:
    """Clé stable SHA-1(type | objet | version GPKG) — spec §5."""
    objet = "|".join(str(anomalie.get(k) or "") for k in (
        "id_conduite", "id_amont", "id_aval", "fid", "id_regard", "node_id"))
    brut = f"{categorie}|{objet}|{version_id or 'sans_version'}"
    return hashlib.sha1(brut.encode("utf-8")).hexdigest()


def _appliquer_statuts_anomalies(rapport: Dict[str, Any], db: Session,
                                 ctx: TenantContext) -> Dict[str, Any]:
    """Enrichit chaque anomalie du rapport avec cle_anomalie + statut courant."""
    try:
        from api.models import QualiteAnomalieStatut

        project, version_id = _projet_et_version(db, ctx)
        if project is None:
            return rapport
        rows = db.query(QualiteAnomalieStatut).filter(
            QualiteAnomalieStatut.project_id == project.id,
            QualiteAnomalieStatut.org_id == ctx.org_id,
        ).all()
        statuts = {r.cle_anomalie: r.statut for r in rows}
        for categorie, items in (rapport.get("anomalies") or {}).items():
            for a in items:
                cle = _cle_anomalie(categorie, a, version_id)
                a["cle_anomalie"] = cle
                a["statut"] = statuts.get(cle, "a_traiter")
    except Exception as e:
        print(f"[QUALITE] Statuts anomalies indisponibles : {e}")
    return rapport




def _construire_contexte_terrain_qualite(db: Session, ctx: TenantContext) -> Optional[Dict[str, Any]]:
    """
    Construit le contexte altimétrique V2.1 (spec docs/05_CONTROLE_QUALITE_V2.md)
    à partir de la première couche `altimetrie_points` opérationnelle du projet :
    suspects d'inversion de sens d'écoulement + cotes radier estimées par regard.
    Retourne None si aucune couche topo exploitable n'existe — l'analyse
    qualité ne doit jamais échouer pour autant.
    """
    try:
        from api.models import Project, ProjectAuxLayer
        from api.services import aux_altimetrie_service as alt

        project = db.query(Project).filter(
            Project.org_id == ctx.org_id,
            Project.is_archived.is_(False),
        ).first()
        if project is None:
            return None

        couche = db.query(ProjectAuxLayer).filter(
            ProjectAuxLayer.project_id == project.id,
            ProjectAuxLayer.org_id == ctx.org_id,
            ProjectAuxLayer.type == "altimetrie_points",
            ProjectAuxLayer.statut == "ok",
        ).first()
        if couche is None:
            return None

        err, _couche, regards_gdf, canas_gdf, artefact = alt._charger_contexte_altimetrie(
            db, ctx.org_id, project.id, couche.id)
        if err is not None:
            return None

        apercu = alt.calculer_apercu_terrain(regards_gdf, canas_gdf, artefact)
        eco = alt.analyser_ecoulement_terrain(regards_gdf, canas_gdf, artefact)

        return {
            "suspects_ecoulement": eco.get("suspects") or [],
            "par_regard": apercu.get("par_regard") or {},
            "couverture_pct": (apercu.get("couverture") or {}).get("pct"),
            "layer_nom": getattr(_couche, "nom", None),
        }
    except Exception as e:
        print(f"[QUALITE] Contexte terrain indisponible : {e}")
        return None


def _sauvegarder_cache_disque(gpkg_path: Path, rapport: Dict[str, Any]):
    try:
        cache_file = _get_disk_cache_path(gpkg_path)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(rapport, f, ensure_ascii=False)
    except Exception as e:
        print(f"[CACHE QUALITE] Erreur ecriture cache disque: {e}")


def reinitialiser_cache_qualite(gpkg_path: Optional[Path] = None):
    """Purge le cache de qualité lors d'un changement de modèle/réseau."""
    global _cache_qualite
    if gpkg_path:
        cache_file = _get_disk_cache_path(gpkg_path)
        if cache_file.exists():
            try:
                cache_file.unlink()
            except Exception:
                pass
    elif _cache_qualite.get("gpkg_path"):
        try:
            old_p = Path(_cache_qualite["gpkg_path"]).with_suffix(".qualite_cache.json")
            if old_p.exists():
                old_p.unlink()
        except Exception:
            pass

    _cache_qualite["rapport"] = None
    _cache_qualite["timestamp"] = None
    _cache_qualite["gpkg_path"] = None

    global _cache_topologie
    _cache_topologie["gpkg_path"] = None
    _cache_topologie["mtime"] = None
    _cache_topologie["resolveur"] = None
    _cache_topologie["pipes"] = None
    _cache_topologie["regards"] = None
    _cache_topologie["rejets"] = None
    _cache_topologie["pipes_m"] = None
    _cache_topologie["regards_m"] = None
    _cache_topologie["rejets_m"] = None


def get_active_project_and_gpkg(db: Session, tenant_ctx: Optional[TenantContext] = None):
    """Résout le chemin du GeoPackage et le nom du projet actif (version courante, 3C.0)."""
    from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet
    if tenant_ctx and tenant_ctx.org_id:
        project = db.query(Project).filter(
            Project.org_id == tenant_ctx.org_id,
            Project.is_archived.is_(False)
        ).first()
        if not project:
            return None, "Aucun réseau"
        chemin = resoudre_gpkg_effectif_pour_projet(db, project)
        if chemin is not None:
            return chemin, project.name
        return None, project.name

    project = db.query(Project).filter(Project.is_archived.is_(False)).first()
    if project:
        chemin = resoudre_gpkg_effectif_pour_projet(db, project)
        if chemin is not None:
            return chemin, project.name

    demo_cand = Path("data/demo_reseau.gpkg")
    if demo_cand.exists():
        return demo_cand, "Quartier Témoin (Démo)"

    return None, "Aucun réseau"
