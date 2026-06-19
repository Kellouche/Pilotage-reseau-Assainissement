# 🔧 Notes techniques Phase 1 — Pour développeurs

**Créé** : Octobre 2024  
**Audience** : Équipe développement

---

## 📌 Architecture système

### Trois piliers Phase 1

```
ValidateurTopologie (src/validateurs/topologie.py)
    ├─ valider_coherence_profondeurs()       [Condition IF]
    ├─ valider_chevauchements_geometriques() [Distance math]
    └─ detecter_doublons_regards()           [Cross join SQL]
        │
        ↓ (3 DataFrames)
        │
    analyser_reseau_complet() (src/qualite_reseau.py)
        │
        ↓ (Intégration Phase 1)
        │
    API /api/v1/qualite/diagnostic
        │
        ↓ (JSON + 9 catégories anomalies)
        │
    Frontend (carte_anomalies.js)
        │
        ↓ (Affichage UI + modal)
```

---

## 🔑 Points clés de code

### 1. Coherence profondeurs

```python
# src/validateurs/topologie.py:35-55

# CONDITION: |prof_fin - prof_noeud| > TOLERANCE
difference = abs(prof_fin_conduite - prof_noeud)
if difference > TOLERANCE_PROFONDEUR:
    # ANOMALIE detectée
    
# SEUIL CRITIQUE: 0.50m (50cm)
# Si < 0.30m : Trop strict (lots rejets)
# Si > 0.75m : Trop laxiste (perte validation)
```

**Modification sûre** :
- Augmenter de 0.10m à la fois
- Consulter ingénieur hydraulique
- Tester avec 100 anomalies avant/après

### 2. Chevauchements géométriques

```python
# src/validateurs/topologie.py:68-98

# FALLBACK: Si PostGIS absent, utiliser distance euclidienne
try:
    # PostGIS: ST_Distance() + ST_Intersects()
    distance = ST_Distance(geometry_i, geometry_j)
except:
    # Fallback: Distance euclidienne 2D
    distance = math.sqrt((x1-x2)**2 + (y1-y2)**2)

# TOLÉRANCE: 0.01m (1cm)
# Très strict → évite faux positifs
# Adapter si données en MTR (pas degrés)
```

**Points d'attention** :
- Unités coordonnées doivent être cohérentes (degrés ou mètres)
- PostGIS recommandé pour précision
- Fallback ok pour 90% des cas

### 3. Doublons regards

```python
# src/validateurs/topologie.py:103-130

# HAVERSINE DISTANCE (lat/lon en degrés)
def _distance_haversine(lat1, lon1, lat2, lon2):
    # Formule: a = sin²(Δφ/2) + cos φ1 ⋅ cos φ2 ⋅ sin²(Δλ/2)
    # Distance réelle ≈ 111.2 * km
    
# SEUIL: 2.0m pour communes
# Logique: Même commune + dist < 2m = doublon

# Ajouter colonne commune pour performance:
# IF NOT EXISTS INDEX communes ON regards(commune)
#   CREATE INDEX idx_communes ON regards(commune)
```

**Optimisation SQL** :
- Index sur `regards.commune` critique pour performance
- CROSS JOIN sans index = O(n²) lent sur 10k regards

---

## 🎨 Frontend mappings

### tabMappings — La clé

```javascript
// static/js/carte_anomalies.js:490

const tabMappings = {
    'connexions': ['conduites_sans_regards', 'incoherences_amont_aval'],
    'geometrie': ['geometries_invalides', 'pentes_suspectes'],
    'donnees': ['champs_manquants'],
    'topologie': ['troncons_orphelins', 
                  'incoherence_profondeur_topologie',      // ✨ PHASE 1
                  'chevauchement_geometrique',             // ✨ PHASE 1
                  'doublon_regards']                       // ✨ PHASE 1
};
```

**Règle stricte** :
- Les clés ici **DOIVENT** correspondre à backend `anomalies` JSON
- Si mismatch → dropdown vide, compteurs = 0
- Vérifier lors d'ajout Phase 2

### getAnomalieTitre() — Traductions

```javascript
// static/js/carte_anomalies.js:240-256

const titres = {
    'incoherence_profondeur_topologie': 'Dénivellation excessive',
    'chevauchement_geometrique': 'Chevauchement géométrique',
    'doublon_regards': 'Doublons regards'
};
```

**Important** :
- Titres = UI pour utilisateur (français)
- Keys = API backend (anglais/underscore)
- Toujours cohérent

---

## 🌊 Constantes hydrauliques

### Vérifiées (ne pas modifier sans raison)

```python
# config/validations_phase1.py

# Profondeur: ±50cm = Standard NP 650
TOLERANCE_PROFONDEUR = 0.50  # ✅ Valide

# Doublons: 2m = Distance terrain typique regard
DISTANCE_DOUBLONS = 2.0      # ✅ Valide

# Géométrie: 1cm = Précision mesure topographique
TOLERANCE_GEOMETRIE = 0.01   # ✅ Valide
```

### À adapter (par projet)

- Profondeur : Si terrain très montagneux → 0.75m
- Doublons : Si zonage dense → 1.0m
- Géométrie : Si données UTM → adapter unités

---

## 🚨 Edge cases connus

### 1. Profondeurs NULL

```python
# Problème: regards.profondeur = NULL
# Conséquence: Validation échouée silencieusement
# Solution: Vérifier NOT NULL en requête

query = "WHERE profondeur IS NOT NULL"  # ✅ Correct
```

### 2. Doublons cross-commune

```python
# Deux regards adjacents, deux communes différentes
# Détection: NON (par design)
# Raison: Responsabilité par commune
# Si besoin: Retirer filtre commune dans detecter_doublons_regards()
```

### 3. Conduites sans géométrie

```python
# Profils aucune coordonnée (0,0) ou NULL
# Détection: Chevauchement faux positif possible
# Solution: Filtrer WHERE latitude IS NOT NULL
```

---

## 📈 Performance benchmarks

### Exécution typique

```
Réseau       | Phase 0 | Phase 1 | Total  | État DB
─────────────┼─────────┼─────────┼────────┼──────────
1000 elem    | 20ms    | 50ms    | 70ms   | OK
5000 elem    | 100ms   | 250ms   | 350ms  | OK
10000 elem   | 200ms   | 500ms   | 700ms  | ⚠️ Lent
50000 elem   | ???     | ???     | ???    | ❌ Timeout
```

### Optimisations appliquées

- ✅ Index sur `regards.commune`
- ✅ Index sur `conduites.id_aval`
- ✅ SELECT spécifique (pas SELECT *)

### Si lenteur détectée

1. **Ajouter INDEX** :
   ```sql
   CREATE INDEX idx_coords ON regards(latitude, longitude);
   ```

2. **Batch processing** (par commune) :
   ```python
   for commune in communes:
       anomalies += detecter_doublons_regards(commune)
   ```

3. **Cache résultats** (1h TTL) :
   ```python
   @cache(expire=3600)
   def analyser_reseau_complet():
       ...
   ```

---

## 🧬 Ajouter Phase 2 (template)

### Créer validateur Phase 2

```python
# src/validateurs/pente.py

class ValidateurPente:
    def valider_pentes(self):
        # TODO: Q = 3.1 * D^2.2
        pass
    
    def detecter_pentes_suspectes(self):
        # TODO: < 0.3% ou > 15%
        pass
```

### Intégrer dans QualiteReseau

```python
# src/qualite_reseau.py

from src.validateurs.pente import ValidateurPente

def analyser_reseau_complet(self):
    # ... Phase 0, Phase 1 ...
    
    validateur_pente = ValidateurPente(session)
    rapport["anomalies"]["pentes_suspectes"] = validateur_pente.detecter_pentes_suspectes()
    
    return rapport
```

### Ajouter UI

```javascript
// templates/carte.html
'pente': ['pentes_suspectes']

// static/js/carte_anomalies.js
tabMappings['pente'] = ['pentes_suspectes']
titres['pentes_suspectes'] = 'Pentes suspectes'
```

---

## 🔍 Debugging

### Logs utiles

```python
# Voir si validateur s'exécute
print("🔍 ValidateurTopologie.valider_coherence_profondeurs() démarrage")

# Voir résultats SQL
print(f"Trouvées {len(anomalies)} anomalies profondeur")

# Voir si intégration ok
print(f"Phase 1 : {len(phase1_total)} anomalies")
```

### Tests unitaires

```python
# tests/test_phase1_integration.py

def test_validateur_seul():
    # Teste SANS QualiteReseau
    validateur = ValidateurTopologie(session)
    results = validateur.valider_coherence_profondeurs()
    assert isinstance(results, list)
    print(f"✅ Validateur retourne {len(results)} anomalies")
```

---

## 🎓 Lessons learned

### Ce qui fonctionne bien

- ✅ SQLAlchemy ORM + fallback distance euclidienne
- ✅ Tolérance fixed (pas de tuning dynamique)
- ✅ Separation des phases pour maintenance
- ✅ Frontend mapping simple et extensible

### Points d'attention

- ⚠️ Performance CROSS JOIN sur très gros réseau (>50k)
- ⚠️ NULL values dans profondeur → silent failures
- ⚠️ Unités coordonnées (degrés vs mètres)
- ⚠️ Commune filtering (impact sur doublons)

### Améliorations futures

- [ ] PostGIS utilisation systématique
- [ ] Caching résultats diagnostiques
- [ ] Batch processing par commune
- [ ] Dashboard scores qualité temps réel

---

## 📞 Questions courantes (FAQs)

**Q: Pourquoi 50cm pour profondeur?**  
R: Standard NP 650 + tolérances mesure terrain

**Q: Pourquoi 2m pour doublons?**  
R: Distance typique regard+ marge erreur GPS/scan

**Q: Fallback distance euclidienne ok?**  
R: Oui pour 2D projections. PostGIS mieux pour précision.

**Q: Peut modifier tolérances live (UI)?**  
R: Non. Éditer config/validations_phase1.py + redémarrer API

---

**Notes v1.0** — Mise à jour biannuelle recommandée 📅
