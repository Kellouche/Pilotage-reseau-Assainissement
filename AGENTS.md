# Directives et Règles Opérationnelles — DrainPilot 5.2

## 1. Automatisation Intégrale et Livraison Continue (CI / Git)

- **Règle d'or de Livraison Autonome (Zero-Prompt Git)** :
  - Dès qu'une modification ou fonction est testée et validée avec succès par les tests automatiques (100% de réussite), **commiter et pousser automatiquement les changements dans le dépôt Git distant (`git push`) sans jamais demander d'autorisation ni de confirmation à l'utilisateur**.
  - Ne jamais suspendre le travail pour demander « Voulez-vous que je committe ? » ou « Puis-je pousser les modifications ? ». L'approbation est permanente et implicite dès lors que la suite de validation est au vert.
  - Le message de commit doit être explicite, structuré selon les conventions (Conventional Commits : `feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`) et indiquer le bilan de tests validés.

## 2. Validation Automatique Obligatoire Avant Commit/Push

- Exécuter impérativement la suite complète des tests de non-régression :
  - Tests unitaires et d'intégration : `.venv\Scripts\pytest -q`
  - Intégrité syntaxique des fichiers JavaScript frontend : validation Node syntaxique sur `static/js/`
  - Procédures de test MCP disponibles pour prévenir toute régression.
- En cas d'échec ou d'erreur lors des tests, bloquer le commit, diagnostiquer la cause et corriger immédiatement.

### 2.0 Conventions de codage — fichiers sources

- Tout fichier `.py`, `.js`, `.html`, `.css` **doit** respecter `docs/CONVENTIONS_CODE.md` :
  - **en-tête explicite obligatoire** en tête de fichier (Projet / Auteur / Dates / Objet, gabarits par langage fournis dans le document) ;
  - **taille maximale 600 lignes** — au-delà, découpage modulaire obligatoire (les fichiers historiques au-delà de la limite sont tolérés mais à refactorer progressivement).
- `Date de modification` de l'en-tête mise à jour à chaque modification substantielle.

### 2.1 Validation navigateur MCP — Règle impérative à chaque modification

- **Toute modification touchant l'interface, la carte, les couches, les formulaires, les workflows utilisateur ou tout comportement visible DOIT être testée dans le navigateur via MCP (Playwright) avant livraison.**
- Protocole obligatoire :
  1. Vérifier que le serveur API tourne et répond (`http://127.0.0.1:<API_PORT>/health` → HTTP 200). S'il ne tourne pas, **le démarrer en mode silencieux** (voir §2.2) avant tout test.
  2. Exécuter le scénario de validation correspondant à la modification (chargement cockpit, interaction concernée, absence d'erreurs console).
  3. **Corriger définitivement toute erreur constatée** — ne jamais livrer avec une erreur console ou un comportement dégradé connu.
  4. Si le correctif s'avère impossible dans le périmètre de la modification, **rendre un compte exhaustif et documenté** : erreur constatée, capture/trace, cause identifiée, contournement éventuel, et ticket de suivi — jamais un silence.
- Une modification « validée » sans passage navigateur sur la zone touchée n'est pas une modification validée.

### 2.2 Vérification du serveur en mode silencieux — à chaque contribution

- **À chaque contribution (commit/push), vérifier que le serveur API local tourne en mode silencieux** :
  - `API_RELOAD=false` (pas de WatchFiles, pas de spam de logs) ;
  - sortie redirigée vers `logs/api_server.log` ;
  - port défini par `API_PORT` dans `config/settings.py` ;
  - `GET /health` doit répondre HTTP 200.
- **Si le serveur n'est pas lancé ou ne répond pas : le démarrer silencieusement** avant de poursuivre les tests, sans demander de permission :
  ```bash
  API_RELOAD=false python run_api.py > logs/api_server.log 2>&1 &
  ```
  puis vérifier `http://127.0.0.1:<API_PORT>/health` → HTTP 200.
- Ne jamais laisser un serveur en mode `--reload` ou avec la console polluée par des logs de debug pour une session de validation.

## 3. Règle d'Invariance Hydraulique & Scientifique

- Préserver strictement l'invariance des calculs SWMM 5.2 (résolution Saint-Venant 1D, bilans de continuité massique stricts).
- Le Golden Dataset (`tests/data/golden_dataset/`) et la suite Golden Master (`tests/test_golden_master.py`) constituent le filet de sécurité absolu.

## 4. Sécurité, Multi-Tenancy et Stealth 404

- Chaque endpoint et requête de persistance doit garantir l'isolation stricte par `org_id`.
- Respecter scrupuleusement la règle furtive *stealth 404* (aucune fuite d'information inter-organisations).

