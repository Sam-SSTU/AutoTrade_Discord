from sqlalchemy import Column, Integer, String, DateTime, JSON, Text, Boolean, Float, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.schema import DefaultClause
from sqlalchemy.orm import relationship
from ..database import Base

class AIMessage(Base):
    __tablename__ = 'ai_messages'
    
    id = Column(Integer, primary_key=True)
    channel_id = Column(String(100), nullable=False, index=True)
    channel_name = Column(String(200), nullable=False)
    message_content = Column(Text, nullable=False)
    references = Column(JSON, nullable=True)  # Store references and attachments as JSON
    
    # 第一阶段分析结果
    is_trading_related = Column(Boolean, default=False, index=True)
    priority = Column(Integer, default=1, index=True)  # 1-5优先级
    keywords = Column(JSON, nullable=True)  # 提取的关键词
    category = Column(String(50), nullable=True, index=True)  # 消息分类
    sentiment = Column(String(20), default='中性')  # 情感倾向
    analysis_summary = Column(Text, nullable=True)  # 分析摘要
    
    # 交易信号相关
    has_trading_signal = Column(Boolean, default=False, index=True)
    trading_signal = Column(JSON, nullable=True)  # 交易信号详情
    
    # 上下文信息
    context_messages = Column(JSON, nullable=True)  # 上下文消息IDs
    
    # 处理状态
    is_processed = Column(Boolean, default=False, index=True)  # 是否已完成第一阶段处理
    processing_error = Column(Text, nullable=True)  # 处理错误信息
    
    created_at = Column(DateTime(timezone=True), 
                       server_default=func.now(),
                       nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)  # 处理完成时间
    
    # 关联关系
    processing_steps = relationship("AIProcessingStep", back_populates="ai_message", cascade="all, delete-orphan")
    manual_edits = relationship("AIManualEdit", back_populates="ai_message", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<AIMessage(id={self.id}, channel_id='{self.channel_id}', is_trading_related={self.is_trading_related}, priority={self.priority})>"

class AIProcessingLog(Base):
    """AI处理日志表，记录处理过程和性能"""
    __tablename__ = 'ai_processing_logs'
    
    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, nullable=False, index=True)
    stage = Column(String(50), nullable=False)  # 处理阶段：stage1, stage2, stage3
    status = Column(String(20), nullable=False)  # 状态：processing, completed, failed
    start_time = Column(DateTime(timezone=True), server_default=func.now())
    end_time = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)  # 处理耗时(毫秒)
    error_message = Column(Text, nullable=True)
    details = Column(JSON, nullable=True)  # 处理详情
    
    def __repr__(self):
        return f"<AIProcessingLog(id={self.id}, message_id={self.message_id}, stage='{self.stage}', status='{self.status}')>" 

class AIProcessingStep(Base):
    """AI处理步骤详情表，记录每个处理步骤的输入和输出数据"""
    __tablename__ = 'ai_processing_steps'
    
    id = Column(Integer, primary_key=True)
    ai_message_id = Column(Integer, ForeignKey('ai_messages.id'), nullable=False, index=True)
    step_name = Column(String(100), nullable=False, index=True)  # 步骤名称：context_building, message_analysis, trading_signal_extraction等
    step_order = Column(Integer, nullable=False)  # 步骤顺序
    status = Column(String(20), nullable=False, default='processing')  # processing, completed, failed, skipped
    
    # 输入数据
    input_data = Column(JSON, nullable=True)  # 步骤的输入数据
    
    # 输出数据
    output_data = Column(JSON, nullable=True)  # 步骤的输出数据
    
    # 处理详情
    processing_details = Column(JSON, nullable=True)  # 处理过程中的详细信息
    error_message = Column(Text, nullable=True)  # 错误信息
    
    # 时间信息
    start_time = Column(DateTime(timezone=True), server_default=func.now())
    end_time = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)  # 处理耗时(毫秒)
    
    # 性能信息
    api_calls_count = Column(Integer, default=0)  # API调用次数
    tokens_used = Column(Integer, default=0)  # 使用的token数量
    cost_usd = Column(Float, default=0.0)  # 估算成本（美元）
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 关联关系
    ai_message = relationship("AIMessage", back_populates="processing_steps")
    
    def __repr__(self):
        return f"<AIProcessingStep(id={self.id}, ai_message_id={self.ai_message_id}, step_name='{self.step_name}', status='{self.status}')>"

class AIManualEdit(Base):
    """AI手动编辑记录表，记录用户对AI处理结果的手动修改"""
    __tablename__ = 'ai_manual_edits'
    
    id = Column(Integer, primary_key=True)
    ai_message_id = Column(Integer, ForeignKey('ai_messages.id'), nullable=False, index=True)
    
    # 编辑信息
    field_name = Column(String(100), nullable=False)  # 被编辑的字段名称
    original_value = Column(JSON, nullable=True)  # 原始值
    edited_value = Column(JSON, nullable=True)  # 编辑后的值
    edit_reason = Column(Text, nullable=True)  # 编辑原因
    
    # 用户信息
    editor_id = Column(String(100), nullable=True)  # 编辑者ID
    editor_name = Column(String(200), nullable=True)  # 编辑者名称
    
    # 时间信息
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 关联关系
    ai_message = relationship("AIMessage", back_populates="manual_edits")
    
    def __repr__(self):
        return f"<AIManualEdit(id={self.id}, ai_message_id={self.ai_message_id}, field_name='{self.field_name}')>" 