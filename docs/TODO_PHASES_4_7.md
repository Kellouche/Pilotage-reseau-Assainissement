# TODO — Finalisation de la Feuille de Route Opérationnelle (Phases 4 à 7)

> ⚠️ **NE PAS DÉMARRER les travaux de la Feuille de Route 2027–2029 avant d'avoir soldé les 4 phases ci-dessous.**
> Référence : [`docs/13_ROADMAP_SAAS.md`](13_ROADMAP_SAAS.md)

---

## 🥇 PRIORITÉ 1 — Phase 6 : Cockpit d'Exploitation & Profils Hydrauliques

> **Impact immédiat pour les ingénieurs bureau.**

- [x] **6.A — Profil en long hydraulique interactif**
  - [x] Sélection d'un tronçon ou d'un parcours amont → aval sur la carte Leaflet
  - [x] Tracé du profil altimétrique : terrain naturel (MNT), cotes radiers amont/aval
  - [x] Affichage de la **ligne de charge piézométrique (HGL)** et de la génératrice supérieure
  - [x] Mise en évidence visuelle des conduites en charge (HGL > génératrice supérieure) et alertes
  - [x] Panneau accordéon rétractable avec Chart.js et export PNG en 1 clic

- [x] **6.B — Animation temporelle de l'onde de crue (Time Slider)**
  - [x] Curseur temporel 0 h → 24 h exploitant le fichier binaire `.out` de SWMM via `timeseries_extractor`
  - [x] Coloration dynamique des conduites selon le taux de charge Q/Qmax à chaque pas de temps
  - [x] Clignotement et marquage visuel radar des regards en débordement
  - [x] Affichage du débit instantané à l'exutoire (mini-hydrogramme Chart.js mis à jour en temps réel et navigation au clic)

- [ ] **6.C — Générateur de Rapport de Diagnostic en 1 clic (PDF)**
  - Synthèse complète : cartographie du réseau, liste des contre-pentes, anomalies critiques
  - Bilan de continuité massique SWMM (%), volume inondé total (m³), durées de submersion
  - Estimation financière des travaux prioritaires (reprises de canalisations, rehaussement de regards)
  - Export au format PDF réglementaire, prêt pour transmission à la direction technique

---

## 🥈 PRIORITÉ 2 — Phase 5 : API Publique & Interopérabilité SIG

> **Connexion avec les outils SIG existants des collectivités (QGIS, ArcGIS).**

- [ ] **5.1** — Clés d'API persistantes (`sp_live_...`) pour authentification QGIS sans session web
- [ ] **5.2** — Export à la volée du réseau en **GeoPackage (`.gpkg`)** et **GeoJSON** (filtrable par commune / bassin)
- [ ] **5.3** — Diffusion de tuiles vectorielles **WFS / MVT** pour réseaux volumineux (> 50 000 regards)
- [ ] **5.4** — Documentation Swagger / OpenAPI 3.0 complète et exemples d'intégration

---

## 🥉 PRIORITÉ 3 — Phase 7 : Industrialisation & Déploiement Production

> **Mise en production officielle et déploiement Docker clé en main.**

- [ ] **7.1** — Fichier `docker-compose.yml` multi-services complet (FastAPI + Celery + PostgreSQL 16 PostGIS + Redis 7 + MinIO + Caddy SSL)
- [ ] **7.2** — Dockerfile multi-étapes optimisé (compilation GDAL, GEOS, PROJ, SWMM Toolkit)
- [ ] **7.3** — Pipeline CI/CD GitHub Actions (pytest, Golden Master, contrôle syntaxique JS)
- [ ] **7.4** — Endpoint `/api/v1/health`, logs JSON structurés et métriques de performance
- [ ] **7.5** — Script de sauvegarde automatique PostgreSQL (`pg_dump` quotidien) et Checklist Go-Live OWASP

---

## 🏅 PRIORITÉ 4 — Phase 4 : Mobilité Terrain & Synchronisation Offline-First

> **Application Flutter terrain robuste sans connexion réseau.**

- [ ] **4.1** — Protocole Delta Sync complet : gestion des suppressions (`deleted_ids`) et curseur d'horodatage (`since_timestamp`)
- [ ] **4.2** — Cache local SQLite mobile et file d'attente des interventions sans réseau
- [ ] **4.3** — Téléversement des photos d'anomalies terrain vers S3/MinIO avec miniatures et liaison regard
- [ ] **4.4** — Journal d'audit immuable (`field_audit_logs`) : relevés certifiés horodatés par agent
- [ ] **4.5** — Algorithme de réconciliation des conflits (priorité aux relevés in situ certifiés)

---

## Suivi d'avancement

| Phase | Titre | Statut |
|---|---|---|
| Phase 6 | Cockpit & Profils Hydrauliques | 🔵 En cours |
| Phase 5 | API Publique & SIG | ⬜ À faire |
| Phase 7 | Docker & Production | ⬜ À faire |
| Phase 4 | Mobilité Terrain | ⬜ À faire |

