# -*- coding: utf-8 -*-
"""qualite_anomalie_statuts

Cycle de vie des anomalies Contrôle Qualité (spec V2.1 §5) :
une ligne par anomalie, clé stable SHA-1(type | objet | gpkg_version_id),
statuts a_traiter / revu / corrige. Isolation stricte org/project.

Idempotent : create_all() de init_db() crée déjà la table sur les bases
de test — on vérifie l'existence avant de créer.

Revision ID: a2b3c4d5e6f7
Revises: b9c0d1e2f3a4
Create Date: 2026-11-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = 'b9c0d1e2f3a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_existe(nom: str) -> bool:
    bind = op.get_bind()
    return nom in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    if _table_existe("qualite_anomalie_statuts"):
        return
    op.create_table(
        'qualite_anomalie_statuts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('gpkg_version_id', sa.String(36), nullable=True),
        sa.Column('cle_anomalie', sa.String(40), nullable=False),
        sa.Column('type_anomalie', sa.String(60), nullable=False),
        sa.Column('id_conduite', sa.String(60), nullable=True),
        sa.Column('statut', sa.String(20), nullable=False, server_default='a_traiter'),
        sa.Column('commentaire', sa.Text(), nullable=True),
        sa.Column('updated_by_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('project_id', 'cle_anomalie', name='uq_qualite_statut_cle'),
    )
    op.create_index('ix_qualite_statuts_org', 'qualite_anomalie_statuts', ['org_id'])
    op.create_index('ix_qualite_statuts_project', 'qualite_anomalie_statuts', ['project_id'])
    op.create_index('ix_qualite_statuts_proj_type', 'qualite_anomalie_statuts', ['project_id', 'type_anomalie'])


def downgrade() -> None:
    if _table_existe("qualite_anomalie_statuts"):
        op.drop_table('qualite_anomalie_statuts')
