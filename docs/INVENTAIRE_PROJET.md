# Inventaire du projet - Phase 1

## Objectif

Ce document classe les éléments présents dans le dépôt afin de distinguer ce qui est
actif, historique, expérimental ou généré. Il sert de base avant tout nettoyage ou
archivage.

## Statuts utilisés

- **Actif** : composant à conserver et maintenir.
- **Historique** : composant utile mais hérité de l'ancienne version.
- **Expérimental** : prototype ou piste à confirmer.
- **Local/généré** : fichier produit localement, à ne pas pousser vers GitHub.
- **À vérifier** : élément présent mais rôle exact à confirmer avant décision.

## Composants suivis par Git

| Élément | Statut | Rôle |
|---|---|---|
| `api/` | Actif | API FastAPI moderne : réseau, clusters, synchronisation, simulations. |
| `config/` | Actif | Configuration centralisée du projet. |
| `docs/` | Actif | Documentation structurante de la phase 1. |
| `src/domain/` | Actif | Logique métier hydraulique et réseau. |
| `src/infrastructure/` | Actif | Chargement, reprojection et préparation des données. |
| `src/controllers/` | Historique | Contrôleurs Flask et génération SWMM initiale. |
| `src/views/` | Historique | Interface Leaflet historique. |
| `tests/` | Actif | Tests unitaires et tests de génération SWMM. |
| `workers/` | Expérimental | Préparation des traitements asynchrones SWMM/Celery. |
| `server.py` | Historique | Serveur Flask historique sur le port `5000`. |
| `run_api.py` | Actif | Lanceur de développement FastAPI. |
| `run_server.py` | Actif | Lanceur FastAPI sans auto-reload. |
| `launch_api.bat` | Actif | Lanceur Windows pour l'API FastAPI. |
| `launch_server.bat` | Historique | Lanceur Windows pour le serveur Flask historique. |
| `migrate_gpkg_to_postgres.py` | À vérifier | Script de migration vers PostgreSQL/PostGIS. |
| `README.md` | Actif | Entrée principale du dépôt. |
| `README_PLATFORM.md` | Actif | Vision plateforme collaborative. |
| `TODO.md` | Historique | Suivi ancien des tâches. |
| `Regles.txt` | Historique | Règles initiales du projet, à consolider dans `docs/`. |
| `Rapport_Methodologique_Clusters_Bassins.md` | Actif | Rapport métier/méthodologique. |
| `methodologie_partitionnement_hydraulique.md` | Actif | Note méthodologique sur le partitionnement. |

## Éléments locaux non suivis à classer

Ces éléments existent dans le workspace mais ne sont pas encore suivis par Git.
Ils ne doivent pas être poussés sans revue.

| Élément | Statut proposé | Décision recommandée |
|---|---|---|
| `mobile/` | Actif | Application mobile officielle React Native/Expo de la phase 1. |
| `swmm_mobile_flutter/` | Expérimental | Prototype alternatif, à archiver ou confirmer. |
| `mobile_app.html` | Expérimental | Prototype mobile web autonome, à archiver si React Native est retenu. |
| `static/` | À vérifier | Ressources web ajoutées localement, à relier à une interface officielle. |
| `templates/map.html` | À vérifier | Template utilisé par les changements locaux de `api/main.py`. |
| `api/websocket.py` | À vérifier | Support WebSocket local, lié aux changements de synchronisation. |
| `LANCER_WEB.md`, `LANCER_MOBILE.md` | À vérifier | Docs ponctuelles à fusionner dans `docs/LANCEMENT.md`. |
| `MOBILE_README.md`, `MOBILE_ALTERNATIVE_README.md` | À vérifier | Docs mobiles à consolider dans une future `docs/MOBILE.md`. |
| `INSTRUCTIONS_FINALES.txt` | À vérifier | Instructions locales à intégrer ou archiver. |
| `diagnostic_mobile.ps1` | À vérifier | Diagnostic local mobile. |
| `install_*.bat`, `install_*.ps1` | À vérifier | Scripts d'installation ponctuels. |
| `final_fix.bat`, `fix_and_launch.bat`, `launch_final.bat`, `launch_mobile_app.bat` | À vérifier | Scripts mobiles temporaires. |
| `test_*.bat`, `test_server.py`, `test_sync.py`, `test_visu_contours.py` | À vérifier | Tests manuels ou expérimentaux à déplacer sous `tests/` si utiles. |
| `swmm_platform.db` | Local/généré | Base SQLite locale, ne pas pousser. |
| `output/` | Local/généré | Exports et résultats locaux, ne pas pousser. |
| fichiers `AST14DEM_*` | Local/généré | Raster/contours volumineux, ne pas pousser. |
| `package-lock.json` racine | À vérifier | À conserver seulement si un package Node racine existe. |
| `nul` | Local/généré | Fichier parasite Windows, à supprimer après validation. |

## Décisions de phase 1

- L'API FastAPI est le backend moderne de référence.
- Le port API de référence est `5001`.
- Le serveur Flask historique reste disponible sur `5000`.
- La documentation structurante doit vivre dans `docs/`.
- Les fichiers de données lourdes et bases locales restent hors Git.
- La piste mobile officielle de phase 1 est `mobile/` en React Native/Expo.

## Prochaines actions

1. Consolider les documents mobiles ponctuels dans `docs/MOBILE.md`.
2. Auditer `swmm_mobile_flutter/` et `mobile_app.html` avant archivage ou suppression.
3. Auditer les scripts `.bat` et `.ps1` non suivis avant ajout ou archivage.
4. Déplacer les tests manuels utiles dans `tests/` ou les documenter comme outils de diagnostic.
5. Supprimer ou ignorer explicitement les fichiers locaux parasites après validation utilisateur.
