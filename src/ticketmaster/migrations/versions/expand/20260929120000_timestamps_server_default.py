"""timestamps server default

Revision ID: a7c1e3f5b902
Revises: c3fb54fb7828
Create Date: 2026-09-29 12:00:00.000000+00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c1e3f5b902"
down_revision: Union[str, Sequence[str], None] = "c3fb54fb7828"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("event", "user", "ticket")


def upgrade() -> None:
    for table in _TABLES:
        for column in ("created_at", "updated_at"):
            op.alter_column(table, column, server_default=sa.func.now())


def downgrade() -> None:
    pass
