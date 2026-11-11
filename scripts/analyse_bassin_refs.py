# -*- coding: utf-8 -*-
"""
ANALYSE LECTURE SEULE — Correspondance Cluster ORM ↔ bassins GPKG (étape 3A).

N'écrit RIEN en base ni sur disque. Produit un rapport classant chaque
correspondance en : CERTAINE / AMBIGUE / IMPOSSIBLE / NON COUVERTE.

Usage : .venv\\Scripts\\python scripts\\analyse_bassin_refs.py [--json]
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


def _normaliser(s: Any) -> str:
    return str(s).strip().lower() if s is not None else ""


def _trouver_cache_gpkg(gpkg_path: Path) -> Optional[Path]:
    """Localise le .clusters_cache.json associée au GPKG (même dossier ou uploads/)."""
    direct = gpkg_path.with_suffix(".clusters_cache.json")
    if direct.exists():
        return direct
    stem = gpkg_path.stem
    for cand in Path("uploads").glob(f"**/*{stem}*.clusters_cache.json"):
        return cand
    return None


def _extraire_bassins_geojson(cache_path: Path) -> List[Dict[str, Any]]:
    """Extrait les bassins (type=bassin_urbain) du cache clusters."""
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    feats = (data.get("bassins_geojson") or {}).get("features", [])
    return [
        {
            "cluster_id": f.get("properties", {}).get("cluster_id"),
            "id_bassin": f.get("properties", {}).get("id_bassin"),
            "exutoire_id": f.get("properties", {}).get("exutoire_id"),
            "nom": f.get("properties", {}).get("nom"),
        }
        for f in feats
        if f.get("properties", {}).get("type") == "bassin_urbain"
    ]


def analyser_projet(db, project: Project) -> Dict[str, Any]:
    """Analyse un projet : bassins GPKG vs clusters ORM."""
    gpkg_path = Path(project.source_gpkg_key) if project.source_gpkg_key else None
    gpkg_ok = bool(gpkg_path and gpkg_path.exists())

    # Clusters ORM rattachés à ce projet (network_id = projects.id)
    orm_clusters = list(
        db.execute(select(Cluster).where(Cluster.network_id == project.id)).scalars().all()
    )
    # + clusters sans network_id mais même org (cas legacy)
    orm_sans_projet = [
        c for c in db.execute(
            select(Cluster).where(Cluster.org_id == project.org_id, Cluster.network_id.is_(None))
        ).scalars().all()
    ]

    bassins: List[Dict[str, Any]] = []
    cache_path = None
    if gpkg_ok:
        cache_path = _trouver_cache_gpkg(gpkg_path)
        if cache_path:
            bassins = _extraire_bassins_geojson(cache_path)

    correspondances: List[Dict[str, Any]] = []
    utilises_orm: set = set()

    for b in bassins:
        ex_id = _normaliser(b.get("exutoire_id"))
        nom = _normaliser(b.get("nom"))
        candidats = []

        # Règle 1 : exutoire_noeud == exutoire_id (pivot stable)
        for c in orm_clusters + orm_sans_projet:
            if ex_id and _normaliser(c.exutoire_noeud) == ex_id:
                candidats.append(("exutoire_noeud", c))
        # Règle 2 : nom exact (uniquement si aucun match exutoire)
        if not candidats and nom:
            for c in orm_clusters + orm_sans_projet:
                if _normaliser(c.nom) == nom:
                    candidats.append(("nom", c))

        if len(candidats) == 1:
            regle, c = candidats[0]
            statut = "CERTAINE" if regle == "exutoire_noeud" else "NOM_UNIQUE"
            correspondances.append({
                "bassin": b, "statut": statut, "regle": regle,
                "cluster_orm_id": c.id, "cluster_nom": c.nom,
                "exutoire_noeud": c.exutoire_noeud,
            })
            utilises_orm.add(c.id)
        elif len(candidats) > 1:
            correspondances.append({
                "bassin": b, "statut": "AMBIGUE",
                "candidats": [(r, c.id, c.nom) for r, c in candidats],
            })
        else:
            correspondances.append({"bassin": b, "statut": "SANS_CLUSTER_ORM"})

    # Clusters ORM non appariés à aucun bassin GPKG
    for c in orm_clusters + orm_sans_projet:
        if c.id not in utilises_orm:
            correspondances.append({
                "statut": "CLUSTER_ORM_SANS_BASSIN",
                "cluster_orm_id": c.id, "cluster_nom": c.nom,
                "exutoire_noeud": c.exutoire_noeud,
                "network_id": c.network_id,
            })

    # Bassins manuels (M_x) — rapportés, jamais persistés (ID instable)
    try:
        from src.infrastructure.persistance_manuelle import charger_bassins_manuels
        manuels = charger_bassins_manuels()
    except Exception:
        manuels = []

    return {
        "project_id": project.id,
        "project_name": project.name,
        "org_id": project.org_id,
        "gpkg_path": str(gpkg_path) if gpkg_path else None,
        "gpkg_existe": gpkg_ok,
        "cache_gpkg": str(cache_path) if cache_path else None,
        "nb_bassins_gpkg": len(bassins),
        "nb_clusters_orm_projet": len(orm_clusters),
        "nb_clusters_orm_sans_projet": len(orm_sans_projet),
        "nb_bassins_manuels": len(manuels),
        "manuels": [
            {"id": m.get("id"), "nom": m.get("nom"), "exutoire": m.get("exutoire")}
            for m in manuels
        ],
        "correspondances": correspondances,
    }


def main() -> None:
    as_json = "--json" in sys.argv
    db = SessionLocal()
    try:
        projets = list(
            db.execute(select(Project).where(Project.is_archived.is_(False))).scalars().all()
        )
        rapports = [analyser_projet(db, p) for p in projets]
    finally:
        db.close()

    if as_json:
        print(json.dumps(rapports, indent=2, ensure_ascii=False, default=str))
        return

    for r in rapports:
        print("=" * 78)
        print(f"PROJET : {r['project_name']}  (id={r['project_id']}, org={r['org_id']})")
        print(f"  GPKG : {r['gpkg_path']}  [existe={r['gpkg_existe']}]")
        print(f"  Cache bassins : {r['cache_gpkg'] or 'ABSENT'}")
        print(f"  Bassins GPKG : {r['nb_bassins_gpkg']} | "
              f"Clusters ORM (projet) : {r['nb_clusters_orm_projet']} | "
              f"(sans projet, même org) : {r['nb_clusters_orm_sans_projet']}")
        if r["manuels"]:
            print(f"  Bassins manuels : {r['nb_bassins_manuels']} -> {r['manuels']}")

        stats = {}
        for c in r["correspondances"]:
            stats[c["statut"]] = stats.get(c["statut"], 0) + 1
        print(f"  Correspondances : {stats}")

        for c in r["correspondances"]:
            if c["statut"] in ("AMBIGUE", "CLUSTER_ORM_SANS_BASSIN"):
                print(f"    [{c['statut']}] {json.dumps(c, ensure_ascii=False, default=str)[:220]}")
            elif c["statut"] == "NOM_UNIQUE":
                b = c["bassin"]
                print(f"    [NOM_UNIQUE] bassin '{b.get('nom')}' (exutoire_id={b.get('exutoire_id')}) "
                      f"-> Cluster ORM #{c['cluster_orm_id']} '{c['cluster_nom']}'")


if __name__ == "__main__":
    main()
