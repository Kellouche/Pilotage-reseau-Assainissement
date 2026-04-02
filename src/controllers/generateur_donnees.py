#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : Pilotage Réseau d'Assainissement
Numéro version : 1.0.0
Date de création : 2026-04-02
Date de modification : 2026-04-02
Objectif : Génération des sections de données d'un fichier SWMM.
Gère les sections INFLOWS, DWF, CURVES, TIMESERIES,
REPORT et TAGS.
"""

from typing import List, Dict

from src.infrastructure.config import GENERIC_PUMP_CURVE_POINTS


class GenerateurDonnees:
    """Génère les sections de données SWMM."""

    def __init__(self, lignes):
        """Initialise avec la référence à la liste de lignes."""
        self.lignes = lignes

    def ajouter_apports(self) -> None:
        """Ajoute la section [INFLOWS] vide."""
        self.lignes.append('[INFLOWS]')
        self.lignes.append(
            ';;Noeud           Constituant  Chronique   '
            'Type   Mfacteur  Sfacteur  Base      Patron'
        )
        self.lignes.append('')

    def ajouter_dwf(self) -> None:
        """Ajoute la section [DWF] vide."""
        self.lignes.append('[DWF]')
        self.lignes.append(
            ';;Noeud           Constituant  '
            'Valeur    Patron'
        )
        self.lignes.append('')

    def ajouter_courbes(
        self, pompes: List[Dict]
    ) -> None:
        """Ajoute la section [CURVES]."""
        self.lignes.append('[CURVES]')
        self.lignes.append(
            ';;Nom             Type          '
            'X-Valeur  Y-Valeur'
        )

        if pompes:
            for x, y in GENERIC_PUMP_CURVE_POINTS:
                self.lignes.append(
                    f'GENERIC_PUMP_CURVE POMPE1        '
                    f'{x:>8.1f}     {y:>6.1f}'
                )

        self.lignes.append('')

    def ajouter_chroniques(self) -> None:
        """Ajoute la section [TIMESERIES] vide."""
        self.lignes.append('[TIMESERIES]')
        self.lignes.append(
            ';;Nom             Date          '
            'Heure     Valeur'
        )
        self.lignes.append('')

    def ajouter_rapport(self) -> None:
        """Ajoute la section [REPORT]."""
        self.lignes.append('[REPORT]')
        self.lignes.append(';;Entree         OUI')
        self.lignes.append(';;Continuite     OUI')
        self.lignes.append(';;Debit          OUI')
        self.lignes.append(';;Profondeur     OUI')
        self.lignes.append(';;Noeud          TOUS')
        self.lignes.append(';;Lien           TOUS')
        self.lignes.append('')

    def ajouter_etiquettes(self) -> None:
        """Ajoute la section [TAGS] vide."""
        self.lignes.append('[TAGS]')
        self.lignes.append(
            ';;Objet           ID            Etiquette'
        )
        self.lignes.append('')
