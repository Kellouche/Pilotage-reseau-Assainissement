"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Endpoints de gestion du réseau physique (nœuds, conduites, regards, exutoires)
================================================================================
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Response
from sqlalchemy.orm import Session
from typing import List, Optional
from pathlib import Path

from api.database import get_db
from api import schemas, crud
from api.models import Project, Organization
from api.core.security import get_tenant_context, get_tenant_context_optional, TenantContext

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
    db: Session = Depends(get_db)
):
    """Liste des regards avec filtres optionnels."""
    regards = crud.get_regards(
        db=db,
        skip=skip,
        limit=limit,
        commune=commune,
        cluster_id=cluster_id
    )
    total = len(regards)  # Pour POC, on compte simplement
    return {
        "regards": regards,  # objets ORM, Pydantic utilisera orm_mode
        "total": total,
        "page": skip // limit + 1,
        "page_size": limit
    }


@router.get("/regards/{regard_id}", response_model=schemas.RegardResponse)
def get_regard(regard_id: int, db: Session = Depends(get_db)):
    """Détail d'un regard par ID."""
    regard = crud.get_regard(db, regard_id)
    if not regard:
        raise HTTPException(status_code=404, detail="Regard non trouvé")
    return regard.to_dict()


@router.post("/regards", response_model=schemas.RegardResponse, status_code=status.HTTP_201_CREATED)
def create_regard(regard: schemas.RegardCreate, user_id: str = "system", db: Session = Depends(get_db)):
    """Crée un nouveau regard."""
    try:
        regard_obj = crud.create_regard(
            db=db,
            regard_data=regard.dict(),
            user_id=user_id
        )
        return regard_obj.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


from api.websocket import manager

@router.patch("/regards/{regard_id}", response_model=schemas.RegardResponse)
async def update_regard(
    regard_id: str,
    update: schemas.RegardUpdate,
    user_id: str = "system",
    db: Session = Depends(get_db)
):
    """Met à jour partiellement un regard."""
    updated = crud.update_regard(
        db=db,
        regard_id=regard_id,
        update_data=update.dict(exclude_unset=True),
        user_id=user_id
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Regard non trouvé")
        
    msg = f"Objet : Regard {updated.code or updated.id} modifié par {user_id} [{updated.longitude},{updated.latitude}]"
    await manager.broadcast(msg)
    
    return updated.to_dict()


@router.delete("/regards/{regard_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_regard(regard_id: int, user_id: str = "system", db: Session = Depends(get_db)):
    """Supprime un regard."""
    success = crud.delete_regard(db, regard_id, user_id=user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Regard non trouvé")
    return None


# ============================================================
# CANALISATIONS
# ============================================================

@router.get("/conduites", response_model=List[schemas.CanalisationResponse])
def list_conduites(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    cluster_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Liste des canalisations."""
    conduites = crud.get_canalisations(
        db=db,
        skip=skip,
        limit=limit,
        cluster_id=cluster_id
    )
    return conduites  # Retourne objets ORM directly, Pydantic gère via orm_mode


@router.get("/conduites/{conduite_id}", response_model=schemas.CanalisationResponse)
def get_conduite(conduite_id: int, db: Session = Depends(get_db)):
    """Détail d'une canalisation."""
    conduite = crud.get_canalisation(db, conduite_id)
    if not conduite:
        raise HTTPException(status_code=404, detail="Canalisation non trouvée")
    return conduite.to_dict()


@router.post("/conduites", response_model=schemas.CanalisationResponse, status_code=status.HTTP_201_CREATED)
def create_conduite(
    conduite: schemas.CanalisationCreate,
    user_id: str = "system",
    db: Session = Depends(get_db)
):
    """Crée une nouvelle canalisation."""
    try:
        conduite_obj = crud.create_canalisation(
            db=db,
            canalisation_data=conduite.dict(),
            user_id=user_id
        )
        return conduite_obj.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/conduites/{conduite_id}", response_model=schemas.CanalisationResponse)
async def update_conduite(
    conduite_id: str,
    update: schemas.CanalisationUpdate,
    user_id: str = "system",
    db: Session = Depends(get_db)
):
    """Met à jour une canalisation."""
    updated = crud.update_canalisation(
        db=db,
        canalisation_id=conduite_id,
        update_data=update.dict(exclude_unset=True),
        user_id=user_id
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Canalisation non trouvée")
        
    msg = f"Objet : Conduite {updated.fid or updated.id} modifiée par {user_id} [0.0,0.0]"
    await manager.broadcast(msg)
    
    return updated.to_dict()


@router.delete("/conduites/{conduite_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conduite(conduite_id: int, user_id: str = "system", db: Session = Depends(get_db)):
    """Supprime une canalisation."""
    success = crud.delete_canalisation(db, conduite_id, user_id=user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Canalisation non trouvée")
    return None


# ============================================================
# REJETS
# ============================================================

@router.get("/rejets", response_model=List[schemas.RejetResponse])
def list_rejets(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Liste des rejets (exutoires)."""
    from api.models import Rejet
    rejets = db.query(Rejet).offset(skip).limit(limit).all()
    return [r.to_dict() for r in rejets]


@router.post("/rejets", response_model=schemas.RejetResponse, status_code=status.HTTP_201_CREATED)
def create_rejet(
    rejet: schemas.RejetCreate,
    user_id: str = "system",
    db: Session = Depends(get_db)
):
    """Crée un nouveau rejet."""
    # TODO: implémenter si besoin
    raise HTTPException(status_code=501, detail="À implémenter")


# ============================================================
# GESTION DES PROJETS & CHARGEMENT DE RÉSEAUX (OPTION B)
# ============================================================

AVAILABLE_DATASETS = [
    {
        "id": "epa_example1",
        "title": "Drainage de Site",
        "short_name": "Drainage de Site",
        "category": "epa_certified",
        "badge": "EPA Certifié",
        "badge_color": "#10b981",
        "icon": "fa-tint",
        "icon_color": "#38bdf8",
        "description": "Modèle standard officiel US EPA 5.2. Drainage pluvial direct avec cotes de radier et écoulement gravitaire.",
        "nodes_count": 7,
        "pipes_count": 6,
        "gpkg_path": "data/benchmarks/epa_example1_drainage.gpkg",
        "is_official": True
    },
    {
        "id": "epa_example3",
        "title": "Réseau Unitaire & Déversoirs",
        "short_name": "Réseau Unitaire",
        "category": "epa_certified",
        "badge": "EPA Certifié",
        "badge_color": "#10b981",
        "icon": "fa-water",
        "icon_color": "#a855f7",
        "description": "Modèle de référence EPA pour l'analyse des surcharges, déversoirs d'orage (weir) et refoulements.",
        "nodes_count": 9,
        "pipes_count": 8,
        "gpkg_path": "data/benchmarks/epa_example3_combined.gpkg",
        "is_official": True
    },
    {
        "id": "epa_example4",
        "title": "Bassin de Rétention & Stockage",
        "short_name": "Bassin de Rétention",
        "category": "epa_certified",
        "badge": "EPA Certifié",
        "badge_color": "#10b981",
        "icon": "fa-database",
        "icon_color": "#f59e0b",
        "description": "Modèle officiel de stockage / rétention (Storage Unit) avec régulation de débit par orifice de vidange.",
        "nodes_count": 4,
        "pipes_count": 2,
        "gpkg_path": "data/benchmarks/epa_example4_storage.gpkg",
        "is_official": True
    },
    {
        "id": "epa_example5",
        "title": "Station de Pompage & Refoulement",
        "short_name": "Station de Pompage",
        "category": "epa_certified",
        "badge": "EPA Certifié",
        "badge_color": "#10b981",
        "icon": "fa-bolt",
        "icon_color": "#ef4444",
        "description": "Station de relevage équipée de pompes avec courbe caractéristique et conduite de refoulement sous pression.",
        "nodes_count": 4,
        "pipes_count": 2,
        "gpkg_path": "data/benchmarks/epa_example5_pumping.gpkg",
        "is_official": True
    },
    {
        "id": "epa_example6",
        "title": "Techniques Alternatives LID",
        "short_name": "Techniques LID",
        "category": "epa_certified",
        "badge": "EPA Certifié",
        "badge_color": "#10b981",
        "icon": "fa-leaf",
        "icon_color": "#22c55e",
        "description": "Infrastructures vertes et noues végétalisées (Low Impact Development) pour la temporisation des crues à la source.",
        "nodes_count": 14,
        "pipes_count": 13,
        "gpkg_path": "data/benchmarks/epa_example6_lid.gpkg",
        "is_official": True
    },
    {
        "id": "demo_temoin",
        "title": "Quartier Témoin (Démo Pratique)",
        "short_name": "Quartier Témoin",
        "category": "demo",
        "badge": "Échantillon Démo",
        "badge_color": "#0284c7",
        "icon": "fa-city",
        "icon_color": "#38bdf8",
        "description": "Quartier urbain de 59 regards et 58 canalisations. Découpage hydrologique en sous-bassins Voronoï.",
        "nodes_count": 59,
        "pipes_count": 58,
        "gpkg_path": "data/demo_reseau.gpkg",
        "is_official": False
    },
    {
        "id": "ville_complete",
        "title": "Réseau Réel Ville (Master Métropole)",
        "short_name": "Métropole Chlef",
        "category": "master",
        "badge": "Réseau Réel Complet",
        "badge_color": "#8b5cf6",
        "icon": "fa-sitemap",
        "icon_color": "#8b5cf6",
        "description": "Patrimoine réel complet de la métropole (+11 000 canalisations et regards, STEP, stations de pompage).",
        "nodes_count": 11000,
        "pipes_count": 11000,
        "gpkg_path": r"D:\IA Water Data Analysis\Assainissement\Assainissement_Ville.gpkg",
        "is_official": False
    }
]


@router.get("/datasets")
def list_available_datasets(
    response: Response,
    tenant_ctx: Optional[TenantContext] = Depends(get_tenant_context_optional),
    db: Session = Depends(get_db)
):
    """Retourne la liste des jeux de données et modèles de référence disponibles ainsi que le projet en cours."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    active_project = None
    try:
        org_id = tenant_ctx.org_id if tenant_ctx else None
        if not org_id:
            default_org = db.query(Organization).first()
            org_id = default_org.id if default_org else "org_default"

        proj = db.query(Project).filter(Project.org_id == org_id, Project.is_archived.is_(False)).first()
        if not proj:
            proj = db.query(Project).filter(Project.is_archived.is_(False)).first()

        from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet
        chemin_eff = resoudre_gpkg_effectif_pour_projet(db, proj)
        if chemin_eff is not None:
            active_project = {
                "id": proj.id,
                "name": proj.name or "Projet Réseau Actif",
                "pipes_count": proj.pipes_count or 0,
                "nodes_count": proj.nodes_count or 0,
                "gpkg_path": str(chemin_eff)
            }
    except Exception as e:
        print(f"[datasets] Erreur extraction projet actif: {e}", flush=True)

    return {"status": "ok", "datasets": AVAILABLE_DATASETS, "active_project": active_project}


@router.post("/load-dataset/{dataset_id}")
def load_benchmark_dataset(
    dataset_id: str,
    tenant_ctx: Optional[TenantContext] = Depends(get_tenant_context_optional),
    db: Session = Depends(get_db)
):
    """Charge l'un des jeux de données officiels EPA ou de démonstration."""
    ds = next((d for d in AVAILABLE_DATASETS if d["id"] == dataset_id), None)
    if not ds:
        raise HTTPException(status_code=404, detail="Jeu de données introuvable.")

    target_path = Path(ds["gpkg_path"])
    if not target_path.exists():
        raise HTTPException(status_code=500, detail=f"Fichier réseau introuvable : {ds['gpkg_path']}")

    if ds["id"] == "ville_complete" and not (tenant_ctx and tenant_ctx.user and tenant_ctx.user.is_superadmin):
        raise HTTPException(status_code=403, detail="Seul un SuperAdmin peut charger le réseau réel complet de la ville.")

    org_id = tenant_ctx.org_id if tenant_ctx else None
    if not org_id:
        default_org = db.query(Organization).first()
        org_id = default_org.id if default_org else "org_default"

    project = db.query(Project).filter(
        Project.org_id == org_id,
        Project.is_archived.is_(False)
    ).first()

    if not project:
        project = Project(
            org_id=org_id,
            name=ds["title"],
            description=ds["description"],
        )
        db.add(project)
        db.flush()

    project.name = ds["title"]
    project.source_gpkg_key = str(target_path)
    _enregistrer_version_gpkg(db, project, target_path, filename_original=target_path.name)
    project.nodes_count = ds["nodes_count"]
    project.pipes_count = ds["pipes_count"]
    db.commit()

    # Effacer immédiatement les résultats de simulation du précédent modèle
    try:
        from api.routes.simulations import reinitialiser_derniere_simulation
        reinitialiser_derniere_simulation()
    except Exception:
        pass
    try:
        from api.routes.qualite import reinitialiser_cache_qualite
        reinitialiser_cache_qualite()
    except Exception:
        pass
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

    return {
        "status": "ok",
        "message": f"Jeu de données '{ds['title']}' chargé avec succès.",
        "project": {
            "id": project.id,
            "name": project.name,
            "badge": ds["badge"],
            "nodes_count": project.nodes_count,
            "pipes_count": project.pipes_count
        }
    }


@router.post("/load-demo")
def load_demo_network(
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Charge le réseau d'exemple Démo (échantillon isolé et sécurisé) pour le projet actif."""
    demo_path = Path("data/demo_reseau.gpkg")
    if not demo_path.exists():
        raise HTTPException(status_code=500, detail="Fichier démo introuvable sur le serveur.")

    project = db.query(Project).filter(
        Project.org_id == tenant_ctx.org_id,
        Project.is_archived.is_(False)
    ).first()

    if not project:
        project = Project(
            org_id=tenant_ctx.org_id,
            name="Projet Démo — Quartier Témoin",
            description="Échantillon de démonstration préconfiguré.",
        )
        db.add(project)
        db.flush()

    project.name = "Projet Démo — Quartier Témoin"
    project.source_gpkg_key = str(demo_path)
    _enregistrer_version_gpkg(db, project, demo_path, filename_original=demo_path.name)
    project.nodes_count = 59
    project.pipes_count = 58
    project.outfalls_count = 1
    db.commit()

    try:
        from api.routes.simulations import reinitialiser_derniere_simulation
        reinitialiser_derniere_simulation()
    except Exception:
        pass
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

    return {
        "status": "ok",
        "message": "Réseau d'exemple Démo chargé avec succès.",
        "project": {
            "id": project.id,
            "name": project.name,
            "nodes_count": project.nodes_count,
            "pipes_count": project.pipes_count,
        }
    }


@router.post("/load-master")
def load_master_network(
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Charge le réseau complet réel (Réservé au SuperAdmin / Direction de projet)."""
    user = tenant_ctx.user
    if not user or not user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès restreint. Seul le SuperAdmin peut charger le réseau réel complet de la ville."
        )

    master_path = Path(r"D:\IA Water Data Analysis\Assainissement\Assainissement_Ville.gpkg")
    if not master_path.exists():
        raise HTTPException(status_code=500, detail="Fichier maître introuvable sur le serveur.")

    project = db.query(Project).filter(
        Project.org_id == tenant_ctx.org_id,
        Project.is_archived.is_(False)
    ).first()

    if not project:
        project = Project(
            org_id=tenant_ctx.org_id,
            name="Réseau Ville (Projet Réel)",
            description="Réseau complet d'assainissement.",
        )
        db.add(project)
        db.flush()

    project.name = "Réseau Ville (Projet Réel)"
    project.source_gpkg_key = str(master_path)
    _enregistrer_version_gpkg(db, project, master_path, filename_original=master_path.name)
    project.nodes_count = 11000
    project.pipes_count = 11000
    db.commit()

    try:
        from api.routes.simulations import reinitialiser_derniere_simulation
        reinitialiser_derniere_simulation()
    except Exception:
        pass
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

    return {
        "status": "ok",
        "message": "Réseau réel complet de la ville chargé pour votre session administrateur.",
        "project": {
            "id": project.id,
            "name": project.name,
        }
    }


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
        from api.routes.simulations import reinitialiser_derniere_simulation
        reinitialiser_derniere_simulation()
    except Exception:
        pass
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
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Téléverse un fichier GeoPackage (.gpkg) ou EPA SWMM (.inp) pour le projet actif."""
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
    if fname_lower.endswith(".inp"):
        # Conversion transparente du fichier EPA SWMM .inp vers GeoPackage (.gpkg)
        from src.domain.inp_parser import convertir_inp_vers_gpkg
        gpkg_target_path = raw_target_path.with_suffix(".gpkg")
        try:
            conv_summary = convertir_inp_vers_gpkg(raw_target_path, gpkg_target_path)
            target_path = gpkg_target_path
        except Exception as e_conv:
            logger.exception("Échec de la conversion du fichier .inp : %s", e_conv)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Erreur lors de l'analyse du fichier SWMM .inp : {str(e_conv)}"
            )
    else:
        target_path = raw_target_path

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
    _enregistrer_version_gpkg(
        db, project, target_path,
        filename_original=file.filename,
        created_by_id=getattr(tenant_ctx.user, "id", None) if tenant_ctx else None,
        strict=True,
    )
    db.commit()

    try:
        from api.routes.simulations import reinitialiser_derniere_simulation
        reinitialiser_derniere_simulation()
    except Exception:
        pass
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
        "project": {
            "id": project.id,
            "name": project.name,
        }
    }


# ============================================================
# HYDROLOGIE & SOUS-BASSINS (SWMM SUBCATCHMENTS)
# ============================================================

@router.get("/subcatchments")
def get_network_subcatchments(
    tenant_ctx: Optional[TenantContext] = Depends(get_tenant_context_optional),
    db: Session = Depends(get_db)
):
    """
    Génère et retourne les sous-bassins versants élémentaires (Subcatchments)
    au format GeoJSON pour le réseau actif du projet.
    """
    import json
    from src.domain.hydrologie import GenerateurHydrologie
    import geopandas as gpd

    gpkg_path = None
    if tenant_ctx and tenant_ctx.org_id:
        from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet
        project = db.query(Project).filter(
            Project.org_id == tenant_ctx.org_id,
            Project.is_archived.is_(False)
        ).first()
        gpkg_path = resoudre_gpkg_effectif_pour_projet(db, project)
        if gpkg_path is None:
            return {
                "type": "FeatureCollection",
                "features": [],
                "total_area_ha": 0.0,
                "subcatchments_count": 0,
                "message": "Aucun réseau chargé pour ce projet."
            }
    else:
        cand = Path("data/demo_reseau.gpkg")
        if cand.exists():
            gpkg_path = cand

    if gpkg_path is None or not gpkg_path.exists():
        return {
            "type": "FeatureCollection",
            "features": [],
            "total_area_ha": 0.0,
            "subcatchments_count": 0,
            "message": "Aucun fichier GeoPackage disponible."
        }

    # Vérification cache rapide sur disque
    cache_sub_path = gpkg_path.with_suffix(".subcatchments_cache.json")
    if cache_sub_path.exists():
        try:
            if cache_sub_path.stat().st_mtime >= gpkg_path.stat().st_mtime:
                with open(cache_sub_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"[subcatchments] Erreur lecture cache: {e}", flush=True)

    try:
        layers = gpd.list_layers(str(gpkg_path))['name'].tolist()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lecture couches GPKG: {e}")

    # Si la couche sous_bassins_voronoi existe déjà dans le GPKG, l'utiliser directement
    if "sous_bassins_voronoi" in layers:
        try:
            subcatchments = gpd.read_file(str(gpkg_path), layer="sous_bassins_voronoi")
            sub_wgs84 = subcatchments.to_crs("EPSG:4326") if subcatchments.crs != "EPSG:4326" else subcatchments
            geojson = json.loads(sub_wgs84.to_json(na="drop"))
            total_area_ha = round(float(subcatchments['area_ha'].sum()), 4) if 'area_ha' in subcatchments else 0.0
            res = {
                **geojson,
                "total_area_ha": total_area_ha,
                "subcatchments_count": len(subcatchments)
            }
            with open(cache_sub_path, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False)
            return res
        except Exception as e:
            print(f"[subcatchments] Erreur lecture couche sous_bassins_voronoi: {e}", flush=True)

    regard_layer = next((l for l in layers if 'regard' in l.lower()), None)
    pipe_layer = next((l for l in layers if any(k in l.lower() for k in ['canalisat', 'conduit', 'pipe', 'troncon']) and 'désaffect' not in l.lower() and 'desaffect' not in l.lower()), None)

    if not regard_layer:
        return {
            "type": "FeatureCollection",
            "features": [],
            "total_area_ha": 0.0,
            "subcatchments_count": 0
        }

    regards_gdf = gpd.read_file(str(gpkg_path), layer=regard_layer)
    canalisations_gdf = gpd.read_file(str(gpkg_path), layer=pipe_layer) if pipe_layer else gpd.GeoDataFrame()

    gh = GenerateurHydrologie()
    subcatchments = gh.generer_sous_bassins(regards_gdf, canalisations_gdf)

    if subcatchments.empty:
        return {
            "type": "FeatureCollection",
            "features": [],
            "total_area_ha": 0.0,
            "subcatchments_count": 0
        }

    sub_wgs84 = subcatchments.to_crs("EPSG:4326") if subcatchments.crs != "EPSG:4326" else subcatchments
    geojson = json.loads(sub_wgs84.to_json(na="drop"))
    total_area_ha = round(float(subcatchments['area_ha'].sum()), 4)

    return {
        **geojson,
        "total_area_ha": total_area_ha,
        "subcatchments_count": len(subcatchments)
    }


@router.get("/orphelins/geojson")
def get_network_orphelins_geojson(
    tenant_ctx: Optional[TenantContext] = Depends(get_tenant_context_optional),
    db: Session = Depends(get_db)
):
    """
    Retourne la liste des éléments orphelins (regards déconnectés du réseau amont-aval)
    au format GeoJSON pour audit et correction.
    """
    import json
    import geopandas as gpd

    gpkg_path = None
    if tenant_ctx and tenant_ctx.org_id:
        from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet
        project = db.query(Project).filter(
            Project.org_id == tenant_ctx.org_id,
            Project.is_archived.is_(False)
        ).first()
        gpkg_path = resoudre_gpkg_effectif_pour_projet(db, project)

    if not gpkg_path or not gpkg_path.exists():
        cand = Path("uploads/a66e32ad-f32b-4529-acc3-7a6026eb5a8a/network_Assainissement_Ville.gpkg")
        if cand.exists():
            gpkg_path = cand

    if not gpkg_path or not gpkg_path.exists():
        raise HTTPException(status_code=404, detail="Aucun projet actif trouvé")

    # 1. Vérifier si elements_orphelins.geojson existe
    orph_json_p = gpkg_path.parent / "elements_orphelins.geojson"
    if orph_json_p.exists():
        with open(orph_json_p, "r", encoding="utf-8") as f:
            return json.load(f)

    # 2. Sinon lire depuis la couche GPKG elements_orphelins_regards
    try:
        layers = gpd.list_layers(str(gpkg_path))['name'].tolist()
        if "elements_orphelins_regards" in layers:
            gdf = gpd.read_file(str(gpkg_path), layer="elements_orphelins_regards")
            gdf_wgs84 = gdf.to_crs("EPSG:4326") if gdf.crs != "EPSG:4326" else gdf
            return json.loads(gdf_wgs84.to_json(na="drop"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lecture orphelins: {e}")

    return {"type": "FeatureCollection", "features": [], "message": "Aucun orphelin trouvé"}


@router.get("/export/inp")
def export_network_inp(
    tenant_ctx: Optional[TenantContext] = Depends(get_tenant_context_optional),
    db: Session = Depends(get_db)
):
    """Exporte l'intégralité du réseau actif au format standard EPA SWMM 5.2 (.inp) avec le nom du réseau."""
    from fastapi.responses import PlainTextResponse
    import re
    import unicodedata
    from src.domain.moteur_swmm import MoteurSWMM

    gpkg_path = None
    project_name = None
    from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet
    if tenant_ctx and tenant_ctx.org_id:
        project = db.query(Project).filter(
            Project.org_id == tenant_ctx.org_id,
            Project.is_archived.is_(False)
        ).first()
        if project:
            project_name = project.name
            gpkg_path = resoudre_gpkg_effectif_pour_projet(db, project)

    if not gpkg_path or not gpkg_path.exists():
        project = db.query(Project).filter(Project.is_archived.is_(False)).first()
        if project:
            if not project_name:
                project_name = project.name
            gpkg_path = resoudre_gpkg_effectif_pour_projet(db, project)

    if not gpkg_path or not gpkg_path.exists():
        cand = Path("data/demo_reseau.gpkg")
        if cand.exists():
            gpkg_path = cand
            project_name = "demo_reseau"

    if not gpkg_path or not gpkg_path.exists():
        raise HTTPException(status_code=404, detail="Aucun réseau hydraulique actif trouvé pour l'export.")

    # 1. Si le fichier .inp original existe à côté du GPKG, le renvoyer directement (100% fidèle et instantané)
    original_inp = gpkg_path.with_suffix(".inp")
    if original_inp.exists():
        with open(original_inp, "r", encoding="utf-8", errors="ignore") as f:
            inp_content = f.read()
    else:
        # 3D.2 — plus de lecture de _DERNIERE_SIMULATION (état global non
        # cloisonné) : le modèle est assemblé depuis le GPKG du projet.
        moteur = MoteurSWMM()
        inp_content, _ = moteur.assembler_modele_inp(
            gpkg_path=gpkg_path,
            cluster_id=None,
            pente_moyenne_pct=1.0
        )
        try:
            with open(original_inp, "w", encoding="utf-8") as f:
                f.write(inp_content)
        except Exception:
            pass

    nom_reseau = project_name or gpkg_path.stem
    r = re.sub(r'\.(gpkg|inp)$', '', str(nom_reseau).strip(), flags=re.I)
    sans_accent = unicodedata.normalize('NFKD', r).encode('ASCII', 'ignore').decode('utf-8')
    clean = re.sub(r'[^\w\-_.]+', '_', sans_accent)
    clean = re.sub(r'_+', '_', clean).strip('_') or "reseau_swmm"
    filename = f"{clean}.inp"

    return PlainTextResponse(
        inp_content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

