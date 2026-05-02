import json
import logging
import os
from pathlib import Path
from flask import Flask, render_template, jsonify
import geopandas as gpd
import networkx as nx

app = Flask(__name__, template_folder='templates', static_folder='static')
logger = logging.getLogger(__name__)

GPKG_PATH = Path(r"D:\IA Water Data Analysis\Assainissement\Assainissement_Ville.gpkg")
WGS84 = "EPSG:4326"

# Caches globaux pour la performance
_DATA_CACHE = None
_GLOBAL_GRAPH = None

KEYWORDS = {
    'conduites': 'canalisations',
    'regards': 'regards',
    'stations': 'station_de_relevage',
    'step': 'step',
    'ouvrages': 'ouvrages_speciaux'
}

def charger_donnees():
    result = {"statut": "ok", "couches": {}, "compteurs": {}}
    try:
        layers = gpd.list_layers(GPKG_PATH)['name'].tolist()
    except Exception as e:
        print(f"[ERROR] Impossible de lister les couches: {e}")
        return result
    for key, motcle in KEYWORDS.items():
        layer_name = next((l for l in layers if motcle.lower() in l.lower()), None)
        if not layer_name:
            result["couches"][key] = {"type": "FeatureCollection", "features": []}
            result["compteurs"][key] = 0
            continue
        try:
            gdf = gpd.read_file(GPKG_PATH, layer=layer_name)
            if gdf.crs and gdf.crs != WGS84:
                gdf = gdf.to_crs(WGS84)
            geojson = json.loads(gdf.to_json())
            result["couches"][key] = geojson
            result["compteurs"][key] = len(geojson.get('features', []))
        except Exception as e:
            print(f"[ERROR] {key}: {e}")
            result["couches"][key] = {"type": "FeatureCollection", "features": []}
            result["compteurs"][key] = 0
    return result

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/v1/layers')
def api_layers():
    global _DATA_CACHE
    if _DATA_CACHE is None:
        print("[SERVER] Chargement initial des données...")
        _DATA_CACHE = charger_donnees()
    return jsonify(_DATA_CACHE)

@app.route('/api/v1/cluster')
def api_cluster():
    """Endpoint pour détecter et retourner les clusters hydrauliques."""
    global _GLOBAL_GRAPH
    try:
        from src.domain.detecteur_clusters import (
            construire_graphe_depuis_geopackage, 
            trouver_exutoires_physiques, 
            tracer_cluster_depuis_exutoire, 
            construire_geojson_cluster,
            calculer_bassin_polygon
        )
        
        # Construire le graphe une seule fois (cache)
        if _GLOBAL_GRAPH is None:
            print("[SERVER] Construction initiale du graphe...")
            _GLOBAL_GRAPH = construire_graphe_depuis_geopackage()
        G = _GLOBAL_GRAPH
        
        if G is None or len(G.nodes()) == 0:
            logger.warning("[cluster] Graphe vide")
            return jsonify({"type": "FeatureCollection", "features": []})
        
        # Trouver les exutoires physiques
        exutoires = trouver_exutoires_physiques(G)
        
        # Si aucun exutoire physique trouvé, chercher les nœuds de sortie
        if not exutoires:
            logger.warning("[cluster] Aucun exutoire physique, recherche des sorties de graphe")
            noeuds_sortie = [n for n in G.nodes() if G.out_degree(n) == 0 and G.in_degree(n) > 0]
            exutoires = {noeud: {"type": "sortie_graphe", "nom": f"Sortie_{i}", "distance": 0} 
                        for i, noeud in enumerate(noeuds_sortie[:20])} # Limité à 20 pour la démo
        
        all_features = []
        processed_exutoires = 0
        
        # On traite chaque exutoire séparément pour avoir des bassins distincts
        for i, (noeud_exutoire, info) in enumerate(exutoires.items()):
            if noeud_exutoire not in G: continue
            
            edges = tracer_cluster_depuis_exutoire(G, noeud_exutoire)
            if not edges: continue
            
            # Calculer le polygone du bassin pour ce cluster
            bassin_hull = calculer_bassin_polygon(edges)
            
            # Générer le GeoJSON pour CE cluster spécifique
            cluster_geojson = construire_geojson_cluster(
                G, edges, 
                bassin_hull=bassin_hull, 
                cluster_id=i+1
            )
            
            if cluster_geojson and "features" in cluster_geojson:
                all_features.extend(cluster_geojson["features"])
                processed_exutoires += 1
        
        logger.info(f"[cluster] {processed_exutoires} bassins urbains générés")
        
        return jsonify({
            "type": "FeatureCollection",
            "features": all_features
        })
        
    except Exception as e:
        logger.error(f"[ERROR] Cluster detection: {e}", exc_info=True)
        return jsonify({"type": "FeatureCollection", "features": []})

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    print(f"[SERVER] GPKG: {GPKG_PATH}")
    app.run(debug=True, host='0.0.0.0', port=5000)
