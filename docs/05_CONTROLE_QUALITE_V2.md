# 05 — Contrôle Qualité du Réseau : spécification V2.1

> **Statut : spec de référence figée** (arbitrage de deux contre-expertises indépendantes,novembre 2026).
> **Portée :** refonte complète du module « Contrôle Qualité du Réseau d'Assainissement » — moteur d'analyse, endpoints, persistance des statuts, interface.
> **Public :** ingénieurs hydrauliciens, BET, mainteneurs.

---

## 1. Pourquoi cette refonte

Le module actuel produit des anomalies **non vérifiées** : sur le jeu de référence « Assainissement_Ville » (10 295 canalisations), il affiche **1 134 « pentes suspectes » critiques** et **944 incohérences amont/aval**. Deux contre-expertises ont établi que ces chiffres sont des artefacts :

- `PROFRADI` est une **profondeur** de radier (mélange m/mm, 7 valeurs aberrantes > 100), pas une altitude. La « pente » actuelle soustrait des profondeurs entre elles — un approfondissement normal du réseau gravitaire devient une « contre-pente ».
- Le GPKG ne contient **aucune cote NGF exploitable** (`COTTN`, `COORDZ` vides à 100 %).
- La seule altitude disponible est la couche satellite `altimetrie_points` (« TOPO CHLEF », 84 302 points, EPSG:32631).
- `templates/qualite.html` charge Leaflet sans jamais instancier de carte : tableau brut limité à 50 lignes.

**Principe fondateur V2.1 : zéro anomalie listée sans source de référence identifiable.** Si la donnée ne permet pas de trancher, l'objet est classé `donnees_manquantes` — jamais `anomalie`.

## 2. Sévérité = impact sur la simulation

| Sévérité | Définition |
|---|---|
| `bloquant` | la simulation ne peut pas tourner ou produit un résultat structurellement faux |
| `majeure` | résultats faussés localement (zone, nœud, tronçon) |
| `mineure` | qualité du jeu de données, impact limité |
| `informatif` | convention, alias, snap — à corriger à l'occasion |

## 3. Taxonomie des anomalies

| Catégorie | Exemples | Sévérité |
|---|---|---|
| `topologie` | extrémité orpheline, boucle, double liaison, nœud sans exutoire, déconnexion spatiale extrême | bloquant/majeure |
| `sens_ecoulement` | inversion de sens vs gradient du terrain | majeure |
| `altimetrie` | contre-pente certifiée (N1/N2), discontinuité de pose `PROF_FE` > 3 m | majeure/mineure |
| `attributs` | diamètre ≤ 0, matériau absent, longueur déclarée ≠ géométrie | majeure/mineure |
| `donnees_manquantes` | pas de radier exploitable, pas de point topo proche, colonne source vide, `pente_non_evaluable` | informatif → action : compléter la source |
| `conventions` | alias (79), snap (75), homonymes résolus | informatif |

## 4. Détection des pentes — cascade d'autorité

### 4.1 Niveaux

```
N1 — PENTE CERTIFIÉE : dénivelée NGF explicite (récolement géomètre)
     ou z_tampon exploitable.
     → sur le jeu Ville : ~0 cas (GPKG nu altimétriquement).

N2 — DOUBLE SIGNAL :
     a) sens_ecoulement : pente locale du terrain > 1 % ET cap de la
        conduite opposé à l'azimut de descente de > 120°
        → inversion certaine (Priorité 1) ;
     b) pente radier estimée : point topo < 15 m du nœud ET profondeur
        radier réelle (PROFRADI ou PROF_FE, jamais médiane injectée)
        → « suspecte sous réserve de validation terrain ».

N3 — INDÉTERMINÉ : topo > 50 m, médiane injectée, cohérence topo
     douteuse, refoulement, regard de chute non modélisé
     → donnees_manquantes (pente_non_evaluable). JAMAIS anomalie.
```

### 4.2 Garde-fous obligatoires (ordre du pipeline)

1. **Topologie d'abord** : exutoires, orphelins, extrémités — via `ResoluteurNoeuds` canonique (registre fusionné Regards + Rejets + Stations + STEP ; interdiction de chercher dans `Regards` seul).
2. **Cohérence géométrique** : `dist(regard, vertex extrémité) ≤ 0,50 m` (tolérance snap) **et** `L_géométrie / corde ≤ 3,0` (les tronçons sinueux sont valides — 52 conduites saines ont un écart corde/longueur > 2 m). Un tronçon « 16,2 m » reliant deux regards à 4,2 km = `deconnexion_spatiale_extreme`, **pas** une pente.
3. **Altimétrie ensuite, jamais avant** : la pente n'est calculée que sur N1/N2 après validation topologique.
4. **Attributs** : diamètre, matériau, longueur.
5. **Polluants** : sanitisation `PROFRADI` (0,30–10 m accepté ; >10 → conversion d'unité suspecte + avertissement ; hors limites → rejet → N3), doublons `Code`, IDs dupliqués entre couches.

### 4.3 Champs `PROF_FE_AM` / `PROF_FE_AV` — usage borné

Ce sont des **profondeurs de fil d'eau** (~2 130 tronçons renseignés), PAS des cotes NGF. Ils servent uniquement à :

- affiner `z_radier = z_tampon − PROF_FE` quand un MNT est disponible ;
- détecter les **discontinuités de pose** (variation de profondeur > 3 m entre regards consécutifs).

**Jamais** de calcul de pente absolue sur `PROF_FE` seul — cela reproduirait le bug `PROFRADI`.

### 4.4 Exclusions explicites

- Conduites de refoulement / stations de relevage : jamais de contrôle de pente gravitaire.
- Regards de chute : calcul par extrémité de conduite, pas par cote unique de nœud.
- Artefact `regards_terrain` périmé : régénération à la volée si la couche `altimetrie_points` est `ok`, sinon repli N3 explicite (jamais de bascule silencieuse).

## 5. Sortie — anomalies enrichies et double score

### 5.1 Chaque anomalie porte

`type`, `severite`, `geometry` (WGS84), objet (`id_conduite`, `id_regard`…), cause, valeurs mesurées, **provenance de la source** (`mesure` / `mnt_haute_confiance` / `indetermine`), action suggérée, statut persisté.

### 5.2 Persistance des statuts

Table dédiée `qualite_anomalie_statuts` isolée par `org_id`/`project_id`, clé stable `hash(type_anomalie, id_objet, gpkg_version_id)`. Purge/obsolescence à la révocation d'un snapshot GPKG.

### 5.3 Score v2 — jamais opaque

Affichage **disjoint** : `Qualité topologique : X %` et `Complétude altimétrique : Y %`. Le dénominateur est toujours visible.

## 6. Endpoints

| Méthode | Route | Rôle |
|---|---|---|
| `GET` | `/api/v1/qualite/analyse` | rapport complet (cache mtime GPKG **et** versions couches aux) |
| `GET` | `/api/v1/qualite/anomalies.geojson?type=&severite=&statut=` | couche carte clusterisable |
| `GET` | `/api/v1/qualite/anomalies/{type}?cursor=&limit=` | pagination réelle |
| `POST` | `/api/v1/qualite/anomalies/{id}/statut` | `a_traiter` / `revu` / `corrige` |
| `GET` | `/api/v1/qualite/synthese` | verdict + couverture + top 3 actions |

## 7. Interface (`/qualite` dans le cockpit)

```
┌──────────────────────────────────────────────────────────┐
│ Synthèse : verdict + couverture + top 3 actions          │
├───────────────────────────────┬──────────────────────────┤
│ CARTE Leaflet clusterisée     │ FILE D'ANOMALIES         │
│ • clic → zoom + fiche         │ • filtres type/sév./statut│
│ • fond MNT/satellite          │ • ◀ ▶ précédent/suivant  │
│                               │ • action : éditer /      │
│                               │   recalculer / marquer   │
└───────────────────────────────┴──────────────────────────┘
```

- Clustering obligatoire (Leaflet.markercluster) — des milliers de points sans cluster = écran noir.
- Fiche anomalie : objet, cause, valeurs, provenance, actions.
- Compteur de file « anomalie 37 / N » + navigation ← →.
- Statuts persistants : « corrigée » sort du décompte, consultable en filtre.
- Score dépliable : composition, sources, couverture, date, version GPKG.

## 8. Cibles de recette — jeu « Ville » (10 295 conduites)

| Catégorie | Actuel (défectueux) | Cible V2.1 |
|---|---|---|
| Pentes suspectes | 1 134 | **0** |
| Inversions de sens avérées | 944 (bruit) | **180–250** |
| Altimétrie indéterminée | 0 (masquée) | **7 500–8 500** |
| Raccordements spatiaux extrêmes | non détectés | **10–25** |
| Orphelins réels | ~350 | **≤ 15** |

**Cas témoins obligatoires :**
- `ID_AMONT 20150 → ID_AVAL 3824` : L=35,2 m, distance 36,1 m, terrain 111,5→138,3 m (+76 %) → **doit être détecté** comme inversion de sens.
- Tronçon « 16,2 m » reliant deux regards à 4,2 km → `deconnexion_spatiale_extreme`, jamais pente.
- Conduites sinueuses (52 cas, sinuosité jusqu'à 1,72) → **jamais** rejetées par le test géométrique.

## 9. Invariants intouchables

- Multi-tenant `org_id`/`project_id` sur tout endpoint et table ; stealth 404.
- Cache invalidé par mtime GPKG **et** version des couches auxiliaires.
- **Aucune modification des calculs hydrauliques** — la qualité lit, ne calcule pas.
- Compatibilité des 648 tests existants + nouveaux tests de non-régression chiffrés (§8).
- Gestion des verrous fichiers Windows (WinError 5) : context managers GDAL/SQLite stricts dans tout nouveau code lisant des GPKG.

## 10. Traçabilité des décisions

| Décision | Origine |
|---|---|
| `PROFRADI` = profondeur, jamais altitude | `assainissement_topologique.py` L40-72 + contre-expertise 1 |
| `z_radier_terrain` seul = NO-GO (bruit IDW σ≈±0,3-0,5 m → σ_pente ±1,2 %) | contre-expertise 1 §2 |
| `PROF_FE_AM/AV` = profondeurs, pas cotes | vérification expert 2 (moyennes 2,35/3,73 m) |
| Test corde/longueur Δ<2 m rejetait 52 conduites saines | mesure expert 2 (écart jusqu'à 134,8 m) |
| Priorité « sens d'écoulement vs terrain » sur « pente ponctuelle » | arbitrage expert 2 §4 |
| `ResoluteurNoeuds` obligatoire pour les 79 rejets | MISSION_TOPOLOGIE_INP + expert 2 |
