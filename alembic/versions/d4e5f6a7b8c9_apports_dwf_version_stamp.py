# -*- coding: utf-8 -*-
"""
LOT P1.4 — Estampillage GPKG des apports DWF.

Ajoute gpkg_version_id (FK gpkg_versions, SET NULL) et gpkg_sha256
(NULL) à apports_dwf : version exacte du réseau contre laquelle le
nœud a été validé. Les apports existants restent NULL = non réconciliés
(rejetés à la simulation jusqu'à revalidation explicite).
"""
from alembic import op
import sqlalchemy as sa


revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("apports_dwf",
                  sa.Column("gpkg_version_id", sa.String(length=36), nullable=True))
    op.add_column("apports_dwf",
                  sa.Column("gpkg_sha256", sa.String(length=64), nullable=True))
    # SQLite : ALTER de contrainte non supporté → pas de FK ajoutée ici
    # (garantie tenant/projet applicative ; l'ORM porte la FK pour les
    # nouvelles bases). Index simple compatible.
    op.create_index("ix_apports_dwf_gpkg_version", "apports_dwf", ["gpkg_version_id"])


def downgrade() -> None:
    op.drop_index("ix_apports_dwf_gpkg_version", table_name="apports_dwf")
    op.drop_column("apports_dwf", "gpkg_sha256")
    op.drop_column("apports_dwf", "gpkg_version_id")
