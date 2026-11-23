# TODO — Finalisation de la Feuille de Route Opérationnelle (Phases 4 à 7)

> ⚠️ **NE PAS DÉMARRER les travaux de la Feuille de Route 2027–2029 avant d'avoir soldé les phases ci-dessous.**
> Référence principale : [`docs/13_ROADMAP_SAAS.md`](13_ROADMAP_SAAS.md)

---

## 🥇 Phase 6 : Cockpit d'Exploitation, Profils Hydrauliques & Diagnostic Expert

> **Statut : ✅ COMPLÉTÉ & VALIDÉ EN PRODUCTION** (Cockpit Leaflet HD réactif, bilans de continuité massique stricts, intégration hydrodynamique temps réel).

- [x] **6.A — Profil en long hydraulique interactif (HGL Saint-Venant 1D)**
  - [x] Sélection d'un tronçon ou d'un parcours amont → aval sur la carte Leaflet
  - [x] Tracé altimétrique : terrain naturel (MNT / nuage TOPO), cotes radiers amont/aval, génératrice supérieure
  - [x] Affichage de la **ligne de charge piézométrique (HGL)** à la cote maximale d'inondation
  - [x] Mise en évidence visuelle des conduites en charge (HGL > génératrice supérieure) avec hachures sous pression
  - [x] Panneau accordéon rétractable avec Chart.js, zoom interactif et export PNG en 1 clic

- [x] **6.B — Animation temporelle de l'onde de crue (Time Slider binaire)**
  - [x] Curseur temporel 0 h → 24 h exploitant le fichier binaire `.out` de SWMM via `timeseries_extractor`
  - [x] Coloration dynamique des conduites selon le taux de charge $Q/Q_{\max}$ à chaque pas de temps
  - [x] Clignotement et marquage visuel radar des regards en débordement avec durées de submersion
  - [x] Hydrogramme dynamique aux exutoires avec mise à jour instantanée et navigation temporelle au clic

- [x] **6.C — Générateur de Rapport d'Expertise Technique en 1 clic (PDF A4)**
  - [x] Synthèse complète : anomalies critiques, contre-pentes, regards débordants, volumes inondés totaux ($m^3$)
  - [x] Bilan de continuité massique SWMM (erreur $< 0.2\%$), débits de crête aux exutoires
  - [x] Bordereau des prix unitaires estimatif (BPU) pour les travaux prioritaires (reprises de collecteurs, rehaussements)
  - [x] Export au format PDF réglementaire (ReportLab) avec planches cartographiques du réseau intégrées

- [x] **6.D — Module Avancé des Apports de Temps Sec (DWF — Phases P1.1 à P1.5.4)**
  - [x] Injection d'eaux usées multi-profils (journalier urbain, constant, industriel) et modes de saisie (EH ou débit direct)
  - [x] Modale de gestion DWF avec tableau interactif, validation et suppression ciblée
  - [x] Sélecteur cartographique interactif avec masquage temporaire de la modale et neutralisation des popups parasites
  - [x] Légende cartographique dynamique en temps réel : pastille bicolore cyan/bleu pour les regards injectés et débit cumulé affiché en L/s
  - [x] Réconciliation automatique avec le GeoPackage source et traçabilité d'audit (`apports_dwf_history`)

- [x] **6.E — Registre des Cotes Suspectes & Contrôle Qualité Altimétrique**
  - [x] Détection automatique des sauts de radier anormaux (> 20m ou anomalies MNT)
  - [x] Suspension sécuritaire du tracé du profil en long en cas d'incohérence altimétrique critique
  - [x] Registre interactif de validation / correction des cotes par l'ingénieur avec persistance instantanée
  - [x] Intégration du nuage altimétrique réel TOPO Chlef (84 302 points IDW) avec mémorisation sans conflit d'affichage

- [x] **6.F — Contrôle de Cohérence Pluie-Débit (Rationnel vs Saint-Venant 1D)**
  - [x] Évaluation du débit rationnel brut attendu ($Q = C \cdot I \cdot A / 360$) selon la surface du bassin et l'intensité maximale de pluie
  - [x] Comparaison automatique avec le débit de pointe simulé par Saint-Venant 1D
  - [x] Détection et qualification du laminage hydraulique en réseau et du stockage temporaire dans les collecteurs

- [x] **6.G — Import Multi-Formats, Benchmark EPA & Couches Satellites**
  - [x] Téléversement direct de fichiers GeoPackage (`.gpkg`) et conversion automatique transparente des fichiers `.inp` EPA SWMM vers GPKG
  - [x] Versionnement immuable des réseaux téléversés avec intégrité stricte (`_enregistrer_version_gpkg`)
  - [x] Bibliothèque intégrée de benchmarks officiels EPA (Ex 1, 3, 4, 6 LID), jeu Quartier Démo (59 regards) et Master Réseau Ville
  - [x] Import piloté de couches SIG satellites auxiliaires (`.shp` avec sidecars/zip, `.gpkg`, `.geojson`) : typage (`altimetrie_points`, `bv_officiel`, `metrologie`), normalisation GPKG mono-couche EPSG:4326 et calcul de grille IDW

- [x] **6.H — Outil SIG d'Extraction par Pochoir Spatial (SHP.md)**
  - [x] Découpage spatial à la volée du réseau et des couches satellites par un polygone GeoJSON (Polygon / MultiPolygon)
  - [x] Règle spatiale absolue d'INTERSECTION : les objets qui coupent le pochoir sont conservés entiers pour sanctuariser l'intégrité hydraulique
  - [x] Génération et téléchargement sécurisé d'un livrable zip (Shapefiles thématiques `.shp`, GeoPackage fusionné avec couche `pochoir` et `manifeste.json` de métadonnées)

- [x] **6.I — Découpage & Édition Manuelle de Bassins Versants (Clusters)**
  - [x] Sélection et regroupement manuel de conduites sur la carte pour former un sous-réseau personnalisé
  - [x] Attribution d'un exutoire personnalisé (nom, type de rejet, coordonnées)
  - [x] Endpoints CRUD complets (`/api/v1/clusters/manual-basins`) et persistance étanche par organisation (`manual_overrides_{org_id}.json`)

- [x] **6.J — Module de Simulation BMS (ONM) & Ordres de Mission Préventifs**
  - [x] Modélisation hydrodynamique prédictive sur Bulletins Météorologiques Spéciaux de l'ONM Algérie (cumul mm, durée h, profils de pluie en cloche Huff ou orage concentré)
  - [x] Générateur automatique d'Ordres de Mission terrain (`bms_ordre_mission.py`) pour les régies d'assainissement (ONA) et brigades d'intervention
  - [x] Ciblage préventif des regards critiques à curer et des avaloirs à déboucher avant l'arrivée de la pluie avec qualification du niveau d'alerte météo (jaune, orange, rouge)

- [x] **6.K — Système d'Expertise Multi-Agents IA & Garde-Fou Hydraulicien**
  - [x] Chaîne d'analyse collaborative à 7 agents spécialisés : Agent 0 Garde-Fou Hydraulicien, Agent 1 Diagnostic surcharges, Agent 2 Génie Civil, Agent 3 GDO/Variante 0, Agent 4 Risques de submersion voirie, Agent 5 Finance BPU DZD, Agent 6 Synthèse exécutive
  - [x] Orchestrateur multi-agents consolidant les avis techniques dans le rapport d'expertise A4 ReportLab
  - [x] API de paramétrage fin du garde-fou et de ré-audit a posteriori (`/api/v1/projets/{project_id}/garde-fou`)

- [x] **6.L — Diagnostic Qualité Réseau & Corrections Topologiques Supervisées**
  - [x] Détection systématique des anomalies d'infrastructure (contre-pentes, sauts de radier, diamètres non normalisés, règles NP 650)
  - [x] Tableau de bord des scores de conformité géométrique et altimétrique par commune et par bassin versant avec export CSV/Excel
  - [x] Moteur de suggestions hybrides statistiques/terrain (`/corrections/{fid}/hybride`) et application supervisée des corrections sans rupture de topologie

---

## 🥈 CHANTIERS HYDRAULIQUES IMMÉDIATS (Extension Cœur Métier)

> **Prochaine étape avant les phases 5 et 7 : enrichissement des capacités hydrauliques de pointe.**

### Chantier H1 — Conduites de Refoulement Sous Pression & Stations de Pompage
- [ ] **H1.1** Modélisation topologique du quadruplet SWMM : `STORAGE` (bâche d'aspiration) $\rightarrow$ `PUMP` (Type 3 HMT vs Q) $\rightarrow$ `FORCE_MAIN` (conduite sous pression Hazen-Williams / Darcy-Weisbach) $\rightarrow$ `JUNCTION` (chambre de casse-pression).
- [ ] **H1.2** Paramétrage numérique de stabilité : pas de temps court $\Delta t \le 1\text{ à }5\text{ s}$, `INERTIAL_DAMPING FULL`, `VARIABLE_STEP 0.75`.
- [ ] **H1.3** Rendu cartographique distinctif (conduite violette/indigo) et continuité de la ligne de charge piézométrique (HGL sous pression) sur le profil en long sans décrochement artificiel.
- [ ] **H1.4** Suite de tests unitaires et intégration Golden Master pour les refoulements en charge.

### Chantier H2 — État du Réseau, Sédimentation & Vieillissement Structurel
- [ ] **H2.1** Prise en compte de la sédimentation de fond de radier via le paramètre natif SWMM 5.2 `Geom3` ($h_{\text{séd}}$) dans `[XSECTIONS]`.
- [ ] **H2.2** Réduction de la section utile, calcul du diamètre effectif $D_{\text{eff}}$ et majoration du coefficient de Manning $n$ selon le degré d'encrassement (normes EN 13508-2 / DWA-A 110).
- [ ] **H2.3** Scénarios comparatifs d'exploitation sur le cockpit : *Réseau neuf* vs *Réseau sédimenté*, identification des débordements induits par l'ensablement et cubage estimatif des boues à curer.

### Chantier H3 — Déconnexion Manuelle d'Exutoires & Ajustement des Bassins
- [ ] **H3.1** Outil cartographique interactif de coupure / déconnexion de tronçon frontière (ex. DVO 166 vers trop-plein 171).
- [ ] **H3.2** Filtrage et sélection des exutoires pris en compte directement dans la modale de calcul.
- [ ] **H3.3** Requalification d'un ouvrage spécial en frontière étanche de bassin.

---

## 🥉 PRIORITÉ 2 — Phase 5 : API Publique & Interopérabilité SIG

> **Connexion directe avec les outils SIG des bureaux d'études et régies (QGIS, ArcGIS).**

- [ ] **5.1** — Clés d'API persistantes (`sp_live_...`) avec permissions granulaires pour requêtes externes
- [ ] **5.2** — Endpoints d'export à la volée du réseau filtré en **GeoPackage (`.gpkg`)** et **GeoJSON**
- [ ] **5.3** — Diffusion de flux de tuiles vectorielles **WFS / MVT** pour les réseaux d'envergure (> 50 000 regards)
- [ ] **5.4** — Documentation Swagger / OpenAPI 3.0 exhaustive avec exemples cURL et scripts d'intégration

---

## 🏅 PRIORITÉ 3 — Phase 7 : Industrialisation Docker & Déploiement Production

> **Mise en production officielle et déploiement conteneurisé clé en main.**

- [ ] **7.1** — Fichier `docker-compose.yml` multi-services complet (FastAPI, Worker Celery, PostgreSQL 16 PostGIS, Redis 7, MinIO, Caddy SSL)
- [ ] **7.2** — Dockerfile multi-étapes optimisé avec compilation GDAL, GEOS, PROJ et EPA SWMM 5.2.4 Toolkit
- [ ] **7.3** — Pipeline CI/CD GitHub Actions (tests pytest, Golden Master, contrôle syntaxique JS)
- [ ] **7.4** — Endpoint `/api/v1/health`, métriques d'observabilité et journalisation structurée JSON
- [ ] **7.5** — Sauvegardes automatisées et Checklist de certification Go-Live OWASP

---

## 🎖️ PRIORITÉ 4 — Phase 4 : Mobilité Terrain & Synchronisation Offline-First

> **Application mobile Flutter robuste en environnement déconnecté.**

- [ ] **4.1** — Protocole Delta Sync différentiel avec curseur d'horodatage (`since_timestamp`) et gestion des suppressions
- [ ] **4.2** — Cache local SQLite mobile et file d'attente d'interventions hors-ligne
- [ ] **4.3** — Téléversement des photographies d'anomalies vers MinIO/S3 avec redimensionnement et association au regard
- [ ] **4.4** — Journal d'audit immuable (`field_audit_logs`) avec traçabilité complète des cotes relevées
- [ ] **4.5** — Algorithme de réconciliation des conflits (priorité aux relevés in situ certifiés)

---

## Tableau de Bord d'Avancement des Phases

| Phase | Titre | Statut | Avancement |
|---|---|---|---|
| **Phase 6** | Cockpit d'Exploitation, HGL & DWF | ✅ **Terminée & Validée** | 100% |
| **Chantiers H** | Refoulement sous pression & Sédimentation | ⏳ **En cours de cadrage** | 20% |
| **Phase 5** | API Publique & Interopérabilité SIG | ⬜ À faire | 0% |
| **Phase 7** | Industrialisation Docker & Production | ⬜ À faire | 0% |
| **Phase 4** | Mobilité Terrain & Synchronisation | ⬜ À faire | 0% |
