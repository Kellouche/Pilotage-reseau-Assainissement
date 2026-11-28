"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-27
Objet : Endpoints de contrôle qualité topologique et audit de connectivité
================================================================================
"""

import asyncio
import hashlib
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional, Tuple
import json
import os
import csv
import sqlite3
from pathlib import Path
from datetime import datetime

from api.database import get_db
from api.models import Project
from api.core.security import require_role, TenantContext
from src.analyse_qualite_gpkg import analyser_qualite_gpkg

router = APIRouter(prefix="/qualite", tags=["Qualité réseau"])


# ---------------------------------------------------------------------------
# Facade de compatibilité — cache/helpers extraits dans
# api/services/qualite_cache_service.py et endpoints dans
# qualite_scores.py / qualite_conduites.py (règle modularité ≤600 lignes).
# ---------------------------------------------------------------------------
from api.services.qualite_cache_service import (  # noqa: F401
    _appliquer_statuts_anomalies,
    _cache_qualite,
    _cache_topologie,
    _charger_cache_disque,
    _construire_contexte_terrain_qualite,
    _empreinte_couches_aux,
    _get_disk_cache_path,
    _projet_et_version,
    _sauvegarder_cache_disque,
    _cle_anomalie,
    STATUTS_ANOMALIE_VALIDES,
    get_active_project_and_gpkg,
    reinitialiser_cache_qualite,
)

# Cache global pour éviter de recalculer à chaque requête

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

    # Déduplication des rafales : le frontend « Recalculer l'audit » appelle
    # /synthese puis /anomalies.geojson à la suite avec force_refresh=true ;
    # sans cette fenêtre, chaque endpoint relançait un audit complet (~30 s).
    # Un recalcul il y a <120 s sur le même GPKG + mêmes couches auxiliaires
    # est réutilisé ; passé ce délai ou si l'empreinte change, on recalcule.
    if (_cache_qualite.get("rapport") is not None and
        _cache_qualite.get("gpkg_path") == str(gpkg_target) and
        _cache_qualite.get("empreinte_aux") == empreinte_aux and
        _cache_qualite.get("timestamp") is not None and
        (maintenant - _cache_qualite["timestamp"]) < 120):
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

    # Déduplication des rafales force_refresh (même justification que
    # _assurer_rapport : /synthese + /anomalies.geojson appelés à la suite).
    if (_cache_qualite.get("rapport") is not None and
        _cache_qualite.get("gpkg_path") == str(gpkg_target) and
        _cache_qualite.get("empreinte_aux") == empreinte_aux and
        _cache_qualite.get("timestamp") is not None and
        (maintenant - _cache_qualite["timestamp"]) < 120):
        return _appliquer_statuts_anomalies(_cache_qualite["rapport"], db, ctx)

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
    nb_informatif = 0
    for categorie, items in anomalies.items():
        par_categorie[categorie] = len(items)
        for a in items:
            sev = a.get("severite", "mineure")
            par_severite[sev] = par_severite.get(sev, 0) + 1
            if sev == "informatif":
                nb_informatif += 1
            elif a.get("statut", "a_traiter") == "a_traiter":
                nb_a_traiter += 1

    topologie = (scores.get("topologie") or {}).get("score_qualite")
    hydraulique = (scores.get("hydraulique") or {}).get("score_qualite")
    completude = (scores.get("completude") or {}).get("score_qualite")
    geometrie = (scores.get("geometrie") or {}).get("score_qualite")
    altimetrie = scores.get("altimetrie") or {}
    score_alti = altimetrie.get("score_qualite")
    couverture_pct = altimetrie.get("couverture_pct")

    # Verdict : le pire score déterministe de TOUTES les dimensions
    # disponibles pilote le verdict (altimétrie incluse quand le contexte
    # terrain existe — score_qualite est alors un vrai pourcentage).
    scores_durs = [s for s in (topologie, hydraulique, completude, geometrie, score_alti)
                   if s is not None]
    score_pire = min(scores_durs) if scores_durs else None
    if score_pire is None:
        verdict = "indetermine"
    elif score_pire >= 95:
        verdict = "conforme"
    elif score_pire >= 80:
        verdict = "a_surveiller"
    else:
        verdict = "action_requise"

    # Verrou « conforme » : anomalies critiques ou déconnexions spatiales
    # (identifiants d'extrémités suspects → modèle non fiable) interdisent
    # le verdict favorable même si les scores agrégés restent bons.
    if verdict == "conforme" and (
        par_severite.get("critique", 0) > 0
        or par_categorie.get("deconnexions_spatiales", 0) > 0
    ):
        verdict = "a_surveiller"

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
        "nom_projet": rapport.get("nom_projet") or rapport.get("project_name"),
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
            "completude": completude,
            "geometrie": geometrie,
        },
        "criticite_troncons": scores.get("criticite_troncons") or {},
        "altimetrie": {
            "score_qualite": score_alti,
            "couverture_pct": couverture_pct,
            "nb_donnees_manquantes": (altimetrie.get("total_anomalies") or 0),
        },
        "anomalies": {
            "total": sum(par_categorie.values()),
            "nb_a_traiter": nb_a_traiter,
            "nb_informatif": nb_informatif,
            "par_severite": par_severite,
            "par_categorie": par_categorie,
        },
        "connectivite": stats.get("connectivite"),
        "top_actions": top_actions,
    }

def _calculer_distribution_severite(anomalies: list) -> Dict[str, int]:
    """Calcule la distribution des anomalies par sévérité."""
    distribution = {"mineure": 0, "majeure": 0, "critique": 0}

    for anomalie in anomalies:
        severite = anomalie.get("severite", "mineure")
        if severite in distribution:
            distribution[severite] += 1

    return distribution

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