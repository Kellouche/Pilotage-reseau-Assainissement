"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Gestionnaire de stockage des fichiers, rapports et rasters MNT
================================================================================
"""

import abc
import mimetypes
import os
from pathlib import Path
from typing import List, Optional, Union
import logging

logger = logging.getLogger(__name__)


class StorageError(Exception):
    """Erreur générique du système de stockage d'artefacts."""
    pass


class StorageNotFoundError(StorageError):
    """Artefact introuvable dans le store."""
    pass


class ArtifactStore(abc.ABC):
    """Interface abstraite pour le stockage d'artefacts d'un réseau."""

    @staticmethod
    def build_key(org_id: str, project_id: str, artifact_path: str) -> str:
        """Construit une clé normalisée et partitionnée par organisation et projet."""
        clean_org = str(org_id).strip().replace("\\", "/").strip("/")
        clean_prj = str(project_id).strip().replace("\\", "/").strip("/")
        clean_path = str(artifact_path).strip().replace("\\", "/").lstrip("/")

        # Protection stricte contre la traversée de répertoire
        parts = clean_path.split("/")
        if ".." in parts:
            raise ValueError(f"Traversée de répertoire interdite dans la clé : {artifact_path}")

        return f"{clean_org}/{clean_prj}/{clean_path}"

    @abc.abstractmethod
    def put_bytes(self, key: str, data: bytes, content_type: Optional[str] = None) -> str:
        """Écrit des données binaires sous la clé spécifiée."""
        pass

    @abc.abstractmethod
    def put_file(self, key: str, local_path: Union[str, Path], content_type: Optional[str] = None) -> str:
        """Téléverse un fichier local vers le store."""
        pass

    @abc.abstractmethod
    def put_bytes_if_absent(self, key: str, data: bytes, content_type: Optional[str] = None) -> bool:
        """
        Création conditionnelle : écrit `data` sous `key` UNIQUEMENT si la clé
        est absente. Retourne True si l'objet a été créé, False s'il existait
        déjà (jamais écrasé). Garantit l'absence d'écrasement pour les stores
        qui le supportent (filesystem, S3 conditionnel).
        """
        pass

    @abc.abstractmethod
    def put_file_if_absent(self, key: str, local_path: Union[str, Path], content_type: Optional[str] = None) -> bool:
        """
        Création conditionnelle depuis un fichier local : même contrat que
        put_bytes_if_absent — jamais d'écrasement d'un objet existant.
        """
        pass

    @abc.abstractmethod
    def get_bytes(self, key: str) -> bytes:
        """Récupère le contenu binaire d'un artefact."""
        pass

    @abc.abstractmethod
    def get_file(self, key: str, destination_path: Union[str, Path]) -> Path:
        """Télécharge un artefact vers un chemin local."""
        pass

    @abc.abstractmethod
    def exists(self, key: str) -> bool:
        """Indique si une clé existe dans le store."""
        pass

    @abc.abstractmethod
    def delete(self, key: str) -> bool:
        """Supprime un artefact. Retourne True si supprimé."""
        pass

    @abc.abstractmethod
    def delete_prefix(self, prefix: str) -> int:
        """Supprime tous les artefacts commençant par un préfixe (ex. suppression de projet)."""
        pass

    @abc.abstractmethod
    def list_keys(self, prefix: str = "") -> List[str]:
        """Liste toutes les clés correspondant à un préfixe donné."""
        pass

    @abc.abstractmethod
    def generate_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Génère une URL d'accès sécurisée temporaire pour téléchargement direct."""
        pass


class LocalStore(ArtifactStore):
    """Stockage local sur système de fichiers pour développement et tests."""

    def __init__(self, root_dir: Union[str, Path]):
        self.root_dir = Path(root_dir).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _normaliser_prefixe_etendu(chemin: str) -> str:
        """
        Sous Windows, Path.resolve() peut retourner la forme étendue
        '\\\\?\\<lecteur>:\\…' de façon non déterministe (notamment quand le
        fichier cible existe déjà au moment de la résolution). On retire ce
        préfixe avant toute comparaison de préfixe de chemin.
        """
        if chemin.startswith("\\\\?\\"):
            return chemin[4:]
        return chemin

    def _resolve(self, key: str) -> Path:
        clean_key = str(key).replace("\\", "/").lstrip("/")
        parts = clean_key.split("/")
        if ".." in parts:
            raise ValueError(f"Clé de stockage invalide : {key}")
        target = (self.root_dir / clean_key).resolve()
        # Vérification anti-traversée : comparaison sur formes normalisées,
        # avec borne de séparateur (évite 'artifacts_evil' pour 'artifacts').
        tgt_str = self._normaliser_prefixe_etendu(str(target))
        root_str = self._normaliser_prefixe_etendu(str(self.root_dir))
        if not (tgt_str == root_str or tgt_str.startswith(root_str + os.sep)):
            raise ValueError(f"Accès hors du répertoire racine interdit : {key}")
        return target

    @staticmethod
    def _ecrire_atomique(target: Path, data: bytes) -> None:
        """
        Écriture atomique : fichier temporaire dans le même répertoire puis
        os.replace() — un lecteur concurrent ne voit jamais un contenu partiel.
        """
        import tempfile
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp",
                                       dir=str(target.parent))
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp_path, target)
        except Exception:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise

    def put_bytes(self, key: str, data: bytes, content_type: Optional[str] = None) -> str:
        target = self._resolve(key)
        self._ecrire_atomique(target, data)
        return key

    def put_file(self, key: str, local_path: Union[str, Path], content_type: Optional[str] = None) -> str:
        src = Path(local_path)
        if not src.exists():
            raise FileNotFoundError(f"Fichier local introuvable : {local_path}")
        target = self._resolve(key)
        # Lecture intégrale puis écriture atomique : cible jamais partielle.
        self._ecrire_atomique(target, src.read_bytes())
        return key

    def _lien_atomique_si_absent(self, tmp_path: Path, target: Path) -> bool:
        """
        Publication conditionnelle : hard-link atomique du fichier temporaire
        vers la cible. os.link() échoue avec FileExistsError si la cible existe
        → création strictement conditionnelle, sans fenêtre exists/put.
        Repli documenté si le système de fichiers ne supporte pas les liens
        durs : re-vérification immédiate puis os.replace() (course résiduelle
        possible sur FS sans hardlink, ex. certains montages réseau).
        """
        try:
            os.link(tmp_path, target)
        except FileExistsError:
            return False
        except OSError:
            if target.exists():
                return False
            os.replace(tmp_path, target)
            return True
        tmp_path.unlink(missing_ok=True)
        return True

    def _put_bytes_si_absent(self, target: Path, data: bytes) -> bool:
        import tempfile
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp",
                                       dir=str(target.parent))
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            return self._lien_atomique_si_absent(tmp_path, target)
        except Exception:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise

    def put_bytes_if_absent(self, key: str, data: bytes, content_type: Optional[str] = None) -> bool:
        return self._put_bytes_si_absent(self._resolve(key), data)

    def put_file_if_absent(self, key: str, local_path: Union[str, Path], content_type: Optional[str] = None) -> bool:
        src = Path(local_path)
        if not src.exists():
            raise FileNotFoundError(f"Fichier local introuvable : {local_path}")
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        import tempfile
        fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp",
                                       dir=str(target.parent))
        tmp_path = Path(tmp_name)
        try:
            os.close(fd)
            # Copie dans le même volume que la cible (prérequis os.link)
            import shutil
            shutil.copyfile(src, tmp_path)
            return self._lien_atomique_si_absent(tmp_path, target)
        except Exception:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise

    def get_bytes(self, key: str) -> bytes:
        target = self._resolve(key)
        if not target.exists() or not target.is_file():
            raise StorageNotFoundError(f"Artefact introuvable : {key}")
        return target.read_bytes()

    def get_file(self, key: str, destination_path: Union[str, Path]) -> Path:
        target = self._resolve(key)
        if not target.exists() or not target.is_file():
            raise StorageNotFoundError(f"Artefact introuvable : {key}")
        dest = Path(destination_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(target.read_bytes())
        return dest

    def exists(self, key: str) -> bool:
        try:
            target = self._resolve(key)
            return target.exists() and target.is_file()
        except ValueError:
            return False

    def delete(self, key: str) -> bool:
        try:
            target = self._resolve(key)
            if target.exists() and target.is_file():
                target.unlink()
                return True
            return False
        except ValueError:
            return False

    def delete_prefix(self, prefix: str) -> int:
        clean_prefix = str(prefix).replace("\\", "/").strip("/")
        target_dir = self.root_dir / clean_prefix
        count = 0
        if target_dir.exists():
            if target_dir.is_dir():
                for p in list(target_dir.rglob("*")):
                    if p.is_file():
                        p.unlink()
                        count += 1
                try:
                    import shutil
                    shutil.rmtree(target_dir, ignore_errors=True)
                except Exception:
                    pass
            elif target_dir.is_file():
                target_dir.unlink()
                count = 1
        return count

    def list_keys(self, prefix: str = "") -> List[str]:
        clean_prefix = str(prefix).replace("\\", "/").strip("/")
        start_dir = self.root_dir / clean_prefix if clean_prefix else self.root_dir
        if not start_dir.exists():
            return []

        keys = []
        if start_dir.is_file():
            rel = start_dir.relative_to(self.root_dir)
            return [str(rel).replace("\\", "/")]

        for p in start_dir.rglob("*"):
            if p.is_file():
                rel = p.relative_to(self.root_dir)
                keys.append(str(rel).replace("\\", "/"))
        return sorted(keys)

    def generate_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        # En mode local, on fournit une URL interne vers le endpoint d'artefacts
        clean_key = str(key).replace("\\", "/").lstrip("/")
        return f"/api/v1/artifacts/download?key={clean_key}"


class S3Store(ArtifactStore):
    """Stockage objet compatible S3 (AWS S3, MinIO, Scaleway, Cloudflare R2)."""

    def __init__(
        self,
        bucket_name: str,
        endpoint_url: Optional[str] = None,
        region_name: str = "eu-west-3",
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
    ):
        try:
            import boto3
            from botocore.config import Config
        except ImportError as e:
            raise StorageError("La bibliothèque 'boto3' est requise pour utiliser S3Store.") from e

        self.bucket_name = bucket_name
        self.endpoint_url = endpoint_url
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region_name,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4"),
        )

    def put_bytes(self, key: str, data: bytes, content_type: Optional[str] = None) -> str:
        clean_key = str(key).replace("\\", "/").lstrip("/")
        mime = content_type or mimetypes.guess_type(clean_key)[0] or "application/octet-stream"
        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=clean_key,
                Body=data,
                ContentType=mime,
            )
            return clean_key
        except Exception as e:
            raise StorageError(f"Échec d'écriture S3 ({clean_key}) : {e}") from e

    def put_file(self, key: str, local_path: Union[str, Path], content_type: Optional[str] = None) -> str:
        clean_key = str(key).replace("\\", "/").lstrip("/")
        src = Path(local_path)
        if not src.exists():
            raise FileNotFoundError(f"Fichier local introuvable : {local_path}")
        mime = content_type or mimetypes.guess_type(str(src))[0] or "application/octet-stream"
        try:
            with open(src, "rb") as f:
                self.client.put_object(
                    Bucket=self.bucket_name,
                    Key=clean_key,
                    Body=f,
                    ContentType=mime,
                )
            return clean_key
        except Exception as e:
            raise StorageError(f"Échec téléversement S3 ({clean_key}) : {e}") from e

    def _put_object_si_absent(self, clean_key: str, body, mime: str) -> bool:
        """
        Création conditionnelle S3 : tentative PutObject avec
        If-None-Match='*' (écriture conditionnelle native, rejet 412 si la
        clé existe). Si le SDK/backend ne supporte pas la condition, repli
        sur exists()+put — une course résiduelle subsiste alors, à assumer
        par l'appelant (pour les clés content-addressed, l'écrasement par un
        contenu identique reste inoffensif).
        Retourne True si l'objet a été créé, False s'il existait déjà.
        """
        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=clean_key,
                Body=body,
                ContentType=mime,
                IfNoneMatch="*",
            )
            return True
        except Exception as e:
            from botocore.exceptions import ClientError, ParamValidationError
            if isinstance(e, ParamValidationError):
                pass  # SDK trop ancien pour If-None-Match → repli ci-dessous
            elif isinstance(e, ClientError):
                code = str(e.response.get("Error", {}).get("Code", ""))
                if code in ("PreconditionFailed", "412", "ConditionalRequestConflict"):
                    return False
                raise StorageError(f"Échec écriture conditionnelle S3 ({clean_key}) : {e}") from e
            else:
                raise StorageError(f"Échec écriture conditionnelle S3 ({clean_key}) : {e}") from e
        # Repli : pas de condition native disponible
        if self.exists(clean_key):
            return False
        self.client.put_object(
            Bucket=self.bucket_name,
            Key=clean_key,
            Body=body,
            ContentType=mime,
        )
        return True

    def put_bytes_if_absent(self, key: str, data: bytes, content_type: Optional[str] = None) -> bool:
        clean_key = str(key).replace("\\", "/").lstrip("/")
        mime = content_type or mimetypes.guess_type(clean_key)[0] or "application/octet-stream"
        return self._put_object_si_absent(clean_key, data, mime)

    def put_file_if_absent(self, key: str, local_path: Union[str, Path], content_type: Optional[str] = None) -> bool:
        clean_key = str(key).replace("\\", "/").lstrip("/")
        src = Path(local_path)
        if not src.exists():
            raise FileNotFoundError(f"Fichier local introuvable : {local_path}")
        mime = content_type or mimetypes.guess_type(str(src))[0] or "application/octet-stream"
        with open(src, "rb") as f:
            return self._put_object_si_absent(clean_key, f, mime)

    def get_bytes(self, key: str) -> bytes:
        clean_key = str(key).replace("\\", "/").lstrip("/")
        try:
            resp = self.client.get_object(Bucket=self.bucket_name, Key=clean_key)
            return resp["Body"].read()
        except self.client.exceptions.NoSuchKey:
            raise StorageNotFoundError(f"Artefact S3 introuvable : {key}")
        except Exception as e:
            raise StorageError(f"Erreur lecture S3 ({clean_key}) : {e}") from e

    def get_file(self, key: str, destination_path: Union[str, Path]) -> Path:
        data = self.get_bytes(key)
        dest = Path(destination_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return dest

    def exists(self, key: str) -> bool:
        clean_key = str(key).replace("\\", "/").lstrip("/")
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=clean_key)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> bool:
        clean_key = str(key).replace("\\", "/").lstrip("/")
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=clean_key)
            return True
        except Exception:
            return False

    def delete_prefix(self, prefix: str) -> int:
        clean_prefix = str(prefix).replace("\\", "/").lstrip("/")
        count = 0
        try:
            paginator = self.client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=clean_prefix):
                items = page.get("Contents", [])
                if items:
                    delete_objects = [{"Key": item["Key"]} for item in items]
                    self.client.delete_objects(
                        Bucket=self.bucket_name,
                        Delete={"Objects": delete_objects}
                    )
                    count += len(delete_objects)
            return count
        except Exception as e:
            raise StorageError(f"Échec suppression préfixe S3 ({clean_prefix}) : {e}") from e

    def list_keys(self, prefix: str = "") -> List[str]:
        clean_prefix = str(prefix).replace("\\", "/").lstrip("/")
        keys = []
        try:
            paginator = self.client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=clean_prefix):
                for item in page.get("Contents", []):
                    keys.append(item["Key"])
            return sorted(keys)
        except Exception as e:
            raise StorageError(f"Échec listing S3 ({clean_prefix}) : {e}") from e

    def generate_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        clean_key = str(key).replace("\\", "/").lstrip("/")
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": clean_key},
                ExpiresIn=expires_in,
            )
        except Exception as e:
            raise StorageError(f"Échec URL présignée S3 ({clean_key}) : {e}") from e


def get_storage(backend: Optional[str] = None, root_dir: Optional[str] = None) -> ArtifactStore:
    """
    Factory pour obtenir l'instance d'ArtifactStore selon la configuration environnement.
    Par défaut en dev/test : LocalStore dans 'uploads/artifacts'.
    En production : S3Store configuré via variables d'environnement.
    """
    mode = backend or os.environ.get("STORAGE_BACKEND", "local").lower()

    if mode == "s3":
        bucket = os.environ.get("S3_BUCKET_NAME", "swmm-platform-artifacts")
        endpoint = os.environ.get("S3_ENDPOINT_URL")
        region = os.environ.get("S3_REGION_NAME", "eu-west-3")
        access_key = os.environ.get("AWS_ACCESS_KEY_ID")
        secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
        return S3Store(
            bucket_name=bucket,
            endpoint_url=endpoint,
            region_name=region,
            access_key=access_key,
            secret_key=secret_key,
        )

    target_root = root_dir or os.environ.get("STORAGE_LOCAL_ROOT", "uploads/artifacts")
    return LocalStore(root_dir=target_root)


# Alias de rétro-compatibilité
get_artifact_store = get_storage


# Helpers normalisés pour les artefacts SWMM Platform
def build_network_gpkg_key(org_id: str, project_id: str, filename: str = "network.gpkg") -> str:
    return ArtifactStore.build_key(org_id, project_id, f"gis/{filename}")


def build_dem_key(org_id: str, project_id: str, filename: str = "dem.tif") -> str:
    return ArtifactStore.build_key(org_id, project_id, f"rasters/{filename}")


def build_swmm_inp_key(org_id: str, project_id: str, filename: str = "model.inp") -> str:
    return ArtifactStore.build_key(org_id, project_id, f"swmm/{filename}")


def build_simulation_result_key(org_id: str, project_id: str, job_id: str, filename: str) -> str:
    return ArtifactStore.build_key(org_id, project_id, f"simulations/{job_id}/{filename}")


def build_inspection_photo_key(org_id: str, project_id: str, inspection_id: str, filename: str) -> str:
    return ArtifactStore.build_key(org_id, project_id, f"inspections/{inspection_id}/{filename}")
