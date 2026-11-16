# -*- coding: utf-8 -*-
"""project_aux_layers

Couches SIG « satellite » par projet (SHP.md) — altimétrie, BV officiels,
métrologie… INDÉPENDANCE TOTALE : aucune écriture dans le GPKG projet ni
dans les tables réseau, aucune lecture par le pipeline SWMM/.inp.

Idempotent : init_db() applique create_all avant qu'alembic ne rattrape —
on vérifie l'existence de la table pour éviter un « already exists ».

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-11-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_existe(nom: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(nom)


def upgrade() -> None:
    if _table_existe("project_aux_layers"):
        return
    op.create_table(
        'project_aux_layers',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('type', sa.String(40), nullable=False),
        sa.Column('nom', sa.String(255), nullable=False),
        sa.Column('fichier_source', sa.String(255), nullable=True),
        sa.Column('storage_key', sa.String(512), nullable=False),
        sa.Column('crs_source', sa.String(50), nullable=True),
        sa.Column('geom_type', sa.String(50), nullable=True),
        sa.Column('emprise', sa.JSON(), nullable=True),
        sa.Column('nb_features', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('attributs', sa.JSON(), nullable=True),
        sa.Column('colonne_z', sa.String(100), nullable=True),
        sa.Column('statut', sa.String(30), nullable=False, server_default='ok'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_project_aux_layers_org_id', 'project_aux_layers', ['org_id'])
    op.create_index('ix_project_aux_layers_project_id', 'project_aux_layers', ['project_id'])
    op.create_index('ix_aux_layers_org_proj', 'project_aux_layers', ['org_id', 'project_id'])


def downgrade() -> None:
    if not _table_existe("project_aux_layers"):
        return
    op.drop_index('ix_aux_layers_org_proj', table_name='project_aux_layers')
    op.drop_index('ix_project_aux_layers_project_id', table_name='project_aux_layers')
    op.drop_index('ix_project_aux_layers_org_id', table_name='project_aux_layers')
    op.drop_table('project_aux_layers')
