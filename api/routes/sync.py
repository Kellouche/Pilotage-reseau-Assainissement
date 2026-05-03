"""
Routes de synchronisation bidirectionnelle.
Delta sync, poussée de modifications, versioning.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta

from api.database import get_db
from api import schemas, crud

router = APIRouter(prefix="/sync", tags=["Synchronisation"])


# ============================================================
# DELTA DOWNLOAD (client → server: "what changed since T?")
# ============================================================

@router.get("/delta", response_model=schemas.DeltaResponse)
def get_delta(
    since_version: int = Query(..., ge=0, description="Version client actuelle"),
    tables: str = Query("regards,conduites,rejets", description="Tables à synchroniser"),
    db: Session = Depends(get_db)
):
    """
    Retourne les modifications depuis la version spécifiée.
    Pour synchronisation descendante (server → client).
    """
    table_list = [t.strip() for t in tables.split(",")]
    all_changes = []
    max_new_version = since_version

    for table in table_list:
        # Récupérer changements depuis version+1
        changes = crud.get_changes_since(db, table, since_version + 1)
        for change in changes:
            # Convertir en DeltaChange
            all_changes.append({
                "type": "update",  # pour POC, on ne gère que updates créés via API
                "layer": table,
                "feature_id": str(change.get("id") or change.get("fid")),
                "changes": change
            })

        # Version max de cette table
        table_max_version = crud.get_max_version(db, table)
        if table_max_version > max_new_version:
            max_new_version = table_max_version

    return {
        "version": max_new_version,
        "timestamp": datetime.utcnow(),
        "changes": all_changes,
        "deleted_ids": []  # TODO: gérer suppressions
    }


# ============================================================
# DELTA UPLOAD (client → server: "here are my changes")
# ============================================================

@router.post("/push", response_model=schemas.SyncAck)
def push_changes(
    push: schemas.SyncPush,
    user_id: str = "device",
    db: Session = Depends(get_db)
):
    """
    Reçoit des modifications depuis un client mobile.
    Applique les changements avec résolution de conflits simple.
    """
    accepted = 0
    rejected = 0
    conflicts = []

    for change in push.changes:
        try:
            layer = change.layer
            feature_id = change.feature_id
            changes = change.changes
            op_type = change.type

            if op_type == "delete":
                # TODO: gestion suppressions
                rejected += 1
                continue

            if layer == "regards":
                # Rechercher par code ou id
                if "id" in changes:
                    regard = crud.get_regard(db, int(changes["id"]))
                else:
                    regard = crud.get_regard_by_code(db, changes["code"])

                if regard:
                    # Update
                    updated = crud.update_regard(
                        db=db,
                        regard_id=regard.id,
                        update_data=changes,
                        user_id=user_id
                    )
                    accepted += 1
                else:
                    # Create
                    crud.create_regard(db, changes, user_id=user_id)
                    accepted += 1

            elif layer == "conduites":
                if "id" in changes:
                    canalisation = crud.get_canalisation(db, int(changes["id"]))
                else:
                    canalisation = crud.get_canalisation_by_fid(db, changes["fid"])

                if canalisation:
                    updated = crud.update_canalisation(
                        db=db,
                        canalisation_id=canalisation.id,
                        update_data=changes,
                        user_id=user_id
                    )
                    accepted += 1
                else:
                    crud.create_canalisation(db, changes, user_id=user_id)
                    accepted += 1

            else:
                rejected += 1

        except ValueError as ve:
            # Conflit ou erreur validation
            conflicts.append({
                "layer": change.layer,
                "feature_id": change.feature_id,
                "error": str(ve)
            })
            rejected += 1
        except Exception as e:
            rejected += 1

    # Nouvelle version globale
    new_version = crud.get_max_version(db, "regards")
    new_version = max(new_version, crud.get_max_version(db, "conduites"))

    return {
        "accepted": accepted,
        "rejected": rejected,
        "new_version": new_version,
        "conflicts": conflicts if conflicts else None
    }


# ============================================================
# SESSION SYNC (pour mobile : enregistrer dernier sync)
# ============================================================

@router.post("/session")
def register_sync_session(
    device_id: str,
    db: Session = Depends(get_db)
):
    """Enregistre/renvoie la session de synchronisation d'un appareil."""
    from api.models import AuditLog

    # Pour POC : on retourne simplement un ack
    # En prod : stocker device_id + last_sync dans table devices
    return {
        "device_id": device_id,
        "registered": True,
        "message": "Session enregistrée"
    }
