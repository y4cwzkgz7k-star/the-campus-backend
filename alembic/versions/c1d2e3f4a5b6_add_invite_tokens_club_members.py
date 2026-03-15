"""add_invite_tokens_club_members

Revision ID: c1d2e3f4a5b6
Revises: b2c3d4e5f6a7
Create Date: 2026-03-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Add 'club_manager' to the existing user_role enum.
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction, so we use
    # a separate connection with AUTOCOMMIT isolation level.
    connection = op.get_bind()
    autocommit_conn = connection.execution_options(isolation_level="AUTOCOMMIT")
    autocommit_conn.execute(
        sa.text("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'club_manager'")
    )

    # Step 2: Create invite_type_enum
    invite_type_enum = sa.Enum("club_owner", "club_manager", name="invite_type_enum")
    invite_type_enum.create(op.get_bind(), checkfirst=True)

    # Step 3: Create club_member_role_enum
    club_member_role_enum = sa.Enum("owner", "manager", name="club_member_role_enum")
    club_member_role_enum.create(op.get_bind(), checkfirst=True)

    # Step 4: Create invite_tokens table
    op.create_table(
        "invite_tokens",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "invite_type",
            sa.Enum("club_owner", "club_manager", name="invite_type_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("club_id", sa.UUID(), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("claimed_by_user_id", sa.UUID(), nullable=True),
        sa.Column("email_hint", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["claimed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_invite_tokens_token_hash"),
    )
    op.create_index(
        op.f("ix_invite_tokens_token_hash"), "invite_tokens", ["token_hash"], unique=True
    )

    # Step 5: Create club_members table
    op.create_table(
        "club_members",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("club_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("owner", "manager", name="club_member_role_enum", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("club_id", "user_id", name="uq_club_members_club_user"),
    )
    op.create_index(op.f("ix_club_members_club_id"), "club_members", ["club_id"], unique=False)
    op.create_index(op.f("ix_club_members_user_id"), "club_members", ["user_id"], unique=False)


def downgrade() -> None:
    # Drop indexes and tables in reverse dependency order.
    # NOTE: We do NOT remove 'club_manager' from user_role enum because
    # PostgreSQL does not support removing values from an enum type without
    # recreating it — which would risk breaking existing data.

    op.drop_index(op.f("ix_club_members_user_id"), table_name="club_members")
    op.drop_index(op.f("ix_club_members_club_id"), table_name="club_members")
    op.drop_table("club_members")

    op.drop_index(op.f("ix_invite_tokens_token_hash"), table_name="invite_tokens")
    op.drop_table("invite_tokens")

    # Drop the new enum types
    sa.Enum(name="club_member_role_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="invite_type_enum").drop(op.get_bind(), checkfirst=True)
