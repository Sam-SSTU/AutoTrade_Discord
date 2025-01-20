from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Depends, Body, Response, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime
from pydantic import BaseModel
import logging
import json
import asyncio
import traceback
import os

from ..database import SessionLocal, get_db
from ..models.base import Message, KOL, Platform, Channel, Attachment, UnreadMessage
from ..services.discord_client import DiscordClient
from ..services.file_utils import FileHandler

router = APIRouter()
logger = logging.getLogger(__name__)
discord_client = DiscordClient()

class MessageCreate(BaseModel):
    content: str
    author_name: str
    channel_id: str

class SyncHistoryRequest(BaseModel):
    message_count: int

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/messages")
async def get_messages(
    channel_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """获取消息列表，支持分页"""
    try:
        query = db.query(Message).join(Channel).join(KOL)
        
        if channel_id is not None:
            # 使用platform_channel_id进行过滤
            query = query.filter(Channel.platform_channel_id == channel_id)
            # 检查是否找到频道
            channel = db.query(Channel).filter(Channel.platform_channel_id == channel_id).first()
            if channel:
                logger.info(f"找到频道: {channel.name} (ID: {channel.platform_channel_id})")
            else:
                logger.error(f"找不到Discord频道ID为 {channel_id} 的频道")
                return {"total": 0, "page": page, "per_page": per_page, "messages": []}
            
        # 检查是否有任何消息
        total = query.count()
        logger.info(f"找到 {total} 条消息")
        
        # 添加排序和分页
        messages = query.order_by(desc(Message.created_at))\
            .offset((page - 1) * per_page)\
            .limit(per_page)\
            .all()
            
        logger.info(f"当前页面获取到 {len(messages)} 条消息")
        
        if len(messages) > 0:
            # 输出第一条消息的详细信息作为样本
            sample_msg = messages[0]
            logger.info(f"样本消息: ID={sample_msg.id}, "
                       f"platform_message_id={sample_msg.platform_message_id}, "
                       f"channel_id={sample_msg.channel.platform_channel_id}, "
                       f"content={sample_msg.content[:100]}")
            
        # 转换消息格式，包含附件信息
        result = []
        for msg in messages:
            try:
                attachments = []
                for attachment in msg.attachments:
                    attachments.append({
                        'id': attachment.id,
                        'filename': attachment.filename,
                        'content_type': attachment.content_type,
                        'url': f'/api/messages/attachments/{attachment.id}'
                    })
                    
                result.append({
                    'id': msg.id,
                    'platform_message_id': msg.platform_message_id,
                    'channel_id': msg.channel.platform_channel_id,  # 使用Discord的channel ID
                    'content': msg.content,
                    'embeds': json.loads(msg.embeds) if msg.embeds else [],
                    'attachments': attachments,
                    'referenced_message_id': msg.referenced_message_id,
                    'referenced_content': msg.referenced_content,
                    'created_at': msg.created_at.isoformat(),
                    'author': {
                        'id': msg.kol.id,
                        'name': msg.kol.name,
                        'platform_user_id': msg.kol.platform_user_id
                    }
                })
            except Exception as e:
                logger.error(f"处理消息 {msg.id} 时出错: {str(e)}")
                logger.error(f"错误详情: {traceback.format_exc()}")
                continue
            
        logger.info(f"成功处理 {len(result)} 条消息")
        
        return {
            'total': total,
            'page': page,
            'per_page': per_page,
            'messages': result
        }
        
    except Exception as e:
        logger.error(f"获取消息列表时出错: {str(e)}")
        logger.error(f"错误详情: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/messages")
async def create_message(
    message_create: MessageCreate,
    db: Session = Depends(get_db)
):
    """创建新消息"""
    try:
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
            channel_id=channel.id,
            kol_id=kol.id,
            created_at=datetime.now()
        )
        
        db.add(message)
        db.commit()
        db.refresh(message)
        
        # Increment unread count
        await increment_unread_count(channel.id, db)
        
        # 广播新消息通知
        discord_client.broadcast_message({
            'type': 'new_message',
            'channel_id': channel.platform_channel_id,
            'channel_name': channel.name,
            'author_name': kol.name,
            'content': message.content,
            'created_at': message.created_at.isoformat()
        })
        
        return {
            "id": message.id,
            "content": message.content,
            "author_name": kol.name,
            "channel_id": channel.platform_channel_id,
            "created_at": message.created_at.isoformat(),
            "referenced_message_id": None,
            "referenced_content": None
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating message: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/messages/{message_id}")
async def delete_message(message_id: int, db: Session = Depends(get_db)):
    """删除指定消息"""
    try:
        message = db.query(Message).filter(Message.id == message_id).first()
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        
        # 先更新 unread_messages 表中引用这条消息的记录
        unread_messages = db.query(UnreadMessage).filter(
            UnreadMessage.last_read_message_id == message_id
        ).all()
        
        for unread in unread_messages:
            # 获取该频道的最新消息（除了要删除的消息）
            latest_message = db.query(Message).filter(
                Message.channel_id == unread.channel_id,
                Message.id != message_id
            ).order_by(desc(Message.created_at)).first()
            
            unread.last_read_message_id = latest_message.id if latest_message else None
        
        db.commit()
        
        # 删除消息的附件
        db.query(Attachment).filter(Attachment.message_id == message_id).delete()
        db.commit()
        
        # 最后删除消息
        db.delete(message)
        db.commit()
        
        return {"status": "success"}
    except Exception as e:
        db.rollback()
        logger.error(f"删除消息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/messages/sync-history")
async def sync_history_messages(
    request: SyncHistoryRequest,
    db: Session = Depends(get_db)
):
    """同步所有频道的历史消息"""
    if request.message_count <= 0:
        raise HTTPException(status_code=400, detail="Message count must be positive")

    total_messages = 0
    channel_count = 0
    errors = []
    
    # 获取所有频道的基本信息
    channels = [(channel.platform_channel_id, channel.name) for channel in db.query(Channel).all()]
    
    # 创建信号量限制并发数
    semaphore = asyncio.Semaphore(3)  # 降低并发数到3
    
    async def process_channel(channel_id: str, channel_name: str):
        nonlocal total_messages, channel_count
        # 为每个频道创建新的数据库会话
        channel_db = SessionLocal()
        try:
            async with semaphore:
                # 获取历史消息
                messages = await discord_client.get_channel_messages(
                    channel_id,
                    limit=request.message_count
                )
                
                if not messages:
                    logger.info(f"频道 {channel_name} 没有历史消息")
                    return
                
                # 存储消息
                success_count = 0
                for message_data in messages:
                    try:
                        # 使用频道专用的数据库会话
                        await discord_client.store_message(message_data, channel_db)
                        success_count += 1
                    except Exception as e:
                        logger.error(f"存储消息失败: {str(e)}")
                        errors.append(f"频道 {channel_name} 消息 {message_data.get('id')} 存储失败: {str(e)}")
                        # 回滚当前消息的事务
                        channel_db.rollback()
                        continue
                
                if success_count > 0:
                    total_messages += success_count
                    channel_count += 1
                    logger.info(f"频道 {channel_name} 成功同步 {success_count} 条消息")
                    
        except Exception as e:
            logger.error(f"处理频道失败: {str(e)}")
            errors.append(f"处理频道 {channel_name} 失败: {str(e)}")
            channel_db.rollback()
        finally:
            # 确保关闭数据库会话
            channel_db.close()
    
    # 并发处理所有频道
    tasks = [process_channel(channel_id, channel_name) for channel_id, channel_name in channels]
    await asyncio.gather(*tasks)
    
    # 添加详细的结果日志
    logger.info(f"同步完成: 处理了 {channel_count} 个频道，共 {total_messages} 条消息")
    if errors:
        logger.warning(f"发生了 {len(errors)} 个错误")
    
    return {
        "total_messages": total_messages,
        "channel_count": channel_count,
        "errors": errors if errors else None
    }

@router.post("/messages/clear-all")
async def clear_all_messages(db: Session = Depends(get_db)):
    """清除数据库中的所有消息"""
    try:
        # 获取消息总数
        message_count = db.query(Message).count()
        
        # 删除所有消息
        db.query(Message).delete()
        db.commit()
        
        return {
            "deleted_count": message_count,
            "status": "success"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/messages/attachments/{attachment_id}")
async def get_attachment(attachment_id: int, db: Session = Depends(get_db)):
    """获取附件内容"""
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
        
    return Response(
        content=attachment.file_data,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{attachment.filename}"'
        }
    )

@router.post("/debug/log")
async def debug_log(data: dict = Body(...)):
    """Handle debug logs from frontend"""
    log_type = data.get('type', 'unknown')
    log_data = data.get('data', {})
    
    if log_type == 'scroll_debug':
        logger.info(f"Scroll Debug: {log_data}")
    elif log_type == 'load_more_triggered':
        logger.info(f"Load More Triggered: {log_data}")
    else:
        logger.info(f"Debug Log ({log_type}): {log_data}")
    
    return {"status": "ok"}

@router.get("/messages/unread-counts")
async def get_unread_counts(db: Session = Depends(get_db)):
    """Get unread message counts for all channels"""
    unread_messages = db.query(UnreadMessage).all()
    return {
        str(unread.channel.platform_channel_id): unread.unread_count 
        for unread in unread_messages
    }

@router.post("/messages/mark-channel-read/{channel_id}")
async def mark_channel_read(channel_id: str, db: Session = Depends(get_db)):
    """Mark all messages in a channel as read"""
    channel = db.query(Channel).filter(Channel.platform_channel_id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
        
    # Get the latest message in the channel
    latest_message = db.query(Message).filter(Message.channel_id == channel.id)\
        .order_by(desc(Message.created_at)).first()
        
    # Update or create unread message record
    unread = db.query(UnreadMessage).filter(UnreadMessage.channel_id == channel.id).first()
    if unread:
        unread.last_read_message_id = latest_message.id if latest_message else None
        unread.unread_count = 0
    else:
        unread = UnreadMessage(
            channel_id=channel.id,
            last_read_message_id=latest_message.id if latest_message else None,
            unread_count=0
        )
        db.add(unread)
    
    db.commit()
    return {"status": "success"}

@router.post("/messages/mark-all-read")
async def mark_all_read(db: Session = Depends(get_db)):
    """Mark all messages in all channels as read"""
    db.query(UnreadMessage).update({"unread_count": 0})
    db.commit()
    return {"status": "success"}

# Update the existing create_message function to increment unread count
async def increment_unread_count(channel_id: int, db: Session):
    """Helper function to increment unread count for a channel"""
    unread = db.query(UnreadMessage).filter(UnreadMessage.channel_id == channel_id).first()
    if unread:
        unread.unread_count += 1
    else:
        unread = UnreadMessage(channel_id=channel_id, unread_count=1)
        db.add(unread)
    db.commit()

@router.get("/ping")
async def ping():
    """Check backend connectivity"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@router.get("/unread-counts")
async def get_unread_counts(db: Session = Depends(get_db)):
    """Get unread message counts for all channels"""
    try:
        unread_counts = {}
        unread_messages = db.query(UnreadMessage).all()
        
        for unread in unread_messages:
            channel = db.query(Channel).filter(Channel.id == unread.channel_id).first()
            if channel:
                unread_counts[channel.platform_channel_id] = unread.unread_count
        
        return unread_counts
    except Exception as e:
        logger.error(f"Error getting unread counts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 