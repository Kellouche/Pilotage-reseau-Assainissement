# -*- coding: utf-8 -*-
"""apports_dwf_history

LOT P6.1 — Historique métier des apports DWF (apports_dwf_history).
Table d'audit immuable (append-only) pour la traçabilité des mutations
(création, mise à jour, changement de nœud, réconciliation, activation,
désactivation, suppression, exclusion de simulation) des apports DWF.
Protection anti-cascade : ondelete='RESTRICT' sur org_id et project_id.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-11-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'apports_dwf_history',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('org_id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('apport_id', sa.String(length=36), nullable=False),
        sa.Column('action', sa.String(length=30), nullable=False),
        sa.Column('changed_fields', sa.JSON(), nullable=True),
        sa.Column('previous_state', sa.JSON(), nullable=True),
        sa.Column('new_state', sa.JSON(), nullable=True),
        sa.Column('changed_by_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['changed_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_apports_dwf_history_org_id', 'apports_dwf_history', ['org_id'])
    op.create_index('ix_apports_dwf_history_project_id', 'apports_dwf_history', ['project_id'])
    op.create_index('ix_apports_dwf_history_apport_id', 'apports_dwf_history', ['apport_id'])
    op.create_index('ix_apports_dwf_history_created_at', 'apports_dwf_history', ['created_at'])
    op.create_index('ix_apports_dwf_hist_org_proj', 'apports_dwf_history', ['org_id', 'project_id'])
    op.create_index('ix_apports_dwf_hist_apport_created', 'apports_dwf_history', ['apport_id', 'created_at'])
    op.create_index('ix_apports_dwf_hist_org_created', 'apports_dwf_history', ['org_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_apports_dwf_hist_org_created', table_name='apports_dwf_history')
    op.drop_index('ix_apports_dwf_hist_apport_created', table_name='apports_dwf_history')
    op.drop_index('ix_apports_dwf_hist_org_proj', table_name='apports_dwf_history')
    op.drop_index('ix_apports_dwf_history_created_at', table_name='apports_dwf_history')
    op.drop_index('ix_apports_dwf_history_apport_id', table_name='apports_dwf_history')
    op.drop_index('ix_apports_dwf_history_project_id', table_name='apports_dwf_history')
    op.drop_index('ix_apports_dwf_history_org_id', table_name='apports_dwf_history')
    op.drop_table('apports_dwf_history')
