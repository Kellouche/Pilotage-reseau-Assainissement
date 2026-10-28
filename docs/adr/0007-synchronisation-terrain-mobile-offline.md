# ADR 0007 — Synchronisation Mobile Terrain Hors-Ligne (Offline-First) et Gestion des Conflits

- **Statut :** Acceptée
- **Date :** 2026-10-28
- **Portée :** Application Mobile Flutter, API de Synchronisation, Traçabilité Terrain

## Contexte

Les agents d'exploitation et techniciens d'assainissement effectuent leurs interventions (relevés de cotes, ouverture de tampons, repérage d'anomalies, contrôles de curage) dans des environnements où la couverture réseau 4G/5G est souvent instable ou totalement absente (fossés, tranchées, zones rurales, fonds de vallée).

Si l'application mobile nécessitait une connexion internet permanente, elle deviendrait inutilisable sur le terrain et rejetée par les équipes opérationnelles.

## Décision

Nous adoptons une architecture **Offline-First** pour l'application mobile Flutter couplée à un protocole de synchronisation différentielle sur l'API FastAPI :

1. **Cache local SQLite / Drift sur le smartphone** :
   Avant de partir sur le terrain, l'opérateur synchronise son secteur géographique de travail. La géométrie des regards, canalisations et anomalies est stockée dans une base SQLite locale chiffrée sur l'appareil.
2. **Fonctionnement autonome déconnecté** :
   Toutes les opérations de terrain (consultation de la carte Leaflet mobile, saisie d'un nouveau regard, correction d'une cote de radier, capture d'une photo d'envasement, modification de statut d'anomalie) s'exécutent instantanément en local et sont enregistrées dans un journal d'opérations en attente (`pending_mutations`).
3. **Synchronisation différentielle (Delta Sync) lors du retour de connexion** :
   Dès que le réseau redevient disponible :
   - L'application mobile transmet son lot de mutations horodatées (`POST /api/v1/sync/push`).
   - L'API vérifie les droits de l'opérateur et applique les modifications.
   - En retour, l'API envoie à l'application mobile les éventuelles mises à jour réalisées par les collègues au bureau d'études depuis la dernière synchronisation (`GET /api/v1/sync/pull?since=<timestamp>`).
4. **Stratégie de résolution des conflits** :
   - **Règle générale : "Dernier horodatage terrain valide" (Last-Write-Wins avec horodatage certifié)** pour les cotes physiques observées in situ.
   - **Audit Trail immuable** : Toute modification terrain fait l'objet d'un enregistrement d'historique dans la table `field_audit_logs` (qui a modifié quoi, à quelle heure, avec quelle photo, et quelle était l'ancienne valeur).
   - En cas d'incohérence hydraulique majeure détectée côté serveur (ex: cote de radier saisie créant une contre-pente artificielle de 2 mètres), la modification est marquée comme `A_VALIDER_BUREAU` dans le tableau de bord web sans écraser brutalement la géométrie officielle.

## Alternatives écartées

- **Mode connecté pur avec rechargement HTTP permanent** : Inutilisable dès la moindre perte de signal réseau dans les regards d'eaux usées.
- **Réplication CouchDB / PouchDB** : Complexité d'infrastructure disproportionnée par rapport à une API REST différentielle ciblée.

## Conséquences

- Satisfaction et adoption maximale des équipes mobiles de terrain.
- La base centrale d'assainissement est enrichie continuellement et fiabilisée par les constatations physiques réelles.
