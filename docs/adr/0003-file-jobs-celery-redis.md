# ADR 0003 — File de Traitements Asynchrones Celery et Courtier Redis

- **Statut :** Acceptée
- **Date :** 2026-10-28
- **Portée :** Performance, Scalabilité, Moteur de calcul SWMM 5.2

## Contexte

Dans `swmm-platform-poc`, certains calculs sont extrêmement lourds :
- L'ingestion et la validation topologique de 10 000 regards et 10 000 canalisations.
- Le traitement du Modèle Numérique de Terrain (MNT raster de 50 Mo) pour le découpage des bassins versants.
- L'exécution de simulations dynamiques SWMM 5.2 (résolution des équations de Saint-Venant sur des épisodes pluvieux de 24 heures).

Exécuter ces calculs directement dans le processus du serveur web bloquerait les requêtes HTTP, provoquerait des timeouts chez l'utilisateur et empêcherait toute montée en charge multi-utilisateurs.

## Décision

Nous adoptons le couple standard de l'industrie **Celery (Workers asynchrones) + Redis (Courtier de messages et cache de résultats)** :

1. **Règle absolue du serveur Web FastAPI** :
   Le processus de l'API web ne réalise aucun calcul hydraulique ou géospatial lourd. Lorsqu'un utilisateur demande un calcul, l'API :
   - Vérifie les droits et quotas de l'organisation.
   - Enregistre une tâche en base de données avec le statut `PENDING`.
   - Délègue le job au worker Celery via Redis (`run_swmm_simulation.delay(job_id, network_id)`).
   - Répond immédiatement à l'utilisateur avec un code **HTTP 202 Accepted** et l'identifiant du job (`job_id`).
2. **Suivi d'avancement transparent** :
   Le worker Celery met à jour en continu l'état d'avancement en pourcentage (0 à 100%) et les logs d'étapes dans Redis/PostgreSQL. Le client web ou mobile consulte la progression soit via polling régulier (`GET /api/v1/jobs/{job_id}`), soit en temps réel via WebSocket (`/ws/jobs/{job_id}`).
3. **Isolement des processus de calcul** :
   Le plantage éventuel d'une simulation complexe ou d'une bibliothèque C (EPA SWMM Toolkit) n'affecte jamais la disponibilité de l'application web ni des autres utilisateurs.
4. **Dimensionnement élastique des workers** :
   Le nombre de workers Celery peut être augmenté à la demande (scalabilité horizontale) selon la charge de calcul de la plateforme.

## Alternatives écartées

- **Threads Python en tâche de fond dans FastAPI (`BackgroundTasks`)** : Les `BackgroundTasks` partagent le GIL (Global Interpreter Lock) de Python avec le serveur web, ne persistent pas en cas de redémarrage de l'API et ne permettent pas de répartir la charge sur plusieurs machines physiques.
- **RQ (Redis Queue)** : Plus simple mais moins riche en fonctionnalités avancées (gestion fine des files prioritaires par plan d'abonnement, reprise sur incident, limitation de débit).

## Conséquences

- Redis devient une dépendance obligatoire de l'infrastructure d'exécution.
- La gestion des erreurs de calcul et des annulations de tâches par l'utilisateur doit être explicitement gérée dans le cycle de vie des jobs.
