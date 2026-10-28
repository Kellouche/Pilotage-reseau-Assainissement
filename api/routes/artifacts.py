"""
Routes pour le téléchargement sécurisé des artefacts (GeoPackage, MNT raster, rapports, modèles SWMM).
Phase 2.1 & 2.2 — Conforme ADR-0004 et règle de furtivité ADR-0001 (Stealth 404).
"""

import mimetypes
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response, RedirectResponse

from api.core.security import get_tenant_context, TenantContext
from api.core.storage import get_storage, LocalStore, S3Store, StorageNotFoundError

router = APIRouter(prefix="/artifacts", tags=["Artefacts & Stockage"])


@router.get("/download")
def download_artifact(
    key: str = Query(..., description="Clé de l'artefact stocké ({org_id}/{project_id}/...)"),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Télécharge un artefact en garantissant l'isolation stricte par organisation.
    Toute tentative d'accès à la clé d'un autre tenant renvoie HTTP 404 furtif.
    """
    clean_key = str(key).replace("\\", "/").lstrip("/")

    # Règle d'invisibilité : la clé DOIT appartenir à l'organisation du jeton
    expected_prefix = f"{tenant.org.id}/"
    if not clean_key.startswith(expected_prefix):
        # Stealth 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artefact introuvable",
        )

    storage = get_storage()

    if isinstance(storage, LocalStore):
        try:
            data = storage.get_bytes(clean_key)
            mime, _ = mimetypes.guess_type(clean_key)
            mime = mime or "application/octet-stream"
            filename = clean_key.split("/")[-1]
            return Response(
                content=data,
                media_type=mime,
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        except StorageNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Artefact introuvable",
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Artefact introuvable",
            )

    elif isinstance(storage, S3Store):
        if not storage.exists(clean_key):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Artefact introuvable",
            )
        presigned_url = storage.generate_presigned_url(clean_key, expires_in=1800)
        return RedirectResponse(url=presigned_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    raise HTTPException(status_code=500, detail="Backend de stockage non supporté")
