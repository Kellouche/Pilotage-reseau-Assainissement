# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Objet : Service métier unique de simulation hydraulique SWMM.

Orchestre la résolution du projet/GPKG, la préparation du scénario (BMS inclus),
l'appel au moteur EPA SWMM via PySWMM (MoteurSWMM), le cache de résultats et la
persistance. Aucune dépendance à FastAPI, Celery ou Request : ce module est
appelable aussi bien par l'adaptateur HTTP synchrone que par le worker Celery.
================================================================================
"""

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy.orm import Session

logger = logging.getLogger("swmm_platform.services.simulation_service")


class ContexteProjetIntrouvable(Exception):
    """Levée quand aucun GeoPackage exploitable ne peut être résolu pour le tenant."""


@dataclass
class ContexteProjet:
    """Contexte résolu : projet ORM + chemin du GeoPackage (versionné si possible)."""
    project: Any = None
    gpkg_path: Optional[Path] = None
    project_name: Optional[str] = None
    # Étape 3B : métadonnées de la version GPKG capturée pour cette exécution
    version_meta: Optional[Dict[str, Any]] = None


def _resoudre_gpkg_versionne(db: Session, proj: Any):
    """
    Résout le GPKG de simulation pour un projet via le versionnement (3B).
    Retourne (gpkg_path, version_meta) ou (None, meta_erreur).
    Une version existante mais indisponible n'est JAMAIS remplacée
    silencieusement par un autre fichier.
    """
    from api.services.gpkg_versions import resoudre_version_pour_simulation
    return resoudre_version_pour_simulation(db, proj)


def resoudre_contexte_projet(db: Session, org_id: Optional[str]) -> ContexteProjet:
    """
    Résout le projet actif et son GeoPackage source.
    Reproduit fidèlement la logique historique de POST /simulations/run :
    projet du tenant en priorité, puis premier projet non archivé, puis la
    démo data/demo_reseau.gpkg en dernier recours.
    Étape 3B : si le projet a une version GPKG, le chemin retourné est le
    snapshot matérialisé et version_meta décrit la version capturée.
    """
    from api.models import Project

    gpkg_path = None
    project_name = None
    version_meta = None
    proj = None
    if org_id:
        proj = db.query(Project).filter(
            Project.org_id == org_id,
            Project.is_archived.is_(False)
        ).first()
        if proj:
            project_name = proj.name
            chemin, vmeta = _resoudre_gpkg_versionne(db, proj)
            if chemin is not None:
                gpkg_path = Path(chemin)
                version_meta = vmeta
            elif getattr(proj, "gpkg_version_id", None):
                raise ContexteProjetIntrouvable(
                    vmeta.get("erreur", "Version GPKG indisponible pour ce projet.")
                )
            elif proj.source_gpkg_key and Path(proj.source_gpkg_key).exists():
                gpkg_path = Path(proj.source_gpkg_key)

    if not gpkg_path:
        proj = db.query(Project).filter(Project.is_archived.is_(False)).first()
        if proj:
            if not project_name:
                project_name = proj.name
            chemin, vmeta = _resoudre_gpkg_versionne(db, proj)
            if chemin is not None:
                gpkg_path = Path(chemin)
                version_meta = vmeta
            elif getattr(proj, "gpkg_version_id", None):
                raise ContexteProjetIntrouvable(
                    vmeta.get("erreur", "Version GPKG indisponible pour ce projet.")
                )
            elif proj.source_gpkg_key and Path(proj.source_gpkg_key).exists():
                gpkg_path = Path(proj.source_gpkg_key)
        else:
            cand = Path("data/demo_reseau.gpkg")
            if cand.exists():
                gpkg_path = cand
                project_name = "demo_reseau"

    if not gpkg_path or not gpkg_path.exists():
        raise ContexteProjetIntrouvable("Réseau hydraulique introuvable pour ce projet.")

    return ContexteProjet(project=proj, gpkg_path=gpkg_path,
                          project_name=project_name, version_meta=version_meta)


def _sha256_gpkg(gpkg_path: Path) -> Optional[str]:
    """Empreinte SHA-256 complète du contenu GPKG (cache mémoire par mtime/taille)."""
    try:
        if gpkg_path and Path(gpkg_path).exists():
            from api.services.gpkg_versions import sha256_fichier
            return sha256_fichier(Path(gpkg_path), use_cache=True)
    except Exception as e:
        logger.warning("Empreinte SHA-256 GPKG impossible pour %s : %s", gpkg_path, e)
    return None


def _cle_cache_gpkg(gpkg_path: Path) -> str:
    """
    Identité de cache basée sur le CONTENU du GPKG (SHA-256 tronqué),
    jamais sur le chemin : le snapshot matérialisé d'une version et le
    fichier source du projet partagent ainsi le même cache.
    """
    sha = _sha256_gpkg(gpkg_path)
    if sha:
        return sha[:16]
    stem = Path(gpkg_path).stem if gpkg_path else "inconnu"
    return re.sub(r'[^\w\-]+', '_', stem)


def _repertoire_cache_simulation() -> Path:
    """Répertoire unique de cache : data/.simulation_cache (partagé, content-adressé)."""
    from api.services.gpkg_versions import GPKG_CACHE_DIR
    return Path(GPKG_CACHE_DIR).parent / ".simulation_cache"


def iter_fichiers_cache_simulation(gpkg_path: Path):
    """
    Itère les fichiers de cache candidats pour ce GPKG, du plus récent au plus ancien :
    d'abord les entrées content-adressées (SHA-256), puis le legacy
    <gpkg_path.parent>/.simulation_cache (stem historique) pour compatibilité.
    """
    candidats = []
    cle = _cle_cache_gpkg(gpkg_path)
    sha = _sha256_gpkg(gpkg_path)
    dossier = _repertoire_cache_simulation()
    if dossier.exists():
        candidats.extend(dossier.glob(f"sim_{cle}_cluster_*.json"))
        # Fichiers legacy éventuels dans le même dossier (stem d'origine)
        if gpkg_path:
            stem_legacy = re.sub(r'[^\w\-]+', '_', Path(gpkg_path).stem)
            if stem_legacy != cle:
                candidats.extend(dossier.glob(f"sim_{stem_legacy}_cluster_*.json"))
    legacy_dir = Path(gpkg_path).parent / ".simulation_cache" if gpkg_path else None
    if legacy_dir and legacy_dir != dossier and legacy_dir.exists():
        stem_legacy = re.sub(r'[^\w\-]+', '_', Path(gpkg_path).stem)
        candidats.extend(legacy_dir.glob(f"sim_{stem_legacy}_cluster_*.json"))
    # Dédupliquer puis trier par date de modification décroissante
    uniq = {p.resolve(): p for p in candidats}
    return sorted(uniq.values(), key=lambda x: x.stat().st_mtime, reverse=True)


def resoudre_gpkg_effectif_pour_projet(db: Session, proj: Any) -> Optional[Path]:
    """
    Chemin GPKG effectif pour les endpoints de lecture (téléchargements, PDF) :
    snapshot matérialisé de la version courante si le projet est versionné,
    sinon source_gpkg_key. Si une version est référencée mais indisponible,
    retourne None — jamais de repli silencieux sur un fichier différent.
    """
    if proj is None:
        return None
    chemin, _meta = _resoudre_gpkg_versionne(db, proj)
    if chemin is not None:
        return Path(chemin)
    if getattr(proj, "gpkg_version_id", None):
        return None
    if proj.source_gpkg_key and Path(proj.source_gpkg_key).exists():
        return Path(proj.source_gpkg_key)
    return None


def generer_cle_cache_simulation(gpkg_path: Path, payload: Any) -> Tuple[str, Dict[str, Any]]:
    """
    Génère un dictionnaire canonique normalisé et une empreinte SHA-256
    garantissant l'idempotence exacte de la simulation hydrodynamique.
    L'identité du GPKG est son empreinte de CONTENU (SHA-256) : deux chemins
    vers le même contenu (source projet / snapshot versionné) partagent
    la même empreinte de cache.
    """
    gpkg_stat = gpkg_path.stat() if gpkg_path.exists() else None
    gpkg_size = int(gpkg_stat.st_size) if gpkg_stat else 0
    gpkg_sha256 = _sha256_gpkg(gpkg_path) if gpkg_stat else None

    orph_ids = []
    if getattr(payload, "raccordements_orphelins", None):
        for item in payload.raccordements_orphelins:
            if isinstance(item, dict):
                orph_ids.append(str(item.get("id", item.get("nom", ""))))
            else:
                orph_ids.append(str(item))
    orph_ids.sort()

    params_dict = {
        "gpkg_sha256": gpkg_sha256,
        "gpkg_size": gpkg_size,
        "cluster_id": str(getattr(payload, "cluster_id", None)),
        "scenario_key": str(getattr(payload, "scenario_key", "pluie_decennale")),
        "duree_heures": float(getattr(payload, "duree_heures", None)) if getattr(payload, "duree_heures", None) is not None else None,
        "pas_routage_sec": int(getattr(payload, "pas_routage_sec", None) or 5),
        "pente_moyenne_pct": float(getattr(payload, "pente_moyenne_pct", None) or 1.0),
        "buffer_m": float(getattr(payload, "buffer_m", None) or 35.0),
        "valider_raccordement": bool(getattr(payload, "valider_raccordement", None) if getattr(payload, "valider_raccordement", None) is not None else True),
        "typologie_sol": str(getattr(payload, "typologie_sol", None) or "habitat_mixte"),
        "imperv_pct": float(getattr(payload, "imperv_pct", None)) if getattr(payload, "imperv_pct", None) is not None else None,
        "intensite_max_mmh": float(getattr(payload, "intensite_max_mmh", None)) if getattr(payload, "intensite_max_mmh", None) is not None else None,
        "station_id": str(getattr(payload, "station_id", None) or "chlef_anrh_siege"),
        "raccordements_orphelins": orph_ids,
        "bms_mode": bool(getattr(payload, "bms_mode", False)),
        "bms_vigilance": str(getattr(payload, "bms_vigilance", None) or "orange"),
        "bms_cumul_mm": float(getattr(payload, "bms_cumul_mm", None) or 30.0),
        "bms_heure_debut": str(getattr(payload, "bms_heure_debut", None) or "07:00"),
        "bms_heure_fin": str(getattr(payload, "bms_heure_fin", None) or "21:00"),
        "bms_profil": str(getattr(payload, "bms_profil", None) or "cloche"),
    }
    # Étape 3A : la référence métier du bassin n'entre dans l'empreinte
    # que lorsqu'elle est fournie — les caches historiques restent valides.
    if getattr(payload, "bassin_ref", None):
        params_dict["bassin_ref"] = str(payload.bassin_ref)

    serialized = json.dumps(params_dict, sort_keys=True, ensure_ascii=False)
    param_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
    return param_hash, params_dict


def get_cache_simulation_file(gpkg_path: Path, cluster_id: Any, param_hash: str) -> Path:
    """Retourne le chemin vers le fichier de persistance de simulation (content-adressé)."""
    cache_dir = _repertoire_cache_simulation()
    cache_dir.mkdir(parents=True, exist_ok=True)
    clean_stem = _cle_cache_gpkg(gpkg_path)
    clean_cid = re.sub(r'[^\w\-]+', '_', str(cluster_id))
    return cache_dir / f"sim_{clean_stem}_cluster_{clean_cid}_{param_hash}.json"


def est_simulation_valide(data: Any) -> bool:
    """Vérifie si les résultats de simulation sont valides et non un artefact corrompu ou factice."""
    if not isinstance(data, dict):
        return False
    if "node_results" not in data or "conduit_results" not in data:
        return False
    meta = data.get("meta") or {}
    bbox = meta.get("bbox")
    if bbox and len(bbox) == 4:
        # Rejeter les coordonnées dummy résiduelles (0, 0) envoyées dans l'océan Atlantique
        if abs(bbox[0]) < 1.0 and abs(bbox[1]) < 2.0:
            return False
    # Valide si des conduits/junctions sont répertoriés dans les métadonnées OU dans les dictionnaires de résultats
    nb_conduits = meta.get("conduits_count", 0) or len(data.get("conduit_results", {}))
    nb_junctions = meta.get("junctions_count", 0) or len(data.get("node_results", {}))
    if nb_conduits <= 0 and nb_junctions <= 0 and not data.get("inp_content"):
        return False
    return True


def charger_cache_simulation(gpkg_path: Path, cluster_id: Any, param_hash: str) -> Optional[Dict[str, Any]]:
    """Charge les résultats de la simulation si le fichier de cache existe."""
    cache_file = get_cache_simulation_file(gpkg_path, cluster_id, param_hash)
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data and est_simulation_valide(data):
                return data
        except Exception as e:
            logger.warning("Échec de lecture du cache simulation %s: %s", cache_file, e)
    return None


def sauvegarder_simulation(
    db: Session,
    gpkg_path: Path,
    cluster_id: Any,
    param_hash: str,
    params_dict: Dict[str, Any],
    resultat: Dict[str, Any],
    proj: Any = None,
    tenant: Any = None,
    version_meta: Optional[Dict[str, Any]] = None,
    bassin_ref: Optional[str] = None,
    exutoire_noeud: Optional[str] = None,
) -> Path:
    """Sauvegarde les résultats complets sur disque et référence la simulation dans la base SQLite."""
    from api.models import Simulation

    cache_file = get_cache_simulation_file(gpkg_path, cluster_id, param_hash)

    # Identité de propriété (3D.6) : estampillée dans le JSON pour que le
    # repli disque legacy (`_resultatdeclare_projet`) puisse vérifier
    # l'appartenance du fichier à ce projet/organisation.
    org_id = tenant.org_id if (tenant and hasattr(tenant, "org_id")) else None
    project_id = proj.id if proj else None
    project_name = proj.name if proj else gpkg_path.stem
    if isinstance(resultat, dict):
        meta = resultat.setdefault("meta", {})
        if isinstance(meta, dict):
            if project_id:
                meta["project_id"] = project_id
            if org_id:
                meta["org_id"] = org_id

    # 1. Sauvegarde du JSON complet sur disque
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False)
    except Exception as e:
        logger.error("Erreur lors de l'écriture du cache simulation sur disque: %s", e)

    # 2. Enregistrement en base de données SQLAlchemy
    try:
        kpis_summary = {
            "param_hash": param_hash,
            "cluster_id": cluster_id,
            "scenario_key": params_dict.get("scenario_key"),
            "parameters": params_dict,
            "peak_outflow_m3s": resultat.get("peak_outflow_m3s"),
            "routing_continuity_error_pct": resultat.get("routing_continuity_error_pct"),
            "flooded_nodes_count": resultat.get("flooded_nodes_count", 0),
            "provenance": resultat.get("provenance"),
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }

        # Étape 3B : version GPKG capturée — jamais de valeur sans project_id
        gpkg_version_id = None
        gpkg_sha256 = None
        if version_meta:
            gpkg_sha256 = version_meta.get("sha256")
            if project_id:
                gpkg_version_id = version_meta.get("version_id")

        sim_record = Simulation(
            id=str(uuid.uuid4()),
            org_id=org_id,
            project_id=project_id,
            name=f"SWMM_{project_name}_{cluster_id}_{params_dict.get('scenario_key', 'pluie')}",
            status="completed",
            scenario_pluie=str(params_dict.get("scenario_key", "pluie_decennale")),
            duree_heures=float(params_dict.get("duree_heures") or 4.0),
            results_s3_key=str(cache_file.resolve()),
            gpkg_version_id=gpkg_version_id,
            gpkg_sha256=gpkg_sha256,
            bassin_ref=bassin_ref,
            exutoire_noeud=exutoire_noeud,
            summary_kpis=kpis_summary,
            execution_time_seconds=float(resultat.get("meta", {}).get("execution_duration_sec", 0.0)),
        )
        db.add(sim_record)
        db.commit()
        sim_persistee = True
    except Exception as e:
        db.rollback()
        logger.warning("Avertissement: enregistrement de la simulation en DB impossible: %s", e)
        sim_persistee = False

    # 3. Étape 3C.3 — persistance permanente des artefacts via ResultStore.
    #    Le cache de calcul (.simulation_cache) reste la voie de travail
    #    historique ; ResultStore dépose result.json / model.inp / report.rpt
    #    sous la partition {org}/{projet}/simulations/{id}/ de façon
    #    conditionnelle et immuable. Un échec ici ne remet JAMAIS en cause
    #    la simulation : le statut est enregistré dans summary_kpis.
    if sim_persistee:
        statut_store = _persister_resultats_store(sim_record, resultat)
        try:
            kpis = dict(sim_record.summary_kpis or {})
            kpis["result_store"] = statut_store
            sim_record.summary_kpis = kpis
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning("Statut ResultStore non persisté en DB : %s", e)

    return cache_file


def _persister_resultats_store(simulation: Any, resultat: Dict[str, Any]) -> Dict[str, Any]:
    """
    Étape 3C.3 — dépose les artefacts permanents d'une simulation via
    ResultStore (au-dessus d'ArtifactStore). Appelée UNIQUEMENT après
    commit de la ligne Simulation : la référence utilise les identifiants
    RÉELS persistés (org_id / project_id / id), jamais d'identité inventée.

    Artefacts déposés :
      - result.json  : le JSON complet du résultat (autorité permanente) ;
      - model.inp    : le INP réellement exécuté (si présent) ;
      - report.rpt   : le rapport RPT produit (si présent).
    Les séries temporelles et le résumé restent embarqués dans result.json
    (pas de doublon summary.json).

    Chaque artefact est déposé via `save_idempotent` : contenu identique →
    succès idempotent ; contenu divergent → erreur explicite consignée.
    Retourne un dictionnaire de statut diagnostic (jamais d'exception
    propagée : la simulation et son cache restent valides).
    """
    from api.services.result_store import (
        ArtifactKind,
        ResultAlreadyExists,
        ResultRef,
        ResultStore,
        ResultStoreError,
    )

    statut: Dict[str, Any] = {"artefacts": {}, "complet": False}
    try:
        ref = ResultRef.depuis_simulation(simulation)
    except ResultStoreError as e:
        statut["erreur"] = f"identite_incomplete: {e}"
        logger.error(
            "ResultStore : persistance ignorée pour la simulation %s — "
            "identité incomplète (org_id/project_id requis) : %s",
            getattr(simulation, "id", "?"), e)
        return statut

    statut["ref"] = {
        "org_id": ref.org_id,
        "project_id": ref.project_id,
        "simulation_id": ref.simulation_id,
    }
    store = ResultStore()
    statut["result_key"] = store.cle(ref)

    taches: List[tuple] = [(ArtifactKind.RESULT_JSON, resultat, "application/json")]
    if isinstance(resultat, dict):
        for cle_src, kind in (("inp_content", ArtifactKind.INP),
                              ("rpt_content", ArtifactKind.RPT)):
            contenu = resultat.get(cle_src)
            if contenu:
                taches.append((kind, contenu, "text/plain; charset=utf-8"))

    for kind, contenu, content_type in taches:
        try:
            _, cree = store.save_idempotent(
                ref, contenu, kind=kind, content_type=content_type)
            statut["artefacts"][kind.value] = "created" if cree else "identical"
        except ResultAlreadyExists as e:
            statut["artefacts"][kind.value] = f"error:divergence"
            logger.error("ResultStore : divergence d'artefact %s : %s", kind.value, e)
        except ResultStoreError as e:
            statut["artefacts"][kind.value] = f"error:{e}"
            logger.error("ResultStore : dépôt %s impossible : %s", kind.value, e)
        except Exception as e:
            statut["artefacts"][kind.value] = f"error:{e}"
            logger.exception("ResultStore : erreur inattendue sur %s", kind.value)

    statut["complet"] = bool(statut["artefacts"]) and all(
        v in ("created", "identical") for v in statut["artefacts"].values())
    if not statut["complet"]:
        logger.error(
            "ResultStore : persistance PARTIELLE pour la simulation %s : %s",
            ref.simulation_id, statut["artefacts"])

    # 3C.4 — manifeste d'état : reflète les artefacts RÉELLEMENT présents
    # (relecture + SHA-256), jamais une simple déclaration. Best effort :
    # son échec est diagnostiqué sans invalider les artefacts déposés.
    try:
        manifeste = store.ecrire_manifeste(
            ref, etat_execution="EXECUTED",
            artefacts_attendus=[kind for kind, _, _ in taches])
        statut["manifeste"] = {"etat": manifeste.get("etat"),
                               "key": manifeste.get("key"),
                               "manquants": manifeste.get("manquants")}
    except Exception as e:
        statut["manifeste"] = {"erreur": str(e)}
        logger.error("ResultStore : écriture manifeste impossible : %s", e)
    return statut


def _resultatdeclare_projet(data: Dict[str, Any], proj: Any) -> bool:
    """
    Garde-fou legacy (3D.6) : si le JSON de résultat DÉCLARE un project_id
    ou org_id dans ses métadonnées, il doit correspondre au projet résolu.
    Les anciens fichiers sans ces champs restent acceptés (compatibilité).
    """
    if proj is None or not isinstance(data, dict):
        return True
    meta = data.get("meta") or {}
    pid = meta.get("project_id") or data.get("project_id")
    oid = meta.get("org_id") or data.get("org_id")
    if pid and str(pid) != str(proj.id):
        return False
    if oid and str(oid) != str(getattr(proj, "org_id", "")):
        return False
    return True


def charger_derniere_simulation_disque_ou_db(gpkg_path: Path, db: Session, proj: Any = None) -> Optional[Dict[str, Any]]:
    """
    Recherche la simulation la plus récente enregistrée pour ce GeoPackage
    en vérifiant d'abord la table `simulations` en DB, puis le dossier `.simulation_cache/`.

    Étape 3D.6 — durcissements :
      - la requête DB n'est exécutée QUE si `proj` est fourni : jamais de
        lecture non filtrée susceptible de traverser les organisations ;
      - le résultat est chargé via `charger_resultat_simulation` (chemin
        local OU clé ArtifactStore — compatible Celery/S3) ;
      - le repli disque vérifie la propriété déclarée dans les métadonnées.
    """
    from api.models import Simulation
    # 1. Vérifier la table Simulation — uniquement dans le périmètre projet
    if proj is not None:
        try:
            query = db.query(Simulation).filter(
                Simulation.status == "completed",
                Simulation.project_id == proj.id,
            )
            if getattr(proj, "org_id", None):
                query = query.filter(Simulation.org_id == proj.org_id)
            last_sim = query.order_by(Simulation.created_at.desc()).first()
            if last_sim:
                data = charger_resultat_simulation(last_sim)
                if data and est_simulation_valide(data) \
                        and _resultatdeclare_projet(data, proj):
                    return data
        except Exception as e:
            logger.warning("Erreur interrogation table simulations: %s", e)

    # 2. Fallback dossier .simulation_cache/ (content-adressé + legacy),
    #    borné au GPKG du projet et à la propriété déclarée.
    for fpath in iter_fichiers_cache_simulation(gpkg_path):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data and est_simulation_valide(data) \
                    and _resultatdeclare_projet(data, proj):
                return data
        except Exception:
            continue
    return None


def preparer_scenario_bms(params: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """
    Prépare le scénario d'exécution : construit le scénario BMS ONM si demandé
    et calcule les valeurs effectives (scénario, durée, intensité max).
    Ne mute jamais l'entrée. Retourne (scenario_personnalise, champs_effectifs).
    """
    scenario_key = params.get("scenario_key") or "pluie_decennale"
    duree_heures = params.get("duree_heures")
    intensite_max_mmh = params.get("intensite_max_mmh")

    scenario_bms_dict = None
    if params.get("bms_mode") or scenario_key == "bms_alerte":
        from src.domain.bms_module import creer_scenario_bms
        scenario_bms_dict = creer_scenario_bms(
            cumul_pluie_mm=params.get("bms_cumul_mm") or 30.0,
            duree_heures=params.get("bms_duree_heures"),
            heure_debut=params.get("bms_heure_debut") or "07:00",
            heure_fin=params.get("bms_heure_fin") or "21:00",
            niveau_vigilance=params.get("bms_vigilance") or "orange",
            type_profil=params.get("bms_profil") or "cloche",
            station_id=params.get("station_id") or "chlef_anrh_siege",
        )
        scenario_key = "bms_alerte"
        # Durée de simulation = durée BMS + marge de 3h pour propagation onde de crue jusqu'à l'exutoire
        bms_duree = scenario_bms_dict.get("duree_bms_heures", scenario_bms_dict.get("duree_heures", 3.0))
        min_sim_duration = bms_duree + 3.0
        if duree_heures is None or duree_heures < min_sim_duration:
            duree_heures = min_sim_duration
        if intensite_max_mmh is None:
            intensite_max_mmh = scenario_bms_dict["intensite_max_defaut"]

    return scenario_bms_dict, {
        "scenario_key": scenario_key,
        "duree_heures": duree_heures,
        "intensite_max_mmh": intensite_max_mmh,
    }


def corriger_pic_depuis_timeseries(resultat: Dict[str, Any]) -> Dict[str, Any]:
    """
    Corrige peak_outflow_m3s depuis les séries temporelles si le RPT donne 0.0
    (cas où la durée de simulation est trop courte pour capturer le pic à l'exutoire).
    """
    ts = resultat.get("timeseries")
    if ts and ts.get("status") == "SUCCESS" and ts.get("peak_outflow_m3s", 0.0) > 0:
        rpt_peak = resultat.get("peak_outflow_m3s", 0.0)
        ts_peak = ts.get("peak_outflow_m3s", 0.0)
        if rpt_peak == 0.0 or ts_peak > rpt_peak:
            logger.info("Correction peak_outflow_m3s: RPT=%.3f -> Timeseries=%.3f m³/s", rpt_peak, ts_peak)
            resultat["peak_outflow_m3s"] = ts_peak
            resultat["peak_time_str"] = ts.get("peak_time")
            # Corriger aussi les KPIs dérivés
            resultat["q_exutoire_m3s"] = round(ts_peak, 3)
            resultat["q_genere_m3s"] = round(ts_peak + resultat.get("q_deleste_m3s", 0.0), 3)
    return resultat


def executer_moteur_swmm(
    gpkg_path: Path,
    params: Dict[str, Any],
    execution_mode: str = "sync",
) -> Dict[str, Any]:
    """
    Point d'entrée métier unique : prépare le scénario (BMS) puis exécute
    MoteurSWMM (EPA SWMM via PySWMM) et applique la correction de pic.
    `params` est un mapping aux noms de champs de SimulationRunRequest.
    """
    from src.domain.moteur_swmm import MoteurSWMM

    scenario_bms_dict, eff = preparer_scenario_bms(params)

    moteur = MoteurSWMM()
    resultat = moteur.executer_simulation(
        gpkg_path=gpkg_path,
        scenario_key=eff["scenario_key"],
        duree_heures=eff["duree_heures"],
        pas_routage_sec=params.get("pas_routage_sec"),
        pente_moyenne_pct=params.get("pente_moyenne_pct"),
        cluster_id=params.get("cluster_id"),
        tampon_buffer_m=params.get("buffer_m"),
        valider_raccordement_deporte=(
            params.get("valider_raccordement") if params.get("valider_raccordement") is not None else True
        ),
        typologie_sol=params.get("typologie_sol"),
        imperv_pct=params.get("imperv_pct"),
        intensite_max_mmh=eff["intensite_max_mmh"],
        station_id=params.get("station_id"),
        raccordements_orphelins=params.get("raccordements_orphelins"),
        scenario_personnalise=scenario_bms_dict,
        execution_mode=execution_mode,
    )

    return corriger_pic_depuis_timeseries(resultat)


def construire_reponse_simulation(resultat: Dict[str, Any], cached: bool = False) -> Dict[str, Any]:
    """Structure la réponse standardisée renvoyée au frontend."""
    message = (
        "Résultats restaurés instantanément depuis la sauvegarde (paramètres de simulation inchangés)."
        if cached
        else "Simulation hydrodynamique SWMM 5.2 exécutée avec succès."
    )
    return {
        "status": "success",
        "cached": cached,
        "message": message,
        "meta": resultat.get("meta", {}),
        "provenance": resultat.get("provenance"),
        "kpis": {
            "routing_continuity_error_pct": resultat.get("routing_continuity_error_pct"),
            "runoff_continuity_error_pct": resultat.get("runoff_continuity_error_pct"),
            "total_precipitation_mm": resultat.get("total_precipitation_mm"),
            "total_precipitation_volume_m3": resultat.get("total_precipitation_volume_m3"),
            "total_runoff_volume_m3": resultat.get("total_runoff_volume_m3"),
            "total_infiltration_volume_m3": resultat.get("total_infiltration_volume_m3"),
            "total_outflow_m3": resultat.get("total_outflow_m3"),
            "peak_outflow_m3s": resultat.get("peak_outflow_m3s"),
            "effective_runoff_coeff": resultat.get("effective_runoff_coeff"),
            "peak_time_str": resultat.get("peak_time_str"),
            "max_velocity_ms": resultat.get("max_velocity_ms"),
            "autocurage_statut": resultat.get("autocurage_statut"),
            "autocurage_color": resultat.get("autocurage_color"),
            "autocurage_note": resultat.get("autocurage_note"),
            "total_network_length_m": resultat.get("total_network_length_m"),
            "surcharged_length_m": resultat.get("surcharged_length_m"),
            "surcharged_length_pct": resultat.get("surcharged_length_pct"),
            "coherence_pluie_debit": resultat.get("coherence_pluie_debit"),
            "typologie_sol": resultat.get("meta", {}).get("typologie_sol"),
            "typologie_nom": resultat.get("meta", {}).get("typologie_nom"),
            "imperv_pct": resultat.get("meta", {}).get("imperv_pct"),
            "pluvio_station": resultat.get("meta", {}).get("pluvio_station"),
            "pluvio_station_id": resultat.get("meta", {}).get("pluvio_station_id"),
            "pluvio_code_anrh": resultat.get("meta", {}).get("pluvio_code_anrh"),
            "pluvio_wilaya": resultat.get("meta", {}).get("pluvio_wilaya"),
            "pluvio_scenario_nom": resultat.get("meta", {}).get("pluvio_scenario_nom"),
            "pluvio_periode_retour": resultat.get("meta", {}).get("pluvio_periode_retour"),
            "pluvio_intensite_max_mmh": resultat.get("meta", {}).get("pluvio_intensite_max_mmh"),
            "pluvio_montana": resultat.get("meta", {}).get("pluvio_montana"),
            "pluvio_hauteur_totale_mm": resultat.get("meta", {}).get("pluvio_hauteur_totale_mm"),
            "pluvio_p24_mm": resultat.get("meta", {}).get("pluvio_p24_mm"),
            "pluvio_source": resultat.get("meta", {}).get("pluvio_source"),
            "bms_info": resultat.get("meta", {}).get("bms_info"),
            "flooded_nodes_count": resultat.get("flooded_nodes_count"),
            "surcharged_nodes_count": resultat.get("surcharged_nodes_count", 0),
            "flooded_nodes": resultat.get("flooded_nodes", [])[:15],
            "q_deleste_m3s": resultat.get("q_deleste_m3s", 0.0),
            "q_deleste_ls": resultat.get("q_deleste_ls", 0.0),
            "q_derive_m3s": resultat.get("q_derive_m3s", resultat.get("q_deleste_m3s", 0.0)),
            "q_exutoire_m3s": resultat.get("q_exutoire_m3s", round(float(resultat.get("peak_outflow_m3s") or 0.0), 3)),
            "q_genere_m3s": resultat.get("q_genere_m3s", round(float(resultat.get("peak_outflow_m3s") or 0.0) + float(resultat.get("q_deleste_m3s") or 0.0), 3)),
            "taux_derive_pct": resultat.get("taux_derive_pct", 0.0),
            "taux_exutoire_pct": resultat.get("taux_exutoire_pct", 100.0),
            "soulagement_reseau_pct": resultat.get("soulagement_reseau_pct", resultat.get("taux_derive_pct", 0.0)),
            "reduction_charge_pct": resultat.get("reduction_charge_pct", resultat.get("taux_derive_pct", 0.0)),
            "nb_ouvrages_raccordes": resultat.get("nb_ouvrages_raccordes", 0),
            "bilan_hydraulique": resultat.get("bilan_hydraulique", {}),
            "bilan_hydraulique_decisionnel": resultat.get("bilan_hydraulique_decisionnel", ""),
            "compliance_continuity": resultat.get("compliance_continuity", True),
        },
        "buffer_sensitivity": resultat.get("buffer_sensitivity", {}),
        "agents_expertise": resultat.get("agents_expertise", {}),
        "node_results": resultat.get("node_results", {}),
        "conduit_results": resultat.get("conduit_results", {}),
        "download_inp_url": "/api/v1/simulations/download/inp",
        "download_rpt_url": "/api/v1/simulations/download/rpt",
    }


# ============================================================
# Étape 3D.1 — Résolution contextuelle des simulations
# ============================================================
# Remplace la lecture de la globale `_DERNIERE_SIMULATION` : la simulation
# est toujours retrouvée via sa ligne `Simulation` persistée, filtrée par
# org_id/project_id, jamais par un état process-wide.


class ContexteSimulationIntrouvable(Exception):
    """Aucune simulation autorisée pour ce contexte organisation/projet."""


class ProjetAmbigu(Exception):
    """Plusieurs projets actifs possibles sans project_id explicite."""


@dataclass
class ContexteSimulation:
    """Simulation résolue pour un contexte organisation/projet donné."""
    simulation: Any = None                    # ligne ORM Simulation
    project: Any = None                       # projet ORM propriétaire
    data: Optional[Dict[str, Any]] = None     # JSON résultat complet
    gpkg_path: Optional[Path] = None          # snapshot GPKG résolu (3C.0)
    meta_version: Dict[str, Any] = None       # métadonnées de version GPKG
    resolution: str = ""                      # "simulation_id" | "derniere" | "bassin"


# ---------------------------------------------------------------------------
# Étape 3C.4 — séparation résultat original / enrichissements dérivés
# ---------------------------------------------------------------------------
# `result.json` = sortie hydraulique originale du moteur (IMMUTABLE).
# `result_enriched.json` = données dérivées uniquement. La fusion ne peut
# JAMAIS écraser une donnée hydraulique originale : seuls les champs
# dérivés whitelistés sont appliqués.

CHAMPS_RESULTAT_ENRICHISSABLES = ("timeseries", "buffer_sensitivity")
CHAMPS_META_ENRICHISSABLES = ("buffer_m",)
_CLE_HISTORIQUE_ENRICHI = "_revision_history"


def _extraire_enrichissement(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extrait du résultat complet les SEULS champs dérivés enrichissables.
    Retourne None si aucun champ dérivé n'est présent.
    """
    if not isinstance(data, dict):
        return None
    enrichi: Dict[str, Any] = {}
    for cle in CHAMPS_RESULTAT_ENRICHISSABLES:
        if cle in data:
            enrichi[cle] = data[cle]
    meta = data.get("meta")
    if isinstance(meta, dict):
        sous = {k: meta[k] for k in CHAMPS_META_ENRICHISSABLES if k in meta}
        if sous:
            enrichi["meta"] = sous
    return enrichi or None


def _fusionner_enrichissement(store: Any, ref: Any,
                              base: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fusionne result.json (original immuable) + result_enriched.json
    (dérivé). Règle stricte : les enrichissements ne peuvent compléter ou
    actualiser QUE les champs dérivés whitelistés — toute autre clé est
    ignorée avec avertissement, jamais appliquée au résultat hydraulique.
    """
    try:
        enrichi = store.load_json(ref, _kind_enrichi())
    except Exception:
        return base  # absent ou illisible : le résultat original fait foi
    if not isinstance(enrichi, dict):
        return base
    enrichi = {k: v for k, v in enrichi.items() if k != _CLE_HISTORIQUE_ENRICHI}

    fusionne = dict(base)
    ignores = []
    for cle, valeur in enrichi.items():
        if cle in CHAMPS_RESULTAT_ENRICHISSABLES:
            fusionne[cle] = valeur
        elif cle == "meta" and isinstance(valeur, dict):
            meta = dict(base.get("meta") or {})
            for sk, sv in valeur.items():
                if sk in CHAMPS_META_ENRICHISSABLES:
                    meta[sk] = sv
                else:
                    ignores.append(f"meta.{sk}")
            fusionne["meta"] = meta
        else:
            ignores.append(cle)
    if ignores:
        logger.warning(
            "Enrichissement ignoré (champs non dérivés) pour %s : %s",
            getattr(ref, "simulation_id", "?"), ignores)
    return fusionne


def _kind_enrichi():
    from api.services.result_store import ArtifactKind
    return ArtifactKind.RESULT_ENRICHED


def charger_resultat_simulation(simulation: Any) -> Optional[Dict[str, Any]]:
    """
    Charge le JSON de résultat d'une ligne Simulation.

    Ordre de lecture (étape 3C.3/3C.4) :
      0. ResultStore — artefact permanent `result.json` (immuable) lorsque
         la ligne porte une identité complète (org_id/project_id/id),
         puis fusion avec `result_enriched.json` (dérivés whitelistés
         uniquement — jamais d'écrasement des données hydrauliques) ;
      1. `results_s3_key` comme chemin local existant (sims synchrones
         historiques et actuelles — le cache de calcul reste la voie de
         travail) ;
      2. `results_s3_key` comme clé ArtifactStore (sims Celery :
         `org_id/projet/jobs/<id>/summary.json`).
    Aucune écriture, aucun repli implicite sur un autre résultat : chaque
    voie ne lit que les artefacts de CETTE simulation.
    """
    # 0. ResultStore — uniquement si la ligne porte l'identité complète
    try:
        from api.services.result_store import (
            ArtifactKind,
            ResultNotFound,
            ResultRef,
            ResultStore,
            ResultStoreError,
        )
        ref = ResultRef.depuis_simulation(simulation)
    except ResultStoreError:
        ref = None
    if ref is not None:
        try:
            store = ResultStore()
            data = store.load_json(ref, ArtifactKind.RESULT_JSON)
            if isinstance(data, dict) and data:
                return _fusionner_enrichissement(store, ref, data)
        except ResultNotFound:
            pass  # artefact absent → voies legacy ci-dessous
        except ResultStoreError as e:
            logger.warning(
                "Lecture ResultStore impossible (%s), repli legacy : %s",
                ref.simulation_id, e)
        except Exception as e:
            logger.warning(
                "Lecture ResultStore inattendue (%s), repli legacy : %s",
                ref.simulation_id, e)

    cle = getattr(simulation, "results_s3_key", None)
    if not cle:
        return None
    cle = str(cle)

    # 1. Chemin local (absolu ou relatif au CWD)
    try:
        p = Path(cle)
        if p.exists() and p.is_file():
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:
        logger.warning("Lecture résultat simulation (chemin local) impossible: %s", e)

    # 2. Clé de stockage (ArtifactStore) — sims Celery / S3
    try:
        from api.core.storage import get_storage
        brut = get_storage().get_bytes(cle)
        data = json.loads(brut.decode("utf-8"))
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.warning("Lecture résultat simulation (store %s) impossible: %s", cle, e)

    return None


def persister_resultat_simulation(simulation: Any, data: Dict[str, Any]) -> bool:
    """
    Réécrit le JSON de résultat d'une simulation via le même adaptateur que
    `charger_resultat_simulation` : chemin local si `results_s3_key` est un
    fichier, sinon clé ArtifactStore (put_bytes). Retourne True si écrit.

    Étape 3C.3/3C.4 — write-through ResultStore : si la ligne porte une
    identité complète, les champs DÉRIVÉS du résultat sont extraits et
    déposés dans `result_enriched.json` via `replace_enriched` (canal
    strictement cantonné, historique d'empreintes conservé). Le résultat
    hydraulique original `result.json` n'est JAMAIS réécrit. Le manifeste
    est ensuite actualisé. Un échec du store ne fait pas échouer la
    persistance legacy (journalisé).
    """
    cle = getattr(simulation, "results_s3_key", None)
    if not cle or not isinstance(data, dict):
        return False
    cle = str(cle)
    ecrit = False
    try:
        p = Path(cle)
        if p.exists() and p.is_file():
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            ecrit = True
    except Exception as e:
        logger.warning("Persistance résultat simulation (chemin local) impossible: %s", e)
    if not ecrit:
        try:
            from api.core.storage import get_storage
            get_storage().put_bytes(cle, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                                    content_type="application/json")
            ecrit = True
        except Exception as e:
            logger.warning("Persistance résultat simulation (store %s) impossible: %s", cle, e)

    # Write-through ResultStore (best effort, jamais bloquant) — 3C.4 :
    # uniquement les champs dérivés vers result_enriched.json.
    try:
        from api.services.result_store import (
            ArtifactKind,
            ResultRef,
            ResultStore,
            ResultStoreError,
        )
        try:
            ref = ResultRef.depuis_simulation(simulation)
        except ResultStoreError:
            ref = None
        if ref is not None:
            enrichi = _extraire_enrichissement(data)
            store = ResultStore()
            attendus = [ArtifactKind.RESULT_JSON]
            if enrichi is not None:
                store.replace_enriched(ref, enrichi)
                attendus.append(ArtifactKind.RESULT_ENRICHED)
            store.ecrire_manifeste(ref, etat_execution="EXECUTED",
                                   artefacts_attendus=attendus)
    except ResultStoreError as e:
        logger.warning("Write-through ResultStore impossible (%s): %s",
                       getattr(simulation, "id", "?"), e)
    except Exception as e:
        logger.warning("Write-through ResultStore inattendu (%s): %s",
                       getattr(simulation, "id", "?"), e)

    return ecrit


def _resoudre_projet_pour_simulation(db: Session, org_id: Optional[str],
                                    project_id: Optional[str]) -> Any:
    """
    Résout le projet cible SANS sélection arbitraire :
      - project_id explicite → doit exister et appartenir à org_id ;
      - sinon, les projets actifs de l'org (ou de toute la base si org_id
        est None, compatibilité dev mono-tenant) : exactement UN seul est
        toléré ; plusieurs → ProjetAmbigu ; zéro → ContexteSimulationIntrouvable.
    """
    from api.models import Project

    if project_id:
        proj = db.get(Project, project_id)
        if proj is None or proj.is_archived:
            raise ContexteSimulationIntrouvable("Projet introuvable ou archivé.")
        if org_id and proj.org_id != org_id:
            raise ContexteSimulationIntrouvable(
                "Le projet demandé n'appartient pas à l'organisation.")
        return proj

    q = db.query(Project).filter(Project.is_archived.is_(False))
    if org_id:
        q = q.filter(Project.org_id == org_id)
    projets = q.order_by(Project.id).all()
    if not projets:
        raise ContexteSimulationIntrouvable("Aucun projet actif pour ce contexte.")
    if len(projets) > 1:
        raise ProjetAmbigu(
            "Plusieurs projets actifs : un project_id explicite est requis.")
    return projets[0]


def _simulation_correspond_a_bassin(sim: Any, cluster_id: Any = None,
                                    bassin_ref: Optional[str] = None,
                                    exutoire_noeud: Optional[str] = None) -> bool:
    """
    Identité de bassin d'une simulation : bassin_ref > exutoire_noeud >
    cluster_id persisté (summary_kpis) > nom (dernier recours).
    """
    if bassin_ref is not None:
        cible_bassin = str(bassin_ref).strip().lower()
        if sim.bassin_ref and str(sim.bassin_ref).strip().lower() == cible_bassin:
            return True
    if exutoire_noeud is not None:
        cible_ex = str(exutoire_noeud).strip().lower()
        if sim.exutoire_noeud and str(sim.exutoire_noeud).strip().lower() == cible_ex:
            return True
    if cluster_id is None:
        return False
    cible = str(cluster_id).strip().lower()
    if sim.bassin_ref and str(sim.bassin_ref).strip().lower() == cible:
        return True
    if sim.exutoire_noeud and str(sim.exutoire_noeud).strip().lower() == cible:
        return True
    kpis = sim.summary_kpis or {}
    if str(kpis.get("cluster_id", "")).strip().lower() == cible:
        return True
    params = kpis.get("parameters") or {}
    if isinstance(params, dict) and str(params.get("cluster_id", "")).strip().lower() == cible:
        return True
    nom = str(sim.name or "").lower()
    return bool(nom and cible in nom)


def resoudre_simulation_courante(
    db: Session,
    org_id: Optional[str] = None,
    project_id: Optional[str] = None,
    simulation_id: Optional[str] = None,
    cluster_id: Any = None,
    bassin_ref: Optional[str] = None,
    exutoire_noeud: Optional[str] = None,
    resoudre_gpkg: bool = True,
) -> ContexteSimulation:
    """
    Étape 3D.1 — point d'entrée unique de résolution d'une simulation
    AUTORISÉE pour un contexte organisation/projet.

    - `simulation_id` explicite : lookup direct, garde org/projet stricte.
    - sinon : simulation `completed` la plus récente du projet résolu
      (ORDER BY created_at DESC, id DESC — déterministe).
    - filtres de bassin : cluster_id / bassin_ref / exutoire_noeud.
    - le JSON est chargé via `charger_resultat_simulation` (chemin local
      puis clé ArtifactStore — compatible Celery/S3).
    - `resoudre_gpkg=True` résout le snapshot exact via
      `resoudre_gpkg_pour_simulation` (3C.0) ; les erreurs de provenance
      explicite remontent telles quelles (GpkgSimulationError).

    Lève ContexteSimulationIntrouvable / ProjetAmbigu — jamais de
    substitution silencieuse par une simulation d'un autre périmètre.
    """
    from api.models import Simulation

    proj = _resoudre_projet_pour_simulation(db, org_id, project_id)
    org_effectif = org_id or proj.org_id

    if simulation_id:
        sim = db.get(Simulation, simulation_id)
        if (sim is None or sim.project_id != proj.id
                or (org_effectif and sim.org_id != org_effectif)):
            raise ContexteSimulationIntrouvable(
                "Simulation introuvable pour ce contexte.")
        data = charger_resultat_simulation(sim)
        if not data or not est_simulation_valide(data):
            raise ContexteSimulationIntrouvable(
                "Résultat de simulation indisponible ou invalide.")
        ctx = ContexteSimulation(simulation=sim, project=proj, data=data,
                                 resolution="simulation_id")
        if resoudre_gpkg:
            _joindre_gpkg(db, proj, ctx)
        return ctx

    q = db.query(Simulation).filter(
        Simulation.project_id == proj.id,
        Simulation.status == "completed",
    )
    if org_effectif:
        q = q.filter(Simulation.org_id == org_effectif)
    candidats = q.order_by(
        Simulation.created_at.desc(), Simulation.id.desc()).limit(80).all()

    for sim in candidats:
        if (cluster_id is not None or bassin_ref is not None
                or exutoire_noeud is not None):
            if not _simulation_correspond_a_bassin(
                    sim, cluster_id=cluster_id, bassin_ref=bassin_ref,
                    exutoire_noeud=exutoire_noeud):
                continue
        # results_s3_key peut être vide pour une sim dont seul ResultStore
        # porte le résultat (identité complète) — ne pas exclure a priori.
        if not sim.results_s3_key and _ref_pour_simulation(sim) is None:
            continue
        data = charger_resultat_simulation(sim)
        if not data or not est_simulation_valide(data):
            continue
        ctx = ContexteSimulation(
            simulation=sim, project=proj, data=data,
            resolution="bassin" if (
                cluster_id is not None or bassin_ref is not None
                or exutoire_noeud is not None) else "derniere")
        if resoudre_gpkg:
            _joindre_gpkg(db, proj, ctx)
        return ctx

    raise ContexteSimulationIntrouvable(
        "Aucune simulation autorisée pour ce contexte.")


def _joindre_gpkg(db: Session, proj: Any, ctx: ContexteSimulation) -> None:
    """Résout le snapshot GPKG exact de la simulation (étape 3C.0)."""
    from api.services.gpkg_versions import resoudre_gpkg_pour_simulation
    gpkg, meta = resoudre_gpkg_pour_simulation(db, proj, ctx.data)
    ctx.gpkg_path = gpkg
    ctx.meta_version = meta or {}


# ============================================================
# Étape 3C.4 — Intégrité, manifeste, diagnostic et reprise
# ============================================================

def _ref_pour_simulation(simulation: Any):
    """ResultRef depuis la ligne Simulation, ou None si identité incomplète."""
    from api.services.result_store import ResultRef, ResultStoreError
    try:
        return ResultRef.depuis_simulation(simulation)
    except ResultStoreError:
        return None


def diagnostiquer_resultats_store(simulation: Any) -> Dict[str, Any]:
    """
    Diagnostic d'intégrité complet d'une simulation côté ResultStore :
      - `execution` : EXECUTED si la ligne ORM existe (toujours vrai ici) ;
      - `manifeste` : ABSENT / PARTIAL / DEGRADED / VERIFIED (manifeste
        confronté aux artefacts réellement relus, SHA-256 inclus) ;
      - `persistance_complete` : True uniquement si le manifeste est
        VERIFIED — un manifeste présent ne suffit JAMAIS.
    Lève ResultStoreError si l'identité est incomplète.
    """
    from api.services.result_store import (
        ResultRef, ResultStore, ResultStoreError,
    )
    ref = _ref_pour_simulation(simulation)
    if ref is None:
        raise ResultStoreError(
            "Identité incomplète : diagnostic ResultStore impossible.")
    store = ResultStore()
    verification = store.verifier_manifeste(ref)
    return {
        "simulation_id": ref.simulation_id,
        "org_id": ref.org_id,
        "project_id": ref.project_id,
        "execution": "EXECUTED",
        "manifeste": verification.get("etat", "ABSENT"),
        "persistance_complete": verification.get("etat") == "VERIFIED",
        "details": verification.get("details") or {},
        "attendus_manquants": verification.get("attendus_manquants") or [],
    }


def reprise_resultat_simulation(simulation: Any,
                                resultat: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reprise IDEMPOTANTE d'une persistance interrompue, SANS relancer SWMM.

    `resultat` = données disponibles (typiquement relues depuis le cache
    de calcul ou un artefact existant). Pour chaque artefact :
      - absent            → dépôt conditionnel (save_idempotent) ;
      - présent identique → succès idempotent ;
      - présent divergent → anomalie explicite, JAMAIS écrasé ;
      - altéré (SHA-256 ≠ manifeste) → signalé dans le diagnostic, non
        écrasé automatiquement.
    Le manifeste est réécrit en fin d'opération. Retourne le statut
    détaillé ; ne lève pas d'exception métier (erreurs backend → statut).
    """
    from api.services.result_store import (
        ArtifactKind, ResultAlreadyExists, ResultStore, ResultStoreError,
    )

    statut: Dict[str, Any] = {"simulation_id": getattr(simulation, "id", None),
                              "artefacts": {}, "anomalies": [],
                              "persistance_complete": False}
    ref = _ref_pour_simulation(simulation)
    if ref is None:
        statut["erreur"] = "identite_incomplete"
        return statut

    store = ResultStore()
    # Diagnostic préalable : altérations par rapport au manifeste
    try:
        diag = store.verifier_manifeste(ref)
        if diag.get("etat") in ("DEGRADED",):
            for nom, det in (diag.get("details") or {}).items():
                if det.get("present") and not det.get("intègre"):
                    statut["anomalies"].append(
                        f"artefact_altéré:{nom}")
    except Exception as e:
        logger.warning("Diagnostic manifeste impossible avant reprise : %s", e)

    taches = [(ArtifactKind.RESULT_JSON, resultat, "application/json")]
    if isinstance(resultat, dict):
        for cle_src, kind in (("inp_content", ArtifactKind.INP),
                              ("rpt_content", ArtifactKind.RPT)):
            contenu = resultat.get(cle_src)
            if contenu:
                taches.append((kind, contenu, "text/plain; charset=utf-8"))

    for kind, contenu, content_type in taches:
        try:
            _, cree = store.save_idempotent(
                ref, contenu, kind=kind, content_type=content_type)
            statut["artefacts"][kind.value] = "created" if cree else "identical"
        except ResultAlreadyExists as e:
            statut["artefacts"][kind.value] = "error:divergence"
            statut["anomalies"].append(f"divergence:{kind.value}")
            logger.error("Reprise : divergence refusée sur %s : %s", kind.value, e)
        except ResultStoreError as e:
            statut["artefacts"][kind.value] = f"error:{e}"
            statut["anomalies"].append(f"stockage:{kind.value}")
            logger.error("Reprise : dépôt %s impossible : %s", kind.value, e)
        except Exception as e:
            statut["artefacts"][kind.value] = f"error:{e}"
            statut["anomalies"].append(f"stockage:{kind.value}")
            logger.exception("Reprise : erreur inattendue sur %s", kind.value)

    try:
        manifeste = store.ecrire_manifeste(
            ref, etat_execution="EXECUTED",
            artefacts_attendus=[kind for kind, _, _ in taches])
        statut["manifeste"] = manifeste.get("etat")
    except Exception as e:
        statut["manifeste"] = f"erreur:{e}"
        logger.error("Reprise : écriture manifeste impossible : %s", e)

    statut["persistance_complete"] = (
        statut["manifeste"] == "PERSISTED" and not statut["anomalies"])
    return statut


# ============================================================
# LOT 3C.7.3 — Point d'entrée métier asynchrone (adaptateur Celery)
# ============================================================
# `executer_en_async` est LE point d'entrée unique pour le worker Celery :
# même résolution GPKG versionnée, même MoteurSWMM/PySWMM, même cache,
# même ResultStore que le chemin synchrone. Aucune dépendance à Celery,
# FastAPI ou Request — la session DB est injectée par l'appelant.


def resoudre_gpkg_pour_projet(db: Session, proj: Any) -> Tuple[Path, Dict[str, Any]]:
    """
    Résout le GPKG d'un projet EXPLICITE (jamais de sélection inter-projets).
    Retourne (gpkg_path, version_meta). Une version référencée mais
    indisponible n'est JAMAIS remplacée par un autre fichier : lève
    ContexteProjetIntrouvable.
    """
    chemin, meta = _resoudre_gpkg_versionne(db, proj)
    if chemin is not None:
        return Path(chemin), meta or {}
    raise ContexteProjetIntrouvable(
        (meta or {}).get("erreur", "GeoPackage indisponible pour ce projet."))


def executer_en_async(
    db: Session,
    *,
    org_id: str,
    project_id: Optional[str] = None,
    cluster_id: Any = None,
    parameters: Optional[Dict[str, Any]] = None,
    simulation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Exécute une simulation SWMM pour le worker Celery via le service métier
    unique. Rejoue la même chaîne que POST /simulations/run :

      identité (org/projet/cluster) → GPKG versionné → scénario BMS →
      MoteurSWMM (PySWMM) → cache .simulation_cache → ligne Simulation →
      ResultStore (result.json / model.inp / report.rpt + manifeste).

    `parameters` suit le contrat SimulationCreate (scenario_pluie,
    duree_heures, bms_*, buffer_m, typologie_sol, ...). Les clés d'identité
    (org_id, project_id, simulation_id, cluster_id) sont forcées depuis le
    contexte vérifié — jamais écrasables par les paramètres utilisateur.

    Lève ContexteProjetIntrouvable / ValueError sur toute incohérence
    d'identité ou d'intrant ; les erreurs du moteur se propagent après
    marquage de la Simulation en 'failed'.
    """
    from api.models import Organization, Project, Cluster, Simulation

    params_bruts = dict(parameters or {})

    # 1. Identité organisation — rechargée depuis la base, jamais déduite
    org = db.get(Organization, org_id)
    if org is None:
        raise ContexteProjetIntrouvable(
            f"Organisation introuvable : {org_id}")

    # 2. Projet explicite rattaché à l'organisation
    if not project_id:
        raise ContexteProjetIntrouvable(
            "project_id explicite requis pour l'exécution asynchrone.")
    proj = db.get(Project, project_id)
    if (proj is None or getattr(proj, "org_id", None) != org_id
            or getattr(proj, "is_archived", False)):
        raise ContexteProjetIntrouvable(
            f"Projet {project_id} introuvable ou non autorisé pour {org_id}.")

    # 3. GPKG versionné : snapshot exact, jamais de repli inter-versions
    gpkg_path, version_meta = resoudre_gpkg_pour_projet(db, proj)

    # 4. Cluster/bassin : doit appartenir au projet ET à l'organisation
    cluster_id_effectif = cluster_id if cluster_id is not None else params_bruts.get("cluster_id")
    if cluster_id_effectif is None:
        raise ValueError(
            "Sectorisation requise : cluster_id (ou bassin) obligatoire "
            "avant simulation SWMM.")
    try:
        cluster = db.get(Cluster, int(cluster_id_effectif))
    except (TypeError, ValueError):
        cluster = None
    if (cluster is None or getattr(cluster, "org_id", None) != org_id
            or str(getattr(cluster, "network_id", "")) != str(project_id)):
        raise ValueError(
            f"Cluster {cluster_id_effectif} incohérent avec le projet "
            f"{project_id} / organisation {org_id}.")

    # 5. Ligne Simulation : existante (créée par la route, id = job_id) ou
    #    créée à la demande — toujours rattachée à org/projet vérifiés.
    sim = db.get(Simulation, simulation_id) if simulation_id else None
    if sim is not None:
        if (getattr(sim, "org_id", None) not in (None, org_id)
                or (getattr(sim, "project_id", None)
                    and str(sim.project_id) != str(project_id))):
            raise ValueError(
                f"Simulation {simulation_id} incohérente avec le contexte "
                f"org={org_id} projet={project_id}.")
    if sim is None:
        sim = Simulation(
            id=simulation_id or str(uuid.uuid4()),
            org_id=org_id,
            project_id=project_id,
            status="running",
            scenario_pluie=str(params_bruts.get("scenario_pluie", "pluie_decennale")),
            duree_heures=float(params_bruts.get("duree_heures", 24.0)),
        )
        db.add(sim)
        db.commit()

    # 6. Contrat de paramètres moteur (noms SimulationRunRequest) —
    #    identité retirée des paramètres utilisateur.
    params_exec = dict(params_bruts)
    for cle_identite in ("org_id", "project_id", "simulation_id",
                         "network_id", "swmm_bin"):
        params_exec.pop(cle_identite, None)
    params_exec["scenario_key"] = (
        params_exec.pop("scenario_pluie", None)
        or params_exec.get("scenario_key")
        or "pluie_decennale"
    )
    params_exec["cluster_id"] = cluster_id_effectif

    # 7. Empreinte canonique + exécution via le MOTEUR UNIQUE (PySWMM)
    from types import SimpleNamespace
    _ns = SimpleNamespace(**{
        k: v for k, v in params_exec.items()
        if not isinstance(v, (dict, list)) or k == "raccordements_orphelins"
    })
    param_hash, params_dict = generer_cle_cache_simulation(gpkg_path, _ns)

    debut = datetime.now(timezone.utc)
    try:
        resultat = executer_moteur_swmm(
            gpkg_path, params_exec, execution_mode="celery")
    except Exception:
        sim.status = "failed"
        db.commit()
        raise
    execution_time = round(
        (datetime.now(timezone.utc) - debut).total_seconds(), 2)

    # 8. Enrichissement provenance/contexte (identique au chemin synchrone)
    resultat["source_gpkg"] = str(gpkg_path.resolve())
    resultat["project_name"] = proj.name or gpkg_path.stem
    resultat["param_hash"] = param_hash
    prov = resultat.setdefault("provenance", {})
    prov["gpkg_version_id"] = version_meta.get("version_id")
    prov["gpkg_sha256"] = version_meta.get("sha256")
    prov["gpkg_storage_kind"] = version_meta.get("storage_kind")
    prov["execution_mode"] = "celery"
    if getattr(cluster, "exutoire_noeud", None):
        from api.services.gpkg_versions import exutoire_present_dans_gpkg
        prov["coherence"] = {
            "exutoire_noeud": cluster.exutoire_noeud,
            "exutoire_present_dans_version": exutoire_present_dans_gpkg(
                gpkg_path, cluster.exutoire_noeud),
            "bassin_ref": getattr(cluster, "bassin_ref", None),
        }

    # 9. Cache de calcul + ligne Simulation (même format que le synchrone)
    cache_file = get_cache_simulation_file(gpkg_path, cluster_id_effectif, param_hash)
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False)
    except Exception as e:
        logger.error("Cache simulation async non écrit (%s) : %s", cache_file, e)

    kpis_summary = {
        "param_hash": param_hash,
        "cluster_id": cluster_id_effectif,
        "scenario_key": params_dict.get("scenario_key"),
        "parameters": params_dict,
        "peak_outflow_m3s": resultat.get("peak_outflow_m3s"),
        "routing_continuity_error_pct": resultat.get("routing_continuity_error_pct"),
        "flooded_nodes_count": resultat.get("flooded_nodes_count", 0),
        "provenance": resultat.get("provenance"),
        "execution_mode": "celery",
        "job_id": sim.id,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }
    sim.status = "completed"
    sim.name = f"SWMM_{proj.name}_{cluster_id_effectif}_{params_dict.get('scenario_key', 'pluie')}"
    sim.scenario_pluie = str(params_dict.get("scenario_key", "pluie_decennale"))
    sim.duree_heures = float(params_dict.get("duree_heures") or 24.0)
    sim.results_s3_key = str(cache_file.resolve())
    sim.gpkg_version_id = version_meta.get("version_id") if proj else None
    sim.gpkg_sha256 = version_meta.get("sha256")
    sim.bassin_ref = getattr(cluster, "bassin_ref", None)
    sim.exutoire_noeud = getattr(cluster, "exutoire_noeud", None)
    sim.summary_kpis = kpis_summary
    sim.execution_time_seconds = execution_time
    db.commit()

    # 10. ResultStore : artefacts permanents + manifeste (identique au synchrone)
    statut_store = _persister_resultats_store(sim, resultat)
    try:
        kpis = dict(sim.summary_kpis or {})
        kpis["result_store"] = statut_store
        sim.summary_kpis = kpis
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("Statut ResultStore async non persisté : %s", e)

    return {
        "simulation_id": sim.id,
        "job_id": sim.id,
        "org_id": org_id,
        "project_id": project_id,
        "cluster_id": cluster_id_effectif,
        "param_hash": param_hash,
        "cache_file": str(cache_file.resolve()),
        "gpkg": {
            "path": str(gpkg_path),
            "version_id": version_meta.get("version_id"),
            "sha256": version_meta.get("sha256"),
            "storage_kind": version_meta.get("storage_kind"),
        },
        "result_store": statut_store,
        "execution_time_seconds": execution_time,
        "peak_outflow_m3s": resultat.get("peak_outflow_m3s"),
    }
