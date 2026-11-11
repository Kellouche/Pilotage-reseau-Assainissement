"""cluster_bassin_ref_stable

Étape 3A — référence métier stable des bassins versants.
Ajoute Cluster.bassin_ref (ex. "exutoire:<node_id>") et l'index unique
(network_id, bassin_ref). Additive et réversible.

Revision ID: a1b2c3d4e5f6
Revises: 00258421cdaf
Create Date: 2026-11-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '00258421cdaf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('clusters', sa.Column('bassin_ref', sa.String(length=120), nullable=True))
    op.create_index(
        'uq_cluster_network_bassin_ref',
        'clusters',
        ['network_id', 'bassin_ref'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('uq_cluster_network_bassin_ref', table_name='clusters')
    op.drop_column('clusters', 'bassin_ref')
