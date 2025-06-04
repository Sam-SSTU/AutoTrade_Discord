"""添加AI工作流步骤详情表

Revision ID: 02bfda718165
Revises: d8d335820255
Create Date: 2025-06-04 16:06:51.573801

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '02bfda718165'
down_revision: Union[str, None] = 'd8d335820255'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### 创建AI处理步骤详情表 ###
    op.create_table('ai_processing_steps',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('ai_message_id', sa.Integer(), sa.ForeignKey('ai_messages.id'), nullable=False),
        sa.Column('step_name', sa.String(100), nullable=False),
        sa.Column('step_order', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, default='processing'),
        sa.Column('input_data', sa.JSON(), nullable=True),
        sa.Column('output_data', sa.JSON(), nullable=True),
        sa.Column('processing_details', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('start_time', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('api_calls_count', sa.Integer(), default=0),
        sa.Column('tokens_used', sa.Integer(), default=0),
        sa.Column('cost_usd', sa.Float(), default=0.0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now())
    )
    
    # 为处理步骤表创建索引
    op.create_index('ix_ai_processing_steps_ai_message_id', 'ai_processing_steps', ['ai_message_id'])
    op.create_index('ix_ai_processing_steps_step_name', 'ai_processing_steps', ['step_name'])
    op.create_index('ix_ai_processing_steps_status', 'ai_processing_steps', ['status'])
    
    # ### 创建AI手动编辑记录表 ###
    op.create_table('ai_manual_edits',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('ai_message_id', sa.Integer(), sa.ForeignKey('ai_messages.id'), nullable=False),
        sa.Column('field_name', sa.String(100), nullable=False),
        sa.Column('original_value', sa.JSON(), nullable=True),
        sa.Column('edited_value', sa.JSON(), nullable=True),
        sa.Column('edit_reason', sa.Text(), nullable=True),
        sa.Column('editor_id', sa.String(100), nullable=True),
        sa.Column('editor_name', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now())
    )
    
    # 为手动编辑表创建索引
    op.create_index('ix_ai_manual_edits_ai_message_id', 'ai_manual_edits', ['ai_message_id'])
    op.create_index('ix_ai_manual_edits_field_name', 'ai_manual_edits', ['field_name'])


def downgrade() -> None:
    # ### 删除AI手动编辑记录表 ###
    op.drop_index('ix_ai_manual_edits_field_name', table_name='ai_manual_edits')
    op.drop_index('ix_ai_manual_edits_ai_message_id', table_name='ai_manual_edits')
    op.drop_table('ai_manual_edits')
    
    # ### 删除AI处理步骤详情表 ###
    op.drop_index('ix_ai_processing_steps_status', table_name='ai_processing_steps')
    op.drop_index('ix_ai_processing_steps_step_name', table_name='ai_processing_steps')
    op.drop_index('ix_ai_processing_steps_ai_message_id', table_name='ai_processing_steps')
    op.drop_table('ai_processing_steps') 