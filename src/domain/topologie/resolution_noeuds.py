# -*- coding: utf-8 -*-
"""
================================================================================
Module : Résolveur topologique canonique des nœuds (ID -> alias -> snap -> spatial)
Objet  : Source UNIQUE de résolution des extrémités de tronçons pour tout le
         pipeline (graphe de bassins, génération .inp SWMM, profils en long).
         Chaque résolution est tracée avec sa provenance — jamais silencieuse.
Référence : docs/03_INGENIERIE_HYDRAULIQUE_ET_SWMM.md (§5 chaîne canonique 6 provenances)
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
PROV_ALIAS_AUTO = "alias_auto"  # correspondance par noyau découverte automatiquement
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
    m = re.match(r"^RJ[\s_]?0*(\d+)$", nid)
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
        normalizer=None,
        correspondance_noyau: bool = False,
        alias_auto_max_dist_m: float = 2.5,
    ):
        self.noeuds: Dict[str, Tuple[float, float]] = dict(noeuds)
        self.tolerance_snap_m = float(tolerance_snap_m)
        # Normalisation des identifiants requêtés : _clean_node_id par défaut
        # (espace -> '_'). Le graphe de bassins injecte _identifiant_reseau
        # qui préserve les espaces ('SR HH01') — chaque couche garde son
        # espace de noms sans divergence.
        self._normalizer = normalizer or _clean_node_id
        # Convention découverte automatiquement (decouverte_conventions) :
        # correspondance par noyau d'identifiant confirmée spatialement.
        self._correspondance_noyau = bool(correspondance_noyau)
        self._alias_auto_max_dist_m = float(alias_auto_max_dist_m)
        self._index_num: Dict[int, str] = {}
        self._ids: list = []
        self._tree = None
        if self.noeuds:
            if self._correspondance_noyau:
                from src.domain.topologie.decouverte_conventions import (
                    index_noeuds_numeriques)
                self._index_num = index_noeuds_numeriques(self.noeuds)
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

    def snap(self, point: Tuple[float, float]) -> Optional[Tuple[str, float]]:
        """Snap spatial pur (sans essai d'ID) — utilitaire public."""
        return self._snap(point)

    def plus_proche(self, point: Tuple[float, float]) -> Optional[Tuple[str, float]]:
        """Nœud le plus proche SANS seuil de tolérance (diagnostic de distance)."""
        if self._tree is None or point is None:
            return None
        try:
            d, i = self._tree.query(np.array(point, dtype=float))
            return self._ids[int(i)], float(d)
        except Exception:
            return None

    def _resoudre_par_noyau(
        self,
        nid: str,
        point: Optional[Tuple[float, float]],
    ) -> Optional[ResolutionNoeud]:
        """
        Correspondance par noyau d'identifiant découverte automatiquement :
        'EX_12' -> '12', 'RJ_02' -> nœud '2'. N'aboutit que si EXACTEMENT UN
        nœud candidat est à <= alias_auto_max_dist_m du point — jamais
        d'ambiguïté, jamais de lien sans confirmation spatiale.
        """
        if not self._correspondance_noyau or point is None:
            return None
        from src.domain.topologie.decouverte_conventions import (
            noyaux_candidats, resoudre_noyau)
        valides = {}
        for core in noyaux_candidats(nid):
            cible = resoudre_noyau(self.noeuds, self._index_num, core)
            if cible is None or cible in valides:
                continue
            cx, cy = self.noeuds[cible]
            d = float(np.hypot(point[0] - cx, point[1] - cy))
            if d <= self._alias_auto_max_dist_m:
                valides[cible] = d
        if len(valides) == 1:
            cible, d = next(iter(valides.items()))
            return ResolutionNoeud(cible, PROV_ALIAS_AUTO, d)
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
        nid = self._normalizer(identifiant_brut)

        # 1. Identifiant direct
        if nid and nid in self.noeuds:
            return ResolutionNoeud(nid, PROV_ID, 0.0)

        # 2. Alias sémantique (ex. RJ12 -> 12)
        if nid:
            for alias in _alias_identifiants(nid):
                if alias in self.noeuds:
                    return ResolutionNoeud(alias, PROV_ALIAS, 0.0)

        # 2b. Correspondance par noyau découverte automatiquement
        #     (confirmation spatiale obligatoire, jamais d'ambiguïté)
        if nid:
            res_noyau = self._resoudre_par_noyau(nid, point)
            if res_noyau is not None:
                return res_noyau

        # 3. Snap spatial (filet de secours, tolérance stricte)
        if point is not None:
            hit = self._snap(point)
            if hit is not None:
                return ResolutionNoeud(hit[0], PROV_SNAP, hit[1])
            return ResolutionNoeud(None, PROV_SNAP, -1.0)  # snap tenté, hors tolérance

        return ResolutionNoeud(None, PROV_ABSENT, 0.0)
