# Inventaire du projet — état au 22 novembre 2026

## Objectif

Ce document classe les éléments présents dans le dépôt afin de distinguer ce qui est
actif, historique, expérimental ou généré. Il sert de base avant tout nettoyage ou
archivage.

## Statuts utilisés

- **Actif** : composant à conserver et maintenir.
- **Historique** : composant utile mais hérité d'une version antérieure.
- **Expérimental** : prototype ou piste à confirmer.
- **Local/généré** : fichier produit localement, à ne pas pousser vers GitHub.
- **À vérifier** : élément présent mais rôle exact à confirmer avant décision.

## Composants suivis par Git

| Élément | Statut | Rôle |
|---|---|---|
| `api/` | Actif | API FastAPI unique : 18 routeurs (`auth`, `network`, `simulations`, `clusters`, `qualite`, `corrections`, `sync`, `terrain`, `mnt`, `audit`, `jobs`, `artifacts`, `licensing`, `admin`, `organization`, `apports`, `garde_fou`, `aux_layers`, `extractions`). |
| `api/websocket.py` | Actif | Support WebSocket (progression des jobs). |
| `config/` | Actif | Configuration centralisée (`settings.py` : `API_HOST`/`API_PORT`, DB, GPKG_PATH). |
| `docs/` | Actif | Documentation structurante de la plateforme. |
| `src/domain/` | Actif | Logique métier hydraulique SWMM (générateur `.inp`, hydro-, timeseries, référentiel pluvio). |
| `src/infrastructure/` | Actif | Chargement, reprojection et préparation des données SIG. |
| `src/controllers/`, `src/views/` | Historique | Contrôleurs Flask et visualiseur historique (serveur `server.py` retiré). |
| `src/validateurs/` | Actif | Validateurs topologiques Phase 1 (utilisés par `src/qualite_reseau.py`). |
| `static/` | Actif | Frontend cockpit : `static/js/app/` (30 modules ES), Leaflet, Chart.js. |
| `templates/` | Actif | Templates Jinja : `index.html` (cockpit), `partials/`, pages annexes (`carte.html`, `map.html`, `qualite.html`, `tunnel.html`, `auth/`). |
| `tests/` | Actif | Suite pytest (600+ tests) + Golden Master hydraulique. |
| `workers/` | Actif | Workers Celery (`swmm_tasks`, `mnt_tasks`) pour calculs asynchrones. |
| `mobile/` | Actif | Application mobile officielle Flutter (offline-first, `--dart-define=API_BASE_URL`). |
| `run_api.py` | Actif | Lanceur FastAPI avec auto-reload (`API_RELOAD`). |
| `run_server.py` | Actif | Lanceur FastAPI sans auto-reload. |
| `launch_api.bat` | Actif | Lanceur Windows API. |
| `lancer_plateforme.bat` | Actif | Lanceur Windows groupé (API FastAPI). |
| `migrate_gpkg_to_postgres.py` | Historique | Migration GPKG → PostgreSQL, déjà jouée ou à archiver. |
| `README.md`, `README_PLATFORM.md` | Actif | Entrées principales du dépôt. |
| `TODO.md` | Actif | Suivi opérationnel de la roadmap SaaS. |
| `Regles.txt` | Historique | Règles initiales du projet, à consolider. |
| `Rapport_Methodologique_Clusters_Bassins.md` | Actif | Rapport métier/méthodologique. |
| `methodologie_partitionnement_hydraulique.md` | Actif | Note méthodologique sur le partitionnement. |
| `SHP.md`, `AGENTS.md`, `GEMINI.md` | Actif | Règles et consignes agents/outils. |
| `alembic/` | Actif | Migrations de schéma SQLAlchemy. |
| `e2e/` | Actif | Tests end-to-end Playwright. |
| `prototypes/` | Expérimental | POC UI à qualifier. |

## Éléments locaux non suivis / à classer

| Élément | Statut proposé | Décision recommandée |
|---|---|---|
| `swmm_platform.db`, `database.db`, `test_swmm_platform.db` | Local/généré | Bases SQLite locales — ne jamais pousser. |
| `output/`, `exports/`, `uploads/`, `logs/`, `scratch/` | Local/généré | Données et artefacts produits localement. |
| `*.inp`, `*.rpt` à la racine | Local/généré | Sorties SWMM de tests manuels — nettoyage conseillé. |
| `p*.png`, `wx_*.inp/rpt`, `prof.json`, `_t_*.inp/rpt` | Local/généré | Captures et artefacts de debug — nettoyage conseillé. |
| `nul` | Local/généré | Fichier parasite Windows — supprimer. |
| `pytest-cache-files-*` | Local/généré | Caches pytest — ignorer. |
| `2-ASS/` | À vérifier | Jeu de données GIS source (couches satellite) — à documenter dans DONNEES.md si actif. |

## Inventaire des pistes abandonnées (à supprimer des docs)

Les éléments suivants **n'existent plus** dans le dépôt et ne doivent plus
être mentionnés comme pistes actives :

- `server.py` (serveur Flask historique) — **supprimé** ;
- `swmm_mobile_flutter/` (prototype Flutter alternatif) — **supprimé** ;
- `mobile_app.html` (prototype web mobile) — **supprimé** ;
- `test_api.py`, `test_ws.py`, `test_server.py`, `test_sync.py` à la racine —
  doublons de tests manuels (la suite officielle est sous `tests/`).

## Décisions structurantes actuelles

- **Backend unique** : FastAPI (`api.main:app`), port défini par `API_PORT`.
- **Base de données** : PostgreSQL cible, **fallback SQLite automatique**
  (`swmm_platform.db`) si PostgreSQL est indisponible ; tests sur
  `test_swmm_platform.db`.
- **Stockage d'artefacts** : `ArtifactStore` — `LocalStore` en dev,
  `S3Store` (S3/MinIO) en production via variables `S3_*`.
- **Calculs lourds** : Celery/Redis (`workers/`) — simulations SWMM et
  extraction MNT ; repli synchrone pour les petits calculs.
- **Données SIG** : GeoPackage par projet avec **versionnement immuable**
  (snapshots par sha256) — toute lecture historique se fait sur le snapshot
  producteur, jamais sur le réseau courant.
- **Multi-tenant** : isolation stricte par `org_id`, stealth 404.
- **Documentation structurante** : `docs/` — voir `09_ENDPOINTS_DOCUMENTATION.md`
  pour le référentiel API à jour.

## Prochaines actions

1. Nettoyer les artefacts locaux à la racine (`*.inp`, `*.rpt`, `p*.png`,
   `nul`, `pytest-cache-files-*`).
4. Vérifier le rôle de `2-ASS/` et `prototypes/`.
