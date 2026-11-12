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
from datetime import datetime, timezone
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


class ResultIntegrityError(ResultStoreError):
    """L'artefact est présent mais son empreinte ne correspond pas au référentiel."""


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
    RESULT_ENRICHED = "result_enriched.json"
    MANIFEST = "simulation_manifest.json"
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

    @staticmethod
    def _normaliser_payload(payload: Union[bytes, str, Mapping[str, Any]],
                            kind: ArtifactKind,
                            content_type: Optional[str]
                            ) -> tuple:
        """Normalise un payload en (octets, content_type)."""
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
        return data, content_type

    def _existant_identique(self, key: str, sha: str) -> bool:
        """True si l'objet existant à `key` a le même SHA-256 que `sha`."""
        try:
            existant = self._store.get_bytes(key)
        except StorageNotFoundError:
            # Collision suivie d'une disparition : état instable, on refuse.
            raise ResultStorageError(
                f"Artefact {key} signalé existant puis introuvable (état instable).")
        except StorageError as e:
            raise ResultStorageError(
                f"Vérification de collision impossible ({key}) : {e}") from e
        return hashlib.sha256(existant).hexdigest() == sha

    def save(self, ref: ResultRef, payload: Union[bytes, str, Mapping[str, Any]],
             kind: ArtifactKind = ArtifactKind.RESULT_JSON,
             content_type: Optional[str] = None) -> StoredArtifact:
        """
        Enregistre un artefact de façon CONDITIONNELLE (jamais d'écrasement).

        `payload` : bytes, str (encodé UTF-8) ou Mapping (sérialisé JSON).
        Retourne un StoredArtifact incluant le SHA-256 du contenu déposé.
        Lève ResultAlreadyExists si l'artefact existe déjà.
        """
        data, content_type = self._normaliser_payload(payload, kind, content_type)
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

    def save_idempotent(self, ref: ResultRef,
                        payload: Union[bytes, str, Mapping[str, Any]],
                        kind: ArtifactKind = ArtifactKind.RESULT_JSON,
                        content_type: Optional[str] = None
                        ) -> tuple:
        """
        Écriture conditionnelle idempotente : retourne (StoredArtifact, cree).

        - artefact absent → déposé, cree=True ;
        - artefact présent au contenu IDENTIQUE (SHA-256) → retourne
          l'existant, cree=False (réussite idempotente, pas de collision) ;
        - artefact présent au contenu DIFFÉRENT → ResultAlreadyExists
          (divergence explicite, jamais de succès silencieux).
        """
        data, content_type = self._normaliser_payload(payload, kind, content_type)
        key = self.cle(ref, kind)
        sha = hashlib.sha256(data).hexdigest()
        try:
            cree = self._store.put_bytes_if_absent(key, data, content_type=content_type)
        except StorageError as e:
            raise ResultStorageError(f"Écriture artefact impossible ({key}) : {e}") from e
        if cree:
            logger.info("Artefact résultat enregistré : %s (sha256=%s…)", key, sha[:12])
            return StoredArtifact(ref=ref, kind=kind, key=key,
                                  size=len(data), sha256=sha), True
        if self._existant_identique(key, sha):
            logger.info("Artefact résultat déjà présent et identique : %s", key)
            return StoredArtifact(ref=ref, kind=kind, key=key,
                                  size=len(data), sha256=sha), False
        raise ResultAlreadyExists(
            f"L'artefact {kind.value} existe avec un contenu DIFFÉRENT pour "
            f"cette simulation (clé {key}) : divergence refusée.")

    # -- Intégrité (3C.4) -----------------------------------------------------

    ARTIFACTS_OBLIGATOIRES = frozenset({ArtifactKind.RESULT_JSON})
    # Le manifeste est un artefact d'ÉTAT : il est réécrit à chaque
    # actualisation et n'est jamais listé dans ses propres entrées
    # (pas d'empreinte auto-référencée).

    def verify(self, ref: ResultRef, kind: ArtifactKind,
               sha256_referentiel: Optional[str] = None) -> Dict[str, Any]:
        """
        Vérifie l'intégrité PHYSIQUE d'un artefact : présence, taille et
        SHA-256 du contenu réellement relu. `exists()` n'est jamais utilisé
        comme preuve d'intégrité.

        `sha256_referentiel` : empreinte attendue (manifeste ou appelant).
        Retourne un rapport dict ; `intègre` n'est True que si l'artefact
        est présent ET (aucun référentiel fourni OU empreinte identique).
        """
        if not isinstance(kind, ArtifactKind):
            try:
                kind = ArtifactKind(str(kind))
            except ValueError as e:
                raise ResultStoreError(f"ArtifactKind inconnu : {kind!r}") from e
        key = self.cle(ref, kind)
        rapport = {"ref": {"org_id": ref.org_id, "project_id": ref.project_id,
                           "simulation_id": ref.simulation_id},
                   "kind": kind.value, "key": key,
                   "present": False, "size": None, "sha256": None,
                   "sha256_referentiel": sha256_referentiel,
                   "intègre": False}
        try:
            brut = self._store.get_bytes(key)
        except StorageNotFoundError:
            return rapport
        except StorageError as e:
            raise ResultStorageError(
                f"Vérification impossible ({key}) : {e}") from e
        sha = hashlib.sha256(brut).hexdigest()
        rapport.update(present=True, size=len(brut), sha256=sha,
                       intègre=(sha256_referentiel is None
                                or sha == sha256_referentiel))
        return rapport

    def load_verified(self, ref: ResultRef, kind: ArtifactKind,
                      sha256_referentiel: str) -> bytes:
        """
        Lecture intègre : lève ResultNotFound si absent, ResultIntegrityError
        si l'empreinte diffère du référentiel, ResultStorageError sinon.
        """
        rapport = self.verify(ref, kind, sha256_referentiel)
        if not rapport["present"]:
            raise ResultNotFound(f"Artefact introuvable : {rapport['key']}")
        if not rapport["intègre"]:
            raise ResultIntegrityError(
                f"Empreinte divergente pour {kind.value} "
                f"({rapport['key']}) : attendu {sha256_referentiel[:12]}…, "
                f"relu {rapport['sha256'][:12]}…")
        return self.load(ref, kind)

    # -- Manifeste (3C.4) -----------------------------------------------------

    def generer_manifeste(self, ref: ResultRef,
                          etat_execution: str = "EXECUTED",
                          artefacts_attendus: Optional[List[ArtifactKind]] = None,
                          ) -> Dict[str, Any]:
        """
        Construit le manifeste d'état des artefacts de la simulation.
        Chaque entrée décrit un artefact RÉELLEMENT présent (relecture +
        SHA-256). `artefacts_attendus` = kinds que l'appelant a tenté de
        déposer : un attendu absent rend l'état PARTIAL (même facultatif,
        ex. RPT en échec). À défaut, seuls les obligatoires sont attendus.
        Le manifeste ne contient jamais sa propre empreinte.
        """
        attendus = sorted({k.value for k in
                           (artefacts_attendus or
                            list(self.ARTIFACTS_OBLIGATOIRES))})
        artefacts: Dict[str, Any] = {}
        manquants: List[str] = []
        for kind in ArtifactKind:
            if kind == ArtifactKind.MANIFEST:
                continue
            try:
                v = self.verify(ref, kind)
            except ResultStorageError as e:
                artefacts[kind.value] = {"erreur": str(e)}
                manquants.append(kind.value)
                continue
            if v["present"]:
                artefacts[kind.value] = {
                    "key": v["key"], "size": v["size"], "sha256": v["sha256"]}
            else:
                manquants.append(kind.value)
        attendus_manquants = [k for k in attendus if k not in artefacts]
        obligatoires_manquants = [
            k for k in attendus_manquants
            if k in {kind.value for kind in self.ARTIFACTS_OBLIGATOIRES}]
        return {
            "org_id": ref.org_id,
            "project_id": ref.project_id,
            "simulation_id": ref.simulation_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "execution": etat_execution,
            "etat": "PARTIAL" if attendus_manquants else "PERSISTED",
            "attendus": attendus,
            "attendus_manquants": attendus_manquants,
            "artefacts": artefacts,
            "manquants": manquants,
            "obligatoires_manquants": obligatoires_manquants,
        }

    def ecrire_manifeste(self, ref: ResultRef,
                         etat_execution: str = "EXECUTED",
                         artefacts_attendus: Optional[List[ArtifactKind]] = None
                         ) -> Dict[str, Any]:
        """
        Génère puis dépose `simulation_manifest.json`. Le manifeste est un
        artefact d'ÉTAT réinscriptible (put_bytes) — exception documentée à
        l'immutabilité, qui ne concerne que les artefacts de résultats.
        """
        manifeste = self.generer_manifeste(
            ref, etat_execution=etat_execution,
            artefacts_attendus=artefacts_attendus)
        key = self.cle(ref, ArtifactKind.MANIFEST)
        data = json.dumps(manifeste, ensure_ascii=False).encode("utf-8")
        try:
            self._store.put_bytes(key, data, content_type="application/json")
        except StorageError as e:
            raise ResultStorageError(
                f"Écriture manifeste impossible ({key}) : {e}") from e
        manifeste["key"] = key
        return manifeste

    def verifier_manifeste(self, ref: ResultRef) -> Dict[str, Any]:
        """
        Confronte le manifeste aux artefacts RÉELLEMENT présents :
        présence, taille et SHA-256 relus pour chaque entrée.
        États retournés : ABSENT / DEGRADED / PARTIAL / VERIFIED.
        """
        try:
            manifeste = self.load_json(ref, ArtifactKind.MANIFEST)
        except ResultNotFound:
            return {"etat": "ABSENT", "simulation_id": ref.simulation_id,
                    "details": {}}
        details: Dict[str, Any] = {}
        tous_ok = True
        for nom, entree in (manifeste.get("artefacts") or {}).items():
            try:
                kind = ArtifactKind(nom)
            except ValueError:
                details[nom] = {"intègre": False, "erreur": "kind inconnu"}
                tous_ok = False
                continue
            v = self.verify(ref, kind, entree.get("sha256"))
            details[nom] = {
                "present": v["present"],
                "intègre": v["intègre"],
                "sha256": v["sha256"],
            }
            if not v["present"] or not v["intègre"]:
                tous_ok = False
        attendus = set(manifeste.get("attendus") or
                       [k.value for k in self.ARTIFACTS_OBLIGATOIRES])
        presents = set((manifeste.get("artefacts") or {}).keys())
        attendus_manquants = sorted(attendus - presents)
        if not tous_ok:
            etat = "DEGRADED"
        elif attendus_manquants:
            etat = "PARTIAL"
        else:
            etat = "VERIFIED"
        return {"etat": etat, "simulation_id": ref.simulation_id,
                "execution": manifeste.get("execution"),
                "details": details,
                "attendus_manquants": attendus_manquants,
                "manifeste_etat": manifeste.get("etat")}

    # -- Enrichissements dérivés (3C.4) ---------------------------------------

    def replace_enriched(self, ref: ResultRef,
                         payload: Mapping[str, Any],
                         content_type: Optional[str] = None
                         ) -> StoredArtifact:
        """
        Révision EXPLICITE et STRICTEMENT CANTONNÉE de `result_enriched.json`.

        - Seul ArtifactKind.RESULT_ENRICHED est accepté : aucun autre
          artefact ne peut être révisé par ce canal.
        - Le payload DOIT être un Mapping (données dérivées structurées).
        - Chaque révision conserve la trace des empreintes successives dans
          `_revision_history` (sha256, horodatage, séquence) à l'intérieur
          de l'artefact enrichi.
        - Journalise ancien/nouveau SHA-256 + référence de simulation.
        - Ne touche JAMAIS result.json, model.inp ou report.rpt.
        - Création implicite si l'artefact est absent (premier enrichissement).
        """
        if not isinstance(payload, Mapping):
            raise ResultStoreError(
                "result_enriched.json exige un Mapping de données dérivées.")
        data = dict(payload)
        key = self.cle(ref, ArtifactKind.RESULT_ENRICHED)

        historique: List[Dict[str, Any]] = []
        ancien_sha = None
        try:
            existant = self._store.get_bytes(key)
            ancien_sha = hashlib.sha256(existant).hexdigest()
            try:
                precedent = json.loads(existant.decode("utf-8"))
                if isinstance(precedent, dict):
                    historique = list(precedent.get("_revision_history") or [])
                    # Le contenu métier précédent est remplacé, mais sa
                    # trace d'empreinte est conservée ci-dessous.
            except Exception:
                historique = []
        except StorageNotFoundError:
            pass
        except StorageError as e:
            raise ResultStorageError(
                f"Lecture enrichissement impossible ({key}) : {e}") from e

        nouveau_sha_apercu = hashlib.sha256(
            json.dumps(data, ensure_ascii=False, sort_keys=True)
            .encode("utf-8")).hexdigest()
        historique.append({
            "seq": len(historique) + 1,
            "remplace_sha256": ancien_sha,
            "apercu_sha256": nouveau_sha_apercu,
            "at": datetime.now(timezone.utc).isoformat(),
        })
        data["_revision_history"] = historique

        brut = json.dumps(data, ensure_ascii=False).encode("utf-8")
        sha = hashlib.sha256(brut).hexdigest()
        try:
            self._store.put_bytes(key, brut,
                                  content_type=content_type or "application/json")
        except StorageError as e:
            raise ResultStorageError(
                f"Révision enrichissement impossible ({key}) : {e}") from e
        logger.warning(
            "result_enriched RÉVISÉ : sim=%s ancien=%s nouveau=%s seq=%d",
            ref.simulation_id,
            (ancien_sha or "aucun")[:12], sha[:12], len(historique))
        return StoredArtifact(ref=ref, kind=ArtifactKind.RESULT_ENRICHED,
                              key=key, size=len(brut), sha256=sha)

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
