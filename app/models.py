from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, JSON, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base
import enum

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    TRADER = "trader"
    VIEWER = "viewer"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(Enum(UserRole), default=UserRole.VIEWER)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class Platform(str, enum.Enum):
    TELEGRAM = "telegram"
    DISCORD = "discord"

class KOL(Base):
    __tablename__ = "kols"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    platform = Column(Enum(Platform))
    platform_user_id = Column(String, index=True)
    description = Column(String, nullable=True)
    performance_score = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    messages = relationship("Message", back_populates="kol")

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    kol_id = Column(Integer, ForeignKey("kols.id"))
    platform = Column(Enum(Platform))
    platform_message_id = Column(String, index=True)
    content = Column(String)
    raw_content = Column(JSON)
    referenced_message_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    kol = relationship("KOL", back_populates="messages")
    trade_signals = relationship("TradeSignal", back_populates="message")

class SignalType(str, enum.Enum):
    ENTRY = "entry"
    EXIT = "exit"
    UPDATE = "update"

class TradeSignal(Base):
    __tablename__ = "trade_signals"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"))
    signal_type = Column(Enum(SignalType))
    symbol = Column(String, index=True)
    entry_price = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    leverage = Column(Float, default=1.0)
    direction = Column(String)  # LONG or SHORT
    status = Column(String)  # PENDING, EXECUTED, CANCELLED
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    message = relationship("Message", back_populates="trade_signals")
    orders = relationship("Order", back_populates="trade_signal")

class RiskRule(Base):
    __tablename__ = "risk_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    description = Column(String, nullable=True)
    rule_type = Column(String)  # LEVERAGE, POSITION_SIZE, etc.
    parameters = Column(JSON)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    EXECUTED = "executed"
    CANCELLED = "cancelled"
    FAILED = "failed"

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    trade_signal_id = Column(Integer, ForeignKey("trade_signals.id"))
    order_type = Column(String)  # MARKET, LIMIT, etc.
    symbol = Column(String, index=True)
    quantity = Column(Float)
    price = Column(Float)
    status = Column(Enum(OrderStatus))
    execution_details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    trade_signal = relationship("TradeSignal", back_populates="orders") 