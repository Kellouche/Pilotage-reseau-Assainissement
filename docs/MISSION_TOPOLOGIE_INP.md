# MISSION D'INGÉNIERIE : TRANSFERT FIDÈLE GPKG → SWMM 5.2 « ZÉRO PERTE »

> **Statut** : document d'analyse — la version contractuelle consolidée est
> **[CAHIER_DE_CHARGES_RESTITUTION_INP.md](CAHIER_DE_CHARGES_RESTITUTION_INP.md)**

> **Statut** : version corrigée — fondée sur l'audit mesuré du GPKG réel
> (`Assainissement_Ville.gpkg`, 10 295 canalisations, 10 538 regards,
> 79 rejets, 5 stations de relevage, 38 ouvrages spéciaux)
> **Date** : 22 novembre 2026
> **Références** : `docs/09_ENDPOINTS_DOCUMENTATION.md`, `AGENTS.md`

---

## 1. Contexte et objectif

Le pipeline GPKG → `.inp` SWMM 5.2 de DrainPilot perd aujourd'hui de
l'information physique de façon **silencieuse**. Audit du 22/11/2026 :

| Perte constatée | Preuve |
|---|---|
| `FONCTIONMT='Refoulement'` jamais lu | `graphe_reseau.py:155` cherche `type`/`nature`/`Fonction_1`, pas `FONCTIONMT` → les 12 refoulements partent en conduites **gravitaires** |
| `[PUMPS]`/`[CURVES]`/`[CONTROLS]` absents du `.inp` | Sections générées : JUNCTIONS/OUTFALLS/CONDUITS/XSECTIONS uniquement |
| Stations = JUNCTIONs à 101,000 m artificiel | `SR_HH01`, `SR_HC`, `SR_CH`, `SR_HH02` dans le `.inp` généré |
| 110 attributs patrimoniaux des stations jetés | `KEEP_COLS["stations"] = ["geometry"]` |
| Toutes les sections XSECTIONS = `CIRCULAR` | `FORMESECT`/`HAUTEUR`/`GDEBASE` ignorés |
| Rugosité `n=0.013` en dur | `MATERIAU` non traduit en Manning |
| Ouvrages spéciaux / DVO non restitués | `[WEIRS]` absent du `.inp` |

**Objectif** : un `.inp` qui restitue fidèlement le GPKG — topologie,
éléments spéciaux et attributs physiques — avec **traçabilité totale**
des écarts et hypothèses.

---

## 2. Mesures de référence (audit du 22/11/2026)

Ces chiffres conditionnent le périmètre — ne pas les supposer différents :

| Métrique | Valeur |
|---|---|
| Canalisations actives | 10 295 (hors couches `désaffectée`/`désaffecté` : 15 exclues) |
| Extrémités topologiques résolues par ID | **20 375 / 20 550 (99,15 %)** |
| Extrémités orphelines | 175 (0,85 %) |
| Orphelins récupérables par snapping < 0,5 m | **164 (94 %)** |
| Orphelins réellement irrécupérables | ~11 |
| Conduites `FONCTIONMT='Refoulement'` | **12** (PEHD 315–630 mm, IDs amont = codes `SR_*`) |
| Stations de relevage | **5** (`SR_HH01`, `SR_HH02`, `SR_CL`, `SR_CH`, `SR_HC`) |
| Références `SR` sans station correspondante | `SR_CL` (Carmella) — à qualifier |
| Rejets | 79 — les codes de rejet portés par les `ID_AVAL` sont **absents** des tables de nœuds |

> **Mise à jour 23/11/2026** : ces codes ne sont plus orphelins — ils
> suivent une convention de nommage propre au jeu (alias verbeux +
> zéro-padding) résolue vers le code numérique des rejets (distance
> mesurée 0,0 m). Voir §7.

**Conséquence mesurée** : la connectivité par `ID_AMONT`/`ID_AVAL` est
fiable à 99,15 %. La reconstruction topologique **spatiale complète est
inutile et risquée** — elle n'est retenue que comme filet de secours
pour les 175 orphelins.

---

## 3. Plan de réalisation — 4 phases ordonnées

### PHASE A — Corrections d'intégrité minimales (rapide, prioritaire)

Objectif : honnêteté immédiate — plus aucune perte silencieuse.

| # | Tâche | Fichier | Critère d'acceptation |
|---|---|---|---|
| A.1 | Propager `FONCTIONMT` dans la détection de type de conduite | `src/domain/graphe_reseau.py:155` — ajouter `row.get('FONCTIONMT')` à la chaîne de `get` | `'refoulement'` détecté → pas d'inversion de sens, marquage `type='refoulement'` sur l'arête |
| A.2 | Comptabiliser et **exclure explicitement** les refoulements du calcul gravitaire, avec avertissement | `sections_inp.py` / `assemblage_inp.py` | Le `.inp` ne contient plus les 12 refoulements en `[CONDUITS]` gravitaires ; la provenance liste `refoulements_exclus: 12` |
| A.3 | Audit d'exclusions : `désaffectée`/`désaffecté`, orphelins irrécupérables, `RJxx` non résolus | nouveau `src/domain/moteur_swmm/audit_exclusions.py` | Chaque exclusion a un motif typé (`desaffecte`, `orphelin`, `id_inconnu`, `doublon`) — jamais silencieuse |
| A.4 | Cotes réelles des stations : utiliser `COORDZ` du GPKG au lieu de 101,000 | section JUNCTIONS | Cotes des `SR_*` = cotes GPKG ou marquées `hypothèse` si absentes |

### PHASE B — Restitution des éléments spéciaux SWMM 5.2

> ⚠️ **Correction technique impérative** : SWMM 5.2 n'a **pas** de type
> `FORCE_MAIN` ni d'option Hazen-Williams/Darcy-Weisbach — le frottement
> est Manning's n uniquement. Une conduite de refoulement se modélise
> comme un `[CONDUIT]` alimenté par une `[PUMPE]`. Toute formulation
> « FORCE_MAIN dans [CONDUITS] » est invalide.

| # | Tâche | Détail SWMM | Données GPKG |
|---|---|---|---|
| B.1 | `[PUMPS]` : une pompe par station de relevage (ou groupe fonctionnel) | `Name, From Node (bâche), To Node, Pump Curve` | `Station_de_relevage` + `FONCTIONMT='Refoulement'` |
| B.2 | `[CURVES]` : courbe caractéristique par station | Type 1 (débit/hauteur) si `HMTP`+`DEBTOTAL` renseignés ; sinon courbe standard **documentée comme hypothèse** | `PUISSP1-6`, `HMTP1-6`, `DEBUNIT1-6`, `DEBTOTAL`, `PUISSANCE`, `NBPOMPE`, `MODELPOMP` |
| B.3 | `[CONTROLS]` / `[RULES]` : ordre de marche par niveau de bâche | `[CONTROLS]` simple (ON si bâche > seuil) ou règle par temps sec | `NBRBACHE`, `VOLBACH1-3`, `PROFBACH1-3` |
| B.4 | Nœud de station : `[STORAGE]` si `VOLBACH`/`NBRBACHE` renseignés (vrai volume de bâche), sinon `[JUNCTION]` avec emprise | `[STORAGE]` exige une courbe de stockage — ne pas l'imposer sans données | À trancher par station selon complétude |
| B.5 | Conduite de refoulement : `[CONDUIT]` **en aval de la pompe** (refoulement gravitaire après relevage) ou lien pompe→exutoir | La pompe transforme le tronçon en sous-pression | `ID_AMONT='SR_xxx'` → pompe ; `ID_AVAL` = nœud aval réel |
| B.6 | Correspondance `SR_xxx` ↔ station : normaliser `_`/espace (`SR HH01` = `SR_HH01`) | Mapping robuste + journal des non-matchs | `CODEPRR` vs `ID_AMONT`/`ID_AVAL` |
| B.7 | `[XSECTIONS]` rectangulaires : `FORMESECT` ≠ circulaire → `RECTANGULAR Geom1 Geom2` | `Geom1=largeur(GDEBASE)`, `Geom2=hauteur(HAUTEUR)` | `FORMESECT`, `HAUTEUR`, `GDEBASE`, `PETBASE` |
| B.8 | Rugosité par matériau : table `MATERIAU → Manning n` | PEHD 0,010 ; PVC 0,011 ; Béton 0,013–0,015 ; Fonte/Acier 0,012 ; inconnu → 0,013 **défaut documenté** | `MATERIAU` |
| B.9 | `[WEIRS]` pour déversoirs d'orage : seuil, cote de crête, largeur | `Rectangular Weir` avec `H_s` (seuil) du GPKG | `Ouvrages_Speciaux` + seuils |

### PHASE C — Topologie : IDs d'abord, spatial en secours uniquement

| # | Tâche | Détail |
|---|---|---|
| C.1 | Conserver `ID_AMONT`/`ID_AVAL` comme source de connectivité principale | 99,15 % de résolution mesurée — ne pas réécrire |
| C.2 | **Filet de secours spatial** : pour les 175 orphelins uniquement, KD-tree/STRtree ε ≤ 0,5 m (projetté) | Récupère ~164 tronçons ; crée un nœud `N_X_Y` pour les ~11 restants |
| C.3 | Chaque rattachement spatial = **audit obligatoire** : `topologie_spatiale: true`, distance, nœud cible | Visible dans la provenance et le bilan Phase D |
| C.4 | Orientation du sens d'écoulement par cotes radier (`PROF_FE_AM/AV`, `z_radier`) — jamais par la seule géométrie | Ajoute `FONCTIONMT` à la logique existante de `graphe_reseau.py` |
| C.5 | Respecter le filtrage par bassin/cluster (`extraire_sous_reseau_bassin`) — le moteur topologique l'alimente, ne le contourne pas | Isolation snapshot/projet inchangée |

### PHASE D — Inventaire, validation et non-régression

| # | Tâche | Critère |
|---|---|---|
| D.1 | **Bilan de réconciliation 1:1** : tableau SIG ↔ INP par type d'objet (conduites, regards, stations, rejets, DVO) + répartition matériau/diamètre/section | Modal cockpit + export |
| D.2 | **Audit d'exclusions** : chaque objet absent du `.inp` a un motif + justification | Zéro exclusion silencieuse |
| D.3 | **Provenance enrichie** : `refoulements_traites`, `refoulements_exclus`, `stations_pompes`, `hypotheses_courbes`, `raccordements_spatiaux` | Visible dans le rapport et le PDF |
| D.4 | **Re-baselinage Golden Dataset documenté** : les résultats *vont* changer (pompes, rugosités, rectangulaires) — nouveau golden avec justification par écart, pas suppression de tests | `tests/data/golden_dataset/` mis à jour + note de changelog hydraulique |
| D.5 | Validation `epa_example5_pumping.gpkg` : le `.inp` généré doit reproduire les pompes du modèle EPA de référence | Golden Master étendu aux sections `[PUMPS]` |
| D.6 | Bilan de continuité massique < 1 % maintenu ; pytest complet + `node --check` ; commit/push automatique | Règle AGENTS.md |

---

## 4. Critères d'acceptation révisés

| # | Critère | Remplace |
|---|---|---|
| 1 | **100 % des objets éligibles** présents dans le `.inp` ; chaque exclusion a un motif audité | « 0 % d'exclusion » (dangereux : aurait inclus les désaffectées) |
| 2 | **≥ 99 % des extrémités connectées** par ID ; les orphelins restants ont un nœud spatial ou une exclusion justifiée | « 99,9 % » (irréaliste sans invention de nœuds) |
| 3 | Les **12 refoulements** sont des `[PUMPS]`+`[CONDUITS]` (pas gravitaires) ; les **5 stations** ont des courbes et cotes réelles ou hypothèses tracées | « FORCE_MAIN » (inexistant dans SWMM) |
| 4 | **Chaque hypothèse** (courbe pompe par défaut, rugosité inconnue, nœud spatial) est dans la provenance | — |
| 5 | Tests verts + **re-baselinage Golden documenté** | « tests passent » (insuffisant si le comportement change) |

---

## 5. Points de vigilance non négociables

1. **Multi-tenant** : `org_id`/`project_id`/snapshot — aucune fuite inter-projets.
2. **Ne pas toucher** `src/domain/` moteur physique sans Golden Master — les
   sections `[PUMPS]`/`[CURVES]` sont un **ajout**, pas une modification
   des équations Saint-Venant.
3. **Complétude des données** : `NBPOMPE`, `PUISSP`, `HMTP` sont majoritairement
   NULL sur les 5 stations — les courbes seront des **hypothèses documentées**,
   pas des données fabricant. L'UI doit le dire.
4. **`SR_CL` (Carmella)** : station sans refoulement ni station `.inp` —
   à qualifier avant de l'inventer dans le modèle.
5. **Codes de rejet des `ID_AVAL`** : ✅ **résolu** — convention de
   nommage du jeu (alias + zéro-padding) résolue vers le code des rejets
   (0,0 m mesuré). Voir §7 ; ne plus traiter comme `id_inconnu`.
6. **Calibration d'abord** : la Phase A (honnêteté) doit être livrée **avant**
   la Phase B (complexité) — ne jamais accumuler les chantiers.

---

## 6. Livrables attendus

- `.inp` généré pour le réseau réel avec sections `[PUMPS]`, `[CURVES]`,
  `[CONTROLS]`, `[XSECTIONS]` rectangulaires, rugosités par matériau
- Bilan de réconciliation SIG ↔ INP (modal cockpit + export)
- Audit d'exclusions complet (zéro silencieux)
- Provenance enrichie (hypothèses, rattachements spatiaux, pompes)
- Golden Dataset re-baseliné + note de justification
- Documentation `docs/` mise à jour

---

## 7. Stratégie d'ouverture des fichiers GPKG — résolution canonique et découverte automatique (IMPLÉMENTÉ 23/11/2026)

> Statut : **en production**. Le système n'exige **aucune connaissance** du
> contenu du fichier de la part de l'utilisateur : il lit, analyse et
> découvre seul les conventions de nommage et la tolérance de snap.

### 7.1 Chaîne de résolution canonique des extrémités

Source unique : `src/domain/topologie/resolution_noeuds.py`
(`ResoluteurNoeuds`), consommée à l'identique par le graphe de bassins
(`graphe_reseau.py`), le générateur `.inp` (`sections_inp.py`) et l'audit
qualité (`analyse_qualite_gpkg.py`) :

```
ID texte → alias sémantique codé → alias automatique par noyau
         → snap spatial ≤ tolérance → nœud spatial tracé → absent
```

Chaque résolution porte sa **provenance** (`id`, `alias`, `alias_auto`,
`snap`, `spatial`, `absent`) — jamais silencieuse.

### 7.2 Découverte automatique des conventions — adaptative, sans configuration

Module : `src/domain/topologie/decouverte_conventions.py`
(`obtenir_conventions(gpkg_path)`).

La méthode est **générique** : elle ne présuppose aucune convention de
nommage. Pour tout GeoPackage, qu'il s'agisse d'un export_SIG français,
d'un shapefile converti ou d'un fichier propriétaire, le système :

1. ** collecte les extrémités non résolues** par la chaîne de base
   (ID strict + alias connus + snap par défaut) ;
2. **analyse les motifs d'identifiants** de ces échecs — tout préfixe,
   suffixe, séparateur ou convention de zéro-padding est candidat
   (`PREFIX_123`, `SORTIE-123`, `123_BIS`, `A0123`…) ;
3. **valide chaque motif candidat par preuve spatiale** : le noyau
   extrait de l'identifiant doit correspondre à un nœud existant **ET**
   l'extrémité doit se trouver à ≤ 2 m du nœud cible. Une convention
   n'est retenue que si ≥ 3 occurrences la confirment toutes — une
   coïncidence isolée ou une ambiguïté (plusieurs nœuds candidats) ne
   produit jamais de lien ;
4. **ajuste la tolérance de snap** sur la distribution réelle des
   distances au nœud le plus proche : elle n'augmente (plafond 3 m) que
   si un cluster statistique net existe (≥ 8 échantillons, P75 ≤ 2,5 m),
   sinon 0,50 m est conservé ;
5. **persiste le résultat** dans `<fichier>.conventions.json` à côté du
   GPKG, verrouillé par taille + mtime — la découverte tourne une fois
   par fichier et est partagée par tous les consommateurs.

Le tout **sans aucune saisie utilisateur** : un utilisateur novice qui
dépose un fichier inconnu obtient le même traitement qu'un expert —
les conventions sont découvertes, appliquées et **tracées** (provenance
`alias_auto` dans le graphe, `raccordements_spatiaux` dans le `.inp`,
carte « Connectivité extrémités » de l'audit qualité).

Mesure sur le GPKG Ville réel : 95 extrémités non résolues analysées →
la convention de nommage des codes de rejet est redécouverte par le
mécanisme (alias + zéro-padding, distance 0,0 m), aucune convention
supplémentaire, snap 0,50 m conservé. Sur un fichier inconnu avec une
convention différente, la règle s'activerait automatiquement — ou rien
ne serait inventé et les extrémités resteraient flaggées.

### 7.3 Verdict d'import et audit

- `POST /api/v1/network/upload` renvoie `inventaire` (couches détectées,
  nb regards/conduites/rejets) → dialogue de verdict après import.
- `/api/v1/qualite/analyse` expose `statistiques_globales.connectivite` :
  extrémités totales, résolues par provenance (ID/alias/alias_auto/snap),
  spatiales à vérifier, absentes, taux de résolution, conventions
  découvertes. Mesuré sur le GPKG Ville : **99,85 %** des 20 590
  extrémités résolues, 31 spatiales (mineures), 0 absente.
- Le badge orphelins de la carte (partition Voronoï) reflète le même
  résolveur : plus que les vrais déconnectés (ex. 36 tronçons / 11 regards
  sur le jeu réel).
