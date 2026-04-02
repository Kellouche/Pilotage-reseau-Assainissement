#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : Pilotage Réseau d'Assainissement
Numéro version : 1.0.0
Date de création : 2026-04-02
Date de modification : 2026-04-02
Objectif : Génération des sections de liens d'un fichier SWMM.
Gère les sections CONDUITS, PUMPS, XSECTIONS, ORIFICES,
WEIRS et LOSSES.
"""

from typing import List, Dict


class GenerateurLiens:
    """Génère les sections liées aux liens SWMM."""

    def __init__(self, lignes):
        """Initialise avec la référence à la liste de lignes."""
        self.lignes = lignes

    def ajouter_conduites(
        self, conduites: List[Dict]
    ) -> None:
        """Ajoute la section [CONDUITS]."""
        self.lignes.append('[CONDUITS]')
        self.lignes.append(
            ';;ID             NoeudAmont    NoeudAval     '
            'Longueur    Rugosite  DecAmont  '
            'DecAval   DebitInit DebitMax'
        )

        for conduite in conduites:
            ligne_txt = (
                f"{conduite['conduit_id']:<15} "
                f"{conduite['from_node']:<15} "
                f"{conduite['to_node']:<15} "
                f"{conduite['length']:>10.2f}     "
                f"{conduite['roughness']:>8.3f}     "
                f"{conduite['in_offset']:>8.2f}     "
                f"{conduite['out_offset']:>8.2f}     "
                f"{conduite['init_flow']:>8.2f}     "
                f"{conduite['max_flow']:>7.2f}"
            )
            self.lignes.append(ligne_txt)

        self.lignes.append('')

    def ajouter_pompes(
        self, pompes: List[Dict]
    ) -> None:
        """Ajoute la section [PUMPS]."""
        self.lignes.append('[PUMPS]')
        self.lignes.append(
            ';;ID             NoeudAmont    NoeudAval     '
            'CourbePompe       Etat      Demarrage Arret'
        )

        for pompe in pompes:
            ligne_txt = (
                f"{pompe['pump_id']:<15} "
                f"{pompe['from_node']:<15} "
                f"{pompe['to_node']:<15} "
                f"{pompe['pump_curve']:<15} "
                f"OUVERT       "
                f"0.0"
            )
            self.lignes.append(ligne_txt)

        self.lignes.append('')

    def ajouter_orifices(self) -> None:
        """Ajoute la section [ORIFICES] vide."""
        self.lignes.append('[ORIFICES]')
        self.lignes.append(
            ';;ID             NoeudAmont    NoeudAval     '
            'Type      Decalage  CoeffQ    Barrage'
        )
        self.lignes.append('')

    def ajouter_deversoirs(self) -> None:
        """Ajoute la section [WEIRS] vide."""
        self.lignes.append('[WEIRS]')
        self.lignes.append(
            ';;ID             NoeudAmont    NoeudAval     '
            'Type      Crete     CoeffQ    Barrage'
        )
        self.lignes.append('')

    def ajouter_sections_transversales(
        self, conduites: List[Dict]
    ) -> None:
        """Ajoute la section [XSECTIONS]."""
        self.lignes.append('[XSECTIONS]')
        self.lignes.append(
            ';;Lien             Forme           Geom1       '
            'Geom2       Geom3       Geom4       Barillets'
        )

        for conduite in conduites:
            ligne_txt = (
                f"{conduite['conduit_id']:<15} "
                f"{conduite['shape']:<15} "
                f"{conduite['geom1']:>10.2f}   "
                f"{conduite['geom2']:>10.2f}   "
                f"{conduite['geom3']:>10.2f}   "
                f"{conduite['geom4']:>10.2f}   "
                f"{conduite['barrels']:>7}"
            )
            self.lignes.append(ligne_txt)

        self.lignes.append('')

    def ajouter_pertes(self) -> None:
        """Ajoute la section [LOSSES] vide."""
        self.lignes.append('[LOSSES]')
        self.lignes.append(
            ';;Lien             PerteEntree  '
            'PerteSortie  PerteMoy'
        )
        self.lignes.append('')
