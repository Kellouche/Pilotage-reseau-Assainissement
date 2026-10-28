# ADR 0004 — Stockage des Fichiers et Artefacts Volumineux sur S3 / MinIO

- **Statut :** Acceptée
- **Date :** 2026-10-28
- **Portée :** Stockage, Fichiers, Artefacts géospatiaux et hydrauliques

## Contexte

Dans sa conception initiale de POC, l'application stocke les fichiers directement sur le système de fichiers local du serveur :
- Fichiers raster MNT (`AST14DEM_...tif`, 8 Mo à plusieurs centaines de Mo).
- Fichiers Shapefiles et GeoPackage (`.gpkg`).
- Fichiers d'entrée SWMM (`.inp`) et résultats binaires de simulation (`.out`).
- Rapports d'audit et planches de profils en long.

Cette approche du « filesystem comme base de données » viole les principes 12-Factor, empêche le déploiement sur des conteneurs éphémères (Kubernetes, clusters cloud stateless) et pose des risques majeurs de sécurité (vulnérabilités de type path traversal `../../`).

## Décision

Nous adoptons un **stockage d'objets standardisé compatible S3**, matérialisé par :
- **MinIO** en environnement local de développement et sur les déploiements on-premise autonomes.
- **Tout service S3 compatible** (Scaleway Object Storage, OVH Cloud Storage, AWS S3) pour la production cloud souveraine.

### Règles d'organisation des buckets S3 :
1. **Cloisonnement strict par organisation dans l'arborescence des clés d'objets** :  
   `s3://swmm-platform-artefacts/{org_id}/networks/{network_id}/...`
2. **Typologie des objets stockés** :
   - `raw/` : Fichiers originaux téléversés par l'utilisateur (GeoPackage, Shapefile compressé, Raster DEM `.tif`).
   - `swmm/` : Modèles compilés (`model.inp`) et résultats complets bruts (`simulation.out`).
   - `reports/` : Rapports exécutifs certifiés générés au format PDF.
   - `terrain/` : Photos géolocalisées des anomalies téléversées par les agents mobiles.
3. **Téléchargement sécurisé par URLs pré-signées** :
   Les fichiers volumineux ne transitent pas inutilement par la mémoire du serveur FastAPI. L'API délivre des URLs pré-signées temporaires (validité 15 minutes) permettant au navigateur ou à l'application mobile de télécharger ou téléverser directement les données en toute sécurité.

## Alternatives écartées

- **Stockage des fichiers volumineux sous forme de BLOB dans PostgreSQL** : Gonfle inutilement la taille de la base relationnelle, dégrade les performances des sauvegardes et sature la mémoire du serveur de base de données.
- **Partage réseau NFS ou volume monté persistant** : Complexe à sécuriser en multi-tenant, problème de verrouillage de fichiers en écriture concurrente.

## Conséquences

- Le serveur web FastAPI et les workers Celery deviennent entièrement **Stateless** (sans état local persistant), ce qui simplifie radicalement leur maintenance et leur montée en charge.
- Les identifiants et clés d'accès S3 (`S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET_NAME`) sont configurés par variables d'environnement.
