"""add ai messages table

Revision ID: c04869c0b8a5
Revises: 0084c06c5c5d
Create Date: 2025-01-23 21:35:39.072865

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c04869c0b8a5'
down_revision: Union[str, None] = '0084c06c5c5d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('ai_messages',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('channel_id', sa.String(100), nullable=False),
        sa.Column('channel_name', sa.String(200), nullable=False),
        sa.Column('message_content', sa.Text(), nullable=False),
        sa.Column('references', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ai_messages_channel_id', 'ai_messages', ['channel_id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('ix_ai_messages_channel_id', table_name='ai_messages')
    op.drop_table('ai_messages')
    # ### end Alembic commands ###
