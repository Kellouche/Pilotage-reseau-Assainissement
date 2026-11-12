"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Endpoints de gestion et téléchargement des artefacts de simulation
================================================================================
"""

import mimetypes
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response, RedirectResponse
from sqlalchemy.orm import Session

from api.core.security import get_tenant_context, TenantContext
from api.core.storage import get_storage, LocalStore, S3Store, StorageNotFoundError
from api.database import get_db
from api.models import Project

router = APIRouter(prefix="/artifacts", tags=["Artefacts & Stockage"])


@router.get("/download")
def download_artifact(
    key: str = Query(..., description="Clé de l'artefact stocké ({org_id}/{project_id}/...)"),
    project_id: Optional[str] = Query(
        None,
        description="Projet attendu — obligatoire pour les clés relevant d'un projet",
    ),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Télécharge un artefact en garantissant l'isolation stricte.
    - Le préfixe `{org_id}/` est obligatoire (stealth 404 sinon).
    - Si le second segment de la clé est un projet de l'organisation,
      `project_id` doit être fourni et identique à ce segment : une clé
      d'un AUTRE projet de la même organisation est refusée (3C.7.5).
    - Les segments non-projet (ex. `licences/`) restent sous le seul
      contrôle d'organisation (comportement legacy conservé).
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

    # Isolation projet : le segment projet de la clé est résolu en base.
    segments = clean_key.split("/")
    key_project_id = segments[1] if len(segments) > 2 else None
    if key_project_id:
        projet_cle = db.get(Project, key_project_id)
        if projet_cle is not None and projet_cle.org_id == tenant.org.id:
            # Clé rattachée à un projet : le contexte projet doit correspondre
            if not project_id or str(project_id) != str(key_project_id):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Artefact introuvable",
                )
        elif project_id:
            # Segment non-projet mais project_id fourni : refus par prudence
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
