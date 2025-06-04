from typing import Dict, Any, Optional
from ..models import Message, Channel
from sqlalchemy.orm import Session
from fastapi import WebSocket
import json
from datetime import datetime, timezone
from sqlalchemy import text
import asyncio
import logging
from .models import AIMessage
from .concurrent_processor import concurrent_processor
from ..config.settings import get_settings

logger = logging.getLogger(__name__)

class AIMessageHandler:
    def __init__(self):
        self._active_connections: Dict[int, WebSocket] = {}
        
    async def start_processing(self):
        """启动AI处理器"""
        await concurrent_processor.start()
        logger.info("AI消息处理器已启动")

    async def stop_processing(self):
        """停止AI处理器"""
        await concurrent_processor.stop()
        logger.info("AI消息处理器已停止")

    async def connect(self, websocket: WebSocket, client_id: int):
        await websocket.accept()
        self._active_connections[client_id] = websocket
        logger.info(f"AI WebSocket客户端 {client_id} 已连接")

    def disconnect(self, client_id: int):
        self._active_connections.pop(client_id, None)
        logger.info(f"AI WebSocket客户端 {client_id} 已断开")

    async def store_message(self, db: Session, message: Message) -> AIMessage:
        """
        存储转发的消息到AI消息表中，并添加到并发处理队列
        只处理开启转发的频道消息
        """
        # 检查频道是否开启转发
        if not message.channel.is_forwarding:
            logger.debug(f"频道 {message.channel.name} 未开启转发，跳过AI处理")
            return None
        
        # 准备引用和附件数据
        references = {
            "referenced_message_id": message.referenced_message_id,
            "referenced_content": message.referenced_content,
            "attachments": [
                {
                    "id": attachment.id,
                    "filename": attachment.filename,
                    "content_type": attachment.content_type,
                    "url": f"/api/messages/attachments/{attachment.id}",
                    "is_image": attachment.content_type and attachment.content_type.startswith('image/')
                }
                for attachment in message.attachments
            ] if message.attachments else [],
            "embeds": json.loads(message.embeds) if message.embeds else []
        }

        # 记录附件信息用于调试
        if message.attachments:
            logger.info(f"消息包含 {len(message.attachments)} 个附件")
            for i, att in enumerate(message.attachments):
                logger.info(f"附件 {i+1}: {att.filename}, 类型: {att.content_type}, ID: {att.id}")

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

        # 计算消息优先级（可以根据频道、内容等因素调整）
        priority = self._calculate_message_priority(message, ai_message)

        # 添加到并发处理队列
        success = await concurrent_processor.add_task(ai_message.id, priority)
        if not success:
            logger.error(f"无法将AI消息 {ai_message.id} 添加到处理队列")

        # 广播原始消息到前端
        await self.broadcast_new_message(message, ai_message)
        
        logger.info(f"AI消息 {ai_message.id} 已存储并加入处理队列，优先级: {priority}")
        return ai_message

    def _calculate_message_priority(self, message: Message, ai_message: AIMessage) -> int:
        """计算消息处理优先级 (1-5, 5最高)"""
        priority = 3  # 默认优先级
        
        # 根据频道分类调整优先级
        if message.channel.kol_category:
            if message.channel.kol_category.value == 'CRYPTO':
                priority = 4  # 加密货币频道优先级较高
        
        # 根据消息长度调整
        if len(ai_message.message_content) > 100:
            priority += 1  # 长消息可能包含更多信息
        
        # 根据是否包含引用调整
        if message.referenced_message_id:
            priority += 1  # 回复消息优先级更高
        
        return min(priority, 5)  # 最大优先级为5

    async def broadcast_new_message(self, message: Message, ai_message: AIMessage):
        """广播新消息到前端"""
        # 准备附件信息
        attachments = []
        if message.attachments:
            for attachment in message.attachments:
                # 从环境变量获取基础URL，如果没有则使用localhost
                settings = get_settings()
                base_url = settings.BASE_URL if hasattr(settings, "BASE_URL") else "http://localhost:8000"
                
                # 构建相对和完整URL
                relative_url = f"/api/messages/attachments/{attachment.id}"
                full_url = f"{base_url}{relative_url}"
                
                att_info = {
                    "id": attachment.id,
                    "filename": attachment.filename,
                    "content_type": attachment.content_type,
                    "url": relative_url,
                    "full_url": full_url
                }
                # 标记图片类型
                if attachment.content_type and attachment.content_type.startswith('image/'):
                    att_info["is_image"] = True
                    logger.info(f"标记图片附件: {att_info['filename']}, URL: {att_info['full_url']}")
                attachments.append(att_info)
        
        message_data = {
            "type": "new_ai_message",
            "ai_message_id": ai_message.id,
            "original_message": {
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
                "attachments": attachments
            },
            "status": "queued_for_processing",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        }

        await self._broadcast_to_clients(message_data)

    async def broadcast_processing_result(self, ai_message: AIMessage):
        """广播AI处理结果到前端"""
        # 准备附件信息
        attachments = []
        references = {}
        
        if ai_message.references:
            # 处理引用内容
            if "referenced_content" in ai_message.references:
                references["referenced_content"] = ai_message.references["referenced_content"]
                references["referenced_message_id"] = ai_message.references.get("referenced_message_id")
            
            # 处理附件
            if "attachments" in ai_message.references:
                # 从环境变量获取基础URL，如果没有则使用localhost
                settings = get_settings()
                base_url = settings.BASE_URL if hasattr(settings, "BASE_URL") else "http://localhost:8000"
                
                for att in ai_message.references["attachments"]:
                    att_info = dict(att)  # 复制原始附件信息
                    
                    # 确保有URL
                    if "id" in att_info and not att_info.get("url"):
                        relative_url = f"/api/messages/attachments/{att_info['id']}"
                        att_info["url"] = relative_url
                    
                    # 确保有完整URL
                    if att_info.get("url") and not att_info.get("full_url"):
                        url = att_info.get("url")
                        if not url.startswith("http"):
                            full_url = f"{base_url}{url}" if url.startswith('/') else f"{base_url}/{url}"
                            att_info["full_url"] = full_url
                        else:
                            att_info["full_url"] = url
                    
                    # 标记图片类型
                    if att_info.get("content_type", "").startswith('image/'):
                        att_info["is_image"] = True
                        logger.info(f"标记图片附件: {att_info.get('filename')}, URL: {att_info.get('full_url', att_info.get('url', '无URL'))}")
                    
                    attachments.append(att_info)
        
        # 记录附件信息用于调试
        if attachments:
            logger.info(f"广播结果包含 {len(attachments)} 个附件")
            for i, att in enumerate(attachments):
                logger.info(f"附件 {i+1}: {att.get('filename')}, URL: {att.get('full_url', att.get('url', '无URL'))}, 是否图片: {att.get('is_image', False)}")
        
        analysis_data = {
            "type": "ai_analysis_result",
            "ai_message_id": ai_message.id,
            "channel_id": ai_message.channel_id,
            "channel_name": ai_message.channel_name,
            "content": ai_message.message_content,
            "references": references,
            "attachments": attachments,
            "analysis": {
                "is_trading_related": ai_message.is_trading_related,
                "priority": ai_message.priority,
                "keywords": ai_message.keywords,
                "category": ai_message.category,
                "urgency": ai_message.urgency,
                "sentiment": ai_message.sentiment,
                "confidence": ai_message.confidence,
                "summary": ai_message.analysis_summary,
                "has_trading_signal": ai_message.has_trading_signal,
                "trading_signal": ai_message.trading_signal,
                "contains_images": bool(attachments and any(att.get("is_image") for att in attachments))
            },
            "processed_at": ai_message.processed_at.strftime("%Y-%m-%d %H:%M:%S") if ai_message.processed_at else None,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        }

        await self._broadcast_to_clients(analysis_data)
        
        # 如果是高优先级交易消息，发送特殊通知
        if ai_message.is_trading_related and ai_message.priority >= 4:
            alert_data = {
                "type": "high_priority_alert",
                "ai_message_id": ai_message.id,
                "channel_name": ai_message.channel_name,
                "category": ai_message.category,
                "urgency": ai_message.urgency,
                "summary": ai_message.analysis_summary,
                "trading_signal": ai_message.trading_signal,
                "contains_images": bool(attachments and any(att.get("is_image") for att in attachments)),
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            }
            await self._broadcast_to_clients(alert_data)

    async def _broadcast_to_clients(self, data: Dict[str, Any]):
        """向所有连接的客户端广播数据"""
        if not self._active_connections:
            return
        
        message_text = json.dumps(data, ensure_ascii=False)
        disconnected_clients = []
        
        for client_id, websocket in self._active_connections.items():
            try:
                await websocket.send_text(message_text)
            except Exception as e:
                logger.error(f"向客户端 {client_id} 发送消息失败: {str(e)}")
                disconnected_clients.append(client_id)
        
        # 清理断开的连接
        for client_id in disconnected_clients:
            self.disconnect(client_id)

    async def get_processing_status(self, db: Session) -> Dict[str, Any]:
        """获取处理状态信息"""
        # 获取并发处理器统计
        processor_stats = concurrent_processor.get_stats()
        
        # 获取数据库统计
        unprocessed_count = db.query(AIMessage).filter(AIMessage.is_processed == False).count()
        
        # 获取最近处理的消息
        recent_messages = db.query(AIMessage).filter(
            AIMessage.is_processed == True,
            AIMessage.is_trading_related == True,
            AIMessage.priority >= 4
        ).order_by(AIMessage.processed_at.desc()).limit(5).all()
        
        return {
            "processor_stats": processor_stats,
            "unprocessed_count": unprocessed_count,
            "connected_clients": len(self._active_connections),
            "recent_high_priority_messages": [
                {
                    "id": msg.id,
                    "channel_name": msg.channel_name,
                    "priority": msg.priority,
                    "category": msg.category,
                    "summary": msg.analysis_summary,
                    "processed_at": msg.processed_at.strftime("%Y-%m-%d %H:%M:%S")
                }
                for msg in recent_messages
            ]
        }

    async def reprocess_failed_messages(self, db: Session, limit: int = 10) -> int:
        """重新处理失败的消息"""
        failed_messages = db.query(AIMessage).filter(
            AIMessage.is_processed == False,
            AIMessage.processing_error.isnot(None)
        ).limit(limit).all()
        
        reprocessed_count = 0
        for ai_message in failed_messages:
            # 清除错误信息
            ai_message.processing_error = None
            db.commit()
            
            # 重新加入队列
            priority = 3  # 重新处理的消息使用默认优先级
            success = await concurrent_processor.add_task(ai_message.id, priority)
            if success:
                reprocessed_count += 1
        
        logger.info(f"重新加入 {reprocessed_count} 条失败消息到处理队列")
        return reprocessed_count

    async def update_configuration(self, config: Dict[str, Any]) -> Dict[str, str]:
        """动态更新处理配置"""
        # 注意：某些配置需要重启处理器才能生效
        results = {}
        
        if "max_batch_size" in config:
            concurrent_processor.max_batch_size = config["max_batch_size"]
            results["max_batch_size"] = "已更新"
        
        if "processing_timeout" in config:
            concurrent_processor.processing_timeout = config["processing_timeout"]
            results["processing_timeout"] = "已更新"
        
        # 其他配置项可能需要重启才能生效
        if "max_workers" in config or "queue_max_size" in config:
            results["restart_required"] = "某些配置需要重启处理器才能生效"
        
        return results

ai_message_handler = AIMessageHandler() 