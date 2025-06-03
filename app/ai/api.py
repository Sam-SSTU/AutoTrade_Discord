from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel

from ..database import get_db
from .models import AIMessage, AIProcessingLog
from .message_handler import ai_message_handler
from .preprocessor import message_preprocessor
from .concurrent_processor import concurrent_processor

router = APIRouter(prefix="/ai", tags=["AI处理"])

class ConfigUpdate(BaseModel):
    """配置更新模型"""
    max_batch_size: Optional[int] = None
    processing_timeout: Optional[int] = None
    max_workers: Optional[int] = None
    queue_max_size: Optional[int] = None

@router.get("/status", summary="获取AI处理状态")
async def get_processing_status(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """获取AI消息处理的整体状态"""
    return await ai_message_handler.get_processing_status(db)

@router.get("/stats", summary="获取处理统计信息")
async def get_processing_stats(
    hours: int = Query(default=24, description="统计时间范围（小时）"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """获取指定时间范围内的处理统计信息"""
    return await message_preprocessor.get_processing_stats(db, hours)

@router.get("/config", summary="获取当前配置")
async def get_current_config() -> Dict[str, Any]:
    """获取当前AI处理配置"""
    stats = concurrent_processor.get_stats()
    return {
        "max_workers": stats["max_workers"],
        "max_batch_size": stats["max_batch_size"],
        "queue_max_size": concurrent_processor.queue_max_size,
        "processing_timeout": concurrent_processor.processing_timeout,
        "rate_limit": concurrent_processor.rate_limiter.max_requests,
        "is_running": stats["is_running"],
        "current_queue_size": stats["queue_size"],
        "active_workers": stats["active_workers"]
    }

@router.post("/config", summary="更新处理配置")
async def update_config(
    config: ConfigUpdate,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """动态更新AI处理配置"""
    config_dict = config.dict(exclude_none=True)
    
    if not config_dict:
        raise HTTPException(status_code=400, detail="没有提供配置更新")
    
    # 验证配置值
    if "max_batch_size" in config_dict and config_dict["max_batch_size"] <= 0:
        raise HTTPException(status_code=400, detail="批处理大小必须大于0")
    
    if "processing_timeout" in config_dict and config_dict["processing_timeout"] <= 0:
        raise HTTPException(status_code=400, detail="处理超时时间必须大于0")
    
    # 更新配置
    results = await ai_message_handler.update_configuration(config_dict)
    
    return {
        "message": "配置更新完成",
        "updated_configs": config_dict,
        "results": results
    }

@router.get("/messages", summary="获取AI消息列表")
async def get_ai_messages(
    page: int = Query(default=1, ge=1, description="页码"),
    size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    is_trading_related: Optional[bool] = Query(default=None, description="是否交易相关"),
    priority_min: Optional[int] = Query(default=None, ge=1, le=5, description="最低优先级"),
    category: Optional[str] = Query(default=None, description="消息分类"),
    urgency: Optional[str] = Query(default=None, description="紧急程度"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """分页获取AI消息列表，支持筛选"""
    
    query = db.query(AIMessage).filter(AIMessage.is_processed == True)
    
    # 应用筛选条件
    if is_trading_related is not None:
        query = query.filter(AIMessage.is_trading_related == is_trading_related)
    
    if priority_min is not None:
        query = query.filter(AIMessage.priority >= priority_min)
    
    if category:
        query = query.filter(AIMessage.category == category)
    
    if urgency:
        query = query.filter(AIMessage.urgency == urgency)
    
    # 计算总数
    total = query.count()
    
    # 分页查询
    messages = query.order_by(AIMessage.created_at.desc()).offset((page - 1) * size).limit(size).all()
    
    return {
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
        "data": [
            {
                "id": msg.id,
                "channel_id": msg.channel_id,
                "channel_name": msg.channel_name,
                "content": msg.message_content[:200] + "..." if len(msg.message_content) > 200 else msg.message_content,
                "is_trading_related": msg.is_trading_related,
                "priority": msg.priority,
                "keywords": msg.keywords,
                "category": msg.category,
                "urgency": msg.urgency,
                "sentiment": msg.sentiment,
                "confidence": msg.confidence,
                "summary": msg.analysis_summary,
                "has_trading_signal": msg.has_trading_signal,
                "created_at": msg.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "processed_at": msg.processed_at.strftime("%Y-%m-%d %H:%M:%S") if msg.processed_at else None
            }
            for msg in messages
        ]
    }

@router.get("/messages/{message_id}", summary="获取AI消息详情")
async def get_ai_message_detail(
    message_id: int,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """获取单条AI消息的详细信息"""
    
    ai_message = db.query(AIMessage).filter(AIMessage.id == message_id).first()
    if not ai_message:
        raise HTTPException(status_code=404, detail="消息不存在")
    
    # 获取处理日志
    logs = db.query(AIProcessingLog).filter(AIProcessingLog.message_id == message_id).order_by(AIProcessingLog.start_time).all()
    
    return {
        "id": ai_message.id,
        "channel_id": ai_message.channel_id,
        "channel_name": ai_message.channel_name,
        "content": ai_message.message_content,
        "references": ai_message.references,
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
        "context_messages": ai_message.context_messages,
        "is_processed": ai_message.is_processed,
        "processing_error": ai_message.processing_error,
        "created_at": ai_message.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "processed_at": ai_message.processed_at.strftime("%Y-%m-%d %H:%M:%S") if ai_message.processed_at else None,
        "processing_logs": [
            {
                "id": log.id,
                "stage": log.stage,
                "status": log.status,
                "start_time": log.start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": log.end_time.strftime("%Y-%m-%d %H:%M:%S") if log.end_time else None,
                "duration_ms": log.duration_ms,
                "error_message": log.error_message,
                "details": log.details
            }
            for log in logs
        ]
    }

@router.get("/high-priority", summary="获取高优先级交易消息")
async def get_high_priority_messages(
    limit: int = Query(default=10, ge=1, le=50, description="返回数量"),
    db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    """获取高优先级的交易相关消息"""
    
    messages = await message_preprocessor.get_high_priority_messages(db, limit)
    
    return [
        {
            "id": msg.id,
            "channel_name": msg.channel_name,
            "content": msg.message_content[:200] + "..." if len(msg.message_content) > 200 else msg.message_content,
            "priority": msg.priority,
            "category": msg.category,
            "urgency": msg.urgency,
            "sentiment": msg.sentiment,
            "confidence": msg.confidence,
            "summary": msg.analysis_summary,
            "keywords": msg.keywords,
            "has_trading_signal": msg.has_trading_signal,
            "trading_signal": msg.trading_signal,
            "created_at": msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
        }
        for msg in messages
    ]

@router.post("/reprocess-failed", summary="重新处理失败的消息")
async def reprocess_failed_messages(
    limit: int = Query(default=10, ge=1, le=100, description="重新处理的数量"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """重新处理失败的消息"""
    
    count = await ai_message_handler.reprocess_failed_messages(db, limit)
    
    return {
        "message": f"已重新加入 {count} 条失败消息到处理队列",
        "reprocessed_count": count
    }

@router.post("/start-processing", summary="启动AI处理器")
async def start_processing() -> Dict[str, str]:
    """启动AI消息处理器"""
    await ai_message_handler.start_processing()
    return {"message": "AI消息处理器已启动"}

@router.post("/stop-processing", summary="停止AI处理器")
async def stop_processing() -> Dict[str, str]:
    """停止AI消息处理器"""
    await ai_message_handler.stop_processing()
    return {"message": "AI消息处理器已停止"}

@router.post("/clear-queue", summary="清空处理队列")
async def clear_queue() -> Dict[str, str]:
    """清空AI处理队列"""
    await concurrent_processor.clear_queue()
    return {"message": "处理队列已清空"}

@router.get("/categories", summary="获取消息分类统计")
async def get_message_categories(
    hours: int = Query(default=24, description="统计时间范围（小时）"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """获取消息分类统计信息"""
    
    since = datetime.utcnow() - timedelta(hours=hours)
    
    # 统计各分类的消息数量
    from sqlalchemy import func
    
    category_stats = db.query(
        AIMessage.category,
        func.count(AIMessage.id).label('count'),
        func.avg(AIMessage.priority).label('avg_priority'),
        func.sum(func.case([(AIMessage.is_trading_related == True, 1)], else_=0)).label('trading_related_count')
    ).filter(
        AIMessage.created_at >= since,
        AIMessage.is_processed == True
    ).group_by(AIMessage.category).all()
    
    return {
        "time_range_hours": hours,
        "categories": [
            {
                "category": stat.category or "未分类",
                "count": stat.count,
                "avg_priority": round(float(stat.avg_priority), 2) if stat.avg_priority else 0,
                "trading_related_count": stat.trading_related_count
            }
            for stat in category_stats
        ]
    }

@router.get("/keywords", summary="获取热门关键词")
async def get_popular_keywords(
    hours: int = Query(default=24, description="统计时间范围（小时）"),
    limit: int = Query(default=20, description="返回数量"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """获取热门关键词统计"""
    
    since = datetime.utcnow() - timedelta(hours=hours)
    
    # 获取交易相关消息的关键词
    messages = db.query(AIMessage).filter(
        AIMessage.created_at >= since,
        AIMessage.is_processed == True,
        AIMessage.is_trading_related == True,
        AIMessage.keywords.isnot(None)
    ).all()
    
    # 统计关键词频率
    keyword_counts = {}
    for msg in messages:
        if msg.keywords:
            for keyword in msg.keywords:
                keyword_counts[keyword] = keyword_counts.get(keyword, 0) + 1
    
    # 排序并返回前N个
    sorted_keywords = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    
    return {
        "time_range_hours": hours,
        "keywords": [
            {
                "keyword": keyword,
                "count": count
            }
            for keyword, count in sorted_keywords
        ]
    } 