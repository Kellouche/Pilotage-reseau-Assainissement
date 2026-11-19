"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-19
Objet : Module de sauvegarde et persistance des corrections manuelles (Multi-Tenant)
================================================================================
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

DATA_DIR = Path("data")
OVERRIDES_DIR = DATA_DIR / "manual_overrides"
OVERRIDES_FILE = DATA_DIR / "manual_overrides.json"


def _resoudre_fichier_overrides(org_id: Optional[str] = None) -> Path:
    """
    Résout le fichier JSON de stockage des bassins manuels :
    - Si org_id est fourni : partitionné sous data/manual_overrides/{org_id}.json
    - Si org_id est None : repli vers OVERRIDES_FILE (legacy / monkeypatch tests)
    """
    if org_id:
        clean_org = "".join(c for c in str(org_id) if c.isalnum() or c in ("-", "_"))
        if clean_org:
            OVERRIDES_DIR.mkdir(parents=True, exist_ok=True)
            return OVERRIDES_DIR / f"{clean_org}.json"
    return OVERRIDES_FILE


def initialiser_stockage(org_id: Optional[str] = None) -> Path:
    target = _resoudre_fichier_overrides(org_id)
    if not target.parent.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        with open(target, "w", encoding="utf-8") as f:
            json.dump([], f)
    return target


def sauvegarder_bassin_manuel(data: Dict[str, Any], org_id: Optional[str] = None) -> Dict[str, Any]:
    target = initialiser_stockage(org_id)
    try:
        with open(target, "r", encoding="utf-8") as f:
            overrides = json.load(f)
    except Exception:
        overrides = []

    # Ajouter un ID unique par organisation
    max_id = max([b.get("id", 0) for b in overrides if isinstance(b.get("id"), int)], default=0)
    data["id"] = max_id + 1
    if org_id:
        data["org_id"] = str(org_id)
    overrides.append(data)

    with open(target, "w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=4, ensure_ascii=False)
    return data


def charger_bassins_manuels(org_id: Optional[str] = None) -> List[Dict[str, Any]]:
    target = _resoudre_fichier_overrides(org_id)
    if not target.exists():
        return []
    try:
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def supprimer_bassin_manuel(bassin_id: Any, org_id: Optional[str] = None) -> bool:
    """Supprime un bassin par son ID (peut être 'M_1' ou 1). Retourne True si trouvé et supprimé, False sinon."""
    if isinstance(bassin_id, str) and bassin_id.startswith("M_"):
        bassin_id = int(bassin_id.split("_")[1])
    try:
        b_id_int = int(bassin_id)
    except (ValueError, TypeError):
        return False

    target = _resoudre_fichier_overrides(org_id)
    overrides = charger_bassins_manuels(org_id)
    new_overrides = [b for b in overrides if b.get("id") != b_id_int]

    if len(new_overrides) == len(overrides):
        return False

    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(new_overrides, f, indent=4, ensure_ascii=False)
    return True
