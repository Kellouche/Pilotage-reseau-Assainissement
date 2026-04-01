# Pilotage Reseau d'Assainissement

Outils de visualisation interactive et de generation de fichiers SWMM 5.2 a partir de donnees GeoPackage.

## Fonctionnalites

- **Visualisation cartographique** interactive avec clustering dynamique (Leaflet.js)
- **Generation de fichiers SWMM** .inp a partir de donnees geospatiales
- **Reprojection automatique** UTM Zone 31N (EPSG:32631) → WGS84 (EPSG:4326)

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

### Generation SWMM

```bash
python main.py
# genere Assainissement_Ville.inp
```

### Tests

```bash
pytest test_*.py -v
```

## Structure

```
server.py            Serveur Flask (visualisation)
index.html           Interface web (Leaflet.js)
main.py              Point d'entree SWMM
data_processor.py    Traitement des donnees geospatiales
swmm_generator.py    Generation du fichier .inp
config.py            Configuration (CRS, parametres SWMM)
launch_server.bat    Lanceur Windows
```

## Donnees

| Element              | Nombre  |
|----------------------|---------|
| Regards              | 10 538  |
| Rejets               | 79      |
| Canalisations        | 10 295  |
| Ouvrages speciaux    | 38      |
| Stations de relevage | 5       |
| STEP                 | 1       |

## Dependances

- geopandas, pandas, shapely, numpy — traitement geospatial
- flask — serveur web
