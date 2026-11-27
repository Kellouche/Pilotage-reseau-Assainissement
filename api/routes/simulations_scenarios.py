# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Endpoints scénarios de pluie, référentiels pluviométriques, BMS et ouvrages proches (extraits de simulations.py).
================================================================================
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.core.security import get_tenant_context, TenantContext, require_role
from api.database import get_db
from api.models import Project
from api.routes.simulations_contexte import _gpkg_demo_autorise, _org_id_requete
from api.services.simulation_service import (
    ContexteSimulationIntrouvable,
    ProjetAmbigu,
    _resoudre_projet_pour_simulation,
)
from src.domain.moteur_swmm import SCENARIOS_PLUIE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulations", tags=["Simulations — Scénarios & référentiels"])


@router.get("/typologies-sol")
def get_simulation_typologies_sol(
    ctx: TenantContext = Depends(require_role("viewer"))
):
    """Retourne la liste des typologies d'occupation du sol et leurs paramètres d'imperméabilisation."""
    from src.domain.moteur_swmm import TYPOLOGIES_OCCUPATION_SOL
    return {
        "typologies": [
            {
                "key": k,
                "nom": v["nom"],
                "description": v["description"],
                "imperv_pct": v["imperv_pct"],
                "c_ruissellement_ref": v["c_ruissellement_ref"]
            }
            for k, v in TYPOLOGIES_OCCUPATION_SOL.items()
        ],
        "default": "habitat_mixte"
    }


@router.get("/pluviometrie/referentiel")
def get_pluviometrie_referentiel(
    ctx: TenantContext = Depends(require_role("viewer"))
):
    """Retourne le référentiel pluviométrique complet certifié (Wilayas, Stations, Métadonnées)."""
    from src.domain.referentiel_pluvio import charger_referentiel, lister_wilayas, lister_stations
    ref = charger_referentiel()
    return {
        "metadata": ref.get("metadata", {}),
        "wilaya_active_recommandee": ref.get("wilaya_active_recommandee", "Chlef"),
        "wilayas": lister_wilayas(),
        "stations_chlef": lister_stations("Chlef"),
        "total_stations": len(lister_stations()),
    }


@router.get("/pluviometrie/stations")
def get_pluviometrie_stations(
    wilaya: Optional[str] = None,
    ctx: TenantContext = Depends(require_role("viewer"))
):
    """Retourne la liste des stations hydro-météorologiques (optionnellement filtrée par wilaya)."""
    from src.domain.referentiel_pluvio import lister_stations
    return {"stations": lister_stations(wilaya_key=wilaya)}


@router.get("/scenarios")
def get_simulation_scenarios(
    station_id: Optional[str] = "chlef_anrh_siege",
    ctx: TenantContext = Depends(require_role("viewer"))
):
    """Retourne les scénarios de pluie et de sollicitation disponibles pour une station donnée."""
    from src.domain.referentiel_pluvio import generer_scenarios_swmm_pour_station, obtenir_station
    st_id = station_id or "chlef_anrh_siege"
    scenarios_dict = generer_scenarios_swmm_pour_station(st_id)
    if not scenarios_dict:
        scenarios_dict = SCENARIOS_PLUIE

    st_info = obtenir_station(st_id) or {}
    default_i_max = scenarios_dict.get("pluie_decennale", {}).get("intensite_max_defaut", 74.9)

    return {
        "station": st_info,
        "station_id": st_id,
        "scenarios": [
            {
                "key": k,
                "nom": v["nom"],
                "station": v.get("station", "Station Hydro-Météo"),
                "station_id": v.get("station_id", st_id),
                "code_anrh": v.get("code_anrh", ""),
                "wilaya": v.get("wilaya", "Wilaya de Chlef"),
                "periode_retour": v.get("periode_retour", "T = 10 ans"),
                "intensite_max_defaut": v.get("intensite_max_defaut", default_i_max),
                "duree_heures": v["duree_heures"],
                "formule_montana": v.get("formule_montana", ""),
                "hauteur_p24_mm": v.get("hauteur_p24_mm", 0.0),
                "hauteur_totale_mm": v.get("hauteur_totale_mm", 0.0),
                "source": v.get("source", ""),
                "description": v["description"]
            }
            for k, v in scenarios_dict.items()
        ],
        "default_scenario": "pluie_decennale",
        "default_intensite_max": default_i_max,
        "solver": "EPA SWMM 5.2 Dynamic Wave (DYNWAVE)",
        "infiltration_method": "Horton (f0=75 mm/h, fc=10 mm/h, k=4.0 1/h)",
    }


class BMSPreviewRequest(BaseModel):
    cumul_pluie_mm: float = 30.0
    duree_heures: Optional[float] = None
    heure_debut: str = "07:00"
    heure_fin: str = "21:00"
    niveau_vigilance: str = "orange"
    type_profil: str = "cloche"
    wilaya: str = "Chlef"
    station_id: str = "chlef_anrh_siege"


@router.post("/pluviometrie/bms-preview")
def preview_bms_scenario(
    payload: BMSPreviewRequest,
    ctx: Optional[TenantContext] = Depends(require_role("viewer"))
):
    """Génère l'hyétogramme prévisionnel et les indicateurs clés d'un BMS pour aperçu instantané."""
    from src.domain.bms_module import creer_scenario_bms
    scen = creer_scenario_bms(
        cumul_pluie_mm=payload.cumul_pluie_mm,
        duree_heures=payload.duree_heures,
        heure_debut=payload.heure_debut,
        heure_fin=payload.heure_fin,
        niveau_vigilance=payload.niveau_vigilance,
        type_profil=payload.type_profil,
        wilaya=payload.wilaya,
        station_id=payload.station_id,
    )
    return scen


@router.get("/ouvrages-proches")
def get_simulation_ouvrages_proches(
    cluster_id: str,
    rayon_m: float = 45.0,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Retourne les ouvrages spéciaux orphelins (déversoirs d'orage, trop-pleins, stations de relevage)
    détectés à proximité (< rayon_m) du bassin sélectionné pour validation interactive avant simulation.
    """
    from src.domain.ouvrages_orphelins import detecter_ouvrages_orphelins_proches
    from api.models import Project
    from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet

    org_id = _org_id_requete(tenant)
    gpkg_path = None
    try:
        proj = _resoudre_projet_pour_simulation(db, org_id, None)
    except ProjetAmbigu as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContexteSimulationIntrouvable:
        proj = None
    if proj is not None:
        gpkg_path = resoudre_gpkg_effectif_pour_projet(db, proj)
    if gpkg_path is None:
        gpkg_path = _gpkg_demo_autorise()

    if not gpkg_path or not gpkg_path.exists():
        raise HTTPException(status_code=404, detail="Réseau hydraulique introuvable pour ce projet.")

    return detecter_ouvrages_orphelins_proches(str(gpkg_path), cluster_id, rayon_max_m=rayon_m)
