#!/usr/bin/env python
"""
Test d'intégration Phase 1 - Fondations topologiques
Lance les 3 validations et affiche les résultats

Usage:
    python tests/test_phase1_integration.py
"""

import sys
import os
from pathlib import Path

# Ajouter le répertoire src au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.qualite_reseau import QualiteReseau
from config import settings

def test_phase1_complete():
    """Test complet Phase 1"""
    
    print("=" * 60)
    print("🧪 TEST PHASE 1 — FONDATIONS TOPOLOGIQUES")
    print("=" * 60)
    
    try:
        # Initialiser
        qualite = QualiteReseau(settings.DATABASE_URL)
        
        print("\n✓ Connexion à la base de données établie")
        
        # Lancer diagnostic complet
        print("\n🔍 Lancement diagnostic complet...")
        rapport = qualite.analyser_reseau_complet()
        
        # Afficher résumé Phase 1
        anomalies = rapport.get("anomalies", {})
        
        phase1_types = [
            "incoherence_profondeur_topologie",
            "chevauchement_geometrique",
            "doublon_regards"
        ]
        
        print("\n📊 RÉSULTATS PHASE 1:")
        print("-" * 60)
        
        total_phase1 = 0
        for anomaly_type in phase1_types:
            count = len(anomalies.get(anomaly_type, []))
            total_phase1 += count
            icon = "⚠️ " if count > 0 else "✅"
            print(f"{icon} {anomaly_type:40} : {count:3} anomalie(s)")
        
        print("-" * 60)
        print(f"{'📈 TOTAL PHASE 1':40} : {total_phase1:3} anomalie(s)")
        
        # Afficher quelques exemples
        for anomaly_type in phase1_types:
            anoms = anomalies.get(anomaly_type, [])
            if anoms and len(anoms) > 0:
                print(f"\n📍 Exemple — {anomaly_type}:")
                example = anoms[0]
                print(f"   ID: {example.get('id', 'N/A')}")
                print(f"   Sévérité: {example.get('severite', 'N/A')}")
                print(f"   Description: {example.get('description', 'N/A')[:60]}...")
                if example.get('details'):
                    print(f"   Détails: {example['details']}")
        
        # Score global
        scores = rapport.get("scores_qualite", {})
        print(f"\n📈 Score qualité topologie: {scores.get('topologie', 'N/A')}")
        
        print("\n" + "=" * 60)
        print("✅ TEST PHASE 1 TERMINÉ AVEC SUCCÈS")
        print("=" * 60)
        
        qualite.fermer_connexion()
        return True
        
    except Exception as e:
        print(f"\n❌ ERREUR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_validateur_seul():
    """Test du validateur topologie en isolation"""
    
    print("\n" + "=" * 60)
    print("🔬 TEST VALIDATEUR TOPOLOGIE EN ISOLATION")
    print("=" * 60)
    
    try:
        from src.validateurs.topologie import ValidateurTopologie
        from api.database import SessionLocal
        
        session = SessionLocal()
        validateur = ValidateurTopologie(session)
        
        print("\n✓ Validateur topologie créé")
        
        # Test 1: Cohérence profondeurs
        print("\n🔍 Test 1: Cohérence des profondeurs...")
        anomalies_prof = validateur.valider_coherence_profondeurs()
        print(f"   ✓ Trouvées {len(anomalies_prof)} anomalies")
        
        # Test 2: Chevauchements géométriques
        print("\n🔍 Test 2: Chevauchements géométriques...")
        anomalies_chev = validateur.valider_chevauchements_geometriques()
        print(f"   ✓ Trouvés {len(anomalies_chev)} chevauchements")
        
        # Test 3: Doublons regards
        print("\n🔍 Test 3: Détection doublons regards...")
        anomalies_dbl = validateur.detecter_doublons_regards()
        print(f"   ✓ Trouvés {len(anomalies_dbl)} doublons")
        
        session.close()
        
        print("\n✅ TEST VALIDATEUR RÉUSSI")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ ERREUR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n🚀 DÉMARRAGE TESTS PHASE 1\n")
    
    # Test 1: Validateur seul
    if not test_validateur_seul():
        sys.exit(1)
    
    # Test 2: Intégration complète
    if not test_phase1_complete():
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("🎉 TOUS LES TESTS RÉUSSIS!")
    print("=" * 60)
