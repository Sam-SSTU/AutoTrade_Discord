from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import desc
import logging

from ..database import SessionLocal, get_db
from ..models.base import Channel, KOL, KOLCategory, Message, UnreadMessage, Attachment
from ..services.discord_client import DiscordClient

router = APIRouter()
message_logger = logging.getLogger("Message Logs")
logger = logging.getLogger(__name__)

# Create a single instance of DiscordClient
_discord_client = None

def get_discord_client():
    global _discord_client
    if _discord_client is None:
        _discord_client = DiscordClient()
    return _discord_client

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/channels")
async def get_channels(
    guild_id: Optional[str] = None,
    is_active: Optional[bool] = True,
    kol_category: Optional[str] = None,
    include_inactive: Optional[bool] = False,
    db: Session = Depends(get_db)
):
    """获取频道列表，支持按服务器ID、激活状态和KOL分类筛选"""
    try:
        query = db.query(Channel)
        
        # 打印初始查询条件
        print(f"Query params: guild_id={guild_id}, is_active={is_active}, include_inactive={include_inactive}")
        
        if guild_id:
            query = query.filter(Channel.guild_id == guild_id)
        
        # 修改活跃状态过滤逻辑
        if not include_inactive:
            query = query.filter(Channel.is_active == True)
        
        if kol_category:
            query = query.filter(Channel.kol_category == kol_category)
            
        # 打印SQL查询语句
        print(f"SQL Query: {query}")
        
        channels = query.order_by(desc(Channel.created_at)).all()
        
        # 打印查询结果
        print(f"Found {len(channels)} channels")
        for channel in channels:
            print(f"Channel: {channel.name} (ID: {channel.platform_channel_id}, Active: {channel.is_active})")
        
        result = []
        for channel in channels:
            channel_data = {
                "id": channel.id,
                "platform_channel_id": channel.platform_channel_id,
                "name": channel.name,
                "guild_id": channel.guild_id,
                "guild_name": channel.guild_name,
                "is_active": channel.is_active,
                "type": channel.type,
                "parent_id": channel.parent_id,
                "position": channel.position,
                "category_name": channel.category_name,
                "created_at": channel.created_at.isoformat() if channel.created_at else None,
                "updated_at": channel.updated_at.isoformat() if channel.updated_at else None
            }
            result.append(channel_data)
            
            # 调试日志
            if channel.type == 4:  # 如果是分类
                print(f"Found category: {channel.name} (ID: {channel.platform_channel_id})")
            elif channel.parent_id:  # 如果属于某个分类
                print(f"Channel {channel.name} belongs to category: {channel.parent_id}")
            else:
                print(f"Uncategorized channel: {channel.name}")
        
        # 打印返回结果
        print(f"Returning {len(result)} channels")
        return result
        
    except Exception as e:
        print(f"Error in get_channels: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/channels/sync")
async def sync_channels(db: Session = Depends(get_db)):
    """同步Discord中的频道列表到数据库"""
    result = await get_discord_client().sync_channels_to_db(db)
    return result

@router.post("/channels/{channel_id}/activate")
async def activate_channel(channel_id: int, db: Session = Depends(get_db)):
    """激活指定频道的监听"""
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
        
    channel.is_active = True
    db.commit()
    return {"message": f"Channel {channel.name} activated"}

@router.post("/channels/{channel_id}/deactivate")
async def deactivate_channel(channel_id: int, db: Session = Depends(get_db)):
    """停用指定频道的监听"""
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
        
    channel.is_active = False
    db.commit()
    return {"message": f"Channel {channel.name} deactivated"}

@router.post("/channels/{channel_id}/category")
async def update_channel_category(
    channel_id: int,
    category: str,
    db: Session = Depends(get_db)
):
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    try:
        channel.kol_category = KOLCategory(category) if category else None
        db.commit()
        return {"message": "Channel category updated successfully"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid category")

@router.post("/reset")
async def reset_channels(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """重置所有频道"""
    try:
        # First delete all unread_messages records
        db.query(UnreadMessage).delete()
        db.commit()
        
        # Then delete all attachments
        db.query(Attachment).delete()
        db.commit()
        
        # Now delete all messages
        db.query(Message).delete()
        db.commit()
        
        # Finally delete all channels
        db.query(Channel).delete()
        db.commit()
        
        return {"message": "频道重置成功"}
        
    except Exception as e:
        db.rollback()
        logger.error(f"重置频道失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        ) 