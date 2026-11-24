# Conventions de Codage — DrainPilot 5.2

> **Statut** : Règles opposables pour tout nouveau code et pour toute modification
> substantielle de code existant. Référence : `AGENTS.md` §2.

## 1. En-tête explicatif obligatoire

Tout fichier source `.py`, `.js`, `.html`, `.css` **doit** commencer par un
bloc d'en-tête identifiant le projet, l'auteur, les dates et l'objet du fichier.
Le format est calqué sur le standard déjà présent dans ~92 % du dépôt.

### 1.1 Python (`.py`)

```python
# -*- coding: utf-8 -*-          # uniquement si le fichier contient des accents
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : AAAA-MM-JJ
Date de modification : AAAA-MM-JJ
Objet : <rôle du fichier en une phrase>
================================================================================
"""
```

### 1.2 JavaScript (`.js`)

```javascript
/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : AAAA-MM-JJ
 * Date de modification : AAAA-MM-JJ
 * Objet : <rôle du fichier en une phrase>
 * ================================================================================
 */
```

### 1.3 HTML (`.html`)

```html
<!--
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : AAAA-MM-JJ
Date de modification : AAAA-MM-JJ
Objet : <rôle du fichier en une phrase>
================================================================================
-->
```

Placée **avant** `<!DOCTYPE html>` pour les templates.

### 1.4 CSS (`.css`)

```css
/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : AAAA-MM-JJ
 * Objet : <rôle du fichier en une phrase>
 * ================================================================================
 */
```

### 1.5 Champs

| Champ | Règle |
|---|---|
| `Projet` | Toujours `DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM` |
| `Auteur` | `Dr Abdelhakim KELLOUCHE` (propriétaire) ; les contributions agent signées `Devin` dans le commit Git, pas dans l'en-tête |
| `Date de création` | Date de création du fichier, jamais modifiée ensuite |
| `Date de modification` | **Mise à jour à chaque modification substantielle** du fichier |
| `Objet` | Rôle précis du fichier (endpoint, composant UI, module métier…) — pas de tautologie (« fichier python ») |

## 2. Taille maximale : 600 lignes

Un fichier source `.py`, `.js`, `.html`, `.css` ne doit **pas dépasser 600
lignes**. Au-delà, le code doit être **découpé en modules**.

### 2.1 Principes de découpage

- **JS** : un module par responsabilité dans `static/js/app/` (ex.
  `time_slider.js`, `hyeto_hydro.js`, `bassins_selection.js`) ; partage d'état
  via `window.*State` explicitement nommé.
- **Python API** : un routeur par domaine dans `api/routes/` ; logique métier
  dans `api/services/` ; extraction domaine dans `src/domain/`.
- **HTML** : morceler en `templates/partials/` (panels, modales, barres
  d'outils) inclus par le template parent.
- **CSS** : regrouper par écran/composant (`cockpit.css`, `carte_style.css`…).

### 2.2 Fichiers existants au-delà de 600 lignes

La règle s'applique **aux nouveaux fichiers** et aux **refactorisations**.
Les fichiers historiques dépassant la limite sont tolérés mais doivent être
découpés **progressivement**, à l'occasion de modifications substantielles —
jamais de refonte brutale non demandée. État approximatif au 2026-11-24 :

| Fichier | Lignes |
|---|---|
| `api/routes/simulations.py` | ~3 750 |
| `templates/qualite.html` | ~2 500 |
| `api/services/simulation_service.py` | ~1 770 |
| `static/js/app/profil_long.js` | ~1 540 |
| `static/js/app/bassins_selection.js` | ~1 370 |
| `api/routes/qualite.py` | ~1 640 |

### 2.3 Exceptions

- Fichiers **générés** (migration Alembic, code produit par script) : pas
  d'en-tête manuel requis, une ligne de provenance suffit.
- Librairies **vendorisées** (`static/js/vendor/`, `static/css/leaflet.css`) :
  intouchables.
- Fichiers de **tests** : la limite est indicative (900 lignes tolérées pour
  une même famille de tests).

## 3. Autres règles associées

- **Pas de fichier fourre-tout** : si un fichier cumule ≥ 3 responsabilités
  sans rapport, il doit être scindé même sous 600 lignes.
- **Nommage** : `snake_case` Python, `camelCase` JS interne,
  `kebab-case` pour les fichiers statiques.
- **En-tête avant tout code** : le bloc d'en-tête est les premières lignes
  du fichier (ligne 1 pour `.py` hors `coding:`).
