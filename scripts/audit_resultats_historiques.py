# -*- coding: utf-8 -*-
"""
Audit 3C.5 — inventaire et classification des résultats historiques.

STRICTEMENT LECTURE SEULE : n'écrit rien en base, ne déplace ni ne copie
aucun fichier, n'appelle aucune méthode d'écriture du store (barrière
_ShopLectureSeule). Usage :

    .venv\\Scripts\\python scripts/audit_resultats_historiques.py [--json sortie.json]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.database import SessionLocal
from api.services import audit_migration_resultats as audit
from api.services.simulation_service import _repertoire_cache_simulation


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="sortie", default=None,
                    help="Chemin du rapport JSON (optionnel)")
    ap.add_argument("--details", action="store_true",
                    help="Inclure le détail par simulation dans la sortie")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        rapport = audit.auditer_base(db)
        # Inventaire des fichiers de cache orphelins potentiels
        dossiers = [
            _repertoire_cache_simulation(),
            Path("data/.gpkg_cache/.simulation_cache"),
            Path("data/benchmarks/.simulation_cache"),
            Path("uploads"),
        ]
        fichiers = audit.inventorient_fichiers_cache(dossiers)
        cles_referencees = {
            str(s.get("results_s3_key")) for s in rapport["simulations"]
            if s.get("results_s3_key")}
        orphelins = [f for f in fichiers
                     if f not in cles_referencees
                     and Path(f).name not in {
                         Path(c).name for c in cles_referencees}]
        rapport["fichiers_cache"] = {
            "total": len(fichiers),
            "non_references_par_une_simulation": len(orphelins),
            "echantillon_orphelins": orphelins[:10],
        }

        resume = {k: v for k, v in rapport.items() if k != "simulations"}
        print(json.dumps(resume, indent=2, ensure_ascii=False))
        if args.details:
            for s in rapport["simulations"]:
                print(json.dumps(s, ensure_ascii=False))
        if args.sortie:
            sortie = {k: v for k, v in rapport.items()}
            Path(args.sortie).write_text(
                json.dumps(sortie, indent=2, ensure_ascii=False),
                encoding="utf-8")
            print(f"Rapport complet écrit : {args.sortie}", file=sys.stderr)
    finally:
        db.close()


if __name__ == "__main__":
    main()
