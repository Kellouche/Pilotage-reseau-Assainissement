"""gpkg_versions_immutables

Étape 3B — versionnement immuable des GeoPackage.
- Table gpkg_versions (empreinte SHA-256, storage_kind/ref, contraintes d'unicité)
- projects.gpkg_version_id : pointeur courant
- simulations.gpkg_version_id / gpkg_sha256 / bassin_ref / exutoire_noeud
- FK composites (version_id, project_id) → (id, project_id) : intégrité tenant
  PostgreSQL. Sous SQLite, ces FK composites ne sont pas enforceables sur des
  tables existantes (ALTER ADD CONSTRAINT non supporté) ; la garantie y est
  applicative + CHECK (voir init_db / modèle ORM).

Additive et réversible : aucune donnée existante n'est modifiée.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'gpkg_versions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('org_id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('storage_kind', sa.String(length=16), nullable=False),
        sa.Column('storage_ref', sa.String(length=512), nullable=False),
        sa.Column('filename_original', sa.String(length=255), nullable=True),
        sa.Column('nb_regards', sa.Integer(), nullable=True),
        sa.Column('nb_conduites', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by_id', sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'sha256', name='uq_gpkgver_project_sha'),
        sa.UniqueConstraint('id', 'project_id', name='uq_gpkgver_id_project'),
    )
    op.create_index('ix_gpkg_versions_org_id', 'gpkg_versions', ['org_id'])
    op.create_index('ix_gpkg_versions_project_id', 'gpkg_versions', ['project_id'])
    op.create_index('ix_gpkg_versions_sha256', 'gpkg_versions', ['sha256'])
    op.create_index('ix_gpkg_versions_org_project', 'gpkg_versions', ['org_id', 'project_id'])

    op.add_column('projects', sa.Column('gpkg_version_id', sa.String(length=36), nullable=True))
    op.create_foreign_key('fk_projects_gpkg_version', 'projects', 'gpkg_versions',
                          ['gpkg_version_id'], ['id'])
    # FK composite tenant : la version pointée doit appartenir au même projet
    op.create_foreign_key('fk_projects_gpkg_version_tenant', 'projects', 'gpkg_versions',
                          ['gpkg_version_id', 'id'], ['id', 'project_id'])

    op.add_column('simulations', sa.Column('gpkg_version_id', sa.String(length=36), nullable=True))
    op.add_column('simulations', sa.Column('gpkg_sha256', sa.String(length=64), nullable=True))
    op.add_column('simulations', sa.Column('bassin_ref', sa.String(length=120), nullable=True))
    op.add_column('simulations', sa.Column('exutoire_noeud', sa.String(length=100), nullable=True))
    op.create_foreign_key('fk_simulations_gpkg_version', 'simulations', 'gpkg_versions',
                          ['gpkg_version_id'], ['id'])
    op.create_foreign_key('fk_simulations_gpkg_version_tenant', 'simulations', 'gpkg_versions',
                          ['gpkg_version_id', 'project_id'], ['id', 'project_id'])
    op.create_check_constraint(
        'ck_sim_gpkg_version_requires_project', 'simulations',
        'gpkg_version_id IS NULL OR project_id IS NOT NULL')


def downgrade() -> None:
    op.drop_constraint('ck_sim_gpkg_version_requires_project', 'simulations')
    op.drop_constraint('fk_simulations_gpkg_version_tenant', 'simulations')
    op.drop_constraint('fk_simulations_gpkg_version', 'simulations')
    op.drop_column('simulations', 'exutoire_noeud')
    op.drop_column('simulations', 'bassin_ref')
    op.drop_column('simulations', 'gpkg_sha256')
    op.drop_column('simulations', 'gpkg_version_id')
    op.drop_constraint('fk_projects_gpkg_version_tenant', 'projects')
    op.drop_constraint('fk_projects_gpkg_version', 'projects')
    op.drop_column('projects', 'gpkg_version_id')
    op.drop_index('ix_gpkg_versions_org_project', table_name='gpkg_versions')
    op.drop_index('ix_gpkg_versions_sha256', table_name='gpkg_versions')
    op.drop_index('ix_gpkg_versions_project_id', table_name='gpkg_versions')
    op.drop_index('ix_gpkg_versions_org_id', table_name='gpkg_versions')
    op.drop_table('gpkg_versions')
