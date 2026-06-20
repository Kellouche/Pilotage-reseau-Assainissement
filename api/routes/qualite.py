"""
Routes pour l'analyse de qualité du réseau d'assainissement.
Exposition des anomalies et scores de qualité via API REST.
"""

import asyncio
from fastapi import APIRouter, BackgroundTasks, HTTPException
from typing import Dict, Any
import json
import os
from datetime import datetime

from src.qualite_reseau import QualiteReseau

router = APIRouter(prefix="/qualite", tags=["Qualité réseau"])

# Cache global pour éviter de recalculer à chaque requête
_cache_qualite = {
    "rapport": None,
    "timestamp": None,
    "duree_validite": 3600  # 1 heure en secondes
}


@router.get("/analyse", response_model=Dict[str, Any])
async def analyser_qualite_reseau(force_refresh: bool = False):
    """
    Analyse complète de la qualité du réseau d'assainissement.

    - **force_refresh**: Force un recalcul complet (sinon utilise le cache)
    """
    global _cache_qualite

    # Vérifier si le cache est encore valide
    maintenant = datetime.now().timestamp()
    if (not force_refresh and
        _cache_qualite["rapport"] is not None and
        _cache_qualite["timestamp"] is not None and
        (maintenant - _cache_qualite["timestamp"]) < _cache_qualite["duree_validite"]):

        print("Utilisation du cache pour l'analyse qualite")
        return _cache_qualite["rapport"]

    try:
        print("Lancement d'une nouvelle analyse qualite...")

        # Créer l'analyseur et lancer l'analyse dans un thread séparé
        # pour ne pas bloquer l'event loop FastAPI (sinon la réponse HTTP
        # n'est jamais renvoyée et la fenêtre de progression reste bloquée)
        analyseur = QualiteReseau()

        rapport = await asyncio.to_thread(analyseur.analyser_reseau_complet)

        # Fermer proprement la connexion
        analyseur.fermer_connexion()

        # Mettre à jour le cache
        _cache_qualite["rapport"] = rapport
        _cache_qualite["timestamp"] = maintenant

        print("Analyse qualite terminee et mise en cache")
        return rapport

    except Exception as e:
        print(f"Erreur lors de l'analyse qualite: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de l'analyse de qualité: {str(e)}"
        )


@router.get("/anomalies/{type_anomalie}", response_model=Dict[str, Any])
async def get_anomalies_par_type(type_anomalie: str):
    """
    Récupère les anomalies d'un type spécifique.

    Types disponibles:
    - conduites_sans_regards
    - troncons_orphelins
    - champs_manquants
    - geometries_invalides
    - pentes_suspectes
    - incoherences_amont_aval
    """
    global _cache_qualite

    if (_cache_qualite["rapport"] is None or
        "anomalies" not in _cache_qualite["rapport"]):

        raise HTTPException(
            status_code=404,
            detail="Aucune analyse de qualité disponible. Lancez d'abord /qualite/analyse"
        )

    anomalies = _cache_qualite["rapport"]["anomalies"]

    if type_anomalie not in anomalies:
        raise HTTPException(
            status_code=404,
            detail=f"Type d'anomalie '{type_anomalie}' non trouvé. Types disponibles: {list(anomalies.keys())}"
        )

    return {
        "type_anomalie": type_anomalie,
        "nombre_anomalies": len(anomalies[type_anomalie]),
        "anomalies": anomalies[type_anomalie],
        "severite_distribution": _calculer_distribution_severite(anomalies[type_anomalie])
    }


@router.get("/scores", response_model=Dict[str, Any])
async def get_scores_qualite():
    """
    Récupère les scores de qualité calculés.
    """
    global _cache_qualite

    if (_cache_qualite["rapport"] is None or
        "scores_qualite" not in _cache_qualite["rapport"]):

        raise HTTPException(
            status_code=404,
            detail="Aucun score de qualité disponible. Lancez d'abord /qualite/analyse"
        )

    return _cache_qualite["rapport"]["scores_qualite"]


@router.get("/statistiques", response_model=Dict[str, Any])
async def get_statistiques_reseau():
    """
    Récupère les statistiques globales du réseau.
    """
    global _cache_qualite

    if (_cache_qualite["rapport"] is None or
        "statistiques_globales" not in _cache_qualite["rapport"]):

        raise HTTPException(
            status_code=404,
            detail="Aucune statistique disponible. Lancez d'abord /qualite/analyse"
        )

    return _cache_qualite["rapport"]["statistiques_globales"]


@router.post("/valider-incremental", response_model=Dict[str, Any])
async def valider_incremental(request: Dict[str, Any]):
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
async def get_scores_qualite_par_bassin():
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
        from api.database import SessionLocal
        from api import crud
        from sqlalchemy import text

        db = SessionLocal()
        try:
            # Récupérer tous les clusters avec leurs stats
            clusters = db.query(crud.Cluster).all()

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
async def exporter_anomalies_csv(background_tasks: BackgroundTasks):
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
async def get_cache_status():
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
async def clear_cache():
    """
    Vide le cache d'analyse qualité.
    """
    global _cache_qualite

    _cache_qualite["rapport"] = None
    _cache_qualite["timestamp"] = None

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
    """Fonction d'export asynchrone."""
    try:
        global _cache_qualite

        if _cache_qualite["rapport"] is None:
            print("Aucun rapport disponible pour l'export")
            return

        # Créer l'analyseur pour l'export
        analyseur = QualiteReseau()
        analyseur.exporter_rapport_csv(_cache_qualite["rapport"], fichier_destination)
        analyseur.fermer_connexion()

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