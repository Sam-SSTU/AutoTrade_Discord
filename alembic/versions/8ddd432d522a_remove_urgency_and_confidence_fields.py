"""remove_urgency_and_confidence_fields

Revision ID: 8ddd432d522a
Revises: d8d335820255
Create Date: 2025-01-26 03:23:21.459798

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8ddd432d522a'
down_revision: Union[str, None] = '02bfda718165'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### 移除 urgency 和 confidence 字段 ###
    op.drop_column('ai_messages', 'urgency')
    op.drop_column('ai_messages', 'confidence')


def downgrade() -> None:
    # ### 恢复 urgency 和 confidence 字段 ###
    op.add_column('ai_messages', sa.Column('urgency', sa.String(20), default='低', nullable=True))
    op.add_column('ai_messages', sa.Column('confidence', sa.Float(), default=0.0, nullable=True))
