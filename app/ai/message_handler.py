from typing import Dict, Any, Optional
from ..models import Message, Channel
from sqlalchemy.orm import Session
from fastapi import WebSocket
import json

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
        message_data = {
            "id": message.id,
            "content": message.content,
            "channel_name": message.channel.name,
            "created_at": message.created_at.isoformat(),
            "referenced_content": message.referenced_content,
            "attachments": [
                {
                    "filename": attachment.filename,
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