from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import desc
import logging
from pydantic import BaseModel
import traceback

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

class ChannelForwardingUpdate(BaseModel):
    is_forwarding: bool

class ChannelActiveUpdate(BaseModel):
    is_active: bool

class ThreadSyncRequest(BaseModel):
    message_count: Optional[int] = 100

@router.get("/channels")
async def get_channels(
    guild_id: Optional[str] = None,
    kol_category: Optional[str] = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db)
):
    """获取频道列表，支持按服务器ID和KOL分类筛选"""
    try:
        query = db.query(Channel)
        
        if guild_id:
            query = query.filter(Channel.guild_id == guild_id)
        
        if kol_category:
            query = query.filter(Channel.kol_category == kol_category)
            
        if not include_inactive:
            query = query.filter(Channel.is_active == True)
            
        channels = query.order_by(desc(Channel.created_at)).all()
        
        result = []
        for channel in channels:
            channel_data = {
                "id": channel.id,
                "platform_channel_id": channel.platform_channel_id,
                "name": channel.name,
                "guild_id": channel.guild_id,
                "guild_name": channel.guild_name,
                "is_forwarding": channel.is_forwarding,
                "is_active": channel.is_active,
                "type": channel.type,
                "parent_id": channel.parent_id,
                "position": channel.position,
                "category_name": channel.category_name,
                "created_at": channel.created_at.isoformat() if channel.created_at else None,
                "updated_at": channel.updated_at.isoformat() if channel.updated_at else None
            }
            result.append(channel_data)
        
        return result
        
    except Exception as e:
        logger.error(f"Error in get_channels: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/channels/sync")
async def sync_channels(db: Session = Depends(get_db)):
    """同步Discord中的频道列表和论坛帖子到数据库"""
    result = await get_discord_client().sync_channels_to_db(db)
    return result

@router.post("/channels/sync-threads")
async def sync_all_threads(request: ThreadSyncRequest = None, db: Session = Depends(get_db)):
    """同步所有论坛帖子"""
    try:
        thread_count = 0
        message_count = request.message_count if request else 100
        # 获取所有论坛频道
        forum_channels = db.query(Channel).filter(
            Channel.type == 15,  # Discord论坛频道类型
            Channel.is_active == True
        ).all()
        
        for channel in forum_channels:
            try:
                # 获取帖子列表
                threads = await get_discord_client().get_forum_threads(channel.platform_channel_id)
                for thread_data in threads:
                    # 为每个帖子创建新的数据库会话
                    thread_db = SessionLocal()
                    try:
                        thread_id = thread_data.get('id')
                        thread_name = thread_data.get('name', '未知帖子')
                        is_archived = thread_data.get('archived', False)
                        
                        # 创建或更新帖子作为子频道
                        thread = thread_db.query(Channel).filter(
                            Channel.platform_channel_id == str(thread_id)
                        ).first()
                        
                        if not thread:
                            thread = Channel(
                                platform_channel_id=str(thread_id),
                                name=thread_name,
                                guild_id=channel.guild_id,
                                guild_name=channel.guild_name,
                                type=11,  # Discord 帖子类型
                                parent_id=str(channel.platform_channel_id),
                                category_name=channel.name,
                                is_active=False if is_archived else True,
                                position=0,
                                owner_id=thread_data.get('owner_id')
                            )
                            thread_db.add(thread)
                            thread_count += 1
                        else:
                            thread.name = thread_name
                            if is_archived:  # 如果是已归档帖子，直接设置为False
                                thread.is_active = False
                        
                        thread_db.commit()

                        # 同步帖子的历史消息
                        if not is_archived and message_count > 0:
                            messages = await get_discord_client().get_channel_messages(thread_id, limit=message_count)
                            # 为每条消息创建新的数据库会话
                            for msg in messages:
                                msg_db = SessionLocal()
                                try:
                                    await get_discord_client().store_message(msg, msg_db)
                                except Exception as e:
                                    message_logger.error(f"存储消息失败: {str(e)}")
                                    msg_db.rollback()
                                finally:
                                    msg_db.close()
                    except Exception as e:
                        message_logger.error(f"处理帖子 {thread_name} 失败: {str(e)}")
                        thread_db.rollback()
                    finally:
                        thread_db.close()
                
                message_logger.info(f"论坛 {channel.name} 同步了 {len(threads)} 个帖子")
            except Exception as e:
                message_logger.error(f"同步论坛 {channel.name} 帖子失败: {str(e)}")
                continue
        
        return {
            "message": f"Successfully synced {thread_count} threads",
            "thread_count": thread_count
        }
        
    except Exception as e:
        logger.error(f"同步论坛帖子失败: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

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

@router.post("/channels/{channel_id}/forwarding")
async def update_channel_forwarding(
    channel_id: str,
    update: ChannelForwardingUpdate,
    db: Session = Depends(get_db)
):
    """更新频道的转发状态"""
    channel = db.query(Channel).filter(Channel.platform_channel_id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    channel.is_forwarding = update.is_forwarding
    db.commit()
    
    return {"status": "success", "is_forwarding": channel.is_forwarding}

@router.post("/channels/{channel_id}/active")
async def update_channel_active(
    channel_id: str,
    update: ChannelActiveUpdate,
    db: Session = Depends(get_db)
):
    """更新频道的监听状态"""
    channel = db.query(Channel).filter(Channel.platform_channel_id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    channel.is_active = update.is_active
    db.commit()
    
    return {"status": "success", "is_active": channel.is_active} 