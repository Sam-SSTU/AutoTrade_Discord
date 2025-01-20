"""Add is_forwarding column to channels table

Revision ID: add_is_forwarding
Revises: 9ceb8b0f8a2f
Create Date: 2024-03-19

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = 'add_is_forwarding'
down_revision = '9ceb8b0f8a2f'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('channels', sa.Column('is_forwarding', sa.Boolean(), nullable=False, server_default='false'))

def downgrade():
    op.drop_column('channels', 'is_forwarding') 