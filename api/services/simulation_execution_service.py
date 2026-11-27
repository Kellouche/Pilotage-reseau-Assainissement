# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Exécution des simulations : sauvegarde/persistance DB, moteur SWMM (PySWMM), réponse métier, contexte de simulation.
================================================================================
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from api.services.simulation_cache_service import (
    est_simulation_valide,
    get_cache_simulation_file,
    iter_fichiers_cache_simulation,
)
from api.services.simulation_resultat_service import charger_resultat_simulation

logger = logging.getLogger("swmm_platform.services.simulation_execution_service")


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

    # LOT P1.4.1 — même empreinte que le chemin de lecture : le nom de
    # fichier cache reste identique lecture/écriture.
    cache_file = get_cache_simulation_file(
        gpkg_path, cluster_id, param_hash,
        gpkg_sha256=(version_meta or {}).get("sha256"))

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
        # Fiabilité du modèle évaluée par l'agent garde-fou hydraulicien :
        # exposée dans summary_kpis pour les badges de la liste des simulations.
        _gf = ((resultat.get("agents_expertise") or {}).get("controle_modele_hydraulique") or {})
        kpis_summary = {
            "param_hash": param_hash,
            "cluster_id": cluster_id,
            "scenario_key": params_dict.get("scenario_key"),
            "parameters": params_dict,
            "peak_outflow_m3s": resultat.get("peak_outflow_m3s"),
            "routing_continuity_error_pct": resultat.get("routing_continuity_error_pct"),
            "flooded_nodes_count": resultat.get("flooded_nodes_count", 0),
            "provenance": resultat.get("provenance"),
            "fiabilite_modele": _gf.get("fiabilite_modele"),
            "fiabilite_anomalies": _gf.get("nb_anomalies", 0),
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


def supprimer_simulation(simulation: Any, db: Session) -> Dict[str, Any]:
    """
    Supprime définitivement une simulation : ligne DB, fichier cache
    disque et artefacts ResultStore (result.json / model.inp / report.rpt).

    Retourne un dictionnaire de statut. La suppression DB est la seule
    étape bloquante : un échec des artefacts est consigné mais n'empêche
    pas le retrait de la ligne (cohérence avec la persistance tolérante).
    """
    statut: Dict[str, Any] = {"db": False, "cache": False, "artefacts": 0}

    # 1. Artefacts permanents ResultStore (partitionnés par org/projet/sim)
    try:
        from api.services.result_store import ResultRef, ResultStore, ResultStoreError
        ref = ResultRef.depuis_simulation(simulation)
        store = ResultStore()
        n = store.store.delete_prefix(ResultStore.prefixe(ref))
        statut["artefacts"] = int(n or 0)
    except Exception as e:
        logger.warning("Suppression artefacts ResultStore impossible (sim %s): %s",
                       getattr(simulation, "id", "?"), e)

    # 2. Fichier cache disque (results_s3_key = chemin local du cache)
    try:
        cle = getattr(simulation, "results_s3_key", None)
        if cle:
            p = Path(str(cle))
            if p.is_file():
                p.unlink()
                statut["cache"] = True
    except Exception as e:
        logger.warning("Suppression cache disque impossible (sim %s): %s",
                       getattr(simulation, "id", "?"), e)

    # 3. Ligne DB (dernière étape : si elle échoue, tout est rollback)
    db.delete(simulation)
    db.commit()
    statut["db"] = True
    return statut


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
    Synchronise également la cohérence pluie-débit (méthode rationnelle).
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

    try:
        from src.domain.moteur_swmm.analyse_rapport import calculer_coherence_pluie_debit
        calculer_coherence_pluie_debit(resultat, resultat.get("meta") or {})
    except Exception as e:
        logger.warning("Impossible de recalculer la cohérence pluie-débit : %s", e)

    return resultat


def executer_moteur_swmm(
    gpkg_path: Path,
    params: Dict[str, Any],
    execution_mode: str = "sync",
    garde_fou_config: Optional[Dict[str, Any]] = None,
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
        pas_routage_sec=(params.get("pas_routage_sec")
                         if params.get("pas_routage_sec") is not None else 5),
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
        apports_dwf=params.get("apports_dwf"),
        execution_mode=execution_mode,
        garde_fou_config=garde_fou_config,
        elevations_terrain=params.get("altimetrie_elevations"),
        altimetrie_meta=params.get("altimetrie_meta"),
        cotes_validations=params.get("cotes_validations"),
        etat_reseau=params.get("etat_reseau"),
    )

    return corriger_pic_depuis_timeseries(resultat)


def construire_reponse_simulation(resultat: Dict[str, Any], cached: bool = False,
                                  simulation_id: Optional[str] = None) -> Dict[str, Any]:
    """Structure la réponse standardisée renvoyée au frontend."""
    message = (
        "Résultats restaurés instantanément depuis la sauvegarde (paramètres de simulation inchangés)."
        if cached
        else "Simulation hydrodynamique SWMM 5.2 exécutée avec succès."
    )
    node_res = resultat.get("node_results", {})
    inp_txt = resultat.get("inp_content")
    if inp_txt and node_res:
        try:
            from src.domain.moteur_swmm.analyse_rapport import enrichir_node_results_cotes_inp
            enrichir_node_results_cotes_inp(node_res, inp_txt)
        except Exception:
            pass
    return {
        "status": "success",
        "cached": cached,
        "message": message,
        "simulation_id": simulation_id or resultat.get("simulation_id"),
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
        # Raccourci de fiabilité du modèle (agent garde-fou hydraulicien)
        "fiabilite_modele": (
            ((resultat.get("agents_expertise") or {}).get("controle_modele_hydraulique") or {}).get("fiabilite_modele")
        ),
        "node_results": node_res,
        "conduit_results": resultat.get("conduit_results", {}),
        # Séries temporelles jointes UNIQUEMENT en mode instantané (cached) :
        # après « Afficher » sur une simulation de l'historique, le time-slider
        # les consomme directement depuis _dernierResultatSimulation. Sans
        # elles, l'API /timeseries re-résoudrait la simulation la plus
        # récente du bassin — pas forcément celle affichée.
        "timeseries": resultat.get("timeseries") if cached else None,
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
