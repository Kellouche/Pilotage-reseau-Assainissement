# Organisation du projet

## Objectif du document

Ce document sert de référence pour comprendre rapidement les composants du projet,
leur rôle, et les prochaines actions d'organisation avant les grands chantiers
fonctionnels.

## Encodage et langue

Tous les documents Markdown, commentaires de code et textes d'interface doivent être
écrits en français lisible, encodés en UTF-8, avec les accents correctement saisis.

À éviter :

- écrire volontairement sans accents ;
- mélanger des textes français lisibles avec des fragments mal encodés ;
- créer des fichiers dans un encodage Windows historique non UTF-8.

## Composants actuels

### Backend FastAPI

Chemin principal : `api/`

Rôle :

- exposer l'API moderne du POC ;
- gérer les objets réseau : regards, conduites, rejets ;
- gérer les clusters hydrauliques ;
- préparer les simulations SWMM ;
- gérer la synchronisation avec le mobile ;
- exposer une page cartographique via `/map`.

Fichiers importants :

- `api/main.py` : point d'entrée API ;
- `api/routes/network.py` : CRUD réseau ;
- `api/routes/sync.py` : synchronisation mobile ;
- `api/routes/clusters.py` : bassins et graphe hydraulique ;
- `api/routes/simulations.py` : jobs de simulation ;
- `api/models.py` : modèles SQLAlchemy ;
- `api/database.py` : connexion base.

### Backend historique Flask

Chemins principaux :

- `server.py`
- `src/controllers/routeur_flask.py`
- `src/views/`

Rôle :

- visualisation cartographique historique ;
- chargement GeoPackage ;
- génération SWMM initiale ;
- logique métier géospatiale existante.

Décision recommandée :

- conserver temporairement comme module historique stable ;
- documenter clairement la différence avec FastAPI ;
- migrer progressivement les fonctions utiles vers l'API moderne.

### Domaine métier

Chemin principal : `src/domain/`

Rôle :

- traitement des nœuds, conduites, pompes ;
- construction du graphe réseau ;
- détection des clusters ;
- extraction de contours et workflows hydrauliques.

Décision recommandée :

- garder ce dossier comme cœur métier partagé ;
- éviter que les routes API contiennent trop de logique hydraulique ;
- ajouter des tests avant toute refonte lourde.

### Infrastructure données

Chemin principal : `src/infrastructure/`

Rôle :

- chargement GeoPackage ;
- reprojection ;
- orientation hydraulique ;
- configuration géospatiale ;
- persistance manuelle.

Décision recommandée :

- documenter les chemins de données requis ;
- remplacer progressivement les chemins absolus par configuration `.env`.

### Application mobile

Chemin principal : `mobile/`

Rôle :

- application React Native/Expo ;
- consultation de carte ;
- synchronisation ;
- saisie terrain de base.

Décision recommandée :

- ignorer `mobile/node_modules/` dans Git ;
- stabiliser les endpoints et ports utilisés ;
- ajouter une documentation mobile dédiée après harmonisation.

### Application Flutter expérimentale

Chemin principal : `swmm_mobile_flutter/`

Rôle probable :

- prototype alternatif mobile.

Décision recommandée :

- clarifier si cette piste est active ou archivée ;
- éviter de maintenir deux applications mobiles en parallèle sans besoin produit.

### Données et sorties locales

Exemples :

- `swmm_platform.db`
- `output/`
- fichiers GeoPackage, raster, shapefile, Excel, CSV.

Décision recommandée :

- ne pas versionner les données lourdes ou générées ;
- fournir plutôt des instructions de placement des données ;
- créer plus tard un petit jeu de démonstration versionnable.

## Conventions recommandées

### Documentation

Tous les documents structurants doivent aller dans `docs/`.

Documents cibles :

- `ROADMAP.md` : vision et phases ;
- `ORGANISATION_PROJET.md` : structure et décisions ;
- `INSTALLATION.md` : installation propre ;
- `LANCEMENT.md` : commandes de lancement ;
- `API.md` : endpoints et exemples ;
- `DONNEES.md` : sources, formats, projections ;
- `MOBILE.md` : usage terrain et synchronisation.

### Nommage

Recommandation :

- garder les noms de modules Python en minuscules ;
- privilégier des noms français cohérents dans `src/` ;
- privilégier des noms anglais courts pour les routes API si elles exposent un contrat public ;
- éviter les doublons de documents au même niveau racine.

### Git

Règles recommandées :

- ne pas commiter `node_modules/`, bases locales, rasters, shapefiles, exports et caches ;
- commiter les documents, scripts utiles, tests et code source ;
- faire des commits petits et explicites ;
- tester impérativement tout ajout ou changement de code avant commit/push ;
- pousser vers GitHub seulement si les tests adaptés au changement aboutissent ;
- indiquer clairement dans le message final quels tests ont été exécutés ;
- pour un changement purement documentaire, vérifier au minimum la cohérence Markdown et le statut Git ;
- vérifier `git status` avant chaque push ;
- pousser sur GitHub après une étape stable.

## Backlog organisationnel

Priorité haute :

- Créer la documentation centrale dans `docs/`.
- Mettre à jour `.gitignore`.
- Ajouter des liens depuis le README principal.
- Harmoniser les ports documentés.
- Identifier les scripts batch utiles et les scripts obsolètes.
- Créer `.env.example`.

Priorité moyenne :

- Créer `docs/LANCEMENT.md`.
- Créer `docs/DONNEES.md`.
- Créer `docs/API.md`.
- Distinguer officiellement FastAPI et Flask historique.
- Clarifier la stratégie mobile : React Native seul ou Flutter aussi.

Priorité basse :

- Archiver les anciens documents expérimentaux.
- Renommer les fichiers de test manuels.
- Ajouter une charte de contribution.
- Ajouter un changelog.
