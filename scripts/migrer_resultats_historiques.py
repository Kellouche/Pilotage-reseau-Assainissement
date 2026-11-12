# -*- coding: utf-8 -*-
"""
Migration contrôlée 3C.6 — résultats historiques classe A → ResultStore.

Périmètre STRICT : uniquement les simulation_id listées ci-dessous
(validées classe A par l'audit 3C.5 et confirmées hors anomalie 3C.5.1).

Pour chaque simulation, les contrôles de l'audit sont REJOUÉS au moment
de l'écriture (jamais de confiance aveugle dans le rapport précédent) :
  1. rechargement ORM + concordance org/project/simulation ;
  2. re-classification live == "A" ;
  3. fichier source existant, lisible, SHA-256 recalculé ;
  4. résultat valide et provenance REAL ;
  5. dépôt via reprise_resultat_simulation (save_idempotent, jamais
     d'écrasement) ;
  6. vérification post-migration : verifier_manifeste == VERIFIED,
     diagnostiquer_resultats_store cohérent, source intacte.

Aucune exécution SWMM, aucune modification de results_s3_key, des
fichiers sources ou du cache. Usage :

    .venv\\Scripts\\python scripts/migrer_resultats_historiques.py [--json rapport.json]
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.database import SessionLocal
from api.models import Organization, Project, Simulation
from api.services import audit_migration_resultats as audit
from api.services import simulation_service as svc
from api.services.result_store import ResultStore

SIMULATIONS_CIBLES = [
    "1f317826-e3b3-4c39-9b84-eaed528d4b74",
    "229f9572-3016-4ab7-abb6-7361c024d86c",
    "14a16ec4-1d62-41bb-ada1-2ddc1de3c3b5",
]


def _sha256_fichier(chemin: Path) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def _controler_prealable(db, sim) -> dict:
    """Rejoue les critères classe A. Retourne {ok, motifs, data, sha_source}."""
    ctrl = {"ok": False, "motifs": [], "data": None, "sha_source": None}
    if sim is None or sim.status != "completed":
        ctrl["motifs"].append("simulation_absente_ou_non_completed")
        return ctrl
    if not (sim.org_id and sim.project_id and sim.id):
        ctrl["motifs"].append("identite_incomplete")
        return ctrl

    # Re-classification live via le moteur d'audit 3C.5
    store_ro = audit._StoreLectureSeule(ResultStore().store)
    projets = {str(p.id): p for p in db.query(Project).all()}
    orgs = {str(o.id): o for o in db.query(Organization).all()}
    r = audit.auditer_simulation(sim, db, store_ro, projets, orgs)
    ctrl["classe_live"] = r["classe"]
    if r["classe"] != "A":
        ctrl["motifs"].append(f"classe_live={r['classe']}")
        return ctrl

    # Source existante et intègre
    cle = sim.results_s3_key
    p = Path(str(cle)) if cle else None
    if not p or not p.exists() or not p.is_file():
        ctrl["motifs"].append("source_introuvable")
        return ctrl
    ctrl["sha_source"] = _sha256_fichier(p)

    data = svc.charger_resultat_simulation(sim)
    if not data or not svc.est_simulation_valide(data):
        ctrl["motifs"].append("resultat_invalide")
        return ctrl
    ctrl["data"] = data
    ctrl["ok"] = True
    return ctrl


def _verifier_post(db, sim, ctrl) -> dict:
    """Vérifications post-migration exigées par le lot."""
    from api.services.result_store import (
        ArtifactKind, ResultRef, ResultStoreError,
    )
    out = {}
    try:
        ref = ResultRef.depuis_simulation(sim)
    except ResultStoreError as e:
        return {"erreur": f"ref: {e}"}
    store = ResultStore()
    verif = store.verifier_manifeste(ref)
    out["verifier_manifeste"] = verif.get("etat")
    try:
        diag = svc.diagnostiquer_resultats_store(sim)
        out["diagnostic"] = {
            "manifeste": diag.get("manifeste"),
            "persistance_complete": diag.get("persistance_complete"),
        }
    except Exception as e:
        out["diagnostic"] = {"erreur": str(e)}
    # SHA-256 des artefacts déposés
    out["artefacts"] = {}
    for kind in (ArtifactKind.RESULT_JSON, ArtifactKind.INP,
                 ArtifactKind.RPT, ArtifactKind.MANIFEST):
        try:
            out["artefacts"][kind.value] = store.verify(ref, kind)["sha256"]
        except Exception:
            out["artefacts"][kind.value] = None
    # Le result.json déposé correspond-il au résultat historique ?
    try:
        depose = store.load_json(ref, ArtifactKind.RESULT_JSON)
        out["result_json_identique"] = (
            json.dumps(depose, sort_keys=True, ensure_ascii=False)
            == json.dumps(ctrl["data"], sort_keys=True, ensure_ascii=False))
    except Exception as e:
        out["result_json_identique"] = f"erreur:{e}"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="sortie", default=None)
    args = ap.parse_args()

    db = SessionLocal()
    lignes = []
    try:
        for sid in SIMULATIONS_CIBLES:
            ligne = {"simulation_id": sid, "statut": "SKIPPED",
                     "anomalies": []}
            sim = db.get(Simulation, sid)
            ctrl = _controler_prealable(db, sim)
            ligne["classe_live"] = ctrl.get("classe_live")
            ligne["sha256_source"] = ctrl.get("sha_source")
            if not ctrl["ok"]:
                ligne["anomalies"] = ctrl["motifs"]
                lignes.append(ligne)
                continue

            source = Path(str(sim.results_s3_key))
            ligne["fichier_source"] = str(source)

            # Dépôt via le mécanisme autorisé — jamais d'écrasement
            statut = svc.reprise_resultat_simulation(sim, ctrl["data"])
            ligne["reprise"] = statut
            post = _verifier_post(db, sim, ctrl)
            ligne["post"] = post

            # Source historique intacte ?
            sha_apres = _sha256_fichier(source)
            ligne["source_intacte"] = (sha_apres == ctrl["sha_source"])
            if not ligne["source_intacte"]:
                ligne["anomalies"].append("source_modifiee!")

            complet = (post.get("verifier_manifeste") == "VERIFIED"
                       and (post.get("diagnostic") or {}).get(
                           "persistance_complete") is True
                       and ligne["source_intacte"])
            anomalies = list(statut.get("anomalies") or [])
            if anomalies:
                ligne["anomalies"].extend(anomalies)
            if statut.get("erreur"):
                ligne["anomalies"].append(statut["erreur"])
            if complet and not anomalies:
                ligne["statut"] = "MIGRATED"
            elif anomalies or str(statut.get("artefacts", {}).get(
                    "result.json", "")).startswith("error"):
                ligne["statut"] = "FAILED"
            else:
                ligne["statut"] = "PARTIAL"
            lignes.append(ligne)
            db.expire(sim)
    finally:
        db.close()

    resume = {
        "cibles": len(SIMULATIONS_CIBLES),
        "migre": sum(1 for l in lignes if l["statut"] == "MIGRATED"),
        "partiel": sum(1 for l in lignes if l["statut"] == "PARTIAL"),
        "echoue": sum(1 for l in lignes if l["statut"] == "FAILED"),
        "ignore": sum(1 for l in lignes if l["statut"] == "SKIPPED"),
    }
    print(json.dumps({"resume": resume, "lignes": lignes},
                     indent=2, ensure_ascii=False))
    if args.sortie:
        Path(args.sortie).write_text(
            json.dumps({"resume": resume, "lignes": lignes},
                       indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
