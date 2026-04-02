#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : Pilotage Réseau d'Assainissement
Numéro version : 1.0.0
Date de création : 2026-04-02
Date de modification : 2026-04-02
Objectif : Définition des routes Flask pour l'API de visualisation
et le service de l'interface web. Point d'entrée HTTP
pour la carte interactive et les données GeoJSON.
"""

import logging
from pathlib import Path

from flask import (
    Flask, jsonify, make_response, request
)

from src.infrastructure.chargeur_geopackage import (
    charger_donnees, vider_cache
)

logger = logging.getLogger(__name__)

CHEMIN_HTML = Path(__file__).parent.parent / "views" / "index.html"

app = Flask(__name__)
logging.getLogger("werkzeug").setLevel(logging.ERROR)


@app.route("/")
def index():
    """Sert la page principale."""
    reponse = make_response(
        CHEMIN_HTML.read_text(encoding="utf-8")
    )
    reponse.headers["Cache-Control"] = (
        "no-cache, no-store, must-revalidate"
    )
    return reponse


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


def demarrer_serveur():
    """Démarre le serveur Flask."""
    print("[data] Pré-chargement …")
    charger_donnees()

    print("""

    ╔════════════════════════════════════════════════════╗
    ║   SERVEUR RÉSEAU D'ASSAINISSEMENT DÉMARRÉ          ║
    ╚════════════════════════════════════════════════════╝

    Ouvrez votre navigateur :
       http://localhost:5000

    Appuyez sur Ctrl+C pour arrêter.
    """)

    app.run(debug=False, port=5000, threaded=True)
