from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import logging
import asyncio

from ..models import Message, KOL, Platform
from ..database import SessionLocal
from .discord_client import DiscordClient

logger = logging.getLogger(__name__)

class MessageHandler:
    def __init__(self):
        self.discord_client = DiscordClient()
        self._monitoring_task: Optional[asyncio.Task] = None
        self._db: Session = SessionLocal()

    async def start(self):
        """启动消息监控服务"""
        logger.info("Starting message monitoring service")
        self._monitoring_task = asyncio.create_task(self._monitor_messages())
        
    async def stop(self):
        """停止消息监控服务"""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        await self.discord_client.close()
        self._db.close()
        logger.info("Message monitoring service stopped")
        
    async def _monitor_messages(self):
        """监控消息的主循环"""
        try:
            await self.discord_client.monitor_channels(self.handle_discord_message)
        except asyncio.CancelledError:
            logger.info("Message monitoring cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in message monitoring: {str(e)}")
            raise

    async def handle_discord_message(self, raw_message: Dict[str, Any]):
        """处理接收到的Discord消息"""
        try:
            # 提取消息数据
            message_data = self.discord_client.extract_message_data(raw_message)
            
            # 检查是否已存在相同消息
            existing_message = self._db.query(Message).filter(
                Message.platform == Platform.DISCORD,
                Message.platform_message_id == str(message_data["id"])
            ).first()
            
            if existing_message:
                return
            
            # 获取或创建KOL记录
            kol = self._get_or_create_kol(message_data["author"])
            
            # 创建消息记录
            message = Message(
                kol_id=kol.id,
                platform=Platform.DISCORD,
                platform_message_id=str(message_data["id"]),
                content=message_data["content"],
                raw_content=raw_message,
                created_at=datetime.fromisoformat(message_data["timestamp"].rstrip("Z"))
            )
            
            # 如果存在引用消息，添加关联
            if message_data.get("referenced_message"):
                message.referenced_message_id = str(message_data["referenced_message"]["id"])
            
            self._db.add(message)
            self._db.commit()
            
        except Exception as e:
            self._db.rollback()
            raise e

    def _get_or_create_kol(self, author_data: Dict[str, Any]) -> KOL:
        """获取或创建KOL记录"""
        kol = self._db.query(KOL).filter(
            KOL.platform == Platform.DISCORD,
            KOL.platform_user_id == str(author_data["id"])
        ).first()
        
        if not kol:
            kol = KOL(
                name=f"{author_data['username']}#{author_data['discriminator']}",
                platform=Platform.DISCORD,
                platform_user_id=str(author_data["id"]),
                is_active=True
            )
            self._db.add(kol)
            self._db.commit()
        
        return kol 