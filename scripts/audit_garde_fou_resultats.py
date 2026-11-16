#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : Audit automatique du garde-fou hydraulicien sur les simulations
       existantes — ré-évalue chaque résultat persisté avec la version
       courante de l'agent (nouvelles détections altimétrie : profondeur
       confondue avec cote, sentinelle 100.0) et met à jour les verdicts
       de fiabilité en base (summary_kpis) ainsi que dans les artefacts
       JSON locaux lorsqu'ils sont la source résolue.

Usage : .venv\\Scripts\\python scripts\\audit_garde_fou_resultats.py [--apply]
       Sans --apply : simulation à blanc (rapport seul, aucune écriture).
================================================================================
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.database import SessionLocal
from api.models import Simulation
from api.services.simulation_service import charger_resultat_simulation
from src.domain.agents_expertise.agent_hydraulicien_garde_fou import (
    AgentHydraulicienGardeFou,
)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger("audit_garde_fou")

SEVERITE_RANG = {"SAIN": 0, "A_VERIFIER": 1, "DEGRADE": 2}


def _persister_resultat(sim, data: dict) -> bool:
    """Réécrit le JSON de résultat là où il a été lu (cache local prioritaire)."""
    cle = getattr(sim, "results_s3_key", None)
    if cle:
        p = Path(str(cle))
        try:
            if p.exists() and p.is_file():
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                return True
        except Exception as e:
            logger.warning("Réécriture impossible %s : %s", p, e)
            return False
    # Repli ResultStore pour les sims sans fichier local
    try:
        from api.services.result_store import (
            ArtifactKind, ResultNotFound, ResultRef, ResultStore,
        )
        ref = ResultRef.depuis_simulation(sim)
        if ref is not None:
            ResultStore().save(ref, data, ArtifactKind.RESULT_JSON)
            return True
    except ResultNotFound:
        pass
    except Exception as e:
        logger.warning("ResultStore save impossible (%s) : %s",
                       getattr(sim, "id", "?"), e)
    return False


def main() -> int:
    apply_changes = "--apply" in sys.argv
    db = SessionLocal()
    agent = AgentHydraulicienGardeFou()

    sims = (db.query(Simulation)
            .filter(Simulation.status == "completed")
            .order_by(Simulation.created_at.desc())
            .all())

    stats = {"total": 0, "charges": 0, "modifies": 0, "degrades": 0,
             "erreurs": 0, "deja_ko": 0}
    details = []

    for sim in sims:
        stats["total"] += 1
        sid = getattr(sim, "id", "?")
        try:
            data = charger_resultat_simulation(sim)
        except Exception as e:
            logger.warning("Chargement impossible %s : %s", sid, e)
            stats["erreurs"] += 1
            continue
        if not isinstance(data, dict) or not data:
            stats["erreurs"] += 1
            continue
        stats["charges"] += 1

        try:
            # Config garde-fou du projet propriétaire (sinon défauts)
            _proj = getattr(sim, "project", None)
            _cfg = getattr(_proj, "garde_fou_config", None)
            gf = agent.analyser(data, config=_cfg)
        except Exception as e:
            logger.warning("Garde-fou en échec %s : %s", sid, e)
            stats["erreurs"] += 1
            continue

        ancien = ((data.get("agents_expertise") or {})
                  .get("controle_modele_hydraulique") or {})
        v_ancien = ancien.get("fiabilite_modele")
        v_nouveau = gf.get("fiabilite_modele")
        n_ancien = ancien.get("nb_anomalies", 0)
        n_nouveau = gf.get("nb_anomalies", 0)

        if v_nouveau == v_ancien and n_nouveau == n_ancien:
            if v_nouveau == "DEGRADE":
                stats["deja_ko"] += 1
            continue

        stats["modifies"] += 1
        if SEVERITE_RANG.get(v_nouveau, 0) > SEVERITE_RANG.get(v_ancien or "SAIN", 0):
            stats["degrades"] += 1

        codes = [a.get("code") for a in (gf.get("anomalies") or [])]
        details.append({
            "simulation": sid,
            "bassin": ((data.get("meta") or {}).get("bassin_nom")
                       or (data.get("meta") or {}).get("cluster_nom")
                       or sim.name),
            "avant": v_ancien or "(absent)",
            "apres": v_nouveau,
            "anomalies": codes,
        })

        if not apply_changes:
            continue

        # 1. Verdict corrigé dans le résultat persisté (traçabilité conservée)
        data.setdefault("agents_expertise", {})["controle_modele_hydraulique"] = {
            **gf,
            "audit_automatique": {
                "date": datetime.now(timezone.utc).isoformat(),
                "motif": "garde_fou_v2_altimetrie",
                "verdict_precedent": v_ancien,
            },
        }
        _persister_resultat(sim, data)

        # 2. Verdict dans summary_kpis (badges listes / historique)
        kpis = dict(sim.summary_kpis or {})
        kpis["fiabilite_modele"] = v_nouveau
        kpis["fiabilite_anomalies"] = n_nouveau
        kpis["audit_garde_fou"] = {
            "date": datetime.now(timezone.utc).isoformat(),
            "verdict_precedent": v_ancien,
            "anomalies": codes,
        }
        sim.summary_kpis = kpis

    if apply_changes:
        db.commit()

    mode = "APPLIQUÉ" if apply_changes else "SIMULATION À BLANC"
    print(f"\n=== AUDIT GARDE-FOU — {mode} ===")
    print(f"Simulations complétées : {stats['total']}")
    print(f"Résultats chargés        : {stats['charges']}")
    print(f"Verdicts à mettre à jour : {stats['modifies']}")
    print(f"Dégradations de verdict  : {stats['degrades']}")
    print(f"Déjà dégradées           : {stats['deja_ko']}")
    print(f"Erreurs de lecture       : {stats['erreurs']}")

    for d in details:
        print(f"  {d['simulation'][:8]}… {str(d['bassin'])[:38]:38} "
              f"{d['avant']:>10} -> {d['apres']:<10} {','.join(d['anomalies'])}")

    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
