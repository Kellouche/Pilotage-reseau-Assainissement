# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : Plateforme de Pilotage du Réseau d'Assainissement
Numéro version : 1.0.0
Date de création : 30-05-2026
Date de modification : 30-05-2026

Objectif du module :
Schémas de validation Pydantic pour les inspections terrain et les incidents géolocalisés.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime

class InspectionCreate(BaseModel):
    """Schéma de création d'une inspection."""
    object_type: str = Field(..., description="Type de l'équipement inspecté (regard, conduite, station, ouvrage)")
    object_id: str = Field(..., description="Identifiant unique ou code de l'équipement")
    etat: Optional[str] = Field(None, description="État de l'équipement (Bon, Moyen, Mauvais)")
    niveau_eau: Optional[str] = Field(None, description="Niveau d'eau (Vide, Normal, Sous charge, Débordement)")
    obstruction: Optional[str] = Field(None, description="Taux d'obstruction (Aucune, Partielle, Totale)")
    odeur: Optional[str] = Field(None, description="Odeur détectée (Aucune, Légère, Forte)")
    debordement: Optional[bool] = Field(False, description="Indique s'il y a débordement")
    commentaires: Optional[str] = Field(None, description="Commentaires libres")
    photos: Optional[List[str]] = Field(None, description="Liste d'URLs ou de chemins de photos")
    statut: Optional[str] = Field("À vérifier", description="Statut de l'inspection")
    inspecteur: Optional[str] = Field(None, description="Nom de l'inspecteur")
    device_id: Optional[str] = Field(None, description="Identifiant de l'appareil mobile")


class InspectionResponse(BaseModel):
    """Schéma de réponse détaillée d'une inspection."""
    id: int
    object_type: str
    object_id: str
    etat: Optional[str] = None
    niveau_eau: Optional[str] = None
    obstruction: Optional[str] = None
    odeur: Optional[str] = None
    debordement: bool
    commentaires: Optional[str] = None
    photos: Optional[List[str]] = None
    statut: str
    date_inspection: datetime
    inspecteur: Optional[str] = None
    device_id: Optional[str] = None
    version: int
    last_modified: datetime

    model_config = ConfigDict(from_attributes=True)


class IncidentCreate(BaseModel):
    """Schéma de création d'un incident géolocalisé."""
    type_incident: str = Field(..., description="Type de l'incident (Débordement, Obstruction, Odeur, etc.)")
    gravite: str = Field(..., description="Niveau de gravité (Faible, Moyenne, Haute, Critique)")
    description: Optional[str] = Field(None, description="Description textuelle")
    longitude: float = Field(..., ge=-180, le=180, description="Coordonnée Longitude")
    latitude: float = Field(..., ge=-90, le=90, description="Coordonnée Latitude")
    statut: Optional[str] = Field("À traiter", description="Statut de l'incident")
    device_id: Optional[str] = Field(None, description="Identifiant de l'appareil mobile")


class IncidentResponse(BaseModel):
    """Schéma de réponse d'un incident géolocalisé."""
    id: int
    type_incident: str
    gravite: str
    description: Optional[str] = None
    longitude: float
    latitude: float
    statut: str
    date_creation: datetime
    device_id: Optional[str] = None
    version: int
    last_modified: datetime

    model_config = ConfigDict(from_attributes=True)
