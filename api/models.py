"""
Modèles SQLAlchemy pour la plateforme.
Représentation ORM des entités métier : regards, canalisations, rejets, clusters, simulations.
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    Text
)
from sqlalchemy.orm import relationship
from datetime import datetime

from api.database import Base

# ============================================================
# MODÈLES DE BASE (sans PostGIS - pour compatibilité)
# ============================================================

class Regard(Base):
    __tablename__ = "regards"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    nom_voie = Column(String(200))
    commune = Column(String(100))
    profondeur = Column(Float)
    diametre = Column(Float)
    type_res = Column(String(50))
    profrad = Column(Float)
    hfermsol = Column(Float)
    longitude = Column(Float)
    latitude = Column(Float)
    cluster_id = Column(Integer, ForeignKey("clusters.id"), nullable=True)
    version = Column(Integer, default=1)
    last_modified = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    modified_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    cluster = relationship("Cluster", back_populates="regards")
    # Pas de relations conduites pour éviter complexité FK sur id_amont/id_aval

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "nom_voie": self.nom_voie,
            "commune": self.commune,
            "profondeur": self.profondeur,
            "diametre": self.diametre,
            "longitude": self.longitude,
            "latitude": self.latitude,
            "cluster_id": self.cluster_id,
            "version": self.version,
            "last_modified": self.last_modified.isoformat() if self.last_modified else None
        }


class Canalisation(Base):
    __tablename__ = "conduites"

    id = Column(Integer, primary_key=True, index=True)
    fid = Column(String(50), unique=True, nullable=False, index=True)
    nom_voie = Column(String(200))
    diametre = Column(Float, nullable=False)
    materiau = Column(String(50))
    longueur = Column(Float)
    prof_fe_am = Column(Float)
    prof_fe_av = Column(Float)
    fonction_mt = Column(String(20))
    id_amont = Column(String(50))
    id_aval = Column(String(50))
    forme_sect = Column(String(20))
    hauteur = Column(Float)
    gdebase = Column(Float)
    geometry_wkt = Column(Text, nullable=True)
    cluster_id = Column(Integer, ForeignKey("clusters.id"), nullable=True)
    version = Column(Integer, default=1)
    last_modified = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    modified_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relation simple vers cluster (pas de relations vers Regard)
    cluster = relationship("Cluster", back_populates="conduites")

    def to_dict(self):
        return {
            "id": self.id,
            "fid": self.fid,
            "nom_voie": self.nom_voie,
            "diametre": self.diametre,
            "materiau": self.materiau,
            "longueur": self.longueur,
            "id_amont": self.id_amont,
            "id_aval": self.id_aval,
            "cluster_id": self.cluster_id,
            "version": self.version,
            "last_modified": self.last_modified.isoformat() if self.last_modified else None
        }


class Rejet(Base):
    __tablename__ = "rejets"

    id = Column(Integer, primary_key=True, index=True)
    nom = Column(String(100), nullable=False)
    commune = Column(String(100))
    nom_voie = Column(String(200))
    # Géométrie
    longitude = Column(Float)
    latitude = Column(Float)
    # Métadonnées
    cluster_id = Column(Integer, ForeignKey("clusters.id"), nullable=True)
    version = Column(Integer, default=1)
    last_modified = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    modified_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    cluster = relationship("Cluster", back_populates="rejets")

    def to_dict(self):
        return {
            "id": self.id,
            "nom": self.nom,
            "commune": self.commune,
            "nom_voie": self.nom_voie,
            "longitude": self.longitude,
            "latitude": self.latitude,
            "cluster_id": self.cluster_id,
            "version": self.version,
            "last_modified": self.last_modified.isoformat() if self.last_modified else None
        }


class Cluster(Base):
    __tablename__ = "clusters"

    id = Column(Integer, primary_key=True, index=True)
    nom = Column(String(100), nullable=False)
    exutoire_noeud = Column(String(100))
    nb_conduites = Column(Integer, default=0)
    nb_noeuds = Column(Integer, default=0)
    longueur_totale = Column(Float, default=0.0)
    diametre_min = Column(Float)
    diametre_max = Column(Float)
    diametre_moy = Column(Float)
    nb_regards = Column(Integer, default=0)
    nb_stations = Column(Integer, default=0)
    nb_ouvrages = Column(Integer, default=0)
    geometry_wkt = Column(Text, nullable=True)
    version = Column(Integer, default=1)
    last_recalculated = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relations simples
    regards = relationship("Regard", back_populates="cluster")
    conduites = relationship("Canalisation", back_populates="cluster")
    rejets = relationship("Rejet", back_populates="cluster")
    simulations = relationship("Simulation", back_populates="cluster")

    def to_dict(self):
        """Convertit en dict sérialisable JSON (sans relations circulaires)."""
        return {
            "id": self.id,
            "nom": self.nom,
            "exutoire_noeud": self.exutoire_noeud,
            "nb_conduites": self.nb_conduites,
            "nb_noeuds": self.nb_noeuds,
            "longueur_totale": self.longueur_totale,
            "diametre_min": self.diametre_min,
            "diametre_max": self.diametre_max,
            "diametre_moy": self.diametre_moy,
            "nb_regards": self.nb_regards,
            "nb_stations": self.nb_stations,
            "nb_ouvrages": self.nb_ouvrages,
            "version": self.version,
            "last_recalculated": self.last_recalculated.isoformat() if self.last_recalculated else None
        }


class Simulation(Base):
    __tablename__ = "simulations"

    id = Column(Integer, primary_key=True, index=True)
    cluster_id = Column(Integer, ForeignKey("clusters.id"), nullable=False)
    job_id = Column(String(64), unique=True, nullable=False, index=True)  # Celery task ID
    status = Column(String(20), default="PENDING")  # PENDING, RUNNING, COMPLETED, FAILED
    parameters = Column(JSON, nullable=True)  # paramètres SWMM
    result_summary = Column(JSON, nullable=True)  # résultats agrégés
    output_file_path = Column(String(500), nullable=True)  # chemin fichier .out
    error_message = Column(Text, nullable=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relations
    cluster = relationship("Cluster", back_populates="simulations")

    def to_dict(self):
        return {
            "id": self.id,
            "job_id": self.job_id,
            "cluster_id": self.cluster_id,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result_summary": self.result_summary
        }


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    table_name = Column(String(50), nullable=False)  # 'regards', 'conduites', etc.
    record_id = Column(Integer, nullable=False)
    operation = Column(String(10), nullable=False)  # INSERT, UPDATE, DELETE
    old_values = Column(JSON, nullable=True)
    new_values = Column(JSON, nullable=True)
    user_id = Column(String(100), nullable=True)
    device_id = Column(String(100), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "table": self.table_name,
            "record_id": self.record_id,
            "operation": self.operation,
            "user_id": self.user_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }
