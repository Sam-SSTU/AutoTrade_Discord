from typing import List, Dict, Any, Optional, Callable
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from datetime import datetime, timedelta
import logging
import asyncio
import time

from .openai_client import get_openai_client
from .models import AIMessage, AIProcessingLog
from ..models.base import Message, Channel, KOL, Attachment
from ..config.settings import get_settings

logger = logging.getLogger(__name__)

class MessagePreprocessor:
    """
    第一阶段：消息预处理器
    负责消息预筛选、上下文构建和AI分析
    目标：在5秒内完成处理
    """
    
    def __init__(self):
        self.openai_client = get_openai_client()
        self.max_context_messages = 10  # 最多获取10条历史消息
        self.result_callback: Optional[Callable] = None  # 处理完成回调
        
    def set_result_callback(self, callback: Callable[[AIMessage], None]):
        """设置处理结果回调函数"""
        self.result_callback = callback
        
    async def process_stage1(self, db: Session, ai_message: AIMessage) -> bool:
        """
        执行第一阶段处理
        
        Args:
            db: 数据库会话
            ai_message: AI消息对象
            
        Returns:
            bool: 处理是否成功
        """
        start_time = time.time()
        
        # 记录开始处理
        log = AIProcessingLog(
            message_id=ai_message.id,
            stage="stage1",
            status="processing"
        )
        db.add(log)
        db.commit()
        
        try:
            # 1. 构建上下文
            context_messages = await self._build_context(db, ai_message)
            
            # 2. 提取引用内容和附件
            referenced_content = None
            attachments = None
            
            if ai_message.references:
                # 提取引用内容
                if ai_message.references.get("referenced_content"):
                    referenced_content = ai_message.references.get("referenced_content")
                    logger.info(f"消息 {ai_message.id} 包含引用内容")
                
                # 提取附件信息
                if ai_message.references.get("attachments"):
                    attachments = []
                    # 复制原始附件列表，确保不修改原始数据
                    for att in ai_message.references.get("attachments"):
                        att_copy = dict(att)  # 创建附件信息的副本
                        
                        # 如果有attachment_id，从数据库获取完整的附件数据
                        if "id" in att_copy:
                            attachment_id = att_copy["id"]
                            try:
                                # 从数据库查询附件对象
                                attachment_obj = db.query(Attachment).filter(Attachment.id == attachment_id).first()
                                
                                if attachment_obj:
                                    # 更新附件信息，包含实际的二进制数据
                                    att_copy["file_data"] = attachment_obj.file_data
                                    att_copy["content_type"] = attachment_obj.content_type
                                    att_copy["filename"] = attachment_obj.filename
                                    att_copy["size"] = len(attachment_obj.file_data) if attachment_obj.file_data else 0
                                    
                                    logger.debug(f"从数据库获取附件 {attachment_id}: {attachment_obj.filename}, 大小: {att_copy['size']} bytes")
                                else:
                                    logger.warning(f"未找到附件 {attachment_id}")
                                    continue
                                    
                            except Exception as e:
                                logger.error(f"获取附件 {attachment_id} 数据失败: {str(e)}")
                                continue
                        
                        # 确保每个附件都有URL（作为备用）
                        if "id" in att_copy and not att_copy.get("url"):
                            att_copy["url"] = f"/api/messages/attachments/{att_copy['id']}"
                            logger.debug(f"为附件 {att_copy['id']} 构建URL: {att_copy['url']}")
                        
                        attachments.append(att_copy)
                    
                    image_count = sum(1 for att in attachments if att.get("content_type", "").startswith("image/"))
                    if image_count > 0:
                        logger.info(f"消息 {ai_message.id} 包含 {image_count} 个图片附件")
                        # 记录图片信息，方便调试
                        for i, att in enumerate(attachments):
                            if att.get("content_type", "").startswith("image/"):
                                has_data = "有" if att.get("file_data") else "无"
                                logger.info(f"图片 {i+1}: {att.get('filename', 'unknown')}, 类型: {att.get('content_type')}, 数据: {has_data}")
            
            # 3. AI分析
            analysis_result = await self.openai_client.analyze_message(
                ai_message.message_content,
                context_messages,
                attachments=attachments,
                referenced_content=referenced_content
            )
            
            # 4. 提取交易信号（只有当分析结果明确包含交易信号时）
            trading_signal = None
            if (analysis_result.get("is_trading_related") and 
                analysis_result.get("priority", 1) >= 4 and 
                analysis_result.get("category") == "Trading Signal"):  # 只有明确是交易信号类别才提取
                trading_signal = await self.openai_client.extract_trading_signals(
                    ai_message.message_content,
                    analysis_result
                )
            
            # 5. 更新AI消息记录
            await self._update_ai_message(db, ai_message, analysis_result, trading_signal, context_messages)
            
            # 6. 完成处理
            await self._complete_processing(db, ai_message, log, start_time)
            
            # 7. 通知前端处理完成
            if self.result_callback:
                await self.result_callback(ai_message)
            
            logger.info(f"消息 {ai_message.id} 第一阶段处理完成，耗时: {time.time() - start_time:.2f}秒")
            return True
            
        except Exception as e:
            logger.error(f"消息 {ai_message.id} 第一阶段处理失败: {str(e)}")
            await self._handle_processing_error(db, ai_message, log, start_time, str(e))
            return False
    
    async def _build_context(self, db: Session, ai_message: AIMessage) -> List[str]:
        """
        构建消息上下文
        获取同一频道的最近历史消息
        """
        try:
            # 获取同频道的最近消息
            recent_messages = db.query(Message).filter(
                and_(
                    Message.channel_id == self._get_channel_id_by_platform_id(db, ai_message.channel_id),
                    Message.created_at < ai_message.created_at
                )
            ).order_by(desc(Message.created_at)).limit(self.max_context_messages).all()
            
            context_messages = []
            context_ids = []
            
            for msg in reversed(recent_messages):  # 按时间正序
                # 包含所有消息内容，不再进行长度过滤
                if msg.content:
                    context_messages.append(msg.content)
                    context_ids.append(msg.id)
            
            # 保存上下文消息ID到AI消息记录
            if context_ids:
                ai_message.context_messages = context_ids
                db.commit()
            
            logger.info(f"为消息 {ai_message.id} 构建了 {len(context_messages)} 条上下文消息")
            return context_messages
            
        except Exception as e:
            logger.error(f"构建上下文失败: {str(e)}")
            return []
    
    def _get_channel_id_by_platform_id(self, db: Session, platform_channel_id: str) -> Optional[int]:
        """根据平台频道ID获取数据库频道ID"""
        channel = db.query(Channel).filter(Channel.platform_channel_id == platform_channel_id).first()
        return channel.id if channel else None
    
    async def _update_ai_message(
        self, 
        db: Session, 
        ai_message: AIMessage, 
        analysis_result: Dict[str, Any],
        trading_signal: Optional[Dict[str, Any]],
        context_messages: List[str]
    ):
        """更新AI消息记录的分析结果"""
        ai_message.is_trading_related = analysis_result.get("is_trading_related", False)
        ai_message.priority = analysis_result.get("priority", 1)
        ai_message.keywords = analysis_result.get("keywords", [])
        ai_message.category = analysis_result.get("category", "其他")
        ai_message.urgency = analysis_result.get("urgency", "低")
        ai_message.sentiment = analysis_result.get("sentiment", "中性")
        ai_message.confidence = analysis_result.get("confidence", 0.0)
        ai_message.analysis_summary = analysis_result.get("summary", "")
        
        # 交易信号
        if trading_signal and trading_signal.get("has_signal"):
            ai_message.has_trading_signal = True
            ai_message.trading_signal = trading_signal
        
        ai_message.is_processed = True
        ai_message.processed_at = datetime.utcnow()
        
        # 如果有错误信息，记录错误
        if "error" in analysis_result:
            ai_message.processing_error = analysis_result["error"]
        
        db.commit()
    
    async def _complete_processing(
        self, 
        db: Session, 
        ai_message: AIMessage, 
        log: AIProcessingLog, 
        start_time: float
    ):
        """完成处理，更新日志"""
        end_time = time.time()
        duration_ms = int((end_time - start_time) * 1000)
        
        log.status = "completed"
        log.end_time = datetime.utcnow()
        log.duration_ms = duration_ms
        
        db.commit()
        
        # 性能警告
        if duration_ms > 5000:  # 超过5秒
            logger.warning(f"消息 {ai_message.id} 处理耗时过长: {duration_ms}ms")
    
    async def _handle_processing_error(
        self, 
        db: Session, 
        ai_message: AIMessage, 
        log: AIProcessingLog, 
        start_time: float, 
        error_message: str
    ):
        """处理错误情况"""
        end_time = time.time()
        duration_ms = int((end_time - start_time) * 1000)
        
        log.status = "failed"
        log.end_time = datetime.utcnow()
        log.duration_ms = duration_ms
        log.error_message = error_message
        
        ai_message.processing_error = error_message
        ai_message.processed_at = datetime.utcnow()
        
        db.commit()
    
    async def get_high_priority_messages(self, db: Session, limit: int = 10) -> List[AIMessage]:
        """获取高优先级的交易相关消息"""
        return db.query(AIMessage).filter(
            and_(
                AIMessage.is_processed == True,
                AIMessage.is_trading_related == True,
                AIMessage.priority >= 4
            )
        ).order_by(
            desc(AIMessage.priority),
            desc(AIMessage.created_at)
        ).limit(limit).all()
    
    async def get_processing_stats(self, db: Session, hours: int = 24) -> Dict[str, Any]:
        """获取处理统计信息"""
        since = datetime.utcnow() - timedelta(hours=hours)
        
        logs = db.query(AIProcessingLog).filter(
            and_(
                AIProcessingLog.stage == "stage1",
                AIProcessingLog.start_time >= since
            )
        ).all()
        
        total_count = len(logs)
        completed_count = len([log for log in logs if log.status == "completed"])
        failed_count = len([log for log in logs if log.status == "failed"])
        
        durations = [log.duration_ms for log in logs if log.duration_ms]
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        return {
            "total_processed": total_count,
            "completed": completed_count,
            "failed": failed_count,
            "success_rate": completed_count / total_count if total_count > 0 else 0,
            "avg_duration_ms": avg_duration,
            "max_duration_ms": max(durations) if durations else 0
        }

# 全局预处理器实例
message_preprocessor = MessagePreprocessor() 