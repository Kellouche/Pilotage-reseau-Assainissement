# SWMM Platform — Plateforme SaaS Collaborative des Réseaux d'Assainissement & Eaux Pluviales

> **Plateforme SaaS Multi-Tenant d'Aide à la Décision, Contrôle Qualité SIG, Analyse Morphologique MNT, Modélisation Dynamique EPA SWMM 5.2 et Synchronisation Mobile Terrain**  
> **Version :** SaaS 2.0 (FastAPI Unifié, Multi-Tenant PostgreSQL/PostGIS, Stockage S3/MinIO, Worker Asynchrone Celery/Redis, Application Mobile Offline)  
> **Date :** Octobre 2026

---

## 🎯 Présentation du Projet

**SWMM Platform SaaS** modernise la gestion patrimoniale et la modélisation hydraulique des réseaux d'assainissement (eaux usées, pluviales et unitaires). Conçue pour combler la rupture historique entre les modélisateurs en bureau d'études et les techniciens d'exploitation sur le terrain, la plateforme permet de :

1. **Auditer automatiquement la qualité géospatiale** de réseaux comptant plus de 10 000 regards et collecteurs (détection des contre-pentes, sauts de radier, doublons et calcul des débits nominaux selon la formule NP 650 et Manning-Strickler).
2. **Analyser le relief par MNT** (Modèle Numérique de Terrain raster) pour délimiter les bassins versants topographiques réels et orienter les écoulements de surface.
3. **Générer et simuler à la demande des modèles EPA SWMM 5.2 officiels** pour anticiper les crues, identifier les tronçons saturés et quantifier les volumes d'inondation en surface.
4. **Synchroniser en temps réel les relevés de terrain** via une application mobile Flutter fonctionnant en mode déconnecté (Offline-First) avec capture photo géolocalisée et traçabilité immuable (Audit Trail).
5. **Générer des rapports d'audit certifiés** et des exports réglementaires complets (OGC GeoPackage, SWMM `.inp`, PDF haute définition).

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

### 1. Via Docker Compose (Recommandé en Production / Staging)

L'environnement complet (PostgreSQL 16 PostGIS, Redis 7, MinIO S3, Serveur Web FastAPI, Worker Asynchrone Celery, Mailpit) démarre en une seule commande :

```bash
docker compose up -d
```

- **Application Web & Cartographie :** `http://localhost:5001/`
- **Documentation API Interactive (Swagger) :** `http://localhost:5001/docs`
- **Console MinIO S3 :** `http://localhost:9001` (`minioadmin` / `minioadmin_secret_2026`)
- **Webmail de Test (Mailpit) :** `http://localhost:8025`

### 2. En Environnement Local (Développement)

```bash
# Activation de l'environnement virtuel Python
.venv\Scripts\activate

# Lancement des tests de non-régression hydraulique (Golden Master)
pytest tests/ -v

# Lancement de l'API unifiée FastAPI
python run_api.py
```

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
