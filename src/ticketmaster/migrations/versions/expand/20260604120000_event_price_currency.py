"""event price and currency

Revision ID: e2f4a6b8c930
Revises: d1e3f5a7b829
Create Date: 2026-06-04 12:00:00.000000+00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2f4a6b8c930"
down_revision: Union[str, Sequence[str], None] = "d1e3f5a7b829"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("event", sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False))
    op.add_column("event", sa.Column("currency", sa.String(), nullable=False))
    op.create_index("ix_event_price_id", "event", ["price", "id"])


def downgrade() -> None:
    pass
