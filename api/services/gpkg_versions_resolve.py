# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Resolution des versions GPKG pour simulation et lecture (snapshot, exutoire) (extrait de services/gpkg_versions.py)
================================================================================
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from api.services.gpkg_versions import (
    GpkgSimulationError,
    _MOTS_CLES_REGARDS,
    _MOTS_CLES_REJETS,
    _materialiser_version_versionnee,
    _version_existe,
    materialiser_version,
    sha256_fichier,
    version_disponible,
)

import logging

logger = logging.getLogger(__name__)


def resoudre_gpkg_pour_simulation(
    db: Session,
    project: Any,
    data_simulation: Optional[Dict[str, Any]],
) -> Tuple[Optional[Path], Dict[str, Any]]:
    """
    Étape 3C.0 — résout le GPKG EXACT ayant produit `data_simulation`
    (dict résultat JSON persisté — la globale `_DERNIERE_SIMULATION` a été
    supprimée en 3D.5).

    Ordre strict :
      1. `provenance.gpkg_version_id` → GpkgVersion validé dans le contexte
         projet/tenant → matérialisation atomique du snapshot ; si la ligne
         version a disparu, repli sur l'empreinte SHA-256 (jamais sur la
         version courante) ;
      2. `provenance.gpkg_sha256` → version (project_id, sha256) du projet,
         sinon `source_gpkg` si son empreinte réelle correspond ;
      3. `source_gpkg` si le fichier existe (provenance absente = legacy) ;
      4. rien de résoluble → (None, meta) : l'appelant applique le fallback
         legacy (GPKG courant du projet).

    Une provenance EXPLICITE mais irrésoluble (version absente ET empreinte
    invérifiable, incohérence tenant) lève GpkgSimulationError —
    jamais de substitution silencieuse par la version courante.
    """
    if not isinstance(data_simulation, dict):
        return None, {}

    prov = data_simulation.get("provenance") or {}
    version_id = prov.get("gpkg_version_id")
    sha_attendu = prov.get("gpkg_sha256")
    source_gpkg = data_simulation.get("source_gpkg")

    # 1. Version explicite
    version_id_perdu = False
    if version_id:
        from api.models import GpkgVersion
        version = db.get(GpkgVersion, version_id)
        if version is not None:
            chemin = _materialiser_version_versionnee(db, project, version)
            return chemin, {
                "version_id": version.id,
                "sha256": version.sha256,
                "storage_kind": version.storage_kind,
                "resolution": "gpkg_version_id",
                "materialized_path": str(chemin),
            }
        # Ligne GpkgVersion absente (ex. base réinitialisée alors que le
        # JSON persisté survit) : on ne substitue PAS la version courante,
        # on tente la vérification par empreinte SHA-256 ci-dessous.
        version_id_perdu = True

    # 2. Empreinte explicite sans version_id
    if sha_attendu:
        version = None
        if project is not None:
            version = _version_existe(db, project.id, sha_attendu)
        if version is not None:
            chemin = _materialiser_version_versionnee(db, project, version)
            return chemin, {
                "version_id": version.id,
                "sha256": version.sha256,
                "storage_kind": version.storage_kind,
                "resolution": "gpkg_sha256",
                "materialized_path": str(chemin),
            }
        # Pas de version enregistrée : le source_gpkg peut encore être le
        # bon contenu SI son empreinte réelle correspond à la provenance.
        if source_gpkg and Path(source_gpkg).exists():
            if sha256_fichier(Path(source_gpkg)) == sha_attendu:
                return Path(source_gpkg), {
                    "version_id": None,
                    "sha256": sha_attendu,
                    "storage_kind": "SOURCE_GPKG_VERIFIE",
                    "resolution": "source_gpkg_sha256",
                    "materialized_path": str(Path(source_gpkg).resolve()),
                }
        raise GpkgSimulationError(
            "Empreinte GPKG de la simulation sans version correspondante "
            "et source_gpkg absent ou divergent — substitution interdite."
        )

    # 3. Aucune provenance exploitable : legacy — source_gpkg si présent.
    #    Une provenance EXPLICITE irrésoluble (version_id perdu sans empreinte
    #    vérifiable) reste une erreur métier : pas de repli silencieux.
    if version_id_perdu:
        raise GpkgSimulationError(
            f"Version GPKG {version_id} de la simulation introuvable en base "
            "et empreinte SHA-256 absente ou invérifiable — substitution interdite."
        )
    if source_gpkg and Path(source_gpkg).exists():
        return Path(source_gpkg), {
            "version_id": None,
            "sha256": None,
            "storage_kind": "LEGACY_SIMULATION",
            "resolution": "source_gpkg_legacy",
            "materialized_path": str(Path(source_gpkg).resolve()),
        }

    # 4. Rien d'exploitable → fallback legacy à la charge de l'appelant
    return None, {}


def exutoire_present_dans_gpkg(gpkg_path: Path, exutoire_noeud: Optional[str]) -> Optional[bool]:
    """
    Vérification best-effort de cohérence : l'exutoire résolu (3A) figure-t-il
    comme identifiant de nœud dans le GPKG exact utilisé par la simulation ?
    Retourne True/False, ou None si indéterminable (jamais bloquant).
    """
    if not exutoire_noeud or not gpkg_path or not Path(gpkg_path).exists():
        return None
    cible = str(exutoire_noeud).strip()
    conn = None
    try:
        conn = sqlite3.connect(f"file:{Path(gpkg_path).as_posix()}?mode=ro", uri=True)
        tables = [r[0] for r in conn.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type='features'")]
        for table in tables:
            nom_bas = table.lower()
            if not any(m in nom_bas for m in _MOTS_CLES_REGARDS + _MOTS_CLES_REJETS):
                continue
            cols = [c[1] for c in conn.execute(f'PRAGMA table_info("{table}")')]
            # Colonnes candidates porteuses d'identifiants de nœuds
            candidates = [c for c in cols if c.lower() in (
                "id", "code", "nom", "origdonne", "noeud", "cle", "identifiant", "numero")]
            # Tolérance numérique : les codes GPKG sont souvent stockés en REAL
            # (ex. Code=3479.0) alors que la référence métier est '3479'.
            try:
                cible_num = float(cible)
                numeric = True
            except (TypeError, ValueError):
                numeric = False
            for col in candidates:
                clauses = ['CAST("{col}" AS TEXT) = ?'.format(col=col)]
                params_list = [[cible]]
                if numeric:
                    clauses.append('CAST("{col}" AS REAL) = ?'.format(col=col))
                    params_list.append([cible_num])
                for clause, params in zip(clauses, params_list):
                    try:
                        row = conn.execute(
                            f'SELECT 1 FROM "{table}" WHERE {clause} LIMIT 1',
                            params,
                        ).fetchone()
                        if row:
                            return True
                    except sqlite3.Error:
                        continue
        return False
    except Exception:
        return None
    finally:
        if conn is not None:
            conn.close()


def resoudre_version_pour_simulation(
    db: Session,
    project: Any,
) -> Tuple[Optional[Path], Dict[str, Any]]:
    """
    Résout LE GPKG à utiliser pour une simulation du projet, en une seule capture :

    - version courante présente → matérialisation atomique du snapshot →
      meta {version_id, sha256, storage_kind, materialized_path} ;
    - pas de version (projet legacy) → source_gpkg_key si existant →
      sha256 calculé à la volée (empreinte honnête, version_id=None) ;
    - rien de disponible → (None, meta avec erreur).

    Le moteur reçoit exclusivement le chemin retourné — jamais source_gpkg_key
    directement lorsqu'une version existe.
    """
    version_id = getattr(project, "gpkg_version_id", None)

    if version_id:
        from api.models import GpkgVersion
        version = db.get(GpkgVersion, version_id)
        if version is None:
            return None, {"erreur": f"Version GPKG {version_id} introuvable en base"}
        # Cohérence tenant : la version DOIT appartenir au projet
        if version.project_id != project.id or version.org_id != project.org_id:
            return None, {"erreur": "Version GPKG incohérente avec le projet (tenant)"}
        ok, raison = version_disponible(version)
        if not ok:
            return None, {
                "erreur": f"Version GPKG indisponible (UNAVAILABLE) : {raison}",
                "version_id": version.id,
                "sha256": version.sha256,
                "storage_kind": version.storage_kind,
            }
        try:
            chemin = materialiser_version(version)
        except Exception as e:
            return None, {
                "erreur": f"Matérialisation GPKG impossible : {e}",
                "version_id": version.id,
                "sha256": version.sha256,
            }
        return chemin, {
            "version_id": version.id,
            "sha256": version.sha256,
            "storage_kind": version.storage_kind,
            "materialized_path": str(chemin),
        }

    # Chemin legacy : source_gpkg_key (compatibilité transition)
    legacy_key = getattr(project, "source_gpkg_key", None)
    if legacy_key:
        p = Path(legacy_key)
        if p.exists():
            return p, {
                "version_id": None,
                "sha256": sha256_fichier(p),
                "storage_kind": "LEGACY",
                "materialized_path": str(p.resolve()),
            }
    return None, {"erreur": "Aucun GeoPackage disponible pour ce projet"}


def resoudre_snapshot_pour_lecture(
    db: Session,
    project: Any,
    snapshot: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Résout le snapshot GPKG à utiliser pour une LECTURE cartographique.

    `snapshot` accepte indifféremment :
      - un gpkg_version_id (UUID) ;
      - un sha256 complet ou préfixe (>= 8 caractères, hexadécimal) ;
      - None / chaîne vide → version COURANTE du projet (comportement
        historique de tous les endpoints de lecture).

    Retourne un contexte normalisé :
      {
        "path": Path,                # fichier matérialisé (cache sha256)
        "version_id": str|None,
        "sha256": str|None,
        "est_version_courante": bool,
        "libelle": str,              # « réseau du … » / nom de fichier
        "nb_regards": int|None,
        "nb_conduites": int|None,
        "storage_kind": str,
      }

    Règles strictes (jamais de substitution silencieuse) :
      - snapshot explicite introuvable / hors projet / indisponible
        → GpkgSimulationError (l'appelant traduit en 404/409) ;
      - la version DOIT appartenir à (project.id, project.org_id) ;
      - le sha retourné est TOUJOURS celui de la version résolue —
        c'est la clé de comparaison INV-2 côté client.
    """
    from api.models import GpkgVersion

    vid_courant = getattr(project, "gpkg_version_id", None)
    org_id = getattr(project, "org_id", None)

    # --- Snapshot explicite -------------------------------------------------
    if snapshot and str(snapshot).strip():
        ident = str(snapshot).strip()
        version = None

        # 1) Identifiant version (UUID) — vérifié prioritaire si format UUID
        if len(ident) >= 32 and "-" in ident:
            version = db.query(GpkgVersion).filter(
                GpkgVersion.id == ident,
                GpkgVersion.project_id == project.id,
                GpkgVersion.org_id == org_id,
            ).first()
            if version is None:
                raise GpkgSimulationError(
                    f"Version GPKG {ident[:12]}… introuvable pour ce projet.")
        else:
            # 2) Empreinte SHA-256 (complète ou préfixe raisonnable)
            empreinte = ident.lower()
            if len(empreinte) < 8:
                raise GpkgSimulationError(
                    "Identifiant de snapshot trop court (sha256 >= 8 caractères).")
            candidats = db.query(GpkgVersion).filter(
                GpkgVersion.project_id == project.id,
                GpkgVersion.org_id == org_id,
                GpkgVersion.sha256.like(f"{empreinte}%"),
            ).limit(2).all()
            if not candidats:
                raise GpkgSimulationError(
                    f"Aucun snapshot GPKG ne correspond à « {ident[:16]}… » "
                    "pour ce projet.")
            if len(candidats) > 1:
                raise GpkgSimulationError(
                    "Empreinte de snapshot ambiguë — préciser davantage.")
            version = candidats[0]

        ok, raison = version_disponible(version)
        if not ok:
            raise GpkgSimulationError(
                f"Snapshot GPKG indisponible : {raison}")
        try:
            chemin = materialiser_version(version)
        except Exception as e:
            raise GpkgSimulationError(
                f"Matérialisation du snapshot impossible : {e}")

        return {
            "path": chemin,
            "version_id": version.id,
            "sha256": version.sha256,
            "est_version_courante": (version.id == vid_courant),
            "libelle": _libelle_version(version),
            "nb_regards": version.nb_regards,
            "nb_conduites": version.nb_conduites,
            "storage_kind": version.storage_kind,
        }

    # --- Version courante (défaut = comportement existant) -------------------
    chemin, meta = resoudre_version_pour_simulation(db, project)
    if chemin is None:
        raise GpkgSimulationError(
            meta.get("erreur") or "Aucun GeoPackage disponible pour ce projet.")
    # meta peut être legacy (sha256 calculé à la volée, version_id=None)
    sha = meta.get("sha256")
    version_id = meta.get("version_id")
    nb_regards = nb_conduites = None
    libelle = "réseau actuel"
    if version_id:
        version = db.get(GpkgVersion, version_id)
        if version is not None:
            nb_regards, nb_conduites = version.nb_regards, version.nb_conduites
            libelle = _libelle_version(version)
    elif sha:
        libelle = f"réseau ({sha[:12]}…)"
    return {
        "path": chemin,
        "version_id": version_id,
        "sha256": sha,
        "est_version_courante": True,
        "libelle": libelle,
        "nb_regards": nb_regards,
        "nb_conduites": nb_conduites,
        "storage_kind": meta.get("storage_kind"),
    }


def _libelle_version(version: Any) -> str:
    """Libellé humain d'un snapshot : nom de fichier + date + volumes."""
    parts = []
    nom = getattr(version, "filename_original", None)
    if nom:
        parts.append(str(nom))
    else:
        parts.append(f"version {str(version.id)[:8]}")
    try:
        if getattr(version, "created_at", None) is not None:
            parts.append(version.created_at.strftime("%d/%m/%Y"))
    except Exception:
        pass
    nb_r, nb_c = getattr(version, "nb_regards", None), getattr(version, "nb_conduites", None)
    if nb_r is not None or nb_c is not None:
        parts.append(f"{nb_r or 0} regards / {nb_c or 0} conduites")
    return " — ".join(parts)
