# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Modele ORM — apports DWF, couches auxiliaires, validations cotes, statuts qualite (extrait de api/models.py)
================================================================================
"""

from datetime import datetime, timezone
import uuid
from typing import List, Optional, Dict, Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.database import Base
from api.models_core import _gen_uuid, _utc_now


class ApportDwf(Base):
    """
    Apport de temps sec (Dry Weather Flow) rattaché à un nœud du réseau.

    Le débit moyen canonique `debit_moyen_m3s` est TOUJOURS stocké en m³/s
    (CMS, cohérent avec FLOW_UNITS du .inp). Deux modes de détermination :
      - "debit" : l'utilisateur saisit directement debit_moyen_m3s ;
      - "eh"    : debit_moyen_m3s est DÉRIVÉ de eh × debit_specifique_l_hab_j
                  et n'est jamais saisi directement (anti-incohérence).
    `profile_key` référence un profil prédéfini de src.domain.apports_dwf
    (grille 168 facteurs compatible SWMM [PATTERNS]).
    """
    __tablename__ = "apports_dwf"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    # LOT A1-DWF — Clé métier unique par projet (format séquentiel AP-YYYY-NNNN)
    code_apport: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    # Identifiant canonique du nœud = _clean_node_id(Code) du GPKG versionné
    # du projet. Pas de FK ORM : la topologie vit dans le GeoPackage.
    node_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    nature: Mapped[str] = mapped_column(String(30), nullable=False)  # domestique, industriel, infiltration, autre
    mode_determination: Mapped[str] = mapped_column(String(10), nullable=False)  # debit, eh
    debit_moyen_m3s: Mapped[float] = mapped_column(Float, nullable=False)
    eh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    debit_specifique_l_hab_j: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    profile_key: Mapped[str] = mapped_column(String(50), default="constant", nullable=False)
    actif: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # LOT P1.4 — estampillage de la version GPKG contre laquelle le nœud a
    # été validé. NULL = apport historique non réconcilié (rejeté à la
    # simulation tant que non ré-estampillé via POST /apports/{id}/revalider).
    # gpkg_version_id reste NULL pour les projets legacy (pas de version
    # artificielle) : seule gpkg_sha256 les identifie.
    gpkg_version_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("gpkg_versions.id", ondelete="SET NULL"),
        nullable=True)
    gpkg_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    observations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)

    organization: Mapped["Organization"] = relationship("Organization")
    project: Mapped["Project"] = relationship("Project", back_populates="apports_dwf")
    gpkg_version: Mapped[Optional["GpkgVersion"]] = relationship("GpkgVersion", foreign_keys=[gpkg_version_id])

    __table_args__ = (
        Index("ix_apports_dwf_org_project", "org_id", "project_id"),
        Index("ix_apports_dwf_project_node", "project_id", "node_id"),
        UniqueConstraint("project_id", "code_apport", name="uq_apports_dwf_project_code"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "project_id": self.project_id,
            "code_apport": self.code_apport,
            "node_id": self.node_id,
            "nature": self.nature,
            "mode_determination": self.mode_determination,
            "debit_moyen_m3s": self.debit_moyen_m3s,
            "debit_moyen_ls": round(self.debit_moyen_m3s * 1000.0, 3) if self.debit_moyen_m3s is not None else None,
            "eh": self.eh,
            "debit_specifique_l_hab_j": self.debit_specifique_l_hab_j,
            "profile_key": self.profile_key,
            "actif": self.actif,
            "gpkg_version_id": self.gpkg_version_id,
            "gpkg_sha256": self.gpkg_sha256,
            "source": self.source,
            "observations": self.observations,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ============================================================
# 4. HISTORIQUE & CONFORMITÉ DES APPORTS DWF — LOT P6.1
# ============================================================

class ApportDwfHistory(Base):
    """
    LOT P6.1 — Historique d'audit et de traçabilité des mutations sur les apports DWF.
    Table immuable (append-only) pour la conformité réglementaire et l'auditabilité.
    Isolation multi-tenant stricte par org_id.
    """
    __tablename__ = "apports_dwf_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    # Protection anti-cascade stricte : un projet ou une organisation avec de l'historique
    # ne peut être supprimé en cascade (intégrité référentielle RESTRICT).
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="RESTRICT"), index=True, nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="RESTRICT"), index=True, nullable=False)
    # L'identifiant de l'apport n'a pas de FK CASCADE afin de préserver l'historique
    # même en cas de suppression de la ligne apports_dwf correspondante.
    apport_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)  # create, update, node_change, reconcile, activate, deactivate, delete, sim_exclusion
    changed_fields: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    previous_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    new_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    changed_by_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False, index=True)

    organization: Mapped["Organization"] = relationship("Organization")
    project: Mapped["Project"] = relationship("Project", back_populates="apports_dwf_history")
    changed_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[changed_by_id])

    __table_args__ = (
        Index("ix_apports_dwf_hist_org_proj", "org_id", "project_id"),
        Index("ix_apports_dwf_hist_apport_created", "apport_id", "created_at"),
        Index("ix_apports_dwf_hist_org_created", "org_id", "created_at"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "project_id": self.project_id,
            "apport_id": self.apport_id,
            "action": self.action,
            "changed_fields": self.changed_fields,
            "previous_state": self.previous_state,
            "new_state": self.new_state,
            "changed_by_id": self.changed_by_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }



# ============================================================
# 5. COUCHES SIG « SATELLITE » — SHP.md (indépendance totale)
# ============================================================

class ProjectAuxLayer(Base):
    """
    Couche SIG satellite rattachée à un projet (SHP.md).

    INDÉPENDANCE TOTALE : jamais fusionnée dans le GPKG projet, jamais
    lue par le pipeline SWMM/.inp, jamais source d'écriture dans les
    tables réseau. Sert à la superposition cartographique et aux outils
    d'aide à la décision (altimétrie, BV officiels, métrologie…).
    Suppression = retrait complet et sans trace (fichiers + ligne).
    """
    __tablename__ = "project_aux_layers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    # Version GPKG du réseau contre laquelle la couche a été importée :
    # un projet = un seul slot « réseau courant », chaque chargement de
    # .gpkg/.inp crée une gpkg_version. Sans cet estampillage, les couches
    # satellites suivaient TOUS les réseaux chargés (project_id identique).
    # NULL = couche importée hors versionnement (projet vierge / legacy).
    gpkg_version_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("gpkg_versions.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(40), nullable=False)  # altimetrie_points, bv_officiel, metrologie, autre…
    nom: Mapped[str] = mapped_column(String(255), nullable=False)
    fichier_source: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)  # clé ArtifactStore du GPKG mono-couche
    crs_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    geom_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    emprise: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)  # bbox EPSG:4326
    nb_features: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attributs: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    colonne_z: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # altimetrie_points : champ d'altitude
    statut: Mapped[str] = mapped_column(String(30), default="ok", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)

    organization: Mapped["Organization"] = relationship("Organization")
    project: Mapped["Project"] = relationship("Project")

    __table_args__ = (
        Index("ix_aux_layers_org_proj", "org_id", "project_id"),
        Index("ix_aux_layers_gpkg_version", "gpkg_version_id"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "gpkg_version_id": self.gpkg_version_id,
            "type": self.type,
            "nom": self.nom,
            "fichier_source": self.fichier_source,
            "crs_source": self.crs_source,
            "geom_type": self.geom_type,
            "emprise": self.emprise,
            "nb_features": self.nb_features,
            "attributs": self.attributs,
            "colonne_z": self.colonne_z,
            "statut": self.statut,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class NodeCoteValidation(Base):
    """
    Registre des validations de cotes nodales suspectes par projet.
    Permet à l'hydraulicien de valider, corriger ou confirmer les cotes et profondeurs suspectes.
    """
    __tablename__ = "node_cote_validations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    node_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    champ: Mapped[str] = mapped_column(String(50), default="profondeur", nullable=False)
    valeur_brute: Mapped[float] = mapped_column(Float, nullable=False)
    valeur_suggeree: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    valeur_validee: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    statut: Mapped[str] = mapped_column(String(30), default="a_valider", nullable=False)  # a_valider, valide, conserve_brut
    motif_suspicion: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    commentaire: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    validated_by_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)

    project: Mapped["Project"] = relationship("Project", back_populates="cotes_validations")
    organization: Mapped["Organization"] = relationship("Organization")

    __table_args__ = (
        Index("ix_node_cote_val_proj_node", "project_id", "node_id"),
        UniqueConstraint("project_id", "node_id", "champ", name="uq_node_cote_val_proj_node_champ"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "node_id": self.node_id,
            "champ": self.champ,
            "valeur_brute": self.valeur_brute,
            "valeur_suggeree": self.valeur_suggeree,
            "valeur_validee": self.valeur_validee,
            "statut": self.statut,
            "motif_suspicion": self.motif_suspicion,
            "commentaire": self.commentaire,
            "validated_at": self.validated_at.isoformat() if self.validated_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class QualiteAnomalieStatut(Base):
    """
    Cycle de vie des anomalies du module Contrôle Qualité (spec V2.1 §5).

    Une ligne par anomalie détectée, identifiée par `cle_anomalie` =
    SHA-1(type_anomalie | objet | gpkg_version_id). Le statut survit aux
    ré-analyses tant que la version du réseau est inchangée ; une nouvelle
    gpkg_version rend les anciennes clés obsolètes (jamais fusionnées).
    """
    __tablename__ = "qualite_anomalie_statuts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    gpkg_version_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    cle_anomalie: Mapped[str] = mapped_column(String(40), nullable=False)
    type_anomalie: Mapped[str] = mapped_column(String(60), nullable=False)
    id_conduite: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    statut: Mapped[str] = mapped_column(String(20), default="a_traiter", nullable=False)  # a_traiter, revu, corrige
    commentaire: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_by_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)

    organization: Mapped["Organization"] = relationship("Organization")
    project: Mapped["Project"] = relationship("Project")

    __table_args__ = (
        UniqueConstraint("project_id", "cle_anomalie", name="uq_qualite_statut_cle"),
        Index("ix_qualite_statuts_proj_type", "project_id", "type_anomalie"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "gpkg_version_id": self.gpkg_version_id,
            "cle_anomalie": self.cle_anomalie,
            "type_anomalie": self.type_anomalie,
            "id_conduite": self.id_conduite,
            "statut": self.statut,
            "commentaire": self.commentaire,
            "updated_by_id": self.updated_by_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
