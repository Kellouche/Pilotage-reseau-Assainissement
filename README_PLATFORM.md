# SWMM Platform POC

**Plateforme Collaborative de Gestion Dynamique des Réseaux d'Assainissement**

## 🎯 Objectif

Transformer le générateur de fichiers SWMM existant en plateforme temps réel permettant :
- **Saisie terrain mobile** : mise à jour du réseau par opérateurs
- **Synchronisation bidirectionnelle** : données toujours cohérentes
- **Simulation SWMM à la demande** : évaluation instantanée des impacts
- **Lutte proactive contre les inondations** : anticipation via modélisation

## 🏗️ Architecture (Zero Budget)

```
Mobile App (React Native Expo)
         ↓ HTTPS
FastAPI Backend (Python)
         ↓
PostgreSQL + PostGIS (données persistentes)
         ↓
Celery Workers ( simulations SWMM asynchrones )
```

**Stack 100% gratuite :**
- FastAPI (web framework)
- PostgreSQL + PostGIS (base de données spatiale)
- Redis (cache + broker Celery)
- Celery (tâches asynchrones)
- React Native Expo (mobile)
- Leaflet/MapLibre (cartographie)

## 🚀 Installation & Démarrage

### Prérequis

- Python 3.10+ (déjà installé)
- PostgreSQL 15+ (optionnel, SQLite fallback)
- Redis (optionnel, pour Celery)

### Installation dépendances

```bash
cd swmm-platform-poc
pip install -r requirements.txt
```

### Configuration

Créer un fichier `.env` (optionnel) :

```bash
DB_HOST=localhost
DB_PORT=5432
DB_NAME=swmm_platform
DB_USER=postgres
DB_PASSWORD=votre_mot_de_passe
REDIS_HOST=localhost
REDIS_PORT=6379
```

Si PostgreSQL n'est pas installé, l'API utilise un mode démo avec données en mémoire.

### Lancement

**Mode simple (sans Celery) :**
```bash
python run_api.py
# ou
python -m uvicorn api.main:app --reload --port 5001
```

**Avec Celery (recommandé prod) :**
```bash
# Terminal 1: Redis
redis-server

# Terminal 2: Celery worker
celery -A workers.celery_app worker --loglevel=info

# Terminal 3: API
python run_api.py
```

### Documentation API

Une fois l'API lancée :
- **Swagger UI interactive** : http://localhost:5001/docs
- **ReDoc** : http://localhost:5001/redoc

## 📱 Application Mobile (React Native Expo)

À créer dans `/mobile` (non inclus dans ce POC).

Structure minimale :
```
mobile/
├── App.js              # Point d'entrée
├── /screens
│   ├── MapScreen.js    # Carte réseau
│   ├── EditScreen.js   # Formulaire édition
│   └── SimList.js      # Liste simulations
├── /services
│   ├── api.js          # Appels API
│   └── sync.js         # Synchronisation delta
└── /storage
    └── database.js     # SQLite local
```

Lancement Expo :
```bash
cd mobile
npm install
npx expo start
# Scanner QR avec Expo Go sur téléphone
```

## 🔄 Synchronisation Mobile

### Delta Sync

Le client envoie sa version actuelle (numéro) → serveur retourne uniquement modifications.
Format :

```json
GET /api/v1/sync/delta?since_version=42

{
  "version": 43,
  "timestamp": "2026-04-25T21:30:00Z",
  "changes": [
    {
      "type": "update",
      "layer": "regards",
      "feature_id": "R1054",
      "changes": {"profondeur": 3.5}
    }
  ],
  "deleted_ids": []
}
```

### Push Modifications

```json
POST /api/v1/sync/push
{
  "device_id": "mobile_001",
  "changes": [
    {
      "type": "update",
      "layer": "regards",
      "feature_id": "R1054",
      "changes": {"diametre": 0.5}
    }
  ]
}

→ Réponse :
{
  "accepted": 1,
  "rejected": 0,
  "new_version": 44,
  "conflicts": null
}
```

## 🧪 API Endpoints Principaux

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `GET /` | GET | Info API |
| `GET /health` | GET | Health check DB |
| `GET /api/v1/regards` | GET | Liste regards (filtres) |
| `POST /api/v1/regards` | POST | Créer regard |
| `PATCH /api/v1/regards/{id}` | PATCH | Modifier regard |
| `DELETE /api/v1/regards/{id}` | DELETE | Supprimer regard |
| `GET /api/v1/conduites` | GET | Liste canalisations |
| `POST /api/v1/conduites` | POST | Créer canalisation |
| `GET /api/v1/clusters` | GET | Liste clusters |
| `POST /api/v1/clusters/recalculate-all` | POST | Recalculer tous clusters |
| `GET /api/v1/clusters/{id}/geojson` | GET | Export GeoJSON cluster |
| `POST /api/v1/simulations` | POST | Lancer simulation SWMM |
| `GET /api/v1/simulations/{id}` | GET | Détail simulation |
| `GET /api/v1/simulations/job/{job_id}` | GET | Statut par job_id |
| `GET /api/v1/sync/delta` | GET | Delta modifications |
| `POST /api/v1/sync/push` | POST | Push changements mobile |

## 🗄️ Modèle de Données

### Tables principales

**regards** : points d'accès au réseau
- `id`, `code` (unique), `longitude`, `latitude`
- `profondeur`, `diametre`, `type_res`
- `cluster_id` (foreign key), `version`

**conduites** : canalisations entre regards
- `id`, `fid` (unique), `diametre`, `longueur`
- `id_amont`, `id_aval` (références regards)
- `geometry_wkt` (linestring)

**clusters** : groupes hydrauliques (bassins)
- `id`, `nom`, `exutoire_noeud`
- `nb_conduites`, `nb_regards`, `longueur_totale`
- Géométrie enveloppe

**simulations** : jobs SWMM
- `id`, `job_id` (unique Celery), `cluster_id`
- `status` (PENDING/RUNNING/COMPLETED/FAILED)
- `result_summary` (JSON), `output_file_path`

**audit_logs** : traçabilité complète
- Toute opération CRUD journalisée
- `table_name`, `record_id`, `operation`, `old_values`, `new_values`

## ⚡ Performance & Scalabilité

### Chargement initial

**Problème** : 10 000+ conduites à charger
**Solution** :
- Pagination (`skip`/`limit`) sur tous endpoints list
- Cache Redis pour :
  - Graphe NetworkX (reconstruit 1×/heure)
  - GeoJSON clusters (précalculés)
  - Résultats simulations récentes (24h)

### Synchronisation

**Delta sync** : transfère uniquement changements depuis last_version
- Réduction bande passante : 99% (1 modification vs 10 000 features)
- Latence : < 2s pour 100 changements

**Versioning** : chaque entité a champ `version` (incrément automatique)
- Résolution conflits : Last-Write-Wins avec horodatage

## 🧰 Scripts Utilitaires

### Migration depuis GeoPackage original

```python
# scripts/migrate_gpkg_to_postgres.py
from src.infrastructure.chargeur_geopackage import charger_donnees
from api.database import engine, SessionLocal
from api.models import Regard, Canalisation, Base

# Charger GPKG
data = charger_donnees()

# Convertir en ORM et insérer
db = SessionLocal()
for regard_geojson in data["regards"]["features"]:
    props = regard_geojson["properties"]
    geom = regard_geojson["geometry"]
    regard = Regard(
        code=props["Code"],
        nom_voie=props.get("NOMVOIE"),
        longitude=geom["coordinates"][0],
        latitude=geom["coordinates"][1],
        profondeur=props.get("Profondeur")
    )
    db.add(regard)

db.commit()
```

### Recalcul clusters (CLI)

```bash
python -c "
from src.domain.graphe_reseau import construire_graphe, trouver_exutoires
from src.domain.detecteur_clusters import tracer_cluster_depuis_exutoire, calculer_statistiques
import json

G = construire_graphe()
exutoires = trouver_exutoires(G)
print(f'{len(exutoires)} exutoires trouvés')

for exutoire in exutoires:
    edges = tracer_cluster_depuis_exutoire(G, exutoire['noeud'])
    stats = calculer_statistiques(G, edges)
    print(f\"Cluster {exutoire['nom']}: {stats['nb_conduites']} conduites\")
"
```

## 🐛 Debug & Logs

### Niveaux de log

```bash
# Activer logs SQLAlchemy
export SQL_ECHO=True

# Voir logs Celery
celery -A workers.celery_app worker --loglevel=debug
```

### Vérifications

```bash
# Health check
curl http://localhost:5001/health

# Liste endpoints
curl http://localhost:5001/openapi.json | jq '.paths | keys'

# Test regard
curl -X POST http://localhost:5001/api/v1/regards \
  -H "Content-Type: application/json" \
  -d '{"code":"TEST001","profondeur":2.5,"longitude":3.0,"latitude":36.5}'
```

## 📦 Déploiement Production (Zero-Cost)

### Option 1 : VPS local (recommandé)

- **Matériel** : PC ancien + 8GB RAM
- **OS** : Ubuntu Server 22.04 (gratuit)
- **Web server** : Nginx reverse proxy
- **Process manager** : systemd
- **SSL** : Let's Encrypt (gratuit)

`/etc/systemd/system/swmm-platform.service` :
```ini
[Unit]
Description=SWMM Platform API
After=network.target postgresql.service redis.service

[Service]
User=swmm
WorkingDirectory=/opt/swmm-platform-poc
ExecStart=/usr/bin/python3 run_api.py
Restart=always

[Install]
WantedBy=multi-user.target
```

### Option 2 : Cloud gratuit

- **PythonAnywhere** : 1 worker web gratuit (limité)
- **Railway/Render** : Free tier avec 512MB RAM
- **Cloudflare Tunnel** : exposition sans IP publique

## 📊 Monitoring

### Métriques à collecter

- `api.requests.total` (compteur)
- `api.requests.duration` (histogramme)
- `db.connections.active`
- `simulations.pending`
- `simulations.completed`
- `sync.conflicts`

### Alertes (seuils simples)

- **DB down** → reboot service
- **Queue length > 100** → scale worker
- **Simulation duration > 5min** → timeout investigation

## 🔐 Sécurité (Minimal Viable)

- **HTTPS** : Let's Encrypt (Cloudflare Tunnel ou Nginx)
- **Auth** : JWT tokens (à implémenter)
- **Rate limiting** : 100 req/min par IP (Redis)
- **Input validation** : Pydantic déjà en place
- **Audit** : table `audit_logs` complète

## 📚 Roadmap

### Phase 1 (Terminée - cette semaine)
- ✅ API FastAPI avec endpoints lecture
- ✅ Modèles SQLAlchemy
- ✅ Swagger documentation

### Phase 2 (Semaine prochaine)
- 🔄 Endpoints écriture (POST/PATCH/DELETE)
- 🔄 Migration données GeoPackage → PostgreSQL
- 🔄 Validation métier (contraintes réseau)

### Phase 3 (Semaine 3)
- 🔄 Synchronisation delta (sync mobile)
- 🔄 Mode hors-ligne (SQLite local)
- 🔄 Conflict resolution LWW

### Phase 4 (Semaine 4)
- 🔄 Simulations async (Celery)
- 🔄 Frontend web (Leaflet + forms)
- 🔄 Beta test terrain (1 opérateur)

### Phase 5 (Semaine 5-6)
- 📱 App mobile Expo
- 📊 Dashboard Grafana
- 📈 POC déployé + démo décideurs

## 🤝 Contribution

Ce POC est développé dans un esprit **Zero-Budget** :
- 100% logiciels libres
- Infrastructure locale gratuite
- Code open-source (MIT)

## 📄 Licence

MIT License - Libre d'utilisation, modification, distribution.

---

**Construit avec ❤️ et Python par Dr Abdelhakim Kellouche & Team**

*Plateforme de lutte contre les inondations par la modélisation proactive.*
