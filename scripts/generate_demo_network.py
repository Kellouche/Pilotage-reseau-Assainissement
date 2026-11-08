"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Génération d'un jeu de données synthétique pour le réseau de démonstration
================================================================================
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
import networkx as nx
from src.domain.graphe_reseau import construire_graphe

def generate_clean_demo():
    master_path = r"D:\IA Water Data Analysis\Assainissement\Assainissement_Ville.gpkg"
    output_path = Path("data/demo_reseau.gpkg")

    print("[1/5] Building master graph to extract connected sub-basin...")
    G = construire_graphe(master_path)
    undir = G.to_undirected()
    comps = [c for c in nx.connected_components(undir) if 40 <= len(c) <= 150]
    c6 = comps[6]
    subG = G.subgraph(c6)

    edge_geoms = [data['geometry'] for u, v, data in subG.edges(data=True)]
    node_codes = [float(n) if n.replace('.','',1).isdigit() else n for n in c6]
    sinks = [n for n in c6 if subG.out_degree(n) == 0]
    sink_id = sinks[0]

    print(f"[2/5] Selected sub-basin Hay En-Nasr: {len(c6)} nodes, {len(edge_geoms)} edges, sink={sink_id}")

    print("[3/5] Reading master layers...")
    all_canalisations = gpd.read_file(master_path, layer="Canalisations_860f298d_9fd9_40a5_bfa4_f913acc71f2e")
    all_regards = gpd.read_file(master_path, layer="Regards_e3c22000_8bba_45a0_a575_d60bbd4b99d3")

    matched_cana_indices = []
    for eg in edge_geoms:
        cand = all_canalisations[all_canalisations.geometry.geom_equals(eg)]
        if len(cand) > 0:
            matched_cana_indices.append(cand.index[0])

    demo_canalisations = all_canalisations.loc[matched_cana_indices].copy()
    demo_regards = all_regards[all_regards['Code'].isin(node_codes)].copy()

    # Create 1 outfall (rejet) at the sink node position
    sink_node_data = G.nodes[sink_id]
    sink_point = Point(sink_node_data['x'], sink_node_data['y'])
    demo_rejet = gpd.GeoDataFrame([{
        'id': 'REJ-DEMO-01',
        'NOM': 'Exutoire Hay En-Nasr',
        'CODE': 'EX-01',
        'COTETN': sink_node_data.get('z_tampon', 100.0),
        'COMMUNE': 'Zone Urbaine',
        'NOM_VOIE': sink_node_data.get('nom_voie', 'Rue Principale'),
        'geometry': sink_point
    }], crs=demo_regards.crs)

    # Drop fid column if present to avoid GeoPackage primary key collision
    for df in [demo_canalisations, demo_regards, demo_rejet]:
        cols_to_drop = [c for c in df.columns if c.lower() in ('fid', 'fid_')]
        if cols_to_drop:
            df.drop(columns=cols_to_drop, inplace=True)
        df.reset_index(drop=True, inplace=True)

    print(f"[4/5] Writing {output_path} with {len(demo_canalisations)} canalisations, {len(demo_regards)} regards, {len(demo_rejet)} rejet...")
    if output_path.exists():
        output_path.unlink()

    demo_canalisations.to_file(output_path, layer="canalisations", driver="GPKG", mode="w")
    demo_regards.to_file(output_path, layer="regards", driver="GPKG", mode="a")
    demo_rejet.to_file(output_path, layer="rejets", driver="GPKG", mode="a")

    print("[5/5] Verification of created demo GeoPackage:")
    layers = gpd.list_layers(output_path)
    print(layers)

    # Test bounds in WGS84
    reg_wgs = demo_regards.to_crs("EPSG:4326")
    cana_wgs = demo_canalisations.to_crs("EPSG:4326")
    tb = cana_wgs.total_bounds
    print(f"Bbox WGS84: SW=[{tb[1]:.5f}, {tb[0]:.5f}], NE=[{tb[3]:.5f}, {tb[2]:.5f}]")
    print("Done!")

if __name__ == "__main__":
    generate_clean_demo()
