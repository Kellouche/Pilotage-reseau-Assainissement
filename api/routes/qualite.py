"""
Routes pour l'analyse de qualité du réseau d'assainissement.
Exposition des anomalies et scores de qualité via API REST.
"""

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

        print("✅ Utilisation du cache pour l'analyse qualité")
        return _cache_qualite["rapport"]

    try:
        print("🔄 Lancement d'une nouvelle analyse qualité...")

        # Créer l'analyseur et lancer l'analyse
        analyseur = QualiteReseau()

        # Analyse complète (sans export CSV pour l'API)
        rapport = analyseur.analyser_reseau_complet()

        # Fermer proprement la connexion
        analyseur.fermer_connexion()

        # Mettre à jour le cache
        _cache_qualite["rapport"] = rapport
        _cache_qualite["timestamp"] = maintenant

        print("✅ Analyse qualité terminée et mise en cache")
        return rapport

    except Exception as e:
        print(f"❌ Erreur lors de l'analyse qualité: {e}")
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
            print("❌ Aucun rapport disponible pour l'export")
            return

        # Créer l'analyseur pour l'export
        analyseur = QualiteReseau()
        analyseur.exporter_rapport_csv(_cache_qualite["rapport"], fichier_destination)
        analyseur.fermer_connexion()

        print(f"✅ Export CSV terminé: {fichier_destination}")

    except Exception as e:
        print(f"❌ Erreur lors de l'export CSV: {e}")


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