# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : Résolution unifiée des références de bassins versants (étape 3A).

Fournit l'unique point d'entrée pour traduire une référence entrante
(bassin_ref, Cluster.id ORM, exutoire_noeud, nom, identifiant ordinal legacy)
en une résolution explicite et non ambiguë. Aucune association arbitraire :
toute ambiguïté ou absence produit un statut d'erreur explicite.
================================================================================
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger("swmm_platform.services.bassin_reference")

PREFIX_EXUTOIRE = "exutoire:"
PREFIX_MANUEL = "manuel:"


@dataclass
class ResolutionBassin:
    """Résultat explicite de la résolution d'une référence de bassin."""
    entree: str
    statut: str  # RESOLU_ORM | RESOLU_GPKG | RESOLU_MANUEL | AMBIGU | NON_TROUVE
    source: str  # basin_ref | cluster_id | exutoire_noeud | nom | ordinal | manuel
    bassin_ref: Optional[str] = None
    exutoire_noeud: Optional[str] = None
    cluster_orm_id: Optional[int] = None
    cluster_nom: Optional[str] = None
    moteur_cluster_id: Optional[Any] = field(default=None)
    detail: str = ""

    @property
    def cluster_id_moteur(self) -> Optional[Any]:
        """Valeur à transmettre à MoteurSWMM.cluster_id (espace GPKG)."""
        if self.moteur_cluster_id is not None:
            return self.moteur_cluster_id
        if self.exutoire_noeud:
            return self.exutoire_noeud
        return self.entree


def _norm(s: Any) -> str:
    return str(s).strip().lower() if s is not None else ""


def _clusters_du_projet(db: Session, network_id: Optional[str]) -> List[Any]:
    """Clusters ORM rattachés au projet (network_id = projects.id)."""
    if not network_id:
        return []
    return list(
        db.execute(select(_modele_cluster()).where(_modele_cluster().network_id == network_id)).scalars().all()
    )


def _modele_cluster():
    from api.models import Cluster
    return Cluster


def _query_clusters(db: Session, *criteres):
    """Clusters ORM correspondant à TOUS les critères (ET logique)."""
    Cluster = _modele_cluster()
    stmt = select(Cluster)
    for critere in criteres:
        if critere is not None:
            stmt = stmt.where(critere)
    return list(db.execute(stmt).scalars().all())


def _critere_projet(Cluster, network_id):
    """Portée projet : réseau explicite, ou clusters non attribués (legacy NULL)
    lorsque aucun projet n'est résolu — jamais de recherche globale."""
    if network_id:
        return Cluster.network_id == network_id
    return Cluster.network_id.is_(None)


def _cluster_par_bassin_ref(db: Session, network_id: Optional[str], ref: str):
    Cluster = _modele_cluster()
    return _query_clusters(db, Cluster.bassin_ref == ref, _critere_projet(Cluster, network_id))


def _cluster_par_exutoire(db: Session, network_id: Optional[str], ex_id: str):
    Cluster = _modele_cluster()
    return _query_clusters(db, Cluster.exutoire_noeud == ex_id, _critere_projet(Cluster, network_id))


def _cluster_par_id(db: Session, network_id: Optional[str], cid: int):
    Cluster = _modele_cluster()
    return _query_clusters(db, Cluster.id == cid, _critere_projet(Cluster, network_id))


def _cluster_par_nom(db: Session, network_id: Optional[str], nom: str):
    Cluster = _modele_cluster()
    return _query_clusters(db, Cluster.nom == nom, _critere_projet(Cluster, network_id))


def _resoudre_depuis_cache_gpkg(gpkg_path: Optional[Path], valeur: Any) -> Optional[Dict[str, Any]]:
    """
    Résolution contextuelle (jamais persistée) d'un identifiant ordinal
    legacy (cluster_id i+1 / id_bassin) via le .clusters_cache.json du projet.
    """
    if not gpkg_path:
        return None
    cache = gpkg_path.with_suffix(".clusters_cache.json")
    if not cache.exists():
        stem = gpkg_path.stem
        candidats = list(Path("uploads").glob(f"**/*{stem}*.clusters_cache.json"))
        cache = candidats[0] if candidats else cache
    if not cache.exists():
        return None
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
    except Exception:
        return None
    feats = (data.get("bassins_geojson") or {}).get("features", [])
    cible = _norm(valeur)
    for f in feats:
        p = f.get("properties", {})
        if p.get("type") != "bassin_urbain":
            continue
        if _norm(p.get("cluster_id")) == cible or _norm(p.get("id_bassin")) == cible:
            return {
                "exutoire_id": p.get("exutoire_id"),
                "nom": p.get("nom"),
                "cluster_id_legacy": p.get("cluster_id"),
                "id_bassin": p.get("id_bassin"),
            }
    return None


def _resoudre_manuel(ref: str) -> Optional[ResolutionBassin]:
    """Bassins manuels M_x : résolution contextuelle, JAMAIS persistée (ID instable)."""
    try:
        from src.infrastructure.persistance_manuelle import charger_bassins_manuels
        manuels = charger_bassins_manuels()
    except Exception:
        return None
    mid = ref[len(PREFIX_MANUEL):].strip()
    for m in manuels:
        if str(m.get("id")) == mid or f"M_{m.get('id')}" == mid:
            return ResolutionBassin(
                entree=ref, statut="RESOLU_MANUEL", source="manuel",
                bassin_ref=ref, moteur_cluster_id=f"M_{m.get('id')}",
                detail=f"Bassin manuel #{m.get('id')}",
            )
    return None


def resoudre_bassin(
    db: Session,
    network_id: Optional[str],
    ref: Any,
    gpkg_path: Optional[Path] = None,
) -> ResolutionBassin:
    """
    Traduit une référence entrante en résolution explicite.
    `network_id` = projects.id (portée d'unicité et de lookup ORM).
    """
    if ref is None or (isinstance(ref, str) and not ref.strip()):
        return ResolutionBassin(entree=str(ref), statut="NON_TROUVE", source="vide",
                                detail="Référence de bassin vide.")

    ref_str = str(ref).strip()

    # ── Règle 1 : préfixe explicite ──────────────────────────────────────
    if ref_str.lower().startswith(PREFIX_EXUTOIRE):
        node_id = ref_str[len(PREFIX_EXUTOIRE):].strip()
        trouves = _cluster_par_bassin_ref(db, network_id, ref_str) or _cluster_par_exutoire(db, network_id, node_id)
        if len(trouves) == 1:
            c = trouves[0]
            return ResolutionBassin(
                entree=ref_str, statut="RESOLU_ORM", source="bassin_ref",
                bassin_ref=c.bassin_ref or ref_str, exutoire_noeud=c.exutoire_noeud or node_id,
                cluster_orm_id=c.id, cluster_nom=c.nom,
            )
        if len(trouves) > 1:
            return ResolutionBassin(entree=ref_str, statut="AMBIGU", source="bassin_ref",
                                    detail=f"{len(trouves)} clusters correspondent à {ref_str}")
        # Aucun cluster ORM : résolution GPKG contextuelle (exutoire_id direct)
        return ResolutionBassin(
            entree=ref_str, statut="RESOLU_GPKG", source="bassin_ref",
            bassin_ref=ref_str, exutoire_noeud=node_id,
            detail="Exutoire référencé sans ligne Cluster ORM (contexte GPKG).",
        )

    if ref_str.lower().startswith(PREFIX_MANUEL):
        res = _resoudre_manuel(ref_str)
        if res:
            return res
        return ResolutionBassin(entree=ref_str, statut="NON_TROUVE", source="manuel",
                                detail="Bassin manuel introuvable dans manual_overrides.json")

    # ── Règle 2 : identifiant ORM Cluster.id (entier) ────────────────────
    try:
        cid = int(ref_str)
    except (TypeError, ValueError):
        cid = None
    if cid is not None:
        trouves = _cluster_par_id(db, network_id, cid)
        if len(trouves) == 1:
            c = trouves[0]
            return ResolutionBassin(
                entree=ref_str, statut="RESOLU_ORM", source="cluster_id",
                bassin_ref=c.bassin_ref, exutoire_noeud=c.exutoire_noeud,
                cluster_orm_id=c.id, cluster_nom=c.nom,
            )
        if len(trouves) > 1:
            return ResolutionBassin(entree=ref_str, statut="AMBIGU", source="cluster_id",
                                    detail="Plusieurs clusters ORM pour cet identifiant")
        # Entrée numérique : tenter aussi la correspondance exutoire_noeud
        # (règle 3) avant de retomber sur l'ordinal legacy (règle 5).
        par_exo = _cluster_par_exutoire(db, network_id, ref_str)
        if len(par_exo) == 1:
            c = par_exo[0]
            return ResolutionBassin(
                entree=ref_str, statut="RESOLU_ORM", source="exutoire_noeud",
                bassin_ref=c.bassin_ref or f"{PREFIX_EXUTOIRE}{ref_str}",
                exutoire_noeud=c.exutoire_noeud or ref_str,
                cluster_orm_id=c.id, cluster_nom=c.nom,
            )
        if len(par_exo) > 1:
            return ResolutionBassin(entree=ref_str, statut="AMBIGU", source="exutoire_noeud",
                                    detail=f"{len(par_exo)} clusters partagent l'exutoire {ref_str}")
        # Pas de cluster ORM : traiter comme identifiant ordinal legacy GPKG
        ctx = _resoudre_depuis_cache_gpkg(gpkg_path, cid)
        if ctx:
            ex_id = ctx.get("exutoire_id")
            # tenter un match ORM par exutoire_noeud pour enrichir
            orm = _cluster_par_exutoire(db, network_id, str(ex_id)) if ex_id else []
            if len(orm) == 1:
                c = orm[0]
                return ResolutionBassin(
                    entree=ref_str, statut="RESOLU_ORM", source="ordinal",
                    bassin_ref=c.bassin_ref, exutoire_noeud=c.exutoire_noeud or ex_id,
                    cluster_orm_id=c.id, cluster_nom=c.nom,
                    detail=f"Ordinal legacy {cid} -> exutoire {ex_id}",
                )
            return ResolutionBassin(
                entree=ref_str, statut="RESOLU_GPKG", source="ordinal",
                exutoire_noeud=str(ex_id) if ex_id else None,
                cluster_nom=ctx.get("nom"),
                detail=f"Ordinal legacy {cid} résolu via cache GPKG (exutoire {ex_id}).",
            )
        return ResolutionBassin(entree=ref_str, statut="NON_TROUVE", source="cluster_id",
                                detail=f"Ni cluster ORM #{cid} ni ordinal GPKG correspondant.")

    # ── Règle 3 : exutoire_noeud brut (id de nœud du graphe) ──────────────
    trouves = _cluster_par_exutoire(db, network_id, ref_str)
    if len(trouves) == 1:
        c = trouves[0]
        return ResolutionBassin(
            entree=ref_str, statut="RESOLU_ORM", source="exutoire_noeud",
            bassin_ref=c.bassin_ref or f"{PREFIX_EXUTOIRE}{ref_str}",
            exutoire_noeud=c.exutoire_noeud or ref_str,
            cluster_orm_id=c.id, cluster_nom=c.nom,
        )
    if len(trouves) > 1:
        return ResolutionBassin(entree=ref_str, statut="AMBIGU", source="exutoire_noeud",
                                detail=f"{len(trouves)} clusters partagent l'exutoire {ref_str}")

    # ── Règle 4 : nom de bassin — UNIQUEMENT si match unique ──────────────
    par_nom = _cluster_par_nom(db, network_id, ref_str)
    if len(par_nom) == 1:
        c = par_nom[0]
        return ResolutionBassin(
            entree=ref_str, statut="RESOLU_ORM", source="nom",
            bassin_ref=c.bassin_ref, exutoire_noeud=c.exutoire_noeud,
            cluster_orm_id=c.id, cluster_nom=c.nom,
            detail="Résolution par nom unique (à préférer bassin_ref).",
        )
    if len(par_nom) > 1:
        return ResolutionBassin(entree=ref_str, statut="AMBIGU", source="nom",
                                detail=f"{len(par_nom)} clusters portent le nom '{ref_str}'")

    # ── Règle 5 : tentative contextuelle GPKG (nom ou exutoire_id) ────────
    ctx = _resoudre_depuis_cache_gpkg(gpkg_path, ref_str)
    if ctx and _norm(ctx.get("nom")) == _norm(ref_str):
        ex_id = ctx.get("exutoire_id")
        return ResolutionBassin(
            entree=ref_str, statut="RESOLU_GPKG", source="nom",
            exutoire_noeud=str(ex_id) if ex_id else None,
            cluster_nom=ctx.get("nom"),
            detail="Nom résolu via cache GPKG (contexte projet courant).",
        )

    return ResolutionBassin(entree=ref_str, statut="NON_TROUVE", source="inconnu",
                            detail="Aucune correspondance pour cette référence de bassin.")
