#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : Pilotage Réseau d'Assainissement
Numéro version : 1.0.0
Date de création : 02-04-2026
Date de modification : 02-04-2026
Objectif : Définition des routes Flask pour l'API de visualisation
et le service de l'interface web. Point d'entrée HTTP
pour la carte interactive et les données GeoJSON.
"""

import logging
from pathlib import Path

from flask import (
    Flask, jsonify, make_response, request, send_from_directory
)

from src.infrastructure.chargeur_geopackage import (
    charger_donnees, vider_cache
)
from src.domain.graphe_reseau import (
    construire_graphe, trouver_exutoires
)
from src.domain.detecteur_clusters import (
    tracer_cluster_depuis_exutoire,
    construire_geojson_cluster,
    calculer_statistiques
)

logger = logging.getLogger(__name__)

CHEMIN_VUES = Path(__file__).parent.parent / "views"

app = Flask(__name__)
logging.getLogger("werkzeug").setLevel(logging.ERROR)


@app.route("/")
def index():
    """Sert la page principale."""
    reponse = make_response(
        CHEMIN_VUES.joinpath("index.html").read_text(encoding="utf-8")
    )
    reponse.headers["Cache-Control"] = (
        "no-cache, no-store, must-revalidate"
    )
    return reponse


@app.route("/styles.css")
def styles():
    """Sert la feuille de style."""
    return send_from_directory(CHEMIN_VUES, "styles.css")


@app.route("/carte.js")
def carte_js():
    """Sert le script JavaScript."""
    return send_from_directory(CHEMIN_VUES, "carte.js")


@app.route("/get-data")
def get_data():
    """Retourne les données GeoJSON de toutes les couches."""
    if request.args.get("reload"):
        vider_cache()

    couches = charger_donnees()
    vide = {"type": "FeatureCollection", "features": []}

    reponse = jsonify({
        "regards": couches.get("regards", vide),
        "rejets": couches.get("rejets", vide),
        "conduites": couches.get("conduites", vide),
        "ouvrages": couches.get("ouvrages", vide),
        "stations": couches.get("stations", vide),
        "step": couches.get("step", vide),
        "center": couches.get("_center"),
        "rues_labels": couches.get("rues_labels", vide),
    })
    reponse.headers["Cache-Control"] = (
        "no-cache, no-store, must-revalidate"
    )
    return reponse


@app.route("/get-all-clusters")
def get_all_clusters():
    """Trace les clusters de tous les exutoires."""
    import time

    t0 = time.time()

    print("[cluster] Construction du graphe …", flush=True)
    G = construire_graphe()

    print("[cluster] Recherche des exutoires …", flush=True)
    exutoires = trouver_exutoires(G)

    if not exutoires:
        return jsonify({
            "clusters": [],
            "total_exutoires": 0,
            "total_conduites": 0,
            "temps_s": 0
        })

    print(f"[cluster] Traitement de {len(exutoires)} exutoires …",
          flush=True)

    clusters = []
    total_conduites = 0

    for i, exutoire in enumerate(exutoires):
        edges = tracer_cluster_depuis_exutoire(
            G, exutoire["noeud"]
        )

        if not edges:
            continue

        geojson = construire_geojson_cluster(G, edges)
        stats = calculer_statistiques(G, edges)
        total_conduites += stats["nb_conduites"]

        clusters.append({
            "exutoire": exutoire,
            "stats": stats,
            "geojson": geojson
        })

    duree = round(time.time() - t0, 1)

    print(f"[cluster] {len(clusters)} clusters créés, "
          f"{total_conduites} conduites, {duree}s",
          flush=True)

    import math

    def nettoyer(val):
        """Remplace NaN et Inf par 0."""
        if isinstance(val, float) and (
            math.isnan(val) or math.isinf(val)
        ):
            return 0
        return val

    for cl in clusters:
        cl["stats"] = {
            k: nettoyer(v) for k, v in cl["stats"].items()
        }
        for feat in cl["geojson"].get("features", []):
            props = feat.get("properties", {})
            for k in list(props.keys()):
                props[k] = nettoyer(props[k])

    return jsonify({
        "clusters": clusters,
        "total_exutoires": len(exutoires),
        "total_conduites": total_conduites,
        "temps_s": duree
    })


def demarrer_serveur():
    """Démarre le serveur Flask."""
    print("", flush=True)
    print("[data] ═══════════════════════════════════════",
          flush=True)
    print("[data]  Démarrage du serveur …", flush=True)
    print("[data] ═══════════════════════════════════════",
          flush=True)
    print("", flush=True)
    print("[data] Étape 1/3 : Chargement des données …",
          flush=True)
    charger_donnees()

    print("", flush=True)
    print("[data] Étape 2/3 : Configuration du serveur …",
          flush=True)

    print("", flush=True)
    print("[data] Étape 3/3 : Démarrage HTTP …", flush=True)

    print("", flush=True)
    print("[data] ═══════════════════════════════════════",
          flush=True)
    print("[data]  SERVEUR PRÊT", flush=True)
    print("[data] ═══════════════════════════════════════",
          flush=True)
    print("[data]", flush=True)
    print("[data]  Ouvrez votre navigateur :", flush=True)
    print("[data]  → http://localhost:5000", flush=True)
    print("[data]", flush=True)
    print("[data]  Ctrl+C pour arrêter.", flush=True)
    print("[data] ═══════════════════════════════════════",
          flush=True)
    print("", flush=True)

    app.run(debug=False, port=5000, threaded=True)
