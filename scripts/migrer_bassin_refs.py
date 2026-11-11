# -*- coding: utf-8 -*-
"""
MIGRATION CONTRÔLÉE — Cluster.bassin_ref (étape 3A).

Pour chaque projet : apparie les bassins du cache GPKG aux clusters ORM et :
  - renseigne `bassin_ref = "exutoire:<node_id>"` sur les clusters existants ;
  - crée les lignes Cluster manquantes (uniquement avec --apply) ;
  - ne touche JAMAIS aux bassins manuels M_x (identifiants instables).

SÉCURITÉS :
  - mode LECTURE SEULE par défaut (dry-run) ; écriture uniquement avec --apply ;
  - idempotent : une seconde exécution ne crée aucun doublon ;
  - abort avec diagnostic si le projet, le GPKG ou l'exutoire est ambigu/absent ;
  - l'index unique (network_id, bassin_ref) garantit l'absence de doublon.

Usage :
  .venv\\Scripts\\python scripts\\migrer_bassin_refs.py            # dry-run
  .venv\\Scripts\\python scripts\\migrer_bassin_refs.py --apply    # écrit en base
  .venv\\Scripts\\python scripts\\migrer_bassin_refs.py --json
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402
from api.database import SessionLocal  # noqa: E402
from api.models import Project, Cluster  # noqa: E402

from analyse_bassin_refs import (  # noqa: E402
    _trouver_cache_gpkg,
    _extraire_bassins_geojson,
    _normaliser,
)

PREFIX_EXUTOIRE = "exutoire:"


def _clusters_du_projet(db, project_id: str) -> List[Cluster]:
    return list(
        db.execute(select(Cluster).where(Cluster.network_id == project_id)).scalars().all()
    )


def migrer_projet(db, project: Project, apply: bool) -> Dict[str, Any]:
    """Migre un projet. Retourne le rapport d'actions."""
    rapport: Dict[str, Any] = {
        "project_id": project.id,
        "project_name": project.name,
        "actions": [],
        "erreurs": [],
        "dry_run": not apply,
    }

    gpkg_path = Path(project.source_gpkg_key) if project.source_gpkg_key else None
    if not gpkg_path or not gpkg_path.exists():
        rapport["erreurs"].append(f"GPKG introuvable : {project.source_gpkg_key}")
        return rapport

    cache_path = _trouver_cache_gpkg(gpkg_path)
    if not cache_path:
        rapport["erreurs"].append(f"Cache bassins introuvable pour {gpkg_path.name}")
        return rapport

    bassins = _extraire_bassins_geojson(cache_path)
    clusters = _clusters_du_projet(db, project.id)

    for b in bassins:
        ex_id = b.get("exutoire_id")
        nom = b.get("nom") or f"Bassin {ex_id}"
        if not ex_id:
            rapport["actions"].append({
                "bassin": nom, "action": "IGNORE_SANS_EXUTOIRE",
                "detail": "Pas d'exutoire_id dans le cache GPKG — aucune référence stable possible.",
            })
            continue

        ref = f"{PREFIX_EXUTOIRE}{ex_id}"

        # Candidats ORM : par bassin_ref, exutoire_noeud ou nom (portée projet)
        par_ref = [c for c in clusters if c.bassin_ref == ref]
        par_exo = [c for c in clusters if _normaliser(c.exutoire_noeud) == _normaliser(ex_id)]
        par_nom = [c for c in clusters if _normaliser(c.nom) == _normaliser(nom)]

        if len(par_ref) > 1 or len(par_exo) > 1:
            rapport["erreurs"].append(
                f"AMBIGUïTÉ {ref} : {len(par_ref)} par ref, {len(par_exo)} par exutoire"
            )
            continue

        cible = (par_ref or par_exo or par_nom or [None])[0]

        if cible is not None:
            if not cible.bassin_ref:
                action = "MAJ_BASSIN_REF"
                if apply:
                    cible.bassin_ref = ref
                    if not cible.exutoire_noeud:
                        cible.exutoire_noeud = str(ex_id)
                    if not cible.network_id:
                        cible.network_id = project.id
                    if not cible.org_id:
                        cible.org_id = project.org_id
                rapport["actions"].append({
                    "bassin": nom, "action": action, "cluster_id": cible.id,
                    "bassin_ref": ref,
                })
            elif not cible.exutoire_noeud:
                action = "MAJ_EXUTOIRE_NOEUD"
                if apply:
                    cible.exutoire_noeud = str(ex_id)
                rapport["actions"].append({
                    "bassin": nom, "action": action, "cluster_id": cible.id,
                    "bassin_ref": ref,
                })
            else:
                rapport["actions"].append({
                    "bassin": nom, "action": "DEJA_MIGRE", "cluster_id": cible.id,
                    "bassin_ref": cible.bassin_ref,
                })
            continue

        # Aucun cluster ORM : création contrôlée (dry-run par défaut)
        action = "CREATION_CLUSTER"
        if apply:
            nouveau = Cluster(
                nom=nom,
                exutoire_noeud=str(ex_id),
                bassin_ref=ref,
                network_id=project.id,
                org_id=project.org_id,
            )
            db.add(nouveau)
            db.flush()  # détecte les violations d'unicité avant commit
            clusters.append(nouveau)
            rapport["actions"].append({
                "bassin": nom, "action": action, "cluster_id": nouveau.id,
                "bassin_ref": ref,
            })
        else:
            rapport["actions"].append({
                "bassin": nom, "action": action + " (dry-run)",
                "bassin_ref": ref, "exutoire_noeud": str(ex_id),
            })

    if apply:
        db.commit()
    else:
        db.rollback()

    return rapport


def main() -> None:
    apply = "--apply" in sys.argv
    as_json = "--json" in sys.argv

    db = SessionLocal()
    try:
        projets = list(
            db.execute(select(Project).where(Project.is_archived.is_(False))).scalars().all()
        )
        rapports = [migrer_projet(db, p, apply) for p in projets]
    finally:
        db.close()

    if as_json:
        print(json.dumps(rapports, indent=2, ensure_ascii=False, default=str))
        return

    mode = "APPLICATION" if apply else "DRY-RUN (aucune écriture — ajouter --apply)"
    print(f"=== MIGRATION bassin_ref — {mode} ===\n")
    total_creations = 0
    for r in rapports:
        print(f"PROJET {r['project_name']} ({r['project_id']})")
        for a in r["actions"]:
            print(f"  [{a['action']}] {a.get('bassin')} -> {a.get('bassin_ref', '')}")
            if "CREATION" in a["action"]:
                total_creations += 1
        for e in r["erreurs"]:
            print(f"  [ERREUR] {e}")
        print()
    print(f"Total créations prévues/Effectuées : {total_creations}")
    if not apply:
        print("Relancer avec --apply pour écrire en base.")


if __name__ == "__main__":
    main()
