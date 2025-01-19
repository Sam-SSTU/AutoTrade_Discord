import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import json
from typing import List
import asyncio
from datetime import datetime

from .models.base import Base
from .database import engine
from .services.message_handler import MessageHandler
from .api import messages, channels

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create database tables
Base.metadata.create_all(bind=engine)

# Initialize templates
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

message_handler = None

# 存储所有活跃的WebSocket连接
active_connections: List[WebSocket] = []

async def broadcast_log(log_entry: str):
    """广播日志消息到所有连接的客户端"""
    # 解析消息内容
    message_type = "system"
    message_data = {
        "type": message_type,
        "content": log_entry
    }

    # 如果是新消息通知，提取更多信息
    if "消息" in log_entry and "来自" in log_entry and "添加成功" in log_entry:
        try:
            # 解析消息ID、作者和频道ID
            parts = log_entry.split(" - ")[0].split("来自")
            message_id = parts[0].split("消息")[-1].strip()
            author = parts[1].strip()
            
            # 从日志中提取频道ID（假设格式为 "channel_id: xxx"）
            channel_id = None
            if "channel_id:" in log_entry:
                channel_id = log_entry.split("channel_id:")[1].split()[0].strip()
            
            message_type = "new_message"
            message_data = {
                "type": message_type,
                "message_id": message_id,
                "author": author,
                "channel_id": channel_id,
                "content": log_entry,
                "created_at": datetime.now().isoformat()
            }
            logger.info(f"Broadcasting new message: {message_data}")
        except Exception as e:
            logger.error(f"Error parsing message log: {e}")
    
    # 发送到所有连接的客户端
    for connection in active_connections:
        try:
            await connection.send_text(json.dumps(message_data))
        except Exception as e:
            logger.error(f"Error sending log to client: {e}")

class AsyncWebSocketLogHandler(logging.Handler):
    def emit(self, record):
        try:
            log_entry = self.format(record)
            # 使用事件循环来运行异步广播函数
            loop = asyncio.get_event_loop()
            asyncio.run_coroutine_threadsafe(broadcast_log(log_entry), loop)
        except Exception as e:
            logger.error(f"Error in log handler: {e}")
            self.handleError(record)

# 配置WebSocket日志处理器
websocket_handler = AsyncWebSocketLogHandler()
websocket_handler.setFormatter(logging.Formatter('%(message)s'))
logging.getLogger('app.services.discord_client').addHandler(websocket_handler)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global message_handler
    message_handler = MessageHandler()
    await message_handler.start()
    
    yield
    
    # Shutdown
    if message_handler:
        await message_handler.stop()
        logger.info("Stopped message monitoring service")

# Create FastAPI application
app = FastAPI(
    title="Discord Message Manager",
    description="A web interface for managing Discord messages and channels",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(messages.router, prefix="/api", tags=["messages"])
app.include_router(channels.router, prefix="/api", tags=["channels"])

# Mount static files
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

@app.get("/")
async def root(request: Request):
    """Return the main page"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "message_monitoring": message_handler is not None
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            # 保持连接活跃
            data = await websocket.receive_text()
            # 可以在这里处理从客户端接收到的消息
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        active_connections.remove(websocket) 