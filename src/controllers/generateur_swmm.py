#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : Pilotage Réseau d'Assainissement
Numéro version : 1.0.0
Date de création : 2026-04-02
Date de modification : 2026-04-02
Objectif : Orchestration de la génération complète d'un fichier
SWMM .inp. Coordonne les sections (nœuds, liens, données)
et écrit le fichier de sortie.
"""

import logging
from pathlib import Path
from typing import List, Dict

import geopandas as gpd

from src.controllers.generateur_noeuds import GenerateurNoeuds
from src.controllers.generateur_liens import GenerateurLiens
from src.controllers.generateur_donnees import GenerateurDonnees

logger = logging.getLogger(__name__)


class GenerateurSWMM:
    """Génère les fichiers SWMM au format .inp."""

    def __init__(self):
        """Initialise le générateur SWMM."""
        self.lignes = []

    def generer(
        self,
        noeuds_gdf: gpd.GeoDataFrame,
        conduites: List[Dict],
        pompes: List[Dict],
        fichier_sortie: str = 'modele.inp'
    ) -> str:
        """Génère le fichier SWMM complet."""
        self.lignes = []

        noeuds = GenerateurNoeuds(self.lignes)
        liens = GenerateurLiens(self.lignes)
        donnees = GenerateurDonnees(self.lignes)

        try:
            noeuds.ajouter_titre()
            noeuds.ajouter_options()
            noeuds.ajouter_jonctions(noeuds_gdf)
            noeuds.ajouter_exutoires(noeuds_gdf)
            noeuds.ajouter_stockage()

            liens.ajouter_conduites(conduites)
            liens.ajouter_pompes(pompes)
            liens.ajouter_orifices()
            liens.ajouter_deversoirs()
            liens.ajouter_sections_transversales(conduites)
            liens.ajouter_pertes()

            donnees.ajouter_apports()
            donnees.ajouter_dwf()
            donnees.ajouter_courbes(pompes)
            donnees.ajouter_chroniques()
            donnees.ajouter_rapport()
            donnees.ajouter_etiquettes()

            noeuds.ajouter_coordonnees(noeuds_gdf)
            noeuds.ajouter_carte()

            chemin = Path(fichier_sortie)
            with open(chemin, 'w', encoding='utf-8') as f:
                f.write('\n'.join(self.lignes))

            logger.info(f"Fichier SWMM généré: {fichier_sortie}")
            return str(chemin)

        except Exception as e:
            logger.error(
                f"Erreur génération fichier SWMM: {e}"
            )
            raise
