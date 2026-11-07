# 13 — Feuille de Route SaaS SWMM Platform

> **Objet** : Transformer `swmm-platform-poc` (application hybride locale d'assainissement et de modélisation SWMM) en une plateforme SaaS multi-tenant collaborative commercialisable.  
> **Portée** : Produit, architecture, sécurité, simulations asynchrones, mobilité terrain, facturation B2B, exploitation Docker.  
> **Convention** : Les cases `[ ]` sont des tâches à cocher ; chaque phase se termine par un **jalon mesurable** avec critères d'acceptation stricts. Tailles de tâches : S (< 1 j), M (1-3 j), L (3-8 j), XL (> 8 j).  
> **Version** : 1.0 — 2026-10-28 (Lancement de la transformation SaaS unifiée sous FastAPI).

---

## Table des Matières

1. [Vision cible et principes directeurs](#1-vision-cible-et-principes-directeurs)
2. [État des lieux — audit technique du POC](#2-état-des-lieux--audit-technique-du-poc)
3. [Architecture cible](#3-architecture-cible)
4. [Choix structurants (décisions arrêtées)](#4-choix-structurants-décisions-arrêtées)
5. [Phase 0 — Assainissement, documentation & Golden Master de référence](#phase-0--assainissement-documentation--golden-master-de-référence)
6. [Phase 1 — Authentification, multi-tenant et persistance PostgreSQL/PostGIS](#phase-1--authentification-multi-tenant-et-persistance-postgresqlpostgis)
7. [Phase 2 — Simulations asynchrones Celery/Redis et stockage d'artefacts S3/MinIO](#phase-2--simulations-asynchrones-celeryredis-et-stockage-dartefacts-s3minio)
8. [Phase 2bis — Moteur Hydrodynamique & Hydrologique EPA SWMM 5.2 Natif](#phase-2bis--moteur-hydrodynamique--hydrologique-epa-swmm-52-natif)
9. [Phase 3 — Produit SaaS : plans, feature gating, console opérateur et licences B2B](#phase-3--produit-saas-plans-feature-gating-console-opérateur-et-licences-b2b)
10. [Phase 4 — Passerelle mobile et synchronisation terrain déconnectée](#phase-4--passerelle-mobile-et-synchronisation-terrain-déconnectée)
11. [Phase 5 — API publique et interopérabilité SIG (QGIS / GeoJSON)](#phase-5--api-publique-et-interopérabilité-sig-qgis--geojson)
12. [Phase 6 — Frontend unifié, cartographie Leaflet et cockpit d'exploitation](#phase-6--frontend-unifié-cartographie-leaflet-et-cockpit-dexploitation)
13. [Phase 7 — Sécurité continue, industrialisation Docker et conformité](#phase-7--sécurité-continue-industrialisation-docker-et-conformité)
14. [Planning synthétique et jalons MVP](#planning-synthétique-et-jalons-mvp)
15. [Risques majeurs et mitigations](#risques-majeurs-et-mitigations)
16. [Indicateurs de succès (KPIs)](#indicateurs-de-succès-kpis)
- [Annexe A — Inventaire des routes à cloisonner](#annexe-a--inventaire-des-routes-à-cloisonner)
- [Annexe B — Artefacts de projet et destination cible S3](#annexe-b--artefacts-de-projet-et-destination-cible-s3)
- [Annexe C — Définition des quotas par plan](#annexe-c--définition-des-quotas-par-plan)
- [Annexe D — Checklist de mise en service (Go-Live)](#annexe-d--checklist-de-mise-en-service-go-live)

---

## 1. Vision Cible et Principes Directeurs

**Vision.** SWMM Platform devient la plateforme SaaS de référence pour la gestion et la modélisation hydraulique des réseaux d'assainissement et d'eaux pluviales. Les bureaux d'études, collectivités et régies municipales s'inscrivent, importent leurs couches SIG (GeoPackage, Shapefiles, MNT raster), auditent instantanément la qualité de leurs données (contre-pentes, sauts de radier), simulent les crues pluviales via EPA SWMM 5.2 et synchronisent leurs interventions de terrain sur smartphone — sans installation locale, facturé à l'abonnement d'entreprise.

**Principes directeurs non négociables :**

| # | Principe | Implication concrète |
|---|----------|----------------------|
| **P1** | **Isolation absolue des locataires** | Aucune donnée d'un client ne peut être lue ou modifiée par une autre organisation. Toute tentative renvoie `HTTP 404`. |
| **P2** | **Le moteur physique reste sanctuarisé** | On ne réécrit pas les algorithmes de `src/domain/` ni le moteur EPA SWMM 5.2. On les encapsule dans des services propres. |
| **P3** | **PostgreSQL/PostGIS = vérité, S3 = stockage d'artefacts** | Fin du stockage direct sur le disque local (`swmm_platform.db` et rasters éparpillés). |
| **P4** | **Tout calcul lourd est asynchrone** | L'API web FastAPI ne lance jamais de simulation SWMM ni de découpage MNT bloquant. |
| **P5** | **Architecture 12-Factor & Portabilité** | Configuration stricte par variables d'environnement (`.env`), zéro mot de passe en dur, images Docker standardisées. |
| **P6** | **Sécurité par défaut (Secure by Design)** | Chaque route est protégée et vérifie le tenant et le rôle RBAC par injection de dépendance. |
| **P7** | **Mobilité déconnectée native (Offline-First)** | L'application mobile terrain fonctionne sans réseau et réconcilie les données avec traçabilité complète. |

---

## 2. État des Lieux — Audit Technique du POC

Audit réalisé en octobre 2026 sur la base de code existante :

### 2.1 Les Acquis Solides (à préserver et valoriser)
- **Cœur métier géospatial et hydraulique riche** :
  - Détection avancée de la qualité de réseau (`src/qualite_reseau.py`, 40 500 lignes d'expertise : pentes, inversions, diamètres, sauts de radier, règles NP 650).
  - Validation topologique rigoureuse (`src/validateurs/topologie.py`).
  - Graphe orienté amont-aval et détection de clusters hydrauliques (`src/domain/detecteur_clusters.py`, `src/domain/graphe_reseau.py`).
  - Extraction de contours et intégration MNT/DEM (`src/domain/contour_workflow.py`, `src/domain/extracteur_contours.py`).
  - Générateur de fichiers d'entrée SWMM 5.2 (`src/controllers/generateur_swmm.py`).
- **Base API moderne amorcée** : Structure FastAPI dans `api/` avec routeurs par domaine (`qualite.py`, `clusters.py`, `network.py`, `simulations.py`, `sync.py`, `terrain.py`).
- **Composante mobile terrain innovante** : Application Flutter dans `mobile/` avec gestion des inspections et anomalies.
- **Visualisation cartographique interactive** : Feuilles de styles et scripts Leaflet avec orientation des conduites et affichage adaptatif selon le zoom.

### 2.2 Les Écarts Bloquants vers un SaaS Commercial

| Domaine | Constat Actuel | Gravité | Actions Correctives Prévues |
|---------|----------------|---------|-----------------------------|
| **Authentification** | Inexistante : aucune session, aucun utilisateur, accès ouvert | 🔴 Bloquant | Intégrer Argon2id, JWT + Cookies de session et RBAC (ADR 0001). |
| **Multi-Tenancy** | Aucune colonne `org_id` dans les tables, données partagées en vrac | 🔴 Bloquant | Migration PostgreSQL avec colonne `org_id` sur toutes les tables (ADR 0002). |
| **Double Serveur Web** | Coexistence confuse de Flask (`server.py`, port 5000) et FastAPI (`api/main.py`, port 5001) | 🔴 Bloquant | Unifier l'ensemble sous **FastAPI** (servir l'API + les templates/static Leaflet). |
| **Persistance des Fichiers** | SQLite local (`swmm_platform.db`) et fichiers MNT `.tif` sur disque | 🔴 Bloquant | PostgreSQL + PostGIS pour les données spatiales, MinIO/S3 pour les rasters et `.inp` (ADR 0004). |
| **Exécution des Calculs** | Risque de blocage lors des gros traitements SIG et simulations SWMM | 🔴 Bloquant | Généraliser les workers Celery + Redis pour toutes les tâches longues (ADR 0003). |
| **Synchronisation Mobile** | Routes de sync basiques sans gestion d'authentification opérateur ni résolution de conflits | 🟠 Majeur | Refonte du protocole de sync différentielle sécurisée (ADR 0007). |
| **Monétisation & Quotas** | Aucune gestion de licences, ni limitations de taille de réseau | 🟠 Majeur | Implémenter le Feature Gating et la console d'administration des licences (ADR 0006). |
| **Conteneurisation** | Pas de `docker-compose.yml` complet pour l'ensemble des briques | 🟠 Majeur | Fournir une infrastructure portable multi-services (ADR 0005). |

---

## 3. Architecture Cible

```
                            ┌──────────────────────────────────────────────┐
                            │    Navigateurs Web Bureau (Ingénieurs/BET)   │
                            │  Tableaux de bord, Cartographie Leaflet, SIG │
                            └──────────────────────┬───────────────────────┘
                                                   │ HTTPS
                                          ┌────────▼────────┐
                                          │  Reverse Proxy  │  Caddy / Nginx (SSL, Compression, Rate-Limit)
                                          └────────┬────────┘
                                                   │
                            ┌──────────────────────▼──────────────────────┐
                            │          SWMM Platform Web API              │
                            │             (FastAPI Unifié)                │
                            │  - Routeurs modulaires (/api/v1/*)          │
                            │  - Authentification Argon2id & JWT/Cookies  │
                            │  - Contrôle d'accès RBAC et Isolation Tenant│
                            │  - Feature Gating & Quotas Métier           │
                            │  - Passerelle Mobile Offline-First          │
                            │  - Console Opérateur SuperAdmin             │
                            └───┬──────────────┬──────────────┬───────────┘
                                │              │              │
                     ┌──────────▼───┐   ┌──────▼──────┐   ┌───▼──────────┐
                     │  PostgreSQL  │   │    Redis    │   │   S3/MinIO   │
                     │   + PostGIS  │   │  - Broker   │   │  - Rasters   │
                     │  - Tenants   │   │    Celery   │   │    MNT .tif  │
                     │  - Réseaux   │   │  - Cache    │   │  - GeoPackage│
                     │  - Regards   │   │  - Statuts  │   │  - Modèles   │
                     │  - Conduites │   └──────┬──────┘   │    .INP      │
                     │  - Licences  │          │          │  - Rapports  │
                     │  - Audit     │   ┌──────▼──────┐   │    PDF       │
                     └──────────────┘   │ Celery Async│   └──────────────┘
                                        │   Workers   │
                                        │  - PySWMM   │
                                        │  - MNT / DEM│
                                        │  - Topologie│
                                        └─────────────┘
                                               ▲
                                               │ HTTPS / JWT
                                    ┌──────────┴───────────┐
                                    │ Application Mobile   │
                                    │   Flutter (Terrain)  │
                                    │ Cache SQLite Offline │
                                    └──────────────────────┘
```

---

## 4. Choix Structurants (Décisions Arrêtées)

Les décisions d'architecture sont formalisées dans les fiches ADR dédiées :
- **D1 (ADR 0001)** : FastAPI unifié pour l'API et les interfaces web (Jinja2/Static), authentification Argon2id et double session JWT/Cookie.
- **D2 (ADR 0002)** : Multi-tenancy mutualisé dans PostgreSQL 16 + PostGIS 3.4 avec isolation stricte par colonne `org_id`.
- **D3 (ADR 0003)** : Traitements asynchrones systématiques des calculs SIG et SWMM via Celery et Redis.
- **D4 (ADR 0004)** : Découplage de la persistance des fichiers volumineux (MNT, GeoPackage, INP, PDF) vers un stockage compatible S3 (MinIO / Cloud souverain).
- **D5 (ADR 0005)** : Conteneurisation complète et hébergement portable via Docker Compose.
- **D6 (ADR 0006)** : Modèle de facturation B2B/B2G par devis proforma, bons de commande administratifs et jetons de licence.
- **D7 (ADR 0007)** : Synchronisation terrain déconnectée (Offline-First) pour l'application mobile Flutter avec journal d'audit immuable.
- **D8 (ADR 0008)** : Définition stricte du périmètre MVP centré sur le diagnostic SIG, la modélisation SWMM 5.2 et les interventions mobiles.

---

## 5. Découpage en Phases Opérationnelles

---

### Phase 0 — Assainissement, Documentation & Golden Master de Référence

> **Objectif** : Poser le socle documentaire officiel, sécuriser le dépôt Git et figer les calculs actuels comme référence d'invariance scientifique.

| Réf | Tâche | Statut | Taille | Livrables / Critères d'acceptation |
|---|---|---|---|---|
| 0.1 | Établir le corpus documentaire de référence | ✅ FAIT | M | `docs/14_FICHE_PRODUIT_CADRAGE.md`, `docs/14_GLOSSAIRE_ET_GARANTIES.md`, `docs/15_PLANS_TARIFAIRES.md`. |
| 0.2 | Rédiger l'ensemble des ADRs (0001 à 0008) | ✅ FAIT | M | Fiches ADR complètes dans `docs/adr/`. |
| 0.3 | Rédiger la feuille de route SaaS détaillée | ✅ FAIT | M | Ce document `docs/13_ROADMAP_SAAS.md` + `docs/09_ENDPOINTS_DOCUMENTATION.md` + `docs/01_README.md`. |
| 0.4 | Nettoyer et sécuriser le dépôt Git | ✅ FAIT | S | `.gitignore` vérifié/renforcé (exclusion des rasters lourds, des `.db` locaux, des caches). |
| 0.5 | Créer le jeu de données test certifié (« Golden Dataset ») | ✅ FAIT | M | Extraction d'un réseau représentatif (379 conduites, 372 regards, MNT 41x41) dans `tests/data/golden_dataset/`. |
| 0.6 | Mettre en place le Golden Master de non-régression | ✅ FAIT | L | Script automatique `tests/test_golden_master.py` validé en 4.2s (invariance stricte inventaire, MNT, clusters, qualité). |

> **Jalon Phase 0 [VALIDÉ ✅]** : Le Golden Master est exécuté avec succès en 4,2 s (5/5 tests validés) ; le Golden Dataset certifié (379 canalisations, 372 regards, MNT) est en place ; la documentation stratégique est validée ; le dépôt Git est assaini.

---

### Phase 1 — Authentification, Multi-Tenant et Persistance PostgreSQL/PostGIS

> **Objectif** : Introduire les organisations, les utilisateurs, les rôles RBAC et migrer la base SQLite locale vers PostgreSQL/PostGIS avec isolation par `org_id`.

| Réf | Tâche | Statut | Taille | Livrables / Critères d'acceptation |
|---|---|---|---|---|
| 1.1 | Schéma de données relationnel & spatial multi-tenant | ✅ FAIT | L | Modèles SQLAlchemy 2.0 / GeoAlchemy2 (`api/models.py`) avec `org_id` universel et contraintes de clés étrangères. |
| 1.2 | Migrations de base de données Alembic | ✅ FAIT | M | Configuration d'Alembic avec scripts de création initiale du schéma PostgreSQL + PostGIS. |
| 1.3 | Module d'authentification et gestion des utilisateurs | ✅ FAIT | L | Hachage Argon2id, création d'organisation, inscription, connexion, renouvellement de tokens JWT et sessions cookies. |
| 1.4 | Dépendances de sécurité et RBAC dans FastAPI | ✅ FAIT | M | `Depends(get_current_tenant_org)`, `Depends(require_role)` protégeant les endpoints contre tout accès non autorisé (stealth 404). |
| 1.5 | Unification de l'accès aux données (CRUD multi-tenant) | ✅ FAIT | L | Refonte de `api/crud.py` garantissant le filtre systématique `.where(Model.org_id == org_id)`. |
| 1.6 | Tests de sécurité et d'isolation inter-organisations | ✅ FAIT | M | Tests pytest prouvant qu'une organisation B reçoit un code `404` en tentant d'accéder aux données d'une organisation A (11/11 tests passés). |

> **Jalon Phase 1 [VALIDÉ ✅]** : 100% des tables portent un `org_id` ; un utilisateur ne peut voir que les données de son organisation ; l'isolation stealth 404 est prouvée par les tests automatisés (31/31 tests au vert).

---

### Phase 2 — Simulations Asynchrones Celery/Redis et Stockage S3/MinIO

> **Objectif** : Décharger le serveur web de tous les calculs lourds (SWMM, MNT, topologie) et éliminer le stockage sur le système de fichiers local.

| Réf | Tâche | Statut | Taille | Livrables / Critères d'acceptation |
|---|---|---|---|---|
| 2.1 | Module de stockage d'artefacts S3 (`api/core/storage.py`) | ✅ FAIT | M | Client MinIO / S3 unifié permettant l'upload, le download et la génération d'URLs pré-signées sécurisées (5/5 tests validés). |
| 2.2 | Migration du stockage des fichiers du POC vers S3 | ✅ FAIT | L | Téléversement des GeoPackages, rasters MNT `.tif` et fichiers `.inp` vers des buckets organisés par `org_id` avec route de download sécurisée (`/api/v1/artifacts/download`). |
| 2.3 | Mise en place de Celery et du broker Redis | ✅ FAIT | M | Configuration de `workers/celery_app.py` et gestionnaire de cycle de vie des jobs `api/core/jobs.py` (modes eager et asynchrone). |
| 2.4 | Encapsulation de la simulation SWMM 5.2 en tâche Celery | ✅ FAIT | L | Tâche asynchrone `run_swmm_simulation_task` avec suivi de progression (0 à 100%), calcul des équations de Saint-Venant et archivage S3. |
| 2.5 | Encapsulation de l'analyse MNT et des clusters en tâche Celery | ✅ FAIT | L | Tâche asynchrone `run_mnt_extraction_task` pour l'extraction de relief, interpolation altimétrique et délimitation de bassins. |
| 2.6 | Endpoints de suivi de tâches et WebSocket | ✅ FAIT | M | `GET /api/v1/jobs/{job_id}`, `GET /api/v1/jobs` et canal WebSocket `/ws/jobs/{job_id}` pour notifier l'interface en temps réel avec isolation stricte 404 (6/6 tests validés). |

> **Jalon Phase 2 [VALIDÉ ✅]** : Aucun calcul long ne bloque le serveur web FastAPI ; les artefacts volumineux sont partitionnés et stockés via ArtifactStore (Local/S3) ; les simulations SWMM et calculs MNT tournent en tâche de fond avec suivi de progression temps réel (42/42 tests au vert).

---

### Phase 2bis — Moteur Hydrodynamique & Hydrologique EPA SWMM 5.2 Natif

> **Objectif** : Passer du template simplifié à l'exécution hydrodynamique complète (Saint-Venant 1D) avec couplage pluie-débit réel, infiltration Horton, découpage surfacique Voronoï, et extraction certifiée des résultats hydrauliques.

| Réf | Tâche | Statut | Taille | Livrables / Critères d'acceptation |
|---|---|---|---|---|
| 2bis.1 | Générateur hydrologique de surface (`[SUBCATCHMENTS]`, `[SUBAREAS]`, `[INFILTRATION]`) | ✅ FAIT | M | Découpage Voronoï/Thiessen borné au réseau (`src/domain/hydrologie.py`), 59 sous-bassins élémentaires, attribution automatique aux regards (`Outlet`), calcul surface ($ha$), largeur $W$, pente, $\%Imperv$ (70%) et infiltration Horton ($f_0=75, f_c=10, k=4\text{ h}^{-1}$). |
| 2bis.2 | Générateur de sollicitations pluvieuses et temps sec (`[RAINGAGES]`, `[TIMESERIES]`) | ✅ FAIT | M | Hyétogrammes de Chicago / lois de Montana locales ($T=10, 50\text{ ans}$, orage d'été brutal 2h, temps sec pur) intégrés dans `src/domain/moteur_swmm.py`. |
| 2bis.3 | Modélisation des singularités hydrauliques et exutoires (`[CONDUITS]`, `[JUNCTIONS]`, `[OUTFALLS]`) | ✅ FAIT | M | Modélisation des sections circulaires Manning ($n=0.013$), cotes radiers, profondeurs de visite et exutoire libre (`FREE`) conforme standard EPA SWMM 5.2. |
| 2bis.4 | Intégration du moteur natif EPA SWMM 5.2 via `pyswmm` & `swmm-toolkit` | ✅ FAIT | L | Résolution hydrodynamique complète (`DYNWAVE`, Saint-Venant 1D) via binaires officiels EPA SWMM 5.2.4 x64 sans dépendance binaire externe. Bilan de continuité massique strict (erreur $< 1\%$, soit $-0.166\%$). |
| 2bis.5 | Extraction et décodeur du rapport de calcul officiel SWMM (`.rpt`) | ✅ FAIT | M | Extraction automatisée des KPIs : bilan de continuité, débit de pointe exutoire, détection des nœuds inondés (durée, débit crête, volume $m^3$), classification des conduites selon le taux de charge $Q/Q_{max}$ et remplissage $H/D$. |
| 2bis.6 | Cockpit SIG d'Ingénierie & Visualisation cartographique des couches thématiques | ✅ FAIT | L | Sidebar structurée en 4 volets thématiques, affichage immédiat de la sectorisation Voronoï avant calcul avec surfaces en $ha$, couches de résultats post-simulation ($Q/Q_{max}$ par couleurs vert/jaune/orange/rouge et regards débordants), et persistance permanente `/api/v1/simulations/latest`. |
| 2bis.7 | Détection spatiale des ouvrages orphelins & Raccordement pré-simulation (Variante 0 Opportuniste) | ✅ FAIT | M | Scan spatial automatique (< 120 m) des déversoirs d'orage (DVO), trop-pleins et stations de relevage orphelins ; interface interactive pré-simulation avec cases à cocher et tracés dynamiques en tiretés cyan (`dashArray: 8, 8`) sur Leaflet ; injection hydrodynamique SWMM et évaluation financière multi-agents (Variante 0, gain > 90%). |

> **Jalon Phase 2bis [VALIDÉ ✅]** : Simulation hydrodynamique native EPA SWMM 5.2 opérationnelle en 1 seconde sur le réseau témoin (erreur de routage $-0.166\%$) ; sectorisation de surface visible en amont (59 SB, 13.02 ha) ; affichage cartographique thématique des surcharges et débits de crête ; téléchargement des artefacts officiels `.INP` et `.RPT` ; détection et raccordement pré-simulation des ouvrages spéciaux orphelins.

---

### Phase 3 — Produit SaaS : Plans, Feature Gating, Console Opérateur et Licences B2B

> **Objectif** : Donner à la plateforme ses capacités commerciales : contrôle des quotas par plan, cycle administratif des bons de commande et cockpit SuperAdmin.

| Réf | Tâche | Statut | Taille | Livrables / Critères d'acceptation |
|---|---|---|---|---|
| 3.1 | Moteur de quotas et Feature Gating (`api/core/quotas.py`) | ✅ FAIT | M | Décorateur de validation des plafonds (nombre max de regards, accès MNT, accès mobile) selon le plan de l'organisation. |
| 3.2 | Générateur de Factures Proforma officielles (PDF) | ✅ FAIT | M | Route `/api/v1/license/proforma` générant un devis réglementaire téléchargeable en DZD avec ReportLab et conversion en toutes lettres. |
| 3.3 | Dépôt et cycle de validation des Bons de Commande | ✅ FAIT | M | Endpoint `/api/v1/license/order` pour téléversement du Bon de Commande client avec archivage ArtifactStore. |
| 3.4 | Générateur et validateur de clés de licences cryptographiques | ✅ FAIT | M | Format de jeton `SP-LIC-{PLAN}-{YEAR}-{RANDOM}`, validation d'intégrité, route `/api/v1/license/activate` et calcul d'échéance. |
| 3.5 | Console Opérateur SuperAdmin (`/api/v1/admin/*`) | ✅ FAIT | L | Endpoints réservés aux super-administrateurs (règle furtive 404) : supervision des abonnés, validation des commandes et prolongation d'essai. |
| 3.6 | Gestion de l'équipe d'organisation (`/api/v1/organization/collaborators`) | ✅ FAIT | M | Endpoints d'invitation de membres d'équipe, contrôle strict des quotas par plan et révocation. |

> **Jalon Phase 3 [VALIDÉ ✅]** : Le parcours complet de souscription administrative (devis / proforma PDF $\rightarrow$ bon de commande $\rightarrow$ approbation SuperAdmin $\rightarrow$ activation de licence `SP-LIC-...`) est opérationnel ; les quotas bloquent les dépassements ; 53/53 tests au vert.

---

### Phase 4 — Passerelle Mobile et Synchronisation Terrain Déconnectée

> **Objectif** : Sécuriser et fiabiliser la synchronisation bidirectionnelle avec l'application mobile Flutter pour un usage terrain robuste sans réseau.

| Réf | Tâche | Taille | Livrables / Critères d'acceptation |
|---|---|---|---|
| 4.1 | Sécurisation de l'API de synchronisation mobile | M | Endpoints `/api/v1/sync/push` et `/api/v1/sync/pull` protégés par JWT avec contrôle de rôle `field_operator`. |
| 4.2 | Protocole de synchronisation différentielle (Delta Sync) | L | Échange optimisé basé sur un curseur d'horodatage (`since_timestamp`) pour ne transférer que les données modifiées. |
| 4.3 | Moteur de réconciliation et résolution des conflits | L | Algorithme côté serveur avec priorité aux relevés in situ certifiés et détection des aberrations géométriques. |
| 4.4 | Téléversement et liaison des photos d'anomalies | M | Envoi des clichés terrain directement vers le bucket S3 avec redimensionnement automatique et association au regard. |
| 4.5 | Audit Trail immuable des modifications de terrain | M | Journalisation systématique dans la table `field_audit_logs` (auteur, horodatage, anciennes/nouvelles cotes, statut). |

> **Jalon Phase 4** : Un agent mobile peut effectuer 20 modifications en mode avion, se reconnecter et synchroniser l'ensemble sans conflit ni perte de données vers la base centrale.

---

### Phase 5 — API Publique et Interopérabilité SIG (QGIS / GeoJSON)

> **Objectif** : Permettre aux clients d'interconnecter la plateforme avec leurs outils SIG existants (QGIS, ArcGIS, exports institutionnels).

| Réf | Tâche | Taille | Livrables / Critères d'acceptation |
|---|---|---|---|
| 5.1 | Endpoints d'export GeoJSON et GeoPackage certifiés | M | Génération à la volée de couches réseau filtrées par bassin versant ou commune. |
| 5.2 | Endpoints de flux cartographiques WFS / Vector Tiles | L | Diffusion de tuiles vectorielles pour l'affichage fluide de grands réseaux (>50 000 objets) sur la carte web. |
| 5.3 | Export officiel des modèles SWMM 5.2 (`.inp`) | S | Téléchargement du fichier `.inp` complet prêt à être réouvert dans le logiciel desktop EPA SWMM standard. |
| 5.4 | Documentation Swagger / OpenAPI 3.0 exhaustive | S | Documentation interactive accessible sur `/docs` avec schémas Pydantic complets et exemples d'appels. |

> **Jalon Phase 5** : Le réseau assaini peut être consommé directement dans QGIS via l'API ou exporté en format standard SWMM 5.2 sans erreur de syntaxe.

---

### Phase 6 — Frontend Unifié, Cartographie Leaflet et Cockpit d'Exploitation

> **Objectif** : Unifier l'expérience utilisateur dans un tableau de bord web moderne, réactif et professionnel servi par FastAPI.

| Réf | Tâche | Taille | Livrables / Critères d'acceptation |
|---|---|---|---|
| 6.1 | Suppression définitive de Flask et unification sous FastAPI | M | Port des templates Jinja2 et des fichiers statiques Leaflet sous FastAPI (`StaticFiles` et `Jinja2Templates`). |
| 6.2 | Refonte de la barre de navigation et de l'espace organisation | M | Affichage du logo de l'organisation cliente, du plan actif, du compte à rebours de licence et du sélecteur de projets. |
| 6.3 | Intégration de la carte interactive d'anomalies | L | Affichage temps réel des contre-pentes, doublons, sens d'écoulement et profils en long hydrauliques. |
| 6.4 | Visualiseur de résultats de simulation SWMM | L | Affichage dynamique des hydrogrammes de débit aux exutoires, des courbes de submersion et des conduites saturées. |
| 6.5 | Module de génération de rapports d'audit PDF | M | Génération d'un rapport de schéma directeur complet en un clic (planches cartographiques, tableau des anomalies, KPIs). |

> **Jalon Phase 6** : L'interface web unique permet à un utilisateur de mener à bien l'intégralité du cycle de travail (import $\rightarrow$ audit $\rightarrow$ MNT $\rightarrow$ simulation $\rightarrow$ rapport).

---

### Phase 7 — Sécurité Continue, Industrialisation Docker et Conformité

> **Objectif** : Préparer la mise en production officielle avec une architecture conteneurisée, robuste et monitorée.

| Réf | Tâche | Taille | Livrables / Critères d'acceptation |
|---|---|---|---|
| 7.1 | Fichier `docker-compose.yml` multi-services complet | M | Orchestration de FastAPI, Worker Celery, PostgreSQL 16 PostGIS, Redis 7, MinIO et Caddy/Nginx. |
| 7.2 | Dockerfile multi-étapes optimisé | M | Compilation légère des bibliothèques C (GDAL, GEOS, PROJ, SWMM Toolkit). |
| 7.3 | Pipeline CI/CD GitHub Actions | M | Exécution automatique des tests pytest, vérification du Golden Master et scan de failles de sécurité. |
| 7.4 | Observabilité, journalisation structurée et métriques | M | Logs JSON sur stdout, suivi des temps de calcul et métriques de santé du système (`/api/v1/health`). |
| 7.5 | Audit de sécurité pré-lancement (Checklist Go-Live) | M | Contrôle contre les failles OWASP Top 10 (CSRF, injection SQL, path traversal, validation des uploads). |

> **Jalon Phase 7** : Démarrage de la stack complète en une commande `docker compose up -d` ; 100% des tests validés en CI ; certification Go-Live obtenue.

---

## 6. Planning Synthétique et Jalons du MVP

```
Mois 1 : Fondations & Sécurité
├── Phase 0 : Corpus documentaire & Golden Master [Jalon 0]
└── Phase 1 : Auth Argon2id, Multi-Tenant & PostgreSQL/PostGIS [Jalon 1]

Mois 2 : Scalabilité & Cœur Hydraulique
├── Phase 2 : Tâches asynchrones Celery & Stockage S3/MinIO [Jalon 2]
└── Phase 3 : Feature Gating, Plans B2B & Console Opérateur [Jalon 3]

Mois 3 : Mobilité & Industrialisation
├── Phase 4 : Synchronisation Mobile Terrain Offline [Jalon 4]
├── Phase 5 & 6 : API Publique, Frontend Leaflet Unifié & Rapports [Jalon 5 & 6]
└── Phase 7 : Dockerisation complète, CI/CD & Lancement Officiel [Jalon 7 — GO LIVE]
```

---

## 7. Risques Majeurs et Mitigations

| Risque Identifié | Impact | Probabilité | Stratégie de Mitigation |
|---|---|---|---|
| **Dérive des calculs hydrauliques lors de la migration** | Critique | Faible | **Filet de sécurité Golden Master** : le test de non-régression compare au millimètre les résultats avant et après refactorisation. |
| **Fichiers MNT raster trop volumineux saturant le serveur** | Élevé | Moyenne | Découpage en tuiles géographiques, compression Cloud Optimized GeoTIFF (COG) et stockage exclusif sur S3. |
| **Conflits de saisie entre agents terrain et bureau** | Moyen | Élevée | Protocole de réconciliation avec horodatage certifié, historique immuable (Audit Trail) et revue des cas douteux. |
| **Rejet du paiement par carte bancaire par les régies publiques** | Élevé | Très élevée | **Support natif du circuit administratif B2G** : devis proforma réglementaire, bon de commande administratif et clés de licence. |
| **Fuite de données entre deux organisations concurrentes** | Critique | Faible | Dépendance de sécurité universelle `Depends(get_current_tenant_org)` et tests de pénétration automatisés en CI. |

---

## 8. Indicateurs de Succès (KPIs)

1. **Intégrité scientifique** : **0 % d'écart** sur les résultats de simulation hydraulique et de diagnostic par rapport au moteur historique.
2. **Performance** : Temps de réponse des routes cartographiques $< 200 \text{ ms}$ pour 10 000 objets ; temps de génération du fichier SWMM $< 5 \text{ s}$.
3. **Disponibilité web** : 0 requête web bloquée par un calcul lourd (100% des calculs de plus de 2 secondes déportés sur Celery).
4. **Fiabilité mobile** : Taux de succès de synchronisation terrain $> 99{,}9\%$ même après une semaine complète de travail hors-ligne.
5. **Couverture de tests** : $> 85\%$ de couverture du code métier avec tests d'isolation multi-tenant systématiques.

---

## Annexes

### Annexe A — Inventaire des Routes à Cloisonner

Toutes les routes existantes et cibles doivent intégrer la vérification du locataire :

```
/api/v1/network/*       -> Protégé par org_id (lecture et écriture des regards/conduites)
/api/v1/qualite/*       -> Protégé par org_id (audit qualité et anomalies du réseau)
/api/v1/clusters/*      -> Protégé par org_id (graphe hydraulique et bassins versants)
/api/v1/mnt/*           -> Protégé par org_id (rasters d'élévation et extraction de crêtes)
/api/v1/simulations/*   -> Protégé par org_id (génération et lancement de modèles SWMM)
/api/v1/sync/*          -> Protégé par org_id et rôle field_operator (synchronisation mobile)
/api/v1/reports/*       -> Protégé par org_id (génération et téléchargement de rapports PDF)
/api/v1/organization/*  -> Réservé aux administrateurs de l'organisation locataire
/api/v1/admin/*         -> Règle d'invisibilité stricte (HTTP 404 pour les non-superadmins)
```

### Annexe B — Artefacts de Projet et Destination Cible S3

| Fichier / Donnée | Emplacement POC Historique | Emplacement Cible S3 / MinIO |
|---|---|---|
| GeoPackage réseau | `swmm-platform-poc/*.gpkg` | `s3://swmm-artefacts/{org_id}/networks/{id}/network.gpkg` |
| Raster MNT relief | `swmm-platform-poc/AST14DEM_*.tif` | `s3://swmm-artefacts/{org_id}/dem/{id}/elevation.tif` |
| Fichier d'entrée SWMM | `output/*.inp` | `s3://swmm-artefacts/{org_id}/simulations/{id}/model.inp` |
| Binaire de résultat SWMM | Fichiers temporaires locaux | `s3://swmm-artefacts/{org_id}/simulations/{id}/results.out` |
| Rapports d'audit officiels | Génération locale éphémère | `s3://swmm-artefacts/{org_id}/reports/{id}/audit_report.pdf` |
| Photos terrain anomalies | Dossier local mobile | `s3://swmm-artefacts/{org_id}/field_photos/{id}.jpg` |

### Annexe C — Définition des Quotas par Plan

| Plan Métier | Max Nœuds / Regards | Projets Actifs | Calculs Parallèles | Module MNT | Application Mobile | Rétention Données |
|---|---|---|---|---|---|---|
| `demo` (14 jours) | 2 000 | 3 | 1 | Inclus | ❌ Non | 14 jours |
| `education` | 500 | 3 | 1 | ❌ Non | ❌ Non | 30 jours |
| `bet` | 15 000 | 25 | 3 | Inclus | Option | 365 jours |
| `exploitation` | Illimité | Illimité | 10 (prioritaire) | Inclus | **Inclus (Illimité)**| Illimité |

### Annexe D — Checklist de Mise en Service (Go-Live)

- [ ] Les 8 fiches ADR sont approuvées et appliquées dans le code.
- [ ] Le Golden Master de non-régression hydraulique est validé à 100%.
- [ ] Chaque route de l'API vérifie le locataire (`org_id`) et le rôle RBAC.
- [ ] Aucun mot de passe par défaut ni secret en dur n'existe dans le dépôt.
- [ ] Les mots de passe sont hachés avec Argon2id.
- [ ] Les calculs SWMM et traitements MNT s'exécutent sur Celery sans bloquer l'API.
- [ ] Les fichiers volumineux sont stockés sur S3 / MinIO avec URLs pré-signées.
- [ ] La synchronisation mobile offline réconcilie les modifications sans perte de données.
- [ ] La console opérateur SuperAdmin permet de valider les bons de commande et d'émettre des licences.
- [ ] L'ensemble de la plateforme démarre via `docker compose up -d` sans configuration manuelle complexe.
