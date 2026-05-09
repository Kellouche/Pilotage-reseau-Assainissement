# Feuille de route - SWMM Platform POC

## Vision

Faire évoluer le POC actuel vers une plateforme web/mobile de pilotage du réseau
d'assainissement, combinant SIG, collecte terrain, synchronisation, contrôle qualité
des données et simulations SWMM pour l'aide à la décision.

L'objectif produit n'est pas seulement de visualiser un réseau, mais de fournir un
outil opérationnel pour les équipes bureau et terrain : corriger la donnée,
identifier les bassins, suivre les interventions, simuler les impacts hydrauliques
et anticiper les risques d'inondation.

## Principes directeurs

- Prioriser la fiabilité avant les nouvelles fonctionnalités.
- Garder une architecture simple, documentée et testable.
- Séparer clairement prototype, données locales, scripts de lancement et code produit.
- Tracer toutes les modifications terrain.
- Rendre la carte utile aux ingénieurs comme aux agents terrain.
- Préparer la migration progressive vers PostgreSQL/PostGIS sans bloquer le mode SQLite.

## Phase 1 - Stabilisation et organisation

Objectif : rendre le projet lisible, démarrable et maintenable.

Actions prioritaires :

- Clarifier les modes de lancement : API FastAPI, ancien serveur Flask, web, mobile.
- Harmoniser les ports documentés et utilisés par l'application.
- Corriger ou isoler les documents obsolètes ou en double.
- Ajouter une documentation centrale dans `docs/`.
- Protéger le dépôt Git contre les gros fichiers locaux : bases SQLite, rasters, shapefiles, `node_modules`.
- Créer un inventaire clair des composants : backend, web, mobile, données, scripts.
- Ajouter un fichier `.env.example` pour les variables importantes.
- Documenter le mode actuel SQLite et la cible PostgreSQL/PostGIS.
- Formaliser la règle qualité : tout code ajouté ou modifié doit être testé avant push GitHub.

Livrables :

- `docs/ROADMAP.md`
- `docs/ORGANISATION_PROJET.md`
- `.gitignore` renforcé
- README enrichi avec les liens utiles

## Phase 2 - Qualité des données réseau

Objectif : transformer la base géospatiale en donnée exploitable et contrôlée.

Fonctionnalités :

- Tableau des anomalies réseau.
- Détection des conduites sans regard amont ou aval.
- Détection des tronçons orphelins.
- Vérification des longueurs, diamètres, matériaux et profondeurs manquants.
- Contrôle des géométries invalides.
- Détection des incohérences amont/aval et pentes suspectes.
- Score qualité par commune, bassin ou type d'objet.
- Export des anomalies en CSV/Excel.

Livrable :

- Module "Qualité réseau" avec priorisation des corrections.

## Phase 3 - Carte web opérationnelle

Objectif : faire de la carte web l'interface principale de consultation et pilotage.

Fonctionnalités :

- Couches activables : regards, conduites, rejets, stations, STEP, ouvrages, bassins, anomalies.
- Recherche par code, voie, commune, bassin ou identifiant.
- Filtres par type, diamètre, matériau, commune, bassin, statut.
- Coloration thématique des conduites.
- Popups enrichis avec fiche objet.
- Export GeoJSON/CSV.
- Mesure de distance.
- Affichage des changements récents en temps réel.

Livrable :

- Interface SIG légère, lisible et orientée exploitation.

## Phase 4 - Mobile terrain

Objectif : permettre la collecte et la correction de données sur site.

Fonctionnalités :

- Mode hors ligne avec file d'attente locale.
- Consultation des objets proches de la position GPS.
- Fiche terrain pour regard, conduite, station et ouvrage.
- Photos, commentaires, état, niveau d'eau, obstruction, odeur, débordement.
- Création d'incident géolocalisé.
- Statuts : à vérifier, corrigé terrain, validé bureau.
- Scan code/QR si disponible.
- Synchronisation montante et descendante fiable.

Livrable :

- Application terrain utile même avec connexion instable.

## Phase 5 - Synchronisation et traçabilité

Objectif : sécuriser les échanges entre mobile et serveur.

Fonctionnalités :

- Gestion complète création, modification, suppression.
- Version globale cohérente.
- Enregistrement des appareils mobiles.
- Journal des modifications par utilisateur, appareil et date.
- Détection et affichage des conflits.
- Validation manuelle des changements sensibles.
- WebSocket pour notifier les clients connectés.
- Tableau des modifications récentes.

Livrable :

- Synchronisation auditée et robuste.

## Phase 6 - Simulations SWMM

Objectif : passer de la préparation des simulations à l'exécution hydraulique réelle.

Fonctionnalités :

- Génération automatique de fichier `.inp` par bassin.
- Lancement de simulation SWMM.
- File de jobs avec statut : pending, running, completed, failed.
- Lecture des résultats : surcharge, débordement, vitesse, tirant d'eau, conduites critiques.
- Scénarios de pluie : faible, intense, décennale, centennale, personnalisée.
- Comparaison avant/après modification.
- Cartographie des résultats.
- Rapport PDF par bassin ou scénario.

Livrable :

- Moteur d'aide à la décision hydraulique.

## Phase 7 - Tableau de bord décisionnel

Objectif : offrir une synthèse aux responsables techniques.

Indicateurs :

- Nombre d'objets par commune et par bassin.
- Linéaire total par diamètre et matériau.
- Bassins les plus critiques.
- Anomalies ouvertes, traitées et validées.
- Modifications terrain récentes.
- Simulations récentes et résultats critiques.
- Carte des zones prioritaires.

Livrable :

- Dashboard web de pilotage et reporting.

## Phase 8 - Sécurité et utilisateurs

Objectif : préparer un usage institutionnel.

Fonctionnalités :

- Authentification.
- Rôles : administrateur, ingénieur, agent terrain, lecteur.
- Permissions par action : voir, modifier, valider, simuler, exporter.
- Journal d'audit complet.
- Sauvegardes automatiques.
- Protection des endpoints sensibles.
- Politique de restauration.

Livrable :

- Plateforme contrôlée et exploitable en production.

## Phase 9 - Industrialisation

Objectif : rendre la plateforme déployable et maintenable.

Actions :

- Migration PostgreSQL/PostGIS.
- Script d'installation fiable ou Docker Compose.
- Tests automatiques API, synchronisation et génération SWMM.
- Monitoring API/base/jobs.
- Documentation utilisateur.
- Documentation administrateur.
- Jeu de données de démonstration.
- Procédure de mise à jour.

Livrable :

- Version candidate pour démonstration officielle ou pilote terrain.

## Ordre de priorité recommandé

1. Stabilisation et organisation du dépôt.
2. Qualité des données réseau.
3. Carte web opérationnelle.
4. Synchronisation mobile robuste.
5. Simulations SWMM réelles.
6. Dashboard décisionnel.
7. Sécurité, utilisateurs et déploiement.
