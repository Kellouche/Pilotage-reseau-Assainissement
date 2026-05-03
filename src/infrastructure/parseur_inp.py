#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parseur de fichier .inp SWMM.
Extrait les comptes : tronçons (conduites), regards (junctions),
stations de relevage (pumping stations), STEP (WWTP), ouvrages (outfalls/structures).
"""

import re
from pathlib import Path
from typing import Dict, Optional


def parse_inp(filepath: str) -> Dict[str, int]:
    """Parse un fichier .inp SWMM et retourne les comptes par type."""
    counts = {
        "troncons": 0,      # [CONDUITS] section
        "regards": 0,       # [JUNCTIONS] section (nœuds hydrauliques)
        "stations": 0,      # [PUMPS] section (stations de pompage)
        "step": 0,          # [OUTFALLS] avec traitement? ou [WWTPS] si présent
        "ouvrages": 0       # [OUTFALLS] (exutoires simples)
    }
    
    path = Path(filepath)
    if not path.exists():
        print(f"[WARN] Fichier .inp non trouvé: {filepath}")
        return counts
    
    current_section = None
    
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(';'):
                continue
            
            # Détection de sections
            if line.startswith('[') and line.endswith(']'):
                current_section = line.upper()
                continue
            
            # Compter selon section
            if current_section == '[CONDUITS]':
                # Ignorer la ligne d'en-tête (sous-section)
                if re.match(r'^\s*Name\s*', line, re.IGNORECASE):
                    continue
                counts["troncons"] += 1
            
            elif current_section == '[JUNCTIONS]':
                if re.match(r'^\s*Name\s*', line, re.IGNORECASE):
                    continue
                counts["regards"] += 1
            
            elif current_section == '[PUMPS]':
                if re.match(r'^\s*Name\s*', line, re.IGNORECASE):
                    continue
                counts["stations"] += 1
            
            elif current_section == '[OUTFALLS]':
                if re.match(r'^\s*Name\s*', line, re.IGNORECASE):
                    continue
                # Différencier STEP vs Ouvrage simple
                # Habituellement STEP a "TREATMENT" dans les paramètres ou nom spécifique
                # On compte tout comme ouvrage par défaut; STEP peut être déduit par nom
                counts["ouvrages"] += 1
            
            elif current_section == '[WWTPS]':  # Sectionoptionnelle pour STEP
                if re.match(r'^\s*Name\s*', line, re.IGNORECASE):
                    continue
                counts["step"] += 1
    
    # NOTE: dans SWMM, les STEP sont souvent dans [OUTFALLS] avec un flag traitement
    # On ne peut pas distinguer sans analyser les paramètres. Pour le POC, on suppose
    # que les stations d'épuration sont dans [OUTFALLS] et identifiées par nom.
    # Une approche plus fine : lire les paramètres de chaque OUTFALL
    return counts


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python parseur_inp.py <fichier.inp>")
        sys.exit(1)
    
    result = parse_inp(sys.argv[1])
    print("Compteurs SWMM:")
    for k, v in result.items():
        print(f"  {k}: {v}")
