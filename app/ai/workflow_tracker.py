from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
import json
import time
import logging
from datetime import datetime, timezone
from .models import AIMessage, AIProcessingStep

logger = logging.getLogger(__name__)

class WorkflowTracker:
    """AI工作流跟踪器，用于记录每个处理步骤的详细信息"""
    
    def __init__(self, db: Session, ai_message: AIMessage):
        self.db = db
        self.ai_message = ai_message
        self.current_step_order = 0
        
    async def start_step(
        self, 
        step_name: str, 
        input_data: Optional[Dict[str, Any]] = None,
        processing_details: Optional[Dict[str, Any]] = None
    ) -> AIProcessingStep:
        """
        开始一个新的处理步骤
        
        Args:
            step_name: 步骤名称
            input_data: 输入数据
            processing_details: 处理详情
            
        Returns:
            AIProcessingStep: 创建的步骤记录
        """
        self.current_step_order += 1
        
        # 确保输入数据可以序列化
        safe_input_data = self._make_json_safe(input_data) if input_data else None
        safe_processing_details = self._make_json_safe(processing_details) if processing_details else None
        
        step = AIProcessingStep(
            ai_message_id=self.ai_message.id,
            step_name=step_name,
            step_order=self.current_step_order,
            status='processing',
            input_data=safe_input_data,
            processing_details=safe_processing_details,
            start_time=datetime.now(timezone.utc)
        )
        
        self.db.add(step)
        self.db.commit()
        self.db.refresh(step)
        
        logger.info(f"开始处理步骤: {step_name} (AI消息ID: {self.ai_message.id})")
        return step
    
    async def complete_step(
        self,
        step: AIProcessingStep,
        output_data: Optional[Dict[str, Any]] = None,
        processing_details: Optional[Dict[str, Any]] = None,
        api_calls_count: int = 0,
        tokens_used: int = 0,
        cost_usd: float = 0.0
    ):
        """
        完成一个处理步骤
        
        Args:
            step: 步骤记录
            output_data: 输出数据
            processing_details: 处理详情
            api_calls_count: API调用次数
            tokens_used: 使用的token数量
            cost_usd: 估算成本
        """
        end_time = datetime.now(timezone.utc)
        duration_ms = int((end_time - step.start_time).total_seconds() * 1000)
        
        # 确保输出数据可以序列化
        safe_output_data = self._make_json_safe(output_data) if output_data else None
        safe_processing_details = self._make_json_safe(processing_details) if processing_details else None
        
        # 合并处理详情
        if step.processing_details and safe_processing_details:
            combined_details = {**step.processing_details, **safe_processing_details}
        else:
            combined_details = safe_processing_details or step.processing_details
        
        step.status = 'completed'
        step.output_data = safe_output_data
        step.processing_details = combined_details
        step.end_time = end_time
        step.duration_ms = duration_ms
        step.api_calls_count = api_calls_count
        step.tokens_used = tokens_used
        step.cost_usd = cost_usd
        
        self.db.commit()
        
        logger.info(f"完成处理步骤: {step.step_name}, 耗时: {duration_ms}ms, API调用: {api_calls_count}次")
    
    async def fail_step(
        self,
        step: AIProcessingStep,
        error_message: str,
        processing_details: Optional[Dict[str, Any]] = None
    ):
        """
        标记步骤失败
        
        Args:
            step: 步骤记录
            error_message: 错误消息
            processing_details: 处理详情
        """
        end_time = datetime.now(timezone.utc)
        duration_ms = int((end_time - step.start_time).total_seconds() * 1000)
        
        # 确保处理详情可以序列化
        safe_processing_details = self._make_json_safe(processing_details) if processing_details else None
        
        # 合并处理详情
        if step.processing_details and safe_processing_details:
            combined_details = {**step.processing_details, **safe_processing_details}
        else:
            combined_details = safe_processing_details or step.processing_details
        
        step.status = 'failed'
        step.error_message = error_message
        step.processing_details = combined_details
        step.end_time = end_time
        step.duration_ms = duration_ms
        
        self.db.commit()
        
        logger.error(f"步骤失败: {step.step_name}, 错误: {error_message}, 耗时: {duration_ms}ms")
    
    async def skip_step(
        self,
        step_name: str,
        reason: str,
        input_data: Optional[Dict[str, Any]] = None
    ) -> AIProcessingStep:
        """
        跳过一个处理步骤
        
        Args:
            step_name: 步骤名称
            reason: 跳过原因
            input_data: 输入数据
            
        Returns:
            AIProcessingStep: 创建的步骤记录
        """
        self.current_step_order += 1
        
        # 确保输入数据可以序列化
        safe_input_data = self._make_json_safe(input_data) if input_data else None
        
        step = AIProcessingStep(
            ai_message_id=self.ai_message.id,
            step_name=step_name,
            step_order=self.current_step_order,
            status='skipped',
            input_data=safe_input_data,
            processing_details={'skip_reason': reason},
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            duration_ms=0
        )
        
        self.db.add(step)
        self.db.commit()
        self.db.refresh(step)
        
        logger.info(f"跳过处理步骤: {step_name}, 原因: {reason}")
        return step
    
    def _make_json_safe(self, data: Any) -> Any:
        """
        确保数据可以安全地序列化为JSON
        处理包含二进制数据的情况
        """
        if data is None:
            return None
            
        if isinstance(data, dict):
            safe_data = {}
            for key, value in data.items():
                safe_data[key] = self._make_json_safe(value)
            return safe_data
        elif isinstance(data, list):
            return [self._make_json_safe(item) for item in data]
        elif isinstance(data, (bytes, bytearray)):
            # 对于二进制数据，存储基本信息而不是实际数据
            return {
                'type': 'binary_data',
                'size': len(data),
                'content_type': 'application/octet-stream'
            }
        elif isinstance(data, (str, int, float, bool)):
            return data
        elif data is None:
            return None
        else:
            # 对于其他类型，尝试转换为字符串
            try:
                return str(data)
            except Exception:
                return f"<{type(data).__name__} object>"
    
    async def get_workflow_summary(self) -> Dict[str, Any]:
        """获取工作流摘要信息"""
        steps = self.db.query(AIProcessingStep).filter(
            AIProcessingStep.ai_message_id == self.ai_message.id
        ).order_by(AIProcessingStep.step_order).all()
        
        total_duration = sum(step.duration_ms or 0 for step in steps)
        total_api_calls = sum(step.api_calls_count or 0 for step in steps)
        total_tokens = sum(step.tokens_used or 0 for step in steps)
        total_cost = sum(step.cost_usd or 0.0 for step in steps)
        
        step_summaries = []
        for step in steps:
            step_summaries.append({
                'step_name': step.step_name,
                'step_order': step.step_order,
                'status': step.status,
                'duration_ms': step.duration_ms,
                'api_calls_count': step.api_calls_count,
                'tokens_used': step.tokens_used,
                'cost_usd': step.cost_usd,
                'has_input_data': step.input_data is not None,
                'has_output_data': step.output_data is not None,
                'error_message': step.error_message
            })
        
        return {
            'ai_message_id': self.ai_message.id,
            'total_steps': len(steps),
            'completed_steps': len([s for s in steps if s.status == 'completed']),
            'failed_steps': len([s for s in steps if s.status == 'failed']),
            'skipped_steps': len([s for s in steps if s.status == 'skipped']),
            'total_duration_ms': total_duration,
            'total_api_calls': total_api_calls,
            'total_tokens_used': total_tokens,
            'total_cost_usd': total_cost,
            'steps': step_summaries
        }

class WorkflowStepContext:
    """工作流步骤上下文管理器，用于自动管理步骤的开始和结束"""
    
    def __init__(
        self, 
        tracker: WorkflowTracker, 
        step_name: str, 
        input_data: Optional[Dict[str, Any]] = None,
        processing_details: Optional[Dict[str, Any]] = None
    ):
        self.tracker = tracker
        self.step_name = step_name
        self.input_data = input_data
        self.processing_details = processing_details
        self.step = None
        self.output_data = None
        self.api_calls_count = 0
        self.tokens_used = 0
        self.cost_usd = 0.0
    
    async def __aenter__(self):
        self.step = await self.tracker.start_step(
            self.step_name, 
            self.input_data, 
            self.processing_details
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # 如果有异常，标记步骤失败
            await self.tracker.fail_step(
                self.step, 
                str(exc_val),
                {'exception_type': exc_type.__name__}
            )
        else:
            # 正常完成步骤
            await self.tracker.complete_step(
                self.step,
                self.output_data,
                self.processing_details,
                self.api_calls_count,
                self.tokens_used,
                self.cost_usd
            )
    
    def set_output(
        self, 
        output_data: Dict[str, Any], 
        api_calls_count: int = 0, 
        tokens_used: int = 0, 
        cost_usd: float = 0.0
    ):
        """设置步骤输出数据和统计信息"""
        self.output_data = output_data
        self.api_calls_count = api_calls_count
        self.tokens_used = tokens_used
        self.cost_usd = cost_usd
    
    def add_processing_detail(self, key: str, value: Any):
        """添加处理详情"""
        if self.processing_details is None:
            self.processing_details = {}
        self.processing_details[key] = value 