# TODO — Réseau d'Assainissement

**Date :** 02-04-2026 07:12
**Utilisateur :** Hakim

---

## À faire — Priorité hydraulique

### Phase 0 — Diagnostic qualité existant (base)

- [X] Anomalie détection : champs manquants, géométries invalides, pentes
- [X] Intégrer auto-lancement après chargement carte (pas d'attente utilisateur)
- [X] Regrouper les icônes par phase d'analyse (🔧 topologie, ⛰ pente, 📊 débit, 🌊 MNT)
- [X] Adapter boîte correction par type anomaly (pas profil pour coords invalides)

### Phase 1 — Fondations topologiques (immédiat)

- [X] Validation des connexions amont-aval (tolérance 50cm)
- [X] Détection des chevauchements géométriques (conduites se croisant sans nœud)
- [X] Détection des doublons regards à < 2m

### Phase 2 — Analyse de pente et profil

- [ ] Calcul continu des pentes avec vérification de débitilité
- [ ] Détection des sauts de pente > 2m (inversion brutale)
- [ ] Courbes caractéristiques longueur-cumul / profondeur-cumul

### Phase 3 — Capacité débitaire

- [ ] Calcul débit nominal selon NP 650 (Q = 3.1 * D^2.2)
- [ ] Détection conduites sous-dimensionnées (défaut de charge)
- [ ] Vérification vitesse d'écoulement (0.3 - 3 m/s)

### Phase 4 — Limites MNT intégrées

- [ ] Intégrer MNT/DEM pour bassins versants réels
- [ ] Comparaison avec bassins topologiques
- [ ] Détection des hors-bassin (écoulement inversé géographique)

---

## À faire — UI/UX cartographique

### Phase 5 — Visualisation hydraulique

- [ ] Mode "flux continu" animation sens débit
- [ ] Coloration par ordre topologique (débit cumulé)
- [ ] Heatmap débit maximal par bassin

### Phase 6 — Diagnostic spatial

- [ ] Panel scores qualité par bassin (rouge/orange/vert)
- [ ] Timeline modifications avec lien carto
- [ ] Mode "contrôle terrain" validation terrain

### Phase 7 — Mobile terrain

- [ ] Synchronisation offline
- [ ] Capture GPS + photo anomalies
- [ ] Mode orientation flèche débit

### Phase 7bis — Moteur Hydrodynamique EPA SWMM 5.2 Réel

- [ ] Générateur hydrologique de surface Voronoï/Thiessen (`[SUBCATCHMENTS]`, `%Imperv`, Horton)
- [ ] Hyétogrammes de pluie de projet Montana / Chicago (`[RAINGAGES]`, `[TIMESERIES]`)
- [ ] Sollicitations de temps sec (`[DWF]`) avec patterns horaires journaliers
- [ ] Traduction des singularités (`[WEIRS]`, `[PUMPS]`, `[STORAGE]`, `[OUTFALLS]`)
- [ ] Intégration du moteur natif compilé `pyswmm` (Saint-Venant 1D / `DYNWAVE`)
- [ ] Parser binaire `.out` pour extraction des chroniques temporelles ($Q(t), y(t), V(t)$)
- [ ] Time Slider temporel et animation de l'onde de crue sur la carte Leaflet
- [ ] Profil en long hydraulique dynamique animé avec ligne piézométrique

---

## À faire — Architecture

### Phase 8 — Performance

- [ ] Cache calculs topologiques (graphe statique)
- [ ] Validation incrémentale par bassin
- [ ] Batch processing parallèle

### Phase 9 — Traçabilité

- [ ] Versionning géométries (timestamp)
- [ ] Audit trail modifications
- [ ] Impact hydraulique calculé à la volée

---

## Fait

## Fait

- [X] Restructuration MVC du projet (règles 1-5)
- [X] En-têtes de module standardisés (auteur, version, dates, objectif)
- [X] Découpage des fichiers >250 lignes en sous-modules
- [X] Architecture : src/controllers, src/domain, src/infrastructure, src/views, tests
- [X] Sens d'écoulement hydraulique (cotes de radier, inversion des coordonnées)
- [X] Noms de rues comme labels sur la carte (134 rues depuis les regards)
- [X] Flèches de sens d'écoulement visibles à partir du zoom 14
- [X] Labels noms de rues visibles à partir du zoom 13
- [X] Taille des symboles adaptative selon le zoom
- [X] Centre de la carte calculé automatiquement depuis les données
- [X] Filtrage des colonnes GeoPackage → performance (58s → 6s)
- [X] Popups enrichis (rue, commune, diamètre, profondeur, matériau)
- [X] Clustering Leaflet désactivé (points individuels)
- [X] Supprimer Streamlit, garder Flask uniquement
- [X] Supprimer graph_analysis.py et toute logique de clustering
- [X] Simplifier server.py (chargement GeoPackage → API JSON)
- [X] Simplifier index.html (6 couches, pas de clusters)
- [X] Corriger les accents UTF-8 (console Windows + interface web)
- [X] Ajouter en-têtes anti-cache dans Flask (Cache-Control)
- [X] Corriger le zoom (fitBounds uniquement au chargement initial)

---

## Arborescence du projet

```
server.py                          Point d'entrée Flask
requirements.txt                   Dépendances Python
launch_server.bat                  Lanceur Windows
Regles.txt                         Règles du projet
TODO.md                            Suivi des tâches
README.md                          Documentation

src/
  controllers/
    routeur_flask.py               Routes Flask (/ et /get-data)
    generateur_swmm.py             Orchestration génération .inp
    generateur_noeuds.py           Sections TITLE, OPTIONS, JUNCTIONS, OUTFALLS, STORAGE, COORDINATES, MAP
    generateur_liens.py            Sections CONDUITS, PUMPS, XSECTIONS, ORIFICES, WEIRS, LOSSES
    generateur_donnees.py          Sections INFLOWS, DWF, CURVES, TIMESERIES, REPORT, TAGS
  domain/
    aides.py                       Utilitaires (recherche nœud proche, mappage types)
    processeur_noeuds.py           Traitement regards, rejets, ouvrages, stations, STEP
    processeur_conduites.py        Traitement canalisations
    processeur_pompes.py           Traitement pompes de relevage
  infrastructure/
    config.py                      Configuration (CRS, paramètres SWMM)
    chargeur_geopackage.py         Chargement GeoPackage, cache, centre zone
    orientation_conduites.py       Orientation hydraulique amont → aval
    labels_rues.py                 Génération labels noms de rues
  views/
    index.html                     Interface Leaflet
    styles.css                     Styles CSS
    carte.js                       Logique JavaScript carte

tests/
    test_processeur_noeuds.py      Tests unitaires nœuds
    test_processeur_conduites.py   Tests unitaires conduites
    test_generateur_swmm.py        Tests unitaires génération SWMM
```
