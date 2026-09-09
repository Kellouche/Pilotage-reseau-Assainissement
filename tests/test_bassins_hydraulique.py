"""
Tests de validation hydraulique et géométrique des bassins versants.
Fichier : tests/test_bassins_hydraulique.py
"""

import pytest
import networkx as nx
from shapely.geometry import Point, LineString
from src.domain.detecteur_clusters import (
    identifier_exutoires,
    partitionner_bassins_exclusifs
)

@pytest.fixture
def reseau_test():
    G = nx.DiGraph()
    G.add_node('N1', x=0.0, y=0.0, z_radier=105.0, type='regard', geometry=Point(0, 0))
    G.add_node('N2', x=50.0, y=0.0, z_radier=102.0, type='regard', geometry=Point(50, 0))
    G.add_node('N3', x=0.0, y=50.0, z_radier=104.0, type='regard', geometry=Point(0, 50))
    G.add_node('N4', x=100.0, y=25.0, z_radier=98.0, type='step', geometry=Point(100, 25))
    G.add_node('N5', x=0.0, y=200.0, z_radier=110.0, type='regard', geometry=Point(0, 200))
    G.add_node('N6', x=100.0, y=200.0, z_radier=100.0, type='rejet', geometry=Point(100, 200))

    G.add_edge('N1', 'N2', key='T1', length=50.0, geometry=LineString([(0, 0), (50, 0)]))
    G.add_edge('N2', 'N4', key='T2', length=55.0, geometry=LineString([(50, 0), (100, 25)]))
    G.add_edge('N3', 'N4', key='T3', length=103.0, geometry=LineString([(0, 50), (100, 25)]))
    G.add_edge('N5', 'N6', key='T4', length=100.0, geometry=LineString([(0, 200), (100, 200)]))
    return G

def test_exutoires(reseau_test):
    exutoires = identifier_exutoires(reseau_test)
    ids = [ex[0] for ex in exutoires]
    assert 'N4' in ids and 'N6' in ids
    assert ids[0] == 'N4'

def test_sans_chevauchement(reseau_test):
    bassins = partitionner_bassins_exclusifs(reseau_test)
    assert len(bassins) == 2
    poly_a = bassins['N4']['polygon']
    poly_b = bassins['N6']['polygon']
    assert poly_a is not None and poly_b is not None
    assert not poly_a.intersects(poly_b)
