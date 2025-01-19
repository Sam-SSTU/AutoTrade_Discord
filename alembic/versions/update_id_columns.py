"""update id columns to bigint

Revision ID: update_id_columns
Revises: initial_migration
Create Date: 2024-01-19 23:38:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'update_id_columns'
down_revision = 'initial_migration'
branch_labels = None
depends_on = None

def upgrade():
    # Update platform_channel_id in channels table
    op.alter_column('channels', 'platform_channel_id',
                   type_=sa.String(length=64),
                   existing_type=sa.String(),
                   existing_nullable=False)
                   
    # Update platform_message_id in messages table
    op.alter_column('messages', 'platform_message_id',
                   type_=sa.String(length=64),
                   existing_type=sa.String(),
                   existing_nullable=False)
                   
    # Update referenced_message_id in messages table
    op.alter_column('messages', 'referenced_message_id',
                   type_=sa.String(length=64),
                   existing_type=sa.String(),
                   existing_nullable=True)

def downgrade():
    # Revert platform_channel_id in channels table
    op.alter_column('channels', 'platform_channel_id',
                   type_=sa.String(),
                   existing_type=sa.String(length=64),
                   existing_nullable=False)
                   
    # Revert platform_message_id in messages table
    op.alter_column('messages', 'platform_message_id',
                   type_=sa.String(),
                   existing_type=sa.String(length=64),
                   existing_nullable=False)
                   
    # Revert referenced_message_id in messages table
    op.alter_column('messages', 'referenced_message_id',
                   type_=sa.String(),
                   existing_type=sa.String(length=64),
                   existing_nullable=True) 