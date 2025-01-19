from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc

from ..database import SessionLocal, get_db
from ..models.base import Channel, KOL, KOLCategory
from ..services.discord_client import DiscordClient

router = APIRouter()
discord_client = DiscordClient()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/channels")
async def get_channels(
    guild_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    kol_category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取频道列表，支持按服务器ID、激活状态和KOL分类筛选"""
    query = db.query(Channel)
    
    if guild_id:
        query = query.filter(Channel.guild_id == guild_id)
    if is_active is not None:
        query = query.filter(Channel.is_active == is_active)
    if kol_category:
        query = query.filter(Channel.kol_category == kol_category)
        
    channels = query.order_by(desc(Channel.created_at)).all()
    
    return [
        {
            "id": channel.id,
            "platform_channel_id": channel.platform_channel_id,
            "name": channel.name,
            "guild_id": channel.guild_id,
            "guild_name": channel.guild_name,
            "category_id": channel.category_id,
            "category_name": channel.category_name,
            "is_active": channel.is_active,
            "kol_category": channel.kol_category.value if channel.kol_category else None,
            "kol_name": channel.kol_name,
            "created_at": channel.created_at.isoformat() if channel.created_at else None,
            "updated_at": channel.updated_at.isoformat() if channel.updated_at else None
        }
        for channel in channels
    ]

@router.post("/channels/sync")
async def sync_channels(db: Session = Depends(get_db)):
    """同步Discord中的频道列表到数据库"""
    await discord_client.sync_channels_to_db(db)
    return {"message": "Channels synced successfully"}

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