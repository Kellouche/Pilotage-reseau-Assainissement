# SWMM Platform — Pilotage & Modélisation Réseau d'Assainissement SaaS

## 📚 Référentiel Documentaire SaaS 2.0 (Officiel)

- **[Guide Master SaaS](docs/01_README.md)**
- **[Référentiel National Pluviométrique & IDF Algérie (ANRH/UHBC/ONA)](docs/REFERENTIEL_PLUVIOMETRIE_ALGERIE.md)**
- **[Feuille de Route SaaS (Phases 0 à 7)](docs/13_ROADMAP_SAAS.md)**
- **[Fiche Produit & Cadrage Stratégique](docs/14_FICHE_PRODUIT_CADRAGE.md)**
- **[Glossaire et Garanties Métier (Non-Régression)](docs/14_GLOSSAIRE_ET_GARANTIES.md)**
- **[Grille Tarifaire & Plans B2B](docs/15_PLANS_TARIFAIRES.md)**
- **[Documentation Complète des Endpoints API](docs/09_ENDPOINTS_DOCUMENTATION.md)**
- **[Dossier des Décisions d'Architecture (ADR 0001 à 0008)](docs/adr/)**

---

## Documentation Historique du POC

- [Feuille de route POC](docs/ROADMAP.md)
- [Organisation du projet](docs/ORGANISATION_PROJET.md)
- [Inventaire du projet](docs/INVENTAIRE_PROJET.md)
- [Lancement du projet](docs/LANCEMENT.md)
- [Données du projet](docs/DONNEES.md)
- [Application mobile](docs/MOBILE.md)
- [Vision plateforme](README_PLATFORM.md)

Outils de visualisation interactive et de génération de fichiers SWMM 5.2 à partir de données GeoPackage.

## Fonctionnalités Clés du Moteur SWMM 5.2 & SIG

- **Visualisation cartographique interactive** (Leaflet.js) avec gestion multi-couches (conduites, regards, exutoires, sous-bassins Voronoï, éléments orphelins).
- **Partitionnement topologique hydraulique strict** :
  - Découpage automatique des bassins versants d'exutoires physiques sans chevauchement.
  - Détermination des sous-bassins élémentaires par cellules de Voronoï bornées par le rayon de drainage urbain et le corridor de conduite (15 m).
  - Résolution anti-collision d'identifiants entre couches hétérogènes (regards, rejets, ouvrages) et validation géométrique de proximité amont/aval ($\le 25\text{ m}$) éliminant tout raccordement aberrant ou "trou de ver".
  - Garantie de contiguïté stricte : élimination des MultiPolygones disjoints, chaque bassin constitue un polygone unique compact et connexe.
- **Gestion des éléments orphelins (déconnectés)** :
  - Isolation rigoureuse des tronçons et regards sans exutoire physique documenté dans une couche dédiée (`elements_orphelins_regards`) et export GeoJSON indépendant (`elements_orphelins.geojson`).
  - Suppression de tout "snapping" euclidien aveugle vers des exutoires distants.
- **Moteur de Simulation Hydrodynamique SWMM 5.2** :
  - Sectorisation obligatoire par exutoire avant calcul.
  - **Référentiel Pluviométrique National Certifié (ANRH / UHBC / ONA)** : intégration de 7 stations hydro-météorologiques dans la Wilaya de Chlef (Chlef Siège, Oum Drou, Oued Fodda, Bénaïria, Domaine Si Tayeb, Ténès, Boukadir) avec quantiles Gumbel $P_{24}$ et coefficients de Montana $a, b$ certifiés par l'Université Hassiba Ben Bouali de Chlef.
  - Hyétogrammes de projet Chicago centrés ($r=0.40$), contrôle automatique pluie-débit (méthode rationnelle $Q_{\text{rat}} = C \cdot I \cdot A / 360$) et champ de saisie manuelle de l'intensité $I_{\max}$ pour scénarios personnalisés.
  - Sélecteur de typologie urbaine dominante (Centre urbain dense, Collectif, Pavillonnaire, Mixte, Périurbain) et surcharge manuelle du taux d'imperméabilisation (`% Imperv`).
  - Diagnostic hydraulique en temps réel : débits de pointe, erreurs de continuité, mise en charge des conduites ($Q/Q_{\max}$), identification des surcharges et des débordements en surface.
  - Restitution cartographique aux normes d'ingénierie : cercles nets et discrets (Débordement 5.5 px, Surcharge 4.0 px, Normal 2.5 px), sans animation pulsante invasive.
- **Gestion dynamique des jeux de données & caches multi-tenants** :
  - Invalidation et synchronisation immédiate des mémoires caches (graphe, clusters, sous-bassins, dernière simulation) lors du téléversement ou du changement de jeu de données.
  - Actualisation dynamique des statistiques d'en-tête et du panneau latéral selon la zone ou le projet sélectionné.
- **Reprojection automatique** UTM Zone 31N (EPSG:32631) → WGS84 (EPSG:4326).
- **Analyse de qualité réseau** : détection d'anomalies topologiques, scores de qualité et rapports d'expertise.

## Installation

```bash
pip install -r requirements.txt
```

## Utilisation

### Visualisation interactive

```bash
python server.py
# ouvrir http://localhost:5000
```

### Tests

```bash
python -m pytest tests/ -v
```

### Analyse qualité réseau

```bash
# Démarrer l'API
python run_server.py

# Ouvrir les interfaces
# http://localhost:5001/qualite - Tableau de bord qualité
# http://localhost:5001/carte - Carte opérationnelle interactive

# API qualité réseau
# GET /api/v1/qualite/analyse - Analyse complète
# GET /api/v1/qualite/anomalies/{type} - Anomalies par type
# GET /api/v1/qualite/scores - Scores de qualité
# POST /api/v1/qualite/export-csv - Export CSV
```

### Carte opérationnelle

Interface cartographique interactive pour :
- **Visualiser** le réseau d'assainissement
- **Localiser** les anomalies détectées
- **Filtrer** par type et sévérité
- **Corriger** les anomalies directement sur la carte

## Structure du projet

```
src/
  controllers/     Contrôleurs Flask et générateur SWMM
  domain/          Logique métier (traitement nœuds, conduites, pompes)
  infrastructure/  Chargement GeoPackage, configuration
  views/           Interface web (HTML, CSS, JS)
tests/             Tests unitaires et d'intégration
```

Voir TODO.md pour l'arborescence détaillée.

## Données

| Élément              | Nombre  |
|----------------------|---------|
| Regards              | 10 538  |
| Rejets               | 79      |
| Canalisations        | 10 295  |
| Ouvrages spéciaux    | 38      |
| Stations de relevage | 5       |
| STEP                 | 1       |

## Dépendances

- geopandas, pandas, shapely, numpy — traitement géospatial
- flask — serveur web

## Auteur

Dr Abdelhakim Kellouche
