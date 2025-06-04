from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Depends, Body, Response, UploadFile, File
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from datetime import datetime, timezone
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
from ..ai.message_handler import ai_message_handler

router = APIRouter()
logger = logging.getLogger(__name__)
discord_client = DiscordClient()

class MessageCreate(BaseModel):
    content: str
    author_name: str
    channel_id: str

class SyncHistoryRequest(BaseModel):
    message_count: int
    include_threads: bool = False  # 新增参数，控制是否同步论坛帖子

class ChannelReadRequest(BaseModel):
    channel_id: str

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/messages")
async def get_messages(
    channel_id: str,
    page: int = Query(1, gt=0),
    per_page: int = Query(20, gt=0),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """获取频道消息"""
    try:
        channel = db.query(Channel).filter(Channel.platform_channel_id == channel_id).first()
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        
        # 构建查询
        query = db.query(Message).filter(Message.channel_id == channel.id)
        
        # 如果有搜索条件，添加搜索过滤
        if search:
            search_term = f"%{search}%"
            query = query.filter(Message.content.ilike(search_term))
        
        # 按创建时间倒序查询消息
        messages = query.order_by(desc(Message.created_at)).offset(
            (page - 1) * per_page
        ).limit(per_page).all()
        
        return {
            "messages": [{
                "id": message.id,
                "content": message.content,
                "author_name": message.kol.name,
                "created_at": message.created_at.isoformat(),
                "referenced_message_id": message.referenced_message_id,
                "referenced_content": message.referenced_content,
                "attachments": [
                    {
                        "id": attachment.id,
                        "filename": attachment.filename,
                        "content_type": attachment.content_type
                    } for attachment in message.attachments
                ] if message.attachments else []
            } for message in messages],
            "search_term": search,
            "total_found": query.count() if search else None
        }
    except Exception as e:
        logger.error(f"Error getting messages: {str(e)}")
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
                platform_user_id=f"manual_{datetime.now(timezone.utc).timestamp()}",
                is_active=True
            )
            db.add(kol)
            db.commit()
        
        # 创建消息
        message = Message(
            platform_message_id=f"manual_{datetime.now(timezone.utc).timestamp()}",
            content=message_create.content,
            channel_id=channel.id,
            kol_id=kol.id,
            created_at=datetime.now(timezone.utc)  # 使用 now(timezone.utc) 获取纯 UTC 时间
        )
        
        db.add(message)
        db.commit()
        db.refresh(message)
        
        # Increment unread count
        await increment_unread_count(channel.id, db)
        
        # 广播新消息通知
        await discord_client.broadcast_message({
            'type': 'new_message',
            'channel_id': channel.platform_channel_id,
            'channel_name': channel.name,
            'author_name': kol.name,
            'content': message.content,
            'created_at': message.created_at.strftime("%Y-%m-%d %H:%M:%S")  # 格式化为纯时间字符串
        })

        # 如果频道启用了转发，则转发到AI模块
        if channel.is_forwarding:
            # 重新查询以获取完整的关联数据
            message = db.query(Message).options(
                joinedload(Message.channel),
                joinedload(Message.attachments)
            ).filter(Message.id == message.id).first()
            # 存储到AI消息表并广播
            await ai_message_handler.store_message(db, message)
        
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
    channel_messages = 0  # 普通频道消息数
    thread_messages = 0   # 论坛帖子消息数
    channel_count = 0
    thread_count = 0
    errors = []
    
    # 获取所有频道的基本信息
    channels = db.query(Channel).all()
    
    # 创建信号量限制并发数
    semaphore = asyncio.Semaphore(3)

    async def process_channel(channel: Channel):
        nonlocal total_messages, channel_messages, thread_messages, channel_count, thread_count
        # 为每个频道创建新的数据库会话
        channel_db = SessionLocal()
        try:
            async with semaphore:
                # 如果是论坛频道且不需要同步帖子，则跳过
                if channel.type == 15 and not request.include_threads:
                    return

                # 如果是论坛帖子且需要同步帖子
                if channel.type == 11 and request.include_threads:
                    # 获取历史消息
                    messages = await discord_client.get_channel_messages(
                        channel.platform_channel_id,
                        limit=request.message_count
                    )
                    
                    if not messages:
                        logger.info(f"帖子 {channel.name} 没有历史消息")
                        return
                    
                    # 存储消息
                    success_count = 0
                    for message_data in messages:
                        try:
                            await discord_client.store_message(message_data, channel_db)
                            success_count += 1
                        except Exception as e:
                            logger.error(f"存储消息失败: {str(e)}")
                            errors.append(f"帖子 {channel.name} 消息 {message_data.get('id')} 存储失败: {str(e)}")
                            channel_db.rollback()
                            continue
                    
                    if success_count > 0:
                        thread_messages += success_count
                        thread_count += 1
                        logger.info(f"帖子 {channel.name} 成功同步 {success_count} 条消息")
                    return

                # 处理普通频道
                if channel.type not in [4, 15]:  # 排除分类和论坛频道
                    messages = await discord_client.get_channel_messages(
                        channel.platform_channel_id,
                        limit=request.message_count
                    )
                    
                    if not messages:
                        logger.info(f"频道 {channel.name} 没有历史消息")
                        return
                    
                    # 存储消息
                    success_count = 0
                    for message_data in messages:
                        try:
                            await discord_client.store_message(message_data, channel_db)
                            success_count += 1
                        except Exception as e:
                            logger.error(f"存储消息失败: {str(e)}")
                            errors.append(f"频道 {channel.name} 消息 {message_data.get('id')} 存储失败: {str(e)}")
                            channel_db.rollback()
                            continue
                    
                    if success_count > 0:
                        channel_messages += success_count
                        channel_count += 1
                        logger.info(f"频道 {channel.name} 成功同步 {success_count} 条消息")
                
        except Exception as e:
            logger.error(f"处理频道失败: {str(e)}")
            errors.append(f"处理频道 {channel.name} 失败: {str(e)}")
            channel_db.rollback()
        finally:
            # 确保关闭数据库会话
            channel_db.close()

    # 并发处理所有频道
    tasks = [process_channel(channel) for channel in channels]
    await asyncio.gather(*tasks)
    
    # 计算总消息数
    total_messages = channel_messages + thread_messages
    
    # 添加详细的结果日志
    logger.info(f"同步完成: 处理了 {channel_count} 个频道和 {thread_count} 个帖子，共 {total_messages} 条消息")
    if errors:
        logger.warning(f"发生了 {len(errors)} 个错误")
    
    return {
        "total_messages": total_messages,
        "channel_messages": channel_messages,
        "thread_messages": thread_messages,
        "channel_count": channel_count,
        "thread_count": thread_count,
        "errors": errors if errors else None
    }

@router.post("/messages/clear-all")
async def clear_all_messages(db: Session = Depends(get_db)):
    """清除数据库中的所有消息和相关文件"""
    try:
        # Start a transaction
        transaction = db.begin_nested()
        
        try:
            # Get counts before deletion for accurate reporting
            message_count = db.query(Message).count()
            attachment_count = db.query(Attachment).count()
            
            # Delete all unread messages first
            db.query(UnreadMessage).delete(synchronize_session='fetch')
            
            # Delete all attachments
            db.query(Attachment).delete(synchronize_session='fetch')
            
            # Delete all messages
            db.query(Message).delete(synchronize_session='fetch')
            
            # Commit the transaction
            transaction.commit()
            db.commit()  # Commit the outer transaction as well
            
            # Delete physical files after DB transaction succeeds
            storage_dir = os.path.join(os.getcwd(), 'storage')
            if os.path.exists(storage_dir):
                for root, dirs, files in os.walk(storage_dir, topdown=False):
                    for name in files:
                        try:
                            file_path = os.path.join(root, name)
                            if os.path.exists(file_path):
                                os.remove(file_path)
                        except OSError as e:
                            logger.warning(f"Failed to delete file {name}: {str(e)}")
                    for name in dirs:
                        try:
                            dir_path = os.path.join(root, name)
                            if os.path.exists(dir_path):
                                os.rmdir(dir_path)
                        except OSError as e:
                            logger.warning(f"Failed to delete directory {name}: {str(e)}")
                logger.info("已清除所有物理文件")
            
            return {
                "status": "success",
                "deleted_messages": message_count,
                "deleted_attachments": attachment_count,
                "files_cleared": True
            }
            
        except Exception as inner_e:
            # Rollback the nested transaction
            transaction.rollback()
            db.rollback()  # Rollback the outer transaction as well
            raise inner_e
            
    except Exception as e:
        # Rollback the main transaction if needed
        db.rollback()
        logger.error(f"清除数据库失败: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/messages/attachments/{attachment_id}")
async def get_attachment(attachment_id: int, db: Session = Depends(get_db)):
    """获取附件内容"""
    try:
        logger.info(f"Fetching attachment with ID: {attachment_id}")
        attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
        
        if not attachment:
            logger.error(f"Attachment not found: {attachment_id}")
            raise HTTPException(status_code=404, detail="Attachment not found")
        
        if not attachment.file_data:
            logger.error(f"Attachment {attachment_id} has no file data")
            raise HTTPException(status_code=404, detail="Attachment file data not found")
            
        logger.info(f"Successfully retrieved attachment: {attachment.filename} ({attachment.content_type})")
        return Response(
            content=attachment.file_data,
            media_type=attachment.content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{attachment.filename}"'
            }
        )
    except Exception as e:
        logger.error(f"Error retrieving attachment {attachment_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

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
    """获取所有频道的未读消息数"""
    try:
        unread_counts = {}
        channels = db.query(Channel).all()
        
        for channel in channels:
            # 获取该频道的未读消息记录
            unread = db.query(UnreadMessage).filter(UnreadMessage.channel_id == channel.id).first()
            if unread and unread.unread_count > 0:
                unread_counts[channel.platform_channel_id] = unread.unread_count
        
        return unread_counts
    except Exception as e:
        logger.error(f"Error getting unread counts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/messages/mark-channel-read")
async def mark_channel_read(request: ChannelReadRequest, db: Session = Depends(get_db)):
    """标记频道所有消息为已读"""
    try:
        channel = db.query(Channel).filter(Channel.platform_channel_id == request.channel_id).first()
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        
        # 获取频道最新消息
        latest_message = db.query(Message).filter(
            Message.channel_id == channel.id
        ).order_by(desc(Message.created_at)).first()
        
        # 更新或创建未读消息记录
        unread = db.query(UnreadMessage).filter(UnreadMessage.channel_id == channel.id).first()
        if unread:
            unread.unread_count = 0
            if latest_message:
                unread.last_read_message_id = latest_message.id
        else:
            unread = UnreadMessage(
                channel_id=channel.id,
                unread_count=0,
                last_read_message_id=latest_message.id if latest_message else None
            )
            db.add(unread)
        
        db.commit()
        return {"status": "success"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error marking channel as read: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/messages/mark-all-read")
async def mark_all_channels_read(db: Session = Depends(get_db)):
    """标记所有频道的消息为已读"""
    try:
        channels = db.query(Channel).all()
        for channel in channels:
            # 获取该频道的最新消息
            latest_message = db.query(Message).filter(
                Message.channel_id == channel.id
            ).order_by(desc(Message.created_at)).first()
            
            # 更新或创建未读消息记录
            unread = db.query(UnreadMessage).filter(UnreadMessage.channel_id == channel.id).first()
            if unread:
                unread.unread_count = 0
                if latest_message:
                    unread.last_read_message_id = latest_message.id
            else:
                unread = UnreadMessage(
                    channel_id=channel.id,
                    unread_count=0,
                    last_read_message_id=latest_message.id if latest_message else None
                )
                db.add(unread)
        
        db.commit()
        return {"status": "success"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error marking all channels as read: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def increment_unread_count(channel_id: int, db: Session):
    """增加频道的未读消息计数"""
    try:
        unread = db.query(UnreadMessage).filter(UnreadMessage.channel_id == channel_id).first()
        if not unread:
            # 如果没有未读记录，创建新记录
            unread = UnreadMessage(
                channel_id=channel_id,
                unread_count=1,
                last_read_message_id=None  # 初始化时不设置last_read_message_id
            )
            db.add(unread)
        else:
            # 增加未读计数
            unread.unread_count += 1
        
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error incrementing unread count: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ping")
async def ping():
    """Check backend connectivity"""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

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

@router.get("/messages/search")
async def search_messages_global(
    search: str = Query(..., min_length=1),
    page: int = Query(1, gt=0),
    per_page: int = Query(20, gt=0),
    db: Session = Depends(get_db)
):
    """全局搜索消息（包括所有频道和帖子）"""
    try:
        if len(search.strip()) < 1:
            raise HTTPException(status_code=400, detail="Search term must be at least 1 character")
        
        search_term = f"%{search}%"
        
        # 在所有消息中搜索，并关联频道信息
        query = db.query(Message, Channel).join(
            Channel, Message.channel_id == Channel.id
        ).filter(
            Message.content.ilike(search_term)
        ).order_by(desc(Message.created_at))
        
        total_count = query.count()
        
        # 分页查询
        results = query.offset((page - 1) * per_page).limit(per_page).all()
        
        messages = []
        for message, channel in results:
            messages.append({
                "id": message.id,
                "content": message.content,
                "author_name": message.kol.name,
                "created_at": message.created_at.isoformat(),
                "referenced_message_id": message.referenced_message_id,
                "referenced_content": message.referenced_content,
                "channel_id": channel.platform_channel_id,
                "channel_name": channel.name,
                "channel_type": channel.type,  # 用于区分频道类型
                "attachments": [
                    {
                        "id": attachment.id,
                        "filename": attachment.filename,
                        "content_type": attachment.content_type
                    } for attachment in message.attachments
                ] if message.attachments else []
            })
        
        return {
            "messages": messages,
            "search_term": search,
            "total_found": total_count,
            "page": page,
            "per_page": per_page,
            "has_more": len(messages) == per_page
        }
    except Exception as e:
        logger.error(f"Error searching messages: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 