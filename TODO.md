# TODO — Réseau d'Assainissement

**Date :** 2026-04-01 23:44
**Utilisateur :** Hakim

---

## À faire

- [ ] Délimitation automatique des bassins versants
- [ ] Phase suivante du rapport : reprendre la délimitation des bassins versants (MNT/DEM)
- [ ] Pousser sur GitHub quand tout est stable

## Fait

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

## Fichiers actuels

| Fichier | Rôle |
|---------|------|
| server.py | Serveur Flask — chargement GeoPackage, orientation hydraulique, labels rues, API /get-data |
| index.html | Interface Leaflet — carte interactive, 6 couches, flèches, labels rues |
| config.py | Configuration SWMM |
| data_processor.py | Traitement données SWMM |
| swmm_generator.py | Génération fichier .inp |
| main.py | Point d'entrée SWMM |
| requirements.txt | Dépendances Python |
| Rapport_Methodologique_Clusters_Bassins.md | Rapport méthodologique (à mettre à jour) |
