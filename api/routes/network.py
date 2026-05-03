"""
Routes pour la gestion du réseau (regards, canalisations, rejets).
Endpoints CRUD complets avec validation Pydantic.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from api.database import get_db
from api import schemas, crud

router = APIRouter(prefix="/network", tags=["Réseau"])


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


@router.patch("/regards/{regard_id}", response_model=schemas.RegardResponse)
def update_regard(
    regard_id: int,
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
def update_conduite(
    conduite_id: int,
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
