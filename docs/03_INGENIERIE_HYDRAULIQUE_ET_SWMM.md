# 03 — Ingénierie Hydraulique & Moteur SWMM 5.2

> **DrainPilot 5.2** — Document de référence scientifique et opérationnel.
>
> **Audience** : ingénieurs hydrauliciens, modélisateurs SWMM, hydrologues, chercheurs, bureaux d'études, auditeurs.
> **Contenu** : cadre scientifique Saint-Venant 1D, démarche hydrologique (Voronoï, Horton), référentiel pluviométrique Algérie, découverte adaptative des conventions GPKG, chaîne canonique de résolution à 6 provenances, restitution physique fidèle du `.inp`, réconciliation 1:1, diagnostic et restitution.
> **Règle d'or** : les chiffres cités sont **mesurés sur des données réelles de projets** — ils illustrent le comportement du moteur, mais **chaque projet client possède son propre réseau, son propre GeoPackage et ses propres résultats**. Les mesures proviennent d'un cas de référence (le réseau « Ville », utilisé comme jeu de démonstration de production) ; elles ne décrivent pas un « projet par défaut » de la plateforme. Toute évolution des algorithmes impose de les remesurer avant mise à jour.
>
> **Principe d'isolation** : aucune donnée, mesure ou synthèse d'un projet n'est générique — l'inventaire, la connectivité, les exutoires et les résultats de chaque tenant sont strictement propres à son `org_id`/`project_id` (voir Doc 2 §3).

---

## 1. Cadre Scientifique & Résolution Hydraulique 1D

### 1.1 Moteur de calcul

Le cœur de calcul est le moteur officiel **EPA SWMM 5.2.4 x64** via `pyswmm` et le C-Toolkit standard. L'algorithme hydrodynamique est l'**onde dynamique (DYNWAVE)** : résolution simultanée des équations de Saint-Venant 1D en régime transitoire non permanent.

**Équation de continuité :**
$$\frac{\partial A_c}{\partial t} + \frac{\partial Q}{\partial x} = 0$$

**Équation de quantité de mouvement :**
$$\frac{\partial Q}{\partial t} + \frac{\partial}{\partial x}\left(\frac{Q^2}{A_c}\right) + g A_c \frac{\partial H}{\partial x} + g A_c S_f = 0$$

avec la pente de frottement de Manning-Strickler :
$$S_f = \frac{n^2 |Q| Q}{A_c^2 R_h^{4/3}}$$

**Nomenclature des paramètres :**

| Symbole | Signification | Unité |
|---|---|---|
| $A_c$ | Section mouillée de l'écoulement | m² |
| $Q$ | Débit instantané | m³/s |
| $H$ | Cote piézométrique (charge) | m |
| $S_f$ | Pente de frottement | m/m (sans unité) |
| $n$ | Coefficient de rugosité de Manning | s/m$^{1/3}$ (fonction du matériau) |
| $R_h$ | Rayon hydraulique ($A_c / P$) | m |

> **Référence** : équations de Saint-Venant 1D résolues par le moteur
> dynamique d'EPA SWMM 5.2 — *EPA SWMM 5.2 User's Manual*, chapitre
> « Hydraulic Computation » (modèle onde dynamique, `DYNWAVE`).

> ⚠️ **Invariance hydraulique** : ces équations ne sont jamais modifiées par le SaaS. La plateforme ajoute de la donnée et de la traçabilité autour du moteur — jamais d'approximation logicielle des lois physiques. Le Golden Master (`tests/test_golden_master.py`) verrouille la non-régression.

### 1.2 Critères de validité

- **Bilan de continuité massique** : erreur < ±5 % exigée par l'US EPA ; mesurée à **−0,166 %** (routage) et **−4,182 %** (ruissellement) sur le réseau de référence (cas d'illustration — chaque projet produit son propre bilan).
- **Invariant produit** : les bilans de masse restent strictement tracés dans chaque `.rpt` archivé.

### 1.3 Interopérabilité `.inp`

- **Export** : section `[MAP]` injectée avec `DIMENSIONS` calculées sur l'emprise UTM + marge 8 % → ouverture directe dans EPA SWMM Desktop.
- **Ingestion** : parsing modulaire (`src/domain/inp_parser.py`) des sections `[JUNCTIONS]`, `[OUTFALLS]`, `[STORAGE]`, `[CONDUITS]`, `[XSECTIONS]`, `[SUBCATCHMENTS]`, `[COORDINATES]`, `[VERTICES]`, `[POLYGONES]` ; détection automatique du CRS ; conversion en GeoPackage standard.

### 1.4 Formats d'entrée : `.inp` natif, GPKG/SHP/ZIP acceptés avec réserves

> ⚠️ **Règle de référence** : le **modèle de calcul de référence est le fichier `.inp` EPA SWMM 5.2** — c'est le format dans lequel toutes les sections hydrauliques (pompes, weirs, sections, contrôles) sont exprimées sans perte et c'est le format d'export officiel du moteur.

La plateforme accepte aussi l'ingestion de données SIG hétérogènes — **GeoPackage (`.gpkg`)**, **Shapefile (`.shp` + `.shx`/`.dbf`/`.prj`/`.cpg` ou `.zip`)**, GeoJSON et couches auxiliaires — mais **la conversion vers le modèle `.inp` peut avoir des conséquences sur la transformation des données** :

- **Perte potentielle d'attributs** : champs non reconnus par le schéma cible (matériau absent, cotes manquantes, sections non standard) sont soit ignorés, soit remplacés par des **hypothèses tracées** — jamais silencieuses (voir §6.5).
- **Reconstruction topologique** : les extrémités non résolues par identifiant suivent la chaîne canonique §5 (alias → snap adaptatif → spatial → absent) ; chaque rattachement est audité mais **un rattachement spatial n'a pas la même valeur probante qu'une connectivité déclarée par ID**.
- **Sections et ouvrages** : formes non circulaires, déversoirs, refoulements et stations ne sont restitués que si les attributs sources le permettent ; sinon l'écart est consigné dans le bilan de réconciliation §7.
- **Conséquence pratique** : un `.inp` fourni par un bureau d'études et réimporté ne subit **aucune conversion de modèle** — il est parsé puis resimulé tel quel ; en revanche un GPKG/SHP importé passe par le générateur `.inp` de DrainPilot, et **le résultat peut différer** du modèle d'origine si les données SIG étaient incomplètes ou ambigües.

> **Recommandation d'ingénierie** : pour une étude contractuelle, privilégier l'export `.inp` final pour la restitution et l'archivage ; utiliser le GPKG/SHP comme source d'inventaire et de géométrie, pas comme vérité hydraulique absolue.

---

## 2. Démarche Hydrologique & Sectorisation de Surface

### 2.1 Sous-bassins par polygones de Voronoï / Thiessen

Chaque regard de visite $N_i$ est le récepteur hydrologique d'un sous-bassin élémentaire $SB_i$ :

$$\mathcal{V}(N_i) = \{ p \in \Omega \mid \|p - N_i\| \le \|p - N_j\|, \ \forall j \ne i \}$$

- Enveloppe $\Omega$ bornée par le buffer morphologique du réseau (**35 m** autour des canalisations et regards).
- Propriétés calculées par sous-bassin : surface drainée $A$ (ha), largeur hydraulique $W = \sqrt{A}$, pente moyenne $S$ (0,5 % par défaut), coefficient d'imperméabilisation **70 %** en zone urbaine dense.
- **Codification** : sous-bassin `SB_<code regard>`, exutoire = le regard ; regard = code SIG patrimonial conservé (traçabilité ITV/plans de récolement) ; conduites affichées `amont → aval`.

### 2.2 Infiltration de Horton

$$f(t) = f_c + (f_0 - f_c) e^{-k t}$$

| Paramètre | Valeur |
|---|---|
| $f_0$ (capacité initiale) | 75,0 mm/h |
| $f_c$ (capacité ultime) | 10,0 mm/h |
| $k$ (décroissance) | 4,0 h⁻¹ |
| Temps de ressuyage | 7,0 jours |

### 2.3 Apports de temps sec (DWF)

Injection multi-profils (domestique, industriel, continu) avec réconciliation GPKG et sélecteur cartographique — endpoints `/api/v1/apports/*` (voir Doc 2 §4.7).

---

## 3. Référentiel National Pluviométrique d'Algérie

Données certifiées **ANRH / UHBC / ONA / ONM** — fichier source `data/referentiel_pluviometrie_algerie.json`, module `src/domain/referentiel_pluvio.py`.

### 3.1 Cadre réglementaire ONA

| Période de retour | Application |
|---|---|
| $T = 2$ ans (biennale) | Exploitation courante, confort urbain |
| **$T = 10$ ans (décennale)** | **Standard obligatoire ONA** — collecteurs principaux, surface libre |
| $T = 20$ ans (vicennale) | Orages convectifs, tolérance mise en charge sans submersion |
| $T = 50$ ans (cinquantennale) | Résilience points bas, bassins d'orage |
| $T = 100$ ans (centennale) | Crues exceptionnelles, sécurité exutoires |

### 3.2 Formulations

- **Montana** : $I(t) = a \cdot t^{-b}$ → en mm/h : $I = 60 \cdot a \cdot t^{-b}$.
- **Hyétogramme de Chicago centré** : pic à $r = 0{,}40$ de la durée (typique des orages convectifs méditerranéens du Chéliff).
- **Contrôle pluie-débit** : comparaison automatique $Q_{\text{sim}}$ (Saint-Venant) vs méthode rationnelle $Q_{\text{rat}} = C_{\text{eff}} \cdot I_{\max} \cdot A_{\text{urb}} / 360$.

### 3.3 Stations de la Wilaya de Chlef (Bassin 01 Chélif-Zahrez)

| Station | Code ANRH | Alt. | $P_{24}$ ($T{=}10$) | $a$ ($T{=}10$) | $b$ ($T{=}10$) | $I_{\max}(15\text{ min})$ |
|---|---|---|---|---|---|---|
| Chlef Siège (Ech-Cheliff) | `010501` | 154 m | 56,0 mm | 9,334 | 0,745 | 74,9 mm/h |
| Pontéba (Oum Drou) | `010502` | 142 m | 54,0 mm | 9,020 | 0,748 | 72,0 mm/h |
| Oued Fodda | `010505` | 180 m | 62,0 mm | 9,850 | 0,742 | 78,5 mm/h |
| Bénaïria (Dahra) | `010508` | 480 m | 72,0 mm | 11,200 | 0,738 | 89,0 mm/h |
| Domaine Si Tayeb | `010512` | 165 m | 55,0 mm | 9,250 | 0,746 | 74,0 mm/h |
| Ténès (Littoral) | `010520` | 15 m | 68,0 mm | 10,450 | 0,740 | 83,5 mm/h |
| Boukadir (Bas Chélif O.) | `010525` | 110 m | 52,0 mm | 8,850 | 0,750 | 70,5 mm/h |

**Station de référence Chlef Siège — Montana par période de retour :**

| $T$ | $a$ | $b$ | $I_{\max}(15\text{ min})$ | $P_{24}$ |
|---|---|---|---|---|
| 2 ans | 5,250 | 0,720 | 45,0 mm/h | 34,0 mm |
| 5 ans | 7,107 | 0,733 | 58,5 mm/h | 45,0 mm |
| **10 ans** | **9,334** | **0,745** | **74,9 mm/h** | **56,0 mm** |
| 20 ans | 11,823 | 0,752 | 92,5 mm/h | 66,5 mm |
| 50 ans | 15,795 | 0,760 | 120,0 mm/h | 81,0 mm |
| 100 ans | 19,338 | 0,764 | 144,5 mm/h | 94,0 mm |

Stations régionales complémentaires : Khemis Miliana (Aïn Defla), Mascara-Ghriss, Alger Port/Cap Caxine, Oran Es-Sénia, Constantine Aïn El Bey.

### 3.4 Alerte BMS & traçabilité

Bulletin météo ONM (vigilance jaune/orange/rouge) → hyétogrammes en cloche ou triangulaires avec marge de vidange ; ordres de mission de curage préventif PDF. **Chaque simulation conserve en métadonnées** : station, code ANRH, coefficients Montana, $P_{24}$ — traçabilité intégrale dans les rapports.

---

## 4. Stratégie d'Ouverture des GeoPackages & Découverte Autonome

> **Principe fondateur** : l'utilisateur ne saisit **aucune convention** — le système lit, analyse et découvre seul les conventions de nommage et la tolérance de snap de chaque fichier, puis les **trace**.

Module : `src/domain/topologie/decouverte_conventions.py` (`obtenir_conventions(gpkg_path)`).

### 4.1 Méthode générique d'inférence (adaptative, sans configuration)

La découverte est **générique** : elle ne présuppose aucune convention. Pour tout GeoPackage — export SIG, shapefile converti, fichier propriétaire — le système :

1. **Collecte les extrémités non résolues** par la chaîne de base (ID strict + alias connus + snap par défaut).
2. **Analyse les motifs d'identifiants** en échec : tout préfixe, suffixe, séparateur ou zéro-padding est candidat — le mécanisme n'a pas de liste de conventions codée en dur.
3. **Valide chaque motif par preuve spatiale** : le noyau extrait doit correspondre à un nœud existant **et** l'extrémité doit se trouver à ≤ 2 m du nœud cible ; une convention n'est retenue que si **≥ 3 occurrences** la confirment toutes — coïncidence isolée ou ambiguïté ⇒ jamais de lien.
4. **Ajuste la tolérance de snap** sur la distribution réelle des distances : elle n'augmente (plafond **3,0 m**) que sur cluster statistique net (≥ 8 échantillons, P75 ≤ 2,5 m) ; sinon **0,50 m** est conservé. Le snap n'est jamais arbitraire.
5. **Persiste le résultat** dans `<fichier>.conventions.json` à côté du GPKG (verrou taille + mtime) — découverte une fois par fichier, partagée par graphe, `.inp` et audit qualité.

### 4.2 Mesures réelles — exemple sur le réseau « Ville »

> **Attention — cas d'illustration** : les chiffres ci-dessous proviennent
> d'**un projet réel précis** (le réseau « Ville », GeoPackage
> `Assainissement_Ville.gpkg`, ~10 300 canalisations et ~10 500 regards).
> Ils servent à montrer l'ordre de grandeur et le comportement du
> résolveur sur un jeu de production exigeant — **ils ne sont pas des
> valeurs par défaut de la plateforme**. Chaque projet importé produit
> ses propres mesures via `/api/v1/qualite/analyse`.

| Provenance | Extrémités | Part |
|---|---|---|
| `id` (identifiant strict) | 20 405 | 99,10 % |
| `alias` / `alias_auto` | 79 + 75 | 0,75 % |
| `snap` | (inclus ci-dessus) | — |
| `spatial` (nœud créé, à vérifier) | 31 | 0,15 % |
| `absent` | **0** | 0 % |
| **Total** | **20 590** | **99,85 % résolues** |

Sur ce même réseau de référence, la convention de nommage des codes de rejet est redécouverte par le mécanisme (distance mesurée 0,0 m) ; aucune convention supplémentaire ; snap 0,50 m conservé. Sur un autre projet, les conventions découvertes et la tolérance de snap sont **propres à son fichier** — conservées dans son propre `<fichier>.conventions.json`.

---

## 5. Chaîne Canonique de Résolution des Extrémités

Source unique : `src/domain/topologie/resolution_noeuds.py` (`ResoluteurNoeuds`), consommée **à l'identique** par le graphe de bassins (`graphe_reseau.py`), le générateur `.inp` (`sections_inp.py`) et l'audit qualité (`analyse_qualite_gpkg.py`).

### 5.1 Les 6 provenances tracées

```
id → alias (codé) → alias_auto → snap → spatial → absent
```

| Provenance | Signification | Traçabilité |
|---|---|---|
| `id` | Identifiant texte résolu directement | graphe + audit |
| `alias` | Alias sémantique codé (convention connue) | graphe + audit |
| `alias_auto` | Correspondance par noyau **découverte automatiquement** | graphe + `.conventions.json` + audit |
| `snap` | Raccordement spatial ≤ tolérance adaptative | `raccordements_spatiaux` dans `.inp` |
| `spatial` | Nœud spatial créé à la coordonnée réelle (à vérifier) | comptabilisé, jamais silencieux |
| `absent` | Non résolu — extrémité flaggée | inventoriée orpheline |

**Consommateurs** : graphe (`graphe_reseau.py`), sections `.inp` (`sections_inp.py`), audit qualité (`analyse_qualite_gpkg.py` expose `statistiques_globales.connectivite` avec ventilation par provenance).

### 5.2 Inventaire des orphelins

L'endpoint `GET /api/v1/network/orphelins` (Doc 2 §4.2) expose trois catégories :

- **Nœuds isolés** : déclarés dans le SIG sans aucune conduite connectée (degré 0 dans le graphe) — type, nom, voie, commune, coords WGS84.
- **Conduites hors graphe** : exclues car une extrémité n'a pas été résolue — `G.graph['conduits_non_graphes']` conserve cle/index, extrémités brutes et résolues, motif (`amont`/`aval` manquant), longueur, diamètre, centroïde.
- **Arêtes de composantes sans exutoire** : sous-réseaux connexes qui ne drainent vers aucun exutoire officiel.

À titre d'exemple, sur le réseau « Ville » : **242 nœuds isolés + 14 tronçons hors graphe** — chacun localisable en un clic depuis l'onglet Orphelins de `/carte`. Sur un autre projet, l'inventaire affiché est celui de **son** graphe, calculé à la demande.

### 5.3 Garde-fous topologiques

- `FONCTIONMT='Refoulement'` bloque toute inversion topologique artificielle du sens d'écoulement.
- Snap spatial **ciblé** (KD-tree/STRtree) uniquement pour les extrémités non résolues — jamais de reconstruction spatiale globale (la connectivité par ID est fiable à 99 %+).
- Isolation stricte par `org_id`/`project_id`/snapshot — le cache du graphe est clé par `empreinte SHA-256|chemin` du GPKG.
- Raccordements candidats des nœuds orphelins : revue **P1** (`suspects-ecoulement`) et scoring **P2** (`raccordements-orphelins`) — jamais de lien inventé silencieusement.

---

## 6. Restitution Physique Fidèle dans le `.inp` SWMM 5.2

### 6.1 Contraintes SWMM 5.2 vérifiées (à ne jamais oublier)

- **Pas de `FORCE_MAIN`** ni Hazen-Williams/Darcy-Weisbach : frottement **Manning's n uniquement**.
- Une conduite de refoulement = `[CONDUIT]` **alimenté par une `[POMPE]`** ; l'écoulement sous pression est calculé, pas déclaré.
- **Toute pompe exige un ordre de marche** (`[CONTROLS]`/`[RULES]`) — sans contrôle, SWMM la fait tourner en continu → débits inventés.
- `[STORAGE]` exige une courbe de stockage ; `[JUNCTION]` suffit pour une bâche simple.
- `[WEIRS]` exige une section `RECT_OPEN` dans `[XSECTIONS]` (seule forme valide pour weirs SWMM 5.2).
- Sections non circulaires : `RECT_CLOSED Geom1 Geom2` (jamais `RECTANGULAR` — ERROR 205).
- Courbes pompe : `PUMP1` à `PUMP5` uniquement (jamais `PUMP` — ERROR 205).

### 6.2 Refoulements & stations de relevage

- Conduites `FONCTIONMT='Refoulement'` → **1 pompe `[PUMPS]` par tête de chaîne** (`PUMP3`, courbe hauteur-débit), nœud intermédiaire `N_REF_*` en `[JUNCTIONS]`, tronçons aval en `[CONDUITS]` sous pression avec rugosité Manning.
- **Règle de non-surpompage** : les segments aval d'une même chaîne restent des conduites — pas de pompe en série (sur le réseau de référence : 5 pompes par tête de chaîne au lieu de 12 pompes naïves).
- Régulation par niveaux de bâche (marche/arrêt 0,300 / 0,100 m) ; courbes issues des attributs fabricant quand renseignés, sinon **hypothèses tracées**.
- Cotes des stations = `COORDZ` du GPKG (plus de 101,000 m artificiel) ; `VOLBACH`/`NBRBACHE` → `[STORAGE]` si données complètes, sinon `[JUNCTION]` documentée.

### 6.3 Déversoirs d'orage (DVO)

- `TYPEOUVR='Déversoir d'orage'` → `[WEIRS]` seuil transversal + `RECT_OPEN` obligatoire.
- Seuils (`H_de_Seuil`/`loSeuil`/`LaSeuil`) majoritairement NULL → valeurs par défaut **tracées comme hypothèses**, jamais présentées comme données GPKG.

### 6.4 Sections & rugosités

- `FORMESECT` non circulaire → `RECT_CLOSED Geom1 Geom2` (`Geom1` = hauteur, `Geom2` = largeur).
- Rugosité par matériau : PEHD 0,010 · PVC 0,011 · Fonte/Acier 0,012 · Béton 0,013–0,015 · inconnu → 0,013 **défaut tracé**.

### 6.5 Règle d'or de la restitution

**Zéro perte silencieuse** : chaque objet absent du `.inp` a un motif typé (`desaffecte`, `hors_bassin`, `id_inconnu`, `orphelin`, `doublon`) ; chaque hypothèse d'ingénierie (courbe pompe, seuil DVO, nœud spatial, rugosité inconnue, injection de cote terrain) figure dans la provenance et le rapport. La distinction **donnée GPKG vs hypothèse** est affichée dans l'UI.

---

## 7. Bilan de Réconciliation 1:1 & Registre d'Audit

- **Équilibre comptable** : `Total SIG = Modélisés INP + Exclus justifiés + Ajouts techniques (pompes, nœuds N_REF)`.
- Endpoint dédié : `GET /api/v1/simulations/reconciliation` — inventaire SIG vs INP, ventilation du parc (matériau, forme, diamètre), hypothèses appliquées.
- Exposition cockpit : widget de bilan + export ; audit d'exclusions complet.
- Snapshots GPKG versionnés par SHA-256 : une simulation archivée reste rejouable sur **exactement** le réseau qui l'a produite.

---

## 8. Diagnostic Avancé, Cartographie & Restitution

### 8.1 Profil en long hydraulique (HGL)

- Extraction exclusive des cotes piézométriques depuis le `.out` binaire (`node_hydraulics`) — jamais recalculée.
- Représentation : terrain naturel, radier, généatrice supérieure, **plan d'eau réel WSP**, ligne de charge HGL, hachures de mise en charge, pastille de débordement.
- Chemin topologique orienté par graphe (Dijkstra) entre deux nœuds choisis.

### 8.2 Surcharge vs débordement (formalisme)

- **Surcharge** : `z_radier + D < HGL ≤ z_tampon` — eau sous pression confinée, pas d'inondation.
- **Débordement** : `HGL > z_tampon` — voirie submergée ; SWMM chiffre débit crête, durée, volume.
- **Paradoxe hydraulique expliqué** : goulot amont (petit diamètre ∝ D^8/3, pente faible, temps de concentration court, laminage Saint-Venant) coexistant avec exutoire calme — comportement physique, pas anomalie.

### 8.3 Cartographie thématique & animation

- Taux de charge `Q/Q_max` : <50 % vert · 50-80 % jaune · 80-100 % orange · ≥100 % rouge (sous pression).
- Regards : surcharge orange / débordement rouge clignotant ; chevrons de sens d'écoulement cyan (désactivés par défaut).
- **Time slider** : animation autonome de l'onde de crue (Q(t), y(t) par pas de calcul), synchronisation cartographique dynamique, lecture ×1/×2/×5.
- **Hyétogramme ↔ hydrogramme** : pluie Montana/Chicago (axe inversé) vs crue Saint-Venant, lag time, volumes, coefficient de ruissellement effectif.

### 8.4 Registres de revue humaine (Human-in-the-Loop)

- **Cotes suspectes** : suspension préventive du tracé en cas d'altitude aberrante jusqu'à validation hydraulicien (`/api/v1/simulations/cotes-suspectes`).
- **Sens d'écoulement suspects** : file de revue P1 sur couches altimétriques (`suspects-ecoulement`).
- **Raccordements orphelins** : scoring P2 des candidats de connexion.
- **Injection opt-in de cotes terrain** : les points topographiques des couches satellite peuvent enrichir l'interprétation du terrain — tracée, jamais silencieuse (`regards-terrain`, `apercu-inp`).

### 8.5 Inventaire orphelins opérationnel

Onglet **Orphelins** de `/carte` : listing filtrable des nœuds isolés et tronçons hors graphe/sans exutoire ; clic → centrage zoom 18 + marqueur pulsant + popup sur la carte active (quel que soit le contexte cartographique).

### 8.6 Rapports

- **Profil en long PDF**, rapport diagnostic multi-agents A4 (5 domaines : causal hydraulique, prescriptions génie civil, GDO, matrice de risques P1/P2/P3, analyse techno-économique BPU/VAN/TRI), ordre de mission BMS, exports `.inp`/`.rpt` officiels.
- Chaîne multi-agents : garde-fou, diagnostic, génie civil, GDO, risques, finance BPU, synthèse.
