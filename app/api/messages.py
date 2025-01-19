from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Depends, Body
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime
from pydantic import BaseModel
import logging
import json

from ..database import SessionLocal
from ..models.base import Message, KOL, Platform, Channel
from ..services.discord_client import DiscordClient

router = APIRouter()
logger = logging.getLogger(__name__)

class MessageCreate(BaseModel):
    content: str
    author_name: str
    channel_id: str

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/messages")
async def get_messages(
    db: Session = Depends(get_db),
    channel_id: Optional[str] = None,
    author_name: Optional[str] = None,
    page: int = Query(1, gt=0),
    limit: int = Query(20, gt=0)
):
    """获取消息列表，支持分页和过滤"""
    logger.info(f"Getting messages for channel_id: {channel_id}")
    
    query = db.query(Message).join(KOL).join(Channel)
    
    # 应用过滤条件
    if channel_id:
        logger.info(f"Filtering by channel_id: {channel_id}")
        query = query.filter(Channel.platform_channel_id == channel_id)
    if author_name:
        logger.info(f"Filtering by author_name: {author_name}")
        query = query.filter(KOL.name.ilike(f"%{author_name}%"))
    
    # 计算总数
    total_count = query.count()
    
    # 计算分页
    offset = (page - 1) * limit
    logger.info(f"Pagination: page={page}, limit={limit}, offset={offset}")
    
    # 获取消息并按时间倒序排列
    messages = query.order_by(desc(Message.created_at)).offset(offset).limit(limit).all()
    logger.info(f"Found {len(messages)} messages")
    
    # 格式化响应
    formatted_messages = []
    for message in messages:
        try:
            # 添加调试日志
            logger.debug(f"Processing message {message.id}, raw content: {message.content!r}")
            
            # 处理附件和嵌入内容
            try:
                attachments = message.attachments if isinstance(message.attachments, list) else json.loads(message.attachments or '[]')
                embeds = message.embeds if isinstance(message.embeds, list) else json.loads(message.embeds or '[]')
            except json.JSONDecodeError:
                logger.error(f"Error decoding JSON for message {message.id}")
                attachments = []
                embeds = []
            
            # 确保content不为None
            content = message.content
            if content is None:
                content = ""
                logger.debug(f"Message {message.id} has None content, setting to empty string")
            
            formatted_message = {
                "id": message.id,
                "content": content,
                "author_name": message.kol.name if message.kol else "Unknown",
                "channel_name": message.channel.name if message.channel else "Unknown",
                "channel_id": message.channel.platform_channel_id,
                "created_at": message.created_at.isoformat() if message.created_at else None,
                "referenced_message_id": message.referenced_message_id,
                "referenced_content": message.referenced_content,
                "attachments": attachments,
                "embeds": embeds
            }
            formatted_messages.append(formatted_message)
            logger.debug(f"Formatted message: {formatted_message}")
        except Exception as e:
            logger.error(f"Error formatting message {message.id}: {str(e)}")
            continue
    
    logger.info(f"Returning {len(formatted_messages)} formatted messages")
    logger.debug(f"First message content: {formatted_messages[0]['content'] if formatted_messages else 'No messages'}")
    
    return {
        "messages": formatted_messages,
        "total": total_count,
        "page": page,
        "has_more": offset + len(messages) < total_count
    }

@router.post("/messages")
async def create_message(
    message_create: MessageCreate,
    db: Session = Depends(get_db)
):
    """创建新消息"""
    # 获取Channel
    channel = db.query(Channel).filter(
        Channel.platform_channel_id == message_create.channel_id
    ).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    # 获取或创建KOL
    kol = db.query(KOL).filter(KOL.name == message_create.author_name).first()
    if not kol:
        kol = KOL(
            name=message_create.author_name,
            platform=Platform.DISCORD.value,
            platform_user_id=f"manual_{datetime.now().timestamp()}",
            is_active=True
        )
        db.add(kol)
        db.commit()
    
    # 创建消息
    message = Message(
        platform_message_id=f"manual_{datetime.now().timestamp()}",
        content=message_create.content,
        channel_id=channel.id,  # 使用数据库的channel ID
        kol_id=kol.id,
        created_at=datetime.now()
    )
    
    db.add(message)
    db.commit()
    db.refresh(message)
    
    return {
        "id": message.id,
        "content": message.content,
        "author_name": kol.name,
        "channel_id": channel.platform_channel_id,  # 返回Discord的channel ID
        "created_at": message.created_at.isoformat(),
        "referenced_message_id": None,
        "referenced_content": None
    }

@router.delete("/messages/{message_id}")
async def delete_message(message_id: int, db: Session = Depends(get_db)):
    """删除指定消息"""
    message = db.query(Message).filter(Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    db.delete(message)
    db.commit()
    return {"status": "success"} 