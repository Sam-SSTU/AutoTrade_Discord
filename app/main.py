import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path
import json
from typing import List
import asyncio
from datetime import datetime
import os
import time
from websockets.exceptions import ConnectionClosedOK

# Apply proxy patch for HTTPS-over-HTTPS support
from .utils.proxy_patch import apply_proxy_patch
apply_proxy_patch()

# Configure improved logging
from .utils.logging_config import configure_logging, register_websocket, unregister_websocket
logger = configure_logging()

from .models.base import Base
from .database import engine
from .services.message_handler import MessageHandler
from .services.discord_client import DiscordClient
from .api import messages, channels
from . import routes
from .ai import ai_message_handler

# Create database tables
Base.metadata.create_all(bind=engine)

# Initialize templates
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

message_handler = None
discord_client = DiscordClient()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global message_handler
    message_handler = MessageHandler()
    await message_handler.start()
    
    # 启动AI消息处理器
    await ai_message_handler.start_processing()
    
    # 设置AI处理结果回调，将结果广播到前端
    from .ai.concurrent_processor import concurrent_processor
    concurrent_processor.set_result_callback(ai_message_handler.broadcast_processing_result)
    
    logger.info("Started AI message processing service")
    
    yield
    
    # Shutdown
    if message_handler:
        await message_handler.stop()
        logger.info("Stopped message monitoring service")
    
    # 停止AI消息处理器
    await ai_message_handler.stop_processing()
    logger.info("Stopped AI message processing service")

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
app.include_router(routes.router)  # 页面路由
app.include_router(channels.router, prefix="/api")  # API路由
app.include_router(messages.router, prefix="/api")  # API路由

# 添加AI路由
from .ai.api import router as ai_router
app.include_router(ai_router, prefix="/api")  # AI API路由

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# 配置静态文件服务
storage_path = os.path.join(os.getcwd(), 'storage')
os.makedirs(storage_path, exist_ok=True)
app.mount("/storage", StaticFiles(directory=storage_path), name="storage")

# Serve favicon.ico for apple touch icon requests
APPLE_ICON_PATHS = ["/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"]
FAVICON_PATH = Path(__file__).parent / "static" / "favicon.ico"

@app.get("/apple-touch-icon.png", include_in_schema=False)
async def get_apple_touch_icon():
    if FAVICON_PATH.exists():
        return FileResponse(FAVICON_PATH)
    return {"error": "Favicon not found"}, 404

@app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
async def get_apple_touch_icon_precomposed():
    if FAVICON_PATH.exists():
        return FileResponse(FAVICON_PATH)
    return {"error": "Favicon not found"}, 404

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
    
    try:
        # Register with Discord client
        discord_client.register_websocket(websocket)
        
        # Register with logging system and add log sending method
        register_websocket(websocket)
        
        # Add method to send log messages
        async def send_log_message(message):
            try:
                if websocket.client_state != 'DISCONNECTED':
                    # Format the log message as JSON with type and message
                    if isinstance(message, str):
                        try:
                            # 尝试解析消息是否为 JSON
                            data = json.loads(message)
                            if isinstance(data, dict):
                                log_data = {
                                    "type": "log",
                                    "level": data.get("level", "INFO"),
                                    "logger": data.get("logger", "System"),
                                    "message": data.get("message", "").strip(),
                                    "timestamp": data.get("timestamp", time.time())
                                }
                            else:
                                raise ValueError("Message is not a dict")
                        except json.JSONDecodeError:
                            # 如果不是 JSON，按普通字符串处理
                            parts = message.split(' - ', 2)
                            if len(parts) >= 3:
                                timestamp_str, logger_name, content = parts
                                level = 'INFO'
                                if ' DEBUG ' in message:
                                    level = 'DEBUG'
                                elif ' INFO ' in message:
                                    level = 'INFO'
                                elif ' WARNING ' in message:
                                    level = 'WARN'
                                elif ' ERROR ' in message:
                                    level = 'ERROR'
                                
                                # 修复时间戳解析
                                try:
                                    # 如果是 JSON 字符串，直接使用当前时间
                                    if timestamp_str.strip().startswith('{'):
                                        ts_float = time.time()
                                    else:
                                        # 否则尝试解析时间戳
                                        ts = datetime.strptime(timestamp_str.strip(), '%Y-%m-%d %H:%M:%S,%f')
                                        ts_float = ts.timestamp()
                                except Exception as e:
                                    ts_float = time.time()
                                    logger.debug(f"Using current time as timestamp due to parsing error: {str(e)}")
                                
                                log_data = {
                                    "type": "log",
                                    "level": level,
                                    "logger": logger_name.strip(),
                                    "message": content.strip(),
                                    "timestamp": ts_float
                                }
                            else:
                                log_data = {
                                    "type": "log",
                                    "level": "INFO",
                                    "message": message.strip(),
                                    "timestamp": time.time()
                                }
                    else:
                        # 如果消息已经是字典格式
                        log_data = {
                            "type": "log",
                            "level": message.get("level", "INFO"),
                            "logger": message.get("logger", "System"),
                            "message": message.get("message", str(message)).strip(),
                            "timestamp": message.get("timestamp", time.time())
                        }
                    
                    # 确保所有字段都存在
                    log_data.setdefault("type", "log")
                    log_data.setdefault("level", "INFO")
                    log_data.setdefault("logger", "System")
                    log_data.setdefault("message", "")
                    log_data.setdefault("timestamp", time.time())
                    
                    # 确保中文正确编码
                    json_str = json.dumps(log_data, ensure_ascii=False)
                    await websocket.send_text(json_str)
                return True
            except ConnectionClosedOK:
                # Log a concise message if the connection is already closed
                logger.info(f"Failed to send log to websocket: Connection already closed for client {websocket.client}")
                return False
            except Exception as e:
                logger.error(f"Failed to send log to websocket: {str(e)}", exc_info=True)
                return False
        
        # Attach the method to the websocket object
        websocket._send_log_message = send_log_message
        
        # Send a welcome message
        await websocket.send_text(json.dumps({
            "type": "connection", 
            "status": "connected",
            "message": "WebSocket connection established",
            "timestamp": time.time()
        }, ensure_ascii=False))
        
        while True:
            # Keep the connection alive
            data = await websocket.receive_text()
            try:
                # 尝试解析接收到的数据
                json_data = json.loads(data)
                logger.debug(f"Received WebSocket message: {json.dumps(json_data, ensure_ascii=False)}")
            except json.JSONDecodeError:
                logger.debug(f"Received non-JSON WebSocket message: {data}")
            
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}", exc_info=True)
    finally:
        # Always ensure cleanup in all cases
        discord_client.unregister_websocket(websocket)
        unregister_websocket(websocket)

@app.websocket("/ws/ai")
async def websocket_ai_endpoint(websocket: WebSocket):
    client_id = id(websocket)
    await ai_message_handler.connect(websocket, client_id)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        ai_message_handler.disconnect(client_id)

@app.get("/api/ping")
async def ping():
    """Check backend connectivity"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()} 