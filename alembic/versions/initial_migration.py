"""initial migration

Revision ID: initial_migration
Revises: 
Create Date: 2024-01-20 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'initial_migration'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Platform enum
    op.execute("CREATE TYPE platform AS ENUM ('DISCORD')")
    
    # Create KOL table
    op.create_table(
        'kol',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('platform', sa.Enum('DISCORD', name='platform'), nullable=False),
        sa.Column('platform_user_id', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('platform', 'platform_user_id')
    )
    
    # Create Channel table
    op.create_table(
        'channel',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('platform_channel_id', sa.String(), nullable=False, unique=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('guild_id', sa.String(), nullable=True),
        sa.Column('guild_name', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create Message table
    op.create_table(
        'message',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('platform_message_id', sa.String(), nullable=False, unique=True),
        sa.Column('channel_id', sa.Integer(), nullable=False),
        sa.Column('kol_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('attachments', sa.JSON(), nullable=True),
        sa.Column('embeds', sa.JSON(), nullable=True),
        sa.Column('referenced_message_id', sa.String(), nullable=True),
        sa.Column('referenced_content', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['channel_id'], ['channel.id'], ),
        sa.ForeignKeyConstraint(['kol_id'], ['kol.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index(op.f('ix_message_created_at'), 'message', ['created_at'], unique=False)
    op.create_index(op.f('ix_message_platform_message_id'), 'message', ['platform_message_id'], unique=True)
    op.create_index(op.f('ix_channel_platform_channel_id'), 'channel', ['platform_channel_id'], unique=True)
    op.create_index(op.f('ix_kol_platform_user_id'), 'kol', ['platform_user_id'], unique=False)


def downgrade():
    # Drop indexes
    op.drop_index(op.f('ix_kol_platform_user_id'), table_name='kol')
    op.drop_index(op.f('ix_channel_platform_channel_id'), table_name='channel')
    op.drop_index(op.f('ix_message_platform_message_id'), table_name='message')
    op.drop_index(op.f('ix_message_created_at'), table_name='message')
    
    # Drop tables
    op.drop_table('message')
    op.drop_table('channel')
    op.drop_table('kol')
    
    # Drop enum
    op.execute('DROP TYPE platform') 