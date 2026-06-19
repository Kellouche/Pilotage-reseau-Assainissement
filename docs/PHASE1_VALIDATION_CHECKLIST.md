# ✅ Validation Phase 1 — Checklist finale

**Date** : Octobre 2024  
**Statut** : Prêt pour test complet

---

## 🔍 Avant de démarrer l'application

### Fichiers créés (existence)

```bash
# Backend
[ ] src/validateurs/topologie.py          (190 lignes)
[ ] src/validateurs/__init__.py           (3 lignes)
[ ] config/validations_phase1.py          (120 lignes)

# Frontend
[ ] tests/test_phase1_integration.py      (170 lignes)

# Documentation
[ ] docs/PHASE1_TOPOLOGIE.md
[ ] docs/PHASE1_QUICKSTART.md
[ ] docs/PHASE1_INTEGRATION_SUMMARY.md
```

### Fichiers modifiés (vérification)

```bash
# Code source
[ ] src/qualite_reseau.py
    - Import ValidateurTopologie à la ligne ~13
    - Appel validateur_topo.valider_coherence_profondeurs() ~76
    - Appel validateur_topo.valider_chevauchements_geometriques() ~77
    - Appel validateur_topo.detecter_doublons_regards() ~78

# Templates
[ ] templates/carte.html
    - 3 checkboxes Phase 1 dans tab Topologie
    - Séparateur <hr> + label "Phase 1"
    - 3 span pour compteurs

# JavaScript
[ ] static/js/carte_anomalies.js
    - tabMappings['topologie'] : 4 éléments
    - Titres Phase 1 dans getAnomalieTitre()
    - Descriptions Phase 1 dans getAnomalieDescription()
```

---

## 🚀 Démarrage test (30 secondes)

### Terminal 1 — Lancer l'API

```bash
cd d:\IA Water Data Analysis\Assainissement\swmm-platform-poc
python run_api.py
```

**Attendre** : `✅ Uvicorn running on http://0.0.0.0:5000`

### Terminal 2 — Lancer l'interface

```bash
python run_server.py
```

**Attendre** : `INFO: Application startup complete`

### Navigateur — Ouvrir l'application

```
http://localhost:5001/carte
```

---

## 📋 Test UI/UX (3 minutes)

### Test 1: Onglet Topologie

**Attendu** :
```
┌─ Diagnostic topologie ────┐
│ ☑ Tronçons orphelins      │
│ ─────────────────────────│
│ Phase 1 — Fondations...  │
│ ☑ Dénivellation...       │
│ ☑ Chevauchements...      │
│ ☑ Doublons regards <2m   │
└──────────────────────────┘
```

**Action** :
1. Cliquer tab **Topologie**
2. Vérifier 3 checkboxes Phase 1 visibles
3. ✅ ou ❌ ?

---

### Test 2: Lancer le diagnostic

**Action** :
1. Cliquer **[Filtrer]**
2. Attendre ~1-2 secondes

**Attendu** :
- Compteurs remplis (p.ex. "Dénivellation excessive (8)")
- Dropdown "Aller à l'anomalie" remplit
- Aucun message d'erreur Console

**Vérifier Console Dev** (F12):
```
// Pas d'erreurs comme:
// Error: undefined is not an object (carte_anomalies.js)
// 404: /api/v1/qualite/diagnostic
```

**Action** :
- ✅ Si compteurs remplis
- ❌ Si erreur → Consulter logs API

---

### Test 3: Sélectionner une anomalie Phase 1

**Action** :
1. Dropdown : sélectionner "Dénivellation excessive"
2. Carte zoome à l'anomalie
3. Popup modale s'ouvre

**Attendu** :
```
┌────────────────────────────┐
│ 🔧 Dénivellation excessive │
├────────────────────────────┤
│                            │
│ 💧 Solution hydraulique    │
│ Écart: 0.65m              │
│ (tolérance: 0.50m)        │
│                            │
│ [Corriger...]              │
└────────────────────────────┘
```

**Vérifier** :
- Titre correct : "Dénivellation excessive"
- Formulaire : Montre profondeurs (Phase 1 correct!)
- Pas de profile canvas (qui s'afficherait pour other types)

**Action** :
- ✅ Si modal correct
- ❌ Si mauvais formulaire → JavaScript mismatch

---

### Test 4: Autres anomalies Phase 1

**Répéter Test 3 pour** :
1. "Chevauchements géométriques"
   - Titre : "🌐 Chevauchement géométrique"
   - Description : "Distance: ..."

2. "Doublons regards"
   - Titre : "👥 Doublons regards"
   - Description : "Distance: ..."

**Vérifier** : Chaque anomalie affiche titre + description correcte

---

## 🧪 Test backend (2 minutes)

### Lancer test d'intégration

```bash
# Terminal 3
python tests/test_phase1_integration.py
```

**Attendu** :
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

**Si succès** ✅ :
- Backend fonctionne
- Validateur topologie retourne données
- Intégration QualiteReseau ok

**Si erreur** ❌ :
- Vérifier logs API pour SQL errors
- Vérifier base de données connectée
- Vérifier tables regards/conduites existent

---

## 📊 Résultats attendus (ordre de grandeur)

Pour réseau 5000+ conduites :

| Anomalie | Nombre | % |
|----------|--------|---|
| Dénivellation | 5-15 | 2-3% |
| Chevauchements | 0-3 | <1% |
| Doublons | 2-8 | 0.5-1% |
| **TOTAL** | **10-25** | **3-5%** |

Si aucune anomalie : Peut être ok (réseau bon qualité)  
Si > 50 : Vérifier configuration seuils

---

## 🎯 Critères d'acceptation

| Critère | Attendu | Résultat |
|---------|---------|----------|
| 🔹 UI checkboxes | 3 Phase 1 visibles | [ ] |
| 🔹 Compteurs remplis | Nombres > 0 (ou 0 ok) | [ ] |
| 🔹 Dropdown fonctionne | Sélection zoom map | [ ] |
| 🔹 Modal titre | Correct par type | [ ] |
| 🔹 Modal formulaire | Approprié au type | [ ] |
| 🔹 Backend test | 10-25 anomalies | [ ] |
| 🔹 Pas d'erreurs | Console dev clean | [ ] |

---

## 🐛 Troubleshooting

### Problème : Compteurs à 0 (aucune anomalie Phase 1)

**Cause probable** :
- Réseau de très bonne qualité (rare)
- Ou seuils trop stricts
- Ou données manquantes (profondeurs NULL)

**Solution** :
1. Vérifier `config/validations_phase1.py`
2. Réduire tolerance_cm : 50 → 75
3. Relancer test

### Problème : "ModuleNotFoundError: validateurs"

**Cause** : Lancer depuis mauvais répertoire

**Solution** :
```bash
cd d:\IA Water Data Analysis\Assainissement\swmm-platform-poc
python tests/test_phase1_integration.py
```

### Problème : Erreur SQL dans logs API

**Cause** : Base de données problème

**Solution** :
1. Vérifier PostgreSQL actif ou SQLite présent
2. Vérifier tables regards/conduites existent
3. Vérifier colonnes (latitude, longitude, profondeur)

### Problème : Modal modale modale affiche mauvais formulaire

**Cause** : JavaScript mapping incorrect

**Solution** :
1. Ouvrir Console Dev (F12)
2. Chercher `diagnosticSolutions` dans carte_ui.js
3. Vérifier clés : 'incoherence_profondeur_topologie', etc.

---

## ✨ Succès = Vert partout

```
✅ UI checkboxes Phase 1
✅ Compteurs remplis  
✅ Selection/zoom fonctionne
✅ Modal titre correct
✅ Modal formulaire approprié
✅ Backend test ok
✅ Console clean (zéro erreur)

🎉 Phase 1 PRODUCTION-READY
```

---

## 📞 En cas de problème

1. **Vérifier logs** : Terminal API pour SQL errors
2. **Vérifier database** : `tests/test_phase1_integration.py`
3. **Vérifier console** : F12 → Console tab
4. **Vérifier fichiers** : Tous créés/modifiés per checklist?
5. **Appeler support** : Avec screenshot console + logs

---

**Validation checklist v1.0** ✅
