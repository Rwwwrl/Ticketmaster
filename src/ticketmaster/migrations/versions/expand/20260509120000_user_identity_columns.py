"""user identity columns

Revision ID: a3b1f4d8e207
Revises: 6049953547d2
Create Date: 2026-05-09 12:00:00.000000+00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3b1f4d8e207"
down_revision: Union[str, Sequence[str], None] = "6049953547d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user", sa.Column("uuid", sa.Uuid(), nullable=False))
    op.add_column("user", sa.Column("pool_id", sa.String(), nullable=False))
    op.add_column("user", sa.Column("email", sa.String(), nullable=False))
    op.add_column("user", sa.Column("external_id", sa.String(), nullable=False))
    op.create_index("ix_user_uuid", "user", ["uuid"], unique=True)
    op.create_index("ix_user_email", "user", ["email"], unique=True)
    op.create_index("ix_user_pool_external_id", "user", ["pool_id", "external_id"], unique=True)


def downgrade() -> None:
    pass
