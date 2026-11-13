# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Classe orchestratrice principale MoteurSWMM pour la modélisation hydrodynamique
================================================================================
"""

import hashlib
import importlib.metadata
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List, Union
import geopandas as gpd

from src.domain.hydrologie import GenerateurHydrologie
from src.domain.moteur_swmm.assemblage_inp import assembler_modele_inp_impl
from src.domain.moteur_swmm.analyse_rapport import analyser_rapport_swmm_impl, enrichir_hydraulique_noeuds
from src.domain.moteur_swmm.bilan_hydraulique import calculer_sensibilite_buffers_impl
from src.domain.moteur_swmm.execution_solver import executer_solver_swmm

logger = logging.getLogger("swmm_platform.moteur_swmm.moteur")


def _get_package_version(dist_name: str) -> str:
    """Retourne la version installée d'un package, ou 'inconnu' si absent."""
    try:
        return importlib.metadata.version(dist_name)
    except importlib.metadata.PackageNotFoundError:
        return "inconnu"


def _extraire_version_moteur_swmm(rpt_text: str) -> str:
    """Extrait la version EPA SWMM depuis l'en-tête du rapport .rpt."""
    if not rpt_text:
        return "inconnu"
    m = re.search(r"VERSION\s+([0-9]+(?:\.[0-9]+)*)", rpt_text[:2000], re.IGNORECASE)
    return m.group(1) if m else "inconnu"


def construire_provenance_simulation(
    inp_content: str,
    rpt_text: str,
    execution_mode: str = "sync",
) -> Dict[str, Any]:
    """
    Construit le bloc de traçabilité scientifique d'une simulation réelle.
    Additif : ne modifie aucun calcul hydraulique.
    """
    inp_bytes = inp_content.encode("utf-8") if inp_content else b""
    return {
        "nature": "REAL",
        "engine": "EPA SWMM",
        "engine_version": _extraire_version_moteur_swmm(rpt_text),
        "pyswmm_version": _get_package_version("pyswmm"),
        "swmm_toolkit_version": _get_package_version("swmm-toolkit"),
        "execution_mode": execution_mode,
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "inp_sha256": hashlib.sha256(inp_bytes).hexdigest() if inp_bytes else None,
        "inp_size_bytes": len(inp_bytes),
    }


class MoteurSWMM:
    """
    Orchestrateur de simulation hydrodynamique EPA SWMM 5.2.
    Transforme un réseau SIG (GeoPackage) en modèle .inp, exécute le solveur
    Saint-Venant via pyswmm et extrait les KPIs d'audit capacitaire.
    """

    def __init__(self, tampon_buffer_m: float = 35.0, imperv_defaut: float = 70.0):
        self.tampon_buffer_m = tampon_buffer_m
        self.gh = GenerateurHydrologie(tampon_buffer_m=tampon_buffer_m, imperv_defaut=imperv_defaut)
        self._last_regards: Optional[gpd.GeoDataFrame] = None
        self._last_canalisations: Optional[gpd.GeoDataFrame] = None

    def assembler_modele_inp(
        self,
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
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Génère l'intégralité du contenu textuel conforme au standard EPA SWMM 5.2 .inp.
        """
        contenu_inp, meta, regards_used, canalisations_used = assembler_modele_inp_impl(
            tampon_buffer_m_defaut=self.tampon_buffer_m,
            gpkg_path=gpkg_path,
            scenario_key=scenario_key,
            duree_heures=duree_heures,
            pas_routage_sec=pas_routage_sec,
            pente_moyenne_pct=pente_moyenne_pct,
            cluster_id=cluster_id,
            tampon_buffer_m=tampon_buffer_m,
            G_topo=G_topo,
            exutoires_map=exutoires_map,
            regards_gdf=regards_gdf,
            canalisations_gdf=canalisations_gdf,
            valider_raccordement_deporte=valider_raccordement_deporte,
            typologie_sol=typologie_sol,
            imperv_pct=imperv_pct,
            intensite_max_mmh=intensite_max_mmh,
            station_id=station_id,
            raccordements_orphelins=raccordements_orphelins,
            scenario_personnalise=scenario_personnalise,
            apports_dwf=apports_dwf,
        )
        self._last_regards = regards_used.copy()
        self._last_canalisations = canalisations_used.copy()
        return contenu_inp, meta

    def calculer_sensibilite_buffers(
        self,
        regards: gpd.GeoDataFrame,
        canalisations: gpd.GeoDataFrame,
        base_kpis: Dict[str, Any],
        active_buffer_m: float = 35.0
    ) -> Dict[str, Any]:
        """
        Calcule en arrière-plan la sensibilité pour les 3 cas : 35m, 45m et 60m.
        """
        return calculer_sensibilite_buffers_impl(
            imperv_defaut=self.gh.imperv_defaut,
            regards=regards,
            canalisations=canalisations,
            base_kpis=base_kpis,
            active_buffer_m=active_buffer_m
        )

    def _analyser_rapport_swmm(self, rpt_text: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse et extrait les indicateurs clés (KPIs) et résultats détaillés du rapport SWMM.
        """
        return analyser_rapport_swmm_impl(rpt_text=rpt_text, meta=meta)

    def executer_simulation(
        self,
        gpkg_path: Path,
        scenario_key: str = "pluie_decennale",
        duree_heures: Optional[float] = None,
        pas_routage_sec: int = 5,
        pente_moyenne_pct: Optional[float] = None,
        cluster_id: Optional[Union[int, str]] = None,
        tampon_buffer_m: Optional[float] = None,
        valider_raccordement_deporte: bool = True,
        typologie_sol: Optional[str] = None,
        imperv_pct: Optional[float] = None,
        intensite_max_mmh: Optional[float] = None,
        station_id: Optional[str] = "chlef_anrh_siege",
        raccordements_orphelins: Optional[List[Dict[str, Any]]] = None,
        scenario_personnalise: Optional[Dict[str, Any]] = None,
        apports_dwf: Optional[List[Dict[str, Any]]] = None,
        execution_mode: str = "sync",
    ) -> Dict[str, Any]:
        """
        Exécute la simulation complète avec pyswmm et extrait les KPIs hydrauliques.
        """
        current_buf = tampon_buffer_m if (tampon_buffer_m and tampon_buffer_m > 0) else self.tampon_buffer_m
        
        G_topo_cached = None
        if cluster_id is not None:
            try:
                from api.routes.clusters import _get_graph
                G_topo_cached = _get_graph(str(gpkg_path))
            except Exception:
                pass

        inp_content, meta = self.assembler_modele_inp(
            gpkg_path=gpkg_path,
            scenario_key=scenario_key,
            duree_heures=duree_heures,
            pas_routage_sec=pas_routage_sec,
            pente_moyenne_pct=pente_moyenne_pct,
            cluster_id=cluster_id,
            tampon_buffer_m=current_buf,
            G_topo=G_topo_cached,
            valider_raccordement_deporte=valider_raccordement_deporte,
            typologie_sol=typologie_sol,
            imperv_pct=imperv_pct,
            intensite_max_mmh=intensite_max_mmh,
            station_id=station_id,
            raccordements_orphelins=raccordements_orphelins,
            scenario_personnalise=scenario_personnalise,
            apports_dwf=apports_dwf,
        )

        rpt_text, _, timeseries = executer_solver_swmm(inp_content, return_timeseries=True)
        kpis = self._analyser_rapport_swmm(rpt_text, meta)
        kpis["timeseries"] = timeseries or {}
        # P0 — maxima .rpt (pas de routage) injectés dans node_hydraulics
        # avec provenance explicite ; les maxima .out restent marqués
        # « aux instants de rapport ».
        try:
            enrichir_hydraulique_noeuds(kpis)
        except Exception as e_enrich:
            logger.warning("Enrichissement maxima .rpt impossible: %s", e_enrich)

        # 1. Calcul en arrière-plan de la sensibilité aux 3 cas de buffers (35, 45, 60m)
        try:
            if self._last_regards is not None and not self._last_regards.empty:
                kpis["buffer_sensitivity"] = self.calculer_sensibilite_buffers(
                    regards=self._last_regards,
                    canalisations=self._last_canalisations,
                    base_kpis=kpis,
                    active_buffer_m=current_buf
                )
        except Exception as e_sens:
            logger.warning(f"Erreur analyse sensibilité buffer: {e_sens}")
            kpis["buffer_sensitivity"] = {}

        # 2. Exécution de l'équipe multi-agents d'expertise pour interpréter les résultats
        try:
            from src.domain.agents_expertise import orchestrer_equipe_agents
            kpis["agents_expertise"] = orchestrer_equipe_agents(
                sim_result=kpis,
                canalisations_gdf=self._last_canalisations
            )
        except Exception as e_agents:
            logger.warning(f"Erreur équipe multi-agents: {e_agents}")
            kpis["agents_expertise"] = {}

        kpis["inp_content"] = inp_content
        kpis["rpt_content"] = rpt_text
        kpis["provenance"] = construire_provenance_simulation(
            inp_content=inp_content,
            rpt_text=rpt_text,
            execution_mode=execution_mode,
        )
        # LOT P1.3 — traçabilité des apports DWF effectivement injectés
        # (identité, nœud, nature, profil, méthode, paramètres temporels).
        if meta.get("apports_dwf") or meta.get("apports_dwf_ignores"):
            kpis["provenance"]["apports_dwf"] = {
                "injectes": meta.get("apports_dwf", []),
                "ignores": meta.get("apports_dwf_ignores", []),
            }
        kpis["status"] = "SUCCESS"
        return kpis

