# Lancement du projet

## Objectif

Ce document centralise les commandes de lancement pour éviter les confusions entre
les différents prototypes présents dans le dépôt.

## Commandes officielles

| Besoin | Commande |
|---|---|
| API FastAPI moderne | `python run_api.py` |
| API FastAPI sans auto-reload | `python run_server.py` |
| Serveur Flask historique | `python server.py` |
| Mobile Expo | `cd mobile` puis `npx expo start` |
| Mobile Expo web | `cd mobile` puis `npx expo start --web --port 19006` |

### API FastAPI moderne

Commande recommandée :

```bash
python run_api.py
```

URL attendue :

```text
http://localhost:5001
http://localhost:5001/docs
```

Remarque :

- `run_api.py` lance `api.main:app` sur le port `5001`.
- C'est l'API principale de la plateforme collaborative.
- Le port peut être modifié avec la variable `API_PORT`.
- Le script Windows associé est `launch_api.bat`.

### Serveur Flask historique

Commande :

```bash
python server.py
```

URL attendue :

```text
http://localhost:5000
```

Remarque :

- Ce serveur correspond au visualiseur historique et aux fonctions initiales.
- Il doit être conservé temporairement, mais distingué de l'API FastAPI.
- Le script Windows associé est `launch_server.bat`.

### Application mobile React Native / Expo

Commande :

```bash
cd mobile
npx expo start
```

Mode web possible :

```bash
cd mobile
npx expo start --web --port 19006
```

URL web attendue :

```text
http://localhost:19006
```

## Point d'attention actuel

Décision de phase 1 :

- le port API FastAPI de référence est `5001` ;
- `run_api.py` et `run_server.py` lisent maintenant `API_HOST` et `API_PORT` depuis `config/settings.py` ;
- le serveur Flask historique reste documenté sur `5000`.

Point restant :

- aligner les scripts `.bat` et les clients mobiles non versionnés qui pointent encore vers un ancien port.
- consolider les scripts mobiles temporaires après décision sur la piste mobile officielle.

## Base de données

Comportement actuel :

- tentative de connexion PostgreSQL via les variables `DB_*` ;
- fallback automatique vers `swmm_platform.db` en SQLite si PostgreSQL est indisponible.

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
http://localhost:5001/health
http://localhost:5001/docs
```

Mobile web :

```bash
cd mobile
npx expo start --web --port 19006
```
