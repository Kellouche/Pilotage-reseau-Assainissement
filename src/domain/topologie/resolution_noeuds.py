# -*- coding: utf-8 -*-
"""
================================================================================
Module : Résolveur topologique canonique des nœuds (ID -> alias -> snap -> spatial)
Objet  : Source UNIQUE de résolution des extrémités de tronçons pour tout le
         pipeline (graphe de bassins, génération .inp SWMM, profils en long).
         Chaque résolution est tracée avec sa provenance — jamais silencieuse.
Référence : docs/CAHIER_DE_CHARGES_RESTITUTION_INP.md (chantier 3)
================================================================================
"""

import re
from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Tuple

import numpy as np

from src.domain.moteur_swmm.constants import _clean_node_id


# Provenances possibles d'une résolution d'extrémité
PROV_ID = "id"                # identifiant texte résolu directement
PROV_ALIAS = "alias"          # alias sémantique (ex. RJ12 -> CODE 12 des rejets)
PROV_SNAP = "snap"            # raccordement spatial <= tolerance
PROV_SPATIAL = "spatial"      # nœud spatial créé à la coordonnée réelle
PROV_ABSENT = "absent"        # non résolu (ni ID, ni alias, ni snap, pas de point)


@dataclass(frozen=True)
class ResolutionNoeud:
    """Résultat tracé de la résolution d'une extrémité de tronçon."""
    noeud: Optional[str]
    provenance: str
    distance_m: float = 0.0

    @property
    def resolu(self) -> bool:
        return self.noeud is not None


def _alias_identifiants(nid: str) -> Tuple[str, ...]:
    """
    Retourne les alias candidats pour un identifiant de nœud.

    Règle constatée sur le territoire (GPKG Ville) : les conduites
    référencent les rejets par des codes « RJ<n> » (ReJet + zéro-padding)
    alors que la couche Rejets expose un CODE numérique nu. La distance
    mesurée conduit->rejet est 0,0 m pour les 79 occurrences : c'est une
    convention de nommage, pas une incertitude spatiale.
    """
    alias = []
    m = re.match(r"^RJ_?0*(\d+)$", nid)
    if m:
        alias.append(m.group(1))
    return tuple(alias)


class ResoluteurNoeuds:
    """
    Résout une extrémité de tronçon selon la chaîne canonique :

        1. identifiant texte (ID_AMONT / ID_AVAL) dans l'index des nœuds
        2. alias sémantique (RJ<n> -> <n>)
        3. snap spatial <= tolerance_snap_m (KD-Tree)
        4. échec -> le nœud spatial doit être créé par l'appelant
           (provenance 'spatial'), ou l'extrémité déclarée 'absent'.

    Le snapping n'est JAMAIS utilisé quand l'ID est présent et valide :
    la topologie textuelle fait foi, le spatial n'est qu'un filet de secours.
    """

    def __init__(
        self,
        noeuds: Mapping[str, Tuple[float, float]],
        tolerance_snap_m: float = 0.50,
    ):
        self.noeuds: Dict[str, Tuple[float, float]] = dict(noeuds)
        self.tolerance_snap_m = float(tolerance_snap_m)
        self._ids: list = []
        self._tree = None
        if self.noeuds:
            try:
                from scipy.spatial import cKDTree
                self._ids = list(self.noeuds.keys())
                coords = np.array([self.noeuds[i] for i in self._ids], dtype=float)
                self._tree = cKDTree(coords)
            except Exception:
                self._tree = None

    def _snap(self, point: Tuple[float, float]) -> Optional[Tuple[str, float]]:
        if self._tree is None or point is None:
            return None
        try:
            d, i = self._tree.query(np.array(point, dtype=float))
        except Exception:
            return None
        d = float(d)
        if d <= self.tolerance_snap_m:
            return self._ids[int(i)], d
        return None

    def resoudre(
        self,
        identifiant_brut,
        point: Optional[Tuple[float, float]] = None,
    ) -> ResolutionNoeud:
        """
        Résout une extrémité. `identifiant_brut` est la valeur brute de la
        colonne ID_AMONT/ID_AVAL ; `point` la coordonnée (x, y) en mètres
        du projet, utilisée uniquement en filet de secours.
        """
        nid = _clean_node_id(identifiant_brut)

        # 1. Identifiant direct
        if nid and nid in self.noeuds:
            return ResolutionNoeud(nid, PROV_ID, 0.0)

        # 2. Alias sémantique (ex. RJ12 -> 12)
        if nid:
            for alias in _alias_identifiants(nid):
                if alias in self.noeuds:
                    return ResolutionNoeud(alias, PROV_ALIAS, 0.0)

        # 3. Snap spatial (filet de secours, tolérance stricte)
        if point is not None:
            hit = self._snap(point)
            if hit is not None:
                return ResolutionNoeud(hit[0], PROV_SNAP, hit[1])
            return ResolutionNoeud(None, PROV_SNAP, -1.0)  # snap tenté, hors tolérance

        return ResolutionNoeud(None, PROV_ABSENT, 0.0)
