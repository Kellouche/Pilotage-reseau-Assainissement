# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Compilation et assemblage du modèle hydrodynamique au format standard EPA SWMM 5.2 (.INP)
================================================================================
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List, Union
import geopandas as gpd

from src.domain.hydrologie import GenerateurHydrologie
from src.domain.moteur_swmm.constants import (
    SCENARIOS_PLUIE,
    TYPOLOGIES_OCCUPATION_SOL,
)
from src.domain.moteur_swmm.assainissement_topologique import _assainir_topologie_swmm
from src.domain.moteur_swmm.filtrage_bassin import extraire_sous_reseau_bassin
from src.domain.moteur_swmm.sections_inp import generer_lignes_sections_inp

logger = logging.getLogger("swmm_platform.moteur_swmm.assemblage_inp")


def assembler_modele_inp_impl(
    tampon_buffer_m_defaut: float,
    gpkg_path: Path,
    scenario_key: str = "pluie_decennale",
    duree_heures: Optional[float] = None,
    pas_routage_sec: int = 5,
    pente_moyenne_pct: Optional[float] = None,
    cluster_id: Optional[Union[int, str]] = None,
    tampon_buffer_m: Optional[float] = None,
    G_topo: Optional[Any] = None,
    exutoires_map: Optional[Dict[Any, Any]] = None,
    regards_gdf: Optional[gpd.GeoDataFrame] = None,
    canalisations_gdf: Optional[gpd.GeoDataFrame] = None,
    valider_raccordement_deporte: bool = True,
    typologie_sol: Optional[str] = None,
    imperv_pct: Optional[float] = None,
    intensite_max_mmh: Optional[float] = None,
    station_id: Optional[str] = "chlef_anrh_siege",
    raccordements_orphelins: Optional[List[Dict[str, Any]]] = None,
    scenario_personnalise: Optional[Dict[str, Any]] = None,
    apports_dwf: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, Dict[str, Any], gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    Génère l'intégralité du contenu textuel conforme au standard EPA SWMM 5.2 .inp.
    Retourne (contenu_inp, meta, regards_filtrés, canalisations_filtrées).
    """
    buf_actuel = tampon_buffer_m if (tampon_buffer_m and tampon_buffer_m > 0) else tampon_buffer_m_defaut

    # Résolution typologie de sol & imperméabilisation
    active_imperv = imperv_pct
    n_imp, n_perv = 0.015, 0.25
    d_store_imp, d_store_perv = 2.0, 5.0
    typ_nom = "Habitat mixte / Tissu intermédiaire (65%)"

    if typologie_sol and typologie_sol in TYPOLOGIES_OCCUPATION_SOL:
        typ_cfg = TYPOLOGIES_OCCUPATION_SOL[typologie_sol]
        typ_nom = typ_cfg["nom"]
        if active_imperv is None or active_imperv <= 0:
            active_imperv = typ_cfg["imperv_pct"]
        n_imp = typ_cfg.get("n_imperv", 0.015)
        n_perv = typ_cfg.get("n_perv", 0.25)
        d_store_imp = typ_cfg.get("d_store_imperv", 2.0)
        d_store_perv = typ_cfg.get("d_store_perv", 5.0)
    elif active_imperv is not None and active_imperv > 0:
        typ_nom = f"Personnalisé ({active_imperv:.1f}%)"
    else:
        active_imperv = 65.0

    gh_local = GenerateurHydrologie(
        tampon_buffer_m=buf_actuel,
        imperv_defaut=active_imperv,
        n_imperv=n_imp,
        n_perv=n_perv,
        d_store_imperv=d_store_imp,
        d_store_perv=d_store_perv,
    )
    st_id = station_id or "chlef_anrh_siege"
    try:
        from src.domain.referentiel_pluvio import generer_scenarios_swmm_pour_station
        scenarios_actifs = generer_scenarios_swmm_pour_station(st_id)
    except Exception:
        scenarios_actifs = dict(SCENARIOS_PLUIE)

    if scenario_personnalise and isinstance(scenario_personnalise, dict):
        scenarios_actifs[scenario_key] = scenario_personnalise

    if scenario_key not in scenarios_actifs:
        scenario_key = "pluie_decennale"

    scen = scenarios_actifs[scenario_key]
    duree_sim = duree_heures if (duree_heures and duree_heures > 0) else scen["duree_heures"]

    if regards_gdf is not None and canalisations_gdf is not None:
        regards = regards_gdf.copy()
        canalisations = canalisations_gdf.copy()
        rejets = gpd.GeoDataFrame()
    else:
        layers = gpd.list_layers(str(gpkg_path))["name"].tolist()
        regard_layer = next((l for l in layers if "regard" in l.lower()), None)
        pipe_layer = next((l for l in layers if any(k in l.lower() for k in ["canalisat", "conduit", "pipe", "troncon"]) and "désaffect" not in l.lower() and "desaffect" not in l.lower()), None)
        rejet_layer = next((l for l in layers if any(k in l.lower() for k in ["rejet", "exutoire", "outfall"])), None)

        if not regard_layer or not pipe_layer:
            raise ValueError("Le fichier GeoPackage doit contenir les couches regards et canalisations.")

        regards = gpd.read_file(str(gpkg_path), layer=regard_layer)
        canalisations = gpd.read_file(str(gpkg_path), layer=pipe_layer)
        rejets = gpd.read_file(str(gpkg_path), layer=rejet_layer) if rejet_layer else gpd.GeoDataFrame()

    # Filtrage du sous-réseau par bassin
    (
        regards,
        canalisations,
        outfall_code,
        target_ex_id,
        bassin_nom,
        clean_target_nodes,
        exutoires_map
    ) = extraire_sous_reseau_bassin(
        gpkg_path=gpkg_path,
        cluster_id=cluster_id,
        regards=regards,
        canalisations=canalisations,
        rejets=rejets,
        G_topo=G_topo,
        exutoires_map=exutoires_map,
        valider_raccordement_deporte=valider_raccordement_deporte,
        pente_moyenne_pct=pente_moyenne_pct
    )

    # Découpage hydrologique
    sb_gdf = None
    cache_sub_path = Path(str(gpkg_path)).with_suffix(".subcatchments_cache.json")
    if cluster_id is None and cache_sub_path.exists():
        try:
            with open(cache_sub_path, "r", encoding="utf-8") as f_sub:
                cached_sub = json.load(f_sub)
            features_sub = cached_sub.get("features", [])
            if len(features_sub) == len(regards):
                sb_gdf = gpd.GeoDataFrame.from_features(features_sub)
        except Exception as e_csub:
            logger.warning(f"Impossible de réutiliser subcatchments_cache.json: {e_csub}")
            sb_gdf = None

    if sb_gdf is None or sb_gdf.empty:
        sb_gdf = gh_local.generer_sous_bassins(regards, canalisations)
    swmm_sec = gh_local.formater_sections_swmm(sb_gdf, rain_gage_name="RG1")

    # Génération des sections
    lines, meta = generer_lignes_sections_inp(
        regards=regards,
        canalisations=canalisations,
        rejets=rejets,
        sb_gdf=sb_gdf,
        swmm_sec=swmm_sec,
        scen=scen,
        duree_sim=duree_sim,
        pas_routage_sec=pas_routage_sec,
        pente_moyenne_pct=pente_moyenne_pct,
        outfall_code=outfall_code,
        target_ex_id=target_ex_id,
        exutoires_map=exutoires_map,
        clean_target_nodes=clean_target_nodes,
        raccordements_orphelins=raccordements_orphelins,
        intensite_max_mmh=intensite_max_mmh,
        active_imperv=active_imperv,
        typ_nom=typ_nom,
        typologie_sol=typologie_sol,
        st_id=st_id,
        scenario_key=scenario_key,
        cluster_id=cluster_id,
        bassin_nom=bassin_nom,
        buf_actuel=buf_actuel,
        apports_dwf=apports_dwf
    )

    contenu_inp = "\n".join(lines)
    contenu_inp = _assainir_topologie_swmm(contenu_inp)
    return contenu_inp, meta, regards, canalisations
