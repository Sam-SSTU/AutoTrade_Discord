import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import json
from typing import List
import asyncio
from datetime import datetime
import os

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
app.include_router(routes.router)  # 页面路由
app.include_router(channels.router, prefix="/api")  # API路由
app.include_router(messages.router, prefix="/api")  # API路由

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# 配置静态文件服务
storage_path = os.path.join(os.getcwd(), 'storage')
os.makedirs(storage_path, exist_ok=True)
app.mount("/storage", StaticFiles(directory=storage_path), name="storage")

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
                    await websocket.send_text(message)
                return True
            except Exception as e:
                logger.error(f"Failed to send log to websocket: {str(e)}")
                return False
        
        # Attach the method to the websocket object
        websocket._send_log_message = send_log_message
        
        # Send a welcome message
        await websocket.send_text(json.dumps({
            "type": "connection", 
            "status": "connected",
            "message": "WebSocket connection established"
        }))
        
        while True:
            # Keep the connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
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