from sqlalchemy import Column, Integer, String, DateTime, JSON, Text, Boolean, Float
from sqlalchemy.sql import func
from sqlalchemy.schema import DefaultClause
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
    urgency = Column(String(20), default='低', index=True)  # 紧急程度
    sentiment = Column(String(20), default='中性')  # 情感倾向
    confidence = Column(Float, default=0.0)  # AI分析置信度
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