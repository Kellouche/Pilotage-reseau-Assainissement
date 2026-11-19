"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-19
Objet : Script rejouable de partitionnement multi-tenant des bassins manuels
================================================================================
"""

import json
import logging
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("migrate_manual_overrides")

DATA_DIR = Path("data")
LEGACY_FILE = DATA_DIR / "manual_overrides.json"
PARTITION_DIR = DATA_DIR / "manual_overrides"


def migrer_bassins_manuels(default_org_id: str = "default_org") -> int:
    """
    Lit le fichier legacy data/manual_overrides.json et partitionne les bassins
    vers data/manual_overrides/{org_id}.json.
    Si un élément possède déjà une clé 'org_id', elle est respectée.
    Sinon, default_org_id est attribué.
    Retourne le nombre total de bassins partitionnés.
    """
    if not LEGACY_FILE.exists():
        logger.info("Aucun fichier legacy %s trouvé. Rien à migrer.", LEGACY_FILE)
        return 0

    try:
        with open(LEGACY_FILE, "r", encoding="utf-8") as f:
            items = json.load(f)
    except Exception as e:
        logger.error("Impossible de lire %s : %s", LEGACY_FILE, e)
        return 0

    if not isinstance(items, list) or not items:
        logger.info("Fichier legacy %s vide ou ne contenant aucun élément.", LEGACY_FILE)
        return 0

    PARTITION_DIR.mkdir(parents=True, exist_ok=True)

    par_org = {}
    for item in items:
        org = item.get("org_id") or default_org_id
        clean_org = "".join(c for c in str(org) if c.isalnum() or c in ("-", "_")) or default_org_id
        item["org_id"] = clean_org
        par_org.setdefault(clean_org, []).append(item)

    total_migres = 0
    for org, org_items in par_org.items():
        dest_file = PARTITION_DIR / f"{org}.json"
        existant = []
        if dest_file.exists():
            try:
                with open(dest_file, "r", encoding="utf-8") as f:
                    existant = json.load(f)
            except Exception:
                existant = []

        # Fusion sans doublon d'identifiant
        exist_ids = {b.get("id") for b in existant if "id" in b}
        nouveaux = [b for b in org_items if b.get("id") not in exist_ids]
        fusion = existant + nouveaux

        with open(dest_file, "w", encoding="utf-8") as f:
            json.dump(fusion, f, indent=4, ensure_ascii=False)

        total_migres += len(nouveaux)
        logger.info("Organisation %s : %d bassins migrés (total dans %s : %d)", org, len(nouveaux), dest_file.name, len(fusion))

    logger.info("Migration terminée : %d bassins partitionnés dans %s", total_migres, PARTITION_DIR)
    return total_migres


if __name__ == "__main__":
    import sys
    default_org = sys.argv[1] if len(sys.argv) > 1 else "default_org"
    migrer_bassins_manuels(default_org)
