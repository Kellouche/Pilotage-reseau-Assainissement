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
    """Détecte les bassins urbains exclusifs (sans chevauchement)."""
    global _GLOBAL_GRAPH
    try:
        from src.domain.detecteur_clusters import (
            construire_graphe_depuis_geopackage,
            trouver_exutoires_physiques,
            partitionner_bassins_exclusifs,
            construire_geojson_cluster,
            calculer_bassin_polygon
        )

        # Graphe en cache
        if _GLOBAL_GRAPH is None:
            print("[SERVER] Construction initiale du graphe...")
            _GLOBAL_GRAPH = construire_graphe_depuis_geopackage()
        G = _GLOBAL_GRAPH

        if G is None or len(G.nodes()) == 0:
            return jsonify({"type": "FeatureCollection", "features": []})

        # Identifier les exutoires physiques
        exutoires = trouver_exutoires_physiques(G)
        if not exutoires:
            logger.warning("[cluster] Aucun exutoire physique trouvé")
            return jsonify({"type": "FeatureCollection", "features": []})

        # ── Partition BFS multi-sources : bassins exclusifs ──────────────
        # Chaque conduite est attribuée à UN SEUL bassin (pas de doublon)
        bassins = partitionner_bassins_exclusifs(G, exutoires)
        # ─────────────────────────────────────────────────────────────────

        all_features = []
        for i, (noeud_exutoire, edges) in enumerate(bassins.items()):
            if not edges:
                continue

            info = exutoires[noeud_exutoire]
            bassin_hull = calculer_bassin_polygon(edges)

            cluster_geojson = construire_geojson_cluster(
                G, edges,
                bassin_hull=bassin_hull,
                cluster_id=i + 1
            )

            if cluster_geojson and "features" in cluster_geojson:
                # Enrichir le nom du bassin avec le type d'exutoire
                for feat in cluster_geojson["features"]:
                    if feat["properties"].get("type") == "bassin_urbain":
                        feat["properties"]["nom"] = (
                            f"{info.get('nom', f'Bassin {i+1}')} "
                            f"[{info.get('type','?').upper()}]"
                        )
                        feat["properties"]["exutoire_type"] = info.get("type", "")
                all_features.extend(cluster_geojson["features"])

        logger.info(f"[cluster] {len(bassins)} bassins exclusifs générés")
        return jsonify({"type": "FeatureCollection", "features": all_features})

    except Exception as e:
        logger.error(f"[ERROR] Cluster detection: {e}", exc_info=True)
        return jsonify({"type": "FeatureCollection", "features": []})

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    print(f"[SERVER] GPKG: {GPKG_PATH}")
    app.run(debug=True, host='0.0.0.0', port=5000)
