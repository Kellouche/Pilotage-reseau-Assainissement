# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : Audit et préparation de la migration des résultats historiques (3C.5).

STRICTEMENT LECTURE SEULE : ce module n'écrit JAMAIS — aucun appel à
ResultStore.save/replace, aucune mutation SQL, aucun déplacement de fichier.
Le store sous-jacent est encapsulé dans `_StoreLectureSeule` qui refuse
explicitement toute méthode d'écriture : toute tentative fait échouer
l'audit bruyamment au lieu de corrompre silencieusement une donnée.

Produit pour chaque simulation historique :
  - identité (org/projet/simulation), type d'exécution (sync/celery/inconnu),
  - emplacement et format historiques, artefacts détectés (tailles, SHA-256),
  - ResultRef candidate, classe A–G, décision de migration proposée.
================================================================================
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger("swmm_platform.services.audit_migration_resultats")


# ---------------------------------------------------------------------------
# Store lecture seule — barrière physique contre toute écriture
# ---------------------------------------------------------------------------

class _StoreLectureSeule:
    """
    Proxy ArtifactStore n'exposant QUE les lectures. Toute méthode
    d'écriture/suppression lève StoreWriteForbidden : le dry-run ne peut
    structurellement pas modifier une donnée.
    """

    _ECRITURES = ("put_bytes", "put_file", "put_bytes_if_absent",
                  "put_file_if_absent", "delete", "delete_prefix")

    def __init__(self, store: Any):
        object.__setattr__(self, "_store", store)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._store, name)

    def _refuser(self, *args: Any, **kwargs: Any) -> Any:
        raise StoreWriteForbidden(
            f"Écriture interdite pendant l'audit 3C.5 : {self._appelant()}")

    @staticmethod
    def _appelant() -> str:
        import inspect
        try:
            return inspect.stack()[2].function
        except Exception:
            return "?"

    def __init_subclass__(cls, **kwargs):
        raise TypeError("_StoreLectureSeule ne doit pas être sous-classée")


for _nom in _StoreLectureSeule._ECRITURES:
    setattr(_StoreLectureSeule, _nom,
            lambda self, *a, __n=_nom, **k: self._refuser(*a, **k))


class StoreWriteForbidden(RuntimeError):
    """Tentative d'écriture sur le store encapsulé en lecture seule."""


# ---------------------------------------------------------------------------
# Classification et décision
# ---------------------------------------------------------------------------

# Classes : A complet / B partiel / C identité incomplète /
#           D référence introuvable / E corrompu / F ambigu / G provenance.
CLASSES = ("A", "B", "C", "D", "E", "F", "G")

DECISION_PAR_CLASSE = {
    "A": "migration_automatique",
    "B": "validation_humaine",
    "C": "non_migrable_identite",
    "D": "non_migrable_reference",
    "E": "non_migrable_corrompu",
    "F": "validation_humaine",   # ambiguïté : JAMAIS automatique
    "G": "exclu_provenance",
}

_PROVENANCES_INCertaines = {"SYNTHETIC", "FAKE", "MOCK", "TEST", "INCONNUE", None}


def _sha256_octets(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _lire_json_local(chemin: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _lire_json_store(store: Any, cle: str) -> Optional[Dict[str, Any]]:
    try:
        brut = store.get_bytes(cle)
        data = json.loads(brut.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _est_cle_store(cle: str) -> bool:
    """Clé ArtifactStore conventionnelle : relative, partitionnée, simulations/."""
    return (not Path(cle).is_absolute()) and "simulations/" in cle


def _provenance_incertaine(data: Dict[str, Any]) -> bool:
    prov = data.get("provenance")
    if prov is None:
        return True  # absence de provenance = incertaine pour la migration
    if isinstance(prov, dict):
        nature = str(prov.get("nature", prov.get("type", ""))).upper()
        return nature in _PROVENANCES_INCertaines or not nature
    return True


def _meta_contredit(data: Dict[str, Any], sim: Any, proj: Any) -> bool:
    """Estampilles déclarées dans le JSON contradictoires avec la ligne/projet."""
    meta = data.get("meta") or {}
    pid = meta.get("project_id") or data.get("project_id")
    oid = meta.get("org_id") or data.get("org_id")
    if pid and proj is not None and str(pid) != str(proj.id):
        return True
    org_attendu = getattr(proj, "org_id", None) or getattr(sim, "org_id", None)
    if oid and org_attendu and str(oid) != str(org_attendu):
        return True
    return False


def _artefacts_celery(manquants: List[str], store: Any, org_id: str,
                      project_id: str, job_id: str) -> Dict[str, Any]:
    """Vérifie la présence des artefacts Celery attendus (lecture seule)."""
    base = f"{org_id}/{project_id}/simulations/{job_id}"
    cles = {
        "summary.json": f"{base}/summary.json",
        "report.rpt": f"{base}/report.rpt",
        "model.inp": f"{org_id}/{project_id}/swmm/model_{job_id}.inp",
    }
    trouves = {}
    for nom, cle in cles.items():
        try:
            trouves[nom] = {"key": cle, "present": bool(store.exists(cle))}
        except Exception as e:
            trouves[nom] = {"key": cle, "present": False, "erreur": str(e)}
    manquants.extend(nom for nom, v in trouves.items() if not v["present"])
    return trouves


def auditer_simulation(sim: Any, db: Session, store: Any,
                       projets: Dict[str, Any],
                       organisations: Dict[str, Any]) -> Dict[str, Any]:
    """
    Audite UNE ligne Simulation sans rien écrire. Retourne le rapport
    de classification (clés du lot 3C.5 §7).
    """
    from api.services.simulation_service import est_simulation_valide

    rapport: Dict[str, Any] = {
        "simulation_id": getattr(sim, "id", None),
        "org_id": getattr(sim, "org_id", None),
        "project_id": getattr(sim, "project_id", None),
        "statut": getattr(sim, "status", None),
        "results_s3_key": getattr(sim, "results_s3_key", None),
        "type_execution": "inconnu",
        "format_historique": None,
        "emplacement_historique": None,
        "artefacts": {},
        "ref_candidate": None,
        "classe": None,
        "decision": None,
        "motifs": [],
    }

    org_id = getattr(sim, "org_id", None)
    project_id = getattr(sim, "project_id", None)
    sim_id = getattr(sim, "id", None)
    cle = getattr(sim, "results_s3_key", None)
    proj = projets.get(str(project_id)) if project_id else None
    org = organisations.get(str(org_id)) if org_id else None

    # --- C. Identité incomplète -------------------------------------------
    identite_complete = bool(org_id and project_id and sim_id)
    if identite_complete and (proj is None or (org_id and org is None)):
        identite_complete = False
        rapport["motifs"].append("reference_fk_absente")
    if not identite_complete:
        rapport["classe"] = "C"
        rapport["decision"] = DECISION_PAR_CLASSE["C"]
        rapport["motifs"].append("identite_incomplete")
        return rapport

    rapport["ref_candidate"] = {
        "org_id": str(org_id), "project_id": str(project_id),
        "simulation_id": str(sim_id)}

    # --- Localisation du contenu ------------------------------------------
    data: Optional[Dict[str, Any]] = None
    brut: Optional[bytes] = None
    emplacement = None
    if cle:
        cle = str(cle)
        p = Path(cle)
        if p.exists() and p.is_file():
            rapport["type_execution"] = "sync"
            rapport["format_historique"] = "json_complet_cache"
            emplacement = str(p)
            try:
                brut = p.read_bytes()
            except Exception as e:
                rapport["motifs"].append(f"lecture_locale:{e}")
                brut = None
            data = _lire_json_local(p)
        elif _est_cle_store(cle):
            rapport["type_execution"] = "celery"
            rapport["format_historique"] = "summary_json_kpis"
            emplacement = f"store:{cle}"
            try:
                brut = store.get_bytes(cle)
            except Exception as e:
                rapport["motifs"].append(f"store:{e}")
                brut = None
            data = _lire_json_store(store, cle) if brut is not None else None
        else:
            # Chemin relatif ou clé non conventionnelle : tenter le store
            try:
                brut = store.get_bytes(cle)
                data = json.loads(brut.decode("utf-8"))
                if not isinstance(data, dict):
                    data = None
                rapport["type_execution"] = "store_autre"
                rapport["format_historique"] = "cle_store"
                emplacement = f"store:{cle}"
            except Exception:
                pass

    rapport["emplacement_historique"] = emplacement

    # --- D. Référence introuvable ------------------------------------------
    if brut is None:
        rapport["classe"] = "D"
        rapport["decision"] = DECISION_PAR_CLASSE["D"]
        rapport["motifs"].append("reference_introuvable")
        return rapport

    rapport["artefacts"]["result_source"] = {
        "key_ou_chemin": emplacement, "size": len(brut),
        "sha256": _sha256_octets(brut)}

    # --- E. Corrompu / invalide --------------------------------------------
    if data is None:
        rapport["classe"] = "E"
        rapport["decision"] = DECISION_PAR_CLASSE["E"]
        rapport["motifs"].append("json_illisible_ou_non_dict")
        return rapport
    if not est_simulation_valide(data):
        # Tolérance Celery : summary.json ne contient que des KPIs
        if rapport["type_execution"] == "celery" and data:
            pass
        else:
            rapport["classe"] = "E"
            rapport["decision"] = DECISION_PAR_CLASSE["E"]
            rapport["motifs"].append("resultat_invalide")
            return rapport

    # --- F. Ambiguïté de propriété ------------------------------------------
    if _meta_contredit(data, sim, proj):
        rapport["classe"] = "F"
        rapport["decision"] = DECISION_PAR_CLASSE["F"]
        rapport["motifs"].append("estampille_project_ou_org_contradictoire")
        return rapport

    # --- G. Provenance incertaine -------------------------------------------
    if _provenance_incertaine(data):
        rapport["classe"] = "G"
        rapport["decision"] = DECISION_PAR_CLASSE["G"]
        rapport["motifs"].append("provenance_absente_ou_synthetique")
        return rapport

    # --- Complétude des artefacts attendus ----------------------------------
    manquants: List[str] = []
    if rapport["type_execution"] == "celery":
        rapport["artefacts"]["attendus"] = _artefacts_celery(
            manquants, store, str(org_id), str(project_id), str(sim_id))
    else:
        for champ, nom in (("inp_content", "model.inp"),
                           ("rpt_content", "report.rpt")):
            present = bool(data.get(champ))
            rapport["artefacts"][nom] = {"present": present,
                                         "embarque": True}
            if not present:
                manquants.append(nom)
    rapport["artefacts"]["manquants"] = manquants

    # --- A / B ---------------------------------------------------------------
    rapport["classe"] = "B" if manquants else "A"
    rapport["decision"] = DECISION_PAR_CLASSE[rapport["classe"]]
    if manquants:
        rapport["motifs"].append("artefacts_optionnels_manquants:" +
                                 ",".join(manquants))
    return rapport


def _index_models(db: Session):
    from api.models import Organization, Project
    projets = {str(p.id): p for p in db.query(Project).all()}
    organisations = {str(o.id): o for o in db.query(Organization).all()}
    return projets, organisations


def auditer_base(db: Session, store: Any = None,
                 limite: Optional[int] = None) -> Dict[str, Any]:
    """
    Inventaire complet et classification de toutes les simulations.
    `store` : ArtifactStore (ou lecture seule) pour les clés Celery ;
    par défaut get_storage() encapsulé en lecture seule.
    """
    from api.models import Simulation
    from api.core.storage import get_storage

    if store is None:
        store = _StoreLectureSeule(get_storage())
    elif not isinstance(store, _StoreLectureSeule):
        store = _StoreLectureSeule(store)

    projets, organisations = _index_models(db)
    query = db.query(Simulation).order_by(Simulation.created_at)
    if limite:
        query = query.limit(limite)
    sims = query.all()

    rapports = [auditer_simulation(s, db, store, projets, organisations)
                for s in sims]

    par_classe: Dict[str, int] = {c: 0 for c in CLASSES}
    par_type: Dict[str, int] = {}
    par_decision: Dict[str, int] = {}
    cles_dupliquees: Dict[str, List[str]] = {}
    for r in rapports:
        par_classe[r["classe"]] += 1
        par_type[r["type_execution"]] = par_type.get(r["type_execution"], 0) + 1
        par_decision[r["decision"]] = par_decision.get(r["decision"], 0) + 1
        cle = r.get("results_s3_key")
        if cle:
            cles_dupliquees.setdefault(str(cle), []).append(r["simulation_id"])
    cles_partagees = {k: v for k, v in cles_dupliquees.items() if len(v) > 1}

    return {
        "total_simulations": len(rapports),
        "par_classe": par_classe,
        "par_type_execution": par_type,
        "par_decision": par_decision,
        "cles_resultats_partagees": cles_partagees,
        "simulations": rapports,
    }


def inventorient_fichiers_cache(dossiers: List[Path]) -> List[str]:
    """
    Inventorie les fichiers sim_*.json des caches de calcul (lecture seule).
    Utilisé pour repérer les résultats orphelins (non référencés en DB).
    """
    trouves: List[str] = []
    for dossier in dossiers:
        d = Path(dossier)
        if d.exists():
            trouves.extend(str(p) for p in sorted(d.glob("sim_*.json")))
    return trouves
