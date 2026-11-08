"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Point d'entrée serveur pour le déploiement conteneurisé
================================================================================
"""

import json
import logging
import os
from pathlib import Path
from flask import Flask, render_template, jsonify, request
import geopandas as gpd
import networkx as nx
from src.infrastructure.persistance_manuelle import (
    sauvegarder_bassin_manuel, 
    charger_bassins_manuels,
    supprimer_bassin_manuel
)

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

@app.route('/carte')
def get_carte():
    """Sert l'interface cartographique de visualisation"""
    return render_template('carte.html')

@app.route('/tunnel')
def get_tunnel():
    """Sert l'interface du tunnel en 4 étapes"""
    return render_template('tunnel.html')

@app.route('/api/v1/layers')
def api_layers():
    global _DATA_CACHE
    if _DATA_CACHE is None:
        print("[SERVER] Chargement initial des données...")
        _DATA_CACHE = charger_donnees()
    return jsonify(_DATA_CACHE)

@app.route('/api/v1/manual-basin', methods=['POST'])
def api_save_manual_basin():
    data = request.json
    res = sauvegarder_bassin_manuel(data)
    return jsonify(res)

@app.route('/api/v1/manual-basin/<bassin_id>', methods=['DELETE'])
def api_delete_manual_basin(bassin_id):
    res = supprimer_bassin_manuel(bassin_id)
    return jsonify({"status": "ok" if res else "error"})

@app.route('/api/v1/cluster')
def api_cluster():
    """Détecte les bassins urbains exclusifs (sans chevauchement)."""
    global _GLOBAL_GRAPH
    try:
        # Graphe en cache
        if _GLOBAL_GRAPH is None:
            print("[SERVER] Construction initiale du graphe...")
            from src.domain.detecteur_clusters import construire_graphe_depuis_geopackage
            _GLOBAL_GRAPH = construire_graphe_depuis_geopackage()
        G = _GLOBAL_GRAPH

        if G is None or len(G.nodes()) == 0:
            return jsonify({"type": "FeatureCollection", "features": []})

        # Importer les fonctions de détection de bassins
        from src.domain.detecteur_clusters import (
            trouver_exutoires_physiques,
            partitionner_bassins_hydrauliques,
            determiner_nom_bassin,
        )

        # Identifier les exutoires physiques
        exutoires = trouver_exutoires_physiques(G)
        if not exutoires:
            logger.warning("[cluster] Aucun exutoire physique trouvé")
            return jsonify({"type": "FeatureCollection", "features": []})

        # ── Partition hydraulique : bassins exclusifs sans inclusion ──────
        #    Conforme à la littérature : chaque bassin draine vers son exutoire,
        #    pas de chevauchement, pas d'inclusion, série et parallèle gérés.
        bassins, nb_orphelines, _ = partitionner_bassins_hydrauliques(G, exutoires)

        all_features = []
        for i, (noeud_exutoire, info) in enumerate(exutoires.items()):
            edges = bassins.get(noeud_exutoire, set())
            if not edges:
                continue

            # Calculer le polygone du bassin à partir des arêtes
            from src.domain.detecteur_clusters import calculer_bassin_polygon
            bassin_hull = calculer_bassin_polygon(edges, G=G)

            # Déterminer le nom du bassin depuis les données de la zone drainée
            nom_bassin = determiner_nom_bassin(edges, G, exutoire_info=info)

            cluster_geojson = construire_geojson_cluster(
                G, edges,
                bassin_hull=bassin_hull,
                cluster_id=i + 1,
                exutoire_node=noeud_exutoire,
                exutoire_info=info,
                nom_bassin=nom_bassin
            )

            if cluster_geojson and "features" in cluster_geojson:
                # Enrichir le nom du bassin avec le type d'exutoire
                for feat in cluster_geojson["features"]:
                    if feat["properties"].get("type") == "bassin_urbain":
                        feat["properties"]["nom"] = (
                            f"{nom_bassin} "
                            f"[{info.get('type','?').upper()}]"
                        )
                        feat["properties"]["exutoire_type"] = info.get("type", "")
                all_features.extend(cluster_geojson["features"])

        # 4. Intégrer les bassins manuels
        manual_bassins = charger_bassins_manuels()
        for mb in manual_bassins:
            conduit_ids = mb.get("conduits", [])
            # Retrouver les arêtes correspondantes dans le graphe
            edges_manual = set()
            for u, v, attrs in G.edges(data=True):
                if attrs.get("conduit_id") in conduit_ids or attrs.get("fid") in conduit_ids:
                    edges_manual.add((u, v))

            if edges_manual:
                from src.domain.detecteur_clusters import calculer_bassin_polygon
                hull = calculer_bassin_polygon(edges_manual, G=G)
                info_ex = mb.get("exutoire") or {"nom": mb.get("nom", "Manuel"), "type": "manuel"}
                
                # Réutiliser construire_geojson_cluster
                # Note: noeud_exutoire pour un bassin manuel peut être extrait de l'info exutoire
                noeud_ex = None
                if mb.get("exutoire") and mb["exutoire"].get("latlng"):
                    ll = mb["exutoire"]["latlng"]
                    noeud_ex = (ll["lng"], ll["lat"])

                mb_geojson = construire_geojson_cluster(
                    G, edges_manual,
                    bassin_hull=hull,
                    cluster_id=f"M_{mb['id']}",
                    exutoire_node=noeud_ex,
                    exutoire_info=info_ex
                )
                
                if mb_geojson and "features" in mb_geojson:
                    for feat in mb_geojson["features"]:
                        if feat["properties"].get("type") == "bassin_urbain":
                            feat["properties"]["nom"] = f"{mb.get('nom')} [MANUEL]"
                            feat["properties"]["exutoire_type"] = info_ex.get("type", "manuel")
                    all_features.extend(mb_geojson["features"])

        logger.info(f"[cluster] {len(bassins)} auto + {len(manual_bassins)} manuels générés")
        return jsonify({
            "type": "FeatureCollection", 
            "features": all_features,
            "nb_orphelines": nb_orphelines
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
