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

## Lot 2 — Moteur de scoring V2.2 (~2 j/h) ✅ FAIT

Fichiers cibles : `src/analyse_qualite_gpkg.py`, `api/services/qualite_cache_service.py`

- [x] **Raccorder les 4 catégories orphelines** aux sous-scores de `scores_qualite` :
  - `deconnexions_spatiales` → `topologie`
  - `incoherences_amont_aval` → `hydraulique`
  - `discontinuites_pose` → `hydraulique` *(choix : rupture de continuité de pose = doute d'écoulement ; `altimetrie` reste une métrique de couverture/évaluabilité, pas de comptage d'anomalies)*
  - `capacite_debit` → `hydraulique`
- [x] **Calculer des sous-scores dédupliqués par tronçon et pondérés par sévérité** (grille `4/3/1/0` exposée dans `scores_qualite.grille_poids_appliquee` ; pénalité/tronçon = poids max / 4, dénominateur `nb_conduites`).
- [x] **Ajouter `score_criticite_troncon`** : `scores_qualite.criticite_troncons[id_conduite] = {score (Σpoids + sev_max), nb_anomalies, severite_max}` — 463 tronçons sur `Assainissement_Ville`.
- [x] **Invalider / versionner les caches** : `moteur` passé à `v2.2` ; `_charger_cache_disque` n'accepte que `v2.2` → régénération automatique.

> **Validation live** : `topologie 99.5` (inclut désormais les 57 `deconnexions_spatiales`), `hydraulique 97.7` (pondéré, inclut `incoherences`/`capacite`/`discontinuites`), verdict `action_requise` (altimétrie 12.4 % prise en compte). Tests qualite : 22/22 verts.

---

## Lot 3 — Correctifs & enrichissement Cockpit V2.2 `/qualite` (~2 j/h) ✅ FAIT

Fichiers cibles : `templates/qualite.html`, `static/js/qualite/qualite_etat_carte.js`, `static/js/qualite/qualite_file_fiche.js`, `static/js/qualite/qualite_table_modals.js`

- [x] **Corriger le bug `#kpi-score-alti`** : affiche désormais `altimetrie.score_qualite` (**12,4 %** vérifié en live, était `96,4 %` = `scores.hydraulique`).
- [x] **Séparer visuellement le bruit `informatif`** : pastille `Total: 9 490 · À traiter: 472 · Info: 9 018` ; lacunes altimétriques déjà derrière le toggle opt-in `chk-toggle-n3` (« Afficher tronçons sans altimétrie », désactivé par défaut).
- [x] **Trier la file d'anomalies** par `criticite_troncons` décroissant (exposé via `/synthese`, additif) puis sévérité ; la fiche affiche « Criticité tronçon (audit V2.2) : score — nb anomalie(s), sévérité max » (vérifié : C_159 en tête de file, score 9).
- [x] **Intégrer les orphelins réseau** (`/api/v1/network/orphelins`) : 242 nœuds + 14 tronçons fusionnés en pseudo-anomalies `orphelins_regards`/`orphelins_troncons` (mapping identique à `/carte`), filtre dédié, KPI topo `Orphelins: 242 nœuds / 14 tronçons`, statut géré localement (pas de persistance moteur).
- [x] **Volet pilotage MOA/MOE** : bouton « Exporter le rapport » → CSV (`qualite_<projet>_<date>.csv`) avec sections Synthèse / Réseau / Scores par dimension / Anomalies / Criticité top 20 tronçons / Orphelins. *Ventilation par commune/bassin non couverte : non disponible dans la synthèse (à prévoir si besoin MOA).*

> **Validation live** : `/qualite` → verdict `ACTION REQUISE`, 0 erreur console, export CSV téléchargé. Tests qualite : 19/19 verts.

---

## Lot 4 — Décommissionnement qualité sur `/carte` & nettoyage legacy (~1 j/h) ✅ FAIT

Fichiers cibles : `templates/carte.html`, `static/js/carte_anomalies.js`, `static/js/carte_core.js`, `static/js/map/map_quality.js`, `templates/map.html`

- [x] **`/carte` supprimée** : route → redirection 301 vers `/qualite` ; `templates/carte.html` + 8 modules `static/js/carte_*.js` + 2 CSS `carte_style*.css` supprimés ; spec e2e `phase0-auto-diagnostic.spec.ts` (spécifique `/carte`) supprimée. *Décision : suppression totale — la recherche d'ouvrage de `/carte` était du code mort (`#search-input` inexistant) et `/map` offre une vraie palette de recherche ; le modal de correction hybride (`/corrections/hybride/suggest` + canvas profil) n'est **pas** porté → voir ticket futur ci-dessous.*
- [x] **Code mort supprimé** : `static/js/map/map_quality.js` (`window.initQuality` jamais appelé) + bloc `#quality-score-container` (`display:none`) retirés de `templates/map.html`.
- [x] **Harmonisation session dev** : middleware `canonical_host_redirect_middleware` dans `api/main.py` — GET/HEAD sur `localhost`/`::1` → 301 vers l'hôte canonique `APP_CANONICAL_HOST` (défaut `127.0.0.1`), ce qui unifie cookies + localStorage et élimine les 401 croisés.

### Ticket futur (hors périmètre Lot 4)

- [ ] **Porter la suggestion hybride altimétrique** dans la fiche `/qualite` : l'endpoint `/api/v1/corrections/hybride/suggest` attend un `fid` DB alors que les anomalies référencent des `id_conduite` GPKG → nécessite d'abord un mapping GPKG↔DB. Code de référence dans l'historique git (`carte_ui_correction.js`, `carte_ui_modal.js`).

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
