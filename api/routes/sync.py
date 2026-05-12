"""
Routes de synchronisation bidirectionnelle.
Delta sync, poussée de modifications, versioning.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import json

from api.database import get_db
from api import schemas, crud
from api.websocket import manager

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
    background_tasks: BackgroundTasks,
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
                # Utiliser feature_id comme ID du regard
                regard = crud.get_regard(db, int(change.feature_id))

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

    print(f"Push completed: accepted={accepted}, rejected={rejected}")

    # Notifier les clients WebSocket des modifications
    if accepted > 0:
        from datetime import datetime

        # Créer un message détaillé pour chaque modification acceptée
        messages = []
        change_index = 0

        for change in push.changes:
            if change_index >= accepted:
                break

            layer = change.layer
            feature_id = change.feature_id

            if layer == "regards":
                try:
                    regard = crud.get_regard(db, int(feature_id))
                    if regard:
                        # Format: Objet : Regard [CODE] [X,Y] -- DateTime
                        coord_x = regard.longitude if regard.longitude is not None else 0.0
                        coord_y = regard.latitude if regard.latitude is not None else 0.0
                        code = regard.code if regard.code else f'ID:{regard.id}'
                        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

                        message = f"Objet : Regard {code} [{coord_x:.6f},{coord_y:.6f}] -- {timestamp}"
                        messages.append(message)
                except Exception as e:
                    print(f"Erreur récupération regard {feature_id}: {e}")

            elif layer == "conduites":
                try:
                    if "id" in change.changes:
                        conduite = crud.get_canalisation(db, int(change.changes["id"]))
                    else:
                        conduite = crud.get_canalisation_by_fid(db, change.changes.get("fid"))

                    if conduite:
                        # Format avec coordonnées comme pour les regards
                        from sqlalchemy import func
                        centroid = db.session.query(func.ST_Centroid(conduite.geom)).scalar()
                        coord_x = centroid.x if centroid else 0.0
                        coord_y = centroid.y if centroid else 0.0
                        fid = conduite.fid if conduite.fid else f'ID:{conduite.id}'
                        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                        message = f"Objet : Conduite {fid} [{coord_x:.6f},{coord_y:.6f}] -- {timestamp}"
                        messages.append(message)
                except Exception as e:
                    print(f"Erreur récupération conduite {feature_id}: {e}")

            change_index += 1

        # Calculer le nombre total de modifications
    total_modified = len(push.changes)

    # Diffuser le résumé d'abord
    summary_message = f"Modifications synchronisées: {accepted} acceptées"
    if total_modified > 1:
        summary_message += f" ({total_modified} points modifiés)"
    print(f"Sending broadcast: {summary_message}")
    background_tasks.add_task(manager.broadcast, summary_message)

    # Puis diffuser chaque message détaillé
    for message in messages:
        print(f"Sending broadcast: {message}")
        background_tasks.add_task(manager.broadcast, message)

        # Message de synthèse
        summary_message = f"Modifications synchronisées: {accepted} acceptées"
        print(f"Sending broadcast: {summary_message}")
        background_tasks.add_task(manager.broadcast, summary_message)

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
