# Données du projet

## Objectif

Ce document décrit les données attendues par la plateforme et les règles de gestion
à respecter pendant la phase d'organisation.

## Source principale

La source métier actuelle est un fichier GeoPackage contenant les couches du réseau
d'assainissement :

- regards ;
- canalisations ;
- rejets ;
- stations de relevage ;
- STEP ;
- ouvrages spéciaux.

Le chemin est configurable avec la variable d'environnement `GPKG_PATH`.

Exemple :

```env
GPKG_PATH=D:\IA Water Data Analysis\Assainissement\Assainissement_Ville.gpkg
```

Si cette variable n'est pas définie, le projet utilise le chemin local historique
présent dans `config/settings.py`.

## Projections

Les données source sont traitées avec deux projections de référence :

- `EPSG:32631` : UTM Zone 31N, projection de travail ;
- `EPSG:4326` : WGS84, projection d'affichage web/mobile.

Les endpoints cartographiques doivent renvoyer les géométries en WGS84 pour rester
compatibles avec Leaflet, React Native Maps et les clients web.

## Données locales à ne pas versionner

Les fichiers suivants ne doivent pas être poussés vers GitHub :

- bases SQLite locales : `*.db`, `*.sqlite`, `*.sqlite3` ;
- GeoPackage volumineux : `*.gpkg` ;
- rasters : `*.tif`, `*.tiff` ;
- shapefiles et fichiers associés : `*.shp`, `*.shx`, `*.dbf`, `*.prj`, `*.cpg` ;
- exports générés : dossier `output/`.

Le dépôt doit contenir le code, la documentation et éventuellement un petit jeu de
données de démonstration anonymisé si nécessaire.

## Base de données applicative

Comportement actuel :

- PostgreSQL/PostGIS est la cible recommandée pour la production ;
- SQLite est utilisé comme fallback local si PostgreSQL n'est pas disponible.

Les paramètres PostgreSQL sont configurables avec :

- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`

## Règles de qualité

Avant d'utiliser une donnée dans une simulation ou une analyse métier, vérifier :

- la présence des identifiants ;
- la validité des géométries ;
- la cohérence amont/aval ;
- les diamètres et longueurs manquants ;
- les tronçons orphelins ;
- les coordonnées hors zone.
