# MISSION D'INGÉNIERIE : TRANSFERT FIDÈLE GPKG → SWMM 5.2 « ZÉRO PERTE »

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
| Rejets | 79 — les codes `RJxx` des ID_AVAL (73) sont **absents** des tables de nœuds |

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
5. **Les 73 codes `RJxx`** : absents des tables de nœuds — probablement des
   rejets d'un jeu plus ancien ; à exclure avec motif `id_inconnu`, pas à
   deviner spatialement.
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
