from typing import Dict, Any, Optional
from ..models import Message, Channel
from sqlalchemy.orm import Session
from fastapi import WebSocket
import json
from datetime import datetime
from sqlalchemy import text
from .models import AIMessage

class AIMessageHandler:
    def __init__(self):
        self._active_connections: Dict[int, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: int):
        await websocket.accept()
        self._active_connections[client_id] = websocket

    def disconnect(self, client_id: int):
        self._active_connections.pop(client_id, None)

    async def store_message(self, db: Session, message: Message) -> AIMessage:
        """
        将转发的消息存储到AI消息表中并广播
        """
        # 准备引用和附件数据
        references = {
            "referenced_message_id": message.referenced_message_id,
            "referenced_content": message.referenced_content,
            "attachments": [
                {
                    "filename": attachment.filename,
                    "content_type": attachment.content_type,
                }
                for attachment in message.attachments
            ] if message.attachments else [],
            "embeds": json.loads(message.embeds) if message.embeds else []
        }

        # 创建新的AI消息记录
        ai_message = AIMessage(
            channel_id=message.channel.platform_channel_id,
            channel_name=message.channel.name,
            message_content=message.content,
            references=references
        )

        db.add(ai_message)
        # 使用原生SQL设置时间戳
        db.flush()
        db.execute(
            text("UPDATE ai_messages SET created_at = (now() at time zone 'utc')::timestamp WHERE id = :id"),
            {"id": ai_message.id}
        )
        db.commit()
        db.refresh(ai_message)

        # 广播消息
        await self.broadcast_message(message)
        
        return ai_message

    async def broadcast_message(self, message: Message):
        """
        广播消息到所有连接的客户端
        """
        message_data = {
            "id": message.id,
            "platform_message_id": message.platform_message_id,
            "content": message.content,
            "channel_id": message.channel.id,
            "platform_channel_id": message.channel.platform_channel_id,
            "channel_name": message.channel.name,
            "guild_id": message.channel.guild_id,
            "guild_name": message.channel.guild_name,
            "created_at": message.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "referenced_message_id": message.referenced_message_id,
            "referenced_content": message.referenced_content,
            "attachments": [
                {
                    "id": attachment.id,
                    "filename": attachment.filename,
                    "content_type": attachment.content_type,
                    "url": f"/api/messages/attachments/{attachment.id}"
                }
                for attachment in message.attachments
            ] if message.attachments else []
        }

        for websocket in self._active_connections.values():
            try:
                await websocket.send_text(json.dumps(message_data))
            except Exception:
                continue

ai_message_handler = AIMessageHandler() 