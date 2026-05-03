"""
Schémas Pydantic pour validation des requêtes et réponses API.
Définit les contrats de données pour tous les endpoints.
"""

from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, List, Any, Dict
from datetime import datetime

# ============================================================
# SCHÉMAS COMMUNS
# ============================================================

class GeoJSONGeometry(BaseModel):
    """Géométrie GeoJSON simplifiée."""
    type: str  # "Point" ou "LineString"
    coordinates: List[Any]


class BaseResponse(BaseModel):
    """Réponse de base avec status."""
    status: str
    message: Optional[str] = None


class ErrorResponse(BaseModel):
    """Réponse d'erreur."""
    error: str
    detail: Optional[str] = None


# ============================================================
# SCHÉMAS REGARDS
# ============================================================

class RegardCreate(BaseModel):
    """Création d'un regard."""
    code: str = Field(..., min_length=1, max_length=50, description="Code unique du regard")
    nom_voie: Optional[str] = Field(None, max_length=200)
    commune: Optional[str] = Field(None, max_length=100)
    profondeur: Optional[float] = Field(None, ge=0)
    diametre: Optional[float] = Field(None, gt=0)
    type_res: Optional[str] = Field(None, max_length=50)
    profrad: Optional[float] = None
    hfermsol: Optional[float] = None
    longitude: float = Field(..., ge=-180, le=180)
    latitude: float = Field(..., ge=-90, le=90)

    @field_validator('longitude', 'latitude')
    @classmethod
    def validate_coordinates(cls, v):
        if v is None:
            raise ValueError("coordonnée obligatoire")
        return v


class RegardUpdate(BaseModel):
    """Mise à jour d'un regard (partiel)."""
    code: Optional[str] = Field(None, min_length=1, max_length=50)
    nom_voie: Optional[str] = Field(None, max_length=200)
    commune: Optional[str] = Field(None, max_length=100)
    profondeur: Optional[float] = Field(None, ge=0)
    diametre: Optional[float] = Field(None, gt=0)
    type_res: Optional[str] = Field(None, max_length=50)
    profrad: Optional[float] = None
    hfermsol: Optional[float] = None
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    latitude: Optional[float] = Field(None, ge=-90, le=90)

    model_config = ConfigDict(extra='ignore')


class RegardResponse(BaseModel):
    """Réponse détaillée d'un regard."""
    id: int
    code: str
    nom_voie: Optional[str] = None
    commune: Optional[str] = None
    profondeur: Optional[float] = None
    diametre: Optional[float] = None
    longitude: float
    latitude: float
    cluster_id: Optional[int] = None
    version: int
    last_modified: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RegardListResponse(BaseModel):
    """Liste de regards (pour GET /regards)."""
    regards: List[RegardResponse]
    total: int
    page: int = 1
    page_size: int = 100


# ============================================================
# SCHÉMAS CANALISATIONS
# ============================================================

class CanalisationCreate(BaseModel):
    """Création d'une canalisation."""
    fid: str = Field(..., min_length=1, max_length=50)
    nom_voie: Optional[str] = Field(None, max_length=200)
    diametre: float = Field(..., gt=0)
    materiau: Optional[str] = Field(None, max_length=50)
    longueur: Optional[float] = Field(None, ge=0)
    prof_fe_am: Optional[float] = None
    prof_fe_av: Optional[float] = None
    fonction_mt: Optional[str] = Field(None, max_length=20)
    id_amont: str = Field(..., description="Code du regard amont")
    id_aval: str = Field(..., description="Code du regard aval")
    forme_sect: Optional[str] = Field(None, max_length=20)
    hauteur: Optional[float] = None
    gdebase: Optional[float] = None
    geometry_wkt: Optional[str] = Field(None, description="Géométrie LineString WKT")


class CanalisationUpdate(BaseModel):
    """Mise à jour d'une canalisation."""
    fid: Optional[str] = Field(None, min_length=1, max_length=50)
    nom_voie: Optional[str] = Field(None, max_length=200)
    diametre: Optional[float] = Field(None, gt=0)
    materiau: Optional[str] = Field(None, max_length=50)
    longueur: Optional[float] = Field(None, ge=0)
    prof_fe_am: Optional[float] = None
    prof_fe_av: Optional[float] = None
    fonction_mt: Optional[str] = Field(None, max_length=20)
    id_amont: Optional[str] = None
    id_aval: Optional[str] = None
    geometry_wkt: Optional[str] = None

    model_config = ConfigDict(extra='ignore')


class CanalisationResponse(BaseModel):
    """Réponse détaillée d'une canalisation."""
    id: int
    fid: str
    nom_voie: Optional[str] = None
    diametre: float
    materiau: Optional[str] = None
    longueur: Optional[float] = None
    id_amont: Optional[str] = None
    id_aval: Optional[str] = None
    cluster_id: Optional[int] = None
    version: int
    last_modified: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RejetCreate(BaseModel):
    """Création d'un rejet (exutoire)."""
    nom: str = Field(..., min_length=1, max_length=100)
    commune: Optional[str] = Field(None, max_length=100)
    nom_voie: Optional[str] = Field(None, max_length=200)
    longitude: float = Field(..., ge=-180, le=180)
    latitude: float = Field(..., ge=-90, le=90)


class RejetUpdate(BaseModel):
    """Mise à jour d'un rejet."""
    nom: Optional[str] = Field(None, min_length=1, max_length=100)
    commune: Optional[str] = Field(None, max_length=100)
    nom_voie: Optional[str] = Field(None, max_length=200)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    latitude: Optional[float] = Field(None, ge=-90, le=90)

    model_config = ConfigDict(extra='ignore')


class RejetResponse(BaseModel):
    """Réponse détaillée d'un rejet."""
    id: int
    nom: str
    commune: Optional[str] = None
    nom_voie: Optional[str] = None
    longitude: float
    latitude: float
    cluster_id: Optional[int] = None
    version: int
    last_modified: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# SCHÉMAS CLUSTERS
# ============================================================

class ClusterResponse(BaseModel):
    """Détail d'un cluster hydraulique."""
    id: int
    nom: str
    exutoire_noeud: Optional[str] = None
    nb_conduites: int
    nb_noeuds: int
    longueur_totale: Optional[float] = None
    diametre_min: Optional[float] = None
    diametre_max: Optional[float] = None
    diametre_moy: Optional[float] = None
    nb_regards: int
    nb_stations: int
    nb_ouvrages: int
    version: int
    last_recalculated: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ClusterListResponse(BaseModel):
    """Liste des clusters."""
    clusters: List[ClusterResponse]
    total: int


# ============================================================
# SCHÉMAS SIMULATIONS
# ============================================================

class SimulationCreate(BaseModel):
    """Lancement d'une simulation SWMM."""
    cluster_id: int = Field(..., gt=0, description="ID du cluster à simuler")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Paramètres SWMM optionnels")
    options: Optional[Dict[str, Any]] = Field(None, description="Options de simulation")


class SimulationResponse(BaseModel):
    """Réponse d'une simulation."""
    id: int
    job_id: str
    cluster_id: int
    status: str
    result_summary: Optional[Dict[str, Any]] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SimulationStatusResponse(BaseModel):
    """Statut d'une simulation (pour polling)."""
    job_id: str
    status: str
    progress: Optional[str] = None
    result_url: Optional[str] = None


# ============================================================
# SCHÉMAS SYNC
# ============================================================

class DeltaChange(BaseModel):
    """Changement dans un delta sync."""
    type: str  # "create", "update", "delete"
    layer: str  # "regards", "conduites", "rejets"
    feature_id: str
    changes: Dict[str, Any]


class DeltaResponse(BaseModel):
    """Réponse delta pour synchronisation."""
    version: int
    timestamp: datetime
    changes: List[DeltaChange]
    deleted_ids: Optional[List[str]] = None


class SyncPush(BaseModel):
    """Push de modifications depuis un client mobile."""
    device_id: str
    changes: List[DeltaChange]


class SyncAck(BaseModel):
    """Accusé de réception sync."""
    accepted: int  # nombre de changements acceptés
    rejected: int  # nombre rejetés
    new_version: int
    conflicts: Optional[List[Dict[str, Any]]] = None


# ============================================================
# SCHÉMAS AUDIT
# ============================================================

class AuditLogResponse(BaseModel):
    """Entrée d'audit."""
    id: int
    table_name: str
    record_id: int
    operation: str
    user_id: Optional[str] = None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)
