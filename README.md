# Pilotage Réseau d'Assainissement

Outils de visualisation interactive et de génération de fichiers SWMM 5.2 à partir de données GeoPackage.

## Fonctionnalités

- **Visualisation cartographique** interactive (Leaflet.js)
- **Génération de fichiers SWMM** .inp à partir de données géospatiales
- **Reprojection automatique** UTM Zone 31N (EPSG:32631) → WGS84 (EPSG:4326)
- **Architecture MVC** modulaire avec en-têtes de module standardisés

## Installation

```bash
pip install -r requirements.txt
```

## Utilisation

### Visualisation interactive

```bash
python server.py
# ouvrir http://localhost:5000
```

### Tests

```bash
python -m pytest tests/ -v
```

## Structure du projet

```
src/
  controllers/     Contrôleurs Flask et générateur SWMM
  domain/          Logique métier (traitement nœuds, conduites, pompes)
  infrastructure/  Chargement GeoPackage, configuration
  views/           Interface web (HTML, CSS, JS)
tests/             Tests unitaires et d'intégration
```

Voir TODO.md pour l'arborescence détaillée.

## Données

| Élément              | Nombre  |
|----------------------|---------|
| Regards              | 10 538  |
| Rejets               | 79      |
| Canalisations        | 10 295  |
| Ouvrages spéciaux    | 38      |
| Stations de relevage | 5       |
| STEP                 | 1       |

## Dépendances

- geopandas, pandas, shapely, numpy — traitement géospatial
- flask — serveur web

## Auteur

Dr Abdelhakim Kellouche
