# Feuille de Route - SWMM Platform POC

## Vision

Faire evoluer le POC actuel vers une plateforme web/mobile de pilotage du reseau
d'assainissement, combinant SIG, collecte terrain, synchronisation, controle qualite
des donnees et simulations SWMM pour l'aide a la decision.

L'objectif produit n'est pas seulement de visualiser un reseau, mais de fournir un
outil operationnel pour les equipes bureau et terrain : corriger la donnee,
identifier les bassins, suivre les interventions, simuler les impacts hydrauliques
et anticiper les risques d'inondation.

## Principes Directeurs

- Prioriser la fiabilite avant les nouvelles fonctionnalites.
- Garder une architecture simple, documentee et testable.
- Separer clairement prototype, donnees locales, scripts de lancement et code produit.
- Tracer toutes les modifications terrain.
- Rendre la carte utile aux ingenieurs comme aux agents terrain.
- Preparer la migration progressive vers PostgreSQL/PostGIS sans bloquer le mode SQLite.

## Phase 1 - Stabilisation et Organisation

Objectif : rendre le projet lisible, demarrable et maintenable.

Actions prioritaires :

- Clarifier les modes de lancement : API FastAPI, ancien serveur Flask, web, mobile.
- Harmoniser les ports documentes et utilises par l'application.
- Corriger ou isoler les documents obsoletes ou en double.
- Ajouter une documentation centrale dans `docs/`.
- Proteger le depot Git contre les gros fichiers locaux : bases SQLite, rasters, shapefiles, `node_modules`.
- Creer un inventaire clair des composants : backend, web, mobile, donnees, scripts.
- Ajouter un fichier `.env.example` pour les variables importantes.
- Documenter le mode actuel SQLite et la cible PostgreSQL/PostGIS.

Livrables :

- `docs/ROADMAP.md`
- `docs/ORGANISATION_PROJET.md`
- `.gitignore` renforce
- README enrichi avec les liens utiles

## Phase 2 - Qualite des Donnees Reseau

Objectif : transformer la base geospatiale en donnee exploitable et controlee.

Fonctionnalites :

- Tableau des anomalies reseau.
- Detection des conduites sans regard amont ou aval.
- Detection des troncons orphelins.
- Verification des longueurs, diametres, materiaux et profondeurs manquants.
- Controle des geometries invalides.
- Detection des incoherences amont/aval et pentes suspectes.
- Score qualite par commune, bassin ou type d'objet.
- Export des anomalies en CSV/Excel.

Livrable :

- Module "Qualite reseau" avec priorisation des corrections.

## Phase 3 - Carte Web Operationnelle

Objectif : faire de la carte web l'interface principale de consultation et pilotage.

Fonctionnalites :

- Couches activables : regards, conduites, rejets, stations, STEP, ouvrages, bassins, anomalies.
- Recherche par code, voie, commune, bassin ou identifiant.
- Filtres par type, diametre, materiau, commune, bassin, statut.
- Coloration thematique des conduites.
- Popups enrichis avec fiche objet.
- Export GeoJSON/CSV.
- Mesure de distance.
- Affichage des changements recents en temps reel.

Livrable :

- Interface SIG legere, lisible et orientee exploitation.

## Phase 4 - Mobile Terrain

Objectif : permettre la collecte et la correction de donnees sur site.

Fonctionnalites :

- Mode hors ligne avec file d'attente locale.
- Consultation des objets proches de la position GPS.
- Fiche terrain pour regard, conduite, station et ouvrage.
- Photos, commentaires, etat, niveau d'eau, obstruction, odeur, debordement.
- Creation d'incident geolocalise.
- Statuts : a verifier, corrige terrain, valide bureau.
- Scan code/QR si disponible.
- Synchronisation montante et descendante fiable.

Livrable :

- Application terrain utile meme avec connexion instable.

## Phase 5 - Synchronisation et Tracabilite

Objectif : securiser les echanges entre mobile et serveur.

Fonctionnalites :

- Gestion complete creation, modification, suppression.
- Version globale coherente.
- Enregistrement des appareils mobiles.
- Journal des modifications par utilisateur, appareil et date.
- Detection et affichage des conflits.
- Validation manuelle des changements sensibles.
- WebSocket pour notifier les clients connectes.
- Tableau des modifications recentes.

Livrable :

- Synchronisation auditee et robuste.

## Phase 6 - Simulations SWMM

Objectif : passer de la preparation des simulations a l'execution hydraulique reelle.

Fonctionnalites :

- Generation automatique de fichier `.inp` par bassin.
- Lancement de simulation SWMM.
- File de jobs avec statut : pending, running, completed, failed.
- Lecture des resultats : surcharge, debordement, vitesse, tirant d'eau, conduites critiques.
- Scenarios de pluie : faible, intense, decennale, centennale, personnalisee.
- Comparaison avant/apres modification.
- Cartographie des resultats.
- Rapport PDF par bassin ou scenario.

Livrable :

- Moteur d'aide a la decision hydraulique.

## Phase 7 - Tableau de Bord Decisionnel

Objectif : offrir une synthese aux responsables techniques.

Indicateurs :

- Nombre d'objets par commune et par bassin.
- Lineaire total par diametre et materiau.
- Bassins les plus critiques.
- Anomalies ouvertes, traitees et validees.
- Modifications terrain recentes.
- Simulations recentes et resultats critiques.
- Carte des zones prioritaires.

Livrable :

- Dashboard web de pilotage et reporting.

## Phase 8 - Securite et Utilisateurs

Objectif : preparer un usage institutionnel.

Fonctionnalites :

- Authentification.
- Roles : administrateur, ingenieur, agent terrain, lecteur.
- Permissions par action : voir, modifier, valider, simuler, exporter.
- Journal d'audit complet.
- Sauvegardes automatiques.
- Protection des endpoints sensibles.
- Politique de restauration.

Livrable :

- Plateforme controlee et exploitable en production.

## Phase 9 - Industrialisation

Objectif : rendre la plateforme deployable et maintenable.

Actions :

- Migration PostgreSQL/PostGIS.
- Script d'installation fiable ou Docker Compose.
- Tests automatiques API, synchronisation et generation SWMM.
- Monitoring API/base/jobs.
- Documentation utilisateur.
- Documentation administrateur.
- Jeu de donnees de demonstration.
- Procedure de mise a jour.

Livrable :

- Version candidate pour demonstration officielle ou pilote terrain.

## Ordre de Priorite Recommande

1. Stabilisation et organisation du depot.
2. Qualite des donnees reseau.
3. Carte web operationnelle.
4. Synchronisation mobile robuste.
5. Simulations SWMM reelles.
6. Dashboard decisionnel.
7. Securite, utilisateurs et deploiement.

