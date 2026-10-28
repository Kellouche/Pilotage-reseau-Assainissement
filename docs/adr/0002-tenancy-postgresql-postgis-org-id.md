# ADR 0002 — Multi-Tenancy Mutualisé dans PostgreSQL + PostGIS via `org_id`

- **Statut :** Acceptée
- **Date :** 2026-10-28
- **Portée :** Données, Cloisonnement, Modèle relationnel & spatial

## Contexte

La plateforme doit héberger simultanément plusieurs collectivités, régies d'eau et bureaux d'études concurrents. Les données géospatiales des réseaux d'assainissement (regards, collecteurs, stations de relèvement, résultats de crues) sont confidentielles et stratégiques. Aucune fuite de données entre locataires ne peut être tolérée.

## Décision

Nous retenons l'approche **Multi-Tenant Mutualisé à isolation logique stricte par colonne `org_id`** dans une base de données PostgreSQL 16 enrichie de l'extension spatiale **PostGIS** :

1. **Clé de cloisonnement universelle** :
   Chaque table métier (`organizations`, `users`, `projects`, `networks`, `nodes`, `conduits`, `subcatchments`, `anomalies`, `simulations`, `field_interventions`) intègre obligatoirement la colonne `org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE`.
2. **Indexation spatiale et multi-tenant systématique** :
   Les index composites commencent par `org_id` (ex: `INDEX idx_conduits_org_network (org_id, network_id)`). Les colonnes géométriques PostGIS disposent d'un index GiST spatial combiné ou partitionné logiquement.
3. **Contrôle automatique d'accès au niveau applicatif** :
   L'injection de dépendance FastAPI `Depends(get_current_tenant_org)` extrait l'identifiant d'organisation depuis la session/JWT vérifiée. Toute requête SQL (SQLAlchemy 2.0 / GeoAlchemy2) inclut impérativement le filtre `.where(Model.org_id == current_org.id)`.
4. **Tentative d'accès inter-organisations** :
   Toute tentative de lecture ou d'écriture sur un identifiant n'appartenant pas à l'organisation connectée renvoie immédiatement une erreur **HTTP 404 Not Found** (règle d'invisibilité totale : un attaquant ne doit même pas savoir si la ressource existe chez un tiers).

## Alternatives écartées

- **Une base de données par organisation (Database-per-tenant)** : Isolement matériel fort, mais coût d'infrastructure prohibitif, complexité ingérable pour les migrations de schémas géospatiaux et latence au démarrage des connexions.
- **Un schéma PostgreSQL par organisation (Schema-per-tenant)** : Complexité élevée de gestion des connexions PostGIS, maintenance fastidieuse des migrations Alembic et risques de dépassement de pool de connexions.

## Conséquences

- Sauvegardes et réplications simplifiées pour l'opérateur (un seul cluster PostgreSQL à administrer).
- L'omission du filtre `org_id` dans une requête constitue un bug bloquant interdit par les tests de sécurité automatisés.
- Possibilité d'activer ultérieurement les politiques de sécurité au niveau des lignes de PostgreSQL (**Row-Level Security / RLS**) comme seconde ligne de défense en profondeur.
