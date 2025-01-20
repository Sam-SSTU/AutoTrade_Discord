"""add unread messages table

Revision ID: add_unread_messages
Revises: update_id_columns
Create Date: 2024-03-20 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_unread_messages'
down_revision = 'update_id_columns'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('unread_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('channel_id', sa.Integer(), nullable=False),
        sa.Column('last_read_message_id', sa.Integer(), nullable=True),
        sa.Column('unread_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], ),
        sa.ForeignKeyConstraint(['last_read_message_id'], ['messages.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_unread_messages_channel_id'), 'unread_messages', ['channel_id'], unique=True)


def downgrade():
    op.drop_index(op.f('ix_unread_messages_channel_id'), table_name='unread_messages')
    op.drop_table('unread_messages') 