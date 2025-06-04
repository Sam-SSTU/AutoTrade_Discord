from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import logging
import asyncio
import json
import traceback

from ..models.base import Message, KOL, Platform, Channel, UnreadMessage
from ..database import SessionLocal
from .discord_client import DiscordClient
from .message_utils import extract_message_content

# 创建Message Logs记录器
message_logger = logging.getLogger("Message Logs")
logger = logging.getLogger(__name__)

class MessageHandler:
    def __init__(self):
        self.discord_client = DiscordClient()
        self._monitoring_task: Optional[asyncio.Task] = None
        self._db: Session = SessionLocal()

    async def start(self):
        """启动消息监控服务"""
        message_logger.info("开始监听消息")
        self._monitoring_task = asyncio.create_task(self._monitor_messages())
        
    async def stop(self):
        """停止消息监控服务"""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                message_logger.info("停止监听消息")
            
        if hasattr(self.discord_client, 'close'):
            await self.discord_client.close()
            
        if not self._db.is_active:
            self._db.close()
            
        message_logger.info("消息监听服务已停止")
        
    async def _monitor_messages(self):
        """监控消息的主循环"""
        try:
            await self.discord_client.start_monitoring(self.handle_discord_message)
        except asyncio.CancelledError:
            message_logger.info("停止监听消息")
            raise
        except Exception as e:
            message_logger.error(f"监听消息出错: {str(e)}")
            raise

    async def handle_discord_message(self, message_data: Dict[str, Any]):
        """处理接收到的Discord消息"""
        try:
            # 验证消息数据
            if not message_data:
                return
                
            # 记录关键信息
            content = message_data.get('content', '')
            author = message_data.get('author', {})
            username = f"{author.get('username')}#{author.get('discriminator')}"
            channel_id = str(message_data.get('channel_id'))
            
            # 获取频道信息
            channel = self._db.query(Channel).filter(
                Channel.platform_channel_id == channel_id
            ).first()
            
            # 如果是新的论坛帖子，需要先创建或更新帖子记录
            if message_data.get('thread'):
                thread_data = message_data['thread']
                thread_id = str(thread_data.get('id'))
                thread_name = thread_data.get('name', '未知帖子')
                parent_id = str(thread_data.get('parent_id'))
                
                # 查找父级论坛频道
                parent_channel = self._db.query(Channel).filter(
                    Channel.platform_channel_id == parent_id
                ).first()
                
                if parent_channel:
                    # 创建或更新帖子记录
                    thread = self._db.query(Channel).filter(
                        Channel.platform_channel_id == thread_id
                    ).first()
                    
                    if not thread:
                        thread = Channel(
                            platform_channel_id=thread_id,
                            name=thread_name,
                            guild_id=parent_channel.guild_id,
                            guild_name=parent_channel.guild_name,
                            type=11,  # Discord 帖子类型
                            parent_id=parent_id,
                            is_active=True,
                            position=0
                        )
                        self._db.add(thread)
                        self._db.commit()
                        message_logger.info(f"创建新帖子: {thread_name}")
                    
                    # 更新 channel 为新创建的帖子
                    channel = thread
            
            # 简化的日志输出
            message_logger.info(f"{username}发了消息: {content or '[空消息]'}")
            
            # 使用 discord_client 的方法存储消息（已包含所有必要的数据库操作）
            await self.discord_client.store_message(message_data, self._db)
            
            # 返回消息处理结果（如果需要）
            if channel:
                return {
                    'type': 'new_message',
                    'channel_id': channel.platform_channel_id,
                    'channel_name': channel.name,
                    'author_name': username,
                    'content': content,
                    'created_at': datetime.now().isoformat()
                }
            
        except Exception as e:
            message_logger.error(f"处理消息出错: {str(e)}")
            message_logger.error(traceback.format_exc())
            self._db.rollback()
            raise

    def _get_or_create_kol(self, author_data: Dict[str, Any]) -> KOL:
        """获取或创建KOL记录"""
        kol = self._db.query(KOL).filter(
            KOL.platform == Platform.DISCORD.value,
            KOL.platform_user_id == str(author_data["id"])
        ).first()
        
        if not kol:
            kol = KOL(
                name=f"{author_data['username']}#{author_data.get('discriminator', '0')}",
                platform=Platform.DISCORD.value,
                platform_user_id=str(author_data["id"]),
                is_active=True
            )
            self._db.add(kol)
            self._db.commit()
        
        return kol

    def _get_or_create_channel(self, channel_data: Dict[str, Any]) -> Channel:
        """获取或创建Channel记录"""
        channel = self._db.query(Channel).filter(
            Channel.platform_channel_id == str(channel_data["id"])
        ).first()
        
        if not channel:
            channel = Channel(
                platform_channel_id=str(channel_data["id"]),
                name=channel_data.get("name", "Unknown"),
                guild_id=str(channel_data["guild_id"]),
                guild_name=channel_data.get("guild_name", "Unknown"),
                is_active=True
            )
            self._db.add(channel)
            self._db.commit()
        
        return channel 