# DrainPilot 5.2 — Plateforme SaaS Collaborative des Réseaux d'Assainissement & Eaux Pluviales

> **Plateforme SaaS Multi-Tenant d'Aide à la Décision, Contrôle Qualité SIG, Analyse Morphologique MNT, Modélisation Dynamique EPA SWMM 5.2 (Saint-Venant 1D) et Synchronisation Mobile Terrain**  
> **Version :** DrainPilot 5.2 / SaaS 2.0 (API FastAPI unifiée, isolation multi-tenant Stealth 404, stockage S3/MinIO, workers Celery/Redis, cockpit Leaflet HD)  
> **Dernière mise à jour :** Novembre 2026

---

## 🎯 Présentation du Projet

**DrainPilot 5.2** modernise la gestion patrimoniale et la modélisation hydraulique des réseaux d'assainissement (eaux usées, pluviales et unitaires). Conçue pour combler la rupture historique entre les modélisateurs en bureau d'études et les techniciens d'exploitation sur le terrain, la plateforme permet de :

1. **Auditer automatiquement la qualité géospatiale** de réseaux comptant plus de 10 000 regards et collecteurs (détection des contre-pentes, sauts de radier, doublons et calcul des débits nominaux selon la formule NP 650 et Manning-Strickler).
2. **Analyser le relief par MNT et nuages altimétriques réels** (Modèle Numérique de Terrain raster et 84 302 points IDW de TOPO Chlef) pour caler les cotes de terrain et orienter les écoulements de surface.
3. **Simuler en dynamique sur le moteur officiel EPA SWMM 5.2** (Saint-Venant 1D `DYNWAVE`) pour anticiper les crues, identifier les tronçons saturés et quantifier les volumes d'inondation en surface.
4. **Modéliser les alertes météorologiques réelles (BMS ONM Algérie)** et générer automatiquement des ordres de mission terrain préventifs de curage.
5. **Injecter des apports de temps sec (DWF)** multi-profils (domestique, industriel, continu) avec sélecteur cartographique interactif et légende dynamique en temps réel.
6. **Extraire des sous-réseaux par pochoir spatial (SHP.md)** selon une règle stricte d'intersection produisant une archive zip clé en main.
7. **Mobiliser une chaîne d'expertise multi-agents IA** (7 agents spécialisés : garde-fou, diagnostic, génie civil, GDO, risques, finance BPU, synthèse) consolidée dans un rapport d'audit PDF A4 haute définition.
8. **Synchroniser en temps réel les relevés de terrain** via une passerelle mobile fonctionnant en mode déconnecté (Offline-First) avec traçabilité immuable (Audit Trail).

---

## 🏗️ Architecture Technique SaaS

```
                    ┌──────────────────────────────────────────────┐
                    │     Navigateur Web & Application Mobile      │
                    │  Desktop (Leaflet / JS) + Mobile (Flutter)   │
                    └──────────────────────┬───────────────────────┘
                                           │ HTTPS
                                  ┌────────▼────────┐
                                  │  Reverse Proxy  │  Caddy / Nginx (SSL & Rate Limit)
                                  └────────┬────────┘
                                           │
                    ┌──────────────────────▼──────────────────────┐
                    │      SWMM Platform Web API (FastAPI)        │  Uvicorn / Gunicorn
                    │  - Routeurs modulaires (/api/v1/*)          │
                    │  - Authentification Argon2id & JWT/Cookies  │
                    │  - Isolation stricte multi-tenant (org_id)   │
                    │  - Feature Gating & Quotas Métier           │
                    │  - Console Opérateur SuperAdmin             │
                    │  - Synchronisation Terrain Offline-First    │
                    └───┬──────────────┬──────────────┬───────────┘
                        │              │              │
             ┌──────────▼───┐   ┌──────▼──────┐   ┌───▼──────────┐
             │  PostgreSQL  │   │    Redis    │   │   S3/MinIO   │
             │   + PostGIS  │   │  - Cache    │   │  - Rasters   │
             │  - Tenants   │   │  - Broker   │   │    MNT .tif  │
             │  - Réseaux   │   │  - Statuts  │   │  - Fichiers  │
             │  - Regards   │   └──────┬──────┘   │    .INP      │
             │  - Conduites │          │          │  - Résultats │
             │  - Licences  │   ┌──────▼──────┐   │  - PDF / CSV │
             └──────────────┘   │ Worker Async│   └──────────────┘
                                │   Celery    │  EPA SWMM 5.2 Engine
                                └─────────────┘
```

---

## 🚀 Démarrage Rapide

### 1. Environnement Local (Développement)

```bash
# Activation de l'environnement virtuel Python
.venv\Scripts\activate

# Lancement des tests de non-régression hydraulique (Golden Master)
pytest tests/ -v

# Lancement de l'API unifiée FastAPI (auto-reload)
python run_api.py
```

Le port par défaut est `5002` (configurable par `API_PORT` dans `config/settings.py` ou variable d'environnement) :

- **Application Web & Cartographie Leaflet HD :** `http://localhost:5002/`
- **Documentation API Interactive (Swagger) :** `http://localhost:5002/docs`
- **Santé du service :** `http://localhost:5002/health`

> **Base de données :** PostgreSQL est la cible de production ; en
> développement l'API bascule automatiquement sur SQLite
> (`swmm_platform.db`) si PostgreSQL est indisponible. Les artefacts sont
> stockés localement (`LocalStore`) ou sur S3/MinIO via les variables `S3_*`.

### 2. Conteneurisation (cible d'industrialisation)

L'architecture cible vise PostgreSQL/PostGIS, Redis, MinIO S3, l'API FastAPI,
un worker Celery et un reverse proxy TLS (voir
[13_ROADMAP_SAAS.md](13_ROADMAP_SAAS.md) phase 7 et les ADR 0003–0005).
Le `docker-compose` de production est un livrable de la phase
d'industrialisation — il n'est pas encore livré dans ce dépôt.

---

## 👥 Modèle de Gouvernance & Rôles

1. **Super-Administrateur Plateforme (`is_superadmin = True`)** :
   - Accès exclusif à la console opérateur `/api/v1/admin/*`.
   - Examen et validation des bons de commande administratifs B2B/B2G.
   - Émission des clés de licences officielles (`SP-LIC-YYYY-...`) et suivi consolidé du parc abonnés.
2. **Direction d'Entreprise / Responsable Régie (`owner` / `admin`)** :
   - Gestion des membres de l'organisation (`/organization/collaborators`).
   - Téléchargement des factures proforma réglementaires en Dinars Algériens (DZD) ou Euros (EUR).
   - Soumission des bons de commande et activation des abonnements.
3. **Ingénieur d'Études Hydraulique (`engineer`)** :
   - Importation des réseaux GeoPackage / Shapefiles et MNT rasters.
   - Détection des anomalies de pente, calculs de bassins versants et génération des modèles SWMM 5.2.
   - Lancement des simulations de crues et édition des rapports de schéma directeur.
4. **Opérateur & Technicien Terrain (`field_operator`)** :
   - Synchronisation mobile déconnectée des secteurs d'intervention.
   - Contrôle in situ des cotes de radier, relevé d'anomalies avec photos et guidage cartographique.
5. **Observateur (`viewer`)** :
   - Consultation des cartographies et des rapports exécutifs en lecture seule.

---

## 📚 Référentiel Documentaire du Projet

L'ensemble des documents méthodologiques, architecturaux et stratégiques est consigné dans le dossier `docs/` :

- **Cadrage & Produit :**
  - [Fiche Produit & Cadrage Stratégique](14_FICHE_PRODUIT_CADRAGE.md)
  - [Glossaire et Garanties Métier (Spécial Non-Informaticien)](14_GLOSSAIRE_ET_GARANTIES.md)
  - [Grille Tarifaire & Définition Métier des Plans](15_PLANS_TARIFAIRES.md)
- **Architecture & Décisions :**
  - [Méthodologie & Architecture de Simulation EPA SWMM 5.2](16_METHODOLOGIE_SIMULATION_SWMM.md)
  - [Feuille de Route Complète SaaS (Phases 0 à 7)](13_ROADMAP_SAAS.md)
  - [Documentation Complète des Endpoints API](09_ENDPOINTS_DOCUMENTATION.md)
  - [ADR 0001 — Authentification FastAPI, Argon2id & JWT](adr/0001-authentification-fastapi-argon2-jwt.md)
  - [ADR 0002 — Multi-Tenancy Mutualisé PostgreSQL/PostGIS](adr/0002-tenancy-postgresql-postgis-org-id.md)
  - [ADR 0003 — File de Traitements Asynchrones Celery & Redis](adr/0003-file-jobs-celery-redis.md)
  - [ADR 0004 — Stockage d'Artefacts Volumineux S3 & MinIO](adr/0004-stockage-artefacts-s3-minio.md)
  - [ADR 0005 — Hébergement Portable & Conteneurisation Docker](adr/0005-hebergement-portable-docker.md)
  - [ADR 0006 — Modèle Commercial B2B & Licences](adr/0006-facturation-b2b-licences.md)
  - [ADR 0007 — Synchronisation Mobile Terrain Offline-First](adr/0007-synchronisation-terrain-mobile-offline.md)
  - [ADR 0008 — Périmètre du MVP SaaS Assainissement](adr/0008-perimetre-mvp-saas.md)
