# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Persistance et enrichissement des résultats de simulation (result_store, champs dérivés whitelistés).
================================================================================
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("swmm_platform.services.simulation_resultat_service")


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
