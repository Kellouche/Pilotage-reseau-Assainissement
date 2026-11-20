# -*- coding: utf-8 -*-
"""
LOT A1-DWF — Clé métier unique code_apport sur apports_dwf.

Ajoute code_apport (VARCHAR(50), nullable=True, index=True) avec contrainte
d'unicité intra-projet uq_apports_dwf_project_code sur (project_id, code_apport).
"""
from alembic import op
import sqlalchemy as sa


revision = "b9c0d1e2f3a4"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("apports_dwf")}
    if "code_apport" not in cols:
        op.add_column(
            "apports_dwf",
            sa.Column("code_apport", sa.String(length=50), nullable=True),
        )
    indexes = {i["name"] for i in sa.inspect(bind).get_indexes("apports_dwf")}
    if "ix_apports_dwf_code_apport" not in indexes:
        try:
            op.create_index(
                "ix_apports_dwf_code_apport",
                "apports_dwf",
                ["code_apport"],
            )
        except Exception:
            pass
    if "uq_apports_dwf_project_code" not in indexes:
        try:
            op.create_index(
                "uq_apports_dwf_project_code",
                "apports_dwf",
                ["project_id", "code_apport"],
                unique=True,
            )
        except Exception:
            pass


def downgrade() -> None:
    try:
        op.drop_index("uq_apports_dwf_project_code", table_name="apports_dwf")
    except Exception:
        pass
    try:
        op.drop_index("ix_apports_dwf_code_apport", table_name="apports_dwf")
    except Exception:
        pass
    try:
        op.drop_column("apports_dwf", "code_apport")
    except Exception:
        pass
