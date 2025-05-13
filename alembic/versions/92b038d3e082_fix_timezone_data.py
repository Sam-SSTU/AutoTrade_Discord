"""fix_timezone_data

Revision ID: 92b038d3e082
Revises: 4cb5e9817576
Create Date: 2024-03-27

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP
from datetime import datetime, timezone

# revision identifiers, used by Alembic.
revision = '92b038d3e082'
down_revision = '4cb5e9817576'
branch_labels = None
depends_on = None

def upgrade():
    # 1. 修改所有时间字段为带时区的时间戳
    op.execute("""
        -- 修改 messages 表
        ALTER TABLE messages 
        ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE 
        USING created_at AT TIME ZONE 'UTC';
        
        -- 修改 channels 表
        ALTER TABLE channels 
        ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE 
        USING created_at AT TIME ZONE 'UTC',
        ALTER COLUMN updated_at TYPE TIMESTAMP WITH TIME ZONE 
        USING updated_at AT TIME ZONE 'UTC';
        
        -- 修改 kols 表
        ALTER TABLE kols 
        ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE 
        USING created_at AT TIME ZONE 'UTC',
        ALTER COLUMN updated_at TYPE TIMESTAMP WITH TIME ZONE 
        USING updated_at AT TIME ZONE 'UTC';
        
        -- 修改 attachments 表
        ALTER TABLE attachments 
        ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE 
        USING created_at AT TIME ZONE 'UTC';
        
        -- 修改 unread_messages 表
        ALTER TABLE unread_messages 
        ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE 
        USING created_at AT TIME ZONE 'UTC',
        ALTER COLUMN updated_at TYPE TIMESTAMP WITH TIME ZONE 
        USING updated_at AT TIME ZONE 'UTC';
        
        -- 修改 ai_messages 表
        ALTER TABLE ai_messages 
        ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE 
        USING created_at AT TIME ZONE 'UTC';
    """)

def downgrade():
    # 将时间字段改回不带时区的时间戳
    op.execute("""
        -- 修改 messages 表
        ALTER TABLE messages 
        ALTER COLUMN created_at TYPE TIMESTAMP 
        USING created_at AT TIME ZONE 'UTC';
        
        -- 修改 channels 表
        ALTER TABLE channels 
        ALTER COLUMN created_at TYPE TIMESTAMP 
        USING created_at AT TIME ZONE 'UTC',
        ALTER COLUMN updated_at TYPE TIMESTAMP 
        USING updated_at AT TIME ZONE 'UTC';
        
        -- 修改 kols 表
        ALTER TABLE kols 
        ALTER COLUMN created_at TYPE TIMESTAMP 
        USING created_at AT TIME ZONE 'UTC',
        ALTER COLUMN updated_at TYPE TIMESTAMP 
        USING updated_at AT TIME ZONE 'UTC';
        
        -- 修改 attachments 表
        ALTER TABLE attachments 
        ALTER COLUMN created_at TYPE TIMESTAMP 
        USING created_at AT TIME ZONE 'UTC';
        
        -- 修改 unread_messages 表
        ALTER TABLE unread_messages 
        ALTER COLUMN created_at TYPE TIMESTAMP 
        USING created_at AT TIME ZONE 'UTC',
        ALTER COLUMN updated_at TYPE TIMESTAMP 
        USING updated_at AT TIME ZONE 'UTC';
        
        -- 修改 ai_messages 表
        ALTER TABLE ai_messages 
        ALTER COLUMN created_at TYPE TIMESTAMP 
        USING created_at AT TIME ZONE 'UTC';
    """)
