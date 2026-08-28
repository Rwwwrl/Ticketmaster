"""initial contract branch"""

from typing import Sequence, Union

# NOTE @sosov: Empty migration that establishes the contract branch.
# All destructive schema changes (DROP, REMOVE) go here.
revision: str = "5cd61ce39fee"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = ("contract",)
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
