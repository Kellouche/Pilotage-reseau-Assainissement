"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-27
Objet : Endpoints de gestion du réseau physique (nœuds, conduites, regards, exutoires)
================================================================================
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form, Response
from sqlalchemy.orm import Session
from typing import List, Optional
from pathlib import Path

from api.database import get_db
from api import schemas, crud
from api.models import Project, Organization
from api.core.security import (
    get_tenant_context,
    get_tenant_context_optional,
    require_role,
    TenantContext,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/network", tags=["Réseau"])


def _enregistrer_version_gpkg(db: Session, project, gpkg_path, filename_original=None,
                              created_by_id=None, strict: bool = False):
    """
    Enregistre le GeoPackage comme version immuable (étape 3B).
    strict=True : un GPKG invalide fait échouer la requête (HTTP 400).
    Les erreurs de stockage sont journalisées sans bloquer le flux legacy.
    """
    from api.services.gpkg_versions import enregistrer_version_gpkg, GpkgInvalide
    try:
        return enregistrer_version_gpkg(
            db, project, gpkg_path,
            filename_original=filename_original, created_by_id=created_by_id,
        )
    except GpkgInvalide as e:
        if strict:
            raise HTTPException(status_code=400, detail=f"GeoPackage invalide : {e}")
        logger.warning("[gpkg_version] GPKG invalide pour %s : %s",
                       getattr(project, "id", "?"), e)
        return None
    except Exception as e:
        logger.warning("[gpkg_version] Enregistrement de version impossible pour %s : %s",
                       getattr(project, "id", "?"), e)
        return None


# ============================================================
# REGARDS
# ============================================================

@router.get("/regards", response_model=schemas.RegardListResponse)
def list_regards(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    commune: Optional[str] = None,
    cluster_id: Optional[int] = None,
    ctx: TenantContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db)
):
    """Liste des regards avec filtres optionnels cloisonnés par organisation."""
    regards = crud.get_regards(
        db=db,
        skip=skip,
        limit=limit,
        commune=commune,
        cluster_id=cluster_id,
        org_id=ctx.org_id,
    )
    total = len(regards)  # Pour POC, on compte simplement
    return {
        "regards": regards,  # objets ORM, Pydantic utilisera orm_mode
        "total": total,
        "page": skip // limit + 1,
        "page_size": limit
    }


@router.get("/regards/{regard_id}", response_model=schemas.RegardResponse)
def get_regard(
    regard_id: int,
    ctx: TenantContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db)
):
    """Détail d'un regard par ID (stealth 404 si hors organisation)."""
    regard = crud.get_regard(db, regard_id, org_id=ctx.org_id)
    if not regard:
        raise HTTPException(status_code=404, detail="Ressource introuvable")
    return regard.to_dict()


@router.post("/regards", response_model=schemas.RegardResponse, status_code=status.HTTP_201_CREATED)
def create_regard(
    regard: schemas.RegardCreate,
    ctx: TenantContext = Depends(require_role("engineer")),
    db: Session = Depends(get_db)
):
    """Crée un nouveau regard pour l'organisation active."""
    user_id = ctx.user.id if ctx.user else str(ctx.actor.id)
    try:
        regard_obj = crud.create_regard(
            db=db,
            regard_data=regard.dict(),
            user_id=user_id,
            org_id=ctx.org_id,
        )
        return regard_obj.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


from api.websocket import manager

@router.patch("/regards/{regard_id}", response_model=schemas.RegardResponse)
async def update_regard(
    regard_id: str,
    update: schemas.RegardUpdate,
    ctx: TenantContext = Depends(require_role("engineer")),
    db: Session = Depends(get_db)
):
    """Met à jour partiellement un regard appartenant à l'organisation."""
    user_id = ctx.user.id if ctx.user else str(ctx.actor.id)
    updated = crud.update_regard(
        db=db,
        regard_id=regard_id,
        update_data=update.dict(exclude_unset=True),
        user_id=user_id,
        org_id=ctx.org_id,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Ressource introuvable")
        
    msg = f"Objet : Regard {updated.code or updated.id} modifié par {user_id} [{updated.longitude},{updated.latitude}]"
    await manager.broadcast(msg)
    
    return updated.to_dict()


@router.delete("/regards/{regard_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_regard(
    regard_id: int,
    ctx: TenantContext = Depends(require_role("engineer")),
    db: Session = Depends(get_db)
):
    """Supprime un regard de l'organisation."""
    user_id = ctx.user.id if ctx.user else str(ctx.actor.id)
    success = crud.delete_regard(db, regard_id, user_id=user_id, org_id=ctx.org_id)
    if not success:
        raise HTTPException(status_code=404, detail="Ressource introuvable")
    return None


# ============================================================
# CANALISATIONS
# ============================================================

@router.get("/conduites", response_model=List[schemas.CanalisationResponse])
def list_conduites(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    cluster_id: Optional[int] = None,
    ctx: TenantContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db)
):
    """Liste des canalisations cloisonnées par organisation."""
    conduites = crud.get_canalisations(
        db=db,
        skip=skip,
        limit=limit,
        cluster_id=cluster_id,
        org_id=ctx.org_id,
    )
    return conduites  # Retourne objets ORM directly, Pydantic gère via orm_mode


@router.get("/conduites/{conduite_id}", response_model=schemas.CanalisationResponse)
def get_conduite(
    conduite_id: int,
    ctx: TenantContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db)
):
    """Détail d'une canalisation (stealth 404 si hors organisation)."""
    conduite = crud.get_canalisation(db, conduite_id, org_id=ctx.org_id)
    if not conduite:
        raise HTTPException(status_code=404, detail="Ressource introuvable")
    return conduite.to_dict()


@router.post("/conduites", response_model=schemas.CanalisationResponse, status_code=status.HTTP_201_CREATED)
def create_conduite(
    conduite: schemas.CanalisationCreate,
    ctx: TenantContext = Depends(require_role("engineer")),
    db: Session = Depends(get_db)
):
    """Crée une nouvelle canalisation pour l'organisation active."""
    user_id = ctx.user.id if ctx.user else str(ctx.actor.id)
    try:
        conduite_obj = crud.create_canalisation(
            db=db,
            canalisation_data=conduite.dict(),
            user_id=user_id,
            org_id=ctx.org_id,
        )
        return conduite_obj.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/conduites/{conduite_id}", response_model=schemas.CanalisationResponse)
async def update_conduite(
    conduite_id: str,
    update: schemas.CanalisationUpdate,
    ctx: TenantContext = Depends(require_role("engineer")),
    db: Session = Depends(get_db)
):
    """Met à jour une canalisation de l'organisation."""
    user_id = ctx.user.id if ctx.user else str(ctx.actor.id)
    updated = crud.update_canalisation(
        db=db,
        canalisation_id=conduite_id,
        update_data=update.dict(exclude_unset=True),
        user_id=user_id,
        org_id=ctx.org_id,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Ressource introuvable")
        
    msg = f"Objet : Conduite {updated.fid or updated.id} modifiée par {user_id} [0.0,0.0]"
    await manager.broadcast(msg)
    
    return updated.to_dict()


@router.delete("/conduites/{conduite_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conduite(
    conduite_id: int,
    ctx: TenantContext = Depends(require_role("engineer")),
    db: Session = Depends(get_db)
):
    """Supprime une canalisation de l'organisation."""
    user_id = ctx.user.id if ctx.user else str(ctx.actor.id)
    success = crud.delete_canalisation(db, conduite_id, user_id=user_id, org_id=ctx.org_id)
    if not success:
        raise HTTPException(status_code=404, detail="Ressource introuvable")
    return None


# ============================================================
# REJETS
# ============================================================

@router.get("/rejets", response_model=List[schemas.RejetResponse])
def list_rejets(
    skip: int = 0,
    limit: int = 100,
    ctx: TenantContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db)
):
    """Liste des rejets (exutoires) cloisonnés par organisation."""
    from api.models import Rejet
    rejets = db.query(Rejet).filter(Rejet.org_id == ctx.org_id).offset(skip).limit(limit).all()
    return [r.to_dict() for r in rejets]


@router.post("/rejets", response_model=schemas.RejetResponse, status_code=status.HTTP_201_CREATED)
def create_rejet(
    rejet: schemas.RejetCreate,
    ctx: TenantContext = Depends(require_role("engineer")),
    db: Session = Depends(get_db)
):
    """Crée un nouveau rejet."""
    # TODO: implémenter si besoin
    raise HTTPException(status_code=501, detail="À implémenter")


# ============================================================
# GESTION DES PROJETS & CHARGEMENT DE RÉSEAUX (OPTION B)
# ============================================================


@router.post("/reset")
def reset_project_network(
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Réinitialise le projet actif vers un espace vierge (Option B)."""
    project = db.query(Project).filter(
        Project.org_id == tenant_ctx.org_id,
        Project.is_archived.is_(False)
    ).first()

    if project:
        project.source_gpkg_key = None
        project.gpkg_version_id = None
        project.nodes_count = 0
        project.pipes_count = 0
        project.outfalls_count = 0
        project.name = "Nouveau Projet (Vierge)"
        db.commit()


    try:
        from api.routes.qualite import reinitialiser_cache_qualite
        reinitialiser_cache_qualite()
    except Exception:
        pass
    try:
        from api.main import reset_layers_cache
        reset_layers_cache()
    except Exception:
        pass
    try:
        from api.routes.clusters import _reset_graph_cache
        _reset_graph_cache()
    except Exception:
        pass

    return {"status": "ok", "message": "Projet réinitialisé vers un espace vierge."}


@router.post("/upload")
async def upload_network_gpkg(
    file: UploadFile = File(...),
    crs: Optional[str] = Form(None),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """
    Téléverse un fichier GeoPackage (.gpkg) ou EPA SWMM (.inp) pour le projet actif.

    Règle CRS : si le fichier ne déclare pas de projection (ou si la détection
    .inp est incertaine), le paramètre `crs` (code EPSG, ex. "EPSG:32631") est
    **obligatoire** — sans lui, toutes les mesures spatiales seraient faussées.
    """
    fname_lower = (file.filename or "").lower()
    if not (fname_lower.endswith(".gpkg") or fname_lower.endswith(".inp")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Format non supporté. Veuillez téléverser un fichier .gpkg (GeoPackage) ou .inp (EPA SWMM)."
        )

    upload_dir = Path(f"uploads/{tenant_ctx.org_id}")
    upload_dir.mkdir(parents=True, exist_ok=True)
    raw_target_path = upload_dir / f"network_{file.filename}"

    content = await file.read()
    with open(raw_target_path, "wb") as f:
        f.write(content)

    conv_summary = None
    crs_resultat = None
    crs_source_resultat = None
    if fname_lower.endswith(".inp"):
        # Conversion transparente du fichier EPA SWMM .inp vers GeoPackage (.gpkg)
        from src.domain.inp_parser import convertir_inp_vers_gpkg
        gpkg_target_path = raw_target_path.with_suffix(".gpkg")
        try:
            conv_summary = convertir_inp_vers_gpkg(
                raw_target_path, gpkg_target_path, force_crs=crs)
            crs_resultat = conv_summary.get("crs")
            crs_source_resultat = conv_summary.get("crs_source")
            # .inp ne porte jamais de CRS : si l'heursement d'emprise est
            # tombé sur le repli par défaut ("defaut"/"absent") et que
            # l'utilisateur n'a rien fourni, on EXIGE la projection.
            if crs_source_resultat in ("defaut", "absent") and not crs:
                try:
                    gpkg_target_path.unlink(missing_ok=True)
                except Exception:
                    pass
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Projection indéterminée pour ce fichier .inp : les coordonnées "
                        "ne correspondent à aucune signature reconnue (WGS84, UTM, Lambert). "
                        "Renvoyez le fichier avec le paramètre `crs` renseigné "
                        "(ex. crs=EPSG:32631) pour garantir l'exactitude des mesures."
                    ),
                )
            target_path = gpkg_target_path
        except HTTPException:
            raise
        except Exception as e_conv:
            logger.exception("Échec de la conversion du fichier .inp : %s", e_conv)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Erreur lors de l'analyse du fichier SWMM .inp : {str(e_conv)}"
            )
    else:
        target_path = raw_target_path
        # Règle CRS : un GeoPackage sans projection déclarée est refusé tant
        # que l'utilisateur n'a pas renseigné `crs` — sinon toutes les mesures
        # spatiales (longueurs, surfaces, profils) seraient faussées.
        from api.services.gpkg_versions import detecter_crs_gpkg, appliquer_crs_gpkg
        crs_resultat = detecter_crs_gpkg(target_path)
        if crs_resultat is None:
            if not crs:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Ce GeoPackage ne déclare aucune projection (CRS absent). "
                        "Renvoyez le fichier avec le paramètre `crs` renseigné "
                        "(ex. crs=EPSG:32631 pour l'Algérie, ou le code EPSG de votre "
                        "projection source) — sans projection fiable, les mesures "
                        "hydrauliques et spatiales ne peuvent pas être garanties."
                    ),
                )
            try:
                crs_resultat = appliquer_crs_gpkg(target_path, crs)
                crs_source_resultat = "utilisateur"
            except ValueError as e_crs:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e_crs),
                )
        else:
            crs_source_resultat = "fichier"

    # Invalidation des anciens fichiers caches associés à ce fichier
    for ext in [".clusters_cache.json", ".subcatchments_cache.json", ".qualite_cache.json"]:
        cp = target_path.with_suffix(ext)
        if cp.exists():
            try:
                cp.unlink()
            except Exception:
                pass

    project = db.query(Project).filter(
        Project.org_id == tenant_ctx.org_id,
        Project.is_archived.is_(False)
    ).first()

    if not project:
        project = Project(
            org_id=tenant_ctx.org_id,
            name=file.filename.rsplit(".", 1)[0],
        )
        db.add(project)
        db.flush()

    project.name = file.filename.rsplit(".", 1)[0]
    project.source_gpkg_key = str(target_path)
    # Étape 3B : versionnement immuable — un GPKG invalide est rejeté (400)
    version = _enregistrer_version_gpkg(
        db, project, target_path,
        filename_original=file.filename,
        created_by_id=getattr(tenant_ctx.user, "id", None) if tenant_ctx else None,
        strict=True,
    )
    db.commit()

    # Inventaire réel de détection (couches reconnues + comptages) issu de la
    # validation du GPKG — verdict d'import exposé à l'utilisateur.
    inventaire = getattr(version, "_inventaire_meta", None) or {}
    rapport_inventaire = {
        "couches_detectees": inventaire.get("couches", []),
        "couche_regards": inventaire.get("couche_regards"),
        "couche_canalisations": inventaire.get("couche_canalisations"),
        "couche_rejets": inventaire.get("couche_rejets"),
        "nb_regards": inventaire.get("nb_regards"),
        "nb_conduites": inventaire.get("nb_conduites"),
        "nb_rejets": inventaire.get("nb_rejets"),
    }


    try:
        from api.routes.qualite import reinitialiser_cache_qualite
        reinitialiser_cache_qualite()
    except Exception:
        pass
    try:
        from api.main import reset_layers_cache
        reset_layers_cache()
    except Exception:
        pass
    try:
        from api.routes.clusters import _reset_graph_cache
        _reset_graph_cache()
    except Exception:
        pass

    msg = conv_summary.get("message") if (conv_summary and "message" in conv_summary) else f"Fichier {file.filename} téléversé et associé à votre projet avec succès."

    return {
        "status": "ok",
        "message": msg,
        "conversion": conv_summary,
        "crs": crs_resultat,
        "crs_source": crs_source_resultat,
        "inventaire": rapport_inventaire,
        "project": {
            "id": project.id,
            "name": project.name,
        }
    }


# ============================================================
# HYDROLOGIE & SOUS-BASSINS (SWMM SUBCATCHMENTS)
# ============================================================
