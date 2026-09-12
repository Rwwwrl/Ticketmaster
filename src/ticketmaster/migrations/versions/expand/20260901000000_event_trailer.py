"""event trailer

Revision ID: c3fb54fb7828
Revises: dfce0c554e65
Create Date: 2026-09-01 00:00:00.000000+00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3fb54fb7828"
down_revision: Union[str, Sequence[str], None] = "dfce0c554e65"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("event", sa.Column("trailer_bucket", sa.String(), nullable=True))
    op.add_column("event", sa.Column("trailer_key", sa.String(), nullable=True))
    op.execute("UPDATE event SET trailer_bucket = NULL, trailer_key = NULL")


def downgrade() -> None:
    pass
