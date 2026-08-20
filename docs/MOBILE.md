# Application mobile

## Statut retenu

La piste mobile officielle de la phase 1 est l'application Flutter située
dans `mobile/`.

Les autres pistes restent à part :

- `swmm_mobile_flutter/` : prototype Flutter expérimental, à archiver ou confirmer ;
- `mobile_app.html` : prototype web autonome, utile pour comparaison mais non officiel ;
- scripts `final_fix.bat`, `fix_and_launch.bat`, `launch_final.bat`, `launch_mobile_app.bat` : scripts ponctuels à auditer avant conservation.

## Lancement

Depuis la racine du projet :

```bash
cd mobile
flutter pub get
flutter run
```

Mode web de test :

```bash
cd mobile
flutter run -d chrome
```

Remarque : la compilation native Android a été vérifiée en phase 1. Le mode web
reste utile pour les essais rapides, mais il devra être stabilisé séparément si la
plateforme web mobile devient un livrable officiel.

## Configuration de l'API

L'application lit l'URL du backend depuis le fichier `.env`.

Créer un fichier local `mobile/.env` à partir de :

```bash
copy mobile\.env.example mobile\.env
```

Valeur par défaut :

```env
API_BASE_URL=http://127.0.0.1:5001
```

Pour un téléphone physique, `127.0.0.1` pointe vers le téléphone lui-même. Il faut
utiliser l'adresse IP locale de la machine qui exécute FastAPI, par exemple :

```env
API_BASE_URL=http://192.168.1.10:5001
```

## Contenu versionné

À pousser dans Git :

- `mobile/lib/`
- `mobile/android/`
- `mobile/assets/`
- `mobile/pubspec.yaml`
- `mobile/pubspec.lock`
- `mobile/.env.example`

À ne pas pousser :

- `mobile/build/`
- `mobile/.dart_tool/`
- `mobile/.env`

## Tests et vérifications

Avant de pousser une modification mobile :

- vérifier la configuration de pubspec.yaml ;
- vérifier au minimum les fichiers Dart modifiés ;
- vérifier la compilation Android quand le changement touche l'application native ;
- lancer les tests backend si le changement touche l'intégration API.
