# Phase 1 — Fondations topologiques hydrauliques

## 🎯 Vue d'ensemble

**Phase 1** implémente les **3 validations topologiques critiques** pour un réseau d'assainissement:

| # | Validation | Tolérance | Sévérité |
|---|------------|-----------|----------|
| 1️⃣ | Cohérence profondeurs | ±50cm | **MAJEURE** |
| 2️⃣ | Chevauchements géométriques | <1cm | **MAJEURE** |
| 3️⃣ | Doublons regards | <2m | **MINEURE** |

---

## 🛠️ Installation

Aucune installation supplémentaire requise. Phase 1 est **intégré par défaut** dans l'application.

### Fichiers créés

```
src/validateurs/
  ├── topologie.py          # 3 validateurs (190 lignes)
  └── __init__.py           # Module export

config/
  └── validations_phase1.py # Configuration + seuils

docs/
  └── PHASE1_TOPOLOGIE.md   # Documentation complète

tests/
  └── test_phase1_integration.py  # Tests d'intégration
```

---

## 🚀 Démarrage rapide

### 1. Lancer l'application

```bash
# Terminal 1 - API (port 5000)
python run_api.py

# Terminal 2 - UI (port 5001)
python run_server.py
```

### 2. Accéder à la carte

```
http://localhost:5001/carte
```

### 3. Lancer le diagnostic

1. Cliquer sur l'onglet **Topologie**
2. Vérifier que les **4 checkboxes** sont présentes:
   - Tronçons orphelins
   - **Dénivellation excessive** ✨ NEW
   - **Chevauchements géométriques** ✨ NEW
   - **Doublons regards <2m** ✨ NEW

3. Cliquer **[Filtrer]**

### 4. Observer les résultats

- **Compteurs** : Affichent le nombre d'anomalies par type
- **Couleurs** : 
  - 🔴 MAJEURE (rouge/orange)
  - 🟢 MINEURE (vert)
- **Dropdown** : Sélectionner une anomalie pour zoomer

---

## 📊 Utilisation en API

### Endpoint diagnostic complet

```python
POST /api/v1/qualite/diagnostic

# Réponse
{
  "anomalies": {
    "incoherence_profondeur_topologie": [
      {
        "type": "incoherence_profondeur_topologie",
        "severite": "majeure",
        "id_conduite": 42,
        "description": "Écart de profondeur excessive",
        "details": {
          "profondeur_fin_conduite": 2.15,
          "profondeur_noeud": 1.50,
          "difference": 0.65,
          "tolerance": 0.50
        },
        "longitude": 1.234,
        "latitude": 36.567
      }
    ],
    "chevauchement_geometrique": [...],
    "doublon_regards": [...]
  },
  "scores_qualite": {
    "topologie": 92.5
  }
}
```

---

## 🧪 Tests

### Lancer tous les tests Phase 1

```bash
python tests/test_phase1_integration.py
```

**Output attendu** :
```
============================================================
🧪 TEST PHASE 1 — FONDATIONS TOPOLOGIQUES
============================================================

✓ Connexion à la base de données établie

🔍 Lancement diagnostic complet...

📊 RÉSULTATS PHASE 1:
────────────────────────────────────────────────────────
⚠️  incoherence_profondeur_topologie         :   8 anomalie(s)
⚠️  chevauchement_geometrique               :   2 anomalie(s)
✅ doublon_regards                          :   0 anomalie(s)
────────────────────────────────────────────────────────
📈 TOTAL PHASE 1                            :  10 anomalie(s)

✅ TEST PHASE 1 TERMINÉ AVEC SUCCÈS
```

---

## 📈 Configuration des seuils

Éditer `config/validations_phase1.py` pour modifier les tolérances:

```python
VALIDATIONS_TOPOLOGIE = {
    "coherence_profondeurs": {
        "tolerance_cm": 50,  # ← TOLÉRANCE (en cm)
        "severite": "majeure"
    },
    
    "chevauchement_geometrique": {
        "tolerance_distance_m": 0.01,  # ← DISTANCE MIN (en m)
        "severite": "majeure"
    },
    
    "doublon_regards": {
        "distance_max_m": 2.0,  # ← DISTANCE MAX (en m)
        "severite": "mineure"
    }
}
```

---

## 🔧 Architecture technique

### ValidateurTopologie class

```python
from src.validateurs.topologie import ValidateurTopologie

validateur = ValidateurTopologie(session)

# Validation 1: Profondeurs
anomalies_prof = validateur.valider_coherence_profondeurs()

# Validation 2: Géométrie
anomalies_chev = validateur.valider_chevauchements_geometriques()

# Validation 3: Doublons
anomalies_dbl = validateur.detecter_doublons_regards()
```

### Intégration dans QualiteReseau

```python
from src.qualite_reseau import QualiteReseau

qualite = QualiteReseau(settings)
rapport = qualite.analyser_reseau_complet()

# Accéder aux résultats Phase 1
anomalies_prof = rapport["anomalies"]["incoherence_profondeur_topologie"]
anomalies_chev = rapport["anomalies"]["chevauchement_geometrique"]
anomalies_dbl = rapport["anomalies"]["doublon_regards"]
```

---

## 🎨 UI/UX

### Onglet Topologie (après)

```
┌──────────────────────────────────────────────┐
│ Diagnostic topologie                         │
├──────────────────────────────────────────────┤
│                                              │
│ Veuillez cocher les cases pour lancer       │
│ l'analyse.                                   │
│                                              │
│ ☑ Tronçons orphelins              (5)       │
│                                              │
│ ─────────────────────────────────────────   │
│ Phase 1 — Fondations topologiques            │
│ ☑ Dénivellation excessive         (8) ✨     │
│ ☑ Chevauchements géométriques    (2) ✨     │
│ ☑ Doublons regards <2m            (0) ✨     │
│                                              │
│ [Filtrer] [Zoom]                            │
└──────────────────────────────────────────────┘
```

### Modale de correction

```
┌────────────────────────────────────┐
│ 🔧 Dénivellation excessive        │
├────────────────────────────────────┤
│                                   │
│ 💧 Solution hydraulique            │
│ Écart: 0.65m (tolérance: 0.50m)  │
│                                   │
│ [Corriger les profondeurs]        │
└────────────────────────────────────┘
```

---

## 📋 Checklist d'implémentation

- ✅ ValidateurTopologie implémenté (3 validations)
- ✅ Intégration dans QualiteReseau
- ✅ UI checkboxes Phase 1 ajoutées
- ✅ Mapping tabMappings mis à jour
- ✅ Titres et descriptions Phase 1 ajoutés
- ✅ Test d'intégration créé
- ✅ Documentation complète

---

## 🐛 Troubleshooting

### Q: Les anomalies Phase 1 n'apparaissent pas

**R**: Vérifier les logs API:
```bash
# Terminal API
tail -f run_api.log  # Si log file existe
# Ou relancer avec output visible
python -u run_api.py
```

### Q: "ModuleNotFoundError: No module named 'validateurs'"

**R**: Exécuter depuis le répertoire racine:
```bash
cd /path/to/swmm-platform-poc
python tests/test_phase1_integration.py
```

### Q: Les seuils ne correspond pas au besoin hydraulique

**R**: Éditer `config/validations_phase1.py`:
- `tolerance_cm`: Augmenter pour connexions très différentes
- `distance_max_m`: Diminuer pour doublons proches
- `tolerance_distance_m`: Géométrie exacte requis?

---

## 📚 Documentation complète

- [PHASE1_TOPOLOGIE.md](PHASE1_TOPOLOGIE.md) - Théorie hydraulique
- [src/validateurs/topologie.py](../src/validateurs/topologie.py) - Code source commenté
- [config/validations_phase1.py](../config/validations_phase1.py) - Configuration

---

## 🔮 Prochaines étapes (Phase 2+)

- [ ] Analyse débitabilité (Q = 3.1 × D²·²)
- [ ] Détection sous-dimensionnement
- [ ] Vérification vitesse (0.3-3 m/s)
- [ ] Pentes suspectes (< 0.3%, > 15%)

---

**Phase 1 v1.0** — Prêt pour production ✨
