# MISSION — DRAINPILOT : FINALISATION DU MODULE DWF (APPORTS DE TEMPS SEC)

Tu interviens sur le dépôt DrainPilot, plateforme SaaS d'assainissement
hydraulique adossée à EPA SWMM 5.2. Le module « Apports DWF » est
fonctionnel en production (CRUD, injection moteur, estampillage GPKG,
réconciliation, restitution dans les résultats). Il reste un chantier
résiduel d'UX/fonctionnel validé + un chantier majeur d'historisation
(Point 6).

**Avant toute implémentation : tu dois prendre connaissance de l'état
réel du code.** Ne jamais supposer une capacité non vérifiée : chaque
constat doit être confirmé en lisant les fichiers concernés.

---

## 0. RÈGLE DE GOUVERNANCE — APPROBATION PAR LOT (ABSOLUE)

**Tu ne dois écrire aucune ligne de code pour un lot sans avoir
auparavant :**

1. Présenté au maître d'ouvrage (l'utilisateur) un dossier de lot
   complet : périmètre exact, fichiers à créer/modifier, schéma de
   données, endpoints, impacts, risques, plan de tests.
2. Obtenu son **aval explicite** pour ce lot précis.
3. Mené la discussion jusqu'au **levé de toute réserve** de sa part.

**Interdits absolus :**

- Commencer un lot « pour gagner du temps » ou enchaîner deux lots sans
  nouvel aval.
- Modifier un fichier hors du périmètre validé du lot.
- Pousser sur `master` sans validation des tests (voir §4).
- Corriger « au passage » un bug ou une anomalie non couverte par le
  lot — le signaler dans un rapport séparé à la place.

Tu peux en revanche toujours : auditer, proposer, spécifier, rédiger des
maquettes de tests, et préparer les migrations **sur papier** (jamais
exécutées) sans attendre d'aval.

---

## 1. ÉTAT DES LIEUX (vérifié — ne pas remettre en cause)

### Backend (tous vérifiés dans le code)

- Modèle `ApportDwf` : `api/models.py:665-710` — **pas de champ
  `code_apport`**, pas d'historisation.
- Routes : `api/routes/apports.py` — CRUD unitaire strict ; nœud validé
  contre le GPKG courant (**422 si absent**) ; estampillage
  `(gpkg_version_id, gpkg_sha256)` posé à la création / PUT-node /
  `revalider` ; les autres champs ne touchent jamais l'estampillage.
- Service : `api/services/apports_dwf_service.py` — validation stricte
  pré-simulation (**422 global** si incompatibilité) ; motifs stables
  via `code` : `non_reconcilie`, `version_differencee`,
  `sha256_difference`, `sha256_difference_legacy`,
  `apport_estampille_version_alors_que_le_projet_est_legacy`,
  `noeud_absent_du_snapshot` (+ `gpkg_courant_indisponible` côté
  `/a-reconcilier`).
- Simulation : `api/routes/simulations.py` +
  `api/services/simulation_service.py` — même moteur pour sync et
  Celery ; seul paramètre DWF = `dwf_actif` (booléen,
  `api/schemas.py:233`).
- Frontend : `static/js/app/apports_dwf.js` +
  `templates/partials/modal_apports_dwf.html` — gestion + zone
  réconciliation existantes.
- Tests : `tests/test_apports_dwf*.py`, `test_dwf_injection.py`,
  `test_p153_dwf_ui.py`, `test_p154_dwf_resultats.py` — tous verts.

### Décisions UX déjà validées (ne pas rouvrir)

- **DWF-UX-01 à 07** : `code_apport` stable auto-généré unique par
  projet ; infiltration = débit direct uniquement ; changement de nœud
  autorisé avec confirmation + traçabilité ; débit spécifique projet
  par défaut avec dérogation par apport ; modale large ;
  actif/inactif projet, exclusion simulation et incompatibilité
  technique = **3 plans distincts** ; seuils d'avertissement
  DWF-UX-07 = clos.
- **Point 3 (validé)** : simulation « compatibles seuls » autorisée
  par choix explicite (backend à construire) ; création sur nœud absent
  **INTERDITE** ; réconciliation unitaire ; badge « nœud absent »
  informatif ; deux parcours UX (nœud disparu / version modifiée) →
  exige `noeud_present` dans `/a-reconcilier` ; motif
  `exclusion_utilisateur` distinct de `noeud_absent_du_inp`.
- **Point 4 (validé, non implémenté)** : import Excel/CSV en 2 modes
  (ajout / mise à jour par `code_apport`), import partiel ligne à
  ligne, doublons internes = choix utilisateur (jamais fusion ni
  somme), aperçu + confirmation + rapport de rejets téléchargeable,
  2 modèles (eaux usées / infiltrations) à 2 feuilles
  (Instructions / Données).
- **Point 5 (spécification livrée)** : actions contextuelles
  Réconcilier / Changer de nœud / Modifier, confirmation avant
  réconciliation, libellés métier par motif, détails techniques
  repliés, cas `noeud_absent_du_snapshot` = anomalie technique
  bloquant les actions utilisateur.
- **Point 6 (audit + spec livrés)** : historique métier
  `apports_dwf_history`, chaîne SHA-256 par org, ancres externes,
  registre central d'incidents crypto, justificatifs, suppression
  vérifiée, Legal Hold, exports 7 j, rétention 5 ans.

---

## 2. CONTRAINTES ABSOLUES

### Préservation du produit existant

- **Ne JAMAIS modifier le moteur hydraulique SWMM ni les calculs
  Saint-Venant.** Le Golden Dataset (`tests/data/golden_dataset/`) et
  `tests/test_golden_master.py` sont intouchables.
- **Ne pas affecter le code existant** : chaque modification doit être
  additive ou strictement corrective ; aucun refactor non demandé ;
  respecter les conventions du dépôt (voir `AGENTS.md`).
- Isolation multi-tenant stricte par `org_id` + **stealth 404** sur
  tout nouvel endpoint.
- Les snapshots de simulations historiques sont **immuables** : une
  modification d'apport ne réécrit jamais un `result.json` persisté.
- Français pour le code commenté, les messages utilisateur et la
  communication.

### Échecs de tests connus — NE PAS « réparer »

Ces échecs sont **documentés et indépendants de tes lots** ; ne pas les
modifier, ne pas les masquer, ne pas les déclarer comme régressions :

- `tests/test_invariance_scenarios_ab.py::test_resolution_cluster_id_variants`
  (anomalie de clustering connue : 90,21 ha vs 86,54 ha attendu).
- `tests/test_invariance_scenarios_ab.py::test_invariance_scenarios_ab_complet`
  et `tests/test_ouvrages_orphelins.py::test_detecter_ouvrages_orphelins_cluster_85`
  (échecs **environnementaux** : `clusters_cache.json` absent pour
  `network_Assainissement_Ville.gpkg` → 0 ouvrage détecté ; reproduits
  à l'identique sans aucune modification de code).

Tout **autre** échec de test est une régression : bloquer le lot,
diagnostiquer, corriger.

---

## 3. TRAVAUX À RÉALISER, DANS L'ORDRE (sous réserve d'aval §0)

### LOT A — Fondations DWF (prérequis de tout le reste)

- **A1.** Champ `code_apport` : migration Alembic **réversible**,
  contrainte `UNIQUE(project_id, code_apport)`, auto-génération à la
  création (format à proposer, ex. `AP-AAAA-NNNN`), exposition dans
  schémas/réponses, backfill des apports existants.
- **A2.** `noeud_present` dans `GET /a-reconcilier` (contrôle via
  `noeuds_du_gpkg` déjà disponible dans `apports_dwf_service.py`).
- **A3.** Paramètre par run `dwf_compatibles_seulement` (ou
  `dwf_exclure_ids[]`) sur `SimulationRunRequest`, propagé **sync ET
  Celery** via le même `SimulationService` ; les exclus rejoignent
  `provenance.apports_dwf.ignores` avec motif `exclusion_utilisateur`
  + `motif_origine` conservé ; la levée stricte 422 reste le
  comportement par défaut.

### LOT B — UX Point 5 (frontend + A2)

Refonte de la zone réconciliation : libellés métier par motif
(table de correspondance de la spec), confirmation avant `revalider`,
actions contextuelles selon `noeud_present`, accès direct au
formulaire depuis la fiche, cas `noeud_absent_du_snapshot` =
« Vérification technique requise » sans actions, détails techniques
repliés. **Respecter DWF-UX-06** : ne jamais proposer la désactivation
comme solution à une exclusion de simulation.

### LOT C — Import Excel/CSV (Point 4)

Assistant d'import : détection fichier, 2 modes (ajout / mise à jour
par `code_apport`), mapping colonnes, validation ligne à ligne,
collisions fichier↔projet (ajout = rejet `code_deja_present` ;
MAJ = rejet `code_inconnu`), doublons internes avec choix utilisateur
côte à côte (jamais fusion ni somme), aperçu + confirmation, import
partiel, rapport de rejets téléchargeable. Choix d'architecture à
documenter dans le dossier de lot : N appels unitaires existants vs
endpoint bulk transactionnel. Gabarits Excel 2 feuilles (dépendance
`openpyxl` à ajouter si parsing backend).

### LOT D — Point 6 (historisation & conformité), lots P6.0 → P6.9

Ordre validé par l'audit :

- **P6.0** — Réparer `api/routes/audit.py` (attributs inexistants
  `table_name/record_id/operation/timestamp` + **absence
  d'authentification** = faille) ou le retirer.
- **P6.1** — Historique métier `apports_dwf_history` + service
  atomique + hooks routes apports + consultation paginée.
- **P6.2** — Chaîne SHA-256 par org + clés de signature (KMS abstrait).
- **P6.3** — Ancres de preuve externes (stockage distinct).
- **P6.4** — Registre central incidents crypto + réouvertures.
- **P6.5** — Justificatifs et documents de preuve.
- **P6.6** — Legal Hold (double validation, extension automatique).
- **P6.7** — Exports contrôlés (synthétique / détaillé, TTL 7 j).
- **P6.8** — Suppression vérifiée + archivage logique + rétention.
- **P6.9** — Durcissement, tests d'intrusion, recette.

La spécification complète (modèles de données, services, endpoints,
plan par lot, risques) a été produite dans le fil de travail — la
redemander si absente du contexte.

---

## 4. VALIDATION OBLIGATOIRE AVANT CHAQUE COMMIT

Stabilité du produit — non négociable :

1. `.venv\Scripts\pytest -q` — suite complète. Autorisé à committer
   uniquement si : zéro échec **nouveau** par rapport à la baseline
   connue (§2). Documenter le bilan dans le message de commit.
2. `node --check` sur **tout** fichier JS frontend modifié.
3. Tests ciblés du lot : créer les fichiers de test manquants dans
   `tests/` en suivant les conventions existantes (fixtures `ctx_*`,
   clients authentifiés, isolation org, stealth 404).
4. Pour les lots UI (B, C) : vérification manuelle sur
   `http://localhost:5002` (login requis ; token JWT dans
   `localStorage.swmm_access_token`).
5. Migration Alembic : vérifier qu'elle est **réversible**
   (`downgrade` fonctionnel testé) et qu'elle ne casse pas les
   données existantes.

---

## 5. LIVRABLES ATTENDUS PAR LOT

1. **Dossier de lot préalable** (avant code) : périmètre, fichiers,
   schéma, endpoints, impacts, risques, plan de tests → **attente
   d'aval**.
2. Code + migration + tests verts.
3. Commit poussé sur `master` (format Conventional Commits + bilan de
   tests dans le message).
4. Résumé court : fichiers touchés, comportement, résultats de tests,
   points ouverts reportés.

---

## 6. POINTS OUVERTS CONNUS (ne pas bloquer, signaler)

- **Point 5** : 5 micro-ajustements proposés non encore arbitrés
  (`gpkg_courant_indisponible` dans le tableau des motifs ; blocage
  backend réel pour `noeud_absent_du_snapshot` ; champ « désignation »
  inexistant → utiliser `node_id`/`nature`/`source` ; `noeud_present`
  indéterminé quand le GPKG courant est indisponible ; dépendance
  Option B pour P5-12). Implémenter l'esprit validé, consigner les
  choix techniques dans le code.
- **Point 6** : dépendances externes (KMS, bucket S3 de preuves,
  `openpyxl`, Celery beat, politique de sauvegarde) — utiliser les
  interfaces abstraites prévues, mode dégradé documenté.
- Historisation des changements de nœud : dépend du module
  d'historique (P6.1).
- `code_apport` et Option B (point 3) conditionnent les lots B et C.

---

## 7. DÉMARRAGE

**Commence par le LOT A** — mais uniquement après avoir présenté le
dossier de lot A complet et obtenu l'aval du maître d'ouvrage.

Si une décision fonctionnelle non couverte par les arbitrages validés
est requise : documente-la dans le dossier de lot et choisis
l'option la plus conservative **sans t'arrêter** — sauf pour toute
question de **destruction de données** ou de **sécurité**, où tu
t'arrêtes et demandes.
