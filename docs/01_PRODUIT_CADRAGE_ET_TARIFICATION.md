# 01 — Produit, Cadrage & Tarification

> **DrainPilot 5.2** — Plateforme Collaborative de Gestion Dynamique, Diagnostic de Qualité, Alerte Prédictive BMS et Modélisation Hydraulique des Réseaux d'Assainissement & Eaux Pluviales.
>
> **Audience** : décideurs, maîtres d'ouvrage, bureaux d'études, exploitants, commerciaux, étudiants.
> **Contenu** : vision et proposition de valeur, personas et parcours, gouvernance des rôles, garanties métier, grille tarifaire, périmètre MVP, glossaire unifié.
> **Références techniques** : l'architecture est détaillée dans [02_ARCHITECTURE_SYSTEME_ET_API.md](02_ARCHITECTURE_SYSTEME_ET_API.md), la science hydraulique dans [03_INGENIERIE_HYDRAULIQUE_ET_SWMM.md](03_INGENIERIE_HYDRAULIQUE_ET_SWMM.md), l'exploitation dans [04_EXPLOITATION_OPERATIONS_ET_ROADMAP.md](04_EXPLOITATION_OPERATIONS_ET_ROADMAP.md).

---

## 1. Vision Stratégique & Proposition de Valeur

### 1.1 Constat métier

L'exploitation, la gestion patrimoniale et la modélisation hydraulique des réseaux d'assainissement (eaux usées, eaux pluviales et réseaux unitaires) se heurtent à des ruptures opérationnelles majeures :

- **Des données SIG hétérogènes et polluées** : les bases géospatiales contiennent fréquemment des inversions de pente (contre-pentes), des nœuds orphelins, des doublons de regards, des diamètres non renseignés et des cotes de radier manquantes — rendant toute modélisation impossible sans semaines de nettoyage manuel.
- **Le cloisonnement entre bureau d'études et agents de terrain** : les relevés d'inspection télévisée (ITV), les campagnes de curage et les constats terrain restent consignés dans des bordereaux papier ou des fichiers isolés, sans réconciliation dynamique avec le modèle hydraulique.
- **La complexité des outils de modélisation** : le moteur de référence mondial **EPA SWMM 5.2** exige une expertise pointue pour construire manuellement les fichiers `.inp`, délimiter les bassins versants et paramétrer les pluies de projet.
- **La vulnérabilité accrue aux inondations urbaines** : face à l'imperméabilisation croissante et aux épisodes pluvieux intenses, les collectivités manquent d'un outil prédictif rapide pour localiser les goulots d'étranglement, dimensionner les bassins de rétention et évaluer l'impact des débordements en surface.

### 1.2 Mission

DrainPilot 5.2 unifie l'analyse géospatiale, le contrôle qualité de données, la simulation hydraulique d'assainissement, l'alerte prédictive météo et la collecte mobile terrain dans une plateforme cloud collaborative unique :

> *Permettre à chaque gestionnaire, régie communale et bureau d'études d'assainissement d'auditer la qualité de ses réseaux, de modéliser les écoulements de temps sec et de temps de pluie via le moteur certifié EPA SWMM 5.2 (Saint-Venant 1D), d'anticiper les crues extrêmes et de synchroniser les données de terrain — directement dans le navigateur et sur smartphone.*

### 1.3 Capacités fonctionnelles de la plateforme

1. **Audit automatique de la qualité géospatiale** de réseaux de plus de 10 000 regards et collecteurs (contre-pentes, sauts de radier, doublons, débits nominaux NP 650 et Manning-Strickler).
2. **Analyse morphologique par MNT et nuages altimétriques réels** pour caler les cotes de terrain et orienter les écoulements de surface.
3. **Simulation dynamique sur le moteur officiel EPA SWMM 5.2** (Saint-Venant 1D `DYNWAVE`) : crues, tronçons saturés, volumes d'inondation en surface.
4. **Alertes météorologiques réelles (BMS)** et ordres de mission terrain préventifs de curage.
5. **Apports de temps sec (DWF)** multi-profils (domestique, industriel, continu) avec sélection cartographique interactive.
6. **Extraction de sous-réseaux par pochoir spatial** selon une règle stricte d'intersection produisant une archive clé en main.
7. **Chaîne d'expertise multi-agents** consolidée dans un rapport d'audit PDF A4.
8. **Synchronisation terrain temps réel** en mode déconnecté (Offline-First) avec audit trail immuable.
9. **Inventaire des éléments orphelins** (regards isolés, tronçons hors graphe ou sans exutoire) avec localisation cartographique cliquable.

### 1.4 Différenciateurs stratégiques

1. **Rigueur scientifique intégrale** : le cœur de calcul repose sur le moteur officiel **EPA SWMM 5.2** via `pyswmm` et le C-Toolkit standard — Saint-Venant (onde dynamique et cinématique), pertes de charge singulières et Manning-Strickler sans approximation logicielle.
2. **Double échelle bureau-terrain native** : synchronisation bidirectionnelle mobile sécurisée avec traçabilité complète.
3. **Intelligence topologique hybride** (vecteur + MNT raster) : croisement automatique du réseau souterrain avec le relief de surface.
4. **Architecture SaaS multi-tenant industrielle** : cloisonnement strict par organisation, API FastAPI, calcul asynchrone Celery/Redis, stockage objet S3/MinIO.
5. **Souveraineté et portabilité totales** : stack 100 % libre, déployable On-Premise ou Cloud souverain via conteneurs, sans licence Esri/InfoWorks.

---

## 2. Personas Cibles & Parcours Utilisateurs

| Persona | Profil & contexte | Pain points | Apport DrainPilot |
|---|---|---|---|
| **Ingénieur Exploitation & Régie** | Régie publique, opérateur délégataire | Débordements récurrents, plaintes riverains, obstructions | Cartographie interactive, tronçons en surpression, inventaire des orphelins, priorisation des curages |
| **Chef de projet BET / Ingénieriste** | Bureau d'études, SDA, zonage pluvial | Préparation fastidieuse des `.inp`, vérification de milliers de cotes | Générateur automatique depuis GeoPackage, détection d'anomalies, découpage MNT, réconciliation 1:1 |
| **Technicien & agent terrain** | Équipe mobile d'intervention | Relevés papier perdus, formulaires non géolocalisés | Application mobile connectée/déconnectée, correction d'attributs au pied du regard, photos, guidage topologique |
| **Chercheur / Enseignant / Étudiant** | Université, laboratoire, formation | Accès à un moteur de référence sans infrastructure | Plan Académique (grille §4), moteur SWMM réel sur petits réseaux, résultats traçables et reproductibles |
| **Directeur services techniques / Élu** | Collectivité, EPCI | Manque de visibilité patrimoniale, arbitrages budgétaires | Tableaux de bord de santé du réseau (score 0-100), indicateurs de risque, rapports d'audit prêts pour comités |

### Parcours 1 — Diagnostic qualité express d'un réseau SIG

Connexion → ingestion GeoPackage/Shapefile/`.inp` → audit automatique (contre-pentes, regards doublons < 2 m, nœuds borgnes, connexions amont-aval) → score de santé 0-100 et anomalies géolocalisées sur la carte avec filtres de sévérité.

### Parcours 2 — Modélisation pluviale & prévention des inondations

Réseau validé → chargement du MNT → sous-bassins versants automatiques → pluie de projet (période de retour, IDF) → génération `.inp` → simulation asynchrone → visualisation des conduites saturées ($Q/Q_{max} > 1$), regards en débordement, hydrogrammes aux exutoires.

### Parcours 3 — Campagne terrain & mise à jour mobile déconnectée

Technicien → synchronisation de la zone en cache local → corrections et signalements avec photos hors-ligne → push différentiel au retour réseau → résolution des conflits et audit trail.

### Parcours 4 — Rapport de schéma directeur & restitution

Sélection d'un bassin ou de la commune → profil en long hydraulique (terrain, radier, ligne de charge) → rapport PDF haute fidélité → export GeoPackage corrigé et `.inp` certifié.

---

## 3. Gouvernance & Modèle de Rôles

Cinq rôles coexistent dans chaque organisation, combinés au **plan d'abonnement** (feature gating, §4) :

| Rôle | Droits |
|---|---|
| **Super-administrateur plateforme** (`is_superadmin`) | Console opérateur `/api/v1/admin/*`, validation des bons de commande B2B/B2G, émission des licences `SP-LIC-YYYY-…`, suivi du parc abonnés |
| **Direction / Responsable régie** (`owner` / `admin`) | Gestion des membres, factures proforma DZD/EUR, bons de commande, activation des abonnements |
| **Ingénieur d'études** (`engineer`) | Import GeoPackage/Shapefiles/MNT, détection d'anomalies, bassins versants, modèles SWMM 5.2, simulations, rapports |
| **Opérateur & technicien terrain** (`field_operator`) | Synchronisation mobile, correction des cotes de radier, signalement d'anomalies avec photos |
| **Observateur** (`viewer`) | Consultation cartographique et rapports en lecture seule |

L'authentification repose sur hachage **Argon2id** et double session JWT/cookie HTTP-only — voir [ADR 0001](adr/0001-authentification-fastapi-argon2-jwt.md).

---

## 4. Garanties Métier & Filet de Sécurité

### 4.1 La promesse : on déménage l'usine, on ne touche pas aux machines

La transformation en SaaS s'apparente au **déménagement d'une usine** dans un site moderne, sécurisé et secouru :

- **On déplace les machines sans les démonter ni altérer leurs réglages** : le moteur EPA SWMM 5.2, les algorithmes géométriques, le calcul des pentes, la détection des contre-pentes et la méthode NP 650 restent rigoureusement identiques.
- **Ce qui change, c'est uniquement le bâtiment d'accueil** : stockage centralisé, accès par comptes chiffrés, calculs en arrière-plan.

| Ce qui change (infrastructure) | Ce qui ne change jamais (cœur physique) |
|---|---|
| Fichiers locaux `.db` → PostgreSQL/PostGIS + objets S3/MinIO | Moteur EPA SWMM 5.2 via `pyswmm` et C-Toolkit |
| Accès libre local → cloisonnement `org_id` étanche | Lois physiques : Saint-Venant, Manning-Strickler, NP 650 |
| Écran figé → calculs asynchrones | Détection des contre-pentes, diamètres nuls, orphelins, sauts de cote |
| Installation PC → navigateur sans installation | Graphe topologique amont-aval, clusters, bassins versants |
| Relevés papier → mobile synchronisée | Cotes piézométriques, débits de pointe, débordements |

### 4.2 Le filet de sécurité en 5 couches

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       LE FILET DE SÉCURITÉ EN 5 COUCHES                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. PHOTO DE RÉFÉRENCE (« Golden Master ») : valeurs figées avant travaux   │
│ 2. CONTRÔLE AUTOMATIQUE SYSTÉMATIQUE : tests de non-régression au mm       │
│ 3. JALONS AVEC VALIDATION HUMAINE : approbation explicite à chaque phase   │
│ 4. RETOUR ARRIÈRE PERMANENT (Git) : restauration instantanée possible      │
│ 5. AUDIT TRAIL TOTAL : journalisation infalsifiable de chaque calcul       │
└─────────────────────────────────────────────────────────────────────────────┘
```

1. **Golden Master** : avant tout chantier de transformation, l'intégralité des calculs est exécutée sur le réseau témoin réel et les résultats sont figés (anomalies, pentes au mm, clusters, hydrogrammes SWMM).
2. **Tests de non-régression** : à chaque modification, une batterie de tests rejoue les calculs et compare point par point ; tout écart au-delà des tolérances (cote > 1 mm, débit > 0,01 %) bloque la mise à jour. Suite actuelle : **641 tests**.
3. **Validation humaine par jalon** : aucune phase n'est terminée sans démonstration et validation métier.
4. **Traçabilité Git** : chaque modification est versionnée ; retour arrière instantané possible.
5. **Audit trail** : toute modification (web ou mobile) est journalisée — auteur, date, ancienne/nouvelle valeur, motif.

---

## 5. Grille Tarifaire, Quotas & Feature Gating

La tarification est indexée sur la **valeur métier** délivrée, non sur des métriques informatiques.

### 5.1 Principes de segmentation

- **Étudiant / Chercheur** : petits sous-réseaux d'apprentissage, pas d'études opposables → offre Académique gratuite à périmètre borné.
- **Bureau d'études (BET)** : SDA, zonage pluvial, audits capacitaires, dossiers d'autorisation → réseau jusqu'à 15 000 regards, exports certifiés.
- **Régie / Entreprise d'exploitation** : missions continues → système modulaire à la carte selon les priorités d'exploitation.

### 5.2 Version démo & matrice des offres

**Essai démo** : 14 jours, jusqu'à 2 000 regards, contrôle qualité + cartographie + aperçu SWMM, le choix de la formule à l'issue.

| Critères & droits | **0. Essai Démo** | **1. Académique & Recherche** | **2. Bureau d'Études (BET)** | **3. Régies — Système modulaire** |
|---|---|---|---|---|
| Cible | Évaluation | Universités, chercheurs, étudiants | BET VRD, experts hydraulique | Régies, services techniques |
| Tarif | 0 DZD (14 j) | 0 DZD permanent (non commercial) | 45 000 DZD/mois ou 450 000 DZD/an | À la carte : pack 3 modules 650 000 DZD/an ou convention |
| Périmètre réseau | 2 000 regards | 500 regards | 15 000 regards/projet | Réseau communal complet |
| Module A — Mobile terrain | ❌ | ❌ | ❌ | 250 000 DZD/an |
| Module B — Diagnostics NP 650 & autocurage | Inclus (éval.) | Inclus (pédagogique) | Inclus (rapports) | 200 000 DZD/an |
| Module C — SWMM 5.2 & bassins MNT | 1 calcul | 1 calcul | 3 calculs simultanés | 350 000 DZD/an, file prioritaire |
| Export `.inp` | Limité | Limité (filigrane) | Plein accès | Plein accès |
| Rapports PDF | Aperçu | ❌ filigrane pédagogique | Certifié logo BET | Complets |
| Comptes | 2 | 1 | 5 | Multi-comptes |
| Support | FAQ | Communauté | Email < 24 h | Prioritaire + accompagnement |

### 5.3 Quotas techniques (feature gating)

Chaque organisation est rattachée à un code de plan (`demo`, `education`, `bet`, `exploitation`) vérifié par `check_quota` avant chaque calcul lourd :

| Quota | demo | education | bet | exploitation |
|---|---|---|---|---|
| `max_nodes` | 2 000 | 500 | 15 000 | illimité |
| `max_projects` | 3 | 3 | 25 | illimité |
| `max_users` | 2 | 1 | 5 | illimité |
| `concurrent_simulations` | 1 | 1 | 3 | 10 |
| `has_mnt_analysis` | ✓ | ✗ | ✓ | ✓ |
| `has_mobile_access` | ✗ | ✗ | ✗ | ✓ |
| `has_custom_reports` | ✗ | ✗ | ✓ | ✓ |
| `retention_days` | 14 | 30 | 365 | 3 650 |

### 5.4 Facturation B2B / B2G

Les clients publics et régies ne paient pas par carte bancaire : le cycle est **documentaire et réglementaire** —

1. **Devis proforma** PDF officiel (`/organization/license/proforma`) en DZD ou EUR avec mentions fiscales.
2. **Bon de commande** officiel déposé (`/organization/license/purchase-order`).
3. **Validation opérateur** dans la console `/admin/licenses`.
4. **Activation** par clé de licence `SP-LIC-2026-XXXX-XXXX-XXXX`, y compris sur installation hors-ligne.

**Anti-abus Académique** : email institutionnel obligatoire (domaines publics bloqués) + filigrane indélébile *« Document Pédagogique Non Contractuel »* sur les exports.

> Détail des alternatives écartées (Stripe exclusif, dongle USB) : [ADR 0006](adr/0006-facturation-b2b-licences.md).

---

## 6. Périmètre du MVP SaaS

Décision structurante : le MVP est **strictement centré** sur la chaîne de valeur fondamentale bureau d'études / régie, pour éviter la dilution et la dérive de calendrier.

**Inclus** : socle multi-tenant + RBAC + licences ; ingestion GeoPackage/Shapefiles/`.inp` et contrôle qualité avec scoring 0-100 ; segmentation MNT ; moteur SWMM 5.2 asynchrone ; passerelle mobile essentielle ; exports et rapports PDF.

**Différé (post-MVP)** : qualité de l'eau physico-chimique (DCO, DBO5, MES) ; capteurs IoT/SCADA temps réel sur déversoirs ; pilotage prédictif RTC des vannes et pompes.

> Alternatives écartées et conséquences : [ADR 0008](adr/0008-perimetre-mvp-saas.md).

---

## 7. Glossaire Pédagogique Unifié

### 7.1 Terme métier de l'assainissement

- **Cote de radier** : altitude du fond intérieur de la canalisation ou du regard — déterminante pour la pente d'écoulement gravitaire.
- **Contre-pente** : radier aval plus haut que le radier amont → eau stagnante, envasement, odeurs.
- **Saut de pente (dénivelée)** : différence de cote brutale entre conduite entrante et sortante (chute hydraulique).
- **Écoulement à surface libre** : l'eau n'occupe pas toute la section ; en charge = canalisation pleine, risque de mise sous pression.
- **Manning-Strickler** : $V = K \cdot R_h^{2/3} \cdot I^{1/2}$ (vitesse, rugosité, rayon hydraulique, pente).
- **NP 650** : débit nominal d'une conduite circulaire, $Q \approx 3{,}1 \cdot D^{2{,}2}$.
- **EPA SWMM 5.2** : moteur de simulation dynamique de référence (crues pluviales, ondes de crue, débordements).
- **MNT / DEM** : grille raster d'altitude du sol, indispensable aux bassins versants réels.
- **Cluster hydraulique** : groupe connexe de canalisations et regards s'écoulant vers un même exutoire.
- **Rejet / Exutoire (Outfall)** : point terminal du réseau (milieu récepteur ou STEP).
- **Ligne piézométrique (HGL)** : niveau d'eau dans un tube vertical — charge hydraulique totale.
- **Mise en charge / Surcharge** : HGL au-dessus de la génératrice supérieure, sous pression mais confiné sous terre.
- **Débordement / Inondation** : HGL au-dessus de la cote du terrain → voirie submergée.
- **Laminage de crue** : écrêtement du débit de pointe par stockage dans les ouvrages amont.
- **Voronoï / Thiessen** : partition du territoire en zones d'influence des regards (voir Doc 3 §2).
- **Orphelin** : regard sans aucune conduite connectée, ou tronçon exclu du graphe car une extrémité n'a pas pu être résolue — voir Doc 3 §5.

### 7.2 Termes informatiques de la plateforme

- **SaaS** : logiciel en ligne via navigateur, sans installation, mises à jour automatiques.
- **Multi-tenant** : plusieurs organisations sur la même plateforme, isolées hermétiquement par `org_id`.
- **Stealth 404** : règle de sécurité — toute ressource d'une autre organisation répond 404, jamais 403 (aucune fuite d'existence).
- **FastAPI** : framework Python de l'API, rapide et standardisé.
- **PostgreSQL + PostGIS** : base relationnelle et spatiale de référence.
- **Celery & Redis** : calculs lourds en arrière-plan sans figer l'écran.
- **S3 / MinIO** : stockage objet des fichiers volumineux (MNT, `.inp`, `.out`, PDF).
- **Argon2id & JWT** : hachage des mots de passe et sessions sécurisées.
- **RBAC** : contrôle d'accès par rôles (Admin, Ingénieur, Opérateur terrain, Observateur).
- **Docker / Compose** : conteneurs pour un déploiement reproductible.
- **Golden Master** : jeu de résultats de référence figé garantissant la non-régression hydraulique.
- **Audit trail** : journal infalsifiable de chaque modification et calcul.
