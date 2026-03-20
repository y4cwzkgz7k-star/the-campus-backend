"""add_result_consensus_fields

Add two-confirmation result flow fields to matches table:
- result_submitted_by: tracks who submitted the first (pending) result
- submitted_score_home / submitted_score_away: the pending scores
- 'disputed' value added to match_status enum

Revision ID: d3e4f5a6b7c8
Revises: c1d2e3f4a5b6
Create Date: 2026-03-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 'disputed' to the match_status enum
    op.execute("ALTER TYPE match_status ADD VALUE IF NOT EXISTS 'disputed'")

    # Add consensus tracking columns
    op.add_column('matches', sa.Column(
        'result_submitted_by',
        UUID(as_uuid=True),
        sa.ForeignKey('users.id'),
        nullable=True,
    ))
    op.add_column('matches', sa.Column(
        'submitted_score_home',
        sa.Integer(),
        nullable=True,
    ))
    op.add_column('matches', sa.Column(
        'submitted_score_away',
        sa.Integer(),
        nullable=True,
    ))


def downgrade() -> None:
    op.drop_column('matches', 'submitted_score_away')
    op.drop_column('matches', 'submitted_score_home')
    op.drop_column('matches', 'result_submitted_by')
    # Note: PostgreSQL does not support removing values from enums.
    # The 'disputed' value will remain in match_status but is harmless.
