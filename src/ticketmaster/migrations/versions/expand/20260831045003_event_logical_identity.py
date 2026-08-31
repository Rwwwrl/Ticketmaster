"""event logical identity

Revision ID: dfce0c554e65
Revises: e2f4a6b8c930
Create Date: 2026-08-31 04:50:03.084160+00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dfce0c554e65"
down_revision: Union[str, Sequence[str], None] = "e2f4a6b8c930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "event",
        sa.Column("logical_identity", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
    )
    op.create_index("ix_event_logical_identity", "event", ["logical_identity"], unique=True)
    op.alter_column("event", "logical_identity", server_default=None)


def downgrade() -> None:
    pass
