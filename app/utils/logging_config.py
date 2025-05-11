import os
import logging
import sys
import json
import asyncio
from logging.handlers import RotatingFileHandler
from pathlib import Path
from .telegram_logger import TelegramHandler

# 创建日志目录
log_dir = Path(os.getcwd()) / "logs"
log_dir.mkdir(exist_ok=True)

# 定义日志格式
DETAILED_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
SIMPLE_FORMAT = '%(levelname)s: %(message)s'

# 记录WebSocket连接，用于向前端发送日志
websocket_clients = set()

class WebSocketHandler(logging.Handler):
    """向前端WebSocket发送日志的处理器"""
    
    def emit(self, record):
        try:
            log_entry = self.format(record)
            log_data = {
                'type': 'log',
                'level': record.levelname,
                'message': log_entry,
                'timestamp': record.created,
                'logger': record.name
            }
            
            # 获取当前事件循环
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果事件循环正在运行，创建一个任务
                loop.create_task(self._broadcast_log(log_data))
            else:
                # 如果事件循环没有运行，直接运行（不太可能发生）
                loop.run_until_complete(self._broadcast_log(log_data))
        except Exception:
            self.handleError(record)
    
    async def _broadcast_log(self, log_data):
        """广播日志到所有已连接的WebSocket客户端"""
        message = json.dumps(log_data)
        disconnected = set()
        
        # 创建副本进行遍历，避免在遍历时修改集合
        clients_copy = websocket_clients.copy()
        
        for ws in clients_copy:
            try:
                if hasattr(ws, '_send_log_message'):
                    await ws._send_log_message(message)
                elif hasattr(ws, 'state') and ws.state:
                    await ws.send_str(message)
                else:
                    disconnected.add(ws)
            except Exception:
                disconnected.add(ws)
        
        # 遍历完成后再移除断开的连接
        if disconnected:
            try:
                websocket_clients.difference_update(disconnected)
            except RuntimeError as e:
                # 如果集合在其他地方被修改，记录错误但不中断操作
                logging.error(f"Error updating websocket clients set: {str(e)}")

def register_websocket(websocket):
    """注册WebSocket客户端以接收日志"""
    websocket_clients.add(websocket)
    
def unregister_websocket(websocket):
    """取消注册WebSocket客户端"""
    websocket_clients.discard(websocket)

def setup_logger(name, log_file=None, level=logging.INFO, propagate=True):
    """设置带有控制台和文件输出的日志器"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = propagate
    
    # 清除现有处理器，防止重复
    if logger.handlers:
        logger.handlers.clear()
    
    # 添加控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
    logger.addHandler(console_handler)
    
    # 如果指定了日志文件，添加文件处理器
    if log_file:
        file_handler = RotatingFileHandler(
            log_dir / log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
        logger.addHandler(file_handler)
    
    # 添加WebSocket处理器
    ws_handler = WebSocketHandler()
    ws_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
    logger.addHandler(ws_handler)
    
    return logger

def configure_logging():
    """配置整个应用的日志系统"""
    # 先设置根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # 清除现有处理器
    if root_logger.handlers:
        root_logger.handlers.clear()
    
    # 添加控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
    root_logger.addHandler(console_handler)
    
    # 添加主日志文件处理器
    main_file_handler = RotatingFileHandler(
        log_dir / "autotrade.log",
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    main_file_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
    root_logger.addHandler(main_file_handler)
    
    # 添加错误日志文件处理器，只记录ERROR及以上级别
    error_file_handler = RotatingFileHandler(
        log_dir / "errors.log",
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
    root_logger.addHandler(error_file_handler)
    
    # 添加Telegram处理器，只处理ERROR及以上级别和特殊标记的消息
    try:
        telegram_handler = TelegramHandler()
        telegram_handler.setLevel(logging.ERROR)
        telegram_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
        root_logger.addHandler(telegram_handler)
    except Exception as e:
        print(f"Error setting up Telegram logger: {str(e)}")
    
    # 添加WebSocket处理器
    ws_handler = WebSocketHandler()
    ws_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
    root_logger.addHandler(ws_handler)
    
    # 设置特定模块的日志器
    setup_logger("Message Logs", "discord.log", level=logging.DEBUG)
    
    # 返回根日志器，以便在其他地方使用
    return root_logger 