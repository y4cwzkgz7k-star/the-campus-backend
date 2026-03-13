"""add_title_and_result_source_to_matches

Revision ID: a1b2c3d4e5f6
Revises: 69fcdf07d686
Create Date: 2026-03-13 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '69fcdf07d686'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum type first (required before adding the column)
    result_source_enum = sa.Enum('manual', 'consensus', 'ai_camera', name='result_source')
    result_source_enum.create(op.get_bind(), checkfirst=True)

    op.add_column('matches', sa.Column(
        'title', sa.String(150), nullable=True
    ))
    op.add_column('matches', sa.Column(
        'result_source',
        result_source_enum,
        server_default='manual',
        nullable=False,
    ))


def downgrade() -> None:
    op.drop_column('matches', 'result_source')
    op.drop_column('matches', 'title')
    sa.Enum(name='result_source').drop(op.get_bind(), checkfirst=True)
