from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Depends, Body
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime
from pydantic import BaseModel
import logging
import json
import asyncio

from ..database import SessionLocal, get_db
from ..models.base import Message, KOL, Platform, Channel
from ..services.discord_client import DiscordClient

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