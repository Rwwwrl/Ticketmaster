"""event search vector

Revision ID: c9d2e3f4a516
Revises: b8c9d1e2f304
Create Date: 2026-05-20 12:00:00.000000+00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c9d2e3f4a516"
down_revision: Union[str, Sequence[str], None] = "b8c9d1e2f304"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "event",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('english', coalesce(name, '')), 'A') || "
                "setweight(to_tsvector('english', coalesce(description, '')), 'B')",
                persisted=True,
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_event_search_vector",
        "event",
        ["search_vector"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    pass
