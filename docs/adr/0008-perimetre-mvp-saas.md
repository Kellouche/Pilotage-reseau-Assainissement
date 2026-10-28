# ADR 0008 — Définition et Périmètre du MVP SaaS Assainissement

- **Statut :** Acceptée
- **Date :** 2026-10-28
- **Portée :** Périmètre Produit, Jalons de livraison, MVP

## Contexte

La plateforme d'assainissement possède un potentiel fonctionnel immense : diagnostic SIG, segmentation topologique par MNT, simulation dynamique SWMM 5.2, synchronisation mobile, télémesure temps réel SCADA/IoT sur les déversoirs d'orage, calcul de qualité d'eau physico-chimique (DCO, DBO5, MES) et optimisation automatique des pompes de relevage.

Tenter d'implémenter l'intégralité de ces fonctionnalités dès le premier jalon SaaS risquerait de diluer l'effort, de retarder la mise sur le marché et de compromettre la robustesse du socle industriel.

## Décision

Nous définissons un **Périmètre MVP (Minimum Viable Product) SaaS strict**, concentré sur la chaîne de valeur fondamentale du bureau d'études et de la régie communale :

### Ce qui est INCLUS dans le MVP SaaS :
1. **Socle SaaS Multi-Tenant & Sécurité** :
   - Inscription, authentification Argon2id, gestion d'équipe et rôles RBAC.
   - Cloisonnement étanche des réseaux par `org_id`.
   - Feature gating et gestion des licences (Démo, Recherche, BET, Exploitation).
2. **Ingestion & Diagnostic Qualité de Données** :
   - Ingestion de fichiers GeoPackage, Shapefiles et `.inp`.
   - Moteur de contrôle qualité automatique : détection des contre-pentes, doublons regards, nœuds orphelins, sauts de pente et scoring de santé globale (0 à 100).
   - Visualisation cartographique interactive Leaflet avec filtres d'anomalies.
3. **Segmentation & Morphologie MNT** :
   - Traitement des modèles numériques de terrain (MNT raster `.tif`).
   - Découpage automatique des sous-bassins versants et calcul des pentes d'écoulement de surface.
4. **Moteur Hydraulique SWMM 5.2 Asynchrone** :
   - Génération automatique du fichier `.inp` certifié depuis les couches SIG assainies.
   - Lancement asynchrone des calculs de crue via Celery / Redis.
   - Restitution des débits de pointe, hauteurs d'eau dans les regards et identification des conduites saturées.
5. **Passerelle Mobile & Synchronisation Terrain Essentielle** :
   - Consultation du réseau sur smartphone Flutter.
   - Saisie et correction des anomalies topologiques avec prise de photo.
   - Synchronisation différentielle bidirectionnelle avec la base centrale.
6. **Exports et Rapports d'Audit** :
   - Exportation des fichiers GeoPackage corrigés et modèles `.inp`.
   - Génération de rapports d'audit exécutifs au format PDF haute résolution.

### Ce qui est DIFFÉRÉ (Phases ultérieures post-MVP) :
- Modélisation de la qualité de l'eau physico-chimique (pollution, lessivage des chaussées, concentration en DCO/DBO5).
- Intégration en temps réel de capteurs IoT / SCADA télétransmis sur les déversoirs d'orage.
- Pilotage automatique prédictif en temps réel des vannes régulatrices de débit et pompes de refoulement (Real-Time Control / RTC avancé).

## Alternatives écartées

- **Lancer le SaaS uniquement avec la carte sans simulation hydraulique SWMM** : Valeur ajoutée insuffisante par rapport à un visualiseur SIG classique comme QGIS.
- **Intégrer les capteurs IoT temps réel dès le départ** : Dérive de calendrier majeure et complexité excessive pour le premier socle commercial.

## Conséquences

- Le MVP est réaliste, centré sur la résolution des vrais irritants quotidiens des hydrauliciens d'assainissement.
- Le cycle de développement reste maîtrisé et directement mesurable à travers les jalons de la feuille de route.
