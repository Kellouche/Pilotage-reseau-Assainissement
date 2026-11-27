# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Detection des exutoires et composantes orphelines du graphe reseau (extrait de domain/detecteur_clusters.py)
================================================================================
"""

from typing import Dict, List, Set, Tuple, Any, Optional
from collections import Counter
import re
import networkx as nx
from shapely.geometry import Point, LineString, MultiPoint, Polygon, MultiPolygon, mapping
from shapely.ops import unary_union
import shapely



PRIORITE_EXUTOIRES_DEFAUT = {
    'step': 0,
    'station': 1,
    'station_pompage': 1,
    'station_relevement': 1,
    'ouvrage': 2,
    'deversoir': 2,
    'rejet': 3,
    'outfall': 3,
    'exutoire': 3,
    'exutoire_implicite': 8,
    'sortie_graphe': 9
}


def classifier_type_hydraulique(
    type_noeud: str,
    type_ouvrage: Optional[str] = None,
    milieu_rec: Optional[str] = None
) -> Tuple[str, str, str]:
    """
    Retourne (code_type, libelle, couleur_hex) pour un nœud hydraulique aval.
    """
    tn = str(type_noeud or '').lower()
    to = str(type_ouvrage or '').lower()
    mr = str(milieu_rec or '').strip()

    if 'déversoir' in to or 'deversoir' in to or 'dvo' in to:
        return ('deversoir_orage', "Déversoir d'orage (DVO)", '#06b6d4')
    elif 'trop plein' in to or 'trop-plein' in to:
        return ('trop_plein', "Trop-plein de réseau", '#a855f7')
    elif 'rétention' in to or 'retention' in to:
        return ('bassin_retention', "Bassin de rétention", '#10b981')
    elif 'régulation' in to or 'regulation' in to:
        return ('ouvrage_regulation', "Ouvrage de régulation", '#6366f1')
    elif 'réception' in to or 'reception' in to:
        return ('ouvrage_reception', "Ouvrage de réception", '#f59e0b')
    elif 'ouvrage' in tn or to:
        return ('ouvrage_special', "Ouvrage spécial", '#ec4899')
    elif 'rejet' in tn or 'outfall' in tn:
        libelle = f"Rejet direct ({mr})" if mr and mr.lower() != 'nan' else "Rejet vers milieu naturel"
        return ('rejet', libelle, '#ef4444')
    elif 'station' in tn:
        return ('station', "Station de pompage / relevage", '#f97316')
    elif 'step' in tn:
        return ('step', "Station d'épuration (STEP)", '#22c55e')
    return ('regard', "Regard de visite", '#64748b')

def _a_refoulement_sortant(G: nx.DiGraph, noeud) -> bool:
    """Vrai si le nœud a une arête sortante de type refoulement/pompage."""
    try:
        for out_e in G.out_edges(noeud, data=True):
            d_out = out_e[-1]
            t_out = str(d_out.get('type', '')).lower()
            if 'refoulement' in t_out or 'pompage' in t_out:
                return True
    except Exception:
        return False
    return False


def _iterer_aretes_avec_data(G: nx.Graph):
    if G.is_multigraph():
        for u, v, k, data in G.edges(keys=True, data=True):
            yield u, v, k, data
    else:
        for u, v, data in G.edges(data=True):
            yield u, v, None, data

def trouver_exutoires_physiques(
    G: nx.DiGraph,
    priorite_map: Optional[Dict[str, int]] = None,
    inclure_exutoires_implicites: bool = False,
    tolerance_snap_m: float = 1.0,
) -> Dict[str, Dict[str, Any]]:
    if priorite_map is None:
        priorite_map = PRIORITE_EXUTOIRES_DEFAUT

    exutoires = {}
    exutoires_bruts = []
    
    for noeud, data in G.nodes(data=True):
        type_noeud = str(data.get('type', '')).lower()
        matched_type = None
        for cle in priorite_map:
            if cle in type_noeud and cle not in ['exutoire_implicite', 'sortie_graphe']:
                matched_type = cle
                break

        if matched_type:
            # Une station de relèvement avec un refoulement sortant n'est pas
            # un exutoire : c'est une pompe. La classer exutoire tronquerait
            # la chaîne au niveau de la tête (tronçon pompe exclu du bassin
            # aval) et isolerait son petit bassin d'aspiration dans un
            # pseudo-bassin sans suite hydraulique.
            if matched_type.startswith('station') and _a_refoulement_sortant(G, noeud):
                continue
            exutoires_bruts.append((noeud, matched_type, data))

    # Trouver les nœuds connectés pour le snapping
    noeuds_connectes = [n for n in G.nodes() if G.in_degree(n) > 0 or G.out_degree(n) > 0]
    tree = None
    if noeuds_connectes:
        try:
            import numpy as np
            from scipy.spatial import cKDTree
            coords_conn = np.array([[float(G.nodes[n].get('x', 0)), float(G.nodes[n].get('y', 0))] for n in noeuds_connectes])
            tree = cKDTree(coords_conn)
        except Exception:
            tree = None
    
    for noeud, matched_type, data in exutoires_bruts:
        est_deporte = False
        dist_min = 0.0
        meilleur_noeud = noeud

        if G.in_degree(noeud) == 0 and G.out_degree(noeud) == 0 and noeuds_connectes:
            x1, y1 = float(data.get('x', 0)), float(data.get('y', 0))
            if tree is not None:
                p = np.array([x1, y1])
                dist, idx = tree.query(p)
                dist_min = float(dist)
                meilleur_noeud = noeuds_connectes[idx]
            else:
                dist_min = float('inf')
                for nc in noeuds_connectes:
                    nc_data = G.nodes[nc]
                    x2, y2 = float(nc_data.get('x', 0)), float(nc_data.get('y', 0))
                    dist = ((x2 - x1)**2 + (y2 - y1)**2)**0.5
                    if dist < dist_min:
                        dist_min = dist
                        meilleur_noeud = nc
            
            # Seuil de tolérance topologique stricte (bibliographique standard: <= 1.0 m)
            if dist_min <= tolerance_snap_m:
                # Si le nœud snapped est une tête de refoulement, l'ouvrage
                # déporté n'est pas un exutoire mais une pompe : ne pas
                # créer d'exutoire sur ce nœud (le refoulement appartient
                # au bassin de l'exutoire aval).
                if (matched_type.startswith('station')
                        and _a_refoulement_sortant(G, meilleur_noeud)):
                    continue
                to_ouv = data.get('type_ouvrage') or G.nodes[meilleur_noeud].get('type_ouvrage')
                h_seuil = data.get('h_seuil') or G.nodes[meilleur_noeud].get('h_seuil')
                milieu_rec = data.get('milieu_rec') or G.nodes[meilleur_noeud].get('milieu_rec')
                zone_colle = data.get('zone_collecte') or G.nodes[meilleur_noeud].get('zone_collecte')
                typ_det, lib_det, coul_det = classifier_type_hydraulique(matched_type, to_ouv, milieu_rec)

                # Préférer l'adresse la plus descriptive et spécifique
                noms_candidats = [
                    _texte_valide(data.get('nom')),
                    _texte_valide(data.get('nom_voie')),
                    _texte_valide(G.nodes[meilleur_noeud].get('nom_voie')),
                ]
                nom_choisi = max([n for n in noms_candidats if n], key=lambda s: (len(s.split()), len(s)), default=str(noeud))

                exutoires[meilleur_noeud] = {
                    **G.nodes[meilleur_noeud],
                    "type": matched_type,
                    "type_detaille": typ_det,
                    "libelle_type": lib_det,
                    "couleur_type": coul_det,
                    "type_ouvrage": to_ouv,
                    "h_seuil": h_seuil,
                    "milieu_rec": milieu_rec,
                    "zone_collecte": zone_colle,
                    "priorite": priorite_map[matched_type],
                    "nom": nom_choisi,
                    "est_deporte": False,
                    "distance_regard_proche_m": round(dist_min, 2),
                    "regard_proche_id": str(meilleur_noeud)
                }
                continue
            else:
                # Ouvrage déporté (> 1.0 m) : NON rattaché automatiquement, validation requise
                est_deporte = True

        to_ouv = data.get('type_ouvrage')
        h_seuil = data.get('h_seuil')
        milieu_rec = data.get('milieu_rec')
        zone_colle = data.get('zone_collecte')
        typ_det, lib_det, coul_det = classifier_type_hydraulique(matched_type, to_ouv, milieu_rec)

        nom_exutoire = _texte_valide(data.get('nom')) or _texte_valide(data.get('nom_voie')) or str(noeud)
        exutoires[noeud] = {
            **data,
            "type": matched_type,
            "type_detaille": typ_det,
            "libelle_type": lib_det,
            "couleur_type": coul_det,
            "type_ouvrage": to_ouv,
            "h_seuil": h_seuil,
            "milieu_rec": milieu_rec,
            "zone_collecte": zone_colle,
            "priorite": priorite_map[matched_type],
            "nom": nom_exutoire,
            "est_deporte": est_deporte,
            "distance_regard_proche_m": round(dist_min, 2) if est_deporte else 0.0,
            "regard_proche_id": str(meilleur_noeud) if est_deporte else None
        }

    # 3. Nœuds morts du réseau (sans exutoire officiel) -> exutoires implicites
    if inclure_exutoires_implicites:
        for noeud in G.nodes():
            if G.out_degree(noeud) == 0 and noeud not in exutoires:
                exutoires[noeud] = {
                    **G.nodes[noeud],
                    "type": "exutoire_implicite",
                    "priorite": priorite_map["exutoire_implicite"],
                    "nom": str(noeud)
                }

    return exutoires

def detecter_composantes_orphelines(G: nx.DiGraph) -> List[Tuple[Set[str], Set[Tuple], str]]:
    orphelines = []
    composantes = list(nx.weakly_connected_components(G))
    exutoires = trouver_exutoires_physiques(G)
    
    for comp_noeuds in composantes:
        if not any(n in exutoires for n in comp_noeuds):
            edges = set()
            for u, v, k, _ in _iterer_aretes_avec_data(G):
                if u in comp_noeuds and v in comp_noeuds:
                    edges.add((u, v, k) if G.is_multigraph() else (u, v))
            orphelines.append((comp_noeuds, edges, "sans_exutoire"))
            
    return orphelines


def _texte_valide(value: Any) -> Optional[str]:
    if value is None:
        return None
    texte = str(value).strip()
    return texte if texte and texte.lower() not in {'none', 'nan', 'inconnu'} else None


def _premier_texte(*values: Any) -> Optional[str]:
    for value in values:
        texte = _texte_valide(value)
        if texte:
            return texte
    return None


def _est_nom_technique_ou_generique(val: Any) -> bool:
    if val is None:
        return True
    s = str(val).strip()
    if not s or s.lower() in {'none', 'nan', 'null', '', 'sans designation', 'inconnu', 'bassin', 'exutoire'}:
        return True
    if re.match(r'^\d+(\.0)?$', s):
        return True
    return False
