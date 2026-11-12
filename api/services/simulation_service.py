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

    # 1. Sauvegarde du JSON complet sur disque
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False)
    except Exception as e:
        logger.error("Erreur lors de l'écriture du cache simulation sur disque: %s", e)

    # 2. Enregistrement en base de données SQLAlchemy
    try:
        org_id = tenant.org_id if (tenant and hasattr(tenant, "org_id")) else None
        project_id = proj.id if proj else None
        project_name = proj.name if proj else gpkg_path.stem

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
    except Exception as e:
        db.rollback()
        logger.warning("Avertissement: enregistrement de la simulation en DB impossible: %s", e)

    return cache_file


def charger_derniere_simulation_disque_ou_db(gpkg_path: Path, db: Session, proj: Any = None) -> Optional[Dict[str, Any]]:
    """
    Recherche la simulation la plus récente enregistrée pour ce GeoPackage
    en vérifiant d'abord la table `simulations` en DB, puis le dossier `.simulation_cache/`.
    """
    from api.models import Simulation
    # 1. Vérifier la table Simulation
    try:
        query = db.query(Simulation).filter(Simulation.status == "completed")
        if proj:
            query = query.filter(Simulation.project_id == proj.id)
        last_sim = query.order_by(Simulation.created_at.desc()).first()
        if last_sim and last_sim.results_s3_key:
            p = Path(last_sim.results_s3_key)
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data and est_simulation_valide(data):
                    return data
    except Exception as e:
        logger.warning("Erreur interrogation table simulations: %s", e)

    # 2. Fallback dossier .simulation_cache/ (content-adressé + legacy)
    for fpath in iter_fichiers_cache_simulation(gpkg_path):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data and est_simulation_valide(data):
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
