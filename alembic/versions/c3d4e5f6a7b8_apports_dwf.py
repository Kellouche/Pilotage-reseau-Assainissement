"""apports_dwf_temps_sec

LOT P1.2 — Apports de temps sec (DWF) par projet.
- Table apports_dwf : org_id/project_id cloisonnés, node_id canonique
  (_clean_node_id du GPKG versionné), nature, mode de détermination
  (debit direct m³/s | EH × débit spécifique), profil temporel prédéfini,
  actif, source, observations.
Additive : aucune table ni donnée existante n'est modifiée.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'apports_dwf',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('org_id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('node_id', sa.String(length=100), nullable=False),
        sa.Column('nature', sa.String(length=30), nullable=False),
        sa.Column('mode_determination', sa.String(length=10), nullable=False),
        sa.Column('debit_moyen_m3s', sa.Float(), nullable=False),
        sa.Column('eh', sa.Float(), nullable=True),
        sa.Column('debit_specifique_l_hab_j', sa.Float(), nullable=True),
        sa.Column('profile_key', sa.String(length=50), nullable=False),
        sa.Column('actif', sa.Boolean(), nullable=False),
        sa.Column('source', sa.String(length=255), nullable=True),
        sa.Column('observations', sa.Text(), nullable=True),
        sa.Column('created_by_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_apports_dwf_org_id', 'apports_dwf', ['org_id'])
    op.create_index('ix_apports_dwf_project_id', 'apports_dwf', ['project_id'])
    op.create_index('ix_apports_dwf_node_id', 'apports_dwf', ['node_id'])
    op.create_index('ix_apports_dwf_org_project', 'apports_dwf', ['org_id', 'project_id'])
    op.create_index('ix_apports_dwf_project_node', 'apports_dwf', ['project_id', 'node_id'])


def downgrade() -> None:
    op.drop_index('ix_apports_dwf_project_node', table_name='apports_dwf')
    op.drop_index('ix_apports_dwf_org_project', table_name='apports_dwf')
    op.drop_index('ix_apports_dwf_node_id', table_name='apports_dwf')
    op.drop_index('ix_apports_dwf_project_id', table_name='apports_dwf')
    op.drop_index('ix_apports_dwf_org_id', table_name='apports_dwf')
    op.drop_table('apports_dwf')
