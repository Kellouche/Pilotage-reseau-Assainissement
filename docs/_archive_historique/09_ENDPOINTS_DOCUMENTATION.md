# Documentation des Endpoints API — DrainPilot 5.2

> **Plateforme SaaS Multi-Tenant d'Aide à la Décision, Contrôle Qualité SIG,
> Analyse Morphologique MNT, Modélisation Dynamique EPA SWMM 5.2 et
> Synchronisation Mobile Terrain**
> **Dernière mise à jour :** 22 Novembre 2026
> **Architecture :** API unifiée FastAPI (`api.main:app`), multi-tenant,
> stockage d'artefacts `ArtifactStore` (local en dev, S3 en prod),
> worker asynchrone Celery/Redis, RBAC et passerelle mobile.
> **Format d'échange :** JSON (UTF-8), GeoJSON pour les couches spatiales,
> binaire pour les rasters et exports `.inp`/`.rpt`/PDF.

---

## 1. Vue d'ensemble

Toutes les routes métier sont exposées sous le préfixe `/api/v1`.
Les exceptions notables :

- `GET /health` — sonde de santé à la racine (pas sous `/api/v1`) ;
- `GET /api/v1/jobs/ws/{job_id}` — WebSocket temps réel de progression des jobs.

### Authentification

Deux modes acceptés sur les routes protégées :

- **Cookie de session** `access_token` (interface web cockpit) ;
- **`Authorization: Bearer <JWT>`** (mobile, scripts, intégrations).

### Rôles RBAC

| Rôle | Niveau | Usage |
|---|---|---|
| `superadmin` | Plateforme | Console opérateur `/api/v1/admin/*` — invisibilité stricte (404) pour les autres |
| `owner` / `admin` | Organisation | Équipe, licences, facturation proforma, bons de commande |
| `engineer` | Organisation | Import réseaux, corrections, simulations SWMM, exports |
| `field_operator` | Organisation | Synchronisation mobile, terrain, incidents |
| `viewer` | Organisation | Lecture seule |

Le contexte tenant est injecté par `TenantContext` (`api/core/security.py`) ;
l'acteur authentifié est `ctx.actor`, l'organisation `ctx.org`.

---

## 2. Authentification & Sessions — `/api/v1/auth`

| Méthode | Endpoint | Description | Statut |
|---|---|---|---|
| `POST` | `/api/v1/auth/register` | Création organisation + compte admin (201) | `201` |
| `POST` | `/api/v1/auth/verify-email` | Vérification email / activation du compte | `200` |
| `POST` | `/api/v1/auth/resend-code` | Renvoi du code de vérification | `200` |
| `GET` | `/api/v1/auth/check-email` | Vérifie la disponibilité d'un email | `200` |
| `POST` | `/api/v1/auth/login` | Connexion (cookie session + JWT Bearer) | `200` |
| `POST` | `/api/v1/auth/refresh` | Renouvellement du token d'accès | `200` |
| `POST` | `/api/v1/auth/logout` | Déconnexion, révocation du jeton | `200` |
| `GET` | `/api/v1/auth/me` | Profil utilisateur, rôle, organisation | `200` |
| `PATCH` | `/api/v1/auth/profile` | Mise à jour du profil | `200` |
| `POST` | `/api/v1/auth/change-password` | Changement de mot de passe (re-hachage Argon2id) | `200` |
| `GET` | `/api/v1/auth/api-keys` | Liste des clés API personnelles | `200` |
| `POST` | `/api/v1/auth/api-keys` | Création d'une clé API (201) | `201` |
| `DELETE` | `/api/v1/auth/api-keys/{key_id}` | Révocation d'une clé API | `204` |

---

## 3. Réseau d'assainissement — `/api/v1/network`

CRUD sur les couches métier du GeoPackage actif du projet, données servies
en WGS84 pour Leaflet.

| Méthode | Endpoint | Description | Statut |
|---|---|---|---|
| `GET` | `/api/v1/network/regards` | Liste des regards (pagination/filtres) | `200` |
| `GET` | `/api/v1/network/regards/{regard_id}` | Détail d'un regard | `200` |
| `POST` | `/api/v1/network/regards` | Création d'un regard | `201` |
| `PATCH` | `/api/v1/network/regards/{regard_id}` | Modification d'un regard | `200` |
| `DELETE` | `/api/v1/network/regards/{regard_id}` | Suppression d'un regard | `204` |
| `GET` | `/api/v1/network/conduites` | Liste des conduites/collecteurs | `200` |
| `GET` | `/api/v1/network/conduites/{conduite_id}` | Détail d'une conduite | `200` |
| `POST` | `/api/v1/network/conduites` | Création d'une conduite | `201` |
| `PATCH` | `/api/v1/network/conduites/{conduite_id}` | Modification d'une conduite | `200` |
| `DELETE` | `/api/v1/network/conduites/{conduite_id}` | Suppression d'une conduite | `204` |
| `GET` | `/api/v1/network/rejets` | Liste des rejets/exutoires | `200` |
| `POST` | `/api/v1/network/rejets` | Création d'un rejet | `201` |

### Projets, datasets & imports

| Méthode | Endpoint | Description | Statut |
|---|---|---|---|
| `GET` | `/api/v1/network/datasets` | Liste des datasets/projets de l'organisation (+ `active_project`) | `200` |
| `POST` | `/api/v1/network/load-dataset/{dataset_id}` | Active un dataset existant comme projet courant | `200` |
| `POST` | `/api/v1/network/load-demo` | Charge le réseau témoin de démonstration | `200` |
| `POST` | `/api/v1/network/load-master` | Charge le réseau maître de référence | `200` |
| `POST` | `/api/v1/network/reset` | Réinitialise le contexte réseau actif | `200` |
| `POST` | `/api/v1/network/upload` | Import d'un réseau (GeoPackage, shapefile zippé, `.inp`) | `200/202` |
| `GET` | `/api/v1/network/subcatchments` | Sous-bassins Voronoï au format GeoJSON (surfaces ha, imperméabilisation, pente, exutoire) | `200 (GeoJSON)` |
| `GET` | `/api/v1/network/orphelins/geojson` | Regards orphelins / non raccordés au format GeoJSON | `200 (GeoJSON)` |
| `GET` | `/api/v1/network/export/inp` | Export du modèle SWMM `.inp` du réseau courant | `200 (INP)` |

> **Contexte spatial (snapshot)** : les endpoints de lecture spatiale
> (`/layers`, `/simulations/latest`, `/aux-layers/*`, etc.) acceptent le
> paramètre `snapshot` (version_id ou sha256) pour lire le GeoPackage
> **exact** ayant produit une simulation archivée — jamais le réseau courant.

---

## 4. Qualité du réseau — `/api/v1/qualite`

Analyse topologique du réseau actif (anti-inversions, sauts de radier,
doublons, cohérence amont/aval…). Le réseau analysé est celui du contexte
projet actif ; `project_id` peut être passé en query pour cibler un projet.

| Méthode | Endpoint | Description | Statut |
|---|---|---|---|
| `GET` | `/api/v1/qualite/analyse` | Rapport complet d'audit qualité | `200` |
| `GET` | `/api/v1/qualite/diagnostic` | Diagnostic tunnel / vue synthétique | `200` |
| `GET` | `/api/v1/qualite/anomalies/{type_anomalie}` | Détail des anomalies d'un type donné | `200` |
| `GET` | `/api/v1/qualite/scores` | Décomposition des sous-scores de qualité | `200` |
| `GET` | `/api/v1/qualite/scores-bassins` | Scores de qualité par bassin versant | `200` |
| `GET` | `/api/v1/qualite/statistiques` | Statistiques globales du réseau | `200` |
| `POST` | `/api/v1/qualite/valider-incremental` | Validation incrémentale d'anomalies | `200` |
| `POST` | `/api/v1/qualite/export-csv` | Export CSV des anomalies | `200 (CSV)` |
| `GET` | `/api/v1/qualite/cache/status` | État du cache d'analyse | `200` |
| `DELETE` | `/api/v1/qualite/cache` | Purge du cache d'analyse | `200` |

---

## 5. Corrections topologiques — `/api/v1/corrections`

| Méthode | Endpoint | Description | Statut |
|---|---|---|---|
| `POST` | `/api/v1/corrections/manuel/{fid}` | Correction manuelle ciblée d'un objet | `200` |
| `GET` | `/api/v1/corrections/hybride/suggestable_fids` | Liste des objets corrigeables en mode hybride | `200` |
| `GET` | `/api/v1/corrections/hybride/suggest` | Suggestions de correction hybrides (règles + ML) | `200` |
| `GET` | `/api/v1/corrections/profile/{fid}` | Profil longitudinal / fiche détaillée d'un objet | `200` |
| `POST` | `/api/v1/corrections/automatique` | Campagne de corrections automatiques | `200` |

---

## 6. Clusters & graphe hydraulique — `/api/v1/clusters`

| Méthode | Endpoint | Description | Statut |
|---|---|---|---|
| `GET` | `/api/v1/clusters` | Liste des clusters/bassins hydrauliques | `200` |
| `GET` | `/api/v1/clusters/status` | Statut du partitionnement courant | `200` |
| `POST` | `/api/v1/clusters/graph/rebuild` | Reconstruction du graphe de connectivité | `200` |
| `GET` | `/api/v1/clusters/recalculate-all` | Recalcul global (GET, interne) | `200` |
| `POST` | `/api/v1/clusters/recalculate-all` | Recalcul global du partitionnement | `200/202` |
| `POST` | `/api/v1/clusters/manual-basin` | Création d'un bassin manuel (polygone tracé) | `201` |
| `DELETE` | `/api/v1/clusters/manual-basin/{bassin_id}` | Suppression d'un bassin manuel | `204` |
| `GET` | `/api/v1/clusters/manual-basin` | Liste des bassins manuels | `200` |
| `GET` | `/api/v1/clusters/{cluster_id}` | Détail d'un cluster | `200` |
| `POST` | `/api/v1/clusters/{cluster_id}/recalculate` | Recalcul ciblé d'un cluster | `200/202` |
| `GET` | `/api/v1/clusters/{cluster_id}/geojson` | Géométrie GeoJSON du cluster | `200 (GeoJSON)` |
| `GET` | `/api/v1/clusters/{cluster_id}/ouvrages-proches` | Ouvrages à proximité du cluster | `200` |

---

## 7. Simulations EPA SWMM 5.2 — `/api/v1/simulations`

Moteur : PySWMM / Saint-Venant 1D (`DYNWAVE`), découpage Voronoï,
infiltration Horton, hyétographes Chicago/Montana, DWF.
Exécution synchrone (`/run`) ou asynchrone via Celery (`POST /`).

### Pilotage & référentiels

| Méthode | Endpoint | Description | Statut |
|---|---|---|---|
| `GET` | `/api/v1/simulations` | Historique des simulations de l'organisation | `200` |
| `POST` | `/api/v1/simulations` | Lancement asynchrone (retourne `job_id`, 202) | `202` |
| `GET` | `/api/v1/simulations/scenarios` | Scénarios pluviométriques prédéfinis | `200` |
| `GET` | `/api/v1/simulations/typologies-sol` | Typologies de sol / paramètres d'infiltration | `200` |
| `GET` | `/api/v1/simulations/pluviometrie/referentiel` | Référentiel IDF pluviométrie Algérie | `200` |
| `GET` | `/api/v1/simulations/pluviometrie/stations` | Stations pluviométriques du référentiel | `200` |
| `POST` | `/api/v1/simulations/pluviometrie/bms-preview` | Aperçu BMS (bulletin météorologique) | `200` |
| `GET` | `/api/v1/simulations/ouvrages-proches` | Ouvrages proches pour calage spatial | `200` |

### Exécution & résultats

| Méthode | Endpoint | Description | Statut |
|---|---|---|---|
| `POST` | `/api/v1/simulations/run` | Exécution synchrone SWMM 5.2 (synthèse + couches thématiques) | `200` |
| `GET` | `/api/v1/simulations/latest` | Résultats de la dernière simulation (accepte `snapshot`, `simulation_id`) | `200` |
| `GET` | `/api/v1/simulations/{simulation_id}` | Détail d'une simulation | `200` |
| `GET` | `/api/v1/simulations/{simulation_id}/resultat` | Résultats persistés d'une simulation archivée | `200` |
| `DELETE` | `/api/v1/simulations/{simulation_id}` | Suppression d'une simulation | `204` |
| `GET` | `/api/v1/simulations/job/{job_id}` | Simulation associée à un job | `200` |
| `GET` | `/api/v1/simulations/status/{job_id}` | Statut d'avancement d'un job | `200` |
| `GET` | `/api/v1/simulations/cluster/{cluster_id}` | Simulations d'un cluster/bassin | `200` |
| `GET` | `/api/v1/simulations/bassin/{cluster_id}` | Résultats simulés d'un bassin | `200` |
| `GET` | `/api/v1/simulations/bassin/{cluster_id}/historique` | Historique des simulations du bassin | `200` |
| `GET` | `/api/v1/simulations/timeseries` | Séries temporelles Q(t)/y(t) — accepte `simulation_id` et `snapshot` | `200` |
| `GET` | `/api/v1/simulations/recherche-element` | Recherche d'un regard/conduite par numéro ou nom | `200` |
| `POST` | `/api/v1/simulations/validate-buffer` | Validation d'un buffer d'étude (extraction pochoir) | `200` |
| `GET` | `/api/v1/simulations/cotes-suspectes` | Registre des cotes altimétriques suspectes | `200` |
| `POST` | `/api/v1/simulations/cotes-suspectes/valider` | Validation/correction d'une cote suspecte | `200` |

### Profils, rapports & exports

| Méthode | Endpoint | Description | Statut |
|---|---|---|---|
| `GET` | `/api/v1/simulations/profil-en-long` | Profil en long hydraulique HGL le long d'un chemin | `200` |
| `GET` | `/api/v1/simulations/download/inp` | `.inp` SWMM de la dernière simulation | `200 (INP)` |
| `GET` | `/api/v1/simulations/download/rpt` | Rapport `.rpt` officiel EPA SWMM | `200 (RPT)` |
| `GET` | `/api/v1/simulations/rapport-diagnostic-pdf` | Rapport diagnostic PDF haute définition | `200 (PDF)` |
| `GET` | `/api/v1/simulations/bms/ordre-mission-pdf` | Ordre de mission BMS en PDF | `200 (PDF)` |
| `GET` | `/api/v1/simulations/agents/interpretation` | Interprétation multi-agents des résultats | `200` |

---

## 8. Apports de temps sec (DWF) — `/api/v1/apports`

Gestion des débits de temps sec injectés dans le modèle SWMM.
`project_id` est passé en query parameter sur la plupart des routes.

| Méthode | Endpoint | Description | Statut |
|---|---|---|---|
| `GET` | `/api/v1/apports` | Liste des apports DWF du projet | `200` |
| `POST` | `/api/v1/apports` | Création d'un apport (`code_apport` auto `AP-YYYY-NNNN`) | `201` |
| `GET` | `/api/v1/apports/{apport_id}` | Détail d'un apport | `200` |
| `PUT` | `/api/v1/apports/{apport_id}` | Modification d'un apport | `200` |
| `DELETE` | `/api/v1/apports/{apport_id}` | Suppression (204) | `204` |
| `POST` | `/api/v1/apports/{apport_id}/revalider` | Re-validation d'un apport incompatible | `200` |
| `GET` | `/api/v1/apports/profils` | Profils DWF disponibles | `200` |
| `GET` | `/api/v1/apports/noeuds` | Nœuds candidats à l'injection | `200` |
| `GET` | `/api/v1/apports/a-reconcilier` | Apports en attente de réconciliation GPKG | `200` |
| `GET` | `/api/v1/apports/history` | Journal global des apports | `200` |
| `GET` | `/api/v1/apports/{apport_id}/history` | Historique d'un apport | `200` |
| `POST` | `/api/v1/apports/purger-orphelins` | Purge des apports orphelins | `200` |

---

## 9. Couches SIG satellite & altimétrie — `/api/v1/projets/{project_id}/aux-layers`

Import et exploitation de couches externes (shapefile, GeoJSON…) rattachées
à un projet : altimétrie, topographie, référentiels. Le paramètre `snapshot`
est supporté pour l'isolation par version.

| Méthode | Endpoint | Description | Statut |
|---|---|---|---|
| `POST` | `.../aux-layers` | Import d'une couche satellite | `201` |
| `GET` | `.../aux-layers` | Liste des couches du projet | `200` |
| `GET` | `.../aux-layers/{layer_id}` | Métadonnées d'une couche | `200` |
| `DELETE` | `.../aux-layers/{layer_id}` | Suppression d'une couche | `204` |
| `GET` | `.../aux-layers/{layer_id}/geojson` | Contenu GeoJSON de la couche | `200 (GeoJSON)` |
| `GET` | `.../aux-layers/{layer_id}/elevation` | Interpolation de cote (IDW) en un point | `200` |
| `GET` | `.../aux-layers/{layer_id}/regards-terrain` | Injection des cotes terrain sur les regards | `200` |
| `POST` | `.../aux-layers/{layer_id}/regards-terrain/recalculer` | Recalcul des cotes terrain | `200` |
| `GET` | `.../aux-layers/{layer_id}/apercu-inp` | Aperçu de l'impact sur le `.inp` généré | `200` |
| `GET` | `.../aux-layers/{layer_id}/suspects-ecoulement` | File de revue P1 : sens d'écoulement suspects | `200` |
| `GET` | `.../aux-layers/{layer_id}/raccordements-orphelins` | Regards orphelins et scoring P2 des raccordements candidats | `200` |

---

## 10. Extraction par pochoir — `/api/v1/projets/{project_id}/extraction-pochoir`

| Méthode | Endpoint | Description | Statut |
|---|---|---|---|
| `POST` | `/api/v1/projets/{project_id}/extraction-pochoir` | Extraction des entités intersectant un polygone pochoir → zip Shapefiles + GPKG fusionné | `200/202` |

---

## 11. Garde-fou hydraulicien — `/api/v1/projets/{project_id}/garde-fou`

Configuration par projet des seuils de garde-fou (presets et profils réseau).

| Méthode | Endpoint | Description | Statut |
|---|---|---|---|
| `GET` | `.../garde-fou` | Configuration garde-fou du projet | `200` |
| `PUT` | `.../garde-fou` | Mise à jour de la configuration | `200` |
| `POST` | `.../garde-fou/reaudit` | Relance de l'audit avec la nouvelle configuration | `200` |

---

## 12. MNT / Modèle Numérique de Terrain — `/api/v1/mnt`

| Méthode | Endpoint | Description | Statut |
|---|---|---|---|
| `POST` | `/api/v1/mnt/analyser-bassins` | Analyse des bassins versants depuis un DEM TIFF (`dem_path`) | `200` |
| `GET` | `/api/v1/mnt/cache/status` | État du cache d'analyse MNT | `200` |
| `DELETE` | `/api/v1/mnt/cache` | Purge du cache MNT | `200` |
| `GET` | `/api/v1/mnt/statut` | Statut du module MNT | `200` |

> L'extraction MNT lourde est déléguée au worker Celery
> (`workers/tasks/mnt_tasks.py`).

---

## 13. Jobs asynchrones & WebSocket — `/api/v1/jobs`

| Méthode | Endpoint | Description | Statut |
|---|---|---|---|
| `GET` | `/api/v1/jobs` | Liste des jobs de l'organisation (`network_id`, `status`, pagination) | `200` |
| `GET` | `/api/v1/jobs/{job_id}` | Détail/statut d'un job | `200` |
| `WS` | `/api/v1/jobs/ws/{job_id}` | Progression temps réel d'un job (WebSocket) | `WS` |

---

## 14. Artefacts & stockage — `/api/v1/artifacts`

| Méthode | Endpoint | Description | Statut |
|---|---|---|---|
| `GET` | `/api/v1/artifacts/download` | Téléchargement d'un artefact (clé ou URL présignée) | `200` |

Le stockage sous-jacent est `ArtifactStore` (`api/core/storage.py`) :
`LocalStore` en développement, `S3Store` (S3/MinIO) en production via
variables `S3_*`. Les artefacts sont organisés par `org_id`/`project_id`.

---

## 15. Traçabilité & audit — `/api/v1/audit`

| Méthode | Endpoint | Description | Statut |
|---|---|---|---|
| `GET` | `/api/v1/audit/logs` | Journal d'audit de l'organisation | `200` |
| `GET` | `/api/v1/audit/logs/{record_id}` | Détail d'une entrée d'audit | `200` |
| `GET` | `/api/v1/audit/regards/{regard_id}/history` | Historique des modifications d'un regard | `200` |
| `GET` | `/api/v1/audit/conduites/{conduite_id}/history` | Historique des modifications d'une conduite | `200` |

---

## 16. Organisation & équipe — `/api/v1/organization`

| Méthode | Endpoint | Description | Statut |
|---|---|---|---|
| `GET` | `/api/v1/organization/collaborators` | Membres de l'organisation et rôles | `200` |
| `POST` | `/api/v1/organization/collaborators` | Ajout/invitation d'un collaborateur | `201` |
| `DELETE` | `/api/v1/organization/collaborators/{user_id}` | Retrait d'un collaborateur | `200` |

---

## 17. Licences & facturation B2B — `/api/v1/license`

| Méthode | Endpoint | Description | Statut |
|---|---|---|---|
| `GET` | `/api/v1/license/status` | État de la licence active de l'organisation | `200` |
| `GET` | `/api/v1/license/orders` | Bons de commande de l'organisation | `200` |
| `POST` | `/api/v1/license/order` | Soumission d'un bon de commande | `201` |
| `POST` | `/api/v1/license/activate` | Activation par jeton de licence | `200` |
| `GET` | `/api/v1/license/proforma` | Devis proforma PDF (DZD/EUR) | `200 (PDF)` |

---

## 18. Console superadmin — `/api/v1/admin`

Règle d'invisibilité : tout non-superadmin reçoit `404`.

| Méthode | Endpoint | Description | Statut |
|---|---|---|---|
| `GET` | `/api/v1/admin/orders` | Bons de commande en attente de validation | `200` |
| `POST` | `/api/v1/admin/orders/{order_id}/approve` | Approbation + émission du jeton de licence | `200` |
| `POST` | `/api/v1/admin/orders/{order_id}/reject` | Rejet motivé du bon de commande | `200` |
| `GET` | `/api/v1/admin/organizations` | Liste consolidée des organisations | `200` |
| `POST` | `/api/v1/admin/organizations/{org_id}/extend-trial` | Prolongation de la période d'évaluation | `200` |

---

## 19. Synchronisation mobile — `/api/v1/sync`

| Méthode | Endpoint | Description | Statut |
|---|---|---|---|
| `GET` | `/api/v1/sync/delta` | Modifications depuis `since_version` (`tables=regards,conduites,rejets`) | `200` |
| `POST` | `/api/v1/sync/push` | Poussée de mutations hors-ligne (rate-limité, résolution de conflits) | `200` |
| `POST` | `/api/v1/sync/session` | Ouverture de session de synchronisation | `200` |

---

## 20. Collecte terrain — `/api/v1/terrain`

| Méthode | Endpoint | Description | Statut |
|---|---|---|---|
| `POST` | `/api/v1/terrain/inspections` | Création d'une inspection terrain | `201` |
| `GET` | `/api/v1/terrain/inspections` | Liste des inspections | `200` |
| `GET` | `/api/v1/terrain/inspections/{object_type}/{object_id}` | Inspections d'un objet | `200` |
| `POST` | `/api/v1/terrain/incidents` | Signalement d'un incident | `201` |
| `GET` | `/api/v1/terrain/incidents` | Liste des incidents | `200` |
| `PATCH` | `/api/v1/terrain/incidents/{incident_id}` | Mise à jour d'un incident | `200` |

---

## 21. Santé — `/health`

| Méthode | Endpoint | Description | Statut |
|---|---|---|---|
| `GET` | `/health` | État global du service (base de données, `status: healthy/degraded`) | `200` |

---

## 22. Écarts notables par rapport aux versions antérieures

Ce document remplace la version du 28 Octobre 2026, qui décrivait une
architecture cible plus que l'API réelle. Principaux écarts corrigés :

- Préfixe réseau : `/api/v1/network` (et non `/api/v1/networks`) ;
- Routes qualite sans `network_id` dans le path (contexte projet actif) ;
- Nouveaux modules documentés : `apports` (DWF), `aux-layers`, `garde-fou`,
  `extractions`, `corrections`, `artifacts`, `audit`, `licensing`, `admin` ;
- Suppression d'endpoints inexistants : `/terrain/photos/upload`,
  `/terrain/audit-trail`, `/reports/*`, `/mnt/{id}/upload`,
  `/mnt/{id}/extraire-bassins`, `/mnt/{id}/bassins`, `/mnt/{id}/profil-long`,
  `/sync/pull` (remplacé par `/sync/delta`), `/api/v1/health` (→ `/health`) ;
- WebSocket réel : `/api/v1/jobs/ws/{job_id}` (et non `/ws/*`).
