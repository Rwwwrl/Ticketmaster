"""initial expand branch"""

from typing import Sequence, Union

# NOTE @sosov: Empty migration that establishes the expand branch.
# All additive schema changes (CREATE, ADD) go here.
revision: str = "9a66edc19d08"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = ("expand",)
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
