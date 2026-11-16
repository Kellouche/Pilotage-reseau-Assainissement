# -*- coding: utf-8 -*-
"""project_garde_fou_config

Paramétrage du garde-fou hydraulicien par projet (seuils d'acceptation,
preset, profil réseau). Nullable : absence = seuils par défaut.

Idempotent : init_db() applique déjà une migration douce (create_all +
ALTER TABLE) avant qu'alembic ne rattrape — on vérifie l'existence de la
colonne pour éviter un « duplicate column » sur les bases pré-migrées.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-11-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _colonne_existe(nom: str) -> bool:
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns("projects")]
    return nom in cols


def upgrade() -> None:
    if not _colonne_existe("garde_fou_config"):
        op.add_column('projects', sa.Column('garde_fou_config', sa.JSON(), nullable=True))


def downgrade() -> None:
    if _colonne_existe("garde_fou_config"):
        op.drop_column('projects', 'garde_fou_config')
