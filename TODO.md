# TODO — Réseau d'Assainissement

**Date :** 2026-04-02 07:12
**Utilisateur :** Hakim

---

## À faire

- [ ] Délimitation automatique des bassins versants
- [ ] Phase suivante du rapport : reprendre la délimitation des bassins versants (MNT/DEM)
- [ ] Pousser sur GitHub quand tout est stable

## Fait

- [x] Restructuration MVC du projet (règles 1-5)
- [x] En-têtes de module standardisés (auteur, version, dates, objectif)
- [x] Découpage des fichiers >250 lignes en sous-modules
- [x] Architecture : src/controllers, src/domain, src/infrastructure, src/views, tests
- [x] Sens d'écoulement hydraulique (cotes de radier, inversion des coordonnées)
- [x] Noms de rues comme labels sur la carte (134 rues depuis les regards)
- [x] Flèches de sens d'écoulement visibles à partir du zoom 14
- [x] Labels noms de rues visibles à partir du zoom 13
- [x] Taille des symboles adaptative selon le zoom
- [x] Centre de la carte calculé automatiquement depuis les données
- [x] Filtrage des colonnes GeoPackage → performance (58s → 6s)
- [x] Popups enrichis (rue, commune, diamètre, profondeur, matériau)
- [x] Clustering Leaflet désactivé (points individuels)
- [x] Supprimer Streamlit, garder Flask uniquement
- [x] Supprimer graph_analysis.py et toute logique de clustering
- [x] Simplifier server.py (chargement GeoPackage → API JSON)
- [x] Simplifier index.html (6 couches, pas de clusters)
- [x] Corriger les accents UTF-8 (console Windows + interface web)
- [x] Ajouter en-têtes anti-cache dans Flask (Cache-Control)
- [x] Corriger le zoom (fitBounds uniquement au chargement initial)

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
