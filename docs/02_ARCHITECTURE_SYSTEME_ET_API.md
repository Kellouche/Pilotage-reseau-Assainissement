# 02 — Architecture Système & Référentiel API

> **DrainPilot 5.2** — API unifiée FastAPI, multi-tenant, stockage d'artefacts `ArtifactStore`, workers Celery/Redis, passerelle mobile Flutter.
>
> **Audience** : architectes, développeurs backend/frontend, DevOps, auditeurs sécurité, intégrateurs.
> **Contenu** : architecture d'ensemble, synthèse des ADR, modèle de données et géospatial, référentiel exhaustif des endpoints REST/WebSocket, synchronisation mobile.
> **Références** : produit dans [01_PRODUIT_CADRAGE_ET_TARIFICATION.md](01_PRODUIT_CADRAGE_ET_TARIFICATION.md), hydraulique dans [03_INGENIERIE_HYDRAULIQUE_ET_SWMM.md](03_INGENIERIE_HYDRAULIQUE_ET_SWMM.md), exploitation dans [04_EXPLOITATION_OPERATIONS_ET_ROADMAP.md](04_EXPLOITATION_OPERATIONS_ET_ROADMAP.md).

---

## 1. Architecture Technique d'Ensemble

```
                    ┌──────────────────────────────────────────────┐
                    │     Navigateur Web & Application Mobile      │
                    │  Desktop (Leaflet / JS) + Mobile (Flutter)   │
                    └──────────────────────┬───────────────────────┘
                                           │ HTTPS
                                  ┌────────▼────────┐
                                  │  Reverse Proxy  │  Caddy / Nginx (SSL & Rate Limit)
                                  └────────┬────────┘
                                           │
                    ┌──────────────────────▼──────────────────────┐
                    │      DrainPilot Web API (FastAPI)           │  Uvicorn / Gunicorn
                    │  - Routeurs modulaires (/api/v1/*)          │
                    │  - Auth Argon2id & JWT/Cookies               │
                    │  - Isolation multi-tenant (org_id)          │
                    │  - Feature Gating & Quotas Métier           │
                    │  - Console Opérateur SuperAdmin             │
                    └───┬──────────────┬──────────────┬───────────┘
                        │              │              │
             ┌──────────▼───┐   ┌──────▼──────┐   ┌───▼──────────┐
             │  PostgreSQL  │   │    Redis    │   │   S3/MinIO   │
             │   + PostGIS  │   │  - Cache    │   │  - Rasters   │
             │  - Tenants   │   │  - Broker   │   │    MNT .tif  │
             │  - Réseaux   │   │  - Statuts  │   │  - Fichiers  │
             │  - Licences  │   └──────┬──────┘   │    .INP      │
             └──────────────┘          │          │  - Résultats │
                                ┌──────▼──────┐   │  - PDF / CSV │
                                │ Worker Async│   └──────────────┘
                                │   Celery    │  EPA SWMM 5.2 Engine
                                └─────────────┘
```

### Composants

- **Backend unique FastAPI** (`api.main:app`) : routeurs modulaires sous `/api/v1`, authentification Argon2id/JWT, RBAC, feature gating.
- **Base de données** : PostgreSQL 16 + PostGIS en production ; **fallback automatique SQLite** (`swmm_platform.db`) en développement/tests si PostgreSQL est indisponible.
- **Calculs lourds** : Celery + Redis (simulations SWMM, analyses MNT). L'API ne fait aucun calcul lourd — elle répond `202 Accepted` + `job_id`.
- **Stockage d'artefacts** : `ArtifactStore` (`api/core/storage.py`) — `LocalStore` en dev, `S3Store` (S3/MinIO) en prod via variables `S3_*`.
- **Frontend** : cockpit Leaflet HD (`templates/index.html` + `static/js/app/`), cockpit qualité unifié (`/qualite`, intégré à `/map?tab=qualite` ; l'ancienne `/carte` redirige vers `/qualite`), pages dédiées `/tunnel`, centre d'aide `/aide`.
- **Mobile** : application Flutter officielle sous `mobile/` (voir §5).
- **Conteneurisation** : architecture cible multi-conteneurs Docker (voir ADR 0005 et Doc 4 §1 — le `docker-compose` de production est un livrable de la phase d'industrialisation).

### Pages web servies

| Route | Rôle | Auth |
|---|---|---|
| `/` | Cockpit cartographique + simulation SWMM | Connecté |
| `/cockpit`, `/map` | Alias cockpit | Connecté |
| `/carte` | *(décommissionnée)* → redirection 301 vers `/qualite` | Connecté |
| `/qualite` | Cockpit qualité réseau unifié (audit, anomalies, orphelins, corrections) | Connecté |
| `/tunnel` | Tunnel de workflow 4 étapes | Connecté |
| `/aide` | Centre d'aide : documentation Markdown rendue | Connecté |
| `/aide/doc/{path}` | Fragment HTML d'un document normatif | Connecté |
| `/pricing`, `/tarifs` | Offres et licences | Public |
| `/docs` | Swagger UI de l'API | Public |
| `/login`, `/register` | Authentification | Public |

---

## 2. Synthèse des Architecture Decision Records

Les ADRs font foi — ils sont conservés intacts dans [`adr/`](adr/). Cette section en donne la synthèse ; le détail (contexte, alternatives écartées, conséquences) est dans chaque fichier.

### ADR 0001 — Authentification FastAPI, Argon2id & double session

**Décision** : hachage **Argon2id** (`pwd_context`), double session selon le client — cookie HTTP-Only/Secure/SameSite=Lax pour le web (anti-XSS), JWT Bearer (access 60 min + refresh 30 jours révocable) pour mobile/intégrations. RBAC à 5 rôles + superadmin.
**Conséquences** : toutes les routes protégées par `Depends(get_current_active_user)` ; route non protégée = bug bloquant.
→ [adr/0001-authentification-fastapi-argon2-jwt.md](adr/0001-authentification-fastapi-argon2-jwt.md)

### ADR 0002 — Multi-tenancy mutualisé PostgreSQL/PostGIS par `org_id`

**Décision** : isolation **logique stricte** — colonne `org_id` obligatoire sur chaque table métier, index composites commençant par `org_id`, filtre `TenantContext` sur chaque requête. Toute ressource d'une autre organisation répond **HTTP 404** (règle *stealth 404* : invisibilité totale, jamais de 403).
**Conséquences** : sauvegardes simplifiées ; un filtre `org_id` oublié est un bug bloquant couvert par les tests de sécurité ; RLS PostgreSQL possible en défense en profondeur.
→ [adr/0002-tenancy-postgresql-postgis-org-id.md](adr/0002-tenancy-postgresql-postgis-org-id.md)

### ADR 0003 — File de traitements asynchrones Celery + Redis

**Décision** : aucun calcul lourd dans le processus web — l'API enregistre le job (`PENDING`), délègue à Celery via Redis, répond `202` + `job_id`. Progression consultable par polling (`GET /api/v1/jobs/{job_id}`) ou WebSocket (`/api/v1/jobs/ws/{job_id}`).
**Conséquences** : Redis dépendance obligatoire ; gestion explicite des erreurs/annulations de jobs ; montée en charge horizontale des workers.
→ [adr/0003-file-jobs-celery-redis.md](adr/0003-file-jobs-celery-redis.md)

### ADR 0004 — Stockage des artefacts S3 / MinIO

**Décision** : stockage objet compatible S3 (MinIO en dev/on-premise, S3 souverain en prod). Arborescence cloisonnée `s3://…/{org_id}/networks/{network_id}/…` avec typologie `raw/`, `swmm/`, `reports/`, `terrain/`. Téléchargements par **URLs pré-signées** de 15 min.
**Conséquences** : API et workers **stateless** ; configuration par `S3_*`.
→ [adr/0004-stockage-artefacts-s3-minio.md](adr/0004-stockage-artefacts-s3-minio.md)

### ADR 0005 — Hébergement portable multi-conteneurs Docker

**Décision** : `docker-compose` orchestre 6 briques (web, worker, db PostGIS, redis, s3 MinIO, mailpit). Configuration 100 % par variables d'environnement (12-Factor). Images multi-étapes pour les dépendances C (GDAL/GEOS/PROJ, SWMM Toolkit).
**Conséquences** : démarrage en une commande ; portabilité cloud/on-premise ; zéro vendor lock-in. *Statut actuel : architecture cible — le compose de production est un livrable de la phase d'industrialisation (Doc 4 §5).*
→ [adr/0005-hebergement-portable-docker.md](adr/0005-hebergement-portable-docker.md)

### ADR 0006 — Facturation B2B/B2G & licences

**Décision** : cycle documentaire réglementaire (devis proforma → bon de commande → validation SuperAdmin → clé `SP-LIC-YYYY-…`) au lieu du paiement CB ; licences vérifiables hors-ligne ; console `/admin/licenses`.
**Conséquences** : commercialisable auprès des administrations sans friction ; feature gating piloté par les licences en base.
→ [adr/0006-facturation-b2b-licences.md](adr/0006-facturation-b2b-licences.md) — *détaillé aussi dans Doc 1 §5.4*

### ADR 0007 — Synchronisation terrain offline-first

**Décision** : cache local SQLite/Drift sur le smartphone, mutations horodatées en file `pending_mutations`, **delta sync** (`/api/v1/sync/push` + `/api/v1/sync/delta`), conflits en *Last-Write-Wins* avec audit trail immuable ; incohérences majeures marquées `A_VALIDER_BUREAU`.
→ [adr/0007-synchronisation-terrain-mobile-offline.md](adr/0007-synchronisation-terrain-mobile-offline.md) — *détaillé aussi en §5*

### ADR 0008 — Périmètre du MVP SaaS

**Décision** : MVP strict sur la chaîne de valeur BET/régie (multi-tenant, qualité SIG, MNT, SWMM asynchrone, mobile essentiel, exports PDF) ; qualité de l'eau physico-chimique, IoT/SCADA et RTC avancé différés.
→ [adr/0008-perimetre-mvp-saas.md](adr/0008-perimetre-mvp-saas.md) — *détaillé aussi dans Doc 1 §6*

---

## 3. Modèle de Données & Gestion Géospatiale

### 3.1 Projections de référence

| CRS | Usage |
|---|---|
| `EPSG:32631` (UTM 31N) | **Projection de calcul** — métrique, distances, pentes, buffers |
| `EPSG:4326` (WGS84) | **Projection d'affichage** — tous les endpoints cartographiques et le mobile renvoient du WGS84 (Leaflet, React Native Maps) |

### 3.2 Source métier : GeoPackage projet

La donnée patrimoniale vit dans un **GeoPackage par projet** (snapshot versionné). Couches métier attendues : `regards`, `canalisations`, `rejets`, `stations de relevage`, `STEP`, `ouvrages spéciaux`. Le chemin est résolu par `resoudre_gpkg_effectif_pour_projet` (`api/services/simulation_service.py`) — jamais de fichier global partagé entre projets.

**Découverte automatique à l'ouverture** : les conventions de nommage des identifiants (alias par noyau, zéro-padding) et la tolérance de snap sont **inférées par fichier** et persistées dans `<fichier>.conventions.json` — voir Doc 3 §4.

**Versionnement immuable** : chaque simulation est liée au snapshot exact de son GPKG (empreinte SHA-256 + chemin, clé de cache du graphe `empreinte|chemin`). Les endpoints spatiaux acceptent `snapshot=<version_id|sha256>` pour relire le réseau *exact* ayant produit une simulation archivée — jamais le réseau courant. Détail : Doc 3 §5 et `api/services/simulation_service.py`.

### 3.3 Isolation & sécurité des données

- Filtre `org_id` sur chaque table métier (ADR 0002) ; stealth 404 inter-organisations.
- Artefacts cloisonnés par `org_id`/`project_id` dans le store.
- **Règles de non-versionnement Git** : `*.db`, `*.sqlite*`, `*.gpkg`, `*.tif`, `*.shp/.shx/.dbf/.prj/.cpg`, `output/` — le dépôt ne contient que code, doc et éventuel jeu de démonstration anonymisé.

### 3.4 Règles de qualité des données d'entrée

Avant exploitation (simulation ou analyse) : identifiants présents, géométries valides, cohérence amont/aval, diamètres/longueurs renseignés, tronçons orphelins inventoriés, coordonnées dans la zone. L'audit qualité automatique couvre ces contrôles (endpoint §4 ci-dessous).

---

## 4. Référentiel des Endpoints API REST & WebSocket

**Conventions** : préfixe `/api/v1` ; auth cookie session (web) ou `Authorization: Bearer <JWT>` ; JSON UTF-8, GeoJSON pour le spatial, binaire pour rasters/exports ; `snapshot` = version_id ou sha256 du GPKG.

### 4.1 Authentification & sessions — `/api/v1/auth`

| Méthode | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/auth/register` | Création organisation + compte admin (201) |
| `POST` | `/api/v1/auth/verify-email` | Vérification email / activation |
| `POST` | `/api/v1/auth/resend-code` | Renvoi du code de vérification |
| `GET` | `/api/v1/auth/check-email` | Disponibilité d'un email |
| `POST` | `/api/v1/auth/login` | Connexion (cookie + JWT) |
| `POST` | `/api/v1/auth/refresh` | Renouvellement access token |
| `POST` | `/api/v1/auth/logout` | Déconnexion, révocation |
| `GET`/`PATCH` | `/api/v1/auth/me`, `/api/v1/auth/profile` | Profil utilisateur |
| `POST` | `/api/v1/auth/change-password` | Changement de mot de passe |
| `GET`/`POST`/`DELETE` | `/api/v1/auth/api-keys[/{key_id}]` | Clés API personnelles |

### 4.2 Réseau — `/api/v1/network`

CRUD regards/conduites/rejets sur le GPKG actif ; données servies en WGS84.

| Méthode | Endpoint | Description |
|---|---|---|
| `GET`/`POST`/`PATCH`/`DELETE` | `/api/v1/network/regards[/{id}]` | CRUD regards |
| `GET`/`POST`/`PATCH`/`DELETE` | `/api/v1/network/conduites[/{id}]` | CRUD conduites |
| `GET`/`POST` | `/api/v1/network/rejets` | Rejets/exutoires |
| `GET` | `/api/v1/network/datasets` | Projets de l'organisation (+ `active_project`) |
| `POST` | `/api/v1/network/load-dataset/{id}` | Active un dataset comme projet courant |
| `POST` | `/api/v1/network/load-demo` · `/load-master` · `/reset` | Contextes réseau |
| `POST` | `/api/v1/network/upload` | Import GeoPackage / `.inp` — param `crs` (code EPSG) **exigé** si le fichier ne déclare pas de projection ou si la détection `.inp` est incertaine ; la réponse expose `crs` + `crs_source` (`fichier`/`utilisateur`/heuristique) |
| `GET` | `/api/v1/network/subcatchments` | Sous-bassins Voronoï en GeoJSON |
| `GET` | `/api/v1/network/orphelins/geojson` | Regards orphelins persistés (GeoJSON) |
| **`GET`** | **`/api/v1/network/orphelins`** | **Inventaire orphelins : nœuds isolés (degré 0) + tronçons hors graphe/sans exutoire, coords WGS84 + stats — alimente la file qualité de `/qualite`** |
| `GET` | `/api/v1/network/export/inp` | Export `.inp` du réseau courant |

### 4.3 Qualité — `/api/v1/qualite`

| Méthode | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/qualite/analyse` | Rapport complet d'audit qualité |
| `GET` | `/api/v1/qualite/diagnostic` | Diagnostic synthétique (tunnel) |
| `GET` | `/api/v1/qualite/anomalies/{type}` | Détail des anomalies d'un type |
| `GET` | `/api/v1/qualite/scores` · `/scores-bassins` · `/statistiques` | Scores et stats |
| `POST` | `/api/v1/qualite/valider-incremental` · `/export-csv` | Validation / export CSV |
| `GET`/`DELETE` | `/api/v1/qualite/cache[/status]` | Cache d'analyse |

### 4.4 Corrections — `/api/v1/corrections`

`POST /manuel/{fid}`, `GET /hybride/suggestable_fids`, `GET /hybride/suggest`, `GET /profile/{fid}`, `POST /automatique`.

### 4.5 Clusters & graphe — `/api/v1/clusters`

`GET /`, `GET /status`, `POST /graph/rebuild`, `GET|POST /recalculate-all`, CRUD `/manual-basin[/{id}]`, `GET /{id}`, `POST /{id}/recalculate`, `GET /{id}/geojson`, `GET /{id}/ouvrages-proches`.

### 4.6 Simulations SWMM — `/api/v1/simulations`

| Méthode | Endpoint | Description |
|---|---|---|
| `GET`/`POST` | `/api/v1/simulations` | Historique / lancement async (202 `job_id`) |
| `GET` | `/simulations/scenarios` · `/typologies-sol` · `/pluviometrie/referentiel` · `/pluviometrie/stations` · `/pluviometrie/bms-preview` | Référentiels pluie/BMS |
| `POST` | `/api/v1/simulations/run` | Exécution synchrone (synthèse + couches) |
| `GET` | `/simulations/latest` · `/{id}` · `/{id}/resultat` | Résultats (accepte `snapshot`, `simulation_id`) |
| `DELETE` | `/api/v1/simulations/{id}` | Suppression |
| `GET` | `/simulations/job/{job_id}` · `/status/{job_id}` · `/cluster/{id}` · `/bassin/{id}[/historique]` | Jobs, clusters, bassins |
| `GET` | `/simulations/timeseries` | Séries Q(t)/y(t) |
| `GET` | `/simulations/recherche-element` | Recherche regard/conduite par n°/nom |
| `POST` | `/simulations/validate-buffer` | Validation buffer pochoir |
| `GET`/`POST` | `/simulations/cotes-suspectes[/valider]` | Registre cotes suspectes (HITL) |
| `GET` | `/simulations/reconciliation` | **Réconciliation 1:1 SIG ↔ INP : inventaire, ventilation du parc, hypothèses** |
| `GET` | `/simulations/profil-en-long` | Profil en long hydraulique HGL |
| `GET` | `/simulations/download/inp` · `/download/rpt` | `.inp` / `.rpt` officiels |
| `GET` | `/simulations/rapport-diagnostic-pdf` · `/bms/ordre-mission-pdf` · `/agents/interpretation` | PDF & interprétation multi-agents |

### 4.7 Apports DWF — `/api/v1/apports`

CRUD `/` + `/{id}`, `/revalider`, `/profils`, `/noeuds`, `/a-reconcilier`, `/history`, `/{id}/history`, `POST /purger-orphelins` (`project_id` en query).

### 4.8 Couches satellite & altimétrie — `/api/v1/projets/{pid}/aux-layers`

CRUD + `/{id}/geojson`, `/{id}/elevation` (IDW), `/{id}/regards-terrain[/recalculer]`, `/{id}/apercu-inp`, `/{id}/suspects-ecoulement` (revue P1), `/{id}/raccordements-orphelins` (scoring P2). L'upload (`POST /aux-layers`) accepte le param `crs` (code EPSG) **exigé** si le fichier ne déclare pas de projection — aucun repli silencieux.

### 4.9 Extraction pochoir — `/api/v1/projets/{pid}/extraction-pochoir`

`POST` → zip Shapefiles + GPKG fusionné (règle stricte d'intersection).

### 4.10 Garde-fou — `/api/v1/projets/{pid}/garde-fou`

`GET`/`PUT` config, `POST /reaudit`.

### 4.11 MNT — `/api/v1/mnt`

`POST /analyser-bassins` (DEM TIFF), `GET|DELETE /cache[/status]`, `GET /statut`. Extraction lourde via worker Celery.

### 4.12 Jobs & WebSocket

| Méthode | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/jobs` · `/api/v1/jobs/{job_id}` | Jobs de l'organisation |
| `WS` | `/api/v1/jobs/ws/{job_id}` | Progression temps réel |

### 4.13 Artefacts, audit, organisation, licences, admin, sync, terrain

| Routeur | Endpoints clés |
|---|---|
| `/api/v1/artifacts` | `GET /download` (clé ou URL présignée) |
| `/api/v1/audit` | `GET /logs[/{id}]`, `GET /regards/{id}/history`, `GET /conduites/{id}/history` |
| `/api/v1/organization` | `GET`/`POST`/`DELETE /collaborators` |
| `/api/v1/license` | `GET /status` `/orders` `/proforma` (PDF) ; `POST /order` `/activate` |
| `/api/v1/admin` | `GET /orders` `/organizations` ; `POST /orders/{id}/approve|reject` `/organizations/{id}/extend-trial` — **404 pour tout non-superadmin** |
| `/api/v1/sync` | `GET /delta?since_version=&tables=` · `POST /push` · `POST /session` |
| `/api/v1/terrain` | `POST`/`GET /inspections[/{type}/{id}]` · `POST`/`GET`/`PATCH /incidents` |

### 4.14 Santé

`GET /health` → `200` (`status: healthy/degraded`) — sonde à la racine, hors `/api/v1`.

### 4.15 Pages & centre d'aide

`GET /aide` (centre d'aide), `GET /aide/docs` (index JSON), `GET /aide/doc/{path}` (fragment HTML d'un `.md` normatif — whitelist `docs/*.md` + `docs/adr/*.md`, archives exclues, stealth 404).

---

## 5. Passerelle Mobile & Synchronisation Terrain

### 5.1 Application Flutter (`mobile/`)

- Stack : Flutter, base locale SQLite/Drift chiffrée, `FlutterSecureStorage` pour le refresh token.
- Lancement : `cd mobile && flutter pub get && flutter run` ; web de test `flutter run -d chrome`.
- Configuration API : `--dart-define=API_BASE_URL=http://<hôte>:<API_PORT>` — pour un téléphone physique, utiliser l'IP locale de la machine FastAPI (pas `127.0.0.1`).
- Hors-ligne : secteur synchronisé en cache avant intervention ; mutations en file `pending_mutations`.

### 5.2 Protocole de synchronisation (ADR 0007)

1. `POST /api/v1/sync/session` — ouverture de session de sync.
2. `GET /api/v1/sync/delta?since_version=<v>&tables=regards,conduites,rejets` — modifications des collègues depuis la dernière sync.
3. `POST /api/v1/sync/push` — poussée des mutations terrain horodatées (rate-limité, résolution de conflits).
4. Conflits : *Last-Write-Wins* horodaté pour les cotes physiques ; audit trail immuable (`field_audit_logs`) ; incohérences majeures marquées `A_VALIDER_BUREAU` sans écraser la géométrie officielle.

### 5.3 Collecte terrain — `/api/v1/terrain`

Inspections (`POST`/`GET /inspections`, `/{object_type}/{object_id}`) et incidents (`POST`/`GET`/`PATCH /incidents`) géolocalisés avec photos.
