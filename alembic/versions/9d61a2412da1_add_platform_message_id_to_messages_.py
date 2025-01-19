"""Add platform_message_id to messages table

Revision ID: 9d61a2412da1
Revises: 607cd67ec208
Create Date: 2024-02-19 15:23:45.123456

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d61a2412da1'
down_revision: Union[str, None] = '607cd67ec208'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the foreign key constraint first
    op.drop_constraint('messages_referenced_message_id_fkey', 'messages', type_='foreignkey')
    
    # Add platform_message_id column
    op.add_column('messages', sa.Column('platform_message_id', sa.String(), nullable=True))
    op.create_index(op.f('ix_messages_platform_message_id'), 'messages', ['platform_message_id'], unique=False)
    
    # Change referenced_message_id to String
    op.alter_column('messages', 'referenced_message_id',
                    existing_type=sa.INTEGER(),
                    type_=sa.String(),
                    existing_nullable=True)


def downgrade() -> None:
    # Change referenced_message_id back to Integer
    op.alter_column('messages', 'referenced_message_id',
                    existing_type=sa.String(),
                    type_=sa.INTEGER(),
                    existing_nullable=True)
    
    # Drop platform_message_id column
    op.drop_index(op.f('ix_messages_platform_message_id'), table_name='messages')
    op.drop_column('messages', 'platform_message_id')
    
    # Re-add the foreign key constraint
    op.create_foreign_key('messages_referenced_message_id_fkey', 'messages', 'messages',
                         ['referenced_message_id'], ['id'])
