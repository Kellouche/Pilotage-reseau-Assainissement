"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Script d'harmonisation et d'application systématique des en-têtes standardisés
================================================================================
"""

import os
import re
import ast

CANONICAL_PY_HEADER = """\"\"\"
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : {objet}
================================================================================
\"\"\""""

CANONICAL_HTML_HEADER = """<!--
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : {objet}
================================================================================
-->"""

CANONICAL_JS_HEADER = """/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : {objet}
 * ================================================================================
 */"""

MODULE_OBJECTS = {
    # Core API & routes
    "api/__init__.py": "Point d'entrée du package API DrainPilot",
    "api/main.py": "Application FastAPI principale, middlewares, CORS et montage des routeurs",
    "api/database.py": "Gestionnaire de connexions PostgreSQL / PostGIS et SQLite local",
    "api/models.py": "Modèles SQLAlchemy ORM pour le réseau, les bassins et les simulations",
    "api/models_terrain.py": "Modèles de données pour la synchronisation terrain et relevés d'anomalies",
    "api/schemas.py": "Schémas Pydantic de validation des requêtes et réponses SWMM",
    "api/schemas_auth.py": "Schémas Pydantic d'authentification, utilisateurs et organisations",
    "api/schemas_terrain.py": "Schémas Pydantic pour la collecte terrain et signalements d'anomalies",
    "api/crud.py": "Opérations CRUD base de données pour nœuds, conduites et simulations",
    "api/crud_terrain.py": "Opérations CRUD pour les relevés terrain et photos géolocalisées",
    "api/websocket.py": "Gestionnaire WebSocket temps réel pour la progression des calculs SWMM",
    "api/routes/__init__.py": "Point d'entrée du sous-package des routes API REST",
    "api/routes/admin.py": "Endpoints d'administration système, maintenance et métriques globales",
    "api/routes/artifacts.py": "Endpoints de gestion et téléchargement des artefacts de simulation",
    "api/routes/audit.py": "Journal d'audit des actions utilisateurs, modifications et traçabilité",
    "api/routes/auth.py": "Endpoints d'authentification JWT, inscription, connexion et sessions",
    "api/routes/clusters.py": "Endpoints de sectorisation, détection de bassins et sous-bassins",
    "api/routes/corrections.py": "Endpoints de validation et d'application des correctifs topologiques",
    "api/routes/jobs.py": "Endpoints de suivi des jobs asynchrones Celery et calculs de fond",
    "api/routes/licensing.py": "Gestion des licences d'exploitation, quotas et clés d'activation",
    "api/routes/mnt.py": "Endpoints d'analyse altimétrique et découpage topographique MNT",
    "api/routes/network.py": "Endpoints de gestion du réseau physique (nœuds, conduites, regards, exutoires)",
    "api/routes/organization.py": "Gestion multi-tenant des organisations et espaces de travail",
    "api/routes/qualite.py": "Endpoints de contrôle qualité topologique et audit de connectivité",
    "api/routes/simulations.py": "Endpoints de lancement de simulation SWMM 5.2 et restitution des résultats",
    "api/routes/sync.py": "Endpoints de synchronisation bidirectionnelle mobile/terrain et bureau",
    "api/routes/terrain.py": "Endpoints mobiles pour la saisie terrain d'anomalies et photos d'ouvrages",
    "api/core/__init__.py": "Package des fonctionnalités centrales et utilitaires internes",
    "api/core/auth.py": "Logique d'authentification, hachage de mots de passe et gestion des tokens",
    "api/core/jobs.py": "Gestionnaire et suivi de la file de tâches asynchrones",
    "api/core/licensing.py": "Contrôle de validité des licences et vérification des droits d'accès",
    "api/core/mailer.py": "Service d'envoi de courriels transactionnels et notifications d'alertes",
    "api/core/proforma.py": "Génération de devis proforma et facturation automatisée",
    "api/core/quotas.py": "Vérification et respect des quotas de calculs et stockage multi-tenant",
    "api/core/security.py": "Utilitaires de chiffrement, tokens sécurisés et protection CSRF/XSS",
    "api/core/storage.py": "Gestionnaire de stockage des fichiers, rapports et rasters MNT",

    # Config
    "config/__init__.py": "Package de configuration globale du projet",
    "config/settings.py": "Paramètres d'environnement, configuration base de données et flags applicatifs",
    "config/validations_phase1.py": "Règles et critères de validation pour les livrables de Phase 1",

    # Domain & Domain Logic
    "src/domain/__init__.py": "Package des règles métier et du domaine d'ingénierie hydraulique",
    "src/domain/aides.py": "Fiches d'aide interactive, documentation méthodologique et guides d'ingénierie",
    "src/domain/contour_workflow.py": "Workflow automatisé d'extraction et de lissage des contours de bassins",
    "src/domain/detecteur_clusters.py": "Algorithmes de détection de clusters topologiques et bassins versants",
    "src/domain/extracteur_contours.py": "Algorithmes de vectorisation géométrique et enveloppes concaves",
    "src/domain/generateur_bassins_79.py": "Génération et calibration des bassins versants pour le scénario 79",
    "src/domain/graphe_reseau.py": "Modélisation du réseau d'assainissement sous forme de graphe orienté (NetworkX)",
    "src/domain/hydrologie.py": "Modélisation hydrologique (Horton, ruissellement et surfaces imperméables)",
    "src/domain/inp_parser.py": "Parseur et lecteur de fichiers de modélisation SWMM au format .INP",
    "src/domain/moteur_swmm.py": "Moteur d'orchestration et d'exécution des simulations hydrauliques SWMM 5.2",
    "src/domain/ouvrages_orphelins.py": "Détection, isolement et traitement des tronçons et ouvrages orphelins",
    "src/domain/processeur_conduites.py": "Traitement géométrique et hydraulique des tronçons et canalisations",
    "src/domain/processeur_noeuds.py": "Traitement géométrique et hydraulique des regards, jonctions et exutoires",
    "src/domain/processeur_pompes.py": "Modélisation hydraulique des postes de relevage et stations de pompage",
    "src/domain/referentiel_pluvio.py": "Référentiel pluviométrique (Montana, courbes IDF et pluies de projet)",

    # Agents Expertise
    "src/domain/agents_expertise.py": "Wrapper de compatibilité pour le module d'agents d'expertise IA et gestion durable des ouvrages (GDO)",
    "src/domain/agents_expertise/__init__.py": "Package des agents experts d'analyse post-simulation",
    "src/domain/agents_expertise/common.py": "Fonctions utilitaires communes et formatage monétaire / numérique DZD",
    "src/domain/agents_expertise/agent1_diagnostic.py": "Agent Expert 1 : Diagnostic causal hydraulique et goulots d'étranglement",
    "src/domain/agents_expertise/agent2_geniecivil.py": "Agent Expert 2 : Dimensionnement génie civil et métré des conduites",
    "src/domain/agents_expertise/agent3_gdo.py": "Agent Expert 3 : Gestion durable des ouvrages (GDO) et rétention",
    "src/domain/agents_expertise/agent4_risques.py": "Agent Expert 4 : Cartographie et évaluation multidimensionnelle des risques",
    "src/domain/agents_expertise/agent5_finance.py": "Agent Expert 5 : Chiffrage budgétaire DZD et priorisation financière",
    "src/domain/agents_expertise/agent6_synthese.py": "Agent Expert 6 : Synthèse décisionnelle et génération de rapport d'expertise",
    "src/domain/agents_expertise/orchestrateur.py": "Orchestrateur multi-agents d'expertise post-simulation SWMM",

    # Infrastructure & controllers
    "src/infrastructure/__init__.py": "Package d'infrastructure, entrées/sorties et persistance",
    "src/infrastructure/chargeur_geopackage.py": "Module de chargement et d'extraction des couches GeoPackage (.gpkg)",
    "src/infrastructure/config.py": "Configuration technique spécifique à l'infrastructure SIG",
    "src/infrastructure/labels_rues.py": "Gestionnaire d'étiquettes et toponymie des voies urbaines",
    "src/infrastructure/orientation_conduites.py": "Algorithme d'orientation automatique du sens d'écoulement",
    "src/infrastructure/parseur_inp.py": "Parseur bas-niveau pour les fichiers d'entrée SWMM",
    "src/infrastructure/persistance_manuelle.py": "Module de sauvegarde et persistance des corrections manuelles",
    "src/qualite_reseau.py": "Audit de qualité topologique, détection d'inversions de pente et anomalies",
    "src/analyse_qualite_gpkg.py": "Outil d'analyse qualité et de validation des couches GeoPackage",
    "src/validateurs/__init__.py": "Package des validateurs de cohérence du réseau",
    "src/validateurs/topologie.py": "Validateur de cohérence topologique et connectivité hydraulique",
    "src/controllers/__init__.py": "Package des contrôleurs de traitement de données",
    "src/controllers/generateur_donnees.py": "Contrôleur de génération de données de simulation",
    "src/controllers/generateur_liens.py": "Contrôleur de création et chaînage des liens hydrauliques",
    "src/controllers/generateur_noeuds.py": "Contrôleur de génération des nœuds et attributs de regards",
    "src/controllers/generateur_swmm.py": "Contrôleur de compilation des fichiers d'entrée SWMM",
    "src/controllers/routeur_flask.py": "Routeur de secours pour les vues legacy Flask",
    "src/views/__init__.py": "Package des vues et rendus graphiques",

    # Root scripts
    "run_server.py": "Script principal de démarrage du serveur Uvicorn DrainPilot 5.2",
    "run_api.py": "Script alternatif de lancement du serveur d'API REST",
    "server.py": "Point d'entrée serveur pour le déploiement conteneurisé",
    "migrate_gpkg_to_postgres.py": "Script de migration des données GeoPackage vers PostgreSQL/PostGIS",
    "appliquer_correctifs.py": "Script d'application batch des correctifs topologiques du réseau",
    "test_api.py": "Script de vérification de l'état des routes de l'API REST",
    "test_ws.py": "Script de test de connexion et messages WebSocket",

    # Scripts folder
    "scripts/build_golden_dataset.py": "Construction du jeu de données de référence (Golden Master)",
    "scripts/check_db.py": "Vérification de l'état et de la connectivité de la base de données",
    "scripts/db_check_sa.py": "Contrôle d'intégrité de la structure SQLAlchemy ORM",
    "scripts/generate_demo_network.py": "Génération d'un jeu de données synthétique pour le réseau de démonstration",

    # Prototypes
    "prototypes/hydraulic_tree_poc/run_trial.py": "Prototype d'arbre hydraulique et parcours orienté des graphes",

    # Workers
    "workers/__init__.py": "Package des workers asynchrones Celery",
    "workers/celery_app.py": "Instance et configuration de l'application Celery",
    "workers/swmm_worker.py": "Worker d'exécution des calculs lourds SWMM en arrière-plan",
    "workers/tasks/__init__.py": "Package des tâches asynchrones",
    "workers/tasks/mnt_tasks.py": "Tâches asynchrones de traitement et découpage altimétrique MNT",
    "workers/tasks/swmm_tasks.py": "Tâches asynchrones de simulation hydraulique SWMM",

    # Tests
    "tests/__init__.py": "Package de la suite de tests automatisée DrainPilot",
    "tests/conftest.py": "Fixtures Pytest globales, base de données de test et client HTTP",
    "tests/test_async_jobs.py": "Tests unitaires du système de gestion des jobs asynchrones",
    "tests/test_auth_multitenant.py": "Tests d'authentification, isolation multi-tenant et gestion des droits",
    "tests/test_bassin_simulation_sync.py": "Tests automatisés de synchronisation de la simulation par bassin et non-duplication des bandeaux",
    "tests/test_bassin_tooltip_integrity.py": "Tests de vérification de l'intégrité et de la persistance de l'infobulle bassin versant",
    "tests/test_bassins_collectes.py": "Tests d'intégrité des bassins collectés et exutoires",
    "tests/test_bassins_hydraulique.py": "Tests de cohérence hydraulique et débits de pointe par bassin versant",
    "tests/test_bilan_hydraulique_options.py": "Tests des options du bilan hydraulique et formatage monétaire DZD",
    "tests/test_demo_network.py": "Tests de chargement et d'intégrité du réseau de démonstration",
    "tests/test_export_nom_reseau.py": "Tests d'exportation des données réseau et conventions de nommage",
    "tests/test_formatage_couts_dzd.py": "Tests unitaires de formatage monétaire comptable DZD avec séparateur décimal",
    "tests/test_gdo_and_persistance_simulation.py": "Tests de la terminologie GDO et de la persistance des simulations",
    "tests/test_golden_master.py": "Tests de non-régression par rapport au Golden Master de référence",
    "tests/test_graphe_orientation.py": "Tests de l'algorithme d'orientation des conduites et parcours de graphe",
    "tests/test_hydrologie.py": "Tests unitaires des calculs hydrologiques et ruissellement",
    "tests/test_inondation_volume.py": "Tests d'évaluation des volumes de débordement et inondations urbaines",
    "tests/test_inp_parser.py": "Tests unitaires du parseur de fichiers SWMM .INP",
    "tests/test_invariance_scenarios_ab.py": "Tests d'invariance des résultats hydrauliques entre scénarios A et B",
    "tests/test_js_syntax_integrity.py": "Validation automatisée de l'intégrité syntaxique du code JavaScript frontend",
    "tests/test_licensing.py": "Tests unitaires du système de licences logicielles et quotas",
    "tests/test_manual_basins.py": "Tests de création et d'édition manuelle de bassins versants",
    "tests/test_ouvrages_orphelins.py": "Tests de détection et filtrage des tronçons déconnectés",
    "tests/test_phase1_integration.py": "Tests d'intégration globale du livrable Phase 1",
    "tests/test_simulation_cache_idempotence.py": "Tests d'idempotence et mise en cache des résultats de simulation SWMM",
    "tests/test_storage.py": "Tests unitaires du gestionnaire de stockage des artefacts",
    "tests/test_swmm_error_141_outfall.py": "Tests de prévention et résolution de l'erreur SWMM 141 (Outfall invalide)",
    "tests/test_validateurs_topologie.py": "Tests des règles de validation topologique du réseau",
    "tests/test_web_routes.py": "Tests de bout en bout des routes Web et rendu HTML",

    # Templates HTML
    "templates/index.html": "Interface principale cartographique et SIG de modélisation hydraulique DrainPilot",
    "templates/carte.html": "Composant cartographique Leaflet autonome pour visualisation de réseau",
    "templates/map.html": "Vue cartographique plein écran pour l'inspection interactive",
    "templates/qualite.html": "Tableau de bord interactif d'audit et de correction de qualité topologique",
    "templates/landing.html": "Page d'accueil et présentation des fonctionnalités DrainPilot 5.2",
    "templates/tunnel.html": "Interface de paramétrage de l'accès distant sécurisé",
    "templates/auth/login.html": "Page d'authentification utilisateur et connexion multi-tenant",
    "templates/auth/register.html": "Page d'inscription utilisateur et création d'organisation",

    # Static JS
    "static/carte.js": "Contrôleur cartographique Leaflet principal et interaction utilisateur",
    "static/js/carte_anomalies.js": "Gestion de l'affichage et du traitement cartographique des anomalies",
    "static/js/carte_core.js": "Noyau d'initialisation cartographique, projections et tuiles",
    "static/js/carte_ui.js": "Gestionnaire des éléments d'interface utilisateur, panneaux latéraux et menus",
    "static/js/map/map_cluster_detection.js": "Détection et affichage interactif des clusters topologiques",
    "static/js/map/map_core.js": "Couche de base et configuration du canevas cartographique",
    "static/js/map/map_edit_attributes.js": "Édition interactive des attributs des regards et conduites",
    "static/js/map/map_init.js": "Initialisation du contexte cartographique et des écouteurs d'événements",
    "static/js/map/map_layers.js": "Gestion des calques vectoriels, GeoJSON et styles graphiques",
    "static/js/map/map_manual_basins.js": "Outils de dessin et sectorisation manuelle de bassins versants",
    "static/js/map/map_notifications.js": "Système de notifications visuelles et alertes d'ingénierie",
    "static/js/map/map_quality.js": "Visualisation cartographique des anomalies et contrôles qualité",
    "static/js/map/map_state.js": "Gestion centralisée de l'état applicatif et des sélections du réseau"
}


def process_python_file(filepath: str, objet: str):
    """Met à jour l'en-tête d'un fichier Python de façon sécurisée."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    new_header = CANONICAL_PY_HEADER.format(objet=objet)

    # Conserver shebang ou coding s'il existe
    prefix = ""
    rest = content
    if rest.startswith("#!"):
        lines = rest.split("\n", 1)
        prefix += lines[0] + "\n"
        rest = lines[1] if len(lines) > 1 else ""
    if rest.startswith("# -*- coding") or rest.startswith("# coding:"):
        lines = rest.split("\n", 1)
        prefix += lines[0] + "\n"
        rest = lines[1] if len(lines) > 1 else ""

    rest = rest.lstrip()

    # Si le fichier commence déjà par un docstring existant, le remplacer
    if rest.startswith('"""'):
        end_idx = rest.find('"""', 3)
        if end_idx != -1:
            rest = rest[end_idx + 3:].lstrip()
    elif rest.startswith("'''"):
        end_idx = rest.find("'''", 3)
        if end_idx != -1:
            rest = rest[end_idx + 3:].lstrip()

    updated = prefix + new_header + "\n\n" + rest

    # Validation syntaxique stricte avec ast.parse
    try:
        ast.parse(updated, filename=filepath)
    except SyntaxError as e:
        print(f"ERREUR SYNTAXE dans {filepath}: {e}")
        return False

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(updated)
    return True


def process_html_file(filepath: str, objet: str):
    """Met à jour l'en-tête d'un fichier HTML Jinja2."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    new_header = CANONICAL_HTML_HEADER.format(objet=objet)
    rest = content.lstrip()

    # Si le fichier commence déjà par un commentaire HTML, le remplacer
    if rest.startswith("<!--"):
        end_idx = rest.find("-->", 4)
        if end_idx != -1:
            # Vérifier si c'était un en-tête de projet
            first_comment = rest[:end_idx + 3]
            if "Projet :" in first_comment or "Auteur" in first_comment or "DrainPilot" in first_comment or "====" in first_comment:
                rest = rest[end_idx + 3:].lstrip()

    updated = new_header + "\n" + rest
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(updated)
    return True


def process_js_file(filepath: str, objet: str):
    """Met à jour l'en-tête d'un fichier JS."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    new_header = CANONICAL_JS_HEADER.format(objet=objet)
    rest = content.lstrip()

    # Si le fichier commence déjà par un commentaire bloc /* ... */
    if rest.startswith("/*"):
        end_idx = rest.find("*/", 2)
        if end_idx != -1:
            first_comment = rest[:end_idx + 2]
            if "Projet :" in first_comment or "Auteur" in first_comment or "DrainPilot" in first_comment or "====" in first_comment:
                rest = rest[end_idx + 2:].lstrip()

    updated = new_header + "\n\n" + rest
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(updated)
    return True


def main():
    print("Application systématique des en-têtes standardisés...")
    success_count = 0
    total_count = len(MODULE_OBJECTS)

    for rel_path, objet in sorted(MODULE_OBJECTS.items()):
        norm_path = os.path.normpath(rel_path)
        if not os.path.exists(norm_path):
            print(f"Fichier introuvable : {norm_path}")
            continue

        ext = os.path.splitext(norm_path)[1].lower()
        if ext == ".py":
            ok = process_python_file(norm_path, objet)
        elif ext == ".html":
            ok = process_html_file(norm_path, objet)
        elif ext == ".js":
            ok = process_js_file(norm_path, objet)
        else:
            ok = False

        if ok:
            success_count += 1
            print(f"OK: {norm_path}")
        else:
            print(f"ECHEC: {norm_path}")

    print(f"\nTerminé : {success_count}/{total_count} fichiers mis à jour avec succès.")


if __name__ == "__main__":
    main()
