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

## 3. Règle d'Invariance Hydraulique & Scientifique

- Préserver strictement l'invariance des calculs SWMM 5.2 (résolution Saint-Venant 1D, bilans de continuité massique stricts).
- Le Golden Dataset (`tests/data/golden_dataset/`) et la suite Golden Master (`tests/test_golden_master.py`) constituent le filet de sécurité absolu.

## 4. Sécurité, Multi-Tenancy et Stealth 404

- Chaque endpoint et requête de persistance doit garantir l'isolation stricte par `org_id`.
- Respecter scrupuleusement la règle furtive *stealth 404* (aucune fuite d'information inter-organisations).
