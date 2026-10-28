# ADR 0005 — Hébergement Portable et Conteneurisation Multi-Services Docker

- **Statut :** Acceptée
- **Date :** 2026-10-28
- **Portée :** Infrastructure, Déploiement, DevOps, Portabilité

## Contexte

Les utilisateurs cibles de SWMM Platform SaaS présentent des exigences d'hébergement variées :
- Les bureaux d'études privés préfèrent un accès direct clé en main sur le Cloud public.
- Certaines régies publiques de l'eau, métropoles ou entités étatiques imposent une stricte **souveraineté des données** et exigent un déploiement sur leurs propres serveurs internes (On-Premise), parfois sans accès internet direct.

La plateforme doit donc être strictement portable et reproductible sans dépendance vis-à-vis d'un fournisseur cloud propriétaire (zéro « vendor lock-in »).

## Décision

Nous adoptons une standardisation intégrale par conteneurs avec **Docker** et **Docker Compose** :

1. **Composition multi-conteneurs standardisée** :
   Le fichier `docker-compose.yml` orchestre l'ensemble des 6 briques logicielles nécessaires :
   - `web` : API FastAPI servie par `uvicorn` / `gunicorn` multi-workers.
   - `worker` : Worker Celery pour les calculs géospatiaux et SWMM 5.2.
   - `db` : Serveur de base de données PostgreSQL 16 avec extension PostGIS 3.4.
   - `redis` : Broker de messages et cache mémoire.
   - `s3` : Serveur MinIO pour le stockage d'artefacts en local / on-premise.
   - `mailpit` (développement / staging) : Serveur SMTP de test pour les notifications d'invitation et réinitialisation de mot de passe.
2. **Configuration universelle par variables d'environnement (`.env`)** :
   Conformément au manifeste 12-Factor, aucune configuration en dur ni mot de passe par défaut n'est toléré dans le code source. Toutes les variables sont déclarées dans `.env.example` et injectées au démarrage.
3. **Images Docker optimisées multi-étapes (Multi-stage build)** :
   Le `Dockerfile` Python compile les dépendances C/C++ géospatiales (GDAL, GEOS, PROJ) et le moteur C EPA SWMM dans une étape de build isolée afin de produire une image finale légère et sécurisée.

## Alternatives écartées

- **Déploiement direct sur VM avec scripts manuels (Bash / PowerShell)** : Faible reproductibilité, dérive d'environnement et maintenance complexe des versions système de GDAL et PostGIS.
- **Orchestration Kubernetes native dès le MVP** : Complexité opérationnelle disproportionnée pour le stade actuel du produit ; Docker Compose suffit amplement pour piloter des charges moyennes et des serveurs dédiés.

## Conséquences

- Démarrage instantané de l'ensemble de la plateforme de développement ou de démonstration en une seule commande : `docker compose up -d`.
- Portabilité totale : le même code fonctionne à l'identique sur un poste de développement Windows/macOS/Linux, sur un serveur Linux d'entreprise et sur un cluster Cloud souverain.
