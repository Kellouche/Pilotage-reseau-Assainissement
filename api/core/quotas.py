# -*- coding: utf-8 -*-
"""
Module api.core.quotas : Gestion et contrôle des quotas et des fonctionnalités par profil métier pour SWMM Platform SaaS.
Inspiré et calqué sur l'architecture de Pilotage-Réseau-AEP (core.quotas).
Conforme à docs/14_FICHE_PRODUIT_CADRAGE.md et docs/15_PLANS_TARIFAIRES.md.

Profils métier Assainissement :
1. Version Démo (demo / trial / essai) : Évaluation 14 jours, 2 000 regards, calculs SWMM d'initiation.
2. Académique & Recherche (education / academique / recherche) : Gratuit, lois de Manning-Strickler & Saint-Venant, 500 regards, filigrane pédagogique.
3. Bureau d'Études (bet / pro / ingenierie) : 45 000 DZD/mois, schémas directeurs, croisement MNT, 15 000 regards, rapports certifiés sans filigrane.
4. Régies & Exploitants (exploitation / regie / entreprise) : Sur devis/marché public, réseaux illimités, flotte mobile terrain ITV, réconciliation offline.

Auteur : Dr Abdelhakim Kellouche / Antigravity
Date : Octobre 2026
"""

from datetime import datetime, timezone
import logging
from typing import Dict, Any, Optional, Tuple, List
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from api.models import Organization, Network, Job, Membership

logger = logging.getLogger(__name__)

PLAN_PROFILES: Dict[str, Dict[str, Any]] = {
    "demo": {
        "code": "demo",
        "name": "Version Démo (14 jours)",
        "max_nodes": 2000,
        "trial_days": 14,
        "max_concurrent_simulations": 1,
        "max_projects": 3,
        "max_simulations_per_month": 50,
        "max_members": 2,
        # Feature Gating métier Assainissement
        "has_mnt_analysis": True,
        "has_mobile_access": False,
        "has_custom_reports": False,
        "retention_days": 14,
    },
    "education": {
        "code": "education",
        "name": "Académique & Recherche",
        "max_nodes": 500,
        "trial_days": None,
        "max_concurrent_simulations": 1,
        "max_projects": 3,
        "max_simulations_per_month": 50,
        "max_members": 1,  # Compte individuel strict
        # Feature Gating métier Assainissement
        "has_mnt_analysis": False,
        "has_mobile_access": False,
        "has_custom_reports": False,  # Filigrane pédagogique imposé
        "retention_days": 30,
    },
    "bet": {
        "code": "bet",
        "name": "Bureau d'Études (BET)",
        "max_nodes": 15000,
        "trial_days": None,
        "max_concurrent_simulations": 3,
        "max_projects": 25,
        "max_simulations_per_month": 300,
        "max_members": 5,  # Jusqu'à 5 collaborateurs
        # Feature Gating métier Assainissement
        "has_mnt_analysis": True,
        "has_mobile_access": False,
        "has_custom_reports": True,  # Rapports certifiés sans filigrane avec logo BET
        "retention_days": 365,
    },
    "exploitation": {
        "code": "exploitation",
        "name": "Système Modulaire — Régies & Entreprises de Gestion",
        "max_nodes": None,  # Réseau communal complet
        "trial_days": None,
        "max_concurrent_simulations": 10,
        "max_projects": None,  # Patrimoine global multi-secteurs
        "max_simulations_per_month": None,  # Illimité
        "max_members": 15,  # Équipe technique du service assainissement
        # Feature Gating métier Assainissement
        "has_mnt_analysis": True,
        "has_mobile_access": True,  # Application mobile terrain & synchronisation des réclamations/inspections
        "has_custom_reports": True,
        "retention_days": 365,
    },
}

# Table de correspondance des alias
PLAN_ALIASES: Dict[str, str] = {
    "trial": "demo",
    "demo": "demo",
    "essai": "demo",
    "education": "education",
    "academique": "education",
    "recherche": "education",
    "decouverte": "education",
    "bet": "bet",
    "pro": "bet",
    "ingenierie": "bet",
    "exploitation": "exploitation",
    "regie": "exploitation",
    "entreprise": "exploitation",
    "collectivite": "exploitation",
}

FEATURE_LABELS: Dict[str, str] = {
    "has_mnt_analysis": "l'analyse morphologique et l'extraction de bassins versants via MNT / DEM",
    "has_mobile_access": "l'accès à l'application mobile de terrain et la synchronisation des réclamations & inspections",
    "has_custom_reports": "l'export de rapports d'ingénierie certifiés sans filigrane",
}


def normalize_plan_name(raw_name: Optional[str]) -> str:
    """Normalise un code ou alias de plan vers son profil canonique (défaut : demo)."""
    if not raw_name:
        return "demo"
    return PLAN_ALIASES.get(raw_name.strip().lower(), "demo")


def get_plan_limits(plan_name: Optional[str]) -> Dict[str, Any]:
    """Retourne la configuration complète pour un plan donné."""
    canonical = normalize_plan_name(plan_name)
    return PLAN_PROFILES[canonical]


def get_organization_features(org: Optional[Organization]) -> Dict[str, Any]:
    """Retourne l'ensemble des indicateurs de fonctionnalités pour l'organisation."""
    plan_name = getattr(org, "billing_plan", None) if org else "education"
    plan = get_plan_limits(plan_name)
    return {
        "has_mnt_analysis": bool(plan.get("has_mnt_analysis", False)),
        "has_mobile_access": bool(plan.get("has_mobile_access", False)),
        "has_custom_reports": bool(plan.get("has_custom_reports", False)),
        "plan_code": plan.get("code", "demo"),
        "plan_name": plan.get("name", "Version Démo (14 jours)"),
    }


def check_feature_access(org: Optional[Organization], feature_name: str) -> Tuple[bool, Optional[str]]:
    """
    Vérifie si le plan de l'organisation autorise une fonctionnalité métier spécifique.
    Principe d'invisibilité : si non autorisé, renvoie 'Ressource introuvable.' sans divulgation.
    """
    if not org:
        return True, None

    features = get_organization_features(org)
    allowed = bool(features.get(feature_name, False))
    if not allowed:
        return False, "Ressource introuvable."
    return True, None


def get_trial_status(org: Optional[Organization]) -> Dict[str, Any]:
    """
    Retourne le statut d'évaluation ou de licence active pour l'organisation.
    """
    if not org:
        return {"is_trial": False, "days_remaining": 0, "is_expired": False, "total_days": 14}

    now = datetime.now(timezone.utc)
    billing_status = getattr(org, "billing_status", None)
    valid_until = getattr(org, "license_valid_until", None)

    # 1. Licence B2B/B2G active validée par bon de commande
    if billing_status == "active" and valid_until:
        if valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=timezone.utc)
        is_expired = now > valid_until
        delta = valid_until - now
        return {
            "is_trial": False,
            "days_remaining": max(0, delta.days),
            "is_expired": is_expired,
            "total_days": 365,
        }

    # 2. Formule Académique permanente
    canonical_plan = normalize_plan_name(getattr(org, "billing_plan", ""))
    if canonical_plan == "education" and billing_status == "active":
        return {"is_trial": False, "days_remaining": 9999, "is_expired": False, "total_days": 9999}

    # 3. Période d'évaluation (Version Démo 14 jours)
    if canonical_plan == "demo" or billing_status == "trial":
        if valid_until:
            if valid_until.tzinfo is None:
                valid_until = valid_until.replace(tzinfo=timezone.utc)
            delta = valid_until - now
            remaining = max(0, delta.days)
            return {
                "is_trial": True,
                "days_remaining": remaining,
                "is_expired": now > valid_until,
                "total_days": 14,
            }
        created_at = getattr(org, "created_at", None)
        if not created_at:
            return {"is_trial": True, "days_remaining": 14, "is_expired": False, "total_days": 14}
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        elapsed = (now - created_at).days
        remaining = max(0, 14 - elapsed)
        return {
            "is_trial": True,
            "days_remaining": remaining,
            "is_expired": remaining <= 0,
            "total_days": 14,
        }

    return {"is_trial": False, "days_remaining": 0, "is_expired": False, "total_days": 14}


def check_network_size_quota(org: Optional[Organization], node_count: int) -> Tuple[bool, Optional[str]]:
    """
    Vérifie si la taille du réseau (nombre de regards) respecte le quota du plan de l'organisation.
    """
    if not org:
        return True, None

    trial_status = get_trial_status(org)
    if trial_status["is_expired"]:
        return False, "Votre période d'essai de 14 jours est terminée. Veuillez choisir une formule définitive (Bureau d'Études, Régies ou Académique)."

    plan = get_plan_limits(org.billing_plan)
    max_nodes = plan.get("max_nodes")

    if max_nodes is not None and node_count > max_nodes:
        if trial_status["is_trial"]:
            msg = (
                f"Quota dépassé : la Version Démo est plafonnée à {max_nodes} regards (votre réseau en comporte {node_count}). "
                f"Veuillez opter pour la formule Bureau d'Études (15 000 regards) ou Régies (illimité)."
            )
        else:
            msg = (
                f"Quota dépassé pour la formule « {plan['name']} » : ce réseau comporte {node_count} regards, "
                f"alors que votre plan est limité à {max_nodes} regards maximum. "
                f"Veuillez passer à la formule Bureau d'Études (BET) ou Régies."
            )
        return False, msg

    return True, None


def check_projects_count_quota(session: Session, org: Optional[Organization]) -> Tuple[bool, Optional[str]]:
    """
    Vérifie si l'organisation n'a pas atteint le nombre maximum de réseaux/projets autorisés.
    """
    if not org:
        return True, None

    plan = get_plan_limits(org.billing_plan)
    max_projects = plan.get("max_projects")

    if max_projects is not None:
        current_count = session.execute(
            select(func.count(Network.id)).where(Network.org_id == org.id)
        ).scalar() or 0

        if current_count >= max_projects:
            msg = (
                f"Nombre maximal de projets atteint pour la formule « {plan['name']} » ({current_count}/{max_projects}). "
                f"Veuillez archiver ou supprimer un projet existant ou souscrire à une formule supérieure."
            )
            return False, msg

    return True, None


def check_concurrent_simulations_quota(session: Session, org: Optional[Organization]) -> Tuple[bool, Optional[str]]:
    """
    Vérifie si l'organisation n'a pas dépassé son quota de calculs simultanés en cours.
    """
    if not org:
        return True, None

    plan = get_plan_limits(org.billing_plan)
    max_concurrent = plan.get("max_concurrent_simulations", 1)

    active_jobs = session.execute(
        select(func.count(Job.id)).where(
            Job.org_id == org.id,
            Job.status.in_(["queued", "running"]),
        )
    ).scalar() or 0

    if active_jobs >= max_concurrent:
        msg = (
            f"Limite de calculs SWMM simultanés atteinte pour la formule « {plan['name']} » ({active_jobs}/{max_concurrent}). "
            f"Veuillez patienter pendant la finalisation des calculs en cours ou passer à la formule supérieure."
        )
        return False, msg

    return True, None


def check_members_count_quota(session: Session, org: Optional[Organization]) -> Tuple[bool, Optional[str]]:
    """
    Vérifie si l'organisation n'a pas atteint le nombre maximum de collaborateurs autorisés.
    """
    if not org:
        return True, None

    plan = get_plan_limits(org.billing_plan)
    max_members = plan.get("max_members")

    if max_members is not None:
        current_count = session.execute(
            select(func.count(Membership.id)).where(Membership.org_id == org.id)
        ).scalar() or 0

        if current_count >= max_members:
            msg = (
                f"Nombre maximal de collaborateurs atteint pour la formule « {plan['name']} » ({current_count}/{max_members}). "
                f"Veuillez passer à la formule supérieure pour autoriser des collaborateurs supplémentaires."
            )
            return False, msg

    return True, None


def can_access_collaborators(role: str, plan_name: str) -> bool:
    """
    Règle d'invisibilité stricte pour l'espace Collaborateurs :
    - Formule Académique : Jamais (404)
    - Rôles simples (engineer, viewer, field_operator) : Jamais (404)
    - Administrateur délégué (admin) : Uniquement si formule Régies & Exploitation
    - Super Administrateur / Owner : Bureau d'Études et Régies
    """
    canonical_plan = normalize_plan_name(plan_name)
    if canonical_plan == "education":
        return False

    norm_role = (role or "").strip().lower()
    if norm_role in ("super_admin", "owner"):
        return True
    if norm_role == "admin" and canonical_plan == "exploitation":
        return True
    return False


def get_assignable_roles(actor_role: str, plan_name: str) -> List[Tuple[str, str]]:
    """
    Retourne la liste des rôles sélectionnables selon l'acteur et le plan.
    """
    canonical_plan = normalize_plan_name(plan_name)
    norm_role = (actor_role or "").strip().lower()

    if canonical_plan == "exploitation" and norm_role in ("super_admin", "owner"):
        return [
            ("engineer", "Ingénieur Hydraulique"),
            ("viewer", "Observateur / Décideur"),
            ("field_operator", "Opérateur de Terrain (ITV / Curage)"),
            ("admin", "Administrateur Délégué"),
        ]

    if canonical_plan == "exploitation" and norm_role == "admin":
        return [
            ("engineer", "Ingénieur Hydraulique"),
            ("viewer", "Observateur / Décideur"),
            ("field_operator", "Opérateur de Terrain (ITV / Curage)"),
        ]

    if canonical_plan == "bet" and norm_role in ("super_admin", "owner"):
        return [
            ("engineer", "Ingénieur Hydraulique"),
            ("viewer", "Observateur / Décideur"),
        ]

    return []
