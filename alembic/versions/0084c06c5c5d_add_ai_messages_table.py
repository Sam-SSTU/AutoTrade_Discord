"""add_ai_messages_table

Revision ID: 0084c06c5c5d
Revises: 1d2b1b7d9fac
Create Date: 2025-01-23 21:15:10.871974

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0084c06c5c5d'
down_revision: Union[str, None] = '1d2b1b7d9fac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
