# Feuille de route — SWMM Platform (Historique POC & Transition SaaS)

> ⚠️ **Document de transition** : La feuille de route officielle et complète pour la transformation SaaS industrielle de la plateforme est désormais consignée dans **[13_ROADMAP_SAAS.md](13_ROADMAP_SAAS.md)** (Phases 0 à 7, chiffrage des tâches S/M/L/XL, architecture FastAPI/Celery/PostGIS/S3, quotas et jalons d'acceptation stricts).  
> Ce document conserve l'historique des premières phases de cadrage du POC initial.

---

## Vision Initiale du POC

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

## Phase 6 - Simulations SWMM 5.2 Dynamiques

Objectif : passer du simple squelette d'export à l'exécution hydrodynamique complète (Saint-Venant 1D) alimentée par une hydrologie réelle.

Fonctionnalités :

- **Couplage Hydrologique Pluie-Débit** :
  - Découpage automatique des sous-bassins élémentaires (`[SUBCATCHMENTS]`) par polygones de Voronoï/Thiessen bornés au bassin urbain.
  - Attribution automatique au regard d'injection (`Outlet`), calcul de la surface, de la largeur équivalente $W$ et de la pente MNT.
  - Modélisation de l'infiltration de surface selon la loi de Horton ($f_0, f_c, k$) et coefficients d'imperméabilisation ($\%Imperv$).
- **Sollicitations Météorologiques & Eaux Usées** :
  - Générateur d'hyétogrammes synthétiques (`[RAINGAGES]`, `[TIMESERIES]`) via lois de Montana locales ($T = 2, 10, 50\text{ ans}$) et averses de Chicago.
  - Ingestion de chroniques de pluie réelles au pas de 5 min.
  - Débits de temps sec (`[DWF]`) avec coefficients horaires journaliers de pointe.
- **Ouvrages Spéciaux et Singularités** :
  - Modélisation des déversoirs d'orage (`[WEIRS]`), pompes de relevage (`[PUMPS]`), bâches de stockage (`[STORAGE]`) et conditions d'exutoires noyés ou libres (`[OUTFALLS]`).
- **Moteur d'Exécution Natif** :
  - Intégration de `pyswmm` (solveur C officiel EPA SWMM 5.2 embarqué, sans dépendance à un exécutable externe).
  - Résolution des équations complètes de Saint-Venant en onde dynamique (`DYNWAVE`), gestion des mises en charge sous pression et surcharges en surface (`ALLOW_PONDING YES`).
- **Décodage Temporel & Visualisation Cockpit** :
  - Décodeur binaire du fichier `.out` extrayant les séries temporelles complètes ($Q(t), y(t), V(t)$).
  - Curseur temporel (Time Slider $0\text{ h} \rightarrow 24\text{ h}$) animant l'onde de crue sur la carte Leaflet.
  - Coloration dynamique selon le taux de charge ($y/D$) et clignotement des regards inondés.
  - Hydrogrammes interactifs au clic (Chart.js) et profils en long hydrauliques animés avec ligne de charge piézométrique.
- **Rapports d'Ingénierie** :
  - Calcul automatique des volumes inondés ($V_{\text{flood}}$ en $\text{m}^3$), durées de submersion et bilan de continuité massique ($< 1\,\%$).
  - Export du rapport de simulation certifié en PDF/CSV.

Livrable :

- Moteur d'aide à la décision hydraulique temps réel certifié EPA SWMM 5.2.

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
