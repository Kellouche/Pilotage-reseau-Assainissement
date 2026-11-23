# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : Versionnement immuable des GeoPackage (étape 3B).

Garantit la traçabilité et la reproductibilité des simulations :
- chaque import produit une empreinte SHA-256 du contenu effectivement reçu ;
- chaque version est conservée de manière immuable (clé content-addressed) ;
- le projet pointe explicitement vers sa version courante ;
- chaque simulation conserve la référence exacte de la version utilisée ;
- la simulation s'exécute exclusivement sur le snapshot matérialisé.

Ne modifie aucune logique hydraulique : ce module ne fournit que des fichiers.
================================================================================
"""

import hashlib
import logging
import os
import shutil
import sqlite3
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.core.storage import get_storage, ArtifactStore, StorageError

logger = logging.getLogger("swmm_platform.services.gpkg_versions")

STORAGE_KIND_ARTIFACT = "ARTIFACT_STORE"
STORAGE_KIND_LEGACY = "LEGACY_LOCAL"

# Répertoire de matérialisation locale des versions (atomique, par empreinte)
GPKG_CACHE_DIR = Path(os.environ.get("GPKG_CACHE_DIR", "data/.gpkg_cache"))

# Mots-clés de couches requis — alignés sur src/domain/graphe_reseau._trouver_couche
_MOTS_CLES_REGARDS = ["regard"]
_MOTS_CLES_CANALISATIONS = ["canalisat", "conduit", "pipe", "troncon"]
_EXCLUSIONS_CANALISATIONS = ["désaffect", "desaffect"]
_MOTS_CLES_REJETS = ["rejet", "outfall", "exutoire"]  # optionnel


class GpkgInvalide(Exception):
    """Le fichier GeoPackage a échoué à la validation d'import."""
    def __init__(self, raisons: List[str]):
        self.raisons = raisons
        super().__init__("; ".join(raisons))


class GpkgSimulationError(Exception):
    """
    Étape 3C.0 — erreur métier : la provenance GPKG d'une simulation ne peut
    pas être résolue de façon intègre (version absente, invalide ou
    incohérente avec le projet/tenant). Jamais de substitution silencieuse
    par une autre version.
    """
    pass


# ---------------------------------------------------------------------------
# Empreinte & validation
# ---------------------------------------------------------------------------

def sha256_fichier(path: Path, buffer_size: int = 1024 * 1024) -> str:
    """
    Empreinte SHA-256 streaming d'un fichier (jamais chargé en mémoire).

    LOT P1.4.1 — aucun cache : l'empreinte conditionne des décisions de
    sécurité et de cohérence (estampillage DWF, hash de paramètres,
    propriété des caches, clé du graphe réseau). Un cache clé sur
    (chemin, mtime, taille) pouvait restituer un sha obsolète après un
    remplacement de fichier dans la même seconde à taille identique.
    Le coût du recalcul est négligeable devant une exécution SWMM.
    """
    path = Path(path)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(buffer_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _trouver_couche(noms: List[str], mots_cles: List[str], exclusions: Optional[List[str]] = None) -> Optional[str]:
    exclusions = exclusions or []
    for nom in noms:
        nom_bas = nom.lower()
        if any(e in nom_bas for e in exclusions):
            continue
        if any(m in nom_bas for m in mots_cles):
            return nom
    return None


def _compter_lignes(cursor: sqlite3.Cursor, table: str) -> int:
    try:
        return int(cursor.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    except sqlite3.Error:
        return 0


def valider_gpkg(path: Path) -> Dict[str, Any]:
    """
    Validation complète d'un GeoPackage candidat à une version.
    Lève GpkgInvalide avec la liste des raisons en cas d'échec.
    Retourne les métadonnées d'inventaire (comptages de couches).
    """
    raisons: List[str] = []
    path = Path(path)

    if not path.exists() or not path.is_file():
        raise GpkgInvalide([f"Fichier introuvable : {path}"])

    # 1. En-tête SQLite
    try:
        with open(path, "rb") as f:
            header = f.read(16)
        if header != b"SQLite format 3\x00":
            raise GpkgInvalide(["En-tête invalide : le fichier n'est pas une base SQLite/GPKG."])
    except GpkgInvalide:
        raise
    except OSError as e:
        raise GpkgInvalide([f"Lecture impossible : {e}"])

    # 2. Intégrité SQLite (lecture seule)
    conn = None
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        quick = conn.execute("PRAGMA quick_check").fetchone()
        if not quick or str(quick[0]).lower() != "ok":
            raise GpkgInvalide([f"PRAGMA quick_check défaillant : {quick[0] if quick else 'aucun résultat'}"])

        # 3. Structure GeoPackage
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "gpkg_contents" not in tables:
            raise GpkgInvalide(["Table gpkg_contents absente : ce n'est pas un GeoPackage valide."])

        couches = [
            r[0] for r in conn.execute(
                "SELECT table_name FROM gpkg_contents WHERE data_type='features'")
        ]
        if not couches:
            raise GpkgInvalide(["Aucune couche vectorielle (data_type='features') dans gpkg_contents."])

        # 4. Compatibilité DrainPilot : regards + canalisations obligatoires
        couche_regards = _trouver_couche(couches, _MOTS_CLES_REGARDS)
        couche_cana = _trouver_couche(couches, _MOTS_CLES_CANALISATIONS, _EXCLUSIONS_CANALISATIONS)
        couche_rejets = _trouver_couche(couches, _MOTS_CLES_REJETS)

        if not couche_regards:
            raisons.append("Aucune couche de regards détectée (mot-clé 'regard').")
        if not couche_cana:
            raisons.append("Aucune couche de canalisations détectée.")

        meta: Dict[str, Any] = {
            "couches": couches,
            "couche_regards": couche_regards,
            "couche_canalisations": couche_cana,
            "couche_rejets": couche_rejets,
            "nb_regards": 0,
            "nb_conduites": 0,
        }
        if couche_regards:
            nb = _compter_lignes(conn.cursor(), couche_regards)
            meta["nb_regards"] = nb
            if nb == 0:
                raisons.append(f"La couche '{couche_regards}' ne contient aucune ligne.")
        if couche_cana:
            nb = _compter_lignes(conn.cursor(), couche_cana)
            meta["nb_conduites"] = nb
            if nb == 0:
                raisons.append(f"La couche '{couche_cana}' ne contient aucune ligne.")
        if couche_rejets:
            meta["nb_rejets"] = _compter_lignes(conn.cursor(), couche_rejets)

        if raisons:
            raise GpkgInvalide(raisons)
        return meta
    except GpkgInvalide:
        raise
    except sqlite3.Error as e:
        raise GpkgInvalide([f"Base SQLite illisible : {e}"])
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------------------
# Détection & application du CRS (règle : jamais de mesures sans projection)
# ---------------------------------------------------------------------------

def detecter_crs_gpkg(path: Union[str, Path]) -> Optional[str]:
    """
    Retourne le CRS déclaré par les couches du GeoPackage (ex. "EPSG:32631"),
    ou None si aucune couche ne déclare de système de coordonnées.
    Lecture seule — aucune modification du fichier.
    """
    path = Path(path)
    conn = None
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "gpkg_geometry_columns" not in tables:
            return None
        srs_ids = {r[0] for r in conn.execute(
            "SELECT srs_id FROM gpkg_geometry_columns") if r[0] is not None}
        declares = sorted(s for s in srs_ids if s > 0)
        if not declares:
            return None
        # Résolution EPSG via gpkg_spatial_ref_sys si disponible
        if "gpkg_spatial_ref_sys" in tables:
            for sid in declares:
                row = conn.execute(
                    "SELECT organization_coordsys_id FROM gpkg_spatial_ref_sys "
                    "WHERE srs_id = ? AND organization = 'EPSG'", (sid,)
                ).fetchone()
                if row:
                    return f"EPSG:{row[0]}"
        return f"EPSG:{declares[0]}"
    except sqlite3.Error:
        return None
    finally:
        if conn is not None:
            conn.close()


def appliquer_crs_gpkg(path: Union[str, Path], crs_input: str) -> str:
    """
    Déclare `crs_input` (code EPSG, "EPSG:XXXX", WKT ou PROJ) sur toutes les
    couches du GeoPackage qui n'ont pas de CRS (srs_id <= 0 ou NULL).

    Retourne le code EPSG normalisé (ex. "EPSG:32631").
    Lève ValueError si l'entrée n'est pas résolvable en EPSG.
    """
    from pyproj import CRS
    from pyproj.exceptions import CRSError

    try:
        crs = CRS.from_user_input(crs_input)
    except CRSError as e:
        raise ValueError(
            f"Projection invalide ou non reconnue : {crs_input!r} ({e}). "
            "Fournissez un code EPSG (ex. EPSG:32631)."
        )
    epsg = crs.to_epsg()
    if epsg is None:
        raise ValueError(
            f"Projection non convertible en code EPSG : {crs_input!r}. "
            "Fournissez un code EPSG explicite (ex. EPSG:32631)."
        )

    path = Path(path)
    conn = sqlite3.connect(str(path))
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "gpkg_geometry_columns" not in tables:
            raise ValueError("Fichier sans couches géométriques (gpkg_geometry_columns absent).")
        if "gpkg_spatial_ref_sys" in tables:
            conn.execute(
                "INSERT OR REPLACE INTO gpkg_spatial_ref_sys "
                "(srs_name, srs_id, organization, organization_coordsys_id, "
                " definition, description) VALUES (?, ?, 'EPSG', ?, ?, NULL)",
                (f"EPSG:{epsg}", epsg, epsg, crs.to_wkt()),
            )
        conn.execute(
            "UPDATE gpkg_geometry_columns SET srs_id = ? "
            "WHERE srs_id IS NULL OR srs_id <= 0",
            (epsg,),
        )
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        raise ValueError(f"Impossible d'écrire le CRS dans le GeoPackage : {e}")
    finally:
        conn.close()
    return f"EPSG:{epsg}"


# ---------------------------------------------------------------------------
# Clés de stockage &ArtifactStore
# ---------------------------------------------------------------------------

def cle_version_gpkg(org_id: str, project_id: str, sha256: str) -> str:
    """Clé ArtifactStore content-addressed : org/projet/gis/versions/<sha>/network.gpkg."""
    return ArtifactStore.build_key(org_id, project_id, f"gis/versions/{sha256}/network.gpkg")


def _store() -> ArtifactStore:
    return get_storage()


def _chemin_materialise(sha256: str) -> Path:
    return GPKG_CACHE_DIR / f"{sha256}.gpkg"


def _put_file_si_absent(store: ArtifactStore, key: str, source_path: Path) -> bool:
    """
    Création conditionnelle via l'API dédiée du store. Repli pour les stores
    tiers sans put_file_if_absent : exists()+put (course résiduelle
    documentée — acceptable car la clé est content-addressed).
    """
    put_cond = getattr(store, "put_file_if_absent", None)
    if put_cond is not None:
        return bool(put_cond(key, source_path))
    if store.exists(key):
        return False
    store.put_file(key, source_path)
    return True


def _verifier_objet_store(store: ArtifactStore, key: str, sha_attendu: str) -> None:
    """
    Vérifie que l'objet `key` du store contient EXACTEMENT sha_attendu.
    Un objet existant n'est jamais réécrit : s'il est corrompu, on lève une
    erreur — la réécriture silencieuse est proscrite (integrity > disponibilité).
    """
    fd, tmp_str = tempfile.mkstemp(prefix="gpkg_verify_", suffix=".gpkg")
    os.close(fd)
    tmp = Path(tmp_str)
    try:
        store.get_file(key, tmp)
        sha_reel = sha256_fichier(tmp)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
    if sha_reel != sha_attendu:
        raise StorageError(
            f"Objet store corrompu pour la clé {key} : sha attendu {sha_attendu[:12]}…, "
            f"obtenu {sha_reel[:12]}…. Réécriture interdite (version immuable)."
        )


def _assurer_objet_version(store: ArtifactStore, key: str, source_path: Path, sha: str) -> None:
    """
    Garantit que l'objet content-addressed `key` contient `sha` :
    - absent  → création conditionnelle (put_file_if_absent) ;
    - existant ou course perdue → vérification SHA-256 du contenu stocké.
    Jamais d'écrasement, jamais d'objet accepté sans preuve de contenu.
    """
    if not store.exists(key):
        if _put_file_si_absent(store, key, source_path):
            return
    _verifier_objet_store(store, key, sha)


# ---------------------------------------------------------------------------
# Enregistrement d'une version (import)
# ---------------------------------------------------------------------------

def _version_existe(db: Session, project_id: str, sha256: str):
    from api.models import GpkgVersion
    return db.execute(
        select(GpkgVersion).where(
            GpkgVersion.project_id == project_id,
            GpkgVersion.sha256 == sha256,
        )
    ).scalars().first()


def _creer_version_row(db: Session, **kwargs):
    from api.models import GpkgVersion
    v = GpkgVersion(**kwargs)
    db.add(v)
    return v


def _stocker_version(db: Session, org_id: str, project_id: str, sha256: str,
                     source_path: Path, meta: Dict[str, Any],
                     filename_original: Optional[str],
                     created_by_id: Optional[str]) -> "Any":
    """
    Stocke le fichier validé sous la clé content-addressed et crée la ligne
    gpkg_versions + met à jour le pointeur projet, le tout de façon atomique.
    Retourne l'objet GpkgVersion.
    """
    from api.models import GpkgVersion, Project

    store = _store()
    key = cle_version_gpkg(org_id, project_id, sha256)

    # Jamais d'écrasement : la clé est déterminée par le contenu. Un objet
    # existant est vérifié par empreinte (taille + SHA-256), jamais réécrit.
    taille = Path(source_path).stat().st_size
    _assurer_objet_version(store, key, Path(source_path), sha256)
    logger.info("[gpkg_version] Objet version garanti : %s (%d octets)", key, taille)

    # Transaction : ligne version + pointeur projet ensemble.
    # Dédup multi-processus : INSERT protégé par UNIQUE(project_id, sha256) ;
    # en cas de course, on récupère la ligne gagnante via savepoint.
    try:
        with db.begin_nested():
            version = _creer_version_row(
                db,
                org_id=org_id,
                project_id=project_id,
                sha256=sha256,
                size_bytes=taille,
                storage_kind=STORAGE_KIND_ARTIFACT,
                storage_ref=key,
                filename_original=filename_original,
                nb_regards=meta.get("nb_regards"),
                nb_conduites=meta.get("nb_conduites"),
                created_by_id=created_by_id,
            )
            db.flush()
    except IntegrityError:
        # Course concurrente : une autre transaction a inséré la même version
        version = _version_existe(db, project_id, sha256)
        if version is None:
            raise
        logger.info("[gpkg_version] Version existante réutilisée (course dédup) : %s", version.id)

    # Pointeur courant du projet — atomique, dernier commit gagne
    projet = db.get(Project, project_id)
    if projet is not None:
        projet.gpkg_version_id = version.id
    db.flush()
    return version


def enregistrer_version_gpkg(
    db: Session,
    project: Any,
    source_path: Union[str, Path],
    filename_original: Optional[str] = None,
    created_by_id: Optional[str] = None,
    valider: bool = True,
) -> Any:
    """
    Enregistre `source_path` comme version immuable pour `project`.

    - valide le GPKG (quick_check, couches requises) si `valider` ;
    - calcule SHA-256 + taille sur le fichier fourni (pour la migration :
      passer le fichier temporaire validé, jamais la source mutable) ;
    - déduplique sur (project_id, sha256) — aucune réécriture si identique ;
    - stocke sous clé content-addressed (jamais d'écrasement) ;
    - met à jour project.gpkg_version_id.

    Lève GpkgInvalide si le fichier est invalide. Ne commit PAS : l'appelant
    contrôle la transaction (permet l'atomicité avec d'autres écritures).
    """
    from api.models import GpkgVersion  # noqa: F401  (référence pour typage)

    source = Path(source_path)
    if valider:
        meta = valider_gpkg(source)
    else:
        meta = {}

    sha = sha256_fichier(source)
    taille = source.stat().st_size

    existante = _version_existe(db, project.id, sha)
    if existante is not None:
        # Objet référencé mais peut-être absent du store → restauration
        # conditionnelle si possible, vérification si existant.
        if existante.storage_kind == STORAGE_KIND_ARTIFACT:
            _assurer_objet_version(_store(), existante.storage_ref, source, sha)
        projet = db.get(type(project), project.id)
        if projet is not None:
            projet.gpkg_version_id = existante.id
        db.flush()
        # Inventaire de validation exposé à l'appelant (attribut transitoire)
        existante._inventaire_meta = meta
        return existante

    version = _stocker_version(
        db, project.org_id, project.id, sha, source, meta,
        filename_original or source.name, created_by_id,
    )
    version._inventaire_meta = meta
    return version


# ---------------------------------------------------------------------------
# Matérialisation atomique & résolution pour la simulation
# ---------------------------------------------------------------------------

def _copier_atomique(source_path: Path, destination: Path) -> Path:
    """
    Copie `source_path` vers `destination` de façon atomique :
    fichier temporaire dans le même dossier → os.replace() (atomique sur
    le même volume). Le résultat n'est visible qu'une fois complet.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp",
                                   dir=str(destination.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        shutil.copyfile(source_path, tmp_path)
        os.replace(tmp_path, destination)  # atomique
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise
    return destination


def materialiser_version(version: Any) -> Path:
    """
    Retourne le chemin local du GPKG correspondant à `version`, en garantissant
    que son contenu correspond exactement à version.sha256.

    - ARTIFACT_STORE : get_file vers fichier temporaire → vérif SHA-256 →
      renommage atomique dans data/.gpkg_cache/<sha256>.gpkg ;
    - LEGACY_LOCAL  : lecture du chemin enregistré → mêmes garanties ;
    - cache existant : revérifié par empreinte (un cache altéré est réécrit).

    Lève StorageError/FileNotFoundError/ValueError si la version est
    indisponible ou corrompue — jamais de contenu non vérifié au moteur.
    """
    sha = version.sha256
    cible = _chemin_materialise(sha)

    # Cache déjà matérialisé : revérifier l'empreinte (protection altération)
    if cible.exists():
        if sha256_fichier(cible) == sha:
            return cible
        logger.warning("[gpkg_version] Cache altéré détecté, régénération : %s", cible)

    store = _store()
    if version.storage_kind == STORAGE_KIND_ARTIFACT:
        if not store.exists(version.storage_ref):
            raise StorageError(f"Objet GPKG introuvable pour la version {version.id} : {version.storage_ref}")
        tmp_dir = Path(tempfile.mkdtemp(prefix="gpkg_mat_"))
        try:
            brut = store.get_bytes(version.storage_ref)
            tmp_src = tmp_dir / "source.gpkg"
            tmp_src.write_bytes(brut)
            _materialiser_depuis_source(tmp_src, sha, cible)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    elif version.storage_kind == STORAGE_KIND_LEGACY:
        src = Path(version.storage_ref.replace("local:", "", 1))
        if not src.exists():
            raise FileNotFoundError(f"GPKG legacy introuvable : {src}")
        _materialiser_depuis_source(src, sha, cible)
    else:
        raise StorageError(f"storage_kind inconnu : {version.storage_kind}")

    return cible


def _materialiser_depuis_source(src: Path, sha_attendu: str, cible: Path) -> None:
    """Copie atomique + vérification SHA-256 obligatoire avant usage moteur."""
    sha_reel = sha256_fichier(src)
    if sha_reel != sha_attendu:
        raise ValueError(
            f"Empreinte GPKG incohérente : attendu {sha_attendu[:12]}…, obtenu {sha_reel[:12]}…"
        )
    _copier_atomique(src, cible)


def version_disponible(version: Any) -> Tuple[bool, str]:
    """Vérifie la disponibilité effective d'une version (statut UNAVAILABLE dérivé)."""
    try:
        if version.storage_kind == STORAGE_KIND_ARTIFACT:
            return (_store().exists(version.storage_ref), "")
        if version.storage_kind == STORAGE_KIND_LEGACY:
            src = Path(version.storage_ref.replace("local:", "", 1))
            return (src.exists(), "" if src.exists() else "fichier local absent")
        return (False, f"storage_kind inconnu : {version.storage_kind}")
    except Exception as e:
        return (False, str(e))


def _valider_version_pour_contexte(version: Any, project: Any) -> None:
    """Garde tenant/projet : la version DOIT appartenir au projet courant."""
    if project is not None and (
        version.project_id != project.id or version.org_id != project.org_id
    ):
        raise GpkgSimulationError(
            "Version GPKG de la simulation incohérente avec le projet/tenant courant."
        )


def _materialiser_version_versionnee(db: Session, project: Any, version: Any) -> Path:
    _valider_version_pour_contexte(version, project)
    ok, raison = version_disponible(version)
    if not ok:
        raise GpkgSimulationError(f"Version GPKG de la simulation indisponible : {raison}")
    try:
        return materialiser_version(version)
    except Exception as e:
        raise GpkgSimulationError(f"Matérialisation GPKG de la simulation impossible : {e}")


def resoudre_gpkg_pour_simulation(
    db: Session,
    project: Any,
    data_simulation: Optional[Dict[str, Any]],
) -> Tuple[Optional[Path], Dict[str, Any]]:
    """
    Étape 3C.0 — résout le GPKG EXACT ayant produit `data_simulation`
    (dict résultat JSON persisté — la globale `_DERNIERE_SIMULATION` a été
    supprimée en 3D.5).

    Ordre strict :
      1. `provenance.gpkg_version_id` → GpkgVersion validé dans le contexte
         projet/tenant → matérialisation atomique du snapshot ; si la ligne
         version a disparu, repli sur l'empreinte SHA-256 (jamais sur la
         version courante) ;
      2. `provenance.gpkg_sha256` → version (project_id, sha256) du projet,
         sinon `source_gpkg` si son empreinte réelle correspond ;
      3. `source_gpkg` si le fichier existe (provenance absente = legacy) ;
      4. rien de résoluble → (None, meta) : l'appelant applique le fallback
         legacy (GPKG courant du projet).

    Une provenance EXPLICITE mais irrésoluble (version absente ET empreinte
    invérifiable, incohérence tenant) lève GpkgSimulationError —
    jamais de substitution silencieuse par la version courante.
    """
    if not isinstance(data_simulation, dict):
        return None, {}

    prov = data_simulation.get("provenance") or {}
    version_id = prov.get("gpkg_version_id")
    sha_attendu = prov.get("gpkg_sha256")
    source_gpkg = data_simulation.get("source_gpkg")

    # 1. Version explicite
    version_id_perdu = False
    if version_id:
        from api.models import GpkgVersion
        version = db.get(GpkgVersion, version_id)
        if version is not None:
            chemin = _materialiser_version_versionnee(db, project, version)
            return chemin, {
                "version_id": version.id,
                "sha256": version.sha256,
                "storage_kind": version.storage_kind,
                "resolution": "gpkg_version_id",
                "materialized_path": str(chemin),
            }
        # Ligne GpkgVersion absente (ex. base réinitialisée alors que le
        # JSON persisté survit) : on ne substitue PAS la version courante,
        # on tente la vérification par empreinte SHA-256 ci-dessous.
        version_id_perdu = True

    # 2. Empreinte explicite sans version_id
    if sha_attendu:
        version = None
        if project is not None:
            version = _version_existe(db, project.id, sha_attendu)
        if version is not None:
            chemin = _materialiser_version_versionnee(db, project, version)
            return chemin, {
                "version_id": version.id,
                "sha256": version.sha256,
                "storage_kind": version.storage_kind,
                "resolution": "gpkg_sha256",
                "materialized_path": str(chemin),
            }
        # Pas de version enregistrée : le source_gpkg peut encore être le
        # bon contenu SI son empreinte réelle correspond à la provenance.
        if source_gpkg and Path(source_gpkg).exists():
            if sha256_fichier(Path(source_gpkg)) == sha_attendu:
                return Path(source_gpkg), {
                    "version_id": None,
                    "sha256": sha_attendu,
                    "storage_kind": "SOURCE_GPKG_VERIFIE",
                    "resolution": "source_gpkg_sha256",
                    "materialized_path": str(Path(source_gpkg).resolve()),
                }
        raise GpkgSimulationError(
            "Empreinte GPKG de la simulation sans version correspondante "
            "et source_gpkg absent ou divergent — substitution interdite."
        )

    # 3. Aucune provenance exploitable : legacy — source_gpkg si présent.
    #    Une provenance EXPLICITE irrésoluble (version_id perdu sans empreinte
    #    vérifiable) reste une erreur métier : pas de repli silencieux.
    if version_id_perdu:
        raise GpkgSimulationError(
            f"Version GPKG {version_id} de la simulation introuvable en base "
            "et empreinte SHA-256 absente ou invérifiable — substitution interdite."
        )
    if source_gpkg and Path(source_gpkg).exists():
        return Path(source_gpkg), {
            "version_id": None,
            "sha256": None,
            "storage_kind": "LEGACY_SIMULATION",
            "resolution": "source_gpkg_legacy",
            "materialized_path": str(Path(source_gpkg).resolve()),
        }

    # 4. Rien d'exploitable → fallback legacy à la charge de l'appelant
    return None, {}


def exutoire_present_dans_gpkg(gpkg_path: Path, exutoire_noeud: Optional[str]) -> Optional[bool]:
    """
    Vérification best-effort de cohérence : l'exutoire résolu (3A) figure-t-il
    comme identifiant de nœud dans le GPKG exact utilisé par la simulation ?
    Retourne True/False, ou None si indéterminable (jamais bloquant).
    """
    if not exutoire_noeud or not gpkg_path or not Path(gpkg_path).exists():
        return None
    cible = str(exutoire_noeud).strip()
    conn = None
    try:
        conn = sqlite3.connect(f"file:{Path(gpkg_path).as_posix()}?mode=ro", uri=True)
        tables = [r[0] for r in conn.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type='features'")]
        for table in tables:
            nom_bas = table.lower()
            if not any(m in nom_bas for m in _MOTS_CLES_REGARDS + _MOTS_CLES_REJETS):
                continue
            cols = [c[1] for c in conn.execute(f'PRAGMA table_info("{table}")')]
            # Colonnes candidates porteuses d'identifiants de nœuds
            candidates = [c for c in cols if c.lower() in (
                "id", "code", "nom", "origdonne", "noeud", "cle", "identifiant", "numero")]
            # Tolérance numérique : les codes GPKG sont souvent stockés en REAL
            # (ex. Code=3479.0) alors que la référence métier est '3479'.
            try:
                cible_num = float(cible)
                numeric = True
            except (TypeError, ValueError):
                numeric = False
            for col in candidates:
                clauses = ['CAST("{col}" AS TEXT) = ?'.format(col=col)]
                params_list = [[cible]]
                if numeric:
                    clauses.append('CAST("{col}" AS REAL) = ?'.format(col=col))
                    params_list.append([cible_num])
                for clause, params in zip(clauses, params_list):
                    try:
                        row = conn.execute(
                            f'SELECT 1 FROM "{table}" WHERE {clause} LIMIT 1',
                            params,
                        ).fetchone()
                        if row:
                            return True
                    except sqlite3.Error:
                        continue
        return False
    except Exception:
        return None
    finally:
        if conn is not None:
            conn.close()


def resoudre_version_pour_simulation(
    db: Session,
    project: Any,
) -> Tuple[Optional[Path], Dict[str, Any]]:
    """
    Résout LE GPKG à utiliser pour une simulation du projet, en une seule capture :

    - version courante présente → matérialisation atomique du snapshot →
      meta {version_id, sha256, storage_kind, materialized_path} ;
    - pas de version (projet legacy) → source_gpkg_key si existant →
      sha256 calculé à la volée (empreinte honnête, version_id=None) ;
    - rien de disponible → (None, meta avec erreur).

    Le moteur reçoit exclusivement le chemin retourné — jamais source_gpkg_key
    directement lorsqu'une version existe.
    """
    version_id = getattr(project, "gpkg_version_id", None)

    if version_id:
        from api.models import GpkgVersion
        version = db.get(GpkgVersion, version_id)
        if version is None:
            return None, {"erreur": f"Version GPKG {version_id} introuvable en base"}
        # Cohérence tenant : la version DOIT appartenir au projet
        if version.project_id != project.id or version.org_id != project.org_id:
            return None, {"erreur": "Version GPKG incohérente avec le projet (tenant)"}
        ok, raison = version_disponible(version)
        if not ok:
            return None, {
                "erreur": f"Version GPKG indisponible (UNAVAILABLE) : {raison}",
                "version_id": version.id,
                "sha256": version.sha256,
                "storage_kind": version.storage_kind,
            }
        try:
            chemin = materialiser_version(version)
        except Exception as e:
            return None, {
                "erreur": f"Matérialisation GPKG impossible : {e}",
                "version_id": version.id,
                "sha256": version.sha256,
            }
        return chemin, {
            "version_id": version.id,
            "sha256": version.sha256,
            "storage_kind": version.storage_kind,
            "materialized_path": str(chemin),
        }

    # Chemin legacy : source_gpkg_key (compatibilité transition)
    legacy_key = getattr(project, "source_gpkg_key", None)
    if legacy_key:
        p = Path(legacy_key)
        if p.exists():
            return p, {
                "version_id": None,
                "sha256": sha256_fichier(p),
                "storage_kind": "LEGACY",
                "materialized_path": str(p.resolve()),
            }
    return None, {"erreur": "Aucun GeoPackage disponible pour ce projet"}


def resoudre_snapshot_pour_lecture(
    db: Session,
    project: Any,
    snapshot: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Résout le snapshot GPKG à utiliser pour une LECTURE cartographique.

    `snapshot` accepte indifféremment :
      - un gpkg_version_id (UUID) ;
      - un sha256 complet ou préfixe (>= 8 caractères, hexadécimal) ;
      - None / chaîne vide → version COURANTE du projet (comportement
        historique de tous les endpoints de lecture).

    Retourne un contexte normalisé :
      {
        "path": Path,                # fichier matérialisé (cache sha256)
        "version_id": str|None,
        "sha256": str|None,
        "est_version_courante": bool,
        "libelle": str,              # « réseau du … » / nom de fichier
        "nb_regards": int|None,
        "nb_conduites": int|None,
        "storage_kind": str,
      }

    Règles strictes (jamais de substitution silencieuse) :
      - snapshot explicite introuvable / hors projet / indisponible
        → GpkgSimulationError (l'appelant traduit en 404/409) ;
      - la version DOIT appartenir à (project.id, project.org_id) ;
      - le sha retourné est TOUJOURS celui de la version résolue —
        c'est la clé de comparaison INV-2 côté client.
    """
    from api.models import GpkgVersion

    vid_courant = getattr(project, "gpkg_version_id", None)
    org_id = getattr(project, "org_id", None)

    # --- Snapshot explicite -------------------------------------------------
    if snapshot and str(snapshot).strip():
        ident = str(snapshot).strip()
        version = None

        # 1) Identifiant version (UUID) — vérifié prioritaire si format UUID
        if len(ident) >= 32 and "-" in ident:
            version = db.query(GpkgVersion).filter(
                GpkgVersion.id == ident,
                GpkgVersion.project_id == project.id,
                GpkgVersion.org_id == org_id,
            ).first()
            if version is None:
                raise GpkgSimulationError(
                    f"Version GPKG {ident[:12]}… introuvable pour ce projet.")
        else:
            # 2) Empreinte SHA-256 (complète ou préfixe raisonnable)
            empreinte = ident.lower()
            if len(empreinte) < 8:
                raise GpkgSimulationError(
                    "Identifiant de snapshot trop court (sha256 >= 8 caractères).")
            candidats = db.query(GpkgVersion).filter(
                GpkgVersion.project_id == project.id,
                GpkgVersion.org_id == org_id,
                GpkgVersion.sha256.like(f"{empreinte}%"),
            ).limit(2).all()
            if not candidats:
                raise GpkgSimulationError(
                    f"Aucun snapshot GPKG ne correspond à « {ident[:16]}… » "
                    "pour ce projet.")
            if len(candidats) > 1:
                raise GpkgSimulationError(
                    "Empreinte de snapshot ambiguë — préciser davantage.")
            version = candidats[0]

        ok, raison = version_disponible(version)
        if not ok:
            raise GpkgSimulationError(
                f"Snapshot GPKG indisponible : {raison}")
        try:
            chemin = materialiser_version(version)
        except Exception as e:
            raise GpkgSimulationError(
                f"Matérialisation du snapshot impossible : {e}")

        return {
            "path": chemin,
            "version_id": version.id,
            "sha256": version.sha256,
            "est_version_courante": (version.id == vid_courant),
            "libelle": _libelle_version(version),
            "nb_regards": version.nb_regards,
            "nb_conduites": version.nb_conduites,
            "storage_kind": version.storage_kind,
        }

    # --- Version courante (défaut = comportement existant) -------------------
    chemin, meta = resoudre_version_pour_simulation(db, project)
    if chemin is None:
        raise GpkgSimulationError(
            meta.get("erreur") or "Aucun GeoPackage disponible pour ce projet.")
    # meta peut être legacy (sha256 calculé à la volée, version_id=None)
    sha = meta.get("sha256")
    version_id = meta.get("version_id")
    nb_regards = nb_conduites = None
    libelle = "réseau actuel"
    if version_id:
        version = db.get(GpkgVersion, version_id)
        if version is not None:
            nb_regards, nb_conduites = version.nb_regards, version.nb_conduites
            libelle = _libelle_version(version)
    elif sha:
        libelle = f"réseau ({sha[:12]}…)"
    return {
        "path": chemin,
        "version_id": version_id,
        "sha256": sha,
        "est_version_courante": True,
        "libelle": libelle,
        "nb_regards": nb_regards,
        "nb_conduites": nb_conduites,
        "storage_kind": meta.get("storage_kind"),
    }


def _libelle_version(version: Any) -> str:
    """Libellé humain d'un snapshot : nom de fichier + date + volumes."""
    parts = []
    nom = getattr(version, "filename_original", None)
    if nom:
        parts.append(str(nom))
    else:
        parts.append(f"version {str(version.id)[:8]}")
    try:
        if getattr(version, "created_at", None) is not None:
            parts.append(version.created_at.strftime("%d/%m/%Y"))
    except Exception:
        pass
    nb_r, nb_c = getattr(version, "nb_regards", None), getattr(version, "nb_conduites", None)
    if nb_r is not None or nb_c is not None:
        parts.append(f"{nb_r or 0} regards / {nb_c or 0} conduites")
    return " — ".join(parts)
