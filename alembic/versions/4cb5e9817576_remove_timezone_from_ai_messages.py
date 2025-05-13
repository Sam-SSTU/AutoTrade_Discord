"""remove timezone from ai messages

Revision ID: 4cb5e9817576
Revises: c04869c0b8a5
Create Date: 2025-01-23 21:49:25.299739

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '4cb5e9817576'
down_revision: Union[str, None] = 'c04869c0b8a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 修改 ai_messages 表的时区设置
    op.execute("""
        ALTER TABLE ai_messages 
        ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE 
        USING created_at AT TIME ZONE 'UTC';
    """)


def downgrade() -> None:
    # 恢复 ai_messages 表的时区设置
    op.execute("""
        ALTER TABLE ai_messages 
        ALTER COLUMN created_at TYPE TIMESTAMP 
        USING created_at AT TIME ZONE 'UTC';
    """)
