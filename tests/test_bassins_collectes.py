import geopandas as gpd
import networkx as nx
from shapely.geometry import LineString, Point

from src.domain.detecteur_clusters import (
    determiner_nom_bassin,
    calculer_polygone_urbain_estime,
    partitionner_bassins_exclusifs,
    proposer_raccordement_exutoire,
    tracer_cluster_depuis_exutoire,
    trouver_exutoires_physiques,
)
from src.domain.graphe_reseau import ConstructeurGrapheReseau


def test_trace_amont_retourne_stats_et_ignore_les_cycles():
    graphe = nx.DiGraph()
    graphe.add_edge("A", "B", length=10)
    graphe.add_edge("B", "C", length=20)
    graphe.add_edge("C", "A", length=30)

    trace = tracer_cluster_depuis_exutoire(graphe, "C")

    assert {("A", "B"), ("B", "C"), ("C", "A")} == trace["edges"]
    assert trace["longueur_totale_m"] == 60
    assert trace["cycles"]


def test_partition_exclusive_attribue_une_branche_a_un_seul_exutoire():
    graphe = nx.DiGraph()
    for node, point, node_type in [
        ("A", Point(0, 0), "regard"),
        ("B", Point(1, 0), "regard"),
        ("C", Point(2, 0), "step"),
        ("D", Point(2, 1), "rejet"),
    ]:
        graphe.add_node(node, geometry=point, x=point.x, y=point.y, type=node_type)
    graphe.add_edge("A", "B", length=1, geometry=LineString([(0, 0), (1, 0)]) )
    graphe.add_edge("B", "C", length=1, geometry=LineString([(1, 0), (2, 0)]) )
    graphe.add_edge("B", "D", length=1, geometry=LineString([(1, 0), (2, 1)]) )

    bassins = partitionner_bassins_exclusifs(graphe)

    assert bassins["C"]["edges"] == {("A", "B"), ("B", "C")}
    assert bassins["D"]["edges"] == {("B", "D")}
    assert bassins["C"]["edges"].isdisjoint(bassins["D"]["edges"])


def test_cote_radier_manquante_est_signalee_sans_bloquer_le_graphe():
    noeuds = gpd.GeoDataFrame({
        "id": ["A", "B"],
        "COORDZ": [None, 10.0],
        "geometry": [Point(0, 0), Point(1, 0)],
    })
    troncons = gpd.GeoDataFrame({
        "id": ["T1"],
        "noeud_amont": ["A"],
        "noeud_aval": ["B"],
        "geometry": [LineString([(0, 0), (1, 0)])],
    })

    constructeur = ConstructeurGrapheReseau()
    graphe = constructeur.construire_graphe(noeuds, troncons)

    assert graphe.has_edge("A", "B")
    assert any(a["type"] == "cote_radier_manquante" for a in constructeur.anomalies_topologiques)


def test_un_reseau_sans_exutoire_physique_ne_produit_pas_de_bassin():
    graphe = nx.DiGraph()
    graphe.add_node("A", type="regard", geometry=Point(0, 0), x=0, y=0)
    graphe.add_node("B", type="regard", geometry=Point(1, 0), x=1, y=0)
    graphe.add_edge("A", "B", length=1)

    assert partitionner_bassins_exclusifs(graphe) == {}


def test_nom_bassin_indique_exutoire_et_rues_drainees():
    graphe = nx.DiGraph()
    graphe.add_edge("A", "B", length=1, nom_voie="Rue des Eaux")

    nom = determiner_nom_bassin(
        {("A", "B")},
        graphe,
        {"type": "rejet", "nom": "Exutoire Nord"},
    )

    assert "Bassin hydraulique" in nom
    assert "Exutoire Nord" in nom
    assert "Rue des Eaux" in nom


def test_station_de_relevage_draine_tout_son_reseau_amont_par_raccordement():
    noeuds = gpd.GeoDataFrame({
        "id": ["R1", "R2", "SR1"],
        "type": ["regard", "regard", "station_relevage"],
        "COORDZ": [12.0, 11.0, 10.0],
        "geometry": [Point(0, 0), Point(1, 0), Point(2, 0)],
    })
    troncons = gpd.GeoDataFrame({
        "id": ["C1", "C2"],
        "ID_AMONT": ["mauvais-amont-1", "mauvais-amont-2"],
        "ID_AVAL": ["mauvais-aval-1", "mauvais-aval-2"],
        "geometry": [
            LineString([(0, 0), (1, 0)]),
            LineString([(1, 0), (2, 0)]),
        ],
    })

    constructeur = ConstructeurGrapheReseau(tolerance_raccordement=0.01)
    graphe = constructeur.construire_graphe(noeuds, troncons)
    exutoires = trouver_exutoires_physiques(graphe)
    bassins = partitionner_bassins_exclusifs(graphe, exutoires)

    assert "SR1" in exutoires
    assert bassins["SR1"]["valide"] is True
    assert bassins["SR1"]["edges"] == {("R1", "R2"), ("R2", "SR1")}


def test_station_propose_un_raccordement_et_un_polygone_estime():
    graphe = nx.DiGraph()
    graphe.add_node("SR1", type="station", geometry=Point(2, 0), x=2, y=0)
    graphe.add_node("R1", type="regard", geometry=Point(1, 0), x=1, y=0)
    graphe.add_node("R2", type="regard", geometry=Point(0, 0), x=0, y=0)
    graphe.add_edge("R2", "R1", length=1, geometry=LineString([(0, 0), (1, 0)]))

    raccordement = proposer_raccordement_exutoire(graphe, "SR1", distance_max_m=2)
    edges = {("R2", "R1")}
    polygon = calculer_polygone_urbain_estime(graphe, edges, {"R1", "R2"})

    assert raccordement["statut"] == "propose"
    assert raccordement["noeud_reseau"] == "R1"
    assert polygon is not None and polygon.area > 0
