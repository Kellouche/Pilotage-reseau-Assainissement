"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Prototype d'arbre hydraulique et parcours orienté des graphes
================================================================================
"""

import json
import math
import argparse
from pathlib import Path

import geopandas as gpd
import networkx as nx
from shapely.geometry import Point, mapping
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT.parent / "Assainissement_Ville.gpkg"
OUTPUT = Path(__file__).parent / "output"
STATION_CODE = "SR_HH02"
RADIUS_M = 1200.0

LAYERS = {
    "pipes": "Canalisations_860f298d_9fd9_40a5_bfa4_f913acc71f2e",
    "nodes": "Regards_e3c22000_8bba_45a0_a575_d60bb4d99d3",
    "stations": "Station_de_relevage_5c8a759c_c2c5_46cb_a2be_8993c368e0c2",
}


def identifier(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    if text.endswith(".0"):
        try:
            return str(int(float(text)))
        except ValueError:
            pass
    return text


def safe_length(value, geometry):
    try:
        result = float(value)
        if math.isfinite(result) and result > 0:
            return result
    except (TypeError, ValueError):
        pass
    return float(geometry.length)


def select_sample(pipes, nodes, stations, station_code, radius_m):
    station = stations[stations["CODEPRR"].map(identifier) == station_code]
    if station.empty:
        raise RuntimeError(f"Station introuvable: {STATION_CODE}")
    station = station.iloc[[0]]
    area = station.geometry.iloc[0].buffer(radius_m)
    selected_pipes = pipes[pipes.geometry.intersects(area)].copy()
    selected_node_ids = set()
    for column in ("ID_AMONT", "ID_AVAL"):
        selected_node_ids.update(
            value for value in selected_pipes[column].map(identifier).dropna()
        )
    selected_nodes = nodes[nodes["Code"].map(identifier).isin(selected_node_ids)].copy()
    return station, selected_pipes, selected_nodes


def build_graph(pipes, nodes, station):
    graph = nx.DiGraph()
    for _, row in nodes.iterrows():
        node_id = identifier(row.get("Code"))
        if node_id:
            graph.add_node(node_id, geometry=row.geometry, kind="regard")

    station_id = identifier(station["CODEPRR"].iloc[0])
    station_point = station.geometry.iloc[0]
    graph.add_node(station_id, geometry=station_point, kind="station")

    diagnostics = {"missing_endpoints": [], "edges": 0, "duplicate_endpoint_pairs": 0}
    for _, row in pipes.iterrows():
        upstream = identifier(row.get("ID_AMONT"))
        downstream = identifier(row.get("ID_AVAL"))
        if not upstream or not downstream:
            diagnostics["missing_endpoints"].append(identifier(row.get("fid")) or "unknown")
            continue
        if upstream not in graph or downstream not in graph:
            diagnostics["missing_endpoints"].append(identifier(row.get("fid")) or "unknown")
            continue
        if graph.has_edge(upstream, downstream):
            diagnostics["duplicate_endpoint_pairs"] += 1
        graph.add_edge(
            upstream,
            downstream,
            pipe_id=identifier(row.get("fid")) or identifier(row.get("id")),
            length=safe_length(row.get("LINEAIRE"), row.geometry),
            geometry=row.geometry,
        )
        diagnostics["edges"] += 1

    station_candidates = [
        (station_point.distance(data["geometry"]), node)
        for node, data in graph.nodes(data=True)
        if node != station_id and data.get("geometry") is not None
    ]
    nearest_distance, nearest_node = min(station_candidates) if station_candidates else (None, None)
    if graph.in_degree(station_id) == 0 and nearest_node is not None:
        diagnostics["station_snap_candidate"] = {
            "node": nearest_node,
            "distance_m": round(nearest_distance, 2),
        }
    return graph, station_id, diagnostics


def branch_tree(graph, outlet):
    if outlet not in graph:
        return {"outlet": outlet, "nodes": [], "edges": [], "leaves": [], "cycles": []}

    upstream_nodes = nx.ancestors(graph, outlet) | {outlet}
    subgraph = graph.subgraph(upstream_nodes).copy()
    cycles = [list(cycle) for cycle in nx.simple_cycles(subgraph)]
    tree_edges = []
    branches = []
    branch_counter = 0

    def upstream_weight(node):
        return sum(data.get("length", 0.0) for _, _, data in subgraph.in_edges(node, data=True))

    def walk(node, order, branch_id):
        predecessors = list(subgraph.predecessors(node))
        if not predecessors:
            return [node]
        ranked = sorted(predecessors, key=upstream_weight, reverse=True)
        main = ranked[0]
        branch_nodes = [node]
        for predecessor in ranked:
            next_order = order if predecessor == main else order + 1
            edge_data = subgraph.edges[predecessor, node]
            tree_edges.append({
                "from": predecessor,
                "to": node,
                "order": next_order,
                "branch": branch_id if predecessor == main else f"B{len(branches) + 1}",
                "pipe_id": edge_data.get("pipe_id"),
                "length_m": round(edge_data.get("length", 0.0), 2),
            })
            branch_nodes.extend(walk(predecessor, next_order, tree_edges[-1]["branch"]))
        return branch_nodes

    walk(outlet, 0, "B0")
    leaves = [node for node in subgraph if subgraph.in_degree(node) == 0]
    return {
        "outlet": outlet,
        "nodes": sorted(str(node) for node in subgraph.nodes),
        "edges": tree_edges,
        "leaves": sorted(str(node) for node in leaves),
        "cycles": cycles,
    }


def build_estimated_polygons(graph, tree):
    """Construit des géométries de travail, jamais une surface hydrologique."""
    if not tree or not tree.get("edges"):
        return None, None
    corridors = []
    points = []
    for edge in tree["edges"]:
        data = graph.edges[edge["from"], edge["to"]]
        geometry = data.get("geometry")
        if geometry is not None:
            corridors.append(geometry.buffer(15.0))
    for node in tree["nodes"]:
        geometry = graph.nodes[node].get("geometry")
        if geometry is not None:
            points.append(geometry)
    if not corridors or not points:
        return None, None
    network_footprint = unary_union(corridors + [point.buffer(15.0) for point in points])
    urban_envelope = unary_union([point.buffer(50.0) for point in points])
    urban_envelope = urban_envelope.union(network_footprint).buffer(5.0).buffer(-5.0)
    return network_footprint, urban_envelope


def main():
    parser = argparse.ArgumentParser(description="Essai arbre hydraulique et correction de raccordement")
    parser.add_argument("--station", default=STATION_CODE)
    parser.add_argument("--radius", type=float, default=RADIUS_M)
    parser.add_argument("--outlet", help="Nœud réseau à utiliser comme raccordement manuel")
    args = parser.parse_args()
    OUTPUT.mkdir(exist_ok=True)
    if not SOURCE.exists():
        raise FileNotFoundError(f"GeoPackage absent: {SOURCE}")
    available_layers = gpd.list_layers(SOURCE)["name"].tolist()
    layer_names = {
        "pipes": next(name for name in available_layers if name.startswith("Canalisations_")),
        "nodes": next(name for name in available_layers if name.startswith("Regards_")),
        "stations": next(name for name in available_layers if name.startswith("Station_de_relevage_")),
    }
    pipes = gpd.read_file(SOURCE, layer=layer_names["pipes"])
    nodes = gpd.read_file(SOURCE, layer=layer_names["nodes"])
    stations = gpd.read_file(SOURCE, layer=layer_names["stations"])
    station, selected_pipes, selected_nodes = select_sample(
        pipes, nodes, stations, args.station, args.radius
    )
    graph, station_id, diagnostics = build_graph(selected_pipes, selected_nodes, station)
    candidate = diagnostics.get("station_snap_candidate", {}).get("node")
    if args.outlet:
        if args.outlet not in graph:
            raise RuntimeError(f"Raccordement manuel absent du sous-réseau: {args.outlet}")
        active_outlet = args.outlet
        decision = {"mode": "manual_cli", "outlet": active_outlet}
    elif candidate:
        active_outlet = candidate
        decision = {"mode": "proposed", "outlet": active_outlet}
    else:
        active_outlet = station_id
        decision = {"mode": "unconnected", "outlet": active_outlet}
    active_tree = branch_tree(graph, active_outlet)
    candidate_tree = branch_tree(graph, candidate) if candidate else None
    network_footprint, urban_estimated = build_estimated_polygons(graph, active_tree)
    report = {
        "source": str(SOURCE),
        "station": args.station,
        "radius_m": args.radius,
        "connection_decision": decision,
        "sample": {
            "pipes": len(selected_pipes),
            "nodes": len(selected_nodes),
            "graph_nodes": graph.number_of_nodes(),
            "graph_edges": graph.number_of_edges(),
        },
        "diagnostics": diagnostics,
        "tree": active_tree,
        "tree_raw_station": branch_tree(graph, station_id),
        "tree_if_snapped_to_nearest_node": candidate_tree,
        "polygons": {
            "source": "active_tree",
            "network_footprint_area_m2": round(network_footprint.area, 2) if network_footprint else 0.0,
            "urban_estimated_area_m2": round(urban_estimated.area, 2) if urban_estimated else 0.0,
            "warning": "Polygone géométrique provisoire, sans MNT ni parcelles drainées.",
        },
    }
    (OUTPUT / "tree_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    selected_pipes.to_file(OUTPUT / "sample_pipes.geojson", driver="GeoJSON")
    selected_nodes.to_file(OUTPUT / "sample_nodes.geojson", driver="GeoJSON")
    station.to_file(OUTPUT / "sample_station.geojson", driver="GeoJSON")
    polygon_features = []
    for name, geometry in (("empreinte_reseau", network_footprint), ("polygone_urbain_estime", urban_estimated)):
        if geometry is not None:
            polygon_features.append({
                "type": "Feature",
                "properties": {"type": name, "confiance": "faible", "source": "arbre_reseau"},
                "geometry": mapping(geometry),
            })
    (OUTPUT / "estimated_polygons.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": polygon_features}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
