# -*- coding: utf-8 -*-
"""
Package : topologie — résolution canonique des nœuds du réseau.
Source unique de vérité pour la connectivité extrémité -> nœud
(ID -> alias -> snap spatial -> nœud spatial), partagée par le graphe
de bassins, le générateur .inp SWMM et les profils en long.
"""

from src.domain.topologie.resolution_noeuds import (
    PROV_ABSENT,
    PROV_ALIAS,
    PROV_ALIAS_AUTO,
    PROV_ID,
    PROV_SNAP,
    PROV_SPATIAL,
    ResolutionNoeud,
    ResoluteurNoeuds,
)

__all__ = [
    "ResolutionNoeud",
    "ResoluteurNoeuds",
    "PROV_ID",
    "PROV_ALIAS",
    "PROV_ALIAS_AUTO",
    "PROV_SNAP",
    "PROV_SPATIAL",
    "PROV_ABSENT",
]
