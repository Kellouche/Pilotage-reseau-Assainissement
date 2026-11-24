"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Endpoints de contrôle qualité topologique et audit de connectivité
================================================================================
"""

import asyncio
import hashlib
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional, Tuple
import json
import os
import csv
from pathlib import Path
from datetime import datetime

from api.database import get_db
from api.models import Project
from api.core.security import require_role, TenantContext
from src.analyse_qualite_gpkg import analyser_qualite_gpkg

router = APIRouter(prefix="/qualite", tags=["Qualité réseau"])

# Cache global pour éviter de recalculer à chaque requête
_cache_qualite = {
    "gpkg_path": None,
    "rapport": None,
    "timestamp": None,
    "empreinte_aux": None,
    "duree_validite": 3600  # 1 heure en secondes
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


@router.post("/anomalies/statut", response_model=Dict[str, Any])
async def definir_statut_anomalie(
    request: Dict[str, Any],
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_role("engineer"))
):
    """
    Définit le statut d'une anomalie de qualité (a_traiter / revu / corrige).
    Corps : {"cle_anomalie": str, "type_anomalie": str, "statut": str,
             "commentaire": str?, "id_conduite": str?}
    """
    from api.models import QualiteAnomalieStatut

    cle = str(request.get("cle_anomalie") or "").strip()
    type_anomalie = str(request.get("type_anomalie") or "").strip()
    statut = str(request.get("statut") or "").strip()
    if not cle or len(cle) != 40:
        raise HTTPException(status_code=400, detail="cle_anomalie invalide (SHA-1 attendu)")
    if statut not in STATUTS_ANOMALIE_VALIDES:
        raise HTTPException(
            status_code=400,
            detail=f"statut invalide — valeurs acceptées : {sorted(STATUTS_ANOMALIE_VALIDES)}")

    project, version_id = _projet_et_version(db, ctx)
    if project is None:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    row = db.query(QualiteAnomalieStatut).filter(
        QualiteAnomalieStatut.project_id == project.id,
        QualiteAnomalieStatut.cle_anomalie == cle,
    ).first()
    if row is None:
        row = QualiteAnomalieStatut(
            org_id=ctx.org_id,
            project_id=project.id,
            gpkg_version_id=version_id or None,
            cle_anomalie=cle,
            type_anomalie=type_anomalie or "inconnu",
            id_conduite=request.get("id_conduite"),
            statut=statut,
            commentaire=request.get("commentaire"),
            updated_by_id=ctx.user.id if ctx.user else None,
        )
        db.add(row)
    else:
        row.statut = statut
        if request.get("commentaire") is not None:
            row.commentaire = request.get("commentaire")
        if request.get("type_anomalie"):
            row.type_anomalie = type_anomalie
        if request.get("id_conduite") is not None:
            row.id_conduite = request.get("id_conduite")
        row.updated_by_id = ctx.user.id if ctx.user else None

    db.commit()
    db.refresh(row)
    return {"statut": "ok", "anomalie": row.to_dict()}


@router.post("/anomalies/{cle_anomalie}/statut", response_model=Dict[str, Any])
async def definir_statut_anomalie_par_cle(
    cle_anomalie: str,
    request: Dict[str, Any],
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_role("engineer"))
):
    """
    Forme canonique spec §6 : POST /anomalies/{cle_anomalie}/statut.
    Corps : {"statut": "a_traiter|revu|corrige", "commentaire": str?,
             "type_anomalie": str?, "id_conduite": str?}
    """
    corps = dict(request or {})
    corps["cle_anomalie"] = cle_anomalie
    return await definir_statut_anomalie(corps, db, ctx)


@router.get("/statuts", response_model=Dict[str, Any])
async def lister_statuts_anomalies(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_role("viewer"))
):
    """Liste les statuts de cycle de vie des anomalies du projet actif."""
    from api.models import QualiteAnomalieStatut

    project, version_id = _projet_et_version(db, ctx)
    if project is None:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    rows = db.query(QualiteAnomalieStatut).filter(
        QualiteAnomalieStatut.project_id == project.id,
        QualiteAnomalieStatut.org_id == ctx.org_id,
    ).all()
    distribution = {"a_traiter": 0, "revu": 0, "corrige": 0}
    for r in rows:
        distribution[r.statut] = distribution.get(r.statut, 0) + 1

    return {
        "gpkg_version_id": version_id or None,
        "nb_statuts": len(rows),
        "distribution": distribution,
        "statuts": [r.to_dict() for r in rows],
    }


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


@router.get("/analyse", response_model=Dict[str, Any])
async def analyser_qualite_reseau(
    force_refresh: bool = False,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_role("viewer"))
):
    """
    Analyse complète de la qualité du réseau d'assainissement actif.
    Exécute un audit géométrique, attributaire et topologique dynamique sur le GeoPackage.
    """
    global _cache_qualite

    gpkg_target, project_name = get_active_project_and_gpkg(db, ctx)
    if not gpkg_target or not gpkg_target.exists():
        raise HTTPException(
            status_code=404,
            detail="Aucun fichier réseau GeoPackage actif trouvé pour le projet."
        )

    maintenant = datetime.now().timestamp()
    empreinte_aux = _empreinte_couches_aux(db, ctx)
    if (not force_refresh and
        _cache_qualite["rapport"] is not None and
        _cache_qualite["gpkg_path"] == str(gpkg_target) and
        _cache_qualite.get("empreinte_aux") == empreinte_aux and
        _cache_qualite["timestamp"] is not None and
        (maintenant - _cache_qualite["timestamp"]) < _cache_qualite["duree_validite"]):
        return _appliquer_statuts_anomalies(_cache_qualite["rapport"], db, ctx)

    # Tentative de récupération depuis le cache persistant sur disque (instantané <50ms)
    if not force_refresh:
        rapport_disque = _charger_cache_disque(gpkg_target, empreinte_aux)
        if rapport_disque:
            _cache_qualite["rapport"] = rapport_disque
            _cache_qualite["timestamp"] = maintenant
            _cache_qualite["gpkg_path"] = str(gpkg_target)
            _cache_qualite["empreinte_aux"] = empreinte_aux
            return _appliquer_statuts_anomalies(rapport_disque, db, ctx)

    try:
        contexte_terrain = _construire_contexte_terrain_qualite(db, ctx)
        rapport = await asyncio.to_thread(
            analyser_qualite_gpkg, gpkg_target, project_name, contexte_terrain)
        rapport["_empreinte_aux"] = empreinte_aux

        _sauvegarder_cache_disque(gpkg_target, rapport)

        _cache_qualite["rapport"] = rapport
        _cache_qualite["timestamp"] = maintenant
        _cache_qualite["gpkg_path"] = str(gpkg_target)
        _cache_qualite["empreinte_aux"] = empreinte_aux

        return _appliquer_statuts_anomalies(rapport, db, ctx)

    except Exception as e:
        print(f"Erreur lors de l'analyse qualité: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de l'analyse de qualité: {str(e)}"
        )


@router.get("/diagnostic", response_model=Dict[str, Any])
async def diagnostic_tunnel(
    ctx: TenantContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db)
):
    """
    Endpoint allégé pour le tunnel de préparation.
    Renvoie le résumé des anomalies topologiques.
    """
    try:
        # Forcer la reconstruction pour avoir les anomalies fraîches
        from api.routes.clusters import _get_graph, _reset_graph_cache
        _reset_graph_cache()
        G = _get_graph(db, org_id=ctx.org_id)
        if not G:
            return {"anomalies_count": 0, "orphelins_count": 0, "anomalies": []}
            
        anomalies_topologiques = G.graph.get('anomalies_topologiques', [])
        
        # Formater pour le frontend
        formatted_anomalies = []
        for a in anomalies_topologiques:
            formatted_anomalies.append({
                "type": a.get("type", "anomalie"),
                "troncon_id": a.get("troncon_id", "Inconnu"),
                "detail": a.get("detail", "")
            })
            
        return {
            "anomalies_count": len(formatted_anomalies),
            "orphelins_count": sum(1 for a in formatted_anomalies if a['type'] == 'noeud_orphelin'),
            "anomalies": formatted_anomalies
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


async def _assurer_rapport(db: Session, ctx: TenantContext, force_refresh: bool = False) -> Dict[str, Any]:
    """Retourne le rapport qualité en cache (mémoire ou disque), en le recalculant si besoin."""
    global _cache_qualite

    gpkg_target, project_name = get_active_project_and_gpkg(db, ctx)
    if not gpkg_target or not gpkg_target.exists():
        if _cache_qualite.get("rapport") is not None:
            return _appliquer_statuts_anomalies(_cache_qualite["rapport"], db, ctx)
        raise HTTPException(
            status_code=404,
            detail="Aucun fichier réseau GeoPackage actif trouvé pour l'organisation."
        )

    maintenant = datetime.now().timestamp()
    empreinte_aux = _empreinte_couches_aux(db, ctx)

    # 1. Cache mémoire (si même GPKG, même empreinte couches aux, et non expiré)
    if (not force_refresh and
        _cache_qualite.get("rapport") is not None and
        _cache_qualite.get("gpkg_path") == str(gpkg_target) and
        _cache_qualite.get("empreinte_aux") == empreinte_aux and
        _cache_qualite.get("timestamp") is not None and
        (maintenant - _cache_qualite["timestamp"]) < _cache_qualite.get("duree_validite", 3600)):
        return _appliquer_statuts_anomalies(_cache_qualite["rapport"], db, ctx)

    # 2. Cache persistant sur disque (instantané <50ms)
    if not force_refresh:
        rapport_disque = _charger_cache_disque(gpkg_target, empreinte_aux)
        if rapport_disque:
            _cache_qualite.update({
                "rapport": rapport_disque,
                "timestamp": maintenant,
                "gpkg_path": str(gpkg_target),
                "empreinte_aux": empreinte_aux,
            })
            return _appliquer_statuts_anomalies(rapport_disque, db, ctx)

    # 3. Recalcul complet via moteur V2.1
    contexte_terrain = _construire_contexte_terrain_qualite(db, ctx)
    rapport = await asyncio.to_thread(
        analyser_qualite_gpkg, gpkg_target, project_name, contexte_terrain)
    rapport["_empreinte_aux"] = empreinte_aux
    _sauvegarder_cache_disque(gpkg_target, rapport)
    _cache_qualite.update({
        "rapport": rapport,
        "timestamp": maintenant,
        "gpkg_path": str(gpkg_target),
        "empreinte_aux": empreinte_aux,
    })
    return _appliquer_statuts_anomalies(rapport, db, ctx)


@router.get("/anomalies/{type_anomalie}", response_model=Dict[str, Any])
async def get_anomalies_par_type(
    type_anomalie: str,
    cursor: int = 0,
    limit: int = 500,
    force_refresh: bool = False,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_role("viewer"))
):
    """
    Récupère les anomalies d'un type spécifique.

    Types disponibles:
    - conduites_sans_regards
    - troncons_orphelins
    - champs_manquants
    - geometries_invalides
    - pentes_suspectes
    - incoherences_amont_aval
    - inversions_sens_ecoulement
    - deconnexions_spatiales
    - donnees_manquantes
    - discontinuites_pose
    - capacite_debit

    Pagination : `cursor` (offset, défaut 0) et `limit` (défaut 500,
    max 2000). La réponse inclut `total`, `cursor` et `next_cursor`.
    """
    rapport = await _assurer_rapport(db, ctx, force_refresh=force_refresh)
    anomalies = rapport.get("anomalies", {})

    if type_anomalie not in anomalies:
        raise HTTPException(
            status_code=404,
            detail=f"Type d'anomalie '{type_anomalie}' non trouvé. Types disponibles: {list(anomalies.keys())}"
        )

    toutes = anomalies[type_anomalie]
    cursor = max(0, int(cursor or 0))
    limit = min(2000, max(1, int(limit or 500)))
    page = toutes[cursor:cursor + limit]
    next_cursor = cursor + limit if cursor + limit < len(toutes) else None

    return {
        "type_anomalie": type_anomalie,
        "nombre_anomalies": len(toutes),
        "total": len(toutes),
        "cursor": cursor,
        "limit": limit,
        "next_cursor": next_cursor,
        "anomalies": page,
        "severite_distribution": _calculer_distribution_severite(toutes)
    }


@router.get("/anomalies.geojson", response_model=Dict[str, Any])
async def get_anomalies_geojson(
    type: Optional[str] = None,
    severite: Optional[str] = None,
    statut: Optional[str] = None,
    inclure_manquants: bool = False,
    force_refresh: bool = False,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_role("viewer"))
):
    """
    Couche GeoJSON (WGS84) de toutes les anomalies localisées — alimente la
    carte Leaflet clusterisée. Filtres : type (catégorie), severite, statut.
    Par défaut, inclure_manquants=False pour éviter de transférer inutilement
    les ~9 000 points informatifs N3, réduisant le payload de 5 Mo à ~180 Ko.
    """
    rapport = await _assurer_rapport(db, ctx, force_refresh=force_refresh)
    anomalies = rapport.get("anomalies", {})

    categories = [type] if type in anomalies else list(anomalies.keys())
    features = []
    for categorie in categories:
        if categorie == "donnees_manquantes" and not inclure_manquants and type != "donnees_manquantes" and severite != "informatif":
            continue
        for a in anomalies.get(categorie, []):
            if severite and a.get("severite") != severite:
                continue
            if statut and a.get("statut", "a_traiter") != statut:
                continue
            lat, lon = a.get("latitude"), a.get("longitude")
            if lat is None or lon is None:
                continue
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(lon), float(lat)],
                },
                "properties": {
                    "categorie": categorie,
                    "type": a.get("type"),
                    "id_conduite": a.get("id_conduite"),
                    "id_amont": a.get("id_amont"),
                    "id_aval": a.get("id_aval"),
                    "severite": a.get("severite"),
                    "statut": a.get("statut", "a_traiter"),
                    "cle_anomalie": a.get("cle_anomalie"),
                    "provenance": a.get("provenance"),
                    "description": a.get("description"),
                    "distance_m": a.get("distance_m"),
                    "ecart_terrain_m": a.get("ecart_terrain_m"),
                    "pente_contre_pct": a.get("pente_contre_pct"),
                    "confiance": a.get("confiance"),
                },
            })

    return {
        "type": "FeatureCollection",
        "features": features,
        "nb_features": len(features),
        "filtres": {"type": type, "severite": severite, "statut": statut},
    }


@router.get("/synthese", response_model=Dict[str, Any])
async def get_synthese_qualite(
    force_refresh: bool = False,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_role("viewer"))
):
    """
    Verdict global + couverture altimétrique + top 3 actions correctives
    (spec §7 — bandeau de synthèse du cockpit).
    """
    rapport = await _assurer_rapport(db, ctx, force_refresh=force_refresh)
    anomalies = rapport.get("anomalies", {})
    scores = rapport.get("scores_qualite", {})
    stats = rapport.get("statistiques_globales", {})

    nb_pipes = stats.get("nb_conduites") or 1
    par_severite = {"critique": 0, "majeure": 0, "mineure": 0, "informatif": 0}
    par_categorie = {}
    nb_a_traiter = 0
    for categorie, items in anomalies.items():
        par_categorie[categorie] = len(items)
        for a in items:
            sev = a.get("severite", "mineure")
            par_severite[sev] = par_severite.get(sev, 0) + 1
            if a.get("statut", "a_traiter") == "a_traiter":
                nb_a_traiter += 1

    topologie = (scores.get("topologie") or {}).get("score_qualite")
    hydraulique = (scores.get("hydraulique") or {}).get("score_qualite")
    altimetrie = scores.get("altimetrie") or {}
    couverture_pct = altimetrie.get("couverture_pct")

    # Verdict : le pire score déterministe pilote le verdict
    scores_durs = [s for s in (topologie, hydraulique) if s is not None]
    score_pire = min(scores_durs) if scores_durs else None
    if score_pire is None:
        verdict = "indetermine"
    elif score_pire >= 95:
        verdict = "conforme"
    elif score_pire >= 80:
        verdict = "a_surveiller"
    else:
        verdict = "action_requise"

    # Top 3 actions : catégories actives triées par impact (sévérité pondérée)
    poids_sev = {"critique": 4, "majeure": 3, "mineure": 1, "informatif": 0}
    actions_cats = []
    for categorie, items in anomalies.items():
        if not items:
            continue
        impact = sum(poids_sev.get(a.get("severite", "mineure"), 1) for a in items)
        nb_ouvertes = sum(1 for a in items if a.get("statut", "a_traiter") == "a_traiter")
        if nb_ouvertes == 0:
            continue
        actions_cats.append((categorie, impact, nb_ouvertes))
    actions_cats.sort(key=lambda x: (-x[1], -x[2]))
    LIBELLES = {
        "conduites_sans_regards": "Raccorder les conduites orphelines à un nœud",
        "troncons_orphelins": "Vérifier l'isolement des tronçons orphelins",
        "champs_manquants": "Compléter les attributs manquants (diamètre, matériau, longueur)",
        "geometries_invalides": "Réparer les géométries corrompues",
        "pentes_suspectes": "Valider les pentes certifiées NGF sur le terrain",
        "incoherences_amont_aval": "Corriger les inversions de radier NGF",
        "inversions_sens_ecoulement": "Recouper le sens d'écoulement avec le sens de la pente du terrain",
        "deconnexions_spatiales": "Contrôler les identifiants d'extrémités suspects",
        "discontinuites_pose": "Vérifier la continuité de pose (profondeurs PROF_FE)",
        "capacite_debit": "Contrôler la capacité de débit des tronçons",
        "donnees_manquantes": "Compléter l'altimétrie (campagne topo / récolement)",
    }
    top_actions = [
        {
            "categorie": cat,
            "libelle": LIBELLES.get(cat, cat),
            "nb_anomalies": n,
            "nb_ouvertes": ouvertes,
        }
        for cat, _impact, ouvertes in actions_cats[:3]
        for n in [par_categorie.get(cat, 0)]
    ]

    return {
        "verdict": verdict,
        "date_analyse": rapport.get("date_analyse"),
        "moteur": rapport.get("moteur"),
        "reseau": {
            "nb_regards": stats.get("nb_regards"),
            "nb_conduites": stats.get("nb_conduites"),
            "nb_rejets": stats.get("nb_rejets"),
            "longueur_totale_m": stats.get("longueur_totale_m"),
        },
        "scores": {
            "global": (scores.get("global") or {}).get("score_qualite"),
            "topologie": topologie,
            "hydraulique": hydraulique,
            "completude": (scores.get("completude") or {}).get("score_qualite"),
            "geometrie": (scores.get("geometrie") or {}).get("score_qualite"),
        },
        "altimetrie": {
            "couverture_pct": couverture_pct,
            "nb_donnees_manquantes": (altimetrie.get("total_anomalies") or 0),
        },
        "anomalies": {
            "total": sum(par_categorie.values()),
            "nb_a_traiter": nb_a_traiter,
            "par_severite": par_severite,
            "par_categorie": par_categorie,
        },
        "connectivite": stats.get("connectivite"),
        "top_actions": top_actions,
    }


@router.get("/scores", response_model=Dict[str, Any])
async def get_scores_qualite(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_role("viewer"))
):
    """
    Récupère les scores de qualité calculés.
    """
    global _cache_qualite

    gpkg_target, project_name = get_active_project_and_gpkg(db, ctx)
    if (_cache_qualite["rapport"] is None or
        (gpkg_target and _cache_qualite.get("gpkg_path") != str(gpkg_target))):
        if gpkg_target and gpkg_target.exists():
            rapport = await asyncio.to_thread(analyser_qualite_gpkg, gpkg_target, project_name)
            _cache_qualite["rapport"] = rapport
            _cache_qualite["timestamp"] = datetime.now().timestamp()
            _cache_qualite["gpkg_path"] = str(gpkg_target)
        else:
            raise HTTPException(
                status_code=404,
                detail="Aucun score de qualité disponible."
            )

    return _cache_qualite["rapport"]["scores_qualite"]


@router.get("/statistiques", response_model=Dict[str, Any])
async def get_statistiques_reseau(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_role("viewer"))
):
    """
    Récupère les statistiques globales du réseau.
    """
    global _cache_qualite

    gpkg_target, project_name = get_active_project_and_gpkg(db, ctx)
    if (_cache_qualite["rapport"] is None or
        (gpkg_target and _cache_qualite.get("gpkg_path") != str(gpkg_target))):
        if gpkg_target and gpkg_target.exists():
            rapport = await asyncio.to_thread(analyser_qualite_gpkg, gpkg_target, project_name)
            _cache_qualite["rapport"] = rapport
            _cache_qualite["timestamp"] = datetime.now().timestamp()
            _cache_qualite["gpkg_path"] = str(gpkg_target)
        else:
            raise HTTPException(
                status_code=404,
                detail="Aucune statistique disponible."
            )

    return _cache_qualite["rapport"]["statistiques_globales"]


@router.post("/valider-incremental", response_model=Dict[str, Any])
async def valider_incremental(
    request: Dict[str, Any],
    ctx: TenantContext = Depends(require_role("engineer"))
):
    """Validation incrémentale sur un sous-ensemble de conduites.

    Corps attendu: {"ids_conduites": [1, 2, 3]}
    """
    ids = request.get("ids_conduites")
    if not ids or not isinstance(ids, list):
        raise HTTPException(status_code=400, detail="ids_conduites requis (liste d'entiers)")

    try:
        from src.qualite_reseau import QualiteReseau
        analyseur = QualiteReseau()
        try:
            result = analyseur.valider_incremental([int(i) for i in ids])
            return result
        finally:
            analyseur.fermer_connexion()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur validation incrémentale: {str(e)}")


@router.get("/scores-bassins", response_model=Dict[str, Any])
async def get_scores_qualite_par_bassin(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_role("viewer"))
):
    """
    Calcule les scores de qualité par bassin (cluster).
    Agrège les anomalies par cluster et calcule un score par bassin.
    """
    global _cache_qualite

    if (_cache_qualite["rapport"] is None or
        "anomalies" not in _cache_qualite["rapport"]):
        raise HTTPException(
            status_code=404,
            detail="Aucune analyse de qualité disponible. Lancez d'abord /qualite/analyse"
        )

    try:
        from api import crud
        from sqlalchemy import text

        try:
            # Récupérer tous les clusters avec leurs stats (filtré par organisation)
            clusters = db.query(crud.Cluster).filter(crud.Cluster.org_id == ctx.org_id).all()

            # Récupérer toutes les anomalies
            anomalies = _cache_qualite["rapport"]["anomalies"]

            # Aplatir toutes les anomalies avec leurs coordonnées
            toutes_anomalies = []
            for categorie, liste in anomalies.items():
                for a in liste:
                    a["categorie"] = categorie
                    toutes_anomalies.append(a)

            # Pour chaque cluster, compter les anomalies dans sa zone
            scores_bassins = []
            for cluster in clusters:
                nb_anomalies = 0
                nb_anomalies_par_categorie = {}
                severite_counts = {"mineure": 0, "majeure": 0, "critique": 0}

                # Compter les anomalies dont les coordonnées sont dans le cluster
                # Pour l'instant, on utilise une approximation basée sur les IDs
                # Une version plus précise utiliserait un point-in-polygon spatial
                cluster_conduites = set()
                if cluster.exutoire_noeud:
                    try:
                        import ast
                        noeud = ast.literal_eval(cluster.exutoire_noeud)
                        # Récupérer les conduites du cluster depuis le graphe
                        from src.domain.graphe_reseau import _get_graph
                        G = _get_graph()
                        if noeud in G.nodes():
                            # BFS depuis l'exutoire pour trouver toutes les conduites
                            from collections import deque
                            visites = set()
                            file = deque([noeud])
                            while file:
                                n = file.popleft()
                                if n in visites:
                                    continue
                                visites.add(n)
                                for pred in G.predecessors(n):
                                    if pred not in visites:
                                        file.append(pred)
                            # Récupérer les edge IDs
                            for u, v, d in G.edges(visites, data=True):
                                cid = d.get("conduit_id")
                                if cid:
                                    cluster_conduites.add(cid)
                    except Exception:
                        pass

                # Compter les anomalies liées aux conduites de ce cluster
                for a in toutes_anomalies:
                    a_cid = a.get("id_conduite") or a.get("fid") or a.get("id_conduite1") or a.get("id_conduite2")
                    if a_cid and str(a_cid) in cluster_conduites:
                        nb_anomalies += 1
                        cat = a.get("categorie", "inconnue")
                        nb_anomalies_par_categorie[cat] = nb_anomalies_par_categorie.get(cat, 0) + 1
                        sev = a.get("severite", "mineure")
                        if sev in severite_counts:
                            severite_counts[sev] += 1

                # Calculer le score de qualité pour ce bassin
                nb_conduites = cluster.nb_conduites or 1
                score_bassin = max(0, 100 - (nb_anomalies / nb_conduites) * 100) if nb_conduites > 0 else 100

                scores_bassins.append({
                    "cluster_id": cluster.id,
                    "nom_bassin": cluster.nom,
                    "score_qualite": round(score_bassin, 1),
                    "nb_conduites": nb_conduites,
                    "nb_anomalies": nb_anomalies,
                    "anomalies_par_categorie": nb_anomalies_par_categorie,
                    "distribution_severite": severite_counts,
                    "exutoire_type": cluster.exutoire_noeud
                })

            # Trier par score croissant (pires d'abord)
            scores_bassins.sort(key=lambda x: x["score_qualite"])

            return {
                "date_analyse": _cache_qualite["rapport"]["date_analyse"],
                "nb_bassins": len(scores_bassins),
                "score_moyen": round(sum(b["score_qualite"] for b in scores_bassins) / len(scores_bassins), 1) if scores_bassins else 0,
                "bassins": scores_bassins
            }

        finally:
            db.close()

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur calcul scores par bassin: {str(e)}"
        )


@router.post("/export-csv")
async def exporter_anomalies_csv(
    background_tasks: BackgroundTasks,
    ctx: TenantContext = Depends(require_role("viewer"))
):
    """
    Exporte les anomalies détectées au format CSV.
    L'export se fait en arrière-plan.
    """
    try:
        # Créer le répertoire d'export s'il n'existe pas
        export_dir = "exports"
        os.makedirs(export_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        fichier_export = f"{export_dir}/anomalies_qualite_{timestamp}.csv"

        # Lancer l'export en arrière-plan
        background_tasks.add_task(_export_async, fichier_export)

        return {
            "message": "Export CSV lancé en arrière-plan",
            "fichier_destination": fichier_export,
            "status": "en_cours"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors du lancement de l'export: {str(e)}"
        )


@router.get("/cache/status")
async def get_cache_status(
    ctx: TenantContext = Depends(require_role("viewer"))
):
    """
    Vérifie l'état du cache d'analyse qualité.
    """
    global _cache_qualite

    maintenant = datetime.now().timestamp()

    if _cache_qualite["timestamp"] is None:
        status_cache = "vide"
        age_secondes = None
    else:
        age_secondes = maintenant - _cache_qualite["timestamp"]
        if age_secondes < _cache_qualite["duree_validite"]:
            status_cache = "valide"
        else:
            status_cache = "expire"

    return {
        "status_cache": status_cache,
        "age_cache_secondes": age_secondes,
        "duree_validite_secondes": _cache_qualite["duree_validite"],
        "derniere_mise_a_jour": datetime.fromtimestamp(_cache_qualite["timestamp"]).isoformat() if _cache_qualite["timestamp"] else None,
        "analyse_disponible": _cache_qualite["rapport"] is not None
    }


@router.delete("/cache")
async def clear_cache(
    ctx: TenantContext = Depends(require_role("admin"))
):
    """
    Vide le cache d'analyse qualité.
    """
    reinitialiser_cache_qualite()
    return {"message": "Cache d'analyse qualité vidé"}


def _calculer_distribution_severite(anomalies: list) -> Dict[str, int]:
    """Calcule la distribution des anomalies par sévérité."""
    distribution = {"mineure": 0, "majeure": 0, "critique": 0}

    for anomalie in anomalies:
        severite = anomalie.get("severite", "mineure")
        if severite in distribution:
            distribution[severite] += 1

    return distribution


async def _export_async(fichier_destination: str):
    """Fonction d'export asynchrone au format CSV."""
    try:
        global _cache_qualite

        if _cache_qualite["rapport"] is None:
            print("Aucun rapport disponible pour l'export")
            return

        rapport = _cache_qualite["rapport"]
        with open(fichier_destination, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["categorie", "id_conduite", "severite", "description", "latitude", "longitude"])
            for cat, items in rapport.get("anomalies", {}).items():
                for item in items:
                    writer.writerow([
                        cat,
                        item.get("id_conduite", ""),
                        item.get("severite", ""),
                        item.get("description", ""),
                        item.get("latitude", ""),
                        item.get("longitude", "")
                    ])

        print(f"Export CSV termine: {fichier_destination}")

    except Exception as e:
        print(f"Erreur lors de l'export CSV: {e}")


# Schéma de réponse pour la documentation automatique
from pydantic import BaseModel
from typing import List, Optional

class AnomalieResponse(BaseModel):
    type: str
    id_conduite: Optional[int] = None
    fid: Optional[str] = None
    severite: str
    # Autres champs selon le type d'anomalie...

class AnalyseQualiteResponse(BaseModel):
    date_analyse: str
    statistiques_globales: Dict[str, Any]
    anomalies: Dict[str, List[Dict[str, Any]]]
    scores_qualite: Dict[str, Any]