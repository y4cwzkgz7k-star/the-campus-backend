"""add_email_token_fields_to_users

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('email_verification_token_hash', sa.String(64), nullable=True))
    op.add_column('users', sa.Column('password_reset_token_hash', sa.String(64), nullable=True))
    op.add_column('users', sa.Column('password_reset_expires_at', sa.DateTime(timezone=True), nullable=True))

    op.create_index('ix_users_email_verification_token_hash', 'users', ['email_verification_token_hash'])
    op.create_index('ix_users_password_reset_token_hash', 'users', ['password_reset_token_hash'])


def downgrade() -> None:
    op.drop_index('ix_users_password_reset_token_hash', table_name='users')
    op.drop_index('ix_users_email_verification_token_hash', table_name='users')
    op.drop_column('users', 'password_reset_expires_at')
    op.drop_column('users', 'password_reset_token_hash')
    op.drop_column('users', 'email_verification_token_hash')
