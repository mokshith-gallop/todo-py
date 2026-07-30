"""Initial schema: user, task_list, task tables

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- user table ---
    op.create_table(
        "user",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    # --- task_list table ---
    op.create_table(
        "task_list",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("position", sa.Float(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        # Required for composite FK on task table
        sa.UniqueConstraint("id", "user_id", name="uq_task_list_id_user_id"),
    )

    # --- task table ---
    op.create_table(
        "task",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("list_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "priority",
            sa.String(4),
            server_default="none",
            nullable=False,
        ),
        sa.Column("position", sa.Float(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "version", sa.Integer(), server_default="1", nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        # Simple FKs
        sa.ForeignKeyConstraint(["list_id"], ["task_list.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        # Composite FK: ensures task's user owns the list
        sa.ForeignKeyConstraint(
            ["list_id", "user_id"],
            ["task_list.id", "task_list.user_id"],
            name="fk_task_list_same_owner",
        ),
        # CHECK constraints
        sa.CheckConstraint(
            "char_length(trim(title)) > 0", name="ck_task_title_not_blank"
        ),
        sa.CheckConstraint(
            "priority IN ('none', 'low', 'med', 'high')",
            name="ck_task_priority",
        ),
    )

    # --- Indexes on task ---
    op.create_index(
        "ix_task_list_position",
        "task",
        ["list_id", "position"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_task_user", "task", ["user_id"])
    op.create_index(
        "ix_task_purge",
        "task",
        ["deleted_at"],
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_task_purge", table_name="task")
    op.drop_index("ix_task_user", table_name="task")
    op.drop_index("ix_task_list_position", table_name="task")
    op.drop_table("task")
    op.drop_table("task_list")
    op.drop_table("user")
