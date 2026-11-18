# -*- coding: utf-8 -*-
"""
Endpoints d'extraction par pochoir (SHP.md — outil SIG).

POST /projets/{project_id}/extraction-pochoir
  Corps : { nom, geojson (Polygon/MultiPolygon EPSG:4326),
            inclure_reseau?, aux_layer_ids? }
  → zip thématique ({nom}_regard.shp … + {nom}.gpkg + manifeste.json)
    déposé dans l'ArtifactStore ; téléchargement via
    GET /api/v1/artifacts/download?key=…&project_id=…
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.core.security import TenantContext, get_tenant_context
from api.database import get_db
from api.services import extraction_pochoir_service as svc

router = APIRouter()


class ExtractionPochoirRequest(BaseModel):
    nom: str = Field(..., min_length=1, max_length=120,
                     description="Nom de base des fichiers produits")
    geojson: dict = Field(..., description="Polygone pochoir GeoJSON (EPSG:4326)")
    inclure_reseau: bool = Field(True, description="Extraire le réseau projet")
    aux_layer_ids: Optional[List[str]] = Field(
        None, description="Identifiants des couches satellites à inclure")


@router.post("/projets/{project_id}/extraction-pochoir")
def extraire_par_pochoir(
    project_id: str,
    payload: ExtractionPochoirRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Extrait réseau/couches satellites par polygone pochoir → zip téléchargeable."""
    try:
        resultat = svc.extraire_par_pochoir(
            db=db,
            org_id=tenant_ctx.org_id,
            project_id=project_id,
            nom=payload.nom,
            geojson_geom=payload.geojson,
            inclure_reseau=payload.inclure_reseau,
            aux_layer_ids=payload.aux_layer_ids or [],
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Échec de l'extraction : {e}")
    return {"statut": "ok", "extraction": resultat}
