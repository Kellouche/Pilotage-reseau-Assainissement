# -*- coding: utf-8 -*-
"""
================================================================================
Couches SIG « satellite » — endpoints (SHP.md)
================================================================================
Indépendance totale : aucune de ces routes ne touche le GPKG projet, les
tables réseau ou le pipeline SWMM/.inp. Isolation org_id stricte + stealth 404.

Upload PILOTÉ par l'utilisateur : fichier + type de couche déclarés
explicitement — aucun import automatique.
================================================================================
"""

import logging
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from api.core.security import TenantContext, get_tenant_context
from api.database import get_db
from api.models import Project, ProjectAuxLayer
from api.services import aux_layers_service as svc

logger = logging.getLogger(__name__)

router = APIRouter()


def _projet_org(db: Session, tenant_ctx: TenantContext, project_id: str) -> Project:
    """Résout le projet et garantit l'appartenance à l'org (stealth 404)."""
    projet = db.query(Project).filter(
        Project.id == project_id,
        Project.org_id == tenant_ctx.org_id,
        Project.is_archived.is_(False),
    ).first()
    if not projet:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projet introuvable.")
    return projet


def _couche(db: Session, tenant_ctx: TenantContext, project_id: str, layer_id: str) -> ProjectAuxLayer:
    """Résout la couche satellite — stealth 404 si org/projet mismatch."""
    _projet_org(db, tenant_ctx, project_id)
    couche = db.query(ProjectAuxLayer).filter(
        ProjectAuxLayer.id == layer_id,
        ProjectAuxLayer.project_id == project_id,
        ProjectAuxLayer.org_id == tenant_ctx.org_id,
    ).first()
    if not couche:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Couche introuvable.")
    return couche


@router.post("/projets/{project_id}/aux-layers")
async def upload_aux_layer(
    project_id: str,
    file: UploadFile = File(...),
    type: str = Form(...),
    nom: Optional[str] = Form(None),
    colonne_z: Optional[str] = Form(None),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Import d'une couche SIG satellite — action explicite de l'utilisateur.

    - `file` : .gpkg, .geojson ou .zip (jeu .shp complet + sidecars)
    - `type` : altimetrie_points | bv_officiel | metrologie | autre
    - `colonne_z` : (altimetrie_points) nom du champ d'altitude si non
      auto-détectable (ex. Field4 pour TOPO CHLEF)
    """
    _projet_org(db, tenant_ctx, project_id)

    if type not in svc.TYPES_VALIDES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Type invalide. Attendu : {sorted(svc.TYPES_VALIDES)}",
        )

    suffixe = Path(file.filename or "").suffix.lower()
    if suffixe not in svc.EXTENSIONS_ACCEPTEES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Format non supporté. Attendu : .gpkg, .geojson ou .zip "
                   "(un .shp seul est refusé : sidecars requis).",
        )

    # Écriture temporaire du fichier uploadé
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffixe, prefix="aux_upload_") as tmp:
        contenu = await file.read()
        if len(contenu) > svc.TAILLE_MAX_OCTETS:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                detail="Fichier trop volumineux (limite 200 Mo).")
        tmp.write(contenu)
        tmp_path = Path(tmp.name)

    try:
        try:
            resultat = svc.importer_couche_aux(
                db=db,
                org_id=tenant_ctx.org_id,
                project_id=project_id,
                type_couche=type,
                nom=nom or (file.filename or "couche"),
                fichier_path=tmp_path,
                fichier_nom=file.filename or "couche",
                colonne_z=colonne_z,
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        # Couche altimétrique : construction de la grille IDW (post-import)
        if type == "altimetrie_points":
            couche = db.query(ProjectAuxLayer).filter(
                ProjectAuxLayer.id == resultat["id"],
                ProjectAuxLayer.org_id == tenant_ctx.org_id,
            ).first()
            if couche is not None:
                try:
                    from api.services import aux_altimetrie_service as alt
                    meta_grille = alt.construire_grille_altimetrie(
                        org_id=tenant_ctx.org_id,
                        project_id=project_id,
                        layer_id=couche.id,
                        storage_key=couche.storage_key,
                        colonne_z=couche.colonne_z or colonne_z,
                    )
                    couche.statut = "ok"
                    db.commit()
                    resultat["grille_altimetrie"] = meta_grille
                except Exception as e:
                    logger.warning("Grille altimétrique non construite (%s) : %s", couche.id, e)
                    couche.statut = "sans_altitude"
                    db.commit()
                    resultat["statut"] = "sans_altitude"
                    resultat["grille_altimetrie"] = None
                    resultat["avertissement"] = (
                        "Couche importée mais aucune altitude exploitable : "
                        f"{e}. Renseignez 'colonne_z' à l'upload."
                    )

        return {"statut": "ok", "couche": resultat}

    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


@router.get("/projets/{project_id}/aux-layers")
def list_aux_layers(
    project_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Liste les couches satellite du projet (isolation org)."""
    _projet_org(db, tenant_ctx, project_id)
    couches = db.query(ProjectAuxLayer).filter(
        ProjectAuxLayer.project_id == project_id,
        ProjectAuxLayer.org_id == tenant_ctx.org_id,
    ).order_by(ProjectAuxLayer.created_at.desc()).all()
    return {"statut": "ok", "couches": [c.to_dict() for c in couches]}


@router.get("/projets/{project_id}/aux-layers/{layer_id}")
def get_aux_layer(
    project_id: str,
    layer_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Détail d'une couche satellite."""
    couche = _couche(db, tenant_ctx, project_id, layer_id)
    return {"statut": "ok", "couche": couche.to_dict()}


@router.get("/projets/{project_id}/aux-layers/{layer_id}/geojson")
def get_aux_layer_geojson(
    project_id: str,
    layer_id: str,
    bounds: Optional[str] = Query(None, description="minx,miny,maxx,maxy en EPSG:4326"),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Flux GeoJSON borné de la couche satellite."""
    couche = _couche(db, tenant_ctx, project_id, layer_id)

    b = None
    if bounds:
        try:
            vals = [float(v) for v in bounds.split(",")]
            if len(vals) != 4:
                raise ValueError
            b = tuple(vals)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Paramètre bounds invalide : attendu minx,miny,maxx,maxy")

    try:
        geojson = svc.geojson_couche(
            layer_id=couche.id,
            storage_key=couche.storage_key,
            nb_features=couche.nb_features,
            bounds=b,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Erreur lecture couche satellite %s", layer_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Erreur lecture couche : {e}")

    return {"statut": "ok", "type": "FeatureCollection", "couche": couche.to_dict(),
            "features": geojson.get("features", []),
            "nb_features": len(geojson.get("features", []))}


@router.get("/projets/{project_id}/aux-layers/{layer_id}/elevation")
def get_aux_layer_elevation(
    project_id: str,
    layer_id: str,
    lng: float = Query(...),
    lat: float = Query(...),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Sonde altimétrique : cote terrain interpolée (IDW) + confiance.
    Réservé aux couches `altimetrie_points` avec grille construite.
    """
    couche = _couche(db, tenant_ctx, project_id, layer_id)
    if couche.type != "altimetrie_points":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="La sonde altimétrique n'est disponible que pour les couches 'altimetrie_points'.")
    if couche.statut != "ok":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Aucune altitude exploitable pour cette couche (statut : "
                                   f"{couche.statut}). Renseignez 'colonne_z' à l'upload.")

    from api.services import aux_altimetrie_service as alt
    try:
        return alt.elevation(
            org_id=tenant_ctx.org_id,
            project_id=project_id,
            layer_id=couche.id,
            lng=lng,
            lat=lat,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception("Erreur elevation couche %s", layer_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Erreur calcul altimétrique : {e}")
