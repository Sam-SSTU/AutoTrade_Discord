"""add channel category fields

Revision ID: add_channel_category_fields
Revises: add_unread_messages
Create Date: 2024-03-20 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_channel_category_fields'
down_revision = 'add_unread_messages'
branch_labels = None
depends_on = None

def upgrade():
    # Add new columns to channels table
    op.add_column('channels', sa.Column('position', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('channels', sa.Column('parent_id', sa.String(), nullable=True))
    op.add_column('channels', sa.Column('type', sa.Integer(), nullable=True))

def downgrade():
    # Remove the new columns
    op.drop_column('channels', 'type')
    op.drop_column('channels', 'parent_id')
    op.drop_column('channels', 'position') 