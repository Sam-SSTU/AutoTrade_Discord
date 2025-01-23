from typing import Dict, Any, Optional
from ..models import Message, Channel
from sqlalchemy.orm import Session
from fastapi import WebSocket
import json
from datetime import timezone

class AIMessageHandler:
    def __init__(self):
        self._active_connections: Dict[int, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: int):
        await websocket.accept()
        self._active_connections[client_id] = websocket

    def disconnect(self, client_id: int):
        self._active_connections.pop(client_id, None)

    async def broadcast_message(self, message: Message):
        """
        广播消息到所有连接的客户端
        """
        # 确保时间是UTC时间
        created_at_utc = message.created_at.astimezone(timezone.utc)
        
        message_data = {
            "id": message.id,
            "platform_message_id": message.platform_message_id,
            "content": message.content,
            "channel_id": message.channel.id,
            "platform_channel_id": message.channel.platform_channel_id,
            "channel_name": message.channel.name,
            "guild_id": message.channel.guild_id,
            "guild_name": message.channel.guild_name,
            "created_at": created_at_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),  # 使用UTC格式
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