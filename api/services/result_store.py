# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : ResultStore — couche métier de gestion des résultats de simulation.

Étape 3C.2 — contrat au-dessus d'ArtifactStore (api/core/storage.py) :
aucune logique physique dupliquée, une seule abstraction de stockage.

Responsabilités :
  - identité explicite d'un résultat : ResultRef(org_id, project_id,
    simulation_id) — les trois identifiants sont OBLIGATOIRES à l'écriture ;
  - convention de clés déterministe partitionnée org/projet/simulation ;
  - nomenclature contrôlée des artefacts (ArtifactKind) ;
  - écritures conditionnelles : jamais d'écrasement silencieux ;
  - erreurs explicites : ResultNotFound / ResultAlreadyExists /
    ResultStorageError.

Ce module ne connaît ni FastAPI, ni Celery, ni le modèle ORM : il est
appelable par SimulationService, les workers et les routes.
================================================================================
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Union

from api.core.storage import (
    ArtifactStore,
    StorageError,
    StorageNotFoundError,
    get_storage,
)

logger = logging.getLogger("swmm_platform.services.result_store")


# ---------------------------------------------------------------------------
# Erreurs explicites
# ---------------------------------------------------------------------------

class ResultStoreError(Exception):
    """Erreur de base du ResultStore."""


class ResultNotFound(ResultStoreError):
    """Aucun artefact pour cette référence (ou référence malformée côté store)."""


class ResultAlreadyExists(ResultStoreError):
    """L'artefact existe déjà : écriture conditionnelle refusée (immutabilité)."""


class ResultStorageError(ResultStoreError):
    """Erreur du backend de stockage physique sous-jacent."""


# ---------------------------------------------------------------------------
# Référence d'un résultat et nomenclature des artefacts
# ---------------------------------------------------------------------------

_ID_MAX_LEN = 128
_ID_INTERDITS = ("/", "\\", "..")


def _valider_identifiant(valeur: Any, nom: str) -> str:
    """Valide un identifiant de partition : non vide, sans séparateur ni traversal."""
    if not isinstance(valeur, str) or not valeur.strip():
        raise ResultStoreError(f"{nom} est obligatoire pour une référence de résultat.")
    v = valeur.strip()
    if len(v) > _ID_MAX_LEN:
        raise ResultStoreError(f"{nom} trop long (>{_ID_MAX_LEN} caractères).")
    for motif in _ID_INTERDITS:
        if motif in v:
            raise ResultStoreError(f"{nom} invalide : '{motif}' interdit.")
    if any(c.isspace() for c in v):
        raise ResultStoreError(f"{nom} invalide : espaces interdits.")
    return v


@dataclass(frozen=True)
class ResultRef:
    """
    Identité complète d'un résultat de simulation.
    Les trois identifiants sont obligatoires : aucun résultat ne peut être
    enregistré sous une référence incomplète.
    """
    org_id: str
    project_id: str
    simulation_id: str

    def __post_init__(self):
        object.__setattr__(self, "org_id",
                           _valider_identifiant(self.org_id, "org_id"))
        object.__setattr__(self, "project_id",
                           _valider_identifiant(self.project_id, "project_id"))
        object.__setattr__(self, "simulation_id",
                           _valider_identifiant(self.simulation_id, "simulation_id"))

    @classmethod
    def depuis_simulation(cls, simulation: Any) -> "ResultRef":
        """Construit une référence depuis une ligne ORM Simulation."""
        org_id = getattr(simulation, "org_id", None)
        project_id = getattr(simulation, "project_id", None)
        sim_id = getattr(simulation, "id", None)
        if not org_id or not project_id or not sim_id:
            raise ResultStoreError(
                "La simulation ne porte pas une identité complète "
                "(org_id/project_id/simulation_id) : référence refusée.")
        return cls(org_id=str(org_id), project_id=str(project_id),
                   simulation_id=str(sim_id))


class ArtifactKind(str, Enum):
    """Nomenclature contrôlée des artefacts d'une simulation."""
    RESULT_JSON = "result.json"
    INP = "model.inp"
    RPT = "report.rpt"
    TIMESERIES = "timeseries.json"
    SUMMARY = "summary.json"


@dataclass(frozen=True)
class StoredArtifact:
    """Description d'un artefact déposé — sans exposer le backend physique."""
    ref: ResultRef
    kind: ArtifactKind
    key: str
    size: int
    sha256: str


# ---------------------------------------------------------------------------
# ResultStore
# ---------------------------------------------------------------------------

class ResultStore:
    """
    Couche métier des résultats de simulation au-dessus d'ArtifactStore.

    - Clés : `{org_id}/{project_id}/simulations/{simulation_id}/{kind}`
      via `ArtifactStore.build_key` (partitionnement et anti-traversée
      déjà garantis par le store).
    - `save` utilise `put_bytes_if_absent` : un artefact existant n'est
      JAMAIS écrasé — `ResultAlreadyExists` est levé explicitement.
    - `load` traduit `StorageNotFoundError` → `ResultNotFound` et toute
      autre `StorageError` → `ResultStorageError`.
    - `store` injectable : tests et backends alternatifs sans modification.
    """

    def __init__(self, store: Optional[ArtifactStore] = None):
        self._store = store if store is not None else get_storage()

    @property
    def store(self) -> ArtifactStore:
        return self._store

    # -- Clés ---------------------------------------------------------------

    @staticmethod
    def cle(ref: ResultRef, kind: ArtifactKind = ArtifactKind.RESULT_JSON) -> str:
        """Clé physique déterministe et partitionnée pour cet artefact."""
        if not isinstance(ref, ResultRef):
            raise ResultStoreError("Une ResultRef valide est requise.")
        if not isinstance(kind, ArtifactKind):
            try:
                kind = ArtifactKind(str(kind))
            except ValueError as e:
                raise ResultStoreError(f"ArtifactKind inconnu : {kind!r}") from e
        return ArtifactStore.build_key(
            ref.org_id, ref.project_id,
            f"simulations/{ref.simulation_id}/{kind.value}")

    @staticmethod
    def prefixe(ref: ResultRef) -> str:
        """Préfixe listant tous les artefacts d'une simulation."""
        if not isinstance(ref, ResultRef):
            raise ResultStoreError("Une ResultRef valide est requise.")
        return ArtifactStore.build_key(
            ref.org_id, ref.project_id,
            f"simulations/{ref.simulation_id}")

    # -- Opérations -----------------------------------------------------------

    def exists(self, ref: ResultRef,
               kind: ArtifactKind = ArtifactKind.RESULT_JSON) -> bool:
        """Indique si l'artefact existe dans le store."""
        try:
            return bool(self._store.exists(self.cle(ref, kind)))
        except (ValueError, StorageError) as e:
            raise ResultStorageError(f"Vérification d'existence impossible : {e}") from e

    def save(self, ref: ResultRef, payload: Union[bytes, str, Mapping[str, Any]],
             kind: ArtifactKind = ArtifactKind.RESULT_JSON,
             content_type: Optional[str] = None) -> StoredArtifact:
        """
        Enregistre un artefact de façon CONDITIONNELLE (jamais d'écrasement).

        `payload` : bytes, str (encodé UTF-8) ou Mapping (sérialisé JSON).
        Retourne un StoredArtifact incluant le SHA-256 du contenu déposé.
        Lève ResultAlreadyExists si l'artefact existe déjà.
        """
        if isinstance(payload, Mapping):
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if content_type is None:
                content_type = "application/json"
        elif isinstance(payload, str):
            data = payload.encode("utf-8")
        elif isinstance(payload, (bytes, bytearray)):
            data = bytes(payload)
        else:
            raise ResultStoreError(
                f"Payload non supporté pour {kind} : {type(payload).__name__}")

        if not data:
            raise ResultStoreError("Payload vide refusé pour un artefact de résultat.")

        key = self.cle(ref, kind)
        sha = hashlib.sha256(data).hexdigest()
        try:
            cree = self._store.put_bytes_if_absent(key, data, content_type=content_type)
        except StorageError as e:
            raise ResultStorageError(f"Écriture artefact impossible ({key}) : {e}") from e
        if not cree:
            raise ResultAlreadyExists(
                f"L'artefact {kind.value} existe déjà pour cette simulation "
                f"(clé {key}) : écrasement interdit.")
        logger.info("Artefact résultat enregistré : %s (sha256=%s…)", key, sha[:12])
        return StoredArtifact(ref=ref, kind=kind, key=key,
                              size=len(data), sha256=sha)

    def load(self, ref: ResultRef,
             kind: ArtifactKind = ArtifactKind.RESULT_JSON) -> bytes:
        """
        Charge le contenu binaire d'un artefact.
        Lève ResultNotFound si absent, ResultStorageError sinon.
        """
        key = self.cle(ref, kind)
        try:
            return self._store.get_bytes(key)
        except StorageNotFoundError as e:
            raise ResultNotFound(f"Artefact introuvable : {key}") from e
        except StorageError as e:
            raise ResultStorageError(f"Lecture artefact impossible ({key}) : {e}") from e

    def load_json(self, ref: ResultRef,
                  kind: ArtifactKind = ArtifactKind.RESULT_JSON) -> Dict[str, Any]:
        """Charge un artefact JSON en tant que dictionnaire."""
        brut = self.load(ref, kind)
        try:
            data = json.loads(brut.decode("utf-8"))
        except Exception as e:
            raise ResultStorageError(
                f"Artefact JSON illisible pour {kind.value} : {e}") from e
        if not isinstance(data, dict):
            raise ResultStorageError(
                f"Artefact JSON de type inattendu ({type(data).__name__}) pour {kind.value}.")
        return data

    def list_artifacts(self, ref: ResultRef) -> List[str]:
        """
        Liste les clés des artefacts d'une simulation (tous kinds),
        triées. Retourne une liste vide si aucun artefact.
        """
        prefixe = self.prefixe(ref)
        try:
            cles = self._store.list_keys(prefix=prefixe)
        except StorageError as e:
            raise ResultStorageError(
                f"Listing artefacts impossible ({prefixe}) : {e}") from e
        # Ne conserver que les objets directs du préfixe simulation
        return sorted(k for k in cles if k.startswith(prefixe))

    def exists_any(self, ref: ResultRef) -> bool:
        """True si au moins un artefact existe pour cette simulation."""
        return bool(self.list_artifacts(ref))


# ---------------------------------------------------------------------------
# Fabrique pratique
# ---------------------------------------------------------------------------

def get_result_store(store: Optional[ArtifactStore] = None) -> ResultStore:
    """Retourne un ResultStore sur le backend ArtifactStore configuré."""
    return ResultStore(store=store)
