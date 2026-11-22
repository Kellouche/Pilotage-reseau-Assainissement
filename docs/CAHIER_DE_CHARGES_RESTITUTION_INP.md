# CAHIER DES CHARGES : RESTITUTION HYDRAULIQUE EXACTE ET RÉCONCILIATION SWMM 5.2

> **Version** : 1.0 — consolidée le 22 novembre 2026
> **Statut** : contrat de référence pour le chantier GPKG → `.inp`
> **Base factuelle** : audit mesuré du GPKG réel (`Assainissement_Ville.gpkg`)
> **Documents liés** : `docs/MISSION_TOPOLOGIE_INP.md` (analyse & mesures),
> `docs/09_ENDPOINTS_DOCUMENTATION.md`, `AGENTS.md`

---

## 1. Objectif

Corriger les pertes d'informations hydrauliques entre le SIG source (GPKG)
et le moteur SWMM 5.2 de DrainPilot :

- modéliser les **pompes et refoulements** (aujourd'hui envoyés en gravité) ;
- restituer les **sections rectangulaires** et les **rugosités réelles** par matériau ;
- convertir les **déversoirs d'orage** en `[WEIRS]` ;
- garantir un **inventaire transparent 1:1** des éléments éligibles ;
- appliquer un **filet de secours spatial** uniquement aux tronçons orphelins.

**Principe non négociable** : aucune perte ni invention silencieuse — chaque
exclusion et chaque hypothèse est auditée et traçée dans la provenance.

---

## 2. Mesures de référence (audit du 22/11/2026)

| Objet | Mesure réelle |
|---|---|
| Canalisations actives | 10 295 (15 `désaffecté` exclues) |
| Regards / Rejets / Stations / Ouvrages | 10 538 / 79 / 5 / 38 |
| Connectivité par `ID_AMONT`/`ID_AVAL` | **20 375 / 20 550 extrémités (99,15 %)** |
| Extrémités orphelines | **175** (~0,85 %) — récupérables < 0,5 m : 164 (94 %) ; irrécupérables : ~11 |
| Conduites `FONCTIONMT='Refoulement'` | **12** (PEHD 315–630 mm, ID amont = code `SR_*`) |
| Stations de relevage | **5** (`SR_HH01`, `SR_HH02`, `SR_CL`, `SR_CH`, `SR_HC`) |
| `SR_CL` (Carmella) | station **sans refoulement** associé — à qualifier |
| Déversoirs d'orage | **21** (`TYPEOUVR='Déversoir d'orage'` sur 38 ouvrages) — mais `H_de_Seuil`/`loSeuil`/`LaSeuil` **NULL sur 34/38** → `[WEIRS]` = hypothèses tracées |
| Codes `RJxx` dans ID_AVAL | 73 — **absents** des tables de nœuds → exclusion `id_inconnu` |
| Attributs pompes (`NBPOMPE`, `PUISSP`, `HMTP`, `DEBTOTAL`, `VOLBACH`) | majoritairement **NULL** → courbes/seuils = hypothèses documentées |

---

## 3. Contraintes techniques SWMM 5.2 (vérifiées)

- **Pas de `FORCE_MAIN`** ni d'option Hazen-Williams/Darcy-Weisbach : le
  frottement est **Manning's n uniquement**, à surface libre comme sous pression.
- Une conduite de refoulement = un `[CONDUIT]` **alimenté par une `[POMPE]`** ;
  l'écoulement sous pression est calculé par le moteur, il n'existe pas de
  flag « conduite en charge ».
- **Toute pompe exige un ordre de marche** (`[CONTROLS]` ou `[RULES]`) —
  sans contrôle, SWMM la fait tourner en continu → débits inventés.
- `[STORAGE]` exige une courbe de stockage (volume vs cote) ; `[JUNCTION]`
  suffit pour une bâche simple.

---

## 4. Chantiers

### CHANTIER 1 — Refoulements, Pompes et Ouvrages Spéciaux (priorité immédiate)

#### 1.1 Refoulements & Pompes

- Détecter les canalisations `FONCTIONMT == 'Refoulement'` dont l'ID amont
  (`SR_xxx`, normalisation `_`/espace) correspond à une `Station_de_relevage`.
- Émettre `[PUMPS]` : nœud d'aspiration = nœud de bâche de la station,
  nœud de refoulement = `ID_AVAL` de la conduite.
- Émettre `[CURVES]` par station :
  - si `HMTP`/`PUISSANCE`/`DEBUNIT` renseignés → courbe type 1 (débit/hauteur) ;
  - sinon → courbe par défaut **tracée comme hypothèse** dans la provenance.
- Émettre `[CONTROLS]` ou `[RULES]` : marche/arrêt par niveau de bâche
  (`NBRBACHE`, `VOLBACH`, `PROFBACH`) ou règle simplifiée documentée.
- Le tronçon de refoulement reste un `[CONDUIT]` standard en aval de la pompe
  (l'écoulement sous pression est calculé, pas déclaré).
- Propager `FONCTIONMT` dans `graphe_reseau.py` (chaîne de `get` ligne ~155)
  pour désactiver l'inversion de sens sur ces tronçons.

#### 1.2 Nœud de station

- `[STORAGE]` si `VOLBACH`/`NBRBACHE` renseignés (volume de bâche réel),
  sinon `[JUNCTION]` avec emprise documentée.
- Cote = `COORDZ` du GPKG ; si absente → hypothèse tracée (ne plus émettre 101,000).
- `SR_CL` (Carmella) : qualifier avant modélisation — pas de refoulement
  associé → exclure avec motif ou traiter en nœud simple.

#### 1.3 Sections rectangulaires

- `FORMESECT` ≠ circulaire → `RECTANGULAR Geom1 Geom2` dans `[XSECTIONS]`
  (`Geom1` = `GDEBASE`, `Geom2` = `HAUTEUR` ; `PETBASE` si pertinent).

#### 1.4 Rugosités par matériau

| Matériau | Manning n |
|---|---|
| PEHD / PEHD annelé | 0,010 |
| PVC / PVC lisse | 0,011 |
| Fonte / Acier | 0,012 |
| Béton / Béton armé | 0,013–0,015 (choix documenté) |
| Inconnu / non mappé | 0,013 — **défaut tracé comme hypothèse** |

#### 1.5 Déversoirs d'orage (21)

- `TYPEOUVR='Déversoir d'orage'` → `[WEIRS]` seuil transversal.
- `H_de_Seuil`/`loSeuil`/`LaSeuil` majoritairement NULL → **hypothèses
  obligatoirement tracées** (valeur par défaut + justification), jamais
  présentées comme données GPKG.

### CHANTIER 2 — Bilan de réconciliation 1:1 & inventaire

- Inventaire avant/après filtrage de bassin :
  `Total SIG → Éligibles bassin → Modélisés INP → Exclus justifiés`
  (motifs : `desaffecte`, `hors_bassin`, `id_inconnu`, `orphelin`, `doublon`).
- Ventilation du parc par matériau, forme de section, classe de diamètre.
- Exposition : endpoint API + widget récapitulatif dans le Cockpit.
- **Zéro exclusion silencieuse** : chaque objet absent du `.inp` a un motif.

### CHANTIER 3 — Raccordement spatial ciblé des orphelins

- `ID_AMONT`/`ID_AVAL` conservés à 100 % quand renseignés et cohérents.
- Pour les **175 extrémités orphelines** uniquement : recherche spatiale
  de proximité ≤ 0,50 m (STRtree/KD-tree sur les nœuds valides).
- Chaque rattachement spatial est **audité** : `topologie_spatiale=true`,
  distance, nœud cible — visible dans la provenance.
- Les ~11 extrémités irrécupérables → nœud `N_X_Y` ou exclusion `orphelin`
  justifiée. Ne pas deviner les `RJxx` (codes absents des tables de nœuds).

### CHANTIER 4 — Validation, re-baselinage et CI

- Isolation multi-tenant stricte (`org_id` / `project_id` / snapshot).
- **Re-baselinage Golden Dataset documenté** : pompes, rugosités réelles et
  sections rectangulaires *vont* changer les résultats — nouveau golden avec
  justification par écart, pas suppression de tests.
- Validation `epa_example5_pumping.gpkg` : le `.inp` généré doit reproduire
  les pompes du modèle EPA de référence.
- Bilan de continuité massique < 1 % maintenu.
- `pytest` complet + `node --check` JS ; livraison Git Zero-Prompt.

---

## 5. Critères d'acceptation

| # | Critère |
|---|---|
| 1 | 100 % des objets **éligibles** dans le `.inp` ; chaque exclusion a un motif audité (désaffecté, hors bassin, id_inconnu, orphelin, doublon) |
| 2 | ≥ 99 % des extrémités connectées par ID ; orphelins résiduels = nœud spatial audité ou exclusion justifiée |
| 3 | Les 12 refoulements sont des `[PUMPS]`+`[CONDUITS]` avec `[CONTROLS]`/`[RULES]` ; les 5 stations ont courbe et cote réelles **ou hypothèses tracées** |
| 4 | Les 21 DVO sont des `[WEIRS]` ; seuils GPKG utilisés quand renseignés, sinon hypothèse tracée |
| 5 | Chaque hypothèse (courbe pompe, seuil DVO, nœud spatial, rugosité inconnue) figure dans la provenance et le rapport |
| 6 | Tests verts + Golden Dataset re-baseliné avec justification documentée |

---

## 6. Points de vigilance

1. **Multi-tenant** : aucune fuite inter-`org_id`/projet/snapshot.
2. **`src/domain/`** : les sections `[PUMPS]`/`[CURVES]`/`[WEIRS]` sont un
   **ajout** au générateur — ne pas modifier les équations Saint-Venant.
3. **Complétude** : les attributs pompes/DVO sont majoritairement NULL —
   l'UI et la provenance doivent distinguer **donnée GPKG** vs **hypothèse**.
4. **`SR_CL`** : qualifier avant modélisation — pas de refoulement associé.
5. **`RJxx`** : exclusion `id_inconnu`, jamais de devinette spatiale.
6. **Ordre** : l'honnêteté (exclusions auditées, FONCTIONMT propagé) précède
   la complexité (pompes, weirs) — ne pas cumuler les chantiers.

---

## 7. Livrables

- `.inp` du réseau réel avec `[PUMPS]`, `[CURVES]`, `[CONTROLS]`/`[RULES]`,
  `[XSECTIONS]` rectangulaires, rugosités par matériau, `[WEIRS]` DVO
- Bilan de réconciliation SIG ↔ INP (API + widget Cockpit)
- Audit d'exclusions complet (zéro silencieux)
- Provenance enrichie (hypothèses, rattachements spatiaux, pompes)
- Golden Dataset re-baseliné + note de justification
- `docs/` à jour
