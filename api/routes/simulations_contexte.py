# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Helpers de resolution de contexte et d'autorisation partagees par les routeurs simulations (extraits de simulations.py).
================================================================================
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.core.security import get_tenant_context, TenantContext
from api.models import Project
from api.services.simulation_service import (
    ContexteSimulation,
    ContexteSimulationIntrouvable,
    ProjetAmbigu,
    _resoudre_projet_pour_simulation,
    _resultatdeclare_projet,
    resoudre_gpkg_effectif_pour_projet as _resoudre_gpkg_effectif_pour_projet,
    resoudre_simulation_courante,
)

logger = logging.getLogger(__name__)


def _org_id_requete(tenant) -> str:
    """
    LOT P0.1 — organisation obligatoire pour toute route sensible de
    simulation. `tenant` est résolu par `get_tenant_context` (401 HTTP
    avant d'atteindre la route) ; ce garde-fou couvre aussi les appels
    internes directs sans contexte authentifié.
    """
    org_id = getattr(tenant, "org_id", None)
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise.")
    return org_id


def _mode_demo_reseau() -> bool:
    """
    LOT P0.1 — mode démo explicitement activé via DRAINPILOT_MODE_DEMO_RESEAU.
    Désactivé par défaut : le repli data/demo_reseau.gpkg n'est JAMAIS
    un contournement de l'authentification ni une substitution inter-projets.
    """
    try:
        from config.settings import MODE_DEMO_RESEAU
        return bool(MODE_DEMO_RESEAU)
    except Exception:
        return False


def _gpkg_demo_autorise() -> Optional[Path]:
    """GPKG de démonstration si et seulement si le mode démo est activé."""
    if _mode_demo_reseau():
        cand = Path("data/demo_reseau.gpkg")
        if cand.exists():
            return cand
    return None


def _identite_bassin_du_cache(gpkg_path: Optional[Path], cluster_id: str) -> dict:
    """
    Résout l'identité métier stable d'un bassin depuis le cache de
    sectorisation `<gpkg>.clusters_cache.json` : nom + exutoire_id +
    bassin_ref. Les simulations sont enregistrées dans l'espace
    exutoire_noeud/bassin_ref, alors que le dropdown envoie le
    cluster_id positionnel — ce pont est indispensable pour retrouver
    la bonne simulation (ex. cluster 87 « Cite 80 Logts » → exutoire 234).
    """
    if not gpkg_path or cluster_id is None:
        return {}
    cache = Path(gpkg_path).with_suffix(".clusters_cache.json")
    if not cache.exists():
        return {}
    try:
        import json as _json
        data = _json.loads(cache.read_text(encoding="utf-8"))
    except Exception:
        return {}
    cible = str(cluster_id).strip()
    cible_low = cible.lower()
    prefixed = cible_low.startswith("exutoire:") or cible_low.startswith("bassin:")
    cle = cible.split(":", 1)[1] if prefixed else cible
    cle_low = cle.lower()

    features = [
        f for f in (data.get("bassins_geojson") or {}).get("features", [])
        if (f.get("properties") or {}).get("type") == "bassin_urbain"
    ]

    def _ident(p: dict) -> dict:
        ex = p.get("exutoire_id")
        bref = p.get("bassin_ref") or (f"exutoire:{ex}" if ex else None)
        nb_reg = int(p.get("nb_regards") or 0)
        nb_cond = int(p.get("nb_conduites") or 0)
        surf = float(p.get("surface_ha") or 0.0)
        est_isole = not (nb_reg > 0 or nb_cond > 2 or surf > 0.45)
        return {
            "nom": p.get("nom"),
            "exutoire_id": ex,
            "bassin_ref": bref,
            "nb_regards": nb_reg,
            "nb_conduites": nb_cond,
            "surface_ha": surf,
            "est_isole": est_isole,
            "cluster_id": p.get("cluster_id") or p.get("id_bassin"),
        }

    # EQUIVALENCE DES ESPACES D'IDENTIFIANTS :
    if prefixed:
        for f in features:
            p = f.get("properties") or {}
            bref = str(p.get("bassin_ref") or "").strip().lower()
            ex = str(p.get("exutoire_id") or "").strip().lower()
            if (bref and bref == cible_low) or (ex and ex == cle_low):
                return _ident(p)
            if str(p.get("cluster_id") or "").strip() == cle or str(p.get("id_bassin") or "").strip() == cle:
                return _ident(p)
        return {}

    # 1. Correspondance positionnelle (cluster_id / id_bassin)
    for f in features:
        p = f.get("properties") or {}
        if (str(p.get("cluster_id") or "").strip() == cle
                or str(p.get("id_bassin") or "").strip() == cle):
            return _ident(p)

    # 2. Correspondance exutoire_id ou bassin_ref
    for f in features:
        p = f.get("properties") or {}
        ex = str(p.get("exutoire_id") or "").strip().lower()
        bref = str(p.get("bassin_ref") or "").strip().lower()
        if (ex and ex == cle_low) or (bref and bref == cle_low):
            return _ident(p)

    # 3. Correspondance par nom complet (ex: "Exutoire OUT_55")
    for f in features:
        p = f.get("properties") or {}
        nom = str(p.get("nom") or "").strip().lower()
        nom_ex = str(p.get("nom_exutoire") or "").strip().lower()
        if (nom and nom == cle_low) or (nom_ex and nom_ex == cle_low):
            return _ident(p)

    # 4. Correspondance format "Bassin X" (ex: "Bassin 1")
    if cle_low.startswith("bassin "):
        sub_cle = cle_low.replace("bassin ", "").strip()
        for f in features:
            p = f.get("properties") or {}
            if (str(p.get("cluster_id") or "").strip().lower() == sub_cle
                    or str(p.get("id_bassin") or "").strip().lower() == sub_cle):
                return _ident(p)

    # 5. Correspondance par inclusion de l'exutoire_id (ex: "out_55" dans "exutoire out_55")
    for f in features:
        p = f.get("properties") or {}
        ex = str(p.get("exutoire_id") or "").strip().lower()
        if ex and ex in cle_low.replace(" ", "_").split("_"):
            return _ident(p)
    return {}


def _contexte_simulation_autorise(db: Session, tenant, cluster_id=None,
                                  simulation_id=None, project_id=None):
    """
    Étape 3D.2 — résout la simulation AUTORISÉE pour le tenant courant via
    le service contextuel (org_id/project_id stricts, jamais la globale
    _DERNIERE_SIMULATION). Retourne un ContexteSimulation ou None si aucune
    simulation n'est autorisée pour ce périmètre.
    """
    if db is None:
        return None
    org_id = tenant.org_id if (tenant and hasattr(tenant, "org_id") and tenant.org_id) else None
    try:
        return resoudre_simulation_courante(
            db,
            org_id=org_id,
            project_id=project_id,
            simulation_id=simulation_id,
            cluster_id=cluster_id,
            resoudre_gpkg=False,
        )
    except (ContexteSimulationIntrouvable, ProjetAmbigu) as e:
        logger.info("Aucune simulation autorisée pour ce contexte : %s", e)
        return None


def _projet_pour_export_repli(db: Session, tenant, project_id: Optional[str] = None):
    """
    Correctif 3C/R2 — résolution stricte du projet pour les replis disque
    des téléchargements INP/RPT : jamais de `.first()` ; plusieurs projets
    possibles → 409 explicite ; `project_id` explicite invalide ou hors
    organisation → 404 ; aucun projet → None (repli démo uniquement).
    """
    from api.services.simulation_service import _resoudre_projet_pour_simulation
    org_id = tenant.org_id if (tenant and hasattr(tenant, "org_id") and tenant.org_id) else None
    try:
        return _resoudre_projet_pour_simulation(db, org_id, project_id)
    except ProjetAmbigu as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContexteSimulationIntrouvable:
        if project_id:
            raise HTTPException(
                status_code=404, detail="Projet introuvable ou non autorisé.")
        return None


def _gpkg_partage_entre_projets(db: Session, gpkg_path: Path, proj) -> bool:
    """
    Correctif 3C/R1 — True si un AUTRE projet actif peut résoudre le même
    contenu GPKG (snapshot matérialisé identique ou SHA-256 identique).
    Dans ce cas, un fichier `.simulation_cache` non estampillé a un
    propriétaire ambigu et ne doit pas être servi.
    """
    from api.models import Project
    from api.services.gpkg_versions import GPKG_CACHE_DIR, sha256_fichier

    def _sha_effectif(p: Path) -> Optional[str]:
        try:
            if p.parent == Path(GPKG_CACHE_DIR):
                return p.stem  # snapshot matérialisé : nom de fichier = sha256
            return sha256_fichier(p)
        except Exception:
            return None

    sha_cible = _sha_effectif(gpkg_path)
    if not sha_cible:
        return True  # unicité invérifiable → prudence
    for autre in db.query(Project).filter(
            Project.is_archived.is_(False), Project.id != proj.id).all():
        try:
            p2 = _resoudre_gpkg_effectif_pour_projet(db, autre)
        except Exception:
            continue
        if p2 is None:
            continue
        if _sha_effectif(p2) == sha_cible:
            return True
    return False


def _fichier_cache_appartenant(db: Session, proj, gpkg_path: Path,
                               data: Dict[str, Any]) -> bool:
    """
    Correctif 3C/R1 — propriété d'un fichier `.simulation_cache` avant tout
    service dans les téléchargements :
      - `proj` résolu : estampille project_id/org_id contradictoire → refus ;
        estampille conforme → accepté ; non estampillé (legacy) → accepté
        seulement si le GPKG n'est pas partagé avec un autre projet ;
      - `proj` absent (mode démo sans projet) : seuls les fichiers SANS
        estampille sont admissibles — une estampille vers un projet ne
        peut pas être vérifiée → refus par prudence.
    Le nom de fichier et `cluster_id` ne sont JAMAIS une preuve de propriété.
    """
    from api.services.simulation_service import _resultatdeclare_projet
    if not isinstance(data, dict):
        return False
    meta = data.get("meta") or {}
    estampille = bool(
        meta.get("project_id") or meta.get("org_id")
        or data.get("project_id") or data.get("org_id"))
    if proj is None:
        return not estampille
    if not _resultatdeclare_projet(data, proj):
        return False
    if estampille:
        return True
    return not _gpkg_partage_entre_projets(db, gpkg_path, proj)


def _signaler_mismatch_version_gpkg(data: Dict[str, Any], ctx: Any, proj: Any) -> None:
    """
    Compare la version GPKG ayant produit la simulation restaurée avec la
    version COURANTE du projet. En cas de divergence, marque
    ``meta.gpkg_version_mismatch`` pour que le frontend puisse avertir
    l'utilisateur : les entités réseau/bassins affichées correspondent à la
    version courante, pas forcément à celle de la simulation.
    """
    try:
        if not isinstance(data, dict):
            return
        vid_sim = None
        if ctx is not None and getattr(ctx, "simulation", None) is not None:
            vid_sim = getattr(ctx.simulation, "gpkg_version_id", None)
        if vid_sim is None and isinstance(getattr(ctx, "meta_version", None), dict):
            vid_sim = ctx.meta_version.get("version_id")
        if vid_sim is None:
            vid_sim = ((data.get("provenance") or {}).get("gpkg_version_id"))
        vid_projet = getattr(proj, "gpkg_version_id", None) if proj is not None else None
        if vid_sim and vid_projet and str(vid_sim) != str(vid_projet):
            meta = data.setdefault("meta", {})
            if isinstance(meta, dict):
                meta["gpkg_version_mismatch"] = True
                meta["gpkg_version_sim_id"] = str(vid_sim)
                meta["gpkg_version_courante_id"] = str(vid_projet)
        # Identité métier stable de la simulation : le frontend doit
        # distinguer les bassins homonymes et les espaces d'identifiants
        # (cluster_id positionnel vs exutoire_noeud / bassin_ref) — sans
        # ces champs, un nom seul ne suffit jamais à identifier un bassin.
        sim = getattr(ctx, "simulation", None) if ctx is not None else None
        if sim is not None:
            meta = data.setdefault("meta", {})
            if isinstance(meta, dict):
                _bref = getattr(sim, "bassin_ref", None)
                _ex = getattr(sim, "exutoire_noeud", None)
                if _bref:
                    meta["bassin_ref"] = str(_bref)
                if _ex:
                    meta["exutoire_noeud"] = str(_ex)
    except Exception:
        pass
