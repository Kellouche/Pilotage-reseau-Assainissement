"""
Configuration des validations topologiques - Phase 1
Seuils hydrauliques et paramètres de tolérance
"""

# Paramètres hydrauliques critiques
VALIDATIONS_TOPOLOGIE = {
    "coherence_profondeurs": {
        "tolerance_cm": 50,  # 50cm d'écart autorisé
        "severite": "majeure",
        "description": "Valide la continuité des profondeurs entre conduites et nœuds",
        "impact": "Directe sur l'écoulement"
    },
    
    "chevauchement_geometrique": {
        "tolerance_distance_m": 0.01,  # 1cm de distance minimum
        "severite": "majeure",
        "description": "Détecte les conduites qui se croisent sans nœud",
        "impact": "Topologie invalide, écoulement bloqué"
    },
    
    "doublon_regards": {
        "distance_max_m": 2.0,  # Doublons à moins de 2m
        "severite": "mineure",
        "description": "Détecte les regards redondants (candidates fusion)",
        "impact": "Redondance, maintenance difficile"
    }
}

# Niveaux de sévérité
SEVERITES = {
    "critique": {
        "couleur": "#e74c3c",  # Rouge vif
        "icone": "🔴",
        "description": "Erreur critique - réseau non fonctionnel"
    },
    "majeure": {
        "couleur": "#e67e22",  # Orange
        "icone": "🟠",
        "description": "Anomalie majeure - impact hydraulique direct"
    },
    "mineure": {
        "couleur": "#2ecc71",  # Vert
        "icone": "🟢",
        "description": "Anomalie mineure - optimisation recommandée"
    }
}

# Messages utilisateur (UI professionnelle)
MESSAGES_DIAGNOSTIC = {
    "incoherence_profondeur_topologie": {
        "titre": "🔧 Dénivellation excessive",
        "description": "La profondeur de fin de conduite ne correspond pas à celle du nœud de connexion",
        "solution": "Corrigez les profondeurs pour respecter une tolérance de ±50cm",
        "icone": "⚠️"
    },
    
    "chevauchement_geometrique": {
        "titre": "🌐 Chevauchement géométrique",
        "description": "Deux conduites se croisent sans nœud d'intersection",
        "solution": "Créez un nœud d'intersection ou redressez les tracés",
        "icone": "⚠️"
    },
    
    "doublon_regards": {
        "titre": "👥 Doublons regards",
        "description": "Deux regards identiques à proximité (<2m)",
        "solution": "Fusionnez les regards ou conservez le plus fonctionnel",
        "icone": "ℹ️"
    }
}

# Thresholds pour score qualité
SCORE_QUALITE_POIDS = {
    "incoherence_profondeur_topologie": 8,  # Très important
    "chevauchement_geometrique": 10,        # Critique
    "doublon_regards": 2,                   # Peu important
}

# Queries SQL optimisées
SQL_QUERIES = {
    "coherence_profondeurs": """
    SELECT 
        c.id, c.fid, c.id_aval,
        c.prof_fe_av, r.profondeur
    FROM conduites c
    LEFT JOIN regards r ON r.code::text = c.id_aval::text
    WHERE c.prof_fe_av IS NOT NULL
      AND r.profondeur IS NOT NULL
    """,
    
    "doublons_regards": """
    SELECT 
        r1.id as id1, r1.code as code1,
        r2.id as id2, r2.code as code2,
        r1.latitude, r1.longitude,
        r2.latitude, r2.longitude
    FROM regards r1
    CROSS JOIN regards r2
    WHERE r1.id < r2.id
      AND r1.commune = r2.commune
      AND r1.latitude IS NOT NULL
      AND r1.longitude IS NOT NULL
    """
}
