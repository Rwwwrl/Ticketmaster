"""event start_at id index

Revision ID: b8c9d1e2f304
Revises: a3b1f4d8e207
Create Date: 2026-05-14 12:00:00.000000+00:00

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8c9d1e2f304"
down_revision: Union[str, Sequence[str], None] = "a3b1f4d8e207"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_event_start_at_id", "event", ["start_at", "id"], unique=False)


def downgrade() -> None:
    pass
