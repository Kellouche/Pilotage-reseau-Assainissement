# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : Plateforme de Pilotage du Réseau d'Assainissement
Numéro version : 1.0.0
Date de création : 30-05-2026
Date de modification : 30-05-2026

Objectif du module :
Modèles SQLAlchemy pour les données collectées sur le terrain : les fiches d'inspection 
des équipements et la signalisation des incidents géolocalisés.
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, JSON
from datetime import datetime
from api.database import Base

class Inspection(Base):
    """
    Modèle représentant une fiche d'inspection terrain pour un équipement du réseau.
    Concerne les regards, conduites, stations et ouvrages.
    """
    __tablename__ = "inspections"

    id = Column(Integer, primary_key=True, index=True)
    object_type = Column(String(50), nullable=False)  # regard, conduite, station, ouvrage
    object_id = Column(String(100), nullable=False, index=True)  # code ou fid
    etat = Column(String(50), nullable=True)  # Bon, Moyen, Mauvais
    niveau_eau = Column(String(50), nullable=True)  # Vide, Normal, Sous charge, Débordement
    obstruction = Column(String(50), nullable=True)  # Aucune, Partielle, Totale
    odeur = Column(String(50), nullable=True)  # Aucune, Légère, Forte
    debordement = Column(Boolean, default=False)
    commentaires = Column(Text, nullable=True)
    photos = Column(JSON, nullable=True)  # Liste d'URLs ou de chemins vers des photos
    statut = Column(String(50), default="À vérifier")  # À vérifier, Corrigé terrain, Validé bureau
    date_inspection = Column(DateTime, default=datetime.utcnow)
    inspecteur = Column(String(100), nullable=True)
    device_id = Column(String(100), nullable=True)
    version = Column(Integer, default=1)
    last_modified = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "etat": self.etat,
            "niveau_eau": self.niveau_eau,
            "obstruction": self.obstruction,
            "odeur": self.odeur,
            "debordement": self.debordement,
            "commentaires": self.commentaires,
            "photos": self.photos,
            "statut": self.statut,
            "date_inspection": self.date_inspection.isoformat() if self.date_inspection else None,
            "inspecteur": self.inspecteur,
            "device_id": self.device_id,
            "version": self.version,
            "last_modified": self.last_modified.isoformat() if self.last_modified else None
        }


class Incident(Base):
    """
    Modèle représentant un incident géolocalisé signalé sur le terrain par un agent.
    """
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    type_incident = Column(String(100), nullable=False)  # Débordement, Obstruction, Odeur, etc.
    gravite = Column(String(50), nullable=False)  # Faible, Moyenne, Haute, Critique
    description = Column(Text, nullable=True)
    longitude = Column(Float, nullable=False)
    latitude = Column(Float, nullable=False)
    statut = Column(String(50), default="À traiter")  # À traiter, En cours, Résolu
    date_creation = Column(DateTime, default=datetime.utcnow)
    device_id = Column(String(100), nullable=True)
    version = Column(Integer, default=1)
    last_modified = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "type_incident": self.type_incident,
            "gravite": self.gravite,
            "description": self.description,
            "longitude": self.longitude,
            "latitude": self.latitude,
            "statut": self.statut,
            "date_creation": self.date_creation.isoformat() if self.date_creation else None,
            "device_id": self.device_id,
            "version": self.version,
            "last_modified": self.last_modified.isoformat() if self.last_modified else None
        }
