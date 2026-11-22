# Application mobile

## Statut retenu

La piste mobile officielle est l'application Flutter située dans `mobile/`.

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

Remarque : la compilation native Android a été vérifiée. Le mode web
reste utile pour les essais rapides.

## Configuration de l'API

L'application lit l'URL du backend via la variable d'environnement compilée
`API_BASE_URL` (`String.fromEnvironment` dans
`mobile/lib/services/api_service.dart`, défaut `http://127.0.0.1:5002`).
Elle se passe à la compilation avec `--dart-define` :

```bash
cd mobile
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:5002
```

Pour un téléphone physique, `127.0.0.1` pointe vers le téléphone lui-même.
Il faut utiliser l'adresse IP locale de la machine qui exécute FastAPI :

```bash
flutter run --dart-define=API_BASE_URL=http://192.168.1.10:5002
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

## Tests et vérifications

Avant de pousser une modification mobile :

- vérifier la configuration de pubspec.yaml ;
- vérifier au minimum les fichiers Dart modifiés ;
- vérifier la compilation Android quand le changement touche l'application native ;
- lancer les tests backend si le changement touche l'intégration API.
