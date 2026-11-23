# Lancement du projet

## Objectif

Ce document centralise les commandes de lancement pour éviter les confusions entre
les différents modes de la plateforme.

## Commandes officielles

| Besoin | Commande |
|---|---|
| API FastAPI avec auto-reload (dev) | `python run_api.py` |
| API FastAPI sans auto-reload | `python run_server.py` |
| API silencieuse (logs fichier) | `API_RELOAD=false python run_api.py > logs/api_server.log 2>&1` |
| Mobile Flutter | `cd mobile` puis `flutter run` |
| Mobile Flutter web | `cd mobile` puis `flutter run -d chrome` |

> **Note :** l'ancien serveur Flask historique (`server.py`, port 5000) et son
> lanceur `launch_server.bat` ont été retirés du dépôt. L'API FastAPI est
> l'unique backend de la plateforme.

### API FastAPI

Commande recommandée :

```bash
python run_api.py
```

Le port est défini par `API_PORT` dans `config/settings.py` (ou variable
d'environnement `API_PORT`) — il n'est pas figé dans la documentation.
Adapter les URL ci-dessous en conséquence :

```text
http://localhost:<API_PORT>
http://localhost:<API_PORT>/docs
```

Remarque :

- `run_api.py` et `run_server.py` lancent `api.main:app` ; l'hôte et le port
  viennent de `API_HOST` / `API_PORT`.
- `run_api.py` active l'auto-reload WatchFiles ; `run_server.py` démarre
  sans reload.
- Mode silencieux : `API_RELOAD=false` + redirection vers `logs/api_server.log`.
- Le script Windows associé est `launch_api.bat`.

### Application mobile Flutter

Commande :

```bash
cd mobile
flutter pub get
flutter run
```

Mode web possible :

```bash
cd mobile
flutter run -d chrome
```

L'application lit l'URL de l'API via la variable d'environnement compilée
`API_BASE_URL` (voir `mobile/lib/services/api_service.dart`) ou
`mobile/.env.example`. Le port doit correspondre à `API_PORT` côté backend.
Voir [Application mobile](MOBILE.md).

## Base de données

Comportement actuel :

- tentative de connexion PostgreSQL via les variables `DB_*` (timeout 2 s) ;
- **fallback automatique vers SQLite** (`swmm_platform.db`) si PostgreSQL est
  indisponible ;
- les tests utilisent exclusivement `test_swmm_platform.db`.

Pour configurer l'environnement :

```bash
copy .env.example .env
```

Puis adapter les chemins et identifiants locaux.

## Vérification rapide

API :

```bash
python run_api.py
```

Puis ouvrir :

```text
http://localhost:<API_PORT>/health
http://localhost:<API_PORT>/docs
```
