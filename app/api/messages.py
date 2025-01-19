from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime

from ..database import SessionLocal
from ..models.base import Message, KOL, Platform
from ..services.discord_client import DiscordClient

router = APIRouter()

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
    is_reply: Optional[bool] = None,
    page: int = Query(1, gt=0),
    limit: int = Query(20, gt=0)
):
    """获取消息列表，支持分页和过滤"""
    query = db.query(Message).join(KOL)
    
    # 应用过滤条件
    if channel_id:
        query = query.filter(Message.channel_id == channel_id)
    if author_name:
        query = query.filter(KOL.name.ilike(f"%{author_name}%"))
    if is_reply is not None:
        query = query.filter(Message.referenced_message_id.isnot(None) if is_reply else Message.referenced_message_id.is_(None))
    
    # 计算分页
    offset = (page - 1) * limit
    
    # 获取消息
    messages = query.order_by(desc(Message.created_at)).offset(offset).limit(limit).all()
    
    # 格式化响应
    return [
        {
            "id": message.id,
            "content": message.content,
            "author_name": message.kol.name,
            "channel_id": message.channel_id,
            "created_at": message.created_at.isoformat(),
            "referenced_message_id": message.referenced_message_id,
            "referenced_content": message.referenced_content
        }
        for message in messages
    ]

@router.delete("/messages/{message_id}")
async def delete_message(message_id: int, db: Session = Depends(get_db)):
    """删除指定消息"""
    message = db.query(Message).filter(Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    db.delete(message)
    db.commit()
    return {"status": "success"}

@router.get("/blacklist")
async def get_blacklist():
    """获取黑名单列表"""
    client = DiscordClient()
    return client.get_blacklist()

@router.post("/blacklist/{channel_id}")
async def add_to_blacklist(channel_id: str):
    """添加频道到黑名单"""
    client = DiscordClient()
    client.add_to_blacklist(channel_id, "Manually added to blacklist")
    return {"status": "success"}

@router.delete("/blacklist/{channel_id}")
async def remove_from_blacklist(channel_id: str):
    """从黑名单中移除频道"""
    client = DiscordClient()
    client.remove_from_blacklist(channel_id)
    return {"status": "success"} 