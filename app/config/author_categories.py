from typing import Dict, List
import os
from dotenv import load_dotenv

load_dotenv()

# 监听的频道配置
MONITORED_CHANNELS: List[str] = [
    os.getenv("MONITORED_CHANNEL_NEWS"),      # 新闻频道
    os.getenv("MONITORED_CHANNEL_DISCUSSION") # 讨论频道
]

# 频道分类映射
CHANNEL_CATEGORIES: Dict[str, str] = {
    os.getenv("MONITORED_CHANNEL_NEWS"): "news",
    os.getenv("MONITORED_CHANNEL_DISCUSSION"): "discussion"
}

def is_monitored_channel(channel_id: str) -> bool:
    """检查是否是需要监听的频道"""
    return channel_id in MONITORED_CHANNELS

def get_author_category(channel_id: str) -> str:
    """获取作者分类"""
    return CHANNEL_CATEGORIES.get(channel_id, "default") 