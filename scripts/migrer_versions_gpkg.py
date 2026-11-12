# -*- coding: utf-8 -*-
"""
MIGRATION CONTRÔLÉE — versions immuables des GPKG existants (étape 3B).

Pour chaque projet possédant un GeoPackage résolvable :
  1. copie la source vers un fichier temporaire de staging ;
  2. valide le staging (quick_check, couches requises) ;
  3. enregistre la version — SHA-256 calculé sur la copie validée stockée,
     JAMAIS sur le fichier source susceptible d'être modifié ;
  4. met à jour project.gpkg_version_id.

SÉCURITÉS :
  - dry-run par défaut ; écriture uniquement avec --apply ;
  - idempotent : (project_id, sha256) déduplique, aucun doublon ;
  - aucune suppression/déplacement du GPKG source ;
  - simulations historiques NON rattachées (gpkg_version_id reste NULL) ;
  - projet sans GPKG ou GPKG invalide : ignoré + diagnostic.

Usage :
  .venv\\Scripts\\python scripts\\migrer_versions_gpkg.py            # dry-run
  .venv\\Scripts\\python scripts\\migrer_versions_gpkg.py --apply    # écrit
  .venv\\Scripts\\python scripts\\migrer_versions_gpkg.py --json
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from sqlalchemy import select  # noqa: E402
from api.database import SessionLocal  # noqa: E402
from api.models import Project, GpkgVersion, Simulation  # noqa: E402
from api.services.gpkg_versions import (  # noqa: E402
    enregistrer_version_gpkg,
    valider_gpkg,
    sha256_fichier,
    GpkgInvalide,
)


def migrer_projet(db, project: Project, apply: bool) -> Dict[str, Any]:
    rapport: Dict[str, Any] = {
        "project_id": project.id,
        "project_name": project.name,
        "source_gpkg_key": project.source_gpkg_key,
        "actions": [],
        "erreurs": [],
        "dry_run": not apply,
    }

    if getattr(project, "gpkg_version_id", None):
        version = db.get(GpkgVersion, project.gpkg_version_id)
        rapport["actions"].append({
            "action": "DEJA_VERSIONNE",
            "version_id": project.gpkg_version_id,
            "sha256": version.sha256 if version else None,
            "size_bytes": version.size_bytes if version else None,
            "nb_regards": version.nb_regards if version else None,
            "nb_conduites": version.nb_conduites if version else None,
        })
        return rapport

    gpkg_path = Path(project.source_gpkg_key) if project.source_gpkg_key else None
    if not gpkg_path or not gpkg_path.exists():
        rapport["erreurs"].append(f"GPKG introuvable : {project.source_gpkg_key}")
        return rapport

    # 1. Copie de staging : la version est calculée sur la copie validée,
    #    jamais sur la source mutable.
    staging_dir = Path(tempfile.mkdtemp(prefix="gpkg_migration_"))
    staging = staging_dir / gpkg_path.name
    try:
        shutil.copyfile(gpkg_path, staging)

        # 2. Validation
        try:
            meta = valider_gpkg(staging)
        except GpkgInvalide as e:
            rapport["erreurs"].append(f"GPKG invalide : {e}")
            return rapport

        sha_attendu = sha256_fichier(staging)
        taille = staging.stat().st_size

        # Dédup : version déjà existante pour ce projet ?
        existante = db.execute(
            select(GpkgVersion).where(
                GpkgVersion.project_id == project.id,
                GpkgVersion.sha256 == sha_attendu,
            )
        ).scalars().first()

        if existante is not None:
            action = "DEJA_MIGRE"
            version_id = existante.id
        elif not apply:
            action = "CREATION_VERSION (dry-run)"
            version_id = None
        else:
            version = enregistrer_version_gpkg(
                db, project, staging,
                filename_original=gpkg_path.name,
                created_by_id=None,
            )
            version_id = version.id
            action = "CREATION_VERSION"

        rapport["actions"].append({
            "action": action,
            "version_id": version_id,
            "sha256": sha_attendu,
            "size_bytes": taille,
            "nb_regards": meta.get("nb_regards"),
            "nb_conduites": meta.get("nb_conduites"),
        })

        if apply:
            db.commit()
        else:
            db.rollback()
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)

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

        # Statistiques historiques (jamais rétro-attribuées)
        nb_sims = db.query(Simulation).count()
        nb_sims_versionnees = db.query(Simulation).filter(
            Simulation.gpkg_version_id.isnot(None)).count()
    finally:
        db.close()

    if as_json:
        print(json.dumps({"projets": rapports,
                          "simulations_total": nb_sims,
                          "simulations_versionnees": nb_sims_versionnees},
                         indent=2, ensure_ascii=False, default=str))
        return

    mode = "APPLICATION" if apply else "DRY-RUN (aucune écriture — ajouter --apply)"
    print(f"=== MIGRATION versions GPKG — {mode} ===\n")
    for r in rapports:
        print(f"PROJET {r['project_name']} ({r['project_id']})")
        print(f"  source : {r['source_gpkg_key']}")
        for a in r["actions"]:
            print(f"  [{a['action']}] sha256={str(a.get('sha256'))[:16]}… "
                  f"version={a.get('version_id')} "
                  f"({a.get('nb_regards')} regards, {a.get('nb_conduites')} canalisations)")
        for e in r["erreurs"]:
            print(f"  [ERREUR] {e}")
        print()
    print(f"Simulations en base : {nb_sims} | déjà versionnées : {nb_sims_versionnees} "
          f"(les historiques restent NON rattachées par conception)")
    if not apply:
        print("Relancer avec --apply pour écrire en base.")


if __name__ == "__main__":
    main()
