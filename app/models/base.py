from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Enum as SQLEnum, Boolean
from sqlalchemy.orm import relationship
from enum import Enum
from ..database import Base

class Platform(str, Enum):
    DISCORD = "discord"

class KOL(Base):
    __tablename__ = "kols"
    
    id = Column(Integer, primary_key=True)
    name = Column(String)
    platform = Column(SQLEnum(Platform))
    platform_user_id = Column(String)
    category = Column(String)  # 博主分类
    is_active = Column(Boolean, default=True)
    
    messages = relationship("Message", back_populates="kol")

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True)
    kol_id = Column(Integer, ForeignKey("kols.id"))
    platform = Column(SQLEnum(Platform))
    platform_message_id = Column(String)
    channel_id = Column(String)  # 添加频道ID
    content = Column(String)  # 文字内容
    attachments = Column(JSON)  # 图片等附件
    embeds = Column(JSON)  # 嵌入内容
    referenced_message_id = Column(String, nullable=True)  # 引用的消息ID
    referenced_content = Column(String, nullable=True)  # 引用的消息内容
    is_reply = Column(Boolean, default=False)  # 是否是回复消息
    reply_content = Column(String, nullable=True)  # 回复的内容
    created_at = Column(DateTime)  # 消息创建时间
    
    kol = relationship("KOL", back_populates="messages") 