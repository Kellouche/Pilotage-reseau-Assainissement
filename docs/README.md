# DrainPilot 5.2 — Guide de lecture de la documentation

Ce dossier contient **4 documents de référence** qui concentrent l'intégralité
de la documentation produit, technique, scientifique et opérationnelle du
projet, complétés par le registre immuable des **Architecture Decision
Records** (`adr/`). Les anciens documents sources sont conservés pour
traçabilité dans `_archive_historique/` (non normatifs).

> **Règle d'or documentaire** : les 4 documents ci-dessous font foi.
> En cas de divergence avec un fichier archivé, ce sont eux qui décrivent
> l'état réel du système.

## Les 4 documents et leur cible

| Document | Thématique | À lire en premier si vous êtes… |
|---|---|---|
| [01_PRODUIT_CADRAGE_ET_TARIFICATION.md](01_PRODUIT_CADRAGE_ET_TARIFICATION.md) | Vision, personas, garanties métier, grille tarifaire, glossaire | Décideur, commercial, utilisateur métier, étudiant |
| [02_ARCHITECTURE_SYSTEME_ET_API.md](02_ARCHITECTURE_SYSTEME_ET_API.md) | FastAPI, multi-tenant, ADRs, données, référentiel des endpoints, mobile | Architecte, développeur, DevOps, auditeur sécurité |
| [03_INGENIERIE_HYDRAULIQUE_ET_SWMM.md](03_INGENIERIE_HYDRAULIQUE_ET_SWMM.md) | Saint-Venant 1D, Voronoï/Horton, pluviométrie Algérie, topologie adaptative, restitution `.inp`, réconciliation 1:1 | Ingénieur hydraulicien, modélisateur, hydrologue, chercheur, BET |
| [04_EXPLOITATION_OPERATIONS_ET_ROADMAP.md](04_EXPLOITATION_OPERATIONS_ET_ROADMAP.md) | Démarrage, CI/CD, validation MCP, inventaire du dépôt, feuille de route 2026-2029 | Développeur, QA, chef de projet, responsable maintenance |

## Matrice persona → document → sections utiles

### Décideur / Directeur d'exploitation / Régie

1. `01` §1 Vision et proposition de valeur
2. `01` §3 Garantures métier et filet de sécurité (à projeter en réunion)
3. `01` §4 Grille tarifaire et périmètre MVP
4. `03` §7 Bilan de réconciliation 1:1 (la preuve de « zéro perte »)

### Ingénieur BET / Bureau d'études

1. `03` §6 Restitution physique fidèle dans le `.inp` (pompes, weirs, sections)
2. `03` §7 Réconciliation 1:1 et registre d'audit des exclusions
3. `02` §4 Référentiel des endpoints (exports `.inp`, profil en long, PDF)
4. `03` §5 Chaîne canonique de résolution — pour auditer la connectivité d'un jeu de données client

### Chercheur / Scientifique / Doctorant

1. `03` §1 Cadre scientifique (équations, invariants de masse)
2. `03` §2 Démarche hydrologique (Voronoï, Horton, codification)
3. `03` §4-§5 Découverte adaptative des conventions et chaîne à 6 provenances tracées — chaque rattachement est auditable
4. `adr/` pour les décisions d'architecture argumentées

### Étudiant / Formation

1. `01` §6 Glossaire pédagogique unifié (métier + informatique)
2. `03` §1-§3 pour la démarche de modélisation pas à pas
3. `01` §4 pour découvrir le plan Académique

### Développeur / DevOps

1. `04` §1-§2 Démarrage et règles de livraison (mode silencieux, 641 tests, Golden Master)
2. `02` §1-§3 Architecture, ADRs, modèle de données
3. `02` §4 Référentiel exhaustif des endpoints
4. `04` §3 Protocole de validation navigateur MCP obligatoire

### Technicien terrain / Exploitation mobile

1. `01` §2 Personas et parcours utilisateurs
2. `02` §5 Passerelle mobile et synchronisation offline-first
3. `04` §1 Commandes d'exploitation courantes

## Chemins de lecture recommandés

- **« Je découvre le produit »** (15 min) : `01` §1 → §3 → §4, puis `04` §1 pour lancer l'API.
- **« Je dois intégrer l'API »** : `02` §1 → §3 → §4 (endpoint par endpoint), `02` §5 si mobile.
- **« Je dois auditer un modèle hydraulique »** : `03` §5 (connectivité) → §6 (restauration `.inp`) → §7 (réconciliation) → `02` §4 (endpoint `/simulations/reconciliation`).
- **« Je prends la main sur le code »** : `04` §1 → §4 (inventaire du dépôt) → `AGENTS.md` à la racine (règles opérationnelles).

## Comment tirer le meilleur profit de chaque document

- **Doc 1** : les §3 (garanties) et §4 (tarifs) sont réutilisables tels quels en supports commerciaux ; le glossaire §6 est la référence commune pour aligner le vocabulaire métier/informatique.
- **Doc 2** : le §4 est un référentiel d'endpoints vivant — toute route ajoutée au code doit y être consignée ; les synthèses d'ADR renvoient aux fichiers originaux de `adr/` pour le détail des alternatives écartées.
- **Doc 3** : c'est le document de **preuve scientifique** — les chiffres cités (mesures GPKG, taux de connectivité, bilans) sont ceux réellement mesurés sur les données de production ; toute évolution des algorithmes impose de les remesurer avant de mettre à jour.
- **Doc 4** : le §2 (CI/CD Zero-Prompt) et le §3 (protocole MCP) sont les règles de livraison opposables ; le §5 fait foi pour l'état d'avancement et la règle de gel 2026.

## Règles de maintenance de cette documentation

1. **Un fait = un endroit** : ne jamais dupliquer un contenu entre les 4 documents ; renvoyer par lien interne (`01_PRODUIT_...md#section`).
2. **Les ADRs sont immuables** : une nouvelle décision d'architecture crée `adr/XXXX-*.md`, elle ne réécrit jamais un ADR existant.
3. **Les archives ne font pas foi** : `_archive_historique/` est consultable pour l'historique, jamais comme référence contractuelle ou technique.
4. **Chiffres mesurés uniquement** : interdit de recopier un pourcentage ou un volume d'ancien document sans le remesurer sur le GPKG courant.

## Standard de documentation des formules et équations

Toute formule ou équation citée dans les documents de référence doit être
**autoportante** — un lecteur ne doit jamais avoir à deviner ce que
représente un symbole. Pour chaque formule, exiger :

1. **La formulation complète** en notation LaTeX (`$…$` inline, `$$…$$` display), jamais une version approximative ou tronquée.
2. **La nomenclature des paramètres et coefficients** : tableau ou liste
   explicite de chaque symbole avec son **unité** et sa **signification**
   physique (ex. `$n$` = coefficient de rugosité de Manning, sans unité,
   fonction du matériau ; `$I_{\\max}$` = intensité de pointe en mm/h).
3. **Les références** : norme, guide ou publication d'origine — ONA,
   ANRH, UHBC, manuel EPA SWMM 5.2 (ch. hydraulique), documentation
   normativa algérienne, ou référence bibliographique citée.
4. **Un exemple référencé** : application numérique type avec valeurs
   réelles du projet (station, réseau, période de retour) permettant de
   vérifier le calcul de bout en bout — pas d'exemple générique sorti de
   contexte.
5. **Le domaine de validité** : conditions d'application (régime
   d'écoulement, hypothèses, limites connues) quand la formule en dépend.

Ce standard s'applique en particulier au Doc 3 (ingénierie) mais vaut
pour tout document citant une relation mathématique ou empirique.
