# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-11
Date de modification : 2026-11-27
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

# ---------------------------------------------------------------------------
# Facade de compatibilité — implémentations extraites en sous-modules
# (règle modularité ≤600 lignes) ; tous les noms historiques restent
# importables depuis `api.services.simulation_service`.
# ---------------------------------------------------------------------------
from api.services.simulation_cache_service import (  # noqa: F401
    MOTEUR_VERSION_INP,
    _cle_cache_gpkg,
    _repertoire_cache_simulation,
    _resoudre_gpkg_versionne,
    _sha256_gpkg,
    charger_cache_simulation,
    est_simulation_valide,
    generer_cle_cache_simulation,
    get_cache_simulation_file,
    iter_fichiers_cache_simulation,
    resoudre_gpkg_effectif_pour_projet,
    resoudre_gpkg_effectif_pour_projet_avec_meta,
)
from api.services.simulation_resultat_service import (  # noqa: F401
    CHAMPS_META_ENRICHISSABLES,
    CHAMPS_RESULTAT_ENRICHISSABLES,
    _CLE_HISTORIQUE_ENRICHI,
    _extraire_enrichissement,
    _fusionner_enrichissement,
    _kind_enrichi,
    charger_resultat_simulation,
    persister_resultat_simulation,
)
from api.services.simulation_execution_service import (  # noqa: F401
    ContexteSimulation,
    ContexteSimulationIntrouvable,
    ProjetAmbigu,
    _persister_resultats_store,
    _resultatdeclare_projet,
    charger_derniere_simulation_disque_ou_db,
    construire_reponse_simulation,
    corriger_pic_depuis_timeseries,
    executer_moteur_swmm,
    preparer_scenario_bms,
    sauvegarder_simulation,
    supprimer_simulation,
)
from api.services.simulation_contexte_service import (  # noqa: F401
    _joindre_gpkg,
    _ref_pour_simulation,
    _resoudre_projet_pour_simulation,
    _simulation_correspond_a_bassin,
    diagnostiquer_resultats_store,
    resoudre_simulation_courante,
    reprise_resultat_simulation,
)

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

def resoudre_contexte_projet(
    db: Session,
    org_id: Optional[str],
    project_id: Optional[str] = None,
    autoriser_demo: bool = False,
) -> ContexteProjet:
    """
    LOT P0.1 — Résout le projet actif et son GeoPackage source, STRICTEMENT
    dans le périmètre de l'organisation authentifiée.

    Règles :
      - `org_id` est OBLIGATOIRE : aucun contexte → ContexteProjetIntrouvable
        (plus de repli sur le premier projet de toute la base) ;
      - `project_id` explicite → le projet doit exister, appartenir à org_id
        et ne pas être archivé ;
      - sans `project_id` → exactement UN projet actif de l'org est toléré
        (compatibilité contrat existant) ; plusieurs → ProjetAmbigu (→ 409) ;
      - une organisation sans projet actif → ContexteSimulationIntrouvable,
        SAUF `autoriser_demo=True` (mode démo explicitement activé) qui
        retourne le GPKG data/demo_reseau.gpkg sans projet ;
      - un projet résolu mais sans GPKG exploitable → erreur explicite,
        JAMAIS de substitution par le réseau d'un autre projet.

    Étape 3B : si le projet a une version GPKG, le chemin retourné est le
    snapshot matérialisé et version_meta décrit la version capturée.
    """
    if not org_id:
        raise ContexteProjetIntrouvable("Contexte d'organisation requis.")

    proj = None
    try:
        proj = _resoudre_projet_pour_simulation(db, org_id, project_id)
    except ContexteSimulationIntrouvable:
        # Repli démo UNIQUEMENT si : aucun project_id explicite, mode démo
        # explicitement autorisé, et fichier de démonstration présent.
        if project_id is not None or not autoriser_demo:
            raise
        cand = Path("data/demo_reseau.gpkg")
        if cand.exists():
            return ContexteProjet(project=None, gpkg_path=cand,
                                  project_name="demo_reseau")
        raise

    project_name = proj.name
    chemin, vmeta = _resoudre_gpkg_versionne(db, proj)
    gpkg_path = None
    version_meta = None
    if chemin is not None:
        gpkg_path = Path(chemin)
        version_meta = vmeta
    elif getattr(proj, "gpkg_version_id", None):
        raise ContexteProjetIntrouvable(
            vmeta.get("erreur", "Version GPKG indisponible pour ce projet.")
        )
    elif proj.source_gpkg_key and Path(proj.source_gpkg_key).exists():
        gpkg_path = Path(proj.source_gpkg_key)

    if not gpkg_path or not gpkg_path.exists():
        raise ContexteProjetIntrouvable(
            "Réseau hydraulique introuvable pour ce projet.")

    return ContexteProjet(project=proj, gpkg_path=gpkg_path,
                          project_name=project_name, version_meta=version_meta)

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

    # 6bis. LOT P1.3/P1.4 — apports DWF actifs du projet (org/projet vérifiés
    #    ci-dessus), validés STRICTEMENT contre la version GPKG résolue à
    #    l'étape 3 : tout apport non réconcilié fait échouer le job avant
    #    génération INP et lancement moteur. `dwf_actif=False` dans les
    #    paramètres = désactivation explicite du scénario. L'empreinte
    #    entre dans la clé de cache.
    from api.services.apports_dwf_service import (
        preparer_apports_pour_simulation,
    )
    try:
        apports_dwf, info_cache_dwf = preparer_apports_pour_simulation(
            db, proj, dwf_actif=params_exec.get("dwf_actif"),
            version_meta=version_meta, gpkg_path=gpkg_path,
            dwf_compatibles_seulement=bool(params_exec.get("dwf_compatibles_seulement")),
            user_id=getattr(sim, "user_id", None))
    except Exception:
        sim.status = "failed"
        db.commit()
        raise
    params_exec["apports_dwf"] = apports_dwf

    # 6ter. Option C (SHP.md §7bis) — altimétrie terrain IDW : opt-in
    #    explicite, mêmes garde-fous que le chemin synchrone (couverture
    #    ≥ 95 %, artefact non périmé) ; échec → ValueError → job 'failed'.
    if params_exec.get("altimetrie_terrain"):
        from api.services import aux_altimetrie_service as _alt
        _alt_res = _alt.resoudre_elevations_terrain_pour_simulation(
            db, org_id, project_id,
            layer_id=params_exec.get("altimetrie_layer_id"))
        if _alt_res.get("statut") != "ok":
            raise ValueError(
                f"Altimétrie terrain refusée : {_alt_res.get('raison')}")
        params_exec["altimetrie_elevations"] = _alt_res["elevations"]
        params_exec["altimetrie_meta"] = _alt_res["meta"]

    # 7. Empreinte canonique + exécution via le MOTEUR UNIQUE (PySWMM)
    from types import SimpleNamespace
    _ns = SimpleNamespace(**{
        k: v for k, v in params_exec.items()
        if not isinstance(v, (dict, list)) or k == "raccordements_orphelins"
    })
    # LOT P1.4.1 — empreinte fraîche de la version résolue réutilisée
    # comme identité de contenu (un seul hash, valeur identique partout).
    _sha_gpkg_connu = (version_meta or {}).get("sha256")
    param_hash, params_dict = generer_cle_cache_simulation(
        gpkg_path, _ns, extra_params=info_cache_dwf,
        gpkg_sha256=_sha_gpkg_connu)

    debut = datetime.now(timezone.utc)
    try:
        try:
            from api.services.cotes_suspectes_service import obtenir_map_validations_projet
            vmap = obtenir_map_validations_projet(db, proj.id, proj.org_id)
            cotes_validees_dict = {
                nid: ent["profondeur"]["valeur_validee"]
                for nid, ent in vmap.items()
                if "profondeur" in ent and ent["profondeur"].get("statut") == "valide"
                and ent["profondeur"].get("valeur_validee") is not None
            }
            if cotes_validees_dict:
                params_exec["cotes_validations"] = cotes_validees_dict
        except Exception:
            pass
        resultat = executer_moteur_swmm(
            gpkg_path, params_exec, execution_mode="celery",
            garde_fou_config=getattr(proj, "garde_fou_config", None))
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
    if info_cache_dwf.get("apports_dwf_ignores"):
        prov_dwf = prov.setdefault("apports_dwf", {})
        existing_ignores = prov_dwf.get("ignores", [])
        prov_dwf["ignores"] = existing_ignores + [
            ig for ig in info_cache_dwf["apports_dwf_ignores"]
            if ig.get("id") not in {e.get("id") for e in existing_ignores}
        ]
    if params_exec.get("altimetrie_meta"):
        prov["altimetrie"] = {
            "mode": "terrain_idw",
            **params_exec["altimetrie_meta"],
            "nature": "estimee_interpolation_idw",
        }
    if getattr(cluster, "exutoire_noeud", None):
        from api.services.gpkg_versions import exutoire_present_dans_gpkg
        prov["coherence"] = {
            "exutoire_noeud": cluster.exutoire_noeud,
            "exutoire_present_dans_version": exutoire_present_dans_gpkg(
                gpkg_path, cluster.exutoire_noeud),
            "bassin_ref": getattr(cluster, "bassin_ref", None),
        }

    # 9. Cache de calcul + ligne Simulation (même format que le synchrone)
    cache_file = get_cache_simulation_file(
        gpkg_path, cluster_id_effectif, param_hash,
        gpkg_sha256=_sha_gpkg_connu)
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