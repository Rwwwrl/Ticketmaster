"""rename external_id to cognito_username

Revision ID: d1e3f5a7b829
Revises: c9d2e3f4a516
Create Date: 2026-05-22 12:00:00.000000+00:00

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1e3f5a7b829"
down_revision: Union[str, Sequence[str], None] = "c9d2e3f4a516"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_user_pool_external_id", table_name="user")
    op.alter_column("user", "external_id", new_column_name="cognito_username")
    op.create_index(
        "ix_user_pool_cognito_username",
        "user",
        ["pool_id", "cognito_username"],
        unique=True,
    )


def downgrade() -> None:
    pass
