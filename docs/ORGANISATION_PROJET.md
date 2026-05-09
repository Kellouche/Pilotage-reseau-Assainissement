# Organisation du Projet

## Objectif du Document

Ce document sert de reference pour comprendre rapidement les composants du projet,
leur role, et les prochaines actions d'organisation avant les grands chantiers
fonctionnels.

## Composants Actuels

### Backend FastAPI

Chemin principal : `api/`

Role :

- exposer l'API moderne du POC ;
- gerer les objets reseau : regards, conduites, rejets ;
- gerer les clusters hydrauliques ;
- preparer les simulations SWMM ;
- gerer la synchronisation avec le mobile ;
- exposer une page cartographique via `/map`.

Fichiers importants :

- `api/main.py` : point d'entree API ;
- `api/routes/network.py` : CRUD reseau ;
- `api/routes/sync.py` : synchronisation mobile ;
- `api/routes/clusters.py` : bassins et graphe hydraulique ;
- `api/routes/simulations.py` : jobs de simulation ;
- `api/models.py` : modeles SQLAlchemy ;
- `api/database.py` : connexion base.

### Backend Historique Flask

Chemins principaux :

- `server.py`
- `src/controllers/routeur_flask.py`
- `src/views/`

Role :

- visualisation cartographique historique ;
- chargement GeoPackage ;
- generation SWMM initiale ;
- logique metier geospatiale existante.

Decision recommandee :

- conserver temporairement comme module historique stable ;
- documenter clairement la difference avec FastAPI ;
- migrer progressivement les fonctions utiles vers l'API moderne.

### Domaine Metier

Chemin principal : `src/domain/`

Role :

- traitement des noeuds, conduites, pompes ;
- construction du graphe reseau ;
- detection des clusters ;
- extraction de contours et workflows hydrauliques.

Decision recommandee :

- garder ce dossier comme coeur metier partage ;
- eviter que les routes API contiennent trop de logique hydraulique ;
- ajouter des tests avant toute refonte lourde.

### Infrastructure Donnees

Chemin principal : `src/infrastructure/`

Role :

- chargement GeoPackage ;
- reprojection ;
- orientation hydraulique ;
- configuration geospatiale ;
- persistance manuelle.

Decision recommandee :

- documenter les chemins de donnees requis ;
- remplacer progressivement les chemins absolus par configuration `.env`.

### Application Mobile

Chemin principal : `mobile/`

Role :

- application React Native/Expo ;
- consultation de carte ;
- synchronisation ;
- saisie terrain de base.

Decision recommandee :

- ignorer `mobile/node_modules/` dans Git ;
- stabiliser les endpoints et ports utilises ;
- ajouter une documentation mobile dediee apres harmonisation.

### Application Flutter Experimentale

Chemin principal : `swmm_mobile_flutter/`

Role probable :

- prototype alternatif mobile.

Decision recommandee :

- clarifier si cette piste est active ou archivee ;
- eviter de maintenir deux applications mobiles en parallele sans besoin produit.

### Donnees et Sorties Locales

Exemples :

- `swmm_platform.db`
- `output/`
- fichiers GeoPackage, raster, shapefile, Excel, CSV.

Decision recommandee :

- ne pas versionner les donnees lourdes ou generees ;
- fournir plutot des instructions de placement des donnees ;
- creer plus tard un petit jeu de demonstration versionnable.

## Conventions Recommandees

### Documentation

Tous les documents structurants doivent aller dans `docs/`.

Documents cibles :

- `ROADMAP.md` : vision et phases ;
- `ORGANISATION_PROJET.md` : structure et decisions ;
- `INSTALLATION.md` : installation propre ;
- `LANCEMENT.md` : commandes de lancement ;
- `API.md` : endpoints et exemples ;
- `DONNEES.md` : sources, formats, projections ;
- `MOBILE.md` : usage terrain et synchronisation.

### Nommage

Recommandation :

- garder les noms de modules Python en minuscules ;
- privilegier des noms francais coherents dans `src/` ;
- privilegier des noms anglais courts pour les routes API si elles exposent un contrat public ;
- eviter les doublons de documents au meme niveau racine.

### Git

Regles recommandees :

- ne pas commiter `node_modules/`, bases locales, rasters, shapefiles, exports et caches ;
- commiter les documents, scripts utiles, tests et code source ;
- faire des commits petits et explicites ;
- verifier `git status` avant chaque push ;
- pousser sur GitHub apres une etape stable.

## Backlog Organisationnel

Priorite haute :

- Creer la documentation centrale dans `docs/`.
- Mettre a jour `.gitignore`.
- Ajouter des liens depuis le README principal.
- Harmoniser les ports documentes.
- Identifier les scripts batch utiles et les scripts obsoletes.
- Creer `.env.example`.

Priorite moyenne :

- Creer `docs/LANCEMENT.md`.
- Creer `docs/DONNEES.md`.
- Creer `docs/API.md`.
- Distinguer officiellement FastAPI et Flask historique.
- Clarifier la strategie mobile : React Native seul ou Flutter aussi.

Priorite basse :

- Archiver les anciens documents experimentaux.
- Renommer les fichiers de test manuels.
- Ajouter une charte de contribution.
- Ajouter un changelog.

