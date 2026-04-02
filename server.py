#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : Pilotage Réseau d'Assainissement
Numéro version : 1.0.0
Date de création : 2026-04-02
Date de modification : 2026-04-02
Objectif : Point d'entrée principal du serveur Flask.
Démarre le serveur de visualisation interactive
du réseau d'assainissement.
"""

import sys
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8"
    )
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8"
    )

from src.controllers.routeur_flask import demarrer_serveur

if __name__ == "__main__":
    demarrer_serveur()
