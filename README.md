# DrainPilot 5.2 — Plateforme SaaS d'Ingénierie & Modélisation Hydraulique d'Assainissement

[![SWMM 5.2](https://img.shields.io/badge/Solver-EPA%20SWMM%205.2.4-blue.svg)](https://www.epa.gov/water-research/storm-water-management-model-swmm)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI%200.115-teal.svg)](https://fastapi.tiangolo.com)
[![Leaflet HD](https://img.shields.io/badge/Frontend-Leaflet%20HD%20Cockpit-green.svg)](https://leafletjs.com)
[![Multi-Tenant](https://img.shields.io/badge/Architecture-Multi--Tenant%20Stealth%20404-orange.svg)]()
[![Tests](https://img.shields.io/badge/Tests-100%25%20Validés-success.svg)]()

> **DrainPilot 5.2** est la plateforme SaaS industrielle de référence pour l'audit patrimonial, le diagnostic de qualité géospatiale, la modélisation hydrodynamique certifiée EPA SWMM 5.2 (Saint-Venant 1D) et la gestion de crise pluviale des réseaux d'assainissement et d'eaux pluviales.

---

## 📚 Référentiel Documentaire Officiel

- **[Guide Master SaaS](docs/01_README.md)** : Vue d'ensemble de la plateforme SaaS, installation et démarrage rapide.
- **[Feuille de Route SaaS (Phases 0 à 7)](docs/13_ROADMAP_SAAS.md)** : Spécifications complètes de l'architecture industrielle, chiffrage et jalons mesurables.
- **[Suivi des Phases Opérationnelles 4 à 7](docs/TODO_PHASES_4_7.md)** : Checklist détaillée des travaux et priorités immédiates.
- **[Feuille de Route Pluriannuelle 2027–2029](docs/FEUILLE_DE_ROUTE_2027_2029.md)** : Visions stratégiques et extensions futures (DAO AutoCAD, Jumeau numérique).
- **[Documentation des Endpoints API](docs/09_ENDPOINTS_DOCUMENTATION.md)** : Référentiel exhaustif des 19 routeurs et 137 endpoints FastAPI.
- **[Spécification Couches Satellites & Pochoir (SHP.md)](SHP.md)** : Architecture des données SIG externes, altimétrie IDW et extraction par pochoir.
- **[Référentiel Pluviométrique & IDF Algérie](docs/REFERENTIEL_PLUVIOMETRIE_ALGERIE.md)** : Quantiles Gumbel et lois de Montana certifiées (ANRH/UHBC/ONA).
- **[Fiche Produit & Cadrage Stratégique](docs/14_FICHE_PRODUIT_CADRAGE.md)** : Proposition de valeur, personas et parcours utilisateurs.
- **[Grille Tarifaire & Plans B2B](docs/15_PLANS_TARIFAIRES.md)** : Modèle économique, quotas et monétisation.
- **[Dossier des Décisions d'Architecture (ADR)](docs/adr/)** : ADR 0001 à 0008 (Auth Argon2id, Multi-tenancy, Celery, MinIO S3, Docker, etc.).

---

## 🚀 Capacités & Fonctionnalités Clés du SaaS

### 1. Ingestion Multi-Formats & Versionnement Immuable
- **Téléversement Direct** : Prise en charge native des fichiers **GeoPackage (`.gpkg`)** et des fichiers **EPA SWMM (`.inp`)** avec conversion automatique et transparente vers GeoPackage.
- **Versionnement Immuable (Snapshots)** : Chaque import génère une empreinte SHA-256 avec archivage sécurisé. Les simulations historiques pointent toujours sur le snapshot exact producteur.
- **Bibliothèque de Benchmarks Embarqués** : Chargement instantané des modèles de référence EPA (Example 1 Drainage, Example 3 Unitaire & DVO, Example 4 Rétention, Example 6 Techniques Alternatives LID), Quartier Démo (59 regards) et Master Métropole (+11 000 tronçons).
- **Couches Satellites Auxiliaires ([SHP.md](SHP.md))** : Import piloté de Shapefiles `.shp` complets (avec `.shx/.dbf/.prj/.cpg` ou sous forme de `.zip`), GeoJSON et GPKG externes (cadastre, voirie, cours d'eau, réseaux divers) sans impacter le modèle de calcul.

### 2. Outil SIG d'Extraction par Pochoir Spatial
- **Découpage Géométrique à la Volée** : Sélection spatiale d'une zone d'étude par un polygone GeoJSON (tracé interactif ou importé).
- **Règle d'Or Spatiale d'INTERSECTION** : Tout élément du réseau ou des couches satellites qui touche la frontière est conservé **en entier** pour garantir la continuité topologique et hydraulique.
- **Livrable Zip Téléchargeable** : Production instantanée d'une archive contenant les Shapefiles thématiques par couche (`{nom}_regards.shp`, `{nom}_canalisations.shp`), le GeoPackage unifié `{nom}.gpkg` fusionné avec le polygone `pochoir`, et le fichier `manifeste.json` (statistiques et traçabilité).

### 3. Diagnostic Qualité Réseau & Corrections Supervisées
- **Audit Topologique Automatisé** : Détection des contre-pentes, des sauts de radier anormaux, des diamètres non normalisés, des conduites orphelines et calcul des débits théoriques selon NP 650 et Manning-Strickler.
- **Scores par Commune et par Bassin** : Évaluation objective de la santé de la donnée (0 à 100) et export des anomalies en CSV/Excel.
- **Suggestions Hybrides et Profil Altimétrique** : Propositions statistiques de rattrapage de pente selon le diamètre et le matériau (`/corrections/{fid}/hybride`) avec validation supervisée par l'ingénieur.

### 4. Moteur Hydrodynamique PySWMM 5.2 (Saint-Venant 1D)
- **Résolution Onde Dynamique (`DYNWAVE`)** : Résolution numérique complète des équations de Saint-Venant 1D via les binaires officiels EPA SWMM 5.2.4 x64 compilés (aucun binaire externe requis).
- **Bilan de Continuité Massique Strict** : Contrôle automatique de conservation des masses avec une erreur systématiquement inférieure à $0.2\%$ (typiquement $-0.166\%$).
- **Hydrologie de Surface Voronoï & Horton** : Découpage automatisé de sous-bassins élémentaires Voronoï/Thiessen bornés aux linéaires de canalisation, calcul de pente, largeur $W$, imperméabilisation (`%Imperv`) et infiltration de Horton ($f_0, f_c, k$).
- **Hyétogrammes de Projet & Pluviométrie Réelle** : Lois de Montana certifiées, averses de Chicago (décennale, cinquantennale, centennale), orages violents de 2h et chroniques au pas de 5 min.

### 5. Module d'Alerte & Simulation BMS (ONM Algérie)
- **Modélisation sur Bulletins Météorologiques Spéciaux** : Simulation prédictive sur les alertes de l'Office National de la Météorologie (cumul mm, durée h, profils de pluie en cloche Huff ou orage concentré).
- **Générateur d'Ordres de Mission Préventifs** : Édition automatique des ordres de mission terrain pour les régies d'assainissement (ONA) ciblant les regards et avaloirs à curer d'urgence avant l'arrivée de la pluie selon le niveau d'alerte (Jaune, Orange, Rouge).

### 6. Gestion Avancée des Apports de Temps Sec (DWF)
- **Injection Multi-Profils** : Sollicitations d'eaux usées domestiques (profil horaire journalier urbain), apports continus et rejets industriels.
- **Modes de Saisie Flexibles** : Équivalents-Habitants (EH) avec dotation en L/j/hab ou débit direct en L/s et $\text{m}^3/\text{j}$.
- **Sélecteur Cartographique HD** : Sélection interactive au clic sur la carte Leaflet avec masquage temporaire de la modale et neutralisation des popups parasites.
- **Légende Cartographique Dynamique** : Anneau fluorescent cyan/bleu marquant les regards injectés et affichage du débit journalier cumulé en L/s en temps réel.
- **Réconciliation & Traçabilité** : Réconciliation automatique avec le GeoPackage source et journal d'audit immuable (`apports_dwf_history`).

### 7. Contrôle Altimétrique & Registre des Cotes Suspectes
- **Nuage de Points Réels TOPO Chlef** : Intégration de 84 302 points cotés réels avec index spatial et interpolation IDW locale.
- **Détection des Sauts de Radier Aberrants** : Blocage préventif du tracé de profil en long en cas d'incohérence altimétrique critique (> 20 m).
- **Registre Interactif de Validation** : Interface ingénieur permettant de valider ou corriger instantanément les cotes suspectes avec persistance immédiate.

### 8. Contrôle de Cohérence Pluie-Débit (Rationnel vs Saint-Venant)
- **Contrôle Rationnel de Premier Niveau** : Calcul du débit attendu brut ($Q = C \cdot I \cdot A / 360$) en amont de la simulation.
- **Qualification du Laminage Hydraulique** : Comparaison systématique avec le débit de pointe Saint-Venant 1D pour identifier le laminage et le stockage capacitif en réseau.

### 9. Cockpit d'Exploitation Leaflet HD & Profil en Long HGL
- **Profil en Long Hydraulique Interactif** : Ligne de charge piézométrique ($HGL$), cotes radiers amont/aval, génératrice supérieure, terrain naturel interpolé IDW, plan d'eau dynamique (WSP) et hachures de mise en charge sous pression ($HGL > \text{extrados}$).
- **Animation Temporelle de l'Onde de Crue (Time Slider)** : Curseur temporel 0h $\rightarrow$ 24h exploitant les séries binaires `.out`, coloration dynamique selon $Q(t)/Q_{\max}$ et radars visuels de débordement aux nœuds inondés.
- **Hydrogramme Dynamique aux Exutoires** : Graphique interactif Chart.js mis à jour à chaque pas de temps avec navigation temporelle au clic.
- **Isolation des Ouvrages Non Simulables** : Préservation de l'intégrité du rendu sur les sous-réseaux isolés.

### 10. Système d'Expertise Multi-Agents IA & Rapport A4 (PDF / BPU)
- **Chaîne Collaborative à 7 Agents Spécialisés** :
  - *Agent 0 (Garde-Fou Hydraulicien)* : Contrôle de cohérence physique et de pente.
  - *Agent 1 (Diagnostic)* : Analyse des débits de pointe et nœuds inondés.
  - *Agent 2 (Génie Civil)* : Recalibrage des diamètres et prescriptions structurelles.
  - *Agent 3 (GDO / Variante 0)* : Reconnexion opportuniste des singularités et déversoirs orphelins (gain > 90%).
  - *Agent 4 (Risques)* : Vulnérabilité voirie et piétons.
  - *Agent 5 (Finance & BPU)* : Chiffrage estimatif en DZD avec bordereau des prix unitaires.
  - *Agent 6 (Synthèse)* : Synthèse exécutive consolidée.
- **Rapport Réglementaire en 1 Clic** : Générateur PDF A4 haute définition (ReportLab) intégrant cartographie du réseau, bilans de masse et planches d'anomalies.

---

## 🏗️ Architecture Technique

```
                            ┌──────────────────────────────────────────────┐
                            │      Cockpit Web Bureau (Ingénieurs/BET)     │
                            │  Cartographie Leaflet HD, Profils HGL, SIG   │
                            └──────────────────────┬───────────────────────┘
                                                   │ HTTPS
                                          ┌────────▼────────┐
                                          │  Reverse Proxy  │  Caddy / Nginx (SSL, TLS, Gzip)
                                          └────────┬────────┘
                                                   │
                            ┌──────────────────────▼──────────────────────┐
                            │           DrainPilot Web API                │
                            │             (FastAPI Unifié)                │
                            │  - Routeurs modulaires (/api/v1/*)          │
                            │  - Authentification Argon2id & JWT/Cookies  │
                            │  - Isolation Multi-Tenant (Stealth 404)     │
                            │  - Moteur de Quotas B2B & Licences          │
                            │  - Solveur PySWMM 5.2.4 x64 Embarqué        │
                            └───────┬──────────────┬──────────────┬───────┘
                                    │              │              │
                         ┌──────────▼───┐   ┌──────▼──────┐   ┌───▼──────────┐
                         │  PostgreSQL  │   │    Redis    │   │   S3/MinIO   │
                         │   + PostGIS  │   │  - Cache    │   │  - Artifacts │
                         │  - Tenants   │   │  - Broker   │   │  - .INP/.RPT │
                         │  - Réseaux   │   │  - Statuts  │   │  - Rasters   │
                         │  - Licences  │   └──────┬──────┘   │  - PDF / Zip │
                         └──────────────┘          │          └──────────────┘
                                            ┌──────▼──────┐
                                            │ Worker Async│
                                            │   Celery    │  Calculs lourds SWMM
                                            └─────────────┘
```

---

## 💻 Installation & Démarrage Rapide

### Prérequis
- Python 3.11 ou 3.12 (64-bit recommandé pour les binaires SWMM 5.2).
- Environnement virtuel Python activé.

### 1. Installation des dépendances
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Lancement du serveur API & Cockpit Web
```bash
# Lancement de la plateforme unifiée FastAPI
python run_server.py

# Ou avec rechargement automatique en développement :
python run_api.py
```

### 3. Accès aux interfaces
- **Cockpit Cartographique Leaflet HD** : `http://localhost:5002/`
- **Documentation API Swagger Interactive** : `http://localhost:5002/docs`
- **Sonde de Santé** : `http://localhost:5002/health`

---

## 🧪 Validation & Non-Régression Continue

DrainPilot 5.2 applique une politique de tolérance zéro aux régressions :
- **Golden Master de Référence** : `tests/test_golden_master.py` garantit la stricte invariance des calculs hydrauliques Saint-Venant 1D.
- **Intégrité Syntaxique JS** : Validation automatique Node.js sur tous les modules `static/js/`.
- **Livraison Continue Autonome (Zero-Prompt Git)** : Validation automatique à 100% avant chaque commit et push distant.

```bash
# Exécution de la suite de tests complète
pytest -v

# Exécution du Golden Master et des modules clés
pytest -q tests/test_golden_master.py tests/test_js_syntax_integrity.py tests/test_dwf_injection.py
```

---

## 👤 Auteur & Propriété Intellectuelle

**Dr Abdelhakim KELLOUCHE**  
Docteur en Génie Hydraulique & Expert en Modélisation d'Assainissement Urbain  
*DrainPilot 5.2 — Tous droits réservés.*
