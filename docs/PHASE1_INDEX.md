# 📚 Phase 1 — Documentation Index

**Organisée pour rapide navigation et référence**

---

## 🎯 Point d'entrée — Choisir votre rôle

### 👤 Je suis utilisateur (Opérateur réseau)
→ Lire : [PHASE1_QUICKSTART.md](PHASE1_QUICKSTART.md)
- Démarrer l'app
- Utiliser le diagnostic topologie
- Interpréter résultats

### 🧑‍💻 Je suis développeur (Implémentation)
→ Lire : [PHASE1_TECHNICAL_NOTES.md](PHASE1_TECHNICAL_NOTES.md)
- Architecture système
- Points clés du code
- Ajouter Phase 2

### 🏗️ Je suis architect (Design)
→ Lire : [PHASE1_TOPOLOGIE.md](PHASE1_TOPOLOGIE.md)
- Théorie hydraulique complète
- Algorithmes détaillés
- Cas d'usage

### ✅ Je suis testeur (QA)
→ Lire : [PHASE1_VALIDATION_CHECKLIST.md](PHASE1_VALIDATION_CHECKLIST.md)
- Checklist de validation
- Tests end-to-end
- Troubleshooting

### 📋 Je suis project manager (Tracking)
→ Lire : [PHASE1_INTEGRATION_SUMMARY.md](PHASE1_INTEGRATION_SUMMARY.md)
- Statut complet
- Fichiers modifiés/créés
- Timeline

---

## 📖 Documentation par sujet

### Théorie hydraulique
- [PHASE1_TOPOLOGIE.md](PHASE1_TOPOLOGIE.md#-trois-validations-critiques)
  - Cohérence profondeurs (±50cm)
  - Chevauchements géométriques
  - Doublons regards (<2m)

### Guide utilisateur
- [PHASE1_QUICKSTART.md](PHASE1_QUICKSTART.md#-démarrage-rapide)
  - Installation
  - Lancement application
  - Utilisation UI

### Implémentation technique
- [PHASE1_TECHNICAL_NOTES.md](PHASE1_TECHNICAL_NOTES.md#-architecture-système)
  - Architecture 3 piliers
  - Code source clés
  - Performance

### Validation qualité
- [PHASE1_VALIDATION_CHECKLIST.md](PHASE1_VALIDATION_CHECKLIST.md#-validation-phase-1--checklist-finale)
  - Checklist fichiers
  - Tests UI/UX
  - Tests backend

### Résumé projet
- [PHASE1_INTEGRATION_SUMMARY.md](PHASE1_INTEGRATION_SUMMARY.md)
  - Statut complet
  - Fichiers modifiés
  - Points d'attention

---

## 🗂️ Fichiers source référencés

### Backend
- `src/validateurs/topologie.py` - Classe principale (190 lignes)
- `src/validateurs/__init__.py` - Module export
- `src/qualite_reseau.py` - Intégration Phase 1
- `config/validations_phase1.py` - Configuration seuils

### Frontend
- `templates/carte.html` - UI checkboxes Phase 1
- `static/js/carte_anomalies.js` - Mapping anomalies
- `static/js/carte_ui.js` - Modal corrections (existant)

### Tests
- `tests/test_phase1_integration.py` - Tests d'intégration

---

## 📊 Matrice de couverture

| Aspect | Quick-Start | Technical | Topologie | Checklist | Summary |
|--------|:-----------:|:---------:|:---------:|:---------:|:-------:|
| Théorie hydraulique | ⭐ | ⭐ | ⭐⭐⭐ | - | ⭐ |
| Utilisation UI | ⭐⭐⭐ | ⭐ | - | ⭐⭐⭐ | ⭐ |
| Code backend | ⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐ |
| Configuration | ⭐⭐ | ⭐⭐ | ⭐ | - | ⭐ |
| Performance | ⭐ | ⭐⭐⭐ | - | - | ⭐ |
| Validation | - | ⭐ | - | ⭐⭐⭐ | ⭐ |
| Troubleshooting | ⭐⭐ | ⭐⭐ | - | ⭐⭐⭐ | ⭐ |

---

## 🚀 Quick reference

### Je dois...

#### ...démarrer l'app
1. `python run_api.py` (Terminal 1)
2. `python run_server.py` (Terminal 2)
3. `http://localhost:5001/carte`

#### ...lancer le diagnostic
1. Onglet **Topologie**
2. Cocher 4 cases
3. Cliquer **[Filtrer]**

#### ...tester backend
```bash
python tests/test_phase1_integration.py
```

#### ...modifier une tolérance
1. Éditer `config/validations_phase1.py`
2. Changer `TOLERANCE_PROFONDEUR = 0.50` → `0.75`
3. Relancer API

#### ...ajouter Phase 2
1. Créer `src/validateurs/pente.py`
2. Ajouter classe `ValidateurPente`
3. Intégrer dans `qualite_reseau.py`
4. Suivre template [PHASE1_TECHNICAL_NOTES.md](PHASE1_TECHNICAL_NOTES.md#-ajouter-phase-2-template)

#### ...résoudre un problème
→ Aller à [PHASE1_VALIDATION_CHECKLIST.md](PHASE1_VALIDATION_CHECKLIST.md#-troubleshooting)

---

## 📚 Ordre de lecture recommandé

### Première fois (30 min)
1. [PHASE1_QUICKSTART.md](PHASE1_QUICKSTART.md) (5 min)
2. [PHASE1_TOPOLOGIE.md](PHASE1_TOPOLOGIE.md) (15 min)
3. [PHASE1_INTEGRATION_SUMMARY.md](PHASE1_INTEGRATION_SUMMARY.md) (10 min)

### Pour développement (2h)
1. [PHASE1_TECHNICAL_NOTES.md](PHASE1_TECHNICAL_NOTES.md) (1h)
2. Code source `src/validateurs/topologie.py` (30 min)
3. Tests `tests/test_phase1_integration.py` (30 min)

### Pour validation (1h)
1. [PHASE1_VALIDATION_CHECKLIST.md](PHASE1_VALIDATION_CHECKLIST.md) (30 min)
2. Lancer les tests (30 min)

---

## 🔄 Maintenance

### Après chaque modification
- [ ] Lancer tests
- [ ] Vérifier console (zéro erreur)
- [ ] Mettre à jour doc si besoin

### Avant déploiement prod
- [ ] Checklist validation
- [ ] Tests backend passent
- [ ] UI ne crash pas
- [ ] Pas de console errors

### Biannuel
- [ ] Revoir tolérances (seuils)
- [ ] Benchmarker performance
- [ ] Ajouter Phase 2

---

## 🆘 Besoin d'aide?

### Problème technique
→ [PHASE1_TECHNICAL_NOTES.md](PHASE1_TECHNICAL_NOTES.md#-debugging)

### Problème test
→ [PHASE1_VALIDATION_CHECKLIST.md](PHASE1_VALIDATION_CHECKLIST.md#-troubleshooting)

### Besoin info théorique
→ [PHASE1_TOPOLOGIE.md](PHASE1_TOPOLOGIE.md)

### Besoin détails implémentation
→ `src/validateurs/topologie.py` (code commenté)

---

## ✨ Résumé rapide

**Phase 1** = 3 validations hydrauliques fondamentales

| Validation | Tolérance | Exemple |
|-----------|-----------|---------|
| Profondeur | ±50cm | Regard à 1.50m, conduite à 2.15m → Anomalie |
| Géométrie | <1cm | 2 conduites se croisent sans nœud → Anomalie |
| Doublons | <2m | 2 regards à 1.5m d'écart → Anomalie |

**Résultats** :
- Backend : 3 validateurs SQL/Python
- Frontend : 3 checkboxes + dropdown
- API : 9 catégories anomalies

**Status** : ✅ Production-ready

---

**Index v1.0** — Mise à jour avec chaque phase
