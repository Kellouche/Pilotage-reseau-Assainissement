# Couches SIG « Satellite » — Spécification d'architecture

> Statut : **plan validé, en attente de démarrage P0**
> Date : 2026-11-16
> Portée : ajout de données SIG externes (shapefiles, MNT, topographie) à un projet, **sans aucun couplage avec le GeoPackage projet ni le moteur hydraulique**.

---

## 1. Principe fondateur : INDÉPENDANCE TOTALE

Une couche satellite est une **source de consultation et d'aide à la décision**. Elle n'est jamais une entrée du calcul SWMM.

Garanties d'indépendance (non négociables) :

| Garantie | Mise en œuvre |
|---|---|
| **Aucune écriture dans le GPKG projet** | Les `.shp` sont convertis en GPKG mono-couche stockés dans un répertoire dédié `data/aux_layers/` — le fichier projet n'est jamais rouvert en écriture |
| **Aucune écriture dans les tables réseau** | `Canalisation`, `Regard`, `Simulation` ne sont jamais modifiées par une couche satellite. Les apports d'analyse (suspects d'inversion, candidats de connexion) sont des **propositions** qui transitent par le module `/corrections` existant, avec validation utilisateur explicite |
| **Aucun impact sur le `.inp` SWMM** | Le pipeline de génération (`src/domain/`) ne lit jamais les couches satellite. L'invariance hydraulique (Golden Dataset / Golden Master) est préservée par construction |
| **Versionnement séparé** | Une couche satellite n'entre pas dans le SHA-256 du GPKG projet : ajouter/retirer un satellite ne crée **pas** de nouvelle `gpkg_version` et ne rattache/détache aucune simulation |
| **Isolation multi-tenant** | `org_id` + `project_id` sur chaque ligne et chaque requête ; **stealth 404** sur toute ressource d'une autre organisation |
| **Reversibilité** | `DELETE` d'une couche satellite = suppression de ses fichiers + sa ligne DB. Le projet revient à l'état initial sans trace |

---

## 2. Modèle de données

### Table `project_aux_layers`

| Colonne | Type | Rôle |
|---|---|---|
| `id` | UUID | Identifiant de la couche satellite |
| `org_id` | str | Isolation tenant (indexé) |
| `project_id` | str | Projet rattaché |
| `type` | str | `altimetrie_points`, `bv_officiel`, `metrologie`, `mnt_*`, `autre` |
| `nom` | str | Nom affiché (ex. « Topographie Chlef — 84k points ») |
| `fichier_source` | str | Nom du fichier uploadé (traçabilité) |
| `chemin_stockage` | str | Chemin du GPKG mono-couche dérivé |
| `crs_source` | str | CRS d'origine (ex. `EPSG:32631`) |
| `geom_type` | str | `Point`, `Polygon`, `MultiPolygon`… |
| `emprise` | JSON | Bbox `[minx, miny, maxx, maxy]` en EPSG:4326 |
| `nb_features` | int | Nombre d'entités |
| `attributs` | JSON | Liste des champs (pour mapping éventuel) |
| `statut` | str | `ok`, `erreur_import`, `desactivee` |
| `created_at` | datetime | Horodatage |

### Stockage physique

```
data/
  aux_layers/
    {project_id}/
      {layer_id}/
        source/            # fichier(s) uploadé(s) brut(s), archive
        layer.gpkg         # GPKG mono-couche normalisé (CRS 4326)
        derive/            # produits dérivés (grille topo, index…)
```

**Formats d'entrée** : **shapefile = format nominal** — le `.shp` est envoyé **avec tous ses sidecars** (`.shx .dbf .prj .cpg`) en sélection multi-fichiers, ou via un `.zip` contenant le jeu complet. Un `.shp` sans sidecars est **refusé** avec message explicite. Formats secondaires acceptés : `.gpkg`, `.geojson/.json`. Tout est converti en **GPKG mono-couche** via geopandas/pyogrio : un seul format interne à gérer, relecture triviale, pas de dépendance aux sidecars après import.

**CRS** : normalisation EPSG:4326 à l'import (le pipeline carte travaille en 4326/WGS84). Le `crs_source` est conservé pour traçabilité.

---

## 3. API — routeur dédié `aux_layers.py`

| Endpoint | Rôle |
|---|---|
| `POST /api/v1/projets/{id}/aux-layers` | Upload **piloté par l'utilisateur** (`multipart`) : l'utilisateur choisit explicitement le fichier **et** le `type` de couche (`altimetrie_points`, `bv_officiel`, `metrologie`…). Aucun import automatique — validation taille/type, conversion, insertion DB |
| `GET /api/v1/projets/{id}/aux-layers` | Liste des couches satellite du projet |
| `GET /api/v1/projets/{id}/aux-layers/{lid}` | Détail + échantillon d'attributs |
| `GET /api/v1/projets/{id}/aux-layers/{lid}/geojson?bounds=minx,miny,maxx,maxy` | Flux cartographique borné — **obligatoire pour les grosses couches** (même contrat que `/layers`) |
| `GET /api/v1/projets/{id}/aux-layers/{lid}/elevation?lng=&lat=` | *(altimétrie uniquement)* cote terrain estimée + distance au point topo + confiance |
| `DELETE /api/v1/projets/{id}/aux-layers/{lid}` | Suppression complète (fichiers + ligne) |

Règles : `org_id` vérifié sur le projet **et** sur la couche à chaque appel ; stealth 404 si mismatch ; limites de taille et de nombre de features à l'upload ; parsing dans un répertoire temporaire isolé.

---

## 4. Service altimétrie (`aux_altimetrie_service.py`)

Premier type de couche : `altimetrie_points` (cas d'usage : `TOPO CHLEF.shp`, 84 302 points cotés, EPSG:32631).

À l'import :
- Chargement `(x, y, z)` → index `scipy.spatial.cKDTree`
- **Grille interpolée** pré-calculée sur l'emprise du réseau projet (~20–50 m), interpolation IDW/RBF → stockée dans `derive/grid.*`
- Cache invalidé uniquement à la ré-import de la couche

Requêtes :
- `elevation(lng, lat)` → `{z_estime, distance_point_plus_proche, confiance}` où `confiance` décroît avec la distance (topo dense : médiane ~5,6 m ; bords de zone : >50 m → confiance faible, **affichée partout où le chiffre apparaît**)
- `gradient(lng, lat)` → pente terrain locale (base des détections d'inversion)

---

## 5. Réserve scientifique — à afficher dans l'UI

> La cote topo est la **cote du terrain**, pas le **fond de regard** (l'égout est enterré, ~1–3 m).

Conséquences appliquées partout :
- Jamais de comparaison absolue `z_topo` ↔ radier SWMM
- Usage réservé aux **différences** : pente terrain entre deux points, cohérence amont/aval, détection d'inversions flagrantes, **classement** des candidats de connexion
- La profondeur d'égout, quand elle est nécessaire, est une **hypothèse fournie par l'utilisateur** (fourchette paramétrable), jamais un fait déduit du topo

---

## 6. Les 4 objectifs — feuille de route

| # | Objectif | Phase | Mécanisme |
|---|---|---|---|
| 1 | **Superposition des données** | P0 | Couche « Altimétrie » dans le panneau couches (points bornés) + **sonde altimétrique** : clic carte → cote estimée + confiance |
| 2 | **Correction des sens d'écoulement** | P1 | Gradient topo aux extrémités de chaque conduite vs `prof_fe_am/av` et pentes constatées (`_observed_slope` existe déjà dans `corrections.py`) → file de conduites à inversion suspectée → proposition dans `/corrections/hybride`, **validation utilisateur requise** |
| 3 | **Connexion des orphelins** | P2 | Pour chaque regard orphelin : k-plus-proches nœuds/conduites + Δz topo + pente requise → candidats classés avec justification altimétrique → snap **proposé**, jamais automatique (règle existante respectée) |
| 4 | **Correction des profils en long** | P3 | Enrichissement de `profile/{fid}` (existant) : surface topo sous le profil, fond estimé = terrain − profondeur type paramétrable, détection de ruptures de pente |

---

## 7. Artefact dérivé `regards_terrain.json` (décision actée)

Pour les couches `altimetrie_points`, un artefact pré-calculé est produit à
l'import **et** à chaque nouvelle `gpkg_version` réseau :

- **Contenu** : pour chaque regard du GPKG projet → `lng, lat, z_terrain_m,
  distance_topo_m, confiance, pente_terrain_pct, azimut_pente_deg`
  (z IDW + gradient de la grille échantillonné au point)
- **Stockage** : `derive/regards_terrain.json` via ArtifactStore, clé
  `{org}/{projet}/gis/aux_layers/{layer_id}/…` — jamais dans le GPKG projet
- **Estampillage** : `meta.gpkg_sha256` = empreinte de la version réseau
  au moment du calcul → l'endpoint signale `perime: true` si le réseau a
  changé (recalcul sur action explicite, jamais silencieux)
- **Usages** (P1→P3) : sens d'écoulement (Δz terrain amont/aval),
  contre-pentes, classement des candidats orphelins, profils en long
- **P3 — consommation profil en long** (implémenté) : `profil-en-long`
  expose `z_terrain_interp` + `terrain_confiance` par segment et le bloc
  `terrain_interpole` en en-tête, **uniquement si** `meta.gpkg_sha256`
  correspond au SHA-256 du GPKG du profil (artefact périmé → ignoré).
  Le terrain interpolé n'alimente JAMAIS `z_terrain` : la classification
  hydraulique (inondation, revanche, atteint_terrain) reste réservée aux
  cotes altimétriques vérifiées du GPKG. Côté graphique, courbe distincte
  en pointillés « Terrain interpolé IDW (≈, ≠ fond de regard) ».

### 7bis. Option C — injection terrain → radier `.inp` (à valider)

Objectif : remplacer le datum synthétique (`100 m + distance × pente`)
par des cotes radier réelles estimées `z_terrain_IDW − profondeur`.

**Aperçu obligatoire avant tout usage** :
`GET /api/v1/projets/{id}/aux-layers/{lid}/apercu-inp` → par regard
`z_terrain_m`, `profondeur_m` (+`profondeur_estimee`), `z_radier_terrain_m`,
confiance ; statistiques couverture, **inversions amont/aval** détectées.

**Règles actées** :
- Profondeur manquante → **médiane du réseau calculée** (jamais de défaut
  aveugle), flag `profondeur_estimee` propagé jusqu'au profil (symbole
  distinct sur les regards concernés)
- Couverture ≥ **95 %** des nœuds avec terrain sinon refus explicite —
  jamais de mixte de datums dans un même `.inp`
- Exutoire traité comme les autres nœuds (position dans le GPKG → IDW)
- Artefact périmé (sha ≠ GPKG courant) → refus, recalcul requis
- Le `.inp` portera une note de provenance (couche, résolution, sha)
- **Constat live** : 1 951 inversions amont/aval détectées à l'aperçu —
  le bruit IDW (±1–2 m) dépasse la pente locale sur terrain plat ;
  l'injection devra donc s'appuyer sur le garde-fou de pente/monotonie
  existant et remonter les contre-pentes à l'utilisateur, jamais les
  lisser silencieusement
- **Limites rappelées** : cote terrain ≠ fond de regard ; usages limités
  aux différences ; `confiance` propagée partout
- **Collision de codes** : les rares codes dupliqués dans le SIG (13/10 538)
  sont comptés dans `meta.codes_en_doublon` — la clé reste le code métier

---

## 8. Phasage

- **P0 — Import & superposition** : table, endpoints, conversion GPKG, couche carte + sonde. *Premier satellite : TOPO CHLEF (84k points), importé uniquement sur action explicite de l'utilisateur (choix du fichier + du type de couche — aucun import automatique).*
- **P1 — Suspects écoulement** (endpoint implémenté) :
  `GET .../aux-layers/{lid}/suspects-ecoulement` — 3 signaux par conduite
  (relèvement terrain le long du flux, radier estimé, azimut de plus forte
  descente opposé au cap si pente locale ≥ 1 %) → score + motifs +
  sévérité (fort/moyen/faible), top 300. **File de revue uniquement** —
  aucune correction automatique ; recoupement avec `/corrections` requis.
  Seuils : forte inversion > 1 %, moyenne > 0,3 % du long de la conduite.
  Live : 10 136 conduites → 2 002 suspects (624 forts) — les écarts
  extrêmes (>50 m) signalent plutôt des erreurs de connectivité/codes
  que des simples sens inversés.
- **P2 — Orphelins** : scoring altimétrique des candidats de connexion.
- **P3 — Profils en long** : profil terrain/radier superposé dans `profile/{fid}`.
- **P4+ — Autres satellites** : `BV.shp` (validation sectorisation vs BV officiels), `Points de métrologie.shp` (calage), MNT raster si disponible.

Chaque phase = suite pytest complète + `node --check` JS + commit/push conventionnel (AGENTS.md).

---

## 9. Ce que ce document exclut explicitement

- Fusion des satellites dans le GPKG projet (rejetée : couplage de versionnement, risque de pollution des couches lues par mot-clé)
- Modification automatique du réseau (regards, conduites, exutoires) — proposition uniquement
- Support raster MNT (GeoTIFF) — phase ultérieure si un MNT officiel est obtenu ; les points cotés suffisent pour P0–P3
- Toute écriture dans `src/domain/` ou les équations SWMM
