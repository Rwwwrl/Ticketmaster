"""inbox message

Revision ID: c3d9e1f47a58
Revises: dbf0abfd1d37
Create Date: 2026-10-15 12:00:00.000000+00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d9e1f47a58"
down_revision: Union[str, Sequence[str], None] = "dbf0abfd1d37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "inbox_message",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("code", sa.Integer(), nullable=False),
        sa.Column("logical_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inbox_message_logical_id_code", "inbox_message", ["logical_id", "code"], unique=True)
    op.create_index("ix_inbox_message_created_at", "inbox_message", ["created_at"], unique=False)


def downgrade() -> None:
    pass
