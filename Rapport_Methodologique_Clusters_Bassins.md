# Rapport methodologique : Modelisation de clusters hydrauliques et delimitation de bassins versants a partir d'un reseau d'assainissement

**Date :** 1er avril 2026  
**Version :** 1.0  
**Statut :** Document de travail — a valider avant implementation

---

## Table des matieres

1. [Resume executif](#1-resume-executif)
2. [Cadre conceptuel](#2-cadre-conceptuel)
3. [Etat de l'art et revue de litterature](#3-etat-de-lart-et-revue-de-litterature)
4. [Methodologie recommandee](#4-methodologie-recommandee)
5. [Architecture du pipeline de traitement](#5-architecture-du-pipeline-de-traitement)
6. [Donnees et sources recommandees](#6-donnees-et-sources-recommandees)
7. [Outils et bibliotheques](#7-outils-et-bibliotheques)
8. [Criteres d'evaluation et plan de validation](#8-criteres-devaluation-et-plan-de-validation)
9. [Risques et limites](#9-risques-et-limites)
10. [Plan de mise en oeuvre avec jalons](#10-plan-de-mise-en-oeuvre-avec-jalons)
11. [References](#11-references)

---

## 1. Resume executif

Ce rapport definit une methodologie pour :

1. **Delineer des clusters hydrauliques** comme l'ensemble des canalisations convergent vers un point de rejet (exutoire), en integrant regards et ouvrages hydrauliques dans la topologie du reseau.

2. **Delimiter les bassins versants** a partir d'un Modele Numerique de Terrain (MNT/DEM) et de courbes de niveau, en integrant le reseau souterrain pour ameliorer la detection des petits bassins urbains.

L'approche recommandee repose sur trois piliers complementaires :

- **Theorie des graphes** pour l'analyse topologique du reseau d'assainissement (composantes connexes dirigées vers les exutoires).
- **Analyse hydrologique du MNT** pour la derivation du reseau de drainage surfacique et la delimitation des bassins (flow direction, flow accumulation).
- **Couplage reseau souterrain / topographie** pour integrer l'infrastructure dans la modelisation des bassins, en modifiant le MNT aux emplacements des regards et canalisations.

Le pipeline propose est implementable en Python avec GeoPandas, NetworkX, PySheds/TauDEM, et constitue une preparation directe au passage au codage dans l'application existante.

---

## 2. Cadre conceptuel

### 2.1 Definitions

**Cluster hydraulique** : Ensemble des canalisations, regards et ouvrages hydrauliques dont le drainage converge vers un meme point de rejet (exutoire). Equivalent fonctionnel d'un « sous-reseau d'assainissement ».

**Bassin versant** : Surface topographique dont toutes les eaux de ruissellement convergent vers un meme point de sortie (exutoire). En milieu urbain, ce bassin est modifie par l'infrastructure souterraine.

**Point de rejet** : Exutoire du reseau d'assainissement — peut etre un rejet dans un cours d'eau, une STEP, ou un collecteur principal.

**MNT (DEM)** : Modele Numerique de Terrain — grille raster ou chaque pixel represente l'altitude du sol.

**Courbes de niveau** : Lignes iso-altitude tracees a partir du MNT, permettant de visualiser la topographie.

### 2.2 Principe fondamental

Un cluster hydraulique se definit a rebours a partir du point de rejet :

```
Point de rejet (exutoire)
    ↑
    ├── Canalisation aval (directement connectee au rejet)
    │     ↑
    │     ├── Regard amont
    │     │     ↑
    │     │     ├── Canalisation amont
    │     │     │     ↑
    │     │     │     └── Regard amont ...
    │     │     └── Ouvrage special
    │     └── Confluence avec autre canalisation
    └── Station de relevage (pompe)
```

Le cluster est donc un **arbre dirige inverse** dont la racine est le point de rejet.

### 2.3 Relation cluster / bassin versant

En theorie, le bassin versant topographique et le cluster hydraulique devraient correspondre. En pratique :

| Milieu   | Correspondance | Explication |
|----------|---------------|-------------|
| Urbain dense | Faible | Infrastructure souterraine cree des bassins artificiels |
| Peri-urbain | Moyenne | Mixte naturel et infrastructure |
| Rural | Forte | Drainage principalement topographique |

L'enjeu principal est en **milieu urbain**, ou le reseau souterrain redistribue les eaux independamment de la topographie de surface. L'approche recommandee integre donc les deux sources d'information.

---

## 3. Etat de l'art et revue de litterature

### 3.1 Analyse topologique des reseaux d'assainissement

#### 3.1.1 Theorie des graphes appliquee aux reseaux d'assainissement

Les reseaux d'assainissement sont naturellement des **graphes orientes acycliques (DAG)** : les conduites sont les aretes, les regards les noeuds, et l'orientation suit le sens de l'ecoulement gravitaire.

**Reyes-Silva et al. (2020)** [1] ont demontre que les caracteristiques fonctionnelles des reseaux d'assainissement urbains (transport et collecte des eaux usees) peuvent etre exprimees en termes de topologie du reseau, en utilisant des mesures de centralite et de plus courts chemins. Leur etude sur 8 sous-reseaux du reseau de Dresde montre que :

- Le **temps de parcours residuel** (Residence Time) comme poids des aretes permet de representer la distribution des temps de parcours.
- L'**Edge Betweenness Centrality (EBC)** identifie les conduites critiques reliant differentes composantes du systeme.
- Le nombre de **plus courts chemins vers la destination** (Paths) est fortement correle aux debits moyens (coefficient de correlation > 0.9).

Ce resultat est directement applicable a notre probleme : les clusters hydrauliques sont identifiables par les **composantes connexes** du graphe oriente vers chaque exutoire.

**Meijer et al. (2018)** [2] ont developpe une methodologie basee sur la theorie des graphes pour identifier les elements critiques dans les reseaux d'assainissement, en utilisant la centralite de noeuds et d'aretes pour localiser les points de defaillance potentiels.

**Li et al. (2025)** [3] proposent une reconstruction de graphes pour les reseaux d'assainissement incomplets, en utilisant des algorithmes de completion topologique. Cette approche est pertinente pour notre contexte ou les donnees du GeoPackage peuvent contenir des lacunes.

#### 3.1.2 Partitionnement de reseaux

**Di Nardo et al. (2017)** [4] ont developpe des methodes de clustering spectral pondere pour le partitionnement de reseaux de distribution d'eau, applicables aux reseaux d'assainissement.

**Schaeffer (2011)** [5] propose un cadre general de clustering topologique pour l'analyse des systemes de distribution d'eau, utilisant des methodes de partitionnement de graphes.

### 3.2 Delimitation de bassins versants a partir de MNT

#### 3.2.1 Approches classiques (DEM seul)

L'approche classique de delimitation de bassins versants suit un pipeline standard :

1. **Remplissage des depressions** (fill) du MNT
2. **Calcul de la direction d'ecoulement** (flow direction) — algorithme D8 (8 directions) ou D-infinity
3. **Calcul de l'accumulation d'ecoulement** (flow accumulation)
4. **Extraction du reseau hydrographique** — seuillage de l'accumulation
5. **Identification des points de sortie** (pour points)
6. **Delimitation des bassins** par propagation amont

Outils : **TauDEM** (Tarboton, Utah State University) [6], **WhiteboxTools** [7], **GRASS r.watershed** [8], **PySheds** [9].

#### 3.2.2 Approches integrees (DEM + infrastructure)

**Si et al. (2024)** [10] (Universite du Maryland) ont developpe et compare trois methodes pour integrer l'infrastructure souterraine dans la delimitation des bassins :

1. **« Depression digging »** : Modification du MNT aux emplacements des entrees de reseau (regards), en abaissant l'altitude pour creer des depressions artificielles qui attirent le ruissellement.

2. **« Stream burning »** : Modification du MNT le long du trace des canalisations, en abaissant l'altitude pour creuser un chenal artificiel qui guide l'ecoulement vers le reseau.

3. **GRASS r.watershed** avec parametre « depression » : Le module R.watershed de GRASS accepte un parametre de depressions qui force l'ecoulement a converger vers ces points.

Resultats cles de cette etude :
- Le coefficient de similarite Dice (DSC) entre les methodes est de 0.80 en moyenne (bonne reproductibilite).
- Les delimitations integrant l'infrastructure **different significativement** de celles basees uniquement sur le DEM (DSC plus bas, test de Mann-Whitney significatif).
- L'integration de l'infrastructure est donc **necessaire** pour une modelisation realiste en milieu urbain.

#### 3.2.3 Role des courbes de niveau

Les courbes de niveau permettent :
- La **verification visuelle** de la coherence des bassins delimites.
- Le **« nouage »** des courbes de niveau : identification des colles (points bas entre deux collines) pour tracer les lignes de partage des eaux. Cette approche est utilisee en hydrographie classique pour les petits bassins.
- L'**interpolation** d'un MNT de haute resolution a partir des courbes de niveau, ameliorant la precision des bassins dans les zones a forte variabilite topographique.

### 3.3 Matrice de choix entre alternatives

| Critere | DEM seul | DEM + depression | DEM + stream burning | GRASS r.watershed | Theorie des graphes |
|---------|----------|-----------------|---------------------|-------------------|-------------------|
| Complexite d'implementation | Faible | Moyenne | Moyenne | Faible | Moyenne |
| Fidelite en milieu urbain | Faible | Bonne | Bonne | Bonne | Tres bonne (pour le reseau) |
| Dependance aux donnees MNT | Tres forte | Forte | Forte | Forte | Nulle |
| Cout computationnel | Faible | Faible | Faible | Moyen | Faible |
| Robustesse aux donnees manquantes | Faible | Moyenne | Faible | Moyenne | Bonne |
| Applicabilite sans MNT | Non | Non | Non | Non | Oui |
| Couverture (bassin vs reseau) | Bassin | Bassin | Bassin | Bassin | Reseau uniquement |

**Recommandation** : Utiliser une approche **hybride** combinant la theorie des graphes (pour les clusters du reseau) et le DEM modifie (pour les bassins versants).

---

## 4. Methodologie recommandee

### 4.1 Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────┐
│                    DONNEES D'ENTREE                         │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ GeoPackage   │  │ MNT (DEM)    │  │ Courbes de niveau│  │
│  │ - Canalisat. │  │              │  │ (optionnel)      │  │
│  │ - Regards    │  │              │  │                  │  │
│  │ - Rejets     │  │              │  │                  │  │
│  │ - Ouvrages   │  │              │  │                  │  │
│  │ - Stations   │  │              │  │                  │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │            │
└─────────┼─────────────────┼────────────────────┼────────────┘
          │                 │                    │
          ▼                 ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                PRETRAITEMENTS                               │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 1. Nettoyage des donnees (geometries, doublons)     │    │
│  │ 2. Reprojection commune (ex: EPSG:32631)            │    │
│  │ 3. Alignement spatial (snap des noeuds)             │    │
│  │ 4. Remplissage des depressions du MNT               │    │
│  │ 5. Conversion courbes de niveau → MNT (si besoin)   │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────┬───────────────────────────────────┬───────────────┘
          │                                   │
          ▼                                   ▼
┌──────────────────────┐         ┌───────────────────────────┐
│ BRANCHE RESEAU       │         │ BRANCHE BASSIN VERSANT    │
│                      │         │                           │
│ 6. Construction du   │         │ 8. Calcul flow direction  │
│    graphe topologique│         │    (D8 / D-inf)           │
│                      │         │                           │
│ 7. Identification    │         │ 9. Calcul flow            │
│    des exutoires     │         │    accumulation           │
│    (rejets, STEP)    │         │                           │
│                      │         │ 10. Modification du MNT   │
│ 8. Propagation       │         │     (depression digging   │
│    amont depuis      │         │      ou stream burning)   │
│    chaque exutoire   │         │                           │
│                      │         │ 11. Recalcul flow dir/acc │
│ 9. Attribution       │         │     sur MNT modifie       │
│    cluster_id a      │         │                           │
│    chaque conduit    │         │ 12. Delimitation bassins  │
│                      │         │     (pour points =        │
│ 10. Attribution      │         │      exutoires)           │
│     noms / labels    │         │                           │
│                      │         │ 13. Conversion raster →   │
│                      │         │     polygones             │
└──────────┬───────────┘         └─────────────┬─────────────┘
           │                                   │
           ▼                                   ▼
┌─────────────────────────────────────────────────────────────┐
│                COUPLAGE / VALIDATION                         │
│                                                             │
│ 14. Superposition cluster reseau / bassin versant           │
│                                                             │
│ 15. Calcul des surfaces de bassin par cluster               │
│                                                             │
│ 16. Verification de coherence :                             │
│     - Chaque exutoire a un cluster ET un bassin ?           │
│     - Les limites de bassin respectent-elles le reseau ?    │
│     - Courbes de niveau coherentes avec les bassins ?       │
│                                                             │
│ 17. Corrections manuelles si necessaire                     │
│                                                             │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    SORTIES                                  │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Clusters     │  │ Bassins      │  │ Donnees          │  │
│  │ hydrauliques │  │ versants     │  │ enrichies        │  │
│  │ (GeoJSON)    │  │ (polygones)  │  │ (GeoPackage)     │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Etape 1 : Construction du graphe topologique du reseau

**Objectif** : Transformer le reseau de canalisations en graphe oriente.

**Entrees** : Couche « Canalisations » du GeoPackage (10 295 conduites).

**Methode** :

1. Pour chaque canalisation (MultiLineString), extraire les LineString individuelles.
2. Determiner le noeud amont (premier point de la ligne) et le noeud aval (dernier point).
3. Arrondir les coordonnees a une precision donnee (ex: 6 decimales pour WGS84) pour regrouper les extremites proches.
4. Construire un graphe oriente G = (V, E) ou :
   - V = ensemble des extremites de conduites (coordonnees arrondies)
   - E = ensemble des conduites orientees (amont → aval)
5. Integrer les regards comme attributs des noeuds (geolocalisation par buffer ou plus proche voisin).
6. Marquer les noeuds de rejet (rejets, STEP) comme « puits » du graphe.

**Sortie** : Graphe oriente avec attributs sur les noeuds et les aretes.

### 4.3 Etape 2 : Identification des exutoires et propagation amont

**Objectif** : Propager depuis chaque exutoire pour former les clusters.

**Methode** :

1. Identifier les noeuds « puits » : rejets, STEP, connexions vers un collecteur principal.
2. Pour chaque exutoire e, effectuer un **parcours en largeur inverse (BFS inverse)** ou un **parcours en profondeur inverse (DFS inverse)** depuis e, en remontant le sens de l'ecoulement (direction amont).
3. Chaque conduit atteint est attribue au cluster de l'exutoire e.
4. Si un conduit est atteint depuis plusieurs exutoires (cas rare, indique un reseau maille), attribuer au cluster du chemin le plus court.

**Pseudo-code** :

```
fonction detecter_clusters(reseau, exutoires):
    cluster_map = {}  # conduit_id -> cluster_id

    pour chaque (cluster_id, exutoire) dans enumerate(exutoires):
        file = [exutoire]
        visités = set()

        tant que file n'est pas vide:
            noeud_courant = file.defiler()

            pour chaque conduit entrant dans noeud_courant:
                si conduit.id non visité:
                    cluster_map[conduit.id] = cluster_id
                    visités.add(conduit.id)
                    file.enfiler(conduit.noeud_amont)

    retourner cluster_map
```

**Implementation** : NetworkX (`nx.bfs_tree` ou `nx.dfs_tree` avec graphe inverse).

### 4.4 Etape 3 : Enrichissement des clusters

**Objectif** : Integrer les regards et ouvrages dans les clusters.

**Methode** :

1. Pour chaque regard, trouver le conduit le plus proche (dans un buffer de 5 m).
2. Attribuer le cluster du conduit au regard.
3. Pour les ouvrages speciaux et stations, meme traitement.
4. Generer des statistiques par cluster :
   - Nombre de conduites
   - Nombre de regards
   - Longueur totale du reseau
   - Diametre moyen / min / max
   - Pente moyenne (si disponible)

### 4.5 Etape 4 : Delimitation des bassins versants a partir du MNT

**Objectif** : Delimiter la surface de drainage contribuant a chaque exutoire.

**Pretraitements du MNT** :

1. Remplissage des depressions (`fill depressions`)
2. Si courbes de niveau disponibles : interpolation en MNT (ex: via `gdal_contour` inverse ou `scipy.interpolate`)

**Calcul du reseau hydrographique** :

1. Flow direction (D8 ou D-infinity)
2. Flow accumulation
3. Seuillage pour extraire le reseau (ex: accumulation > 1000 pixels)

**Modification du MNT pour integrer le reseau souterrain** :

Option A — **Depression digging** (recommandee pour les regards) :
```
pour chaque regard r:
    MNT[r.x, r.y] = MNT[r.x, r.y] - delta   # delta = 3-5 m
```

Option B — **Stream burning** (recommandee pour les canalisations) :
```
pour chaque canalisation c:
    pour chaque pixel p intersectant c:
        MNT[p] = MNT[p] - delta   # delta = 2-5 m
```

Option C — **Hybride** (recommandee) :
- Depression digging sur les regards
- Stream burning leger le long des canalisations principales

**Delimitation** :

1. Recalculer flow direction et flow accumulation sur le MNT modifie.
2. Utiliser chaque exutoire comme pour point.
3. Delimiter le bassin amont (`watershed` / `basin`).
4. Convertir le raster en polygone.

**Outils recommandes** : PySheds (Python pur) ou TauDEM via QGIS.

### 4.6 Etape 5 : Couplage cluster / bassin

**Objectif** : Verifier la coherence et enrichir les donnees.

1. Superposer les polygones de bassin avec les clusters hydrauliques.
2. Calculer la surface de bassin par cluster.
3. Verifier que chaque exutoire a bien un cluster ET un bassin associe.
4. Identifier les incoherences :
   - Bassin sans cluster (reseau non connecte)
   - Cluster sans bassin (canalisation en tunnel / pas de surface contributrice)
5. Produire un tableau de synthese : cluster_id | exutoire | nb_conduites | nb_regards | surface_bassin_ha

---

## 5. Architecture du pipeline de traitement

### 5.1 Modules logiciels

```
project/
├── server.py              # Serveur Flask existant (a etendre)
├── index.html             # Interface web existante (a etendre)
├── config.py              # Configuration existante
├── data_processor.py      # Traitement donnees existant
├── swmm_generator.py      # Generation SWMM existant
│
├── graph_analysis.py      # NOUVEAU : Analyse topologique du reseau
│   ├── build_graph()      # Construction du graphe NetworkX
│   ├── find_outfalls()    # Identification des exutoires
│   ├── detect_clusters()  # BFS/DFS inverse depuis exutoires
│   ├── enrich_clusters()  # Attribution regards/ouvrages
│   └── cluster_stats()    # Statistiques par cluster
│
├── dem_analysis.py        # NOUVEAU : Analyse du MNT
│   ├── preprocess_dem()   # Fill, reprojection
│   ├── flow_direction()   # Calcul direction d'ecoulement
│   ├── flow_accumulation()# Calcul accumulation
│   ├── modify_dem()       # Depression digging / stream burning
│   ├── delineate_watershed() # Delimitation des bassins
│   └── dem_to_contours()  # Generation courbes de niveau
│
├── coupling.py            # NOUVEAU : Couplage reseau / bassin
│   ├── match_clusters_basins() # Association cluster <-> bassin
│   ├── validate_coherence()    # Verification de coherence
│   └── export_results()        # Export GeoPackage enrichi
│
└── tests/
    ├── test_graph_analysis.py
    ├── test_dem_analysis.py
    └── test_coupling.py
```

### 5.2 Pseudo-code principal

```python
# === Pipeline principal ===

# 1. Chargement des donnees
cana = load_geopackage("Canalisations")
regards = load_geopackage("Regards")
rejets = load_geopackage("Rejets")
dem = load_raster("MNT.tif")

# 2. Pretraitements
cana = clean_geometries(cana)
cana = reproject(cana, target_crs="EPSG:32631")
dem_filled = fill_depressions(dem)

# 3. Analyse du reseau (branche graphe)
G = build_graph(cana)          # NetworkX DiGraph
outfalls = find_outfalls(G, rejets, step)
clusters = detect_clusters(G, outfalls)  # BFS inverse
clusters = enrich_clusters(clusters, regards, ouvrages)

# 4. Analyse du MNT (branche bassin)
flow_dir = d8_flow_direction(dem_filled)
flow_acc = flow_accumulation(flow_dir)

# 5. Modification du MNT
dem_mod = depression_digging(dem_filled, regards, delta=3.0)
dem_mod = stream_burning(dem_mod, cana, delta=2.0)
flow_dir_mod = d8_flow_direction(dem_mod)

# 6. Delimitation des bassins
basins = []
for outfall in outfalls:
    basin = delineate_watershed(flow_dir_mod, pour_point=outfall)
    basins.append(basin)

# 7. Couplage et validation
results = match_clusters_basins(clusters, basins)
validate_coherence(results)

# 8. Export
export_geopackage(results, "clusters_bassins.gpkg")
```

---

## 6. Donnees et sources recommandees

### 6.1 Donnees existantes (disponibles)

| Donnees | Format | Source | Couverture |
|---------|--------|--------|------------|
| Canalisations (10 295) | GeoPackage | Projet existant | Zone d'etude |
| Regards (10 538) | GeoPackage | Projet existant | Zone d'etude |
| Rejets (79) | GeoPackage | Projet existant | Zone d'etude |
| Ouvrages speciaux (38) | GeoPackage | Projet existant | Zone d'etude |
| Stations (5) | GeoPackage | Projet existant | Zone d'etude |

### 6.2 Donnees a acquerir

| Donnees | Format recommande | Source possible | Resolution | Priorite |
|---------|-------------------|----------------|------------|----------|
| **MNT/DEM** | GeoTIFF (.tif) | ASTER GDEM (gratuit, 30m), SRTM (30m), LiDAR (1m si disponible), Copernicus DEM (30m/90m) | 5-30m | **Haute** |
| **Courbes de niveau** | Shapefile / GeoJSON | Derivees du MNT ou cartes topographiques IGN/ANCC (Algerie) | 1-5m d'equidistance | Moyenne |
| **Orthophotos** | GeoTIFF | Google Earth, Bing Maps, donnees nationales | 0.5-1m | Basse |
| **Occupation du sol** | Raster / vecteur | Corine Land Cover, OpenStreetMap, classification d'image | 10-100m | Moyenne |

### 6.3 Sources de MNT recommandees

1. **Copernicus DEM** (https://copernicus.eu) — 30m ou 90m, couverture mondiale, gratuit.
2. **SRTM** (https://earthdata.nasa.gov) — 30m, couverture latitudes 60°N-56°S.
3. **ASTER GDEM** (https://earthdata.nasa.gov) — 30m, couverture 83°N-83°S.
4. **NASADEM** (https://earthdata.nasa.gov) — 30m, version amelioree du SRTM.
5. **Donnees LiDAR** (si disponibles) — 0.5-2m, haute precision.

Pour l'Algerie : Le **Copernicus DEM 30m** ou le **SRTM 30m** sont les plus accessibles. Si des donnees LiDAR ou des levés topographiques sont disponibles localement, ils donneront des resultats nettement superieurs.

---

## 7. Outils et bibliotheques

### 7.1 Python (recommande pour l'integration)

| Bibliotheque | Usage | Lien |
|-------------|-------|------|
| **GeoPandas** | Manipulation de donnees geospatiales vecteur | https://geopandas.org |
| **NetworkX** | Analyse de graphes (BFS, DFS, composantes connexes) | https://networkx.org |
| **PySheds** | Delimitation de bassins versants a partir de MNT | https://github.com/pysheds/pysheds |
| **Rasterio** | Lecture/ecriture de rasters (MNT) | https://rasterio.readthedocs.io |
| **Shapely** | Operations geometriques | https://shapely.readthedocs.io |
| **NumPy** | Calculs sur grilles raster | https://numpy.org |
| **SciPy** | Interpolation (courbes de niveau → MNT), filtrage | https://scipy.org |
| **Flask** | Serveur web (deja utilise) | https://flask.palletsprojects.com |
| **whitebox-python** | Interface Python pour WhiteboxTools | https://github.com/giswqs/whitebox-python |

### 7.2 Outils SIG

| Outil | Usage | Type |
|-------|-------|------|
| **QGIS** | Visualisation, validation, GRASS/TauDEM integres | Desktop |
| **TauDEM** | Analyse hydrologique du MNT (parallelise) | Plugin QGIS / standalone |
| **WhiteboxTools** | Analyse hydrologique (plus de 480 outils) | Plugin QGIS / Python |
| **GRASS GIS** | r.watershed, analyse de terrain | Plugin QGIS / standalone |
| **ArcGIS / HEC-GeoHMS** | Alternative commerciale | Desktop |

### 7.3 Choix recommande pour le pipeline

**Pour les clusters hydrauliques (graphe)** :
- NetworkX + GeoPandas (Python pur, aucune dependance externe)

**Pour les bassins versants (MNT)** :
- **Option 1 (recommandee)** : PySheds — leger, Python pur, adapte aux petits bassins
- **Option 2 (haute precision)** : TauDEM via subprocess Python — parallelise, robuste
- **Option 3 (flexible)** : whitebox-python — acces a 480+ outils hydrologiques

---

## 8. Criteres d'evaluation et plan de validation

### 8.1 Criteres quantitatifs

| Critere | Methode | Seuil acceptable |
|---------|---------|-----------------|
| **Couverture des clusters** | % de conduites assignees a un cluster | > 95% |
| **Coherence topologique** | Chaque cluster a exactement 1 exutoire | 100% |
| **Coherence spatiale** | Superposition cluster / bassin (IoU) | > 0.6 |
| **Temps de calcul** | Pipeline complet | < 60s pour 10k conduites |
| **Robustesse** | Variation du seuil d'arrondi (5-7 decimales) | < 5% de variation |

### 8.2 Scenarios de test

**Scenario 1 : Reseau complet**
- Donnees : GeoPackage complet (10 295 conduites, 79 rejets)
- Verification : chaque conduit attribue a un cluster, pas de cluster orphelin

**Scenario 2 : Reseau partiel (donnees manquantes)**
- Donnees : suppression aleatoire de 10% des conduites
- Verification : les clusters restent coherents, les composantes connexes sont preservées

**Scenario 3 : Bassin versant topographique**
- Donnees : MNT seul, sans integration du reseau
- Verification : coherence avec les courbes de niveau

**Scenario 4 : Bassin versant integre**
- Donnees : MNT modifie (depression digging + stream burning)
- Verification : coherence avec le reseau, comparaison avec scenario 3

**Scenario 5 : Validation terrain (si disponible)**
- Comparaison des bassins delimites avec des observations de terrain
- Coefficient de similarite Dice (DSC > 0.7)

### 8.3 Methodes de verification

1. **Verification topologique** : chaque cluster forme un arbre dirige acyclique.
2. **Verification spatiale** : les limites de bassin respectent les lignes de crête (courbes de niveau).
3. **Verification hydraulique** : la pente est toujours positive de l'amont vers l'aval dans chaque cluster.
4. **Verification visuelle** : superposition sur carte interactive pour controle qualite.

---

## 9. Risques et limites

### 9.1 Risques techniques

| Risque | Impact | Mitigation |
|--------|--------|------------|
| MNT de faible resolution (> 30m) | Bassins imprecis en zone plate | Utiliser LiDAR si disponible, ou courbes de niveau pour interpolation |
| Reseau incomplet / disconnecte | Clusters fragmentes | Reconstruction topologique (Li et al., 2025), tolerance sur le snap |
| Zonnes plates (pente < 0.1%) | Direction d'ecoulement incoherente | Pre-traitement MNT (breach depressions au lieu de fill), verifier les pentes reelles |
| Donnees incoherentes (CRS differentes) | Erreurs de positionnement | Reprojection systematique, verification des emprises |
| Performance (10 000+ conduites) | Temps de calcul eleve | Optimisation avec R-tree spatial index, traitement par tuiles |

### 9.2 Limites fondamentales

1. **Le MNT represente la surface, pas le souterrain** : les bassins delimites sont des bassins de ruissellement de surface. Le reseau souterrain redistribue les eaux differemment. L'integration (depression digging / stream burning) est une approximation.

2. **Les courbes de niveau ne remplacent pas un MNT haute resolution** : l'interpolation a partir de courbes de niveau introduit des artefacts, surtout dans les zones de forte pente.

3. **Les clusters hydrauliques sont statiques** : en realite, les conditions d'ecoulement changent avec le temps (bouchages, surverses, rejets varies). Le cluster est une representation en regime permanent.

4. **Absence de donnees de pente reelle** : si le champ `PENTE` du GeoPackage est vide, la pente est estimee a partir de la geometrie et du MNT, ce qui peut etre imprecis.

### 9.3 Hypotheses de travail

- Le reseau est **principalement gravitaire** (pas de pompes en nombre significatif).
- Le MNT est disponible a une resolution **au minimum de 30m**.
- Les donnees du GeoPackage sont **suffisamment completes** pour construire un graphe topologique coherent (> 90% des connexions identifiables).
- Les coordonnees des extremites de conduites sont **coherentes** entre elles (snap a 1-2m pres).

---

## 10. Plan de mise en oeuvre avec jalons

### Phase 1 : Preparation (2 semaines)

| Tache | Duree | Livrable | Statut |
|-------|-------|----------|--------|
| Acquisition du MNT | 2 jours | GeoTIFF du MNT | A faire |
| Evaluation de la qualite des donnees GeoPackage | 2 jours | Rapport de qualite | **FAIT** (donnees explorees) |
| Mise en place de l'environnement Python | 1 jour | requirements.txt mis a jour | **FAIT** (networkx ajoute) |
| Tests de PySheds / TauDEM sur le MNT | 3 jours | Scripts de test | A faire (Phase 3) |
| Documentation de la structure du graphe | 2 jours | Schema topologique | **FAIT** (dans graph_analysis.py) |

### Phase 2 : Developpement clusters hydrauliques (3 semaines)

| Tache | Duree | Livrable | Statut |
|-------|-------|----------|--------|
| Module `graph_analysis.py` | 5 jours | Construction graphe, BFS, clusters | **FAIT** (01/04/2026) |
| Integration regards / ouvrages | 3 jours | Enrichissement des clusters | **FAIT** (01/04/2026) |
| Statistiques par cluster | 2 jours | Tableau de synthese | **FAIT** (01/04/2026) |
| Tests unitaires | 2 jours | test_graph_analysis.py | A faire |
| Integration dans server.py | 3 jours | API /get-clusters | **FAIT** (01/04/2026) |
| Mise a jour de l'interface | 2 jours | Affichage clusters sur carte | Deja fait (etape precedente) |

### Phase 3 : Developpement bassins versants (3 semaines)

| Tache | Duree | Livrable |
|-------|-------|----------|
| Module `dem_analysis.py` | 4 jours | Pretraitements, flow dir/acc |
| Depression digging / stream burning | 3 jours | MNT modifie |
| Delimitation des bassins | 3 jours | Polygones de bassin |
| Integration courbes de niveau | 2 jours | Verification / interpolation |
| Tests unitaires | 2 jours | test_dem_analysis.py |
| Visualisation des bassins | 3 jours | Affichage sur carte |

### Phase 4 : Couplage et validation (2 semaines)

| Tache | Duree | Livrable |
|-------|-------|----------|
| Module `coupling.py` | 3 jours | Association cluster/bassin |
| Validation topologique et spatiale | 3 jours | Rapport de validation |
| Tests d'integration | 2 jours | test_coupling.py |
| Corrections et ajustements | 3 jours | Code corrige |
| Documentation technique | 2 jours | README mis a jour |

### Phase 5 : Finalisation (1 semaine)

| Tache | Duree | Livrable |
|-------|-------|----------|
| Tests de performance | 2 jours | Benchmarks |
| Nettoyage du code | 1 jour | Code propre |
| Mise a jour de la documentation | 2 jours | Documentation complete |
| Mise a jour du depot Git | 1 jour | Commit final |

**Duree totale estimee : 11 semaines**

---

## 11. References

[1] Reyes-Silva, J.D., Zischg, J., Klinkhamer, C., Rao, P.S.C., Sitzenfrei, R. & Krebs, P. (2020). "Centrality and shortest path length measures for the functional analysis of urban drainage networks." *Applied Network Science*, 5:1. https://doi.org/10.1007/s41109-019-0247-8

[2] Meijer, D., van Bijnen, M., Langeveld, J., Korving, H., Post, J. & Clemens, F. (2018). "Identifying Critical Elements in Sewer Networks Using Graph-Theory." *Water*, 10(2):136. https://doi.org/10.3390/w10020136

[3] Li, R., Liu, J., Sun, T., Shao, J., Tian, F. & Ni, G. (2025). "Enhancing urban pluvial flood modeling through graph reconstruction of incomplete sewer networks." *Hydrology and Earth System Sciences*, 29(20):5677-5694.

[4] Di Nardo, A., Di Natale, M., Giudicianni, C., Greco, R. & Santonastaso, G.F. (2017). "Weighted spectral clustering for water distribution network partitioning." *Applied Network Science*, 2:19. https://doi.org/10.1007/s41109-017-0033-4

[5] Schaeffer, S.E. (2011). "Topological clustering for water distribution systems analysis." *Environmental Modelling & Software*, 26(4):469-474. https://doi.org/10.1016/j.envsoft.2010.10.002

[6] Tarboton, D.G. (1997). "A new method for the determination of flow directions and upslope areas in grid digital elevation models." *Water Resources Research*, 33(2):309-319.

[7] Lindsay, J.B. (2018). "WhiteboxTools User Manual." https://jblindsay.github.io/wbt_book/

[8] GRASS Development Team (2024). "GRASS GIS 8.3 Reference Manual." https://grass.osgeo.org/grass83/manuals/

[9] Bartos, M. (2018). "PySheds: Simple and fast watershed delineation in Python." https://github.com/pysheds/pysheds

[10] Si, Q., Brito, H.C., Alves, P.B.R., Pavao-Zuckerman, M.A., Rufino, I.A.A. & Hendricks, M.D. (2024). "GIS-based spatial approaches to refining urban catchment delineation that integrate stormwater network infrastructure." *Discover Water*, 4:24. https://doi.org/10.1007/s43832-024-00083-z

[11] Jankowfsky, S., Branger, F., Braud, I., Gironás, J. & Rodriguez, F. (2013). "Comparison of catchment and network delineation approaches in complex suburban environments." *Hydrological Processes*, 27(25):3747-3761.

[12] Ji, S. & Qiuwen, Z. (2015). "A GIS-based Subcatchments Division Approach for SWMM." *The Open Civil Engineering Journal*, 9:515-521.

[13] Rossman, L.A. (2015). "Storm Water Management Model User's Manual Version 5.1." EPA/600/R-14/413b. U.S. EPA.

[14] Perelman, L. & Ostfeld, A. (2014). "Simplification of Water Distribution Network Simulation by Topological Clustering." *Procedia Engineering*, 89:493-499.

---

## 12. Journal de suivi de l'implementation

| Date | Phase | Action | Fichiers |
|------|-------|--------|----------|
| 01/04/2026 | Phase 2 | Creation du module `graph_analysis.py` : construction graphe NetworkX, detection exutoires, BFS inverse pour clusters, enrichissement regards/ouvrages, statistiques | `graph_analysis.py` (nouveau) |
| 01/04/2026 | Phase 2 | Refactoring de `server.py` pour utiliser `graph_analysis.py` | `server.py` (modifie) |
| 01/04/2026 | Phase 1 | Ajout de `networkx>=3.0` dans requirements.txt | `requirements.txt` (modifie) |

---

*Fin du rapport*
