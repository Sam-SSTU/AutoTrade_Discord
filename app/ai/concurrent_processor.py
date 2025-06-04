import asyncio
import time
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from ..config.settings import get_settings, reload_settings
from .preprocessor import message_preprocessor
from .models import AIMessage, AIProcessingLog

logger = logging.getLogger(__name__)
settings = get_settings()

@dataclass
class ProcessingTask:
    """处理任务数据类"""
    ai_message_id: int
    priority: int = 1
    created_at: datetime = datetime.now(timezone.utc)
    retry_count: int = 0

class RateLimiter:
    """API请求频率限制器"""
    
    def __init__(self, max_requests_per_minute: int = 10):
        self.max_requests = max_requests_per_minute
        self.requests = []
        self.lock = asyncio.Lock()
    
    async def acquire(self):
        """获取请求许可"""
        async with self.lock:
            now = datetime.now(timezone.utc)
            # 清理过期的请求记录
            self.requests = [req_time for req_time in self.requests 
                           if now - req_time < timedelta(minutes=1)]
            
            # 检查是否超过频率限制
            if len(self.requests) >= self.max_requests:
                # 计算需要等待的时间
                oldest_request = min(self.requests)
                wait_time = 60 - (now - oldest_request).total_seconds()
                if wait_time > 0:
                    logger.warning(f"API频率限制，等待 {wait_time:.1f} 秒")
                    await asyncio.sleep(wait_time)
            
            # 记录新请求
            self.requests.append(now)

class ConcurrentAIProcessor:
    """并发AI消息处理器"""
    
    def __init__(self):
        self.settings = get_settings()
        self.max_workers = self.settings.ai_max_concurrent_workers
        self.max_batch_size = self.settings.ai_max_batch_size
        self.queue_max_size = self.settings.ai_queue_max_size
        self.processing_timeout = self.settings.ai_processing_timeout
        
        # 处理队列和工作器
        self.task_queue = asyncio.Queue(maxsize=self.queue_max_size)
        self.workers = []
        self.rate_limiter = RateLimiter(self.settings.ai_request_rate_limit)
        
        # 回调函数
        self.result_callback = None
        
        # 统计信息
        self.stats = {
            "total_processed": 0,
            "successful": 0,
            "failed": 0,
            "active_workers": 0,
            "queue_size": 0
        }
        
        self._running = False
        logger.info(f"并发AI处理器初始化: {self.max_workers}个工作器, 批大小{self.max_batch_size}")
    
    def set_result_callback(self, callback):
        """设置处理结果回调函数"""
        self.result_callback = callback
        # 同时设置预处理器的回调
        message_preprocessor.set_result_callback(callback)
    
    async def start(self):
        """启动处理器"""
        if self._running:
            return
        
        self._running = True
        
        # 启动工作器
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker(f"worker-{i}"))
            self.workers.append(worker)
        
        logger.info(f"已启动 {len(self.workers)} 个AI处理工作器")
    
    async def stop(self):
        """停止处理器"""
        if not self._running:
            return
        
        self._running = False
        
        # 停止所有工作器
        for worker in self.workers:
            worker.cancel()
        
        # 等待工作器结束
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()
        
        logger.info("AI处理工作器已停止")
    
    async def add_task(self, ai_message_id: int, priority: int = 1) -> bool:
        """添加处理任务"""
        if not self._running:
            logger.warning("处理器未运行，无法添加任务")
            return False
        
        task = ProcessingTask(
            ai_message_id=ai_message_id,
            priority=priority,
            created_at=datetime.now(timezone.utc)
        )
        
        try:
            # 非阻塞添加，如果队列满了直接返回失败
            self.task_queue.put_nowait(task)
            self.stats["queue_size"] = self.task_queue.qsize()
            logger.debug(f"任务 {ai_message_id} 已加入队列，当前队列大小: {self.stats['queue_size']}")
            return True
        except asyncio.QueueFull:
            logger.error(f"队列已满，无法添加任务 {ai_message_id}")
            return False
    
    async def _worker(self, worker_name: str):
        """工作器主循环"""
        logger.info(f"工作器 {worker_name} 已启动")
        
        while self._running:
            try:
                self.stats["active_workers"] += 1
                
                # 批量获取任务
                tasks = await self._get_batch_tasks()
                if not tasks:
                    await asyncio.sleep(0.1)  # 短暂休息
                    continue
                
                # 处理任务批次
                await self._process_batch(worker_name, tasks)
                
            except asyncio.CancelledError:
                logger.info(f"工作器 {worker_name} 被取消")
                break
            except Exception as e:
                logger.error(f"工作器 {worker_name} 出错: {str(e)}")
                await asyncio.sleep(1)  # 错误后等待一秒
            finally:
                self.stats["active_workers"] -= 1
                self.stats["queue_size"] = self.task_queue.qsize()
        
        logger.info(f"工作器 {worker_name} 已停止")
    
    async def _get_batch_tasks(self) -> List[ProcessingTask]:
        """获取一批任务"""
        tasks = []
        
        # 获取第一个任务（阻塞等待）
        try:
            first_task = await asyncio.wait_for(
                self.task_queue.get(), 
                timeout=1.0
            )
            tasks.append(first_task)
        except asyncio.TimeoutError:
            return []
        
        # 尝试获取更多任务（非阻塞）
        while len(tasks) < self.max_batch_size:
            try:
                task = self.task_queue.get_nowait()
                tasks.append(task)
            except asyncio.QueueEmpty:
                break
        
        # 按优先级排序
        tasks.sort(key=lambda t: t.priority, reverse=True)
        return tasks
    
    async def _process_batch(self, worker_name: str, tasks: List[ProcessingTask]):
        """处理任务批次"""
        logger.info(f"工作器 {worker_name} 开始处理 {len(tasks)} 个任务")
        
        from ..database import SessionLocal  # 避免循环导入
        
        for task in tasks:
            start_time = time.time()
            success = False
            
            try:
                # 频率限制
                await self.rate_limiter.acquire()
                
                # 处理单个任务
                db = SessionLocal()
                try:
                    ai_message = db.query(AIMessage).filter(
                        AIMessage.id == task.ai_message_id
                    ).first()
                    
                    if not ai_message:
                        logger.warning(f"AI消息 {task.ai_message_id} 不存在")
                        continue
                    
                    if ai_message.is_processed:
                        logger.info(f"AI消息 {task.ai_message_id} 已被处理")
                        continue
                    
                    # 执行处理，带超时
                    success = await asyncio.wait_for(
                        message_preprocessor.process_stage1(db, ai_message),
                        timeout=self.processing_timeout
                    )
                    
                finally:
                    db.close()
                
                # 更新统计
                self.stats["total_processed"] += 1
                if success:
                    self.stats["successful"] += 1
                    logger.info(f"任务 {task.ai_message_id} 处理成功，耗时: {time.time() - start_time:.2f}秒")
                else:
                    self.stats["failed"] += 1
                    logger.error(f"任务 {task.ai_message_id} 处理失败")
                
            except asyncio.TimeoutError:
                logger.error(f"任务 {task.ai_message_id} 处理超时")
                self.stats["failed"] += 1
            except Exception as e:
                logger.error(f"处理任务 {task.ai_message_id} 时出错: {str(e)}")
                self.stats["failed"] += 1
            
            # 标记任务完成
            self.task_queue.task_done()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取处理统计"""
        return {
            **self.stats,
            "is_running": self._running,
            "max_workers": self.max_workers,
            "max_batch_size": self.max_batch_size,
            "queue_size": self.task_queue.qsize()
        }
    
    async def reload_config(self):
        """重新加载配置"""
        # 如果正在运行，先停止
        was_running = self._running
        if was_running:
            await self.stop()
        
        # 重新加载配置
        self.settings = reload_settings()
        old_max_workers = self.max_workers
        self.max_workers = self.settings.ai_max_concurrent_workers
        self.max_batch_size = self.settings.ai_max_batch_size
        self.queue_max_size = self.settings.ai_queue_max_size
        self.processing_timeout = self.settings.ai_processing_timeout
        
        # 重新创建队列（因为maxsize在创建时固定）
        old_queue_size = self.task_queue.qsize()
        old_tasks = []
        # 保存旧任务
        while not self.task_queue.empty():
            try:
                old_tasks.append(self.task_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        
        # 创建新队列
        self.task_queue = asyncio.Queue(maxsize=self.queue_max_size)
        
        # 恢复旧任务到新队列
        for task in old_tasks:
            try:
                self.task_queue.put_nowait(task)
            except asyncio.QueueFull:
                logger.warning(f"新队列容量不足，丢弃任务 {task.ai_message_id}")
                break
        
        # 更新速率限制器
        self.rate_limiter = RateLimiter(self.settings.ai_request_rate_limit)
        
        logger.info(f"配置已重新加载: max_workers从{old_max_workers}变更为{self.max_workers}, 队列大小从{old_queue_size}变更为{self.task_queue.qsize()}")
        
        # 如果之前在运行，重新启动
        if was_running:
            await self.start()
        
        return {
            "old_max_workers": old_max_workers,
            "new_max_workers": self.max_workers,
            "old_queue_size": old_queue_size,
            "new_queue_size": self.task_queue.qsize(),
            "restarted": was_running
        }
    
    async def clear_queue(self):
        """清空队列"""
        while not self.task_queue.empty():
            try:
                self.task_queue.get_nowait()
                self.task_queue.task_done()
            except asyncio.QueueEmpty:
                break
        logger.info("处理队列已清空")

# 全局处理器实例
concurrent_processor = ConcurrentAIProcessor() 