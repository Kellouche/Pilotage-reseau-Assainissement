# -*- coding: utf-8 -*-
"""
Cloisonnement des couches SIG satellites par version GPKG.

Un projet = un seul slot « réseau courant » : chaque chargement de
.gpkg/.inp réutilise la même ligne projects et crée une gpkg_version.
project_id seul ne distinguait donc pas les réseaux — les couches
satellites apparaissaient dans tous les projets/réseaux.

Ajoute project_aux_layers.gpkg_version_id (FK gpkg_versions, nullable)
et rattache les couches existantes à la version courante de leur
projet au moment de la migration (comportement le plus proche de
l'existant : elles restent visibles sur le réseau actif).

Idempotent : la colonne/index peuvent déjà exister sur les bases
créées par create_all (tests, nouvelles installs).
"""
from alembic import op
import sqlalchemy as sa


revision = "a8b9c0d1e2f3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("project_aux_layers")}
    if "gpkg_version_id" not in cols:
        op.add_column("project_aux_layers",
                      sa.Column("gpkg_version_id", sa.String(length=36), nullable=True))
    # SQLite : ALTER de contrainte non supporté → pas de FK ajoutée ici
    # (garantie applicative ; l'ORM porte la FK pour les nouvelles bases).
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_aux_layers_gpkg_version "
        "ON project_aux_layers (gpkg_version_id)"))
    # Backfill : chaque couche existante rejoint la version GPKG courante
    # de son projet (NULL si le projet n'est pas versionné).
    op.execute(sa.text(
        """
        UPDATE project_aux_layers
        SET gpkg_version_id = (
            SELECT p.gpkg_version_id FROM projects p
            WHERE p.id = project_aux_layers.project_id
        )
        WHERE project_aux_layers.gpkg_version_id IS NULL
        """))


def downgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("project_aux_layers")}
    if "gpkg_version_id" in cols:
        op.drop_index("ix_aux_layers_gpkg_version", table_name="project_aux_layers")
        op.drop_column("project_aux_layers", "gpkg_version_id")
