"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Tests de l'algorithme d'orientation des conduites et parcours de graphe
================================================================================
"""

import pytest
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point, LineString
import pandas as pd
from src.domain.graphe_reseau import ConstructeurGrapheReseau, construire_graphe

def test_orientation_hydraulique_amont_aval():
    # Simuler des nœuds : N1 (z=10), N2 (z=5), N3 (z=1)
    noeuds = gpd.GeoDataFrame({
        'id': ['N1', 'N2', 'N3'],
        'COORDZ': [10.0, 5.0, 1.0],
        'PROFRADI': [0.0, 0.0, 0.0],
        'type': ['regard', 'regard', 'exutoire'],
        'geometry': [Point(0,0), Point(1,1), Point(2,2)]
    })
    
    # Simuler des tronçons
    # T1: Numérisé de N2 vers N1 (sens inverse de la pente)
    # T2: Numérisé de N2 vers N3 (bon sens)
    # T3: Refoulement de N3 vers N1 (contre-pente autorisée car refoulement)
    troncons = gpd.GeoDataFrame({
        'id': ['T1', 'T2', 'T3'],
        'noeud_amont': ['N2', 'N2', 'N3'],
        'noeud_aval': ['N1', 'N3', 'N1'],
        'type': ['gravitaire', 'gravitaire', 'refoulement'],
        'longueur': [10.0, 10.0, 20.0],
        'geometry': [LineString([(1,1), (0,0)]), LineString([(1,1), (2,2)]), LineString([(2,2), (0,0)])]
    })
    
    constructeur = ConstructeurGrapheReseau()
    G = constructeur.construire_graphe(noeuds, troncons)
    
    # 1. Vérifier que T1 a été inversé (doit aller de N1 vers N2 car N1(10) > N2(5))
    assert G.has_edge('N1', 'N2')
    assert G.edges['N1', 'N2']['inverse_automatiquement'] is True
    
    # 2. Vérifier que T2 n'a pas été inversé (N2(5) -> N3(1))
    assert G.has_edge('N2', 'N3')
    assert G.edges['N2', 'N3']['inverse_automatiquement'] is False
    
    # 3. Vérifier que T3 (refoulement) n'est pas inversé malgré la pente montante
    assert G.has_edge('N3', 'N1')
    
    # 4. Vérifier les anomalies stockées
    assert hasattr(constructeur, 'anomalies_topologiques')
    # T3 crée un cycle N1 -> N2 -> N3 -> N1
    cycles = [a for a in constructeur.anomalies_topologiques if a['type'] == 'boucle_fermee']
    assert len(cycles) > 0
