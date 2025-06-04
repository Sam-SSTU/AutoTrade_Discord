"""add_ai_processing_fields

Revision ID: d8d335820255
Revises: 92b038d3e082
Create Date: 2025-06-03 16:43:12.156773

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd8d335820255'
down_revision: Union[str, None] = '92b038d3e082'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### 添加AI消息表的新字段 ###
    # 第一阶段分析结果
    op.add_column('ai_messages', sa.Column('is_trading_related', sa.Boolean(), default=False, nullable=True))
    op.add_column('ai_messages', sa.Column('priority', sa.Integer(), default=1, nullable=True))
    op.add_column('ai_messages', sa.Column('keywords', sa.JSON(), nullable=True))
    op.add_column('ai_messages', sa.Column('category', sa.String(50), nullable=True))
    op.add_column('ai_messages', sa.Column('urgency', sa.String(20), default='低', nullable=True))
    op.add_column('ai_messages', sa.Column('sentiment', sa.String(20), default='中性', nullable=True))
    op.add_column('ai_messages', sa.Column('confidence', sa.Float(), default=0.0, nullable=True))
    op.add_column('ai_messages', sa.Column('analysis_summary', sa.Text(), nullable=True))
    
    # 交易信号相关
    op.add_column('ai_messages', sa.Column('has_trading_signal', sa.Boolean(), default=False, nullable=True))
    op.add_column('ai_messages', sa.Column('trading_signal', sa.JSON(), nullable=True))
    
    # 上下文信息
    op.add_column('ai_messages', sa.Column('context_messages', sa.JSON(), nullable=True))
    
    # 处理状态
    op.add_column('ai_messages', sa.Column('is_processed', sa.Boolean(), default=False, nullable=True))
    op.add_column('ai_messages', sa.Column('processing_error', sa.Text(), nullable=True))
    op.add_column('ai_messages', sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True))
    
    # 创建索引
    op.create_index('ix_ai_messages_is_trading_related', 'ai_messages', ['is_trading_related'])
    op.create_index('ix_ai_messages_priority', 'ai_messages', ['priority'])
    op.create_index('ix_ai_messages_category', 'ai_messages', ['category'])
    op.create_index('ix_ai_messages_urgency', 'ai_messages', ['urgency'])
    op.create_index('ix_ai_messages_has_trading_signal', 'ai_messages', ['has_trading_signal'])
    op.create_index('ix_ai_messages_is_processed', 'ai_messages', ['is_processed'])
    
    # ### 创建AI处理日志表 ###
    op.create_table('ai_processing_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('message_id', sa.Integer(), nullable=False),
        sa.Column('stage', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True)
    )
    
    # 为日志表创建索引
    op.create_index('ix_ai_processing_logs_message_id', 'ai_processing_logs', ['message_id'])
    op.create_index('ix_ai_processing_logs_stage', 'ai_processing_logs', ['stage'])
    op.create_index('ix_ai_processing_logs_status', 'ai_processing_logs', ['status'])
    op.create_index('ix_ai_processing_logs_start_time', 'ai_processing_logs', ['start_time'])


def downgrade() -> None:
    # ### 删除AI处理日志表 ###
    op.drop_index('ix_ai_processing_logs_start_time', table_name='ai_processing_logs')
    op.drop_index('ix_ai_processing_logs_status', table_name='ai_processing_logs')
    op.drop_index('ix_ai_processing_logs_stage', table_name='ai_processing_logs')
    op.drop_index('ix_ai_processing_logs_message_id', table_name='ai_processing_logs')
    op.drop_table('ai_processing_logs')
    
    # ### 删除AI消息表的索引 ###
    op.drop_index('ix_ai_messages_is_processed', table_name='ai_messages')
    op.drop_index('ix_ai_messages_has_trading_signal', table_name='ai_messages')
    op.drop_index('ix_ai_messages_urgency', table_name='ai_messages')
    op.drop_index('ix_ai_messages_category', table_name='ai_messages')
    op.drop_index('ix_ai_messages_priority', table_name='ai_messages')
    op.drop_index('ix_ai_messages_is_trading_related', table_name='ai_messages')
    
    # ### 删除AI消息表的新字段 ###
    op.drop_column('ai_messages', 'processed_at')
    op.drop_column('ai_messages', 'processing_error')
    op.drop_column('ai_messages', 'is_processed')
    op.drop_column('ai_messages', 'context_messages')
    op.drop_column('ai_messages', 'trading_signal')
    op.drop_column('ai_messages', 'has_trading_signal')
    op.drop_column('ai_messages', 'analysis_summary')
    op.drop_column('ai_messages', 'confidence')
    op.drop_column('ai_messages', 'sentiment')
    op.drop_column('ai_messages', 'urgency')
    op.drop_column('ai_messages', 'category')
    op.drop_column('ai_messages', 'keywords')
    op.drop_column('ai_messages', 'priority')
    op.drop_column('ai_messages', 'is_trading_related')
