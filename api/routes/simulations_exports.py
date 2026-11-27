# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Endpoints d'export et de génération de documents : INP, RPT, PDF diagnostic, ordre de mission BMS, réconciliation (extraits de simulations.py).
================================================================================
"""

import json
import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from api.core.security import get_tenant_context, TenantContext
from api.database import get_db
from api.routes.simulations_contexte import (
    _contexte_simulation_autorise,
    _fichier_cache_appartenant,
    _gpkg_demo_autorise,
    _org_id_requete,
    _projet_pour_export_repli,
)
from api.services.simulation_service import (
    est_simulation_valide as _est_simulation_valide,
    iter_fichiers_cache_simulation as _iter_fichiers_cache_simulation,
    resoudre_gpkg_effectif_pour_projet as _resoudre_gpkg_effectif_pour_projet,
)
from src.domain.moteur_swmm import MoteurSWMM

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulations", tags=["Simulations — Exports & documents"])


def _formater_nom_fichier_export(nom_reseau: Optional[str], nom_bassin: Optional[str] = None, ext: str = "inp") -> str:
    """Génère un nom de fichier normalisé et compatible pour EPA SWMM 5.2."""
    if nom_bassin:
        base = str(nom_bassin).strip()
    elif nom_reseau:
        base = re.sub(r'\.(gpkg|inp)$', '', str(nom_reseau).strip(), flags=re.I)
    else:
        base = "modele_swmm"

    sans_accent = unicodedata.normalize('NFKD', base).encode('ASCII', 'ignore').decode('utf-8')
    clean = re.sub(r'[^\w\-_.]+', '_', sans_accent)
    clean = re.sub(r'_+', '_', clean).strip('_')
    if not clean:
        clean = "modele_swmm"
    return f"{clean}.{ext.lstrip('.')}"


@router.get("/download/inp")
def download_latest_inp(
    cluster_id: Optional[str] = None,
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context)
):
    """Télécharge le fichier d'entrée (.inp) généré pour le bassin ou la dernière simulation."""

    _org_id_requete(tenant)
    content = None
    bassin_nom = None
    nom_reseau = None

    # 3D.2 — priorité : INP de la simulation AUTORISÉE du contexte courant
    # (org_id/project_id vérifiés), jamais la globale partagée.
    ctx = _contexte_simulation_autorise(
        db, tenant, cluster_id=cluster_id, project_id=project_id)
    if ctx and ctx.data:
        content = ctx.data.get("inp_content")
        if content:
            meta = ctx.data.get("meta") or {}
            bassin_nom = meta.get("bassin_nom") or meta.get("cluster_nom")
            nom_reseau = (ctx.project.name if ctx.project else None) \
                or ctx.data.get("project_name")

    # 3C.5/R2 — résolution stricte du projet (jamais de .first()).
    proj = _projet_pour_export_repli(db, tenant, project_id=project_id)
    active_gpkg = None
    if proj is not None:
        active_gpkg = _resoudre_gpkg_effectif_pour_projet(db, proj)
        nom_reseau = proj.name
    if active_gpkg is None and proj is None:
        active_gpkg = _gpkg_demo_autorise()
        if active_gpkg is not None:
            nom_reseau = "demo_reseau"

    # 2. Si cluster_id demandé sans simulation autorisée correspondante,
    # chercher dans le cache content-adressé du GPKG effectif du projet —
    # 3C.5/R1 : propriété vérifiée pour chaque fichier avant service.
    if not content and cluster_id and active_gpkg:
        clean_cid = str(cluster_id).strip().lower()
        for cand in _iter_fichiers_cache_simulation(active_gpkg):
            if f"_{clean_cid}_" in cand.name.lower() or f"_cluster_{clean_cid}_" in cand.name.lower():
                try:
                    with open(cand, "r", encoding="utf-8") as cf:
                        cd = json.load(cf)
                    if _est_simulation_valide(cd) and cd.get("inp_content") \
                            and _fichier_cache_appartenant(db, proj, active_gpkg, cd):
                        content = cd["inp_content"]
                        bassin_nom = cd.get("meta", {}).get("bassin_nom") or cd.get("meta", {}).get("cluster_nom") or cluster_id
                        break
                except Exception:
                    continue

    # 3. Si toujours pas de contenu et cluster_id demandé : assembler le modèle INP à la volée !
    if not content and cluster_id and active_gpkg and active_gpkg.exists():
        try:
            from src.domain.moteur_swmm import MoteurSWMM
            moteur = MoteurSWMM()
            content, meta = moteur.assembler_modele_inp(
                gpkg_path=active_gpkg,
                cluster_id=cluster_id,
                pente_moyenne_pct=1.0
            )
            bassin_nom = meta.get("bassin_nom") or meta.get("cluster_nom") or cluster_id
        except Exception as e:
            logger.warning("Échec assemblage INP à la volée pour cluster %s: %s", cluster_id, e)

    if not content:
        raise HTTPException(
            status_code=404,
            detail="Aucun fichier de modèle disponible. Veuillez d'abord exécuter une simulation ou sélectionner un bassin versant."
        )

    filename = _formater_nom_fichier_export(nom_reseau, nom_bassin=bassin_nom, ext="inp")

    return PlainTextResponse(
        content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/download/rpt")
def download_latest_rpt(
    cluster_id: Optional[str] = None,
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context)
):
    """Télécharge le rapport officiel (.rpt) généré par la simulation."""

    _org_id_requete(tenant)
    content = None
    bassin_nom = None
    nom_reseau = None

    # 3D.2 — priorité : RPT de la simulation AUTORISÉE du contexte courant.
    ctx = _contexte_simulation_autorise(
        db, tenant, cluster_id=cluster_id, project_id=project_id)
    if ctx and ctx.data:
        content = ctx.data.get("rpt_content")
        if content:
            meta = ctx.data.get("meta") or {}
            bassin_nom = meta.get("bassin_nom") or meta.get("cluster_nom")
            nom_reseau = (ctx.project.name if ctx.project else None) \
                or ctx.data.get("project_name")

    # 3C.5/R2 — résolution stricte du projet (jamais de .first()).
    proj = _projet_pour_export_repli(db, tenant, project_id=project_id)
    active_gpkg = None
    if proj is not None:
        active_gpkg = _resoudre_gpkg_effectif_pour_projet(db, proj)
        nom_reseau = proj.name
    if active_gpkg is None and proj is None:
        active_gpkg = _gpkg_demo_autorise()
        if active_gpkg is not None:
            nom_reseau = "demo_reseau"

    # 2. Si cluster_id demandé sans simulation autorisée correspondante,
    # chercher dans le cache content-adressé du GPKG effectif du projet —
    # 3C.5/R1 : propriété vérifiée pour chaque fichier avant service.
    if not content and cluster_id and active_gpkg:
        clean_cid = str(cluster_id).strip().lower()
        for cand in _iter_fichiers_cache_simulation(active_gpkg):
            if f"_{clean_cid}_" in cand.name.lower() or f"_cluster_{clean_cid}_" in cand.name.lower():
                try:
                    with open(cand, "r", encoding="utf-8") as cf:
                        cd = json.load(cf)
                    if _est_simulation_valide(cd) and cd.get("rpt_content") \
                            and _fichier_cache_appartenant(db, proj, active_gpkg, cd):
                        content = cd["rpt_content"]
                        bassin_nom = cd.get("meta", {}).get("bassin_nom") or cd.get("meta", {}).get("cluster_nom") or cluster_id
                        break
                except Exception:
                    continue

    if not content:
        raise HTTPException(
            status_code=404,
            detail="Aucun rapport de simulation disponible. Veuillez d'abord exécuter une simulation pour ce bassin."
        )

    filename = _formater_nom_fichier_export(nom_reseau, nom_bassin=bassin_nom, ext="rpt")

    return PlainTextResponse(
        content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/reconciliation")
def get_simulation_reconciliation(
    cluster_id: Optional[str] = None,
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context)
):
    """
    Bilan de réconciliation 1:1 entre le SIG source (GPKG) et le modèle SWMM (.inp).
    Présente l'inventaire avant/après, la ventilation du parc (matériaux, formes, diamètres),
    la matrice d'écarts type des sections SWMM 5.2 et le registre des exclusions auditées.
    """
    _org_id_requete(tenant)
    ctx = _contexte_simulation_autorise(
        db, tenant, cluster_id=cluster_id, project_id=project_id)
    if not ctx or not ctx.data:
        raise HTTPException(
            status_code=404,
            detail="Aucune simulation disponible pour ce contexte."
        )

    meta = ctx.data.get("meta", {})
    reconciliation = meta.get("reconciliation")
    if not reconciliation:
        raise HTTPException(
            status_code=404,
            detail="Bilan de réconciliation non disponible pour cette simulation."
        )

    return {
        "status": "success",
        "simulation_id": ctx.data.get("simulation_id"),
        "cluster_id": cluster_id,
        "reconciliation": reconciliation
    }


# ============================================================
# ORDRE DE MISSION TERRAIN BMS (PDF POUR ÉQUIPES D'ASTREINTE ONA)
# ============================================================

@router.get("/bms/ordre-mission-pdf")
def telecharger_ordre_mission_bms_pdf(
    cluster_id: Optional[str] = None,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Génère et télécharge l'ordre de mission terrain officiel (PDF)
    pour les équipes d'intervention de l'ONA en cas d'alerte météo BMS.
    Identifie la liste prioritaire des regards et collecteurs à curer et sécuriser.
    """
    from src.domain.bms_ordre_mission import generer_pdf_ordre_mission_bms

    _org_id_requete(tenant)

    # 3D.2 — simulation AUTORISÉE du contexte courant, jamais la globale.
    # Contrat historique préservé : PDF générique (données vides) si aucune
    # simulation autorisée — jamais les données d'un autre tenant.
    ctx = _contexte_simulation_autorise(db, tenant)
    sim_data = ctx.data if ctx else {}
    bms_info = sim_data.get("bms_info")

    nom_bassin = (
        sim_data.get("meta", {}).get("bassin_nom")
        or sim_data.get("meta", {}).get("cluster_nom")
        or "Bassin versant urbain"
    )

    pdf_bytes = generer_pdf_ordre_mission_bms(
        simulation_data=sim_data,
        bms_info=bms_info,
        nom_bassin=nom_bassin
    )

    bassin_slug = re.sub(r'[^\w\-]+', '_', nom_bassin)[:30].strip('_') or "reseau"
    filename = f"Ordre_Mission_Terrain_BMS_{bassin_slug}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'}
    )





# ============================================================
# RAPPORT D'EXPERTISE HYDRAULIQUE COMPLET (Phase 6.C)
# ============================================================

@router.get("/rapport-diagnostic-pdf")
def telecharger_rapport_diagnostic_pdf(
    cluster_id: Optional[str] = None,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Génère et télécharge le rapport d'expertise hydraulique complet (PDF)
    conforme aux standards ONA / ANRH pour transmission à la direction technique.
    Contient : cartographie du réseau, liste des contre-pentes, anomalies critiques,
    bilan de continuité massique, volumes inondés, durées de submersion,
    estimation financière des travaux prioritaires.
    """
    from src.domain.rapport_diagnostic import generer_pdf_rapport_diagnostic

    _org_id_requete(tenant)

    # 3D.2 — simulation AUTORISÉE du contexte courant (filtre cluster_id
    # éventuel), jamais la globale partagée ni une restauration non filtrée.
    ctx = _contexte_simulation_autorise(db, tenant, cluster_id=cluster_id)
    sim_data = ctx.data if ctx else None

    if not sim_data or not _est_simulation_valide(sim_data):
        raise HTTPException(
            status_code=404,
            detail="Aucune simulation active disponible pour générer le rapport. Veuillez lancer une simulation SWMM au préalable."
        )

    nom_bassin = (
        sim_data.get("meta", {}).get("bassin_nom")
        or sim_data.get("meta", {}).get("cluster_nom")
        or "Bassin versant urbain"
    )
    project_name = sim_data.get("project_name") or "Réseau Urbain"

    pdf_bytes = generer_pdf_rapport_diagnostic(
        simulation_data=sim_data,
        project_name=project_name
    )

    bassin_slug = re.sub(r'[^\w\-]+', '_', nom_bassin)[:30].strip('_') or "reseau"
    filename = f"Rapport_Expertise_Hydraulique_{bassin_slug}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
