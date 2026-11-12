"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Schémas Pydantic de validation des requêtes et réponses SWMM
================================================================================
"""

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from typing import Optional, List, Any, Dict, Union
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
    # LOT P1.4 — contrat typé (synchrone ET Celery) : None/True = apports
    # DWF actifs injectés (défaut) ; False = désactivation explicite du
    # scénario, sans suppression des apports configurés.
    dwf_actif: Optional[bool] = Field(
        None, description="False = désactive l'injection des apports DWF pour ce run")


class SimulationResponse(BaseModel):
    """Réponse d'une simulation."""
    # LOT P0.1 — les Simulation.id sont des UUID (str) ; les jobs historiques
    # pouvaient être numériques. Union pour ne pas casser la validation.
    id: Union[int, str]
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


# ============================================================
# SCHÉMAS APPORTS DE TEMPS SEC (DWF) — LOT P1.2
# ============================================================

class ApportDwfCreate(BaseModel):
    """Création d'un apport de temps sec rattaché à un nœud du projet."""
    project_id: Optional[str] = Field(None, description="Projet cible (requis si plusieurs projets actifs)")
    node_id: str = Field(..., min_length=1, max_length=100,
                         description="Identifiant du regard/nœud dans le GPKG du projet")
    nature: str = Field("domestique", description="domestique | industriel | infiltration | autre")
    mode_determination: str = Field("debit", description="debit (m³/s direct) | eh (équivalents-habitants)")
    debit_moyen_m3s: Optional[float] = Field(None, gt=0, le=100.0,
                                              description="Débit moyen en m³/s (mode 'debit' ; dérivé en mode 'eh')")
    eh: Optional[float] = Field(None, gt=0, le=10_000_000,
                                description="Nombre d'équivalents-habitants (mode 'eh')")
    debit_specifique_l_hab_j: Optional[float] = Field(None, gt=0, le=5000,
                                                      description="Débit spécifique L/hab/j (mode 'eh', défaut 200)")
    profile_key: str = Field("constant", description="constant | journalier_type | hebdomadaire")
    actif: bool = True
    source: Optional[str] = Field(None, max_length=255)
    observations: Optional[str] = None

    @field_validator("nature")
    @classmethod
    def _nature_valide(cls, v):
        from src.domain.apports_dwf import NATURES_APPORT
        if v not in NATURES_APPORT:
            raise ValueError(f"nature invalide : {v} (attendu : {', '.join(NATURES_APPORT)})")
        return v

    @field_validator("mode_determination")
    @classmethod
    def _mode_valide(cls, v):
        from src.domain.apports_dwf import MODES_DETERMINATION
        if v not in MODES_DETERMINATION:
            raise ValueError(f"mode_determination invalide : {v}")
        return v

    @field_validator("profile_key")
    @classmethod
    def _profil_valide(cls, v):
        from src.domain.apports_dwf import PROFILS_DWF
        if v not in PROFILS_DWF:
            raise ValueError(f"profile_key inconnu : {v}")
        return v

    @model_validator(mode="after")
    def _coherence_mode(self):
        if self.mode_determination == "debit":
            if self.debit_moyen_m3s is None:
                raise ValueError("debit_moyen_m3s est requis en mode 'debit'.")
        else:  # eh
            if self.eh is None:
                raise ValueError("eh est requis en mode 'eh'.")
        return self


class ApportDwfUpdate(BaseModel):
    """Mise à jour partielle d'un apport (PATCH-like via PUT)."""
    node_id: Optional[str] = Field(None, min_length=1, max_length=100)
    nature: Optional[str] = None
    mode_determination: Optional[str] = None
    debit_moyen_m3s: Optional[float] = Field(None, gt=0, le=100.0)
    eh: Optional[float] = Field(None, gt=0, le=10_000_000)
    debit_specifique_l_hab_j: Optional[float] = Field(None, gt=0, le=5000)
    profile_key: Optional[str] = None
    actif: Optional[bool] = None
    source: Optional[str] = Field(None, max_length=255)
    observations: Optional[str] = None

    model_config = ConfigDict(extra='ignore')

    @field_validator("nature")
    @classmethod
    def _nature_valide(cls, v):
        if v is None:
            return v
        from src.domain.apports_dwf import NATURES_APPORT
        if v not in NATURES_APPORT:
            raise ValueError(f"nature invalide : {v}")
        return v

    @field_validator("mode_determination")
    @classmethod
    def _mode_valide(cls, v):
        if v is None:
            return v
        from src.domain.apports_dwf import MODES_DETERMINATION
        if v not in MODES_DETERMINATION:
            raise ValueError(f"mode_determination invalide : {v}")
        return v

    @field_validator("profile_key")
    @classmethod
    def _profil_valide(cls, v):
        if v is None:
            return v
        from src.domain.apports_dwf import PROFILS_DWF
        if v not in PROFILS_DWF:
            raise ValueError(f"profile_key inconnu : {v}")
        return v


class ApportDwfResponse(BaseModel):
    """Représentation complète d'un apport de temps sec."""
    id: str
    org_id: str
    project_id: str
    node_id: str
    nature: str
    mode_determination: str
    debit_moyen_m3s: float
    debit_moyen_ls: Optional[float] = None
    eh: Optional[float] = None
    debit_specifique_l_hab_j: Optional[float] = None
    profile_key: str
    actif: bool
    gpkg_version_id: Optional[str] = Field(
        None, description="Version GPKG validée (NULL = non réconcilié / legacy)")
    gpkg_sha256: Optional[str] = Field(
        None, description="Empreinte SHA-256 du GPKG validé")
    source: Optional[str] = None
    observations: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProfilDwfInfo(BaseModel):
    """Description publique d'un profil temporel prédéfini."""
    key: str
    nom: str
    description: str
    type_swmm: str
    nb_facteurs: int
    moyenne_facteurs: float
    facteurs_168: List[float]
