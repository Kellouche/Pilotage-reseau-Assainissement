# Documentation Complète des Endpoints API — SWMM Platform SaaS

> **Plateforme SaaS Multi-Tenant de Diagnostic, Qualité et Modélisation Hydraulique des Réseaux d'Assainissement (EPA SWMM 5.2)**  
> **Dernière mise à jour :** 28 Octobre 2026  
> **Architecture :** API unifiée FastAPI (`api.main:app`), Multi-Tenant PostgreSQL/PostGIS, Stockage S3/MinIO, Worker Asynchrone Celery/Redis, RBAC et Passerelle Mobile Offline-First.  
> **Format d'échange :** JSON (UTF-8), GeoJSON pour les couches spatiales, binaire pour les rasters et exports `.inp`/PDF.

---

## 1. Vue d'Ensemble de l'Architecture API

L'API de SWMM Platform SaaS expose une architecture RESTful moderne sous le préfixe universel `/api/v1` et des canaux WebSocket pour les événements temps réel sous `/ws`.

### Rôles et Niveaux d'Accès RBAC :
- **`superadmin`** : Opérateur général de la plateforme SaaS. Accès exclusif à la console `/api/v1/admin/*` avec règle d'invisibilité stricte (renvoie `404 Not Found` pour tout autre utilisateur).
- **`admin` (Owner Org)** : Administrateur de l'organisation locataire (`org_id`). Gestion de l'équipe, devis proforma, bons de commande et licences.
- **`engineer`** : Ingénieur d'études et hydraulicien. Droit d'importation des réseaux, correction des anomalies, lancement de simulations SWMM 5.2 et génération de rapports.
- **`field_operator`** : Technicien et agent d'exploitation de terrain. Accès à la synchronisation mobile offline, signalement et mise à jour des anomalies in situ.
- **`viewer`** : Observateur institutionnel en lecture seule.

---

## 2. Administration SaaS & Opérateur Plateforme

*Préfixe : `/api/v1/admin`*  
*Protection : Dépendance `Depends(require_superadmin)` — Règle d'invisibilité HTTP 404.*

| Méthode | Endpoint | Description | Paramètres / Corps | Statut Succès |
|---|---|---|---|---|
| `GET` | `/api/v1/admin/subscribers` | Liste consolidée de tous les locataires abonnés (organisations, plans, compteurs). | `status`, `plan`, `page`, `limit` | `200 OK` |
| `POST` | `/api/v1/admin/subscribers/{org_id}/extend-trial` | Prolongation manuelle d'une période d'évaluation (+14 jours par défaut). | `days: int` | `200 OK` |
| `POST` | `/api/v1/admin/subscribers/{org_id}/change-plan` | Mutation de plan forcée (`demo`, `education`, `bet`, `exploitation`). | `new_plan: str`, `reason: str` | `200 OK` |
| `POST` | `/api/v1/admin/subscribers/{org_id}/toggle-status` | Suspension conservatoire ou réactivation immédiate d'une organisation. | `active: bool` | `200 OK` |
| `GET` | `/api/v1/admin/licenses` | Registre des bons de commande administratifs en attente de validation. | `filter_status: str` | `200 OK` |
| `POST` | `/api/v1/admin/licenses/{order_id}/approve` | Approbation officielle d'un bon de commande et émission du jeton de licence. | `order_id: UUID` | `200 OK` |
| `POST` | `/api/v1/admin/licenses/{order_id}/reject` | Rejet d'un bon de commande avec motif officiel notifié à l'organisation. | `reason: str` | `200 OK` |
| `POST` | `/api/v1/admin/licenses/create-token` | Génération directe d'un jeton de licence cryptographique autonome. | `org_id`, `plan`, `expires_at`, `max_nodes` | `201 Created` |

---

## 3. Organisation, Collaborateurs & Facturation B2B

*Préfixe : `/api/v1/organization`*  
*Protection : `Depends(get_current_tenant_org)` et rôle `admin`.*

| Méthode | Endpoint | Description | Paramètres / Corps | Statut Succès |
|---|---|---|---|---|
| `GET` | `/api/v1/organization/profile` | Informations légales et quotas d'utilisation de l'organisation courante. | — | `200 OK` |
| `GET` | `/api/v1/organization/collaborators` | Annuaire des collaborateurs de l'organisation et rôles associés. | — | `200 OK` |
| `POST` | `/api/v1/organization/collaborators/invite` | Invitation d'un nouveau collaborateur (Ingénieur, Opérateur terrain, etc.). | `email`, `role`, `full_name` | `201 Created` |
| `PUT` | `/api/v1/organization/collaborators/{user_id}/role` | Modification du rôle d'un membre de l'équipe sous contrôle de quota. | `role: str` | `200 OK` |
| `DELETE` | `/api/v1/organization/collaborators/{user_id}` | Révocation d'un membre de l'organisation (préservation des données créées). | — | `204 No Content` |
| `GET` | `/api/v1/organization/license` | État de la licence active, jours restants et historique des commandes. | — | `200 OK` |
| `GET` | `/api/v1/organization/license/proforma` | Génération et téléchargement instantané du devis proforma officiel (PDF). | `plan`, `duration_months`, `currency` | `200 OK (PDF)` |
| `POST` | `/api/v1/organization/license/purchase-order` | Soumission du bon de commande administratif avec fichier justificatif scanné. | `multipart/form-data` (file, reference) | `202 Accepted` |
| `POST` | `/api/v1/organization/license/activate-token` | Activation d'une licence par saisie du jeton cryptographique officiel. | `token: str` | `200 OK` |

---

## 4. Authentification, Sessions & Profils

*Préfixe : `/api/v1/auth`*  
*Protection : Publique pour login/register ; session active pour `me` et `logout`.*

| Méthode | Endpoint | Description | Paramètres / Corps | Statut Succès |
|---|---|---|---|---|
| `POST` | `/api/v1/auth/register` | Création d'une nouvelle organisation et du compte administrateur associé. | `org_name`, `email`, `password`, `full_name` | `201 Created` |
| `POST` | `/api/v1/auth/login` | Connexion par identifiants (renvoie cookie de session web et JWT Bearer mobile). | `username` (email), `password` | `200 OK` |
| `POST` | `/api/v1/auth/refresh` | Renouvellement du token JWT d'accès court via le refresh token mobile. | `refresh_token: str` | `200 OK` |
| `POST` | `/api/v1/auth/logout` | Déconnexion, révocation du jeton en base et suppression des cookies. | — | `200 OK` |
| `GET` | `/api/v1/auth/me` | Profil de l'utilisateur connecté, permissions et informations de son organisation. | — | `200 OK` |
| `PUT` | `/api/v1/auth/me/password` | Modification du mot de passe avec re-hachage immédiat en Argon2id. | `old_password`, `new_password` | `200 OK` |

---

## 5. Gestion des Projets et Réseaux d'Assainissement

*Préfixe : `/api/v1/networks`*  
*Protection : `Depends(get_current_tenant_org)` et rôle `engineer` ou supérieur.*

| Méthode | Endpoint | Description | Paramètres / Corps | Statut Succès |
|---|---|---|---|---|
| `GET` | `/api/v1/networks` | Liste des réseaux et projets d'assainissement de l'organisation. | `page`, `limit` | `200 OK` |
| `POST` | `/api/v1/networks/upload` | Téléversement d'un nouveau réseau (GeoPackage, Shapefile zippé ou `.inp`). | `file: UploadFile`, `name: str` | `202 Accepted` |
| `GET` | `/api/v1/networks/{network_id}` | Détail d'un réseau (statistiques : nombre de regards, collecteurs, STEP, statut). | `network_id: UUID` | `200 OK` |
| `DELETE` | `/api/v1/networks/{network_id}` | Suppression sécurisée d'un réseau et de ses artefacts associés sur S3. | `network_id: UUID` | `204 No Content` |
| `GET` | `/api/v1/networks/{network_id}/nodes` | Récupération des regards/nœuds au format GeoJSON optimisé avec pagination. | `bbox`, `type`, `limit`, `offset` | `200 OK (GeoJSON)` |
| `GET` | `/api/v1/networks/{network_id}/conduits` | Récupération des conduites/collecteurs au format GeoJSON avec attributs hydrauliques. | `bbox`, `diametre_min`, `limit` | `200 OK (GeoJSON)` |
| `GET` | `/api/v1/networks/{network_id}/stats` | Statistiques globales : linéaire total (km), répartition par diamètre et matériau. | — | `200 OK` |

---

## 6. Audit Qualité & Détection d'Anomalies Topologiques

*Préfixe : `/api/v1/qualite`*  
*Protection : `Depends(get_current_tenant_org)`.*

| Méthode | Endpoint | Description | Paramètres / Corps | Statut Succès |
|---|---|---|---|---|
| `GET` | `/api/v1/qualite/{network_id}/analyse` | Rapport complet d'audit de santé du réseau avec score global (0 à 100). | `network_id: UUID` | `200 OK` |
| `GET` | `/api/v1/qualite/{network_id}/anomalies` | Liste filtrable de toutes les anomalies détectées (contre-pentes, sauts, doublons). | `type`, `severite`, `statut` | `200 OK` |
| `GET` | `/api/v1/qualite/{network_id}/anomalies/{type}` | Détail et localisation des anomalies pour un type précis (ex: `contre_pente`). | `type: str` | `200 OK` |
| `POST` | `/api/v1/qualite/{network_id}/anomalies/{anomaly_id}/corriger` | Application d'un correctif topologique (inversion de sens, ajustement de cote). | `nouveau_radier`, `motif` | `200 OK` |
| `GET` | `/api/v1/qualite/{network_id}/scores` | Décomposition détaillée des sous-scores de qualité (géométrie, connectivité, pente). | — | `200 OK` |
| `POST` | `/api/v1/qualite/{network_id}/export-csv` | Export tabulaire complet des anomalies pour traitement bureautique externe. | `filtres` | `200 OK (CSV)` |

---

## 7. Graphe Hydraulique & Clusters de Bassins

*Préfixe : `/api/v1/clusters`*  
*Protection : `Depends(get_current_tenant_org)`.*

| Méthode | Endpoint | Description | Paramètres / Corps | Statut Succès |
|---|---|---|---|---|
| `GET` | `/api/v1/clusters/{network_id}` | Liste des clusters hydrauliques identifiés (sous-réseaux connexes gravitaires). | — | `200 OK` |
| `GET` | `/api/v1/clusters/{network_id}/{cluster_id}/graphe` | Graphe orienté amont-aval du cluster avec sens d'écoulement et débits cumulés. | `cluster_id: str` | `200 OK (JSON)` |
| `GET` | `/api/v1/clusters/{network_id}/exutoires` | Identification de tous les points bas, déversoirs d'orage et rejets exutoires. | — | `200 OK` |
| `POST` | `/api/v1/clusters/{network_id}/recalculer` | Lancement asynchrone du partitionnement de graphe suite à des corrections topologiques. | — | `202 Accepted` |

---

## 8. Analyse Morphologique MNT & Bassins Versants

*Préfixe : `/api/v1/mnt`*  
*Protection : `Depends(get_current_tenant_org)` et vérification du Feature Gating.*

| Méthode | Endpoint | Description | Paramètres / Corps | Statut Succès |
|---|---|---|---|---|
| `POST` | `/api/v1/mnt/{network_id}/upload` | Téléversement d'un raster Modèle Numérique de Terrain (`.tif`) vers le stockage S3. | `file: UploadFile` | `202 Accepted` |
| `POST` | `/api/v1/mnt/{network_id}/extraire-bassins` | Lancement de la tâche asynchrone de délimitation des sous-bassins par analyse de crêtes. | `resolution: float`, `seuil_accumulation: int` | `202 Accepted` |
| `GET` | `/api/v1/mnt/{network_id}/bassins` | Récupération des polygones de sous-bassins versants générés au format GeoJSON. | — | `200 OK (GeoJSON)` |
| `GET` | `/api/v1/mnt/{network_id}/profil-long` | Extraction du profil en long (terrain naturel vs radier) sur un parcours de collecteur. | `start_node`, `end_node` | `200 OK` |

---

## 9. Simulations Hydrauliques EPA SWMM 5.2 & Jobs Asynchrones

*Préfixes : `/api/v1/simulations` et `/api/v1/jobs`*  
*Protection : `Depends(get_current_tenant_org)`.*

| Méthode | Endpoint | Description | Paramètres / Corps | Statut Succès |
|---|---|---|---|---|
| `POST` | `/api/v1/simulations/{network_id}/generer-inp` | Compilation et génération du modèle officiel SWMM 5.2 (`.inp`) depuis le réseau assaini. | `options_calcul: dict` | `201 Created` |
| `POST` | `/api/v1/simulations/{network_id}/lancer` | Lancement d'une simulation dynamique SWMM en tâche de fond sur le worker Celery. | `scenario_pluie`, `duree_heures` | `202 Accepted (job_id)`|
| `GET` | `/api/v1/jobs/{job_id}` | Consultation du statut d'avancement d'un job asynchrone (pourcentage, étape, erreurs). | `job_id: UUID` | `200 OK` |
| `DELETE` | `/api/v1/jobs/{job_id}` | Annulation d'une simulation en cours d'exécution. | `job_id: UUID` | `200 OK` |
| `GET` | `/api/v1/simulations/{sim_id}/resultats` | Synthèse des résultats de calcul : nœuds inondés, collecteurs en charge, hydrogrammes. | `sim_id: UUID` | `200 OK` |
| `GET` | `/api/v1/simulations/{sim_id}/series-temporelles` | Extraction des chroniques de débit ou hauteur sur un nœud ou une conduite précise. | `element_id`, `variable` | `200 OK` |
| `GET` | `/api/v1/simulations/{sim_id}/telecharger-inp` | Téléchargement du fichier d'entrée `.inp` complet pour réouverture sous SWMM Desktop. | — | `200 OK (INP)` |

---

## 10. Passerelle Mobile Terrain & Synchronisation Déconnectée

*Préfixes : `/api/v1/sync` et `/api/v1/terrain`*  
*Protection : JWT valide, organisation active et rôle `field_operator` ou supérieur.*

| Méthode | Endpoint | Description | Paramètres / Corps | Statut Succès |
|---|---|---|---|---|
| `GET` | `/api/v1/sync/pull` | Téléchargement du lot de données pour utilisation mobile déconnectée (depuis timestamp).| `since_timestamp: str`, `network_id` | `200 OK (Delta)` |
| `POST` | `/api/v1/sync/push` | Soumission du lot de mutations enregistrées hors-ligne sur le smartphone. | `mutations: list[dict]` | `200 OK (Rapport)` |
| `POST` | `/api/v1/terrain/photos/upload` | Téléversement d'une photo géolocalisée d'inspection vers le bucket S3 sécurisé. | `file: UploadFile`, `element_id` | `201 Created` |
| `GET` | `/api/v1/terrain/inspections/{network_id}` | Historique complet des contrôles et interventions réalisés par les agents mobiles. | `page`, `limit` | `200 OK` |
| `GET` | `/api/v1/terrain/audit-trail` | Journal d'audit légal et immuable des modifications de cotes et géométries terrain. | `element_id`, `date_debut` | `200 OK` |

---

## 11. Rapports d'Audit & Exports Réglementaires

*Préfixe : `/api/v1/reports`*  
*Protection : `Depends(get_current_tenant_org)`.*

| Méthode | Endpoint | Description | Paramètres / Corps | Statut Succès |
|---|---|---|---|---|
| `POST` | `/api/v1/reports/{network_id}/audit-pdf` | Génération asynchrone du rapport de schéma directeur certifié en PDF haute définition. | `titre`, `inclure_cartes`, `logo` | `202 Accepted` |
| `GET` | `/api/v1/reports/{report_id}/telecharger` | Téléchargement direct du rapport PDF généré (URL signée S3). | — | `200 OK (PDF)` |
| `GET` | `/api/v1/reports/{network_id}/export-geopackage` | Export du réseau nettoyé et validé au format standard OGC GeoPackage (`.gpkg`). | — | `200 OK (GPKG)` |

---

## 12. Endpoints de Santé et Métriques Système

*Préfixe : `/api/v1/health`*  
*Protection : Publique / Monitoring d'infrastructure.*

| Méthode | Endpoint | Description | Paramètres | Statut Succès |
|---|---|---|---|---|
| `GET` | `/api/v1/health` | Vérification de l'état global du service (FastAPI, PostgreSQL, Redis, MinIO). | — | `200 OK` |
| `GET` | `/api/v1/health/ping` | Sonde de vivacité simple (Liveness probe pour conteneurs). | — | `200 OK {"ping": "pong"}` |
