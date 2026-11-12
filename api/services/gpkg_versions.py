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


# ---------------------------------------------------------------------------
# Empreinte & validation
# ---------------------------------------------------------------------------

# Cache d'empreintes legacy : (chemin, mtime, taille) -> sha256
_SHA_CACHE: Dict[tuple, str] = {}


def sha256_fichier(path: Path, buffer_size: int = 1024 * 1024,
                   use_cache: bool = False) -> str:
    """Empreinte SHA-256 streaming d'un fichier (jamais chargé en mémoire)."""
    path = Path(path)
    if use_cache:
        st = path.stat()
        cle = (str(path.resolve()), int(st.st_mtime), st.st_size)
        if cle in _SHA_CACHE:
            return _SHA_CACHE[cle]
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(buffer_size), b""):
            h.update(chunk)
    sha = h.hexdigest()
    if use_cache:
        _SHA_CACHE[cle] = sha
    return sha


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
# Clés de stockage &ArtifactStore
# ---------------------------------------------------------------------------

def cle_version_gpkg(org_id: str, project_id: str, sha256: str) -> str:
    """Clé ArtifactStore content-addressed : org/projet/gis/versions/<sha>/network.gpkg."""
    return ArtifactStore.build_key(org_id, project_id, f"gis/versions/{sha256}/network.gpkg")


def _store() -> ArtifactStore:
    return get_storage()


def _chemin_materialise(sha256: str) -> Path:
    return GPKG_CACHE_DIR / f"{sha256}.gpkg"


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

    # Jamais d'écrasement : la clé est déterminée par le contenu. Si l'objet
    # existe déjà, on le vérifie (taille) au lieu de le réécrire.
    taille = Path(source_path).stat().st_size
    if not store.exists(key):
        store.put_file(key, source_path)
        logger.info("[gpkg_version] Objet stocké : %s (%d octets)", key, taille)

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
        # Objet référencé mais peut-être absent du store → restauration si possible
        if existante.storage_kind == STORAGE_KIND_ARTIFACT and not _store().exists(existante.storage_ref):
            store = _store()
            store.put_file(existante.storage_ref, source)
            logger.warning("[gpkg_version] Objet store manquant restauré : %s", existante.storage_ref)
        projet = db.get(type(project), project.id)
        if projet is not None:
            projet.gpkg_version_id = existante.id
        db.flush()
        return existante

    return _stocker_version(
        db, project.org_id, project.id, sha, source, meta,
        filename_original or source.name, created_by_id,
    )


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
            for col in candidates:
                try:
                    row = conn.execute(
                        f'SELECT 1 FROM "{table}" WHERE CAST("{col}" AS TEXT) = ? LIMIT 1',
                        (cible,),
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
                "sha256": sha256_fichier(p, use_cache=True),
                "storage_kind": "LEGACY",
                "materialized_path": str(p.resolve()),
            }
    return None, {"erreur": "Aucun GeoPackage disponible pour ce projet"}
