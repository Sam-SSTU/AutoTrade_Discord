from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

router = APIRouter()

# 获取当前文件所在目录
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@router.get("/ai", response_class=HTMLResponse)
async def ai_messages(request: Request):
    return templates.TemplateResponse("ai_messages.html", {"request": request})

@router.get("/ai/workflow", response_class=HTMLResponse)
async def ai_workflow(request: Request):
    return templates.TemplateResponse("ai_workflow.html", {"request": request}) 