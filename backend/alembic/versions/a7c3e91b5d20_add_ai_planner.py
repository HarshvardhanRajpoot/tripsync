"""add ai planner: pgvector embeddings on places, ai_plans table

Revision ID: a7c3e91b5d20
Revises: d421dbdea0aa
Create Date: 2026-11-13 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision = 'a7c3e91b5d20'
down_revision = 'd421dbdea0aa'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column('places', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('places', sa.Column('embedding', Vector(768), nullable=True))
    op.create_table(
        'ai_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('trip_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('request', sa.Text(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['trip_id'], ['trips.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ai_plans_id'), 'ai_plans', ['id'], unique=False)
    op.create_index(op.f('ix_ai_plans_trip_id'), 'ai_plans', ['trip_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_ai_plans_trip_id'), table_name='ai_plans')
    op.drop_index(op.f('ix_ai_plans_id'), table_name='ai_plans')
    op.drop_table('ai_plans')
    op.drop_column('places', 'embedding')
    op.drop_column('places', 'description')
