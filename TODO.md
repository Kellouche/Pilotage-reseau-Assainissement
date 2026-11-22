# TODO — DrainPilot 5.2 (SWMM Platform)

**Dernière mise à jour :** 22-11-2026  
**Auteur :** Dr Abdelhakim KELLOUCHE & DrainPilot Engineering Team  
**Architecture active :** FastAPI 0.115+ unifié, PySWMM 5.2.4 x64 (Saint-Venant 1D), Leaflet HD Cockpit, Multi-tenancy strict (Stealth 404).

---

## 🏆 Synthèse de l'Avancement Global

| Domaine / Module | Description | Statut |
|---|---|---|
| **Socle FastAPI & Multi-Tenant** | Architecture REST moderne, isolation stricte `org_id`, règle furtive 404, sessions et tokens JWT | ✅ Réalisé |
| **Gouvernance & Licences B2B** | Quotas par plan, clés de licence cryptographiques `SP-LIC-...`, devis proforma DZD, console SuperAdmin | ✅ Réalisé |
| **Stockage Sécurisé ArtifactStore** | Abstraction MinIO/S3 et stockage local partitionné par organisation | ✅ Réalisé |
| **Import Multi-Formats & Versionnement GPKG** | Téléversement direct de GeoPackage (`.gpkg`) et de modèles EPA SWMM (`.inp` avec parser et conversion automatique), versionnement immuable (`_enregistrer_version_gpkg`), catalogue de benchmarks intégrés (EPA Ex 1/3/4/6, Quartier Démo, Master Ville) | ✅ Réalisé |
| **Couches SIG Satellites Auxiliaires** | Import piloté de couches externes (`.shp` multi-fichiers/zip, `.gpkg`, `.geojson`), typage strict (`altimetrie_points`, `bv_officiel`, `metrologie`, `autre`), normalisation en GPKG mono-couche EPSG:4326, grille altimétrique IDW et artefact dérivé `regards_terrain.json` | ✅ Réalisé |
| **Extraction par Pochoir (SHP.md)** | Découpage spatial à la volée du réseau et des couches satellites par polygone GeoJSON (règle d'or spatiale d'INTERSECTION préservant l'intégrité des objets), export zip clé en main (Shapefiles thématiques, GeoPackage fusionné avec couche pochoir, manifeste JSON) | ✅ Réalisé |
| **Gestion Manuelle de Bassins Versants** | Découpage interactif et regroupement manuel de conduites sur la carte pour former un sous-réseau, affectation d'exutoire sur-mesure, CRUD complet (`/api/v1/clusters/manual-basins`) et persistance isolée `manual_overrides_{org_id}.json` | ✅ Réalisé |
| **Moteur Hydrodynamique PySWMM 5.2** | Intégration binaire officielle 5.2.4 x64, résolution `DYNWAVE` Saint-Venant 1D, bilans massiques stricts (< 0.2% d'erreur) | ✅ Réalisé |
| **Hydrologie de Surface Voronoï** | Découpage Voronoï/Thiessen borné (59 sous-bassins, 13.02 ha), attribution d'exutoires, infiltration de Horton ($f_0, f_c, k$) | ✅ Réalisé |
| **Hyétogrammes Pluvieux & Événements** | Lois de Montana locales, pluies de projet Chicago (décennale, cinquantennale, orage d'été 2h, temps sec pur) | ✅ Réalisé |
| **Gestion des Apports de Temps Sec (DWF)** | Injection multi-profils (journalier, constant, industriel), modes EH/débit direct, sélecteur cartographique interactif avec masquage modal, légende dynamique (pastille fluorescente + débit L/s), réconciliation GPKG et traçabilité d'audit | ✅ Réalisé |
| **Contrôle Qualité Altimétrique & MNT** | Détection automatique des sauts de radier aberrants (> 20m ou MNT tronqué), registre interactif de validation/correction par l'ingénieur, intégration du nuage altimétrique TOPO Chlef (84 302 points IDW) | ✅ Réalisé |
| **Contrôle de Cohérence Pluie-Débit** | Confrontation débit de pointe Saint-Venant 1D vs Débit rationnel brut ($Q = C \cdot I \cdot A / 360$), qualification automatique du laminage et stockage temporaire en réseau | ✅ Réalisé |
| **Cockpit Leaflet HD & Profil en Long** | Profil en long HGL interactif (ligne piézométrique, génératrice supérieure, hachures sous pression), isolation des bassins non simulables, optimisation de chargement (-77% de requêtes), modal de résultats HD | ✅ Réalisé |
| **Animation Temporelle (Time Slider)** | Extraction des chroniques depuis le fichier binaire `.out` (0h → 24h), coloration dynamique du taux de charge $Q/Q_{\max}$, radars visuels de débordement | ✅ Réalisé |
| **Rapport d'Expertise Technique A4** | Générateur PDF réglementaire en 1 clic (ReportLab) avec planches cartographiques, tableaux des surcharges, durées de submersion et bordereau estimatif de travaux (BPU) | ✅ Réalisé |

---

## 🚀 À FAIRE — Chantiers Prioritaires Immédiats

### 1. Conduites de Refoulement Sous Pression & Stations de Relevage

> **Objectif :** Intégrer fidèlement la modélisation hydraulique des conduites de refoulement sous pression alimentées par des postes de pompage sans instabilité numérique.

- [ ] **1.1 Formalisation topologique du quadruplet SWMM :**
  - Bâche de pompage : Déclaration en nœud de type `[STORAGE]` avec loi hauteur-volume $V(h)$ et cotes de marnage (démarrage/arrêt).
  - Ouvrage de pompage : Déclaration en lien de type `[PUMPS]` avec courbe caractéristique de pompe Type 3 (HMT en fonction du débit $Q$).
  - Conduite de refoulement : Déclaration en lien de type `[CONDUITS]` avec section `[XSECTIONS]` en conduite forcée `FORCE_MAIN` (diamètre, équation de perte de charge Hazen-Williams $C_{\text{HW}}$ ou Darcy-Weisbach $\epsilon$).
  - Chambre de rupture gravitaire : Déclaration du nœud aval en `[JUNCTIONS]` avec cote de déversement à l'atmosphère.
- [ ] **1.2 Paramétrage de stabilité du solveur hydrodynamique :**
  - Réduction automatique du pas de temps de routage hydraulique ($\Delta t \le 1$ à 5 s) dès présence d'une `FORCE_MAIN`.
  - Activation de l'amortissement d'inertie `INERTIAL_DAMPING FULL`.
  - Pas de temps variable basé sur le critère de Courant (`VARIABLE_STEP 0.75`).
- [ ] **1.3 Rendu cartographique & Profil en long HGL sous pression :**
  - Affichage spécifique des conduites de refoulement sur la carte Leaflet (tracé violet/indigo distinctif avec icône de station de pompage).
  - Tracé du profil en long HGL adapté aux conduites forcées : continuité de la ligne piézométrique en charge au-dessus de la génératrice supérieure jusqu'à la chambre de rupture sans décrochement artificiel.
- [ ] **1.4 Tests de non-régression hydraulique :**
  - Validation sur cas test canonique (Station de relevage refoulant vers collecteur gravitaire principal).
  - Vérification de la continuité massique (erreur $< 0.5\%$).

---

### 2. État du Réseau, Sédimentation & Vieillissement des Conduites

> **Objectif :** Quantifier l'impact du vieillissement structurel, de l'entartrage et de la sédimentation sur la capacité d'évacuation hydraulique du réseau.

- [ ] **2.1 Intégration de la sédimentation de fond de radier (`Geom3`) :**
  - Exploitation du paramètre natif EPA SWMM 5.2 `Geom3` (hauteur de dépôts de sédiments au fond de la canalisation $h_{\text{séd}}$) dans la section `[XSECTIONS]`.
  - Calcul automatique de la réduction de section d'écoulement et de la perte de capacité théorique.
- [ ] **2.2 Ajustement de rugosité et réduction de diamètre effectif (Normes EN 13508-2 / DWA-A 110) :**
  - Prise en compte de la rugosité accrue due aux dépôts et à l'abrasion : ajustement dynamique du coefficient de Manning $n$ (ex. passage de 0.013 à 0.018 - 0.025).
  - Déduction du diamètre effectif $D_{\text{eff}} = D_{\text{nominal}} - 2 \cdot e_{\text{croûte}}$.
- [ ] **2.3 Scénarios d'exploitation comparatifs (Avant / Après curage) :**
  - Modal de simulation avec bascule "État du réseau" : *Neuf / Réhabilité*, *Exploitation normale*, *Réseau encrassé / Sédimenté (20% radier)*.
  - Visualisation comparative sur le cockpit : surcharges induites par l'encrassement, apparition de débordements prématurés.
  - Chiffrage estimatif du volume de boues à curer ($m^3$) dans le rapport de diagnostic.

---

### 3. Déconnexion Manuelle d'Exutoires & Correction des Frontières de Bassins

> **Objectif :** Permettre à l'ingénieur d'ajuster interactivement le modèle topologique pour isoler ou corriger les bassins d'exutoires.

- [ ] **3.1 Coupure interactive de tronçons frontières sur la carte :**
  - Outil "Ciseau / Déconnexion" pour scinder ou désactiver un tronçon frontière (ex. liaison DVO 166 vers trop-plein 171).
  - Recalcul instantané des bassins versants amont et des ordres topologiques.
- [ ] **3.2 Filtrage d'exutoires secondaires dans la modal de paramétrage :**
  - Sélection / désélection des exutoires pris en compte dans le sous-modèle de calcul.
- [ ] **3.3 Requalification d'ouvrages spéciaux :**
  - Définition d'un seuil ou d'une vanne comme frontière étanche interdisant la remontée amont.

---

### 4. Phase 5 — API Publique & Interopérabilité SIG (QGIS / GeoJSON)

- [ ] **4.1** Clés d'API persistantes (`sp_live_...`) avec permissions granulaires pour requêtes externes.
- [ ] **4.2** Endpoints d'export à la volée du réseau filtré en GeoPackage (`.gpkg`) et GeoJSON.
- [ ] **4.3** Flux de tuiles vectorielles (MVT / WFS) pour les très grands réseaux (> 50 000 regards).
- [ ] **4.4** Documentation Swagger / OpenAPI 3.0 certifiée avec schémas Pydantic.

---

### 5. Phase 7 — Industrialisation Docker & Déploiement Production

- [ ] **5.1** Fichier `docker-compose.yml` multi-services complet (FastAPI, Celery, PostgreSQL 16 PostGIS, Redis 7, MinIO, Caddy SSL).
- [ ] **5.2** Dockerfile multi-étapes optimisé avec compilation C/C++ (GDAL, GEOS, PROJ, EPA SWMM 5.2.4 Toolkit).
- [ ] **5.3** Pipeline CI/CD GitHub Actions (pytest, Golden Master, intégrité syntaxique JS).
- [ ] **5.4** Journalisation structurée JSON, métriques de santé `/api/v1/health` et checklist Go-Live OWASP.

---

### 6. Phase 4 — Mobilité Terrain & Synchronisation Déconnectée (Flutter)

- [ ] **6.1** Protocole Delta Sync différentiel avec curseur temporel (`since_timestamp`) et gestion des suppressions.
- [ ] **6.2** Cache local SQLite mobile et file d'attente hors-ligne.
- [ ] **6.3** Téléversement des photographies d'anomalies vers MinIO/S3 avec liaison d'ouvrage.
- [ ] **6.4** Journal d'audit terrain immuable (`field_audit_logs`) et moteur de réconciliation des conflits.

---

## 📁 Arborescence Réelle du Projet

```
api/
  main.py                          Application FastAPI (port 5002)
  routes/
    network.py                     Upload GPKG/INP, benchmarks EPA, regards, conduites, rejets
    aux_layers.py                  Upload couches satellites (.shp, .gpkg, .zip), altimétrie IDW
    extractions.py                 Extraction par pochoir spatial (SHP.md → zip thématique)
    clusters.py                    Graphe topologique, bassins d'exutoires, bassins manuels
    simulations.py                 Orchestration SWMM 5.2, cotes suspectes, HGL, Time Slider
    apports.py                     Injection des apports de temps sec (DWF)
    qualite.py                     Diagnostic des anomalies, contre-pentes, sauts de radier
  services/
    extraction_pochoir_service.py  Découpage géométrique par intersection stricte et packaging zip
    aux_layers_service.py          Normalisation GPKG mono-couche et gestion du cycle de vie
    aux_altimetrie_service.py      Grille IDW, sonde d'altitude, regards_terrain.json
    simulation_service.py          Résolution GPKG effectif, cache et exécution PySWMM
  core/
    storage.py                     ArtifactStore (MinIO / S3 / Local sécurisé)
    security.py                    TenantContext, isolation stricte multi-tenant et stealth 404
    quotas.py                      Contrôle des quotas par plan de licence

src/
  domain/
    moteur_swmm.py                 Générateur de fichiers .INP officiel EPA SWMM 5.2
    hydrologie.py                  Découpage Voronoï/Thiessen, Horton et hyétogrammes Chicago/Montana
    pyswmm_wrapper.py              Solveur PySWMM 5.2.4 x64 Saint-Venant 1D (DYNWAVE)
    timeseries_extractor.py        Parser binaire des chroniques d'écoulement (.out)
    inp_parser.py                  Parser et convertisseur transparent .inp vers .gpkg
    ouvrages_orphelins.py          Scan spatial et raccordement opportuniste (Variante 0)
    rapport_diagnostic.py          Génération du rapport d'expertise A4 ReportLab avec BPU
  infrastructure/
    persistance_manuelle.py        Persistance isolée des bassins manuels (manual_overrides)
    chargeur_geopackage.py         Lecture optimisée et cache des couches GeoPackage

static/
  js/                              Cockpit Leaflet HD modulaire (carte, profils HGL, DWF, slider...)
  css/                             Feuilles de styles cartographiques et cockpit d'ingénierie
templates/                         Templates HTML Jinja2 (cockpit d'exploitation, modals HD)
docs/
  13_ROADMAP_SAAS.md               Feuille de route SaaS industrielle complète (Phases 0 à 7)
  TODO_PHASES_4_7.md               Suivi détaillé des phases 4 à 7
  FEUILLE_DE_ROUTE_2027_2029.md    Orientations stratégiques pluriannuelles DrainPilot
  16_METHODOLOGIE_SIMULATION_SWMM.md  Méthodologie scientifique et équations SWMM 5.2
SHP.md                             Spécification d'architecture des couches satellites & pochoir
tests/                             Suite complète de validation continue (Golden Master, DWF, cotes...)
```
