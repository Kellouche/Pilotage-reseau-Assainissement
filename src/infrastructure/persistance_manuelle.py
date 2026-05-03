import json
import os
from pathlib import Path

DATA_DIR = Path("data")
OVERRIDES_FILE = DATA_DIR / "manual_overrides.json"

def initialiser_stockage():
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True)
    if not OVERRIDES_FILE.exists():
        with open(OVERRIDES_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)

def sauvegarder_bassin_manuel(data):
    initialiser_stockage()
    with open(OVERRIDES_FILE, "r", encoding="utf-8") as f:
        overrides = json.load(f)
    
    # Ajouter un ID unique
    data["id"] = len(overrides) + 1
    overrides.append(data)
    
    with open(OVERRIDES_FILE, "w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=4, ensure_ascii=False)
    return data

def charger_bassins_manuels():
    if not OVERRIDES_FILE.exists():
        return []
    try:
        with open(OVERRIDES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def supprimer_bassin_manuel(bassin_id):
    """Supprime un bassin par son ID (peut être 'M_1' ou 1)."""
    if isinstance(bassin_id, str) and bassin_id.startswith("M_"):
        bassin_id = int(bassin_id.split("_")[1])
    
    overrides = charger_bassins_manuels()
    new_overrides = [b for b in overrides if b.get("id") != int(bassin_id)]
    
    with open(OVERRIDES_FILE, "w", encoding="utf-8") as f:
        json.dump(new_overrides, f, indent=4, ensure_ascii=False)
    return True
