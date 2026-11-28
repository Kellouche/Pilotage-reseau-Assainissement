# TODO — Unification & Refonte des Modules « Qualité Réseau » (DrainPilot 5.2)

> **Décision d'architecture retenue : Option C** — Unification sur le **Cockpit Qualité V2.1** (`/qualite`, embarqué dans `/map?tab=qualite`) et retrait progressif des onglets qualité legacy de `/carte` + suppression du code mort `map_quality.js`.  
> **Base factuelle (audit sur `Assainissement_Ville` — 20 912 éléments, 9 490 anomalies brutes)** :
> - `9 018` anomalies (`95,03 %`) sont `informatif` (`donnees_manquantes`) et écrasent `score_global` (`54,8 %` vs `97,79 %` hors `informatif`).
> - `/carte` (`tabMappings`) ne couvre que `118 / 472` (`25,00 %`) des anomalies réelles (`inversions_sens_ecoulement` `297` et `deconnexions_spatiales` `57` absentes) et déclenche des `HTTP 404` sur `/api/v1/corrections/hybride/suggest`.
> - `/map?tab=qualite` (`/qualite`) affiche `Verdict : CONFORME` malgré `383` anomalies majeures, et affiche `96,4 %` (`hydraulique`) sous le libellé `Complétude Altimétrique` au lieu de `12,4 %` (`altimetrie.score_qualite`).

---

## Règles transverses & Grille de poids locale configurable

- [ ] **Définir la configuration de grille de poids par défaut (modifiable par organisation/projet)**
  - Grille par défaut alignée sur `poids_sev` existant (`api/routes/qualite.py`) :
    - `critique`: **4** *(option configurable à `10` si durcissement souhaité)* — bloquant simulation SWMM
    - `majeure`: **3** — fausse le modèle hydraulique ou le récolement (`inversions_sens_ecoulement`, `deconnexions_spatiales`, `champs_manquants` critiques)
    - `mineure`: **1** — doute terrain non bloquant (`pentes_suspectes` faibles, raccordement spatial à confirmer, `troncons_orphelins`)
    - `informatif`: **0** — **0 pénalité**, exclu de « À traiter », isolé dans `Couverture Altimétrique (%)`
  - Permettre la surcharge par `org_id` / projet (fichier de config ou table paramètres qualité) sans redéploiement.
  - Embarquer `grille_poids_appliquee` dans chaque rapport JSON (`/api/v1/qualite/analyse` et `/synthese`) pour traçabilité.

---

## Lot 1 — Compteurs, Verdict & Contrat `/api/v1/qualite/synthese` (~1 j/h) ✅ FAIT

Fichier cible : `api/routes/qualite.py` (`get_synthese_qualite`)

- [x] Exclure les anomalies `informatif` (`donnees_manquantes`) du compteur `nb_a_traiter` (`9 490` → `472` sur `Assainissement_Ville`) et exposer `nb_informatif` séparément.
- [x] Exposer `altimetrie.score_qualite` (ex. `12,4 %`) dans la réponse de `/api/v1/qualite/synthese` (actuellement absent).
- [x] Durcir le calcul de `verdict` :
  - Inclure toutes les dimensions déterministes : `topologie`, `hydraulique`, `completude`, `geometrie` (+ `altimetrie` quand le contexte terrain existe).
  - Interdire `verdict = "conforme"` si `critique > 0` ou `deconnexions_spatiales > 0` (verrou → au mieux `a_surveiller`).
- [x] Mettre à jour `docs/05_CONTROLE_QUALITE_V2.md` — contrat `/synthese` v2.2 documenté.

> **Validation live (27/11→28/11)** : `/synthese` retourne `verdict=action_requise`, `nb_a_traiter=472`, `nb_informatif=9018`, `altimetrie.score_qualite=12.4`. Tests `test_qualite_*` : 19/19 verts.

---

## Lot 2 — Moteur de scoring V2.2 (~2 j/h)

Fichiers cibles : `src/analyse_qualite_gpkg.py`, `api/services/qualite_cache_service.py`

- [ ] **Raccorder les 4 catégories orphelines** aux sous-scores de `scores_qualite` :
  - `deconnexions_spatiales` → `topologie`
  - `incoherences_amont_aval` → `hydraulique`
  - `discontinuites_pose` → `altimetrie` (ou `hydraulique` selon validation métier)
  - `capacite_debit` → `hydraulique`
- [ ] **Calculer des sous-scores dédupliqués par tronçon et pondérés par sévérité** (en appliquant `grille_poids`, avec `informatif = 0`) afin d'aligner le comportement des sous-scores sur le périmètre réel du réseau.
- [ ] **Ajouter `score_criticite_troncon`** par `id_conduite` (somme pondérée des anomalies ouvertes + sévérité max) pour permettre le tri par priorité chantier.
- [ ] **Invalider / versionner les caches** `*.qualite_cache.json` (passer `moteur` à `v2.2` ou clé de version cache) pour éviter de servir d'anciens rapports incohérents.

---

## Lot 3 — Correctifs & enrichissement Cockpit V2.1 `/qualite` (~2 j/h)

Fichiers cibles : `templates/qualite.html`, `static/js/qualite/qualite_etat_carte.js`, `static/js/qualite/qualite_file_fiche.js`, `static/js/qualite/qualite_table_modals.js`

- [ ] **Corriger le bug `#kpi-score-alti`** dans `qualite_etat_carte.js` : afficher `altimetrie.score_qualite` (`12,4 %`) et non `scores.hydraulique` (`96,4 %`).
- [ ] **Séparer visuellement le bruit `informatif`** : afficher un compteur `Anomalies actives` hors `informatif`, et conserver les lacunes altimétriques derrière un toggle opt-in (`Afficher les lacunes altimétriques`, désactivé par défaut).
- [ ] **Trier la file d'anomalies** par `score_criticite_troncon` décroissant (en plus du tri par sévérité) et afficher le score/nb d'anomalies du tronçon dans la fiche.
- [ ] **Intégrer les orphelins réseau** (`/api/v1/network/orphelins` : regards isolés + tronçons hors graphe) dans la file et les compteurs topologiques de `/qualite`.
- [ ] **Volet pilotage MOA/MOE** : ajouter un export synthétique (CSV / fiche récapitulative par dimension et par commune/bassin) directement depuis l'en-tête de `/qualite`.

---

## Lot 4 — Décommissionnement qualité sur `/carte` & nettoyage legacy (~1 j/h)

Fichiers cibles : `templates/carte.html`, `static/js/carte_anomalies.js`, `static/js/carte_core.js`, `static/js/map/map_quality.js`, `templates/map.html`

- [ ] Retirer les onglets de diagnostic qualité redondants de `/carte` (ou conserver `/carte` en vue consultation réseau pure) et ajouter un accès direct vers `/map?tab=qualite`.
- [ ] Supprimer le code mort `static/js/map/map_quality.js` et le bloc `#quality-score-container` inutilisé de `templates/map.html`.
- [ ] Harmoniser la gestion de session/cookie dev (`127.0.0.1` vs `localhost`) pour éviter les `HTTP 401` croisés sur `/map?tab=qualite`.

---

## Lot 5 — Recette automatisée & validation (~1 j/h)

- [ ] Adapter les tests `tests/test_qualite_v2.py`, `tests/test_qualite_endpoints_v2.py`, `tests/test_qualite_ui.py` aux nouveaux scores/verdicts.
- [ ] Exécuter la suite complète `.venv\Scripts\pytest -q` et la validation syntaxique JS sur `static/js/`.
- [ ] Valider dans le navigateur (Playwright) sur `Assainissement_Ville` :
  - `0` erreur console / `0` requête HTTP 4xx-5xx sur `/map?tab=qualite` et `/carte`.
  - Cohérence exacte entre `/api/v1/qualite/synthese`, les KPIs affichés et la fiche tronçon (vérifier `C_10016`, `C_78`, `C_1127`).
- [ ] Préparer une note de release expliquant le changement de verdict (`CONFORME` → `À SURVEILLER` / `ACTION REQUISE` sur les réseaux ayant des anomalies majeures).

---

## Points à valider avec l'exploitant & les partenaires (MOA / Agence de l'eau)

- [ ] **Grille de poids par défaut** (`4 / 3 / 1 / 0` vs `10 / 3 / 1 / 0`) et pondération éventuelle par diamètre/linéaire dans `score_criticite_troncon`.
- [ ] **Seuils du verdict SWMM** (`95 %` / `80 %` et règles de blocage sur `deconnexions_spatiales` / `champs_manquants`).
- [ ] **Seuils détecteurs terrain** : tolérance snap (`0,5 m`), déconnexion spatiale (`max(50 m, 2×L)`), écart profondeur (`3 m`), pente minimale (`0,1 %` vs `0,2 %`).
- [ ] **Gouvernance des statuts** : habilitation pour passer une anomalie en `revu` (faux positif accepté) vs `corrige`.
