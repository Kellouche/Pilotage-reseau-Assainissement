# Lancement du projet

## Objectif

Ce document centralise les commandes de lancement pour éviter les confusions entre
les différents prototypes présents dans le dépôt.

## Composants

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

Il existe une incohérence de port à corriger :

- `run_api.py` utilise le port `5001`.
- `run_server.py` affiche `5002`, mais lance actuellement `8000`.
- `mobile/services/api.js` pointe actuellement vers `http://127.0.0.1:8000`.

Décision recommandée :

- choisir `5001` comme port API FastAPI de référence ;
- aligner ensuite `run_server.py`, les scripts `.bat` et le client mobile ;
- documenter clairement le serveur Flask historique sur `5000`.

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

