from sqlalchemy import Column, Integer, String, DateTime, JSON, Text, types
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
    created_at = Column(DateTime(timezone=True), 
                       server_default=func.now(),
                       nullable=False)
    
    def __repr__(self):
        return f"<AIMessage(id={self.id}, channel_id='{self.channel_id}', created_at='{self.created_at}')>" 