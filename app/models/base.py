from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Enum, Boolean, func, LargeBinary
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import enum
from ..database import Base
from datetime import datetime

Base = declarative_base()

class Platform(enum.Enum):
    DISCORD = "discord"

class KOLCategory(enum.Enum):
    CRYPTO = "crypto"
    STOCKS = "stocks"
    FUTURES = "futures"
    FOREX = "forex"
    OTHERS = "others"

class Channel(Base):
    __tablename__ = "channels"
    
    id = Column(Integer, primary_key=True)
    platform_channel_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    guild_id = Column(String, nullable=False)
    guild_name = Column(String, nullable=False)
    category_id = Column(String)
    category_name = Column(String)
    position = Column(Integer, default=0)  # 频道在分类中的位置
    parent_id = Column(String)  # 父频道ID（对应Discord的category ID）
    type = Column(Integer)  # Discord的频道类型（0=text, 2=voice, 4=category等）
    is_active = Column(Boolean, default=False)
    kol_category = Column(Enum(KOLCategory), nullable=True)
    kol_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    messages = relationship("Message", back_populates="channel")

class KOL(Base):
    __tablename__ = "kols"
    
    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String)
    platform_user_id = Column(String, unique=True, index=True)
    name = Column(String)
    category = Column(String)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    messages = relationship("Message", back_populates="kol")

class Attachment(Base):
    __tablename__ = 'attachments'
    
    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey('messages.id', ondelete='CASCADE'), nullable=True)
    filename = Column(String)
    content_type = Column(String)
    file_data = Column(LargeBinary)
    created_at = Column(DateTime, default=datetime.now)
    
    message = relationship("Message", back_populates="attachments")

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True)
    platform_message_id = Column(String, unique=True, nullable=False)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    kol_id = Column(Integer, ForeignKey("kols.id"))
    content = Column(String)
    embeds = Column(JSON)
    referenced_message_id = Column(String)
    referenced_content = Column(String)
    created_at = Column(DateTime)
    
    channel = relationship("Channel", back_populates="messages")
    kol = relationship("KOL", back_populates="messages")
    attachments = relationship("Attachment", back_populates="message", cascade="all, delete-orphan") 

class UnreadMessage(Base):
    __tablename__ = "unread_messages"
    
    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    last_read_message_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    unread_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    channel = relationship("Channel", backref="unread_messages")
    last_read_message = relationship("Message") 