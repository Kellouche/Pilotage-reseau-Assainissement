# Dossier de lot A1 + D0 — Isolation multi-tenant & correctifs mobiles bloquants

> **Statut** : proposition soumise à validation — **aucune ligne de code applicatif n'a été écrite**
> **Référence de base** : `master` @ `8296de7` (2026-11-18)
> **Périmètre** : `api/`, `tests/`, `mobile/`, `static/js/`
> **Hors périmètre** : `src/domain/` (moteur SWMM), `docs/PROMPT_DWF_RESTANT.md` et les fichiers
> actuellement modifiés non commités (`api/routes/aux_layers.py`, `api/services/aux_altimetrie_service.py`,
> `tests/test_aux_layers.py`) — **le lot ne les touche pas**.
> **Date** : 18 novembre 2026

---

## Légende de fiabilité

Tout au long de ce dossier, chaque affirmation est marquée :

| Marque | Signification |
|---|---|
| **[P]** | **Prouvé** — mesuré par exécution ou extraction AST sur le dépôt, commande reproductible en annexe |
| **[L]** | **Lu** — constaté par lecture de code, référence `fichier:ligne` fournie |
| **[E]** | **Estimé** — jugement d'ingénieur, fiabilité ±50 % (charges, risques) |

Les chiffres de ce dossier ont été recalculés à la main après la remise en cause du rapport précédent.
Les corrections par rapport à la première version sont listées en §12.

---

## 0. Résumé pour décision

**Le problème en une phrase** : 68 surfaces HTTP/WS répondent aujourd'hui sans savoir à quelle organisation
elles appartiennent, et certaines renvoient explicitement les données de la première organisation
trouvée en base. **[P]**

**Ce que le lot fait** : il rend la résolution du tenant **obligatoire et non contournable**, applique la
règle *stealth 404*, et répare les défauts mobiles qui détruisent des données aujourd'hui. **[L]**

**Ce qu'il ne fait pas** : il ne durcit pas les jetons (A2), ne change pas les migrations (A6), n'ajoute
pas de CI (A7/A12), ne refactorise pas `simulations.py` (B1).

**Charge** : **11 jours** (A1 = 8 j dont 1,5 j de partitionnement du stockage des bassins manuels
et 0,5 j de suppression de `server.py`, D0 = 3 j), soit **12 jours ouvrés** avec la revue. **[E]**

> [!IMPORTANT]
> La charge A1 passe de 7,5 à 8 j par rapport à la version précédente : `server.py` est promu
> en prérequis bloquant (il exposait les mêmes routes sans auth sur port Flask indépendant) et
> les résolveurs paramétrés sont ventilés par niveau de complexité — ce qui révèle 0,5 j de
> dérive potentielle identifiée a priori.

**Risque de régression mesuré** : **1 test existant** à adapter sur 535. **[P]**

### Quatre décisions sont nécessaires avant d'écrire du code

1. **Matrice des rôles** (§3.2 pour les deux cas litigieux, grille complète au §4.2) — notamment :
   `POST /qualite/export-csv` et `POST /simulations/pluviometrie/bms-preview` sont-ils `viewer` ou `engineer` ?
2. **Sort des surfaces mortes** (§3.4) — supprimer les 3 alias `/api/v1/manual-basin` (en repointant
   `dessin_manuel.js` vers `/api/v1/clusters/manual-basin`) et `/ws/sync` (code mort) ?
   Le stockage JSON global des bassins manuels doit de toute façon être partitionné par organisation.
3. **`clusters.py` — doublon `GET /recalculate-all`** (§3.2) — la seconde déclaration (`:205`) est
   identique à la première (`:153`, `include_in_schema=False`) et inatteignable : faut-il la
   **supprimer** ou la **renommer** `/recalculate-all/async` pour en faire un alias explicite ?
4. **Mode d'authentification mobile** (§6.2) — login mot de passe + jeton sécurisé (recommandé, 2 j),
   ou appairage par code à usage unique (plus sûr, +4 j et un endpoint backend) ?

---

## 1. Ce que le lot change exactement

| Axe | Avant | Après |
|---|---|---|
| Résolution du tenant | Optionnelle, parfois absente, parfois silencieusement remplacée par « première organisation en base » | `Depends(get_tenant_context)` obligatoire sur toute route non explicitement publique |
| Filtrage des données | `org_id` passé à `None` sur la majorité des lectures | `org_id` **obligatoire** dans `crud.py` ; plus aucun fallback global |
| Objet d'une autre organisation | 200 avec les données, ou 403 | **404 furtif**, corps et en-têtes identiques à un identifiant inexistant |
| Identité de l'acteur | `user_id` en paramètre de requête, `"system"`, `"agent_terrain"` | Acteur déduit du jeton uniquement, journalisé tel quel |
| WebSocket jobs | `job_id` suffit | Jeton exigé + contrôle `org_id` |
| Bassins manuels | Fichier unique `data/manual_overrides.json` partagé par toutes les organisations | Stockage partitionné par `org_id`, routes namespacées sous `/clusters` |
| API Flask parallèle | `server.py` exposé, non authentifié, `README.md` le cite | **Archivé dans `legacy/`** avant J2 : prérequis bloquant |
| Mobile | Aucune authentification, perte des relevés rejetés | Jeton sécurisé, push transactionnel, permissions Android |
| Garde-fou | Aucun test ne détecte une route orpheline | Test qui parcourt `app.routes` et échoue si une route non autorisée n'a pas de dépendance tenant |

---

## 2. Constat de référence (chiffres vérifiés)

| Indicateur | Valeur | Marque |
|---|---|---|
| Routes déclarées dans `api/routes/*.py` | **149** | [P] |
| Routes avec dépendance tenant/role | **79** | [P] |
| Routes sans aucune dépendance tenant | **61** (dont 7 publiques légitimes) | [P] |
| Routes en contexte **optionnel** (anonyme accepté) | **9** | [P] |
| **Surfaces de routeur à traiter** | **63** (54 + 9) | [P] |
| Surfaces définies directement sur `app` (`api/main.py`) | **6** (dont 1 alias en doublon) | [P] |
| **Total surfaces distinctes à traiter** | **68** | [P] |
| Routes paramétrées nécessitant un résolveur d'objet | **18** | [P] |
| Fichiers JS appelant une de ces routes | **18**, dont **11 sans jeton** | [P] |
| Appels métier du mobile | **11**, dont **0 authentifié** | [P] |
| Tests de la suite | **535 passed en 5 min 42** | [P] |
| Fichiers de test utilisant `TestClient` | **12** (147 appels HTTP) | [P] |
| Tests existants cassés par A1 | **1** (`test_bms_simulation.py:18`) | [P] |
| `dependency_overrides` dans les tests | **0** | [P] |

### 2.1 Les quatre fuites démontrées par lecture

**Fuite 1 — `GET /api/v1/layers` (mobile + carte web)**
`api/main.py:434-441` : si la requête n'est pas authentifiée, le code prend le **premier projet
non archivé de la base, toutes organisations confondues** :

```python
if not gpkg_target and not user and db:
    project = db.query(Project).filter(Project.is_archived.is_(False)).first()
```

Aucun filtre `org_id`. C'est l'endpoint que le mobile appelle en premier (`api_service.dart:26`). **[L]**

**Fuite 2 — `GET /api/v1/sync/delta`**
`api/routes/sync.py:44` appelle `crud.get_changes_since(db, table, since_version + 1)` **sans** `org_id`,
alors que `crud.get_changes_since` accepte un `org_id` optionnel (`api/crud.py:501-505`) :
la signature autorise le filtrage, l'appel l'omet. Le delta contient donc les modifications de tous
les tenants. **[L]**

**Fuite 3 — `POST /api/v1/network/load-dataset/{dataset_id}`**
`api/routes/network.py:366-368` : sans jeton, l'endpoint choisit `db.query(Organization).first()`
et **écrit** le jeu de données dans le premier projet de cette organisation. Écriture inter-tenant
déclenchée anonymement. **[L]**

**Fuite 4 — `/api/v1/manual-basin` (3 alias + doublon Flask)**
`api/main.py:647-663` délègue à `src/infrastructure/persistance_manuelle.py`, qui lit et écrit un
fichier unique `data/manual_overrides.json` (`:15-17`), **sans aucune notion d'organisation ni de projet**.
Lecture, écriture et suppression inter-tenant, sans authentification. **[L]**

La même API Flask (`server.py:90-98`) expose les mêmes routes (`/api/v1/manual-basin`, `/api/v1/layers`,
`/api/v1/cluster`) **sans authentification sur un port indépendant** et lit les mêmes fichiers de données.
`README.md` documente encore ce point d'entrée. **[L]**

> À noter : la variante `POST /api/v1/clusters/recalculate-all` (`api/routes/clusters.py:169-201`)
> résout le projet via `user.memberships[0]` puis retombe sur `Project.first()` global. Même schéma. **[L]**

---

## 3. Inventaire nominatif des 68 surfaces

### 3.1 Répartition par routeur

| Routeur | Total | Protégées | Sans contexte | Contexte optionnel | À traiter |
|---|---:|---:|---:|---:|---:|
| `api/routes/admin.py` | 5 | 5 | 0 | 0 | 0 |
| `api/routes/apports.py` | 11 | 11 | 0 | 0 | 0 |
| `api/routes/artifacts.py` | 1 | 1 | 0 | 0 | 0 |
| `api/routes/audit.py` | 4 | 4 | 0 | 0 | 0 |
| `api/routes/auth.py` | 13 | 6 | 7 | 0 | 0 |
| `api/routes/aux_layers.py` | 11 | 11 | 0 | 0 | 0 |
| `api/routes/clusters.py` | 13 | 0 | 13 | 0 | 13 |
| `api/routes/corrections.py` | 5 | 0 | 5 | 0 | 5 |
| `api/routes/extractions.py` | 1 | 1 | 0 | 0 | 0 |
| `api/routes/garde_fou.py` | 3 | 3 | 0 | 0 | 0 |
| `api/routes/jobs.py` | 3 | 2 | 1 | 0 | 1 |
| `api/routes/licensing.py` | 5 | 5 | 0 | 0 | 0 |
| `api/routes/mnt.py` | 4 | 0 | 4 | 0 | 4 |
| `api/routes/network.py` | 21 | 4 | 12 | 5 | 17 |
| `api/routes/organization.py` | 3 | 3 | 0 | 0 | 0 |
| `api/routes/qualite.py` | 10 | 0 | 6 | 4 | 10 |
| `api/routes/simulations.py` | 27 | 22 | 5 | 0 | 5 |
| `api/routes/sync.py` | 3 | 1 | 2 | 0 | 2 |
| `api/routes/terrain.py` | 6 | 0 | 6 | 0 | 6 |
| **Total** | **149** | **79** | **61** | **9** | **63** |

Les 7 routes `auth.py` sans dépendance sont **légitimement publiques** : `check-email`, `register`,
`verify-email`, `resend-code`, `login`, `refresh`, `logout`.

### 3.2 Les 54 routes sans aucune dépendance tenant

| # | Fichier:ligne | Méthode | URL montée | Fonction | Rôle proposé |
|---:|---|---|---|---|---|
| 1 | `clusters.py:130` | GET | `/api/v1/clusters` | `list_clusters` | viewer |
| 2 | `clusters.py:138` | GET | `/api/v1/clusters/status` | `get_cluster_status` | viewer |
| 3 | `clusters.py:144` | POST | `/api/v1/clusters/graph/rebuild` | `rebuild_graph_cache` | admin |
| 4 | `clusters.py:153` | GET | `/api/v1/clusters/recalculate-all` | `recalculate_all_clusters_async_precedence` | admin |
| 5 | `clusters.py:160` | GET | `/api/v1/clusters/{cluster_id}` | `get_cluster` | viewer |
| 6 | `clusters.py:169` | POST | `/api/v1/clusters/recalculate-all` | `recalculate_all_clusters` | admin |
| 7 | `clusters.py:205` | GET | `/api/v1/clusters/recalculate-all` | `recalculate_all_clusters_async` | admin — **DOUBLON INATTEIGNABLE** ✦ |
| 8 | `clusters.py:754` | POST | `/api/v1/clusters/{cluster_id}/recalculate` | `recalculate_cluster` | engineer |
| 9 | `clusters.py:763` | GET | `/api/v1/clusters/{cluster_id}/geojson` | `export_cluster_geojson` | viewer |
| 10 | `clusters.py:822` | GET | `/api/v1/clusters/{cluster_id}/ouvrages-proches` | `get_cluster_ouvrages_proches` | viewer |
| 11 | `clusters.py:845` | POST | `/api/v1/clusters/manual-basin` | `save_cluster_manual_basin` | admin |
| 12 | `clusters.py:852` | DELETE | `/api/v1/clusters/manual-basin/{bassin_id}` | `delete_cluster_manual_basin` | admin |
| 13 | `clusters.py:860` | GET | `/api/v1/clusters/manual-basin` | `get_cluster_manual_basins` | admin |
| 14 | `corrections.py:100` | POST | `/api/v1/corrections/manuel/{fid}` | `correction_manuelle` | engineer |
| 15 | `corrections.py:129` | GET | `/api/v1/corrections/hybride/suggestable_fids` | `suggestable_fids` | viewer |
| 16 | `corrections.py:171` | GET | `/api/v1/corrections/hybride/suggest` | `suggestion_hybride` | viewer |
| 17 | `corrections.py:418` | GET | `/api/v1/corrections/profile/{fid}` | `profil_conduite` | viewer |
| 18 | `corrections.py:563` | POST | `/api/v1/corrections/automatique` | `correction_automatique` | engineer |
| 19 | `jobs.py:72` | WEBSOCKET | `/api/v1/jobs/ws/{job_id}` | `websocket_job_progress` | engineer |
| 20 | `mnt.py:36` | POST | `/api/v1/mnt/analyser-bassins` | `analyser_bassins_mnt` | engineer |
| 21 | `mnt.py:141` | GET | `/api/v1/mnt/cache/status` | `get_cache_mnt_status` | admin |
| 22 | `mnt.py:169` | DELETE | `/api/v1/mnt/cache` | `clear_cache_mnt` | admin |
| 23 | `mnt.py:183` | GET | `/api/v1/mnt/statut` | `get_mnt_statut` | viewer |
| 24 | `network.py:57` | GET | `/api/v1/network/regards` | `list_regards` | viewer |
| 25 | `network.py:82` | GET | `/api/v1/network/regards/{regard_id}` | `get_regard` | viewer |
| 26 | `network.py:91` | POST | `/api/v1/network/regards` | `create_regard` | engineer |
| 27 | `network.py:107` | PATCH | `/api/v1/network/regards/{regard_id}` | `update_regard` | engineer |
| 28 | `network.py:130` | DELETE | `/api/v1/network/regards/{regard_id}` | `delete_regard` | engineer |
| 29 | `network.py:143` | GET | `/api/v1/network/conduites` | `list_conduites` | viewer |
| 30 | `network.py:160` | GET | `/api/v1/network/conduites/{conduite_id}` | `get_conduite` | viewer |
| 31 | `network.py:169` | POST | `/api/v1/network/conduites` | `create_conduite` | engineer |
| 32 | `network.py:187` | PATCH | `/api/v1/network/conduites/{conduite_id}` | `update_conduite` | engineer |
| 33 | `network.py:210` | DELETE | `/api/v1/network/conduites/{conduite_id}` | `delete_conduite` | engineer |
| 34 | `network.py:223` | GET | `/api/v1/network/rejets` | `list_rejets` | viewer |
| 35 | `network.py:231` | POST | `/api/v1/network/rejets` | `create_rejet` | engineer |
| 36 | `qualite.py:165` | GET | `/api/v1/qualite/diagnostic` | `diagnostic_tunnel` | viewer |
| 37 | `qualite.py:304` | POST | `/api/v1/qualite/valider-incremental` | `valider_incremental` | engineer |
| 38 | `qualite.py:326` | GET | `/api/v1/qualite/scores-bassins` | `get_scores_qualite_par_bassin` | viewer |
| 39 | `qualite.py:446` | POST | `/api/v1/qualite/export-csv` | `exporter_anomalies_csv` | engineer \* |
| 40 | `qualite.py:476` | GET | `/api/v1/qualite/cache/status` | `get_cache_status` | admin |
| 41 | `qualite.py:504` | DELETE | `/api/v1/qualite/cache` | `clear_cache` | admin |
| 42 | `simulations.py:455` | GET | `/api/v1/simulations/typologies-sol` | `get_simulation_typologies_sol` | viewer |
| 43 | `simulations.py:474` | GET | `/api/v1/simulations/pluviometrie/referentiel` | `get_pluviometrie_referentiel` | viewer |
| 44 | `simulations.py:488` | GET | `/api/v1/simulations/pluviometrie/stations` | `get_pluviometrie_stations` | viewer |
| 45 | `simulations.py:495` | GET | `/api/v1/simulations/scenarios` | `get_simulation_scenarios` | viewer |
| 46 | `simulations.py:547` | POST | `/api/v1/simulations/pluviometrie/bms-preview` | `preview_bms_scenario` | engineer \* |
| 47 | `sync.py:29` | GET | `/api/v1/sync/delta` | `get_delta` | viewer |
| 48 | `sync.py:278` | POST | `/api/v1/sync/session` | `register_sync_session` | admin |
| 49 | `terrain.py:27` | POST | `/api/v1/terrain/inspections` | `create_inspection` | engineer |
| 50 | `terrain.py:50` | GET | `/api/v1/terrain/inspections` | `list_inspections` | viewer |
| 51 | `terrain.py:60` | GET | `/api/v1/terrain/inspections/{object_type}/{object_id}` | `get_inspections_for_object` | viewer |
| 52 | `terrain.py:77` | POST | `/api/v1/terrain/incidents` | `create_incident` | engineer |
| 53 | `terrain.py:100` | GET | `/api/v1/terrain/incidents` | `list_incidents` | viewer |
| 54 | `terrain.py:110` | PATCH | `/api/v1/terrain/incidents/{incident_id}` | `update_incident_status` | engineer |

\* **Décision n°1** : `export-csv` est une lecture déguisée en POST (viewer suffit probablement) et
`bms-preview` est un calcul lourd sans écriture (viewer possible, mais consomme du CPU → quota).
Votre arbitrage est nécessaire.

**Décision n°3** : la ligne `:205` (`recalculate_all_clusters_async`) est identique à la ligne `:153`
(`recalculate_all_clusters_async_precedence`, `include_in_schema=False`) et est **physiquement inatteignable**
car Starlette sert la première correspondance. Les deux fonctions exécutent `background_tasks.add_task(_calculate_clusters_background)` et retournent `{"status": "scheduled"}` à l'identique. Choix :
(a) supprimer `:205`, ou (b) renommer `/recalculate-all/async` pour en faire un alias explicite et documenté.

### 3.3 Les 9 routes en contexte optionnel (le cas le plus insidieux)

Elles *semblent* protégées : elles appellent `get_tenant_context_optional`, qui **retourne `None`**
au lieu de lever une erreur quand l'authentification échoue (`api/core/security.py:184-189`).
Un anonymous est donc traité comme un utilisateur valide, et la route retombe sur un projet global.

| # | Fichier:ligne | Méthode | URL montée | Fonction | Rôle proposé |
|---:|---|---|---|---|---|
| 1 | `network.py:355` | GET | `/api/v1/network/datasets` | `list_available_datasets` | viewer (ou public statique) |
| 2 | `network.py:392` | POST | `/api/v1/network/load-dataset/{dataset_id}` | `load_benchmark_dataset` | admin |
| 3 | `network.py:744` | GET | `/api/v1/network/subcatchments` | `get_network_subcatchments` | viewer |
| 4 | `network.py:878` | GET | `/api/v1/network/orphelins/geojson` | `get_network_orphelins_geojson` | viewer |
| 5 | `network.py:926` | GET | `/api/v1/network/export/inp` | `export_network_inp` | viewer |
| 6 | `qualite.py:110` | GET | `/api/v1/qualite/analyse` | `analyser_qualite_reseau` | viewer |
| 7 | `qualite.py:201` | GET | `/api/v1/qualite/anomalies/{type_anomalie}` | `get_anomalies_par_type` | viewer |
| 8 | `qualite.py:250` | GET | `/api/v1/qualite/scores` | `get_scores_qualite` | viewer |
| 9 | `qualite.py:277` | GET | `/api/v1/qualite/statistiques` | `get_statistiques_reseau` | viewer |

**Décision n°2a** : conserver `get_tenant_context_optional` uniquement pour
`GET /network/datasets` (catalogue statique de 5 entrées) et le **supprimer partout ailleurs**.

### 3.4 Les 6 surfaces définies hors routeurs (`api/main.py`)

| Fichier:ligne | Méthode | URL | Situation | Action proposée |
|---|---|---|---|---|
| `main.py:373` | GET | `/api/v1/layers` | Optionnel + fallback `Project.first()` global (`:434`) | Contexte tenant **obligatoire** |
| `main.py:647` | POST | `/api/v1/manual-basin` | Aucune auth + stockage JSON global | **Alias supprimé** ; `dessin_manuel.js` repointé vers `/api/v1/clusters/manual-basin` |
| `main.py:653` | DELETE | `/api/v1/manual-basin/{bassin_id}` | Idem | **Alias supprimé** |
| `main.py:659` | GET | `/api/v1/manual-basin` | Idem | **Alias supprimé** (aucun appelant vivant) |
| `main.py:550` | WS | `/ws/sync` | Aucune auth ; utilisé uniquement par `static/js/map/map_notifications.js` (code mort) | **Supprimer** |
| `main.py:667` | WS | `/ws/jobs/{job_id}` | Alias de `jobs.py:72`, lui-même non protégé | **Supprimer l'alias**, sécuriser l'original |

**Point d'attention découvert en vérification finale** : les trois routes `/clusters/manual-basin`
(`api/routes/clusters.py:844-863`) sont, elles aussi, de simples délégations à
`persistance_manuelle.py`, qui écrit dans **un fichier unique** (`src/infrastructure/persistance_manuelle.py:15-17`).
Sécuriser l'authentification ne suffit donc pas : un `admin` de B lirait les bassins de A.
Le lot doit **partitionner le stockage** : `data/manual_overrides/{org_id}.json`, avec `org_id`
passé explicitement.

**Décision n°2b** : validez-vous (a) la suppression des 3 alias et de `/ws/sync`, (b) le repointage de
`dessin_manuel.js` vers les routes `/clusters`, et (c) le partitionnement du stockage des bassins manuels ?

### 3.5 `server.py` — porte dérobée Flask (prérequis bloquant, pas point annexe)

> [!CAUTION]
> `server.py` est une **API Flask parallèle non authentifiée** qui expose 7 routes sur un port
> indépendant, dont `/api/v1/layers`, `/api/v1/manual-basin` et `/api/v1/cluster`, **lisant et
> écrivant les mêmes fichiers de données** que l'API FastAPI. `README.md` documente encore ce
> point d'entrée (`README.md:L??`). Il doit être **archivé dans `legacy/` en J1, avant toute
> modification des routes FastAPI**, sinon l'isolation multi-tenant peut être contournée
> trivialement pendant tout le lot. Ce n'est pas un point annexe : c'est un vecteur d'attaque actif.

Action J1 (bloquante avant J2) :
1. Déplacer `server.py` → `legacy/server_flask_archive.py` avec un commentaire d'en-tête daté.
2. Corriger `README.md` : remplacer la section "Lancer server.py" par un renvoi vers `api/main.py`.
3. Vérifier qu'aucun `Makefile`, `docker-compose.yml` ou script CI ne lance `server.py`. **[L]** (aucun trouvé à ce stade)

### 3.6 Les 18 routes paramétrées — résolveurs ventilés par complexité

La matrice de tests a besoin d'un **registre de résolveurs** : pour chaque gabarit d'URL, une fonction
qui retourne un identifiant valide pour l'organisation A et un identifiant appartenant à B.

> [!WARNING]
> Écrire un résolveur `{id} → org_id` n'est pas linéaire. La complexité dépend du nombre de
> JOIN nécessaires pour remonter à l'organisation propriétaire. Les 18 résolveurs sont classés
> en trois niveaux ci-dessous. L'estimation initiale « ≈ 1 jour » s'applique uniquement au
> niveau simple ; les niveaux moyen et complexe ajoutent **0,5 j supplémentaire** (comptabilisé
> dans la charge révisée).

| Niveau | Critère | Résolveurs concernés | Charge |
|---|---|---|---|
| **Simple** | L'entité porte directement `org_id` ou `project_id → org_id` en 1 JOIN | `cluster_id`, `regard_id`, `conduite_id`, `bassin_id`, `type_anomalie` (enum fermée, pas de JOIN) | 0,5 j |
| **Moyen** | 2 JOIN ou résolution via membership utilisateur | `dataset_id` (`load-dataset` → org via membership), `job_id` (via simulation → projet → org), `incident_id`, `sim_a/job_a` | 0,5 j |
| **Complexe** | Paramètre composite ou entité non normalisée | `fid` (identifiant GPKG, pas en base SQL), `object_type/{object_id}` (deux paramètres, type polymorphe) | 0,5 j |

**Total résolveurs : 1,5 j** (au lieu de 1 j dans la version précédente — dérive identifiée en amont).

| URL | Méthode | Paramètre(s) | Niveau |
|---|---|---|---|
| `/api/v1/clusters/{cluster_id}` | GET | `cluster_id` | Simple |
| `/api/v1/clusters/{cluster_id}/recalculate` | POST | `cluster_id` | Simple |
| `/api/v1/clusters/{cluster_id}/geojson` | GET | `cluster_id` | Simple |
| `/api/v1/clusters/{cluster_id}/ouvrages-proches` | GET | `cluster_id` | Simple |
| `/api/v1/clusters/manual-basin/{bassin_id}` | DELETE | `bassin_id` | Simple |
| `/api/v1/network/regards/{regard_id}` | GET/PATCH/DELETE | `regard_id` | Simple |
| `/api/v1/network/conduites/{conduite_id}` | GET/PATCH/DELETE | `conduite_id` | Simple |
| `/api/v1/qualite/anomalies/{type_anomalie}` | GET | `type_anomalie` (enum fermée) | Simple |
| `/api/v1/network/load-dataset/{dataset_id}` | POST | `dataset_id` | Moyen |
| `/api/v1/jobs/ws/{job_id}` | WS | `job_id` | Moyen |
| `/api/v1/terrain/incidents/{incident_id}` | PATCH | `incident_id` | Moyen |
| `/api/v1/corrections/manuel/{fid}` | POST | `fid` | Complexe |
| `/api/v1/corrections/profile/{fid}` | GET | `fid` | Complexe |
| `/api/v1/terrain/inspections/{object_type}/{object_id}` | GET | 2 paramètres | Complexe |

---

## 4. Modèle de protection cible

### 4.1 Règles de résolution (non négociables)

1. **Une route non listée dans l'allowlist publique doit déclarer** `ctx: TenantContext = Depends(get_tenant_context)`.
2. `ctx.org_id` est **obligatoire** dans toutes les fonctions de `crud.py` : suppression des valeurs par défaut
   `Optional[str] = None` sur les lectures (`api/crud.py:77,103,138,182,229,247,282,324,358,418`).
3. **Aucun `Project.first()` / `Organization.first()` sans filtre `org_id`** ne doit subsister.
   Un test de garde fait échouer la suite si le motif réapparaît.
4. `org_id` **n'est jamais** lu depuis la query string. Seul l'en-tête `X-Organization-Id` est accepté,
   et uniquement s'il correspond à une `Membership` réelle (sinon **404**, pas 403).
5. L'identité de l'acteur vient **exclusivement** du jeton. Disparition de `user_id: str = "system"`
   en paramètre de requête (`api/routes/network.py:91,130,210`) et de `"agent_terrain"` codé en dur
   (`api/routes/terrain.py:30`).
6. Le `refresh_token` **n'est plus** accepté comme jeton d'accès (`api/core/security.py:85-86`) —
   c'est un correctif de 3 lignes qui relève de A1 car il rend la matrice de tests fausse.
7. **Aucun stockage de données métier hors base sans clé d'organisation** : le fichier
   `data/manual_overrides.json` devient `data/manual_overrides/{org_id}.json`, et les fonctions de
   `persistance_manuelle.py` reçoivent `org_id` en paramètre obligatoire.

### 4.2 Rôles proposés

| Rôle | Périmètre |
|---|---|
| `viewer` | Toutes les lectures : réseau, clusters, qualité, MNT (statut), simulations (lecture), terrain (lecture), layers |
| `engineer` | Écritures réseau, corrections, validation qualité, inspections/incidents, push de synchronisation, previews de calcul |
| `admin` | Purges de cache, reconstruction de graphe, recalcul global, bassins manuels, chargement de jeu de données, enregistrement de session de synchronisation |
| `superadmin` | Console opérateur, jeu de données « ville complète » |

Mapping verbe → rôle par défaut : `GET` → `viewer`, `POST/PUT/PATCH/DELETE` → `engineer`,
sauf les 12 routes marquées `admin` au §3.2/§3.3 (heuristique sur le chemin : `cache`, `rebuild`,
`manual-basin`, `load-dataset`, `recalculate-all`, `session`).

### 4.3 Stealth 404 — spécification testable

| Situation | Statut | Corps |
|---|---|---|
| Objet inexistant | 404 | `{"detail": "Ressource introuvable"}` |
| Objet d'une autre organisation | 404 | **strictement identique** |
| `X-Organization-Id` d'une org non membre | 404 | identique |
| Rôle insuffisant **sur sa propre org** | 403 | `{"detail": "Privilèges insuffisants"}` |

Interdiction de renvoyer 403 pour un objet d'une autre organisation : 403 confirme l'existence.
Le test compare le corps **et** les en-têtes des deux réponses 404. **[E]** (comparaison de timing
hors périmètre : elle exigerait un banc dédié).

### 4.4 Allowlist publique (figée dans le code et testée)

```
POST /auth/register, POST /auth/login, POST /auth/refresh, POST /auth/logout,
GET  /auth/check-email, POST /auth/verify-email, POST /auth/resend-code,
GET  /health, GET /api/info, GET /api/v1/network/datasets (si décision n°2a validée),
GET / (pages HTML : /login, /register, /cockpit, /carte, /tunnel, /pricing),
GET /favicon.ico
```

Toute autre route sans dépendance tenant fait **échouer la CI**.

---

## 5. Matrice de tests cross-org

### 5.1 Jeu de données de test

Deux organisations complètes, créées par fixture :

| Objet | Org A | Org B |
|---|---|---|
| Organisation | `org_a` (plan `pro`) | `org_b` (plan `pro`) |
| Utilisateurs | `admin_a`, `engineer_a`, `viewer_a` | `admin_b` |
| Projet + GPKG | `projet_a` (58 conduites) | `projet_b` (3 conduites, valeurs distinctes) |
| Réseau | 1 regard, 1 conduite, 1 rejet identifiables | idem, **identifiants distincts** |
| Cluster | `cluster_a` | `cluster_b` |
| Simulation + Job | `sim_a`, `job_a` (terminé) | `sim_b`, `job_b` |
| Terrain | 1 inspection, 1 incident | idem |
| Clé API | `sp_live_` scope `read` et `write` | — |

**Astuce de détection** : les valeurs métier diffèrent (58 vs 3 conduites). Toute réponse contenant
`58` à un acteur de B est une fuite, sans ambiguïté d'interprétation.

### 5.2 Matrice générique — 12 cas, appliqués aux 63 surfaces conservées

> Les 5 surfaces supprimées (3 alias `/manual-basin`, `/ws/sync`, alias `/ws/jobs`) ne sont pas
> testées en isolation mais par un **test d'absence** : elles doivent renvoyer 404 après le lot.

| # | Acteur | Requête | Attendu |
|---:|---|---|---|
| 1 | anonyme | sans en-tête | **401** (+ `WWW-Authenticate`) |
| 2 | `viewer_a` | GET | 200 |
| 3 | `viewer_a` | POST/PATCH/DELETE | **403** |
| 4 | `engineer_a` | écriture | 200/201 |
| 5 | `admin_a` | purge/recalcul/chargement | 200 |
| 6 | `viewer_b` | GET objet de A | **404** |
| 7 | `engineer_b` | PATCH/DELETE objet de A | **404**, et **aucune mutation** en base |
| 8 | `engineer_b` | POST création | 201, `org_id == org_b` **jamais** `org_a` |
| 9 | superadmin | GET objet de A | 200 |
| 10 | clé API `read` | écriture | **403** |
| 11 | jeton expiré | GET | **401** |
| 12 | `refresh_token` en `Bearer` | GET | **401** |

**Volume** : 63 × 4 cas critiques (1, 6, 7, 8) = **252 assertions**, plus 63 × 8 cas restants
sur un échantillon de 12 routes représentatives = **96 assertions**. Total ≈ **348 assertions générées
par paramétrage**, plus 6 tests WS dédiés et 5 tests d'absence. **[E]** sur le volume, **[P]** sur la
liste des routes.

### 5.3 Cas spécifiques non couverts par la matrice générique

| Test | Assertion |
|---|---|
| `/api/v1/layers` anonyme | **401** ; avec `viewer_b` → compteurs de B, jamais 58 |
| `/api/v1/sync/delta` avec `engineer_b` | aucun identifiant de A dans `changes` |
| `/api/v1/network/load-dataset/{id}` anonyme | 401 ; `engineer_b` → écrit dans `projet_b` uniquement |
| `/api/v1/manual-basin` (si conservé) | 404 pour B sur un bassin de A |
| Bassins manuels — stockage | un bassin créé par A n'apparaît **jamais** dans `data/manual_overrides/org_b.json` ni dans la liste renvoyée à B |
| WS `/api/v1/jobs/ws/{job_a}` avec jeton B | fermeture immédiate, aucun message de progression |
| Journal d'audit | `audit_logs.user_id` = identifiant réel, **jamais** `"system"` |
| Requête avec `?org_id=org_b` | paramètre ignoré (aucun changement d'org) |
| `server.py` archivé | `GET http://localhost:5002/api/v1/layers` → connexion refusée (port fermé) |

### 5.4 Le test de garde (le plus important)

Un test qui **parcourt `app.routes`** et échoue si une route hors allowlist n'a pas de dépendance
tenant. Sans lui, la faille revient au prochain endpoint ajouté. C'est le seul livrable qui garantit
la durabilité du lot. **[P]** (faisabilité : `route.dependant.dependencies` expose les dépendances).

---

## 6. Stratégie de compatibilité mobile (D0)

### 6.1 État exact et ce qui casse

| # | Appel mobile | Fichier:ligne | Après A1 | Action D0 |
|---:|---|---|---|---|
| 1 | `GET /api/v1/layers` | `api_service.dart:26` | **401** | Jeton + org |
| 2 | `PATCH /network/conduites/{id}` | `api_service.dart:41` | **401** | Jeton |
| 3 | `POST /terrain/inspections` | `map_screen.dart:334` | **401** | Jeton |
| 4 | `POST /terrain/incidents` | `map_screen.dart:722` | **401** | Jeton |
| 5 | `GET /qualite/scores-bassins` | `api_service.dart:65` | **401** | Jeton |
| 6 | `POST /qualite/valider-incremental` | `api_service.dart:75` | **401** | Jeton |
| 7 | `GET /clusters/{id}/geojson` | `api_service.dart:87` | **401** | Jeton |
| 8 | `POST /mnt/analyser-bassins` | `api_service.dart:97` | **401** | Jeton |
| 9 | `GET /sync/delta` | `api_service.dart:117` | **401** | Jeton |
| 10 | `POST /sync/push` | `api_service.dart:127` | **401** | Jeton |
| 11 | `POST /sync/session` | `api_service.dart:139` | **401** | Jeton |
| 12 | `GET /health` | `api_service.dart:145` | 200 | — |

**11 appels sur 12 cessent de fonctionner.** C'est l'argument décisif pour livrer A1 et D0 ensemble.

### 6.2 Trois options d'authentification mobile

| Option | Principe | Charge | Avantages | Inconvénients |
|---|---|---:|---|---|
| **A. Login + jeton sécurisé** *(recommandée)* | Écran de connexion réutilisant `POST /auth/login`, jeton dans `flutter_secure_storage`, intercepteur HTTP centralisé | **2 j** | Aucun endpoint backend nouveau ; identité réelle dans l'audit | Mot de passe saisi sur le terrain ; jeton de 7 j à protéger |
| B. Appairage par code | L'agent génère un code depuis le web, le saisit une fois sur le mobile ; le serveur émet un jeton d'appareil | 3 j + 1 j backend | Meilleure UX terrain, révocation par appareil | Nécessite une table `device_tokens` et une migration → sort du périmètre A1 |
| C. Clé API embarquée | `sp_live_` dans le binaire | 0,5 j | Trivial | **Rejetée** : secret extractible de l'APK, aucune identité d'acteur, révocation globale |

> [!WARNING]
> L'option A est estimée à **2 j** (et non 1,5 j dans la version précédente). La raison :
> `api_service.dart` n'a **aucun intercepteur HTTP centralisé** — chaque méthode appelle
> `http.get`, `http.patch`, `http.post` directement avec ses propres `headers`. Ajouter
> `Authorization` et `X-Organization-Id` sur 11 appels dispersés, gérer le 401 → purge +
> redirect, et créer un `AuthInterceptor` Dio (ou équivalent) qui centralise les en-têtes
> représente un refactoring de la couche réseau, pas seulement un ajout de header.

**Recommandation** : A pour D0, B pour D1 (mobilité réelle). C est exclue.

Détail de l'option A :
- `mobile/lib/screens/login_screen.dart` (nouveau, ~150 lignes) ;
- **Refactoring de la couche réseau** : remplacement des appels `http.XXX` directs par un
  client centralisé (`AuthHttpClient`) injecté dans `ApiService` — portant `Authorization` et
  `X-Organization-Id` automatiquement sur chaque requête ;
- jeton dans `flutter_secure_storage` (ajout de dépendance) — **pas** dans `SharedPreferences` ;
- `GET /auth/me` (`api/routes/auth.py:507`) fournit les organisations de l'utilisateur → sélecteur
  d'organisation, puis en-tête `X-Organization-Id` sur chaque appel ;
- sur 401 : purge du jeton + retour à l'écran de connexion (pas de refresh en D0, voir décision n°4).

### 6.3 Correctifs D0 non liés à l'authentification

| # | Défaut | Preuve | Correctif | Charge |
|---:|---|---|---|---:|
| D0.1 | **Aucune permission Android** : pas d'Internet en release, pas de GPS, pas de caméra | `mobile/android/app/src/main/AndroidManifest.xml` : **0 `uses-permission`** | Ajouter `INTERNET`, `ACCESS_FINE_LOCATION`, `ACCESS_COARSE_LOCATION`, `CAMERA` ; `usesCleartextTraffic` limité au flavor debug | 2 h |
| D0.2 | **URL d'API triple et incohérente** | 5002 en dur (`api_service.dart:11-14`), 5001 dans `docs/MOBILE.md`, `EXPO_PUBLIC_*` dans `mobile/.env.example` (app Flutter, pas Expo) | Une seule variable `--dart-define=API_BASE_URL`, `.env.example` corrigé, défaut = URL de dev documentée | 2 h |
| D0.3 | **Perte de données au push** : `clearPendingChanges()` appelé **même si `rejected > 0`** | `mobile/lib/screens/sync_screen.dart:131` | Ne retirer que les `localId` acceptés ; conserver les rejetés avec leur motif ; ne jamais vider en bloc | 0,5 j |
| D0.4 | **Delta non incrémental** : `getDelta(0)` codé en dur, version jamais persistée | `sync_screen.dart:86` | Persister `version` retournée, la renvoyer au cycle suivant | 0,5 j |
| D0.5 | **Device ID codé en dur** (`'mobile-device-001'`, 3 emplacements) | `sync_screen.dart`, `home_screen.dart` | Générer un UUID persistant au premier lancement | 0,25 j |
| D0.6 | **Photos factices** (URLs Unsplash) | `fiche_terrain.dart:31-36`, `incident_form.dart:27-28` | Retirer ou marquer explicitement « photo non disponible » | 1 h |
| D0.7 | **Signature et identité de build** : `com.example.swmm_mobile`, release signé avec la clé debug, icônes de 75 octets | `mobile/android/app/build.gradle.kts`, `assets/` | Keystore release, `applicationId` réel, assets corrects | 0,5 j |

Le stockage local (SQLite chiffré, cache secteur, file de rejets, photos réelles) reste en **D1** :
c'est une refonte, pas un correctif.

### 6.4 Critères d'acceptation D0

- [ ] Un build **release** atteint le serveur (permission Internet effective).
- [ ] Un agent se connecte, voit son organisation, charge la carte.
- [ ] Un push partiellement rejeté conserve les relevés rejetés (test manuel documenté).
- [ ] Le second cycle de synchronisation n'envoie plus `since_version=0`.
- [ ] Aucune URL `127.0.0.1` en dur en dehors du défaut de développement.
- [ ] `flutter analyze` sans erreur ; **premier test unitaire** sur `SyncService` (mock HTTP).

---

## 7. Impact sur les 535 tests

### 7.1 Mesure

| Fichier de test | Appels HTTP | En-tête d'auth | Verdict |
|---|---:|---|---|
| `test_apports_dwf.py` | 16 | oui | intact (routeur déjà protégé) |
| `test_apports_dwf_reconcilier.py` | 4 | oui | intact |
| `test_apports_dwf_versions.py` | 15 | oui | intact |
| `test_p61_dwf_history.py` | 26 | oui | intact |
| `test_audit_security.py` | 16 | oui (9) | intact |
| `test_aux_layers.py` | 31 | oui | intact |
| `test_simulations_securite_p01.py` | 14 | oui | intact |
| `test_extraction_pochoir.py` | 8 | oui | intact |
| `test_demo_network.py` | 6 | oui | **à surveiller** (layers) |
| `test_hydrologie.py` | 5 | oui | **à surveiller** (subcatchments) |
| `test_coherence_snapshot_affichage.py` | 5 | oui | **à surveiller** (layers) |
| `test_async_jobs.py` | 1 | non | intact (teste justement le refus anonyme) |

**Conclusion [P]** : aucun test existant ne dépend d'un accès anonyme aux routes à protéger.
Les 8 appels HTTP concernés passent déjà `headers=headers`.

### 7.2 Le seul point de casse réel

`tests/test_bms_simulation.py:18` appelle **directement** la fonction de route :

```python
data = preview_bms_scenario(payload)
```

Après ajout du paramètre `ctx: TenantContext = Depends(...)`, l'appel passe un objet `Depends`
au lieu d'un contexte. **1 test à adapter** (fournir un faux `TenantContext`).
Aucun autre appel direct aux fonctions de route n'existe dans la suite. **[P]**

### 7.3 Risques résiduels (à vérifier pendant l'exécution)

| Risque | Probabilité | Parade |
|---|---|---|
| Un test crée un objet sans `org_id` (colonne nullable) et la nouvelle requête filtrée ne le voit plus | Moyenne | Rendre `org_id` obligatoire côté schéma serait une migration → **hors A1** ; à la place, les fixtures posent `org_id` explicitement. Test dédié sur les fixtures. |
| `crud.py` rendu obligatoire casse des appels internes hors routes (services, workers) | Moyenne | Recensement des appelants avant modification ; `grep -rn "crud\."` = 0 dans les tests |
| `/api/v1/layers` change de comportement pour un utilisateur multi-org (première membership) | Faible | Le test `test_demo_network` couvre le cas mono-org ; ajouter un test multi-org |
| La suite passe de 5 min 42 à ~7 min avec 368 assertions cross-org | Certaine | Marqueur `@pytest.mark.slow` + `pytest-xdist` (préparation de B7) |
| Les résolveurs de niveau "Complexe" (`fid`, `object_type/{object_id}`) prennent plus de temps que prévu | Moyenne | Ventilés en tâche dédiée J7 ; si dépassement, les 3 routes complexes sont temporairement exclues de la matrice paramétrée et testées manuellement |

### 7.4 Livrables de test

- `tests/test_tenant_matrix.py` — matrice générée (63 surfaces × 4 cas critiques).
- `tests/test_tenant_guard.py` — garde sur `app.routes` + allowlist.
- `tests/test_layers_isolation.py` — non-régression sur les 4 fuites démontrées.
- `tests/test_jobs_ws_isolation.py` — WebSocket cross-org.
- **Objectif** : 535 + ~120 tests (les 348 assertions sont regroupées en cas paramétrés),
  suite verte, durée < 8 min. **[E]**

---

## 8. Stratégie de rollback

> [!IMPORTANT]
> Toute modification de la couche d'authentification porte un risque de régression en production.
> Le lot A1 doit pouvoir être désactivé sans redéploiement en cas de comportement inattendu.

### 8.1 Principe : rollback par redéploiement, pas par interrupteur

Le lot **ne modifie aucun schéma SQL**. Le seul changement de données est la migration des fichiers
`manual_overrides.json` (J4), réversible par restauration du fichier sauvegardé. Le rollback nominal
est donc le **redéploiement de l'image précédente** (tag `pre-a1`), ou un `git revert` du commit de lot.

> [!WARNING]
> **Aucun flag ne doit désactiver la résolution du tenant.** Un `TENANT_ENFORCEMENT=false` qui
> renverrait un contexte synthétique rouvrirait les 68 surfaces — et s'il renvoie `role="admin"`,
> il transforme tout porteur de jeton en administrateur de toutes les organisations : c'est une
> **élévation de privilèges**, pas un mode dégradé.

Si un mode transitoire est indispensable pour l'observation, il est **fail-closed** :

```python
# api/core/security.py
_MODES = {"strict", "audit"}
MODE = os.getenv("TENANT_ENFORCEMENT", "strict").strip().lower()
if MODE not in _MODES:
    raise RuntimeError(f"TENANT_ENFORCEMENT invalide: {MODE!r} (attendu: {_MODES})")
```

| Mode | Comportement |
|---|---|
| `strict` (défaut) | Résolution obligatoire, 401/404 comme spécifié |
| `audit` | **Résolution identique** ; journalise `tenant_missing_org` quand une requête authentifiée n'a pas d'organisation résoluble. **N'accorde jamais d'accès supplémentaire.** |

Toute autre valeur (dont `false`, `0`, `off`) fait **échouer le démarrage** : une faute de frappe
en production ne peut pas ouvrir la plateforme.

### 8.2 Ordre de déploiement et point de non-retour

| Phase (§9) | Action | Rollback |
|---|---|---|
| J1 | Archivage `server.py`, allowlist publique, test de garde | Oui — aucune modification comportementale |
| J2–J6 | Protection des routeurs par lot (`network`, `clusters`, `corrections`, `qualite`, `mnt`, `sync`, `terrain`, `simulations`, WS, `/layers`) | Oui — `git revert` par routeur |
| J4 | Partitionnement `manual_overrides/{org_id}.json` + suppression des alias `main.py` et `/ws/sync` | ⚠️ **Seul point de non-retour** : sauvegarde du fichier JSON avant bascule, script de migration rejouable. Les alias supprimés sont restaurables par `git revert` (6 lignes) |
| J8 | Matrice cross-org + tests de fuite | Oui |
| J10–J12 | D0 mobile | Indépendant — retour à l'APK précédent |

**Point de non-retour réel** : uniquement la migration des fichiers JSON en J4. Toutes les autres
modifications sont réversibles par `git revert` isolé ou redéploiement de l'image précédente.

### 8.3 Critères de rollback en production

Redéployer le tag `pre-a1` (ou `git revert` du lot) si, dans les 10 minutes suivant la mise en
production :
- le taux de 401 sur des sessions **valides** dépasse 1 % ;
- plus de 3 erreurs 500 sur `network` ou `clusters` en 2 minutes ;
- aucun mobile ne peut se connecter malgré D0 déployé.

Le mode `audit` peut être activé **avant** un rollback pour confirmer le diagnostic : il ne modifie
aucun contrôle d'accès, il journalise seulement.

---

## 9. Séquencement

| Jour | A1 — isolation | D0 — mobile |
|---:|---|---|
| 1 | **`server.py` archivé + `README.md` corrigé** (prérequis bloquant) ; allowlist publique + test de garde `app.routes` (le test d'abord) | — |
| 2 | `network.py` (17 surfaces) + `crud.py` : `org_id` obligatoire | — |
| 3 | `clusters.py` (13 surfaces) + `corrections.py` (5) + doublon `recalculate-all` résolu | — |
| 4 | Bassins manuels : partitionnement `{org_id}.json`, script de migration, suppression des 3 alias, repointage `dessin_manuel.js` | — |
| 5 | `qualite.py` (10) + `mnt.py` (4) + `sync.py` (2) | — |
| 6 | `terrain.py` (6) + `simulations.py` (5) + WS jobs + `/api/v1/layers` | — |
| 7 | Résolveurs paramétrés (1,5 j ventilés sur J6-J7) | — |
| 8 | Matrice cross-org (252 assertions critiques) + 4 tests de fuite + garde de grep | — |
| 9 | Stabilisation, tests « à surveiller », revue de code | — |
| 10 | — | Manifest Android, URL unique, intercepteur HTTP centralisé, keystore et identité de build |
| 11 | — | Écran de connexion, `flutter_secure_storage`, `AuthHttpClient`, sélecteur d'organisation |
| 12 | Documentation (`docs/09_ENDPOINTS_DOCUMENTATION.md`), mesure finale, recette appareil | Push transactionnel, delta versionné, build release, `flutter analyze` vert |

En solo, les deux volets sont **séquentiels** : J1-J9 pour A1, J10-J12 pour D0. Si deux personnes sont
disponibles, D0 peut démarrer dès J2 (aucune dépendance de code avec A1, seulement un contrat d'API).

**Jalons**

- **J1** : `server.py` archivé, test de garde vert — **condition préalable à tout le reste**.
- **J4** : script de migration des bassins manuels livré et validé (avant la bascule J4 soir).
- **J9** : 68/68 surfaces traitées (63 protégées + 5 supprimées), matrice cross-org verte, 0 test cassé
  hormis `test_bms_simulation` (adapté en J8).
- **J9** : revue de code passée, gardes actives, mode `audit` documenté (s'il a été activé).
- **J12** : recette mobile sur appareil physique, `pytest -q` vert, mode `audit` éteint
  (aucune trace `tenant_missing_org` sur 24 h).

### Definition of Done

- [ ] `server.py` archivé dans `legacy/`, `README.md` corrigé, aucun script de démarrage ne le référence.
- [ ] 68/68 surfaces traitées : **63 protégées** et **5 supprimées** (3 alias `/manual-basin`,
      `/ws/sync`, alias `/ws/jobs`) ; allowlist publique explicite et commentée.
- [ ] `tests/test_tenant_guard.py` échoue si une route non listée n'a pas de dépendance tenant.
- [ ] 0 occurrence de `Project.first()` / `Organization.first()` sans filtre `org_id` (**test de grep**).
- [ ] 0 occurrence de `org_id` lu depuis `query_params`.
- [ ] Aucun stockage métier hors base sans clé d'organisation : `data/manual_overrides/{org_id}.json`,
      `server.py` archivé, 0 route `/api/v1/manual-basin` de premier niveau.
- [ ] Aucun `user_id` en paramètre de requête ; `audit_logs` porte l'acteur réel.
- [ ] 11/11 appels mobiles authentifiés ; push partiellement rejeté sans perte.
- [ ] `pytest -q` vert, durée < 8 min.
- [ ] Golden Master inchangé et vert (aucune modification de `src/domain/`).
- [ ] Mode `TENANT_ENFORCEMENT` **fail-closed** (`strict`/`audit`) documenté dans `.env.example` et
      `docs/09_ENDPOINTS_DOCUMENTATION.md` ; toute valeur permissive fait échouer le démarrage.

---

## 10. Risques du lot

| Risque | Impact | Probabilité | Parade |
|---|---|---|---|
| Le mobile n'est pas prêt au moment du déploiement d'A1 | App terrain hors service | Élevée | Livraison **atomique** A1+D0 ; version mobile minimale imposée |
| Une route oubliée échappe à la matrice | Faille résiduelle | Faible | Garde `app.routes` (exhaustivité mécanique, pas manuelle) |
| La résolution `memberships[0]` choisit la mauvaise org pour un utilisateur multi-org | Données incorrectes | Faible | En-tête `X-Organization-Id` explicite + test multi-org |
| Les 7 j de jeton d'accès rendent le vol de token durable | Élevé | Certaine (risque structurel) | Traité en A2 (jeton 15 min + rotation) — **à planifier immédiatement après** |
| Le comportement `optional` est utilisé par un client inconnu | Rupture | Faible | Vérifié : 0 consommateur hors web/mobile recensés ; allowlist explicite |
| `server.py` pas archivé avant J2 | Toute l'isolation A1 est contournable via le port Flask | Faible (procédure explicite) | Jalon J1 bloquant ; test d'intégration vérifie que le port Flask est fermé |
| Résolveurs `fid` / `object_type` plus longs que prévu | Dépassement de 0,5 j | Moyenne | Tâche isolée J7 ; exclusion temporaire de la matrice si dépassement (3 routes) |

---

## 11. Hors périmètre (lots suivants)

| Lot | Sujet | Pourquoi plus tard |
|---|---|---|
| A2 | Durcissement des jetons, cookies, rate-limit | Indépendant, mais **doit suivre immédiatement** (le jeton de 7 j reste le maillon faible) |
| A3 | Uploads : magic-bytes, taille, chemins | Indépendant de l'isolation ; 3 j |
| A6 | Migrations Alembic applicables | Chantier de schéma, à ne pas mêler à l'isolation |
| A7/A12 | CI + validation JS réelle | Nécessite A1 stable pour être utile |
| D1 | SQLite chiffré, cache secteur, photos, appairage | Refonte, pas correctif |

---

## 12. Corrections apportées aux analyses précédentes

| Affirmation antérieure | Valeur vérifiée | Cause de l'écart |
|---|---|---|
| « ~50 endpoints sans auth » | **68 surfaces** (61 sans contexte − 7 publiques + 9 optionnelles + 6 hors routeurs − 1 alias) | Le premier comptage ignorait les dépendances de routeur et les routes `app` |
| « 79 protégées / 61 non » | Confirmé **après** prise en compte des dépendances de routeur (le premier passage donnait 67/82) | L'analyse AST initiale ne lisait pas `APIRouter(dependencies=[...])` |
| « 0 test cassé » implicite | **1 test cassé** (`test_bms_simulation.py:18`) | Appel direct à une fonction de route, invisible dans un comptage HTTP |
| « supprimer les alias `/manual-basin` » | **Repointer, pas supprimer** | Vérification finale : `static/js/app/dessin_manuel.js:275,305` les utilise et le fichier est chargé par le cockpit (`templates/index.html:101`) |
| « `server.py` = point annexe » | **Prérequis bloquant J1** | 7 routes Flask non authentifiées sur un port indépendant, encore citées par `README.md` : l'isolation resterait contournable pendant tout le lot |
| « Résolveurs paramétrés ≈ 1 j » | **1,5 j** (ventilés Simple/Moyen/Complexe) | Les 3 résolveurs de niveau Complexe (`fid`, `object_type/{id}`) exigent une analyse GPKG hors SQL |
| « Option mobile A = 1,5 j » | **2 j** | `api_service.dart` n'a **aucun intercepteur HTTP centralisé** : les 11 appels construisent leurs en-têtes un à un, il faut extraire un `AuthHttpClient` |
| « Rollback par `TENANT_ENFORCEMENT=false` » | **Rollback par redéploiement ; flag fail-closed `strict`/`audit`** | Le flag initial renvoyait `TenantContext(role="admin", org_id=None)` : élévation de privilèges pour tout porteur de jeton, pas un mode dégradé |
| Charge « ~6 j » | **11 j** (A1 8 + D0 3) | D0 sous-estimé, `server.py` promu, résolveurs ventilés, intercepteur mobile à extraire |

---

## Annexe — Commandes de reproduction

```powershell
# 1. Inventaire des routes et de leurs dépendances (AST, lecture seule)
.venv\Scripts\python.exe C:\Users\Hakim\AppData\Local\Temp\opencode\audit_router_deps.py

# 2. Routes définies directement sur app
.venv\Scripts\python.exe C:\Users\Hakim\AppData\Local\Temp\opencode\audit_app_routes.py

# 3. Impact sur les tests
.venv\Scripts\python.exe C:\Users\Hakim\AppData\Local\Temp\opencode\audit_test_impact.py
.venv\Scripts\python.exe C:\Users\Hakim\AppData\Local\Temp\opencode\audit_direct_calls.py

# 4. Fichiers JS appelant les routes à protéger
.venv\Scripts\python.exe C:\Users\Hakim\AppData\Local\Temp\opencode\audit_callers.py

# 5. Suite de référence
.venv\Scripts\pytest -q

# 6. Vérifier que server.py n'est plus accessible (après J1)
# Doit retourner "Connexion refusée" ou équivalent
curl http://127.0.0.1:5002/api/v1/layers --max-time 3
```

Les scripts 1 à 4 sont des analyseurs statiques : ils ne modifient rien et peuvent être rejoués
après le lot pour vérifier que le compte des surfaces non protégées est bien descendu à 0.
