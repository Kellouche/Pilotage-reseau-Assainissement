# Application mobile

## Statut retenu

La piste mobile officielle de la phase 1 est l'application React Native/Expo située
dans `mobile/`.

Les autres pistes restent à part :

- `swmm_mobile_flutter/` : prototype Flutter expérimental, non retenu comme piste officielle à ce stade ;
- `mobile_app.html` : prototype web autonome, utile pour comparaison mais non officiel ;
- scripts `final_fix.bat`, `fix_and_launch.bat`, `launch_final.bat`, `launch_mobile_app.bat` : scripts ponctuels à auditer avant conservation.

## Lancement

Depuis la racine du projet :

```bash
cd mobile
npm install
npx expo start
```

Mode web de test :

```bash
cd mobile
npx expo start --web --port 19006
```

Remarque : la compilation native Android a été vérifiée en phase 1. Le mode web
reste utile pour les essais rapides, mais il devra être stabilisé séparément si la
plateforme web mobile devient un livrable officiel.

## Configuration de l'API

L'application lit l'URL du backend depuis `EXPO_PUBLIC_API_BASE_URL`.

Créer un fichier local `mobile/.env` à partir de :

```bash
copy mobile\.env.example mobile\.env
```

Valeur par défaut :

```env
EXPO_PUBLIC_API_BASE_URL=http://127.0.0.1:5001
```

Pour un téléphone physique, `127.0.0.1` pointe vers le téléphone lui-même. Il faut
utiliser l'adresse IP locale de la machine qui exécute FastAPI, par exemple :

```env
EXPO_PUBLIC_API_BASE_URL=http://192.168.1.10:5001
```

## Contenu versionné

À pousser dans Git :

- `mobile/App.js`
- `mobile/app.json`
- `mobile/package.json`
- `mobile/package-lock.json`
- `mobile/metro.config.js`
- `mobile/expo/`
- `mobile/screens/`
- `mobile/services/`
- `mobile/assets/`
- `mobile/.env.example`

À ne pas pousser :

- `mobile/node_modules/`
- `mobile/.expo/`
- `mobile/.env`

## Tests et vérifications

Avant de pousser une modification mobile :

- vérifier la configuration Expo ;
- vérifier au minimum les fichiers JavaScript modifiés ;
- vérifier l'export Android Expo quand le changement touche l'application ;
- lancer les tests backend si le changement touche l'intégration API.
