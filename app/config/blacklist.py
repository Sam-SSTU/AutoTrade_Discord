"""
Channel blacklist management module
"""
import json
import os
import logging
from typing import Set, Dict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# 确保数据目录存在
DATA_DIR = Path(__file__).parent.parent.parent / "data"
BLACKLIST_FILE = DATA_DIR / "channel_blacklist.json"

# 从环境变量获取配置
ENABLE_BLACKLIST = os.getenv("ENABLE_CHANNEL_BLACKLIST", "true").lower() == "true"
CLEAR_ON_START = os.getenv("CLEAR_BLACKLIST_ON_START", "false").lower() == "true"

def ensure_data_directory():
    """确保数据目录存在"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

def clear_blacklist():
    """清空黑名单"""
    ensure_data_directory()
    try:
        if BLACKLIST_FILE.exists():
            BLACKLIST_FILE.unlink()
        logger.info("Blacklist has been cleared")
    except Exception as e:
        logger.error(f"Error clearing blacklist: {e}")

def load_blacklist():
    """从文件加载黑名单"""
    # 如果黑名单功能被禁用，返回空字典
    if not ENABLE_BLACKLIST:
        return {}
        
    # 如果配置了启动时清空黑名单，则清空
    if CLEAR_ON_START:
        clear_blacklist()
        return {}
        
    ensure_data_directory()
    if not BLACKLIST_FILE.exists():
        return {}
    try:
        with open(BLACKLIST_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading blacklist: {e}")
        return {}

def save_blacklist(blacklist):
    """保存黑名单到文件"""
    # 如果黑名单功能被禁用，不保存
    if not ENABLE_BLACKLIST:
        return
        
    ensure_data_directory()
    try:
        with open(BLACKLIST_FILE, 'w') as f:
            json.dump(blacklist, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving blacklist: {e}")

def add_to_blacklist(channel_id: str, reason: str):
    """添加频道到黑名单"""
    # 如果黑名单功能被禁用，直接返回
    if not ENABLE_BLACKLIST:
        logger.info("Channel blacklist is disabled, skipping blacklist addition")
        return
        
    blacklist = load_blacklist()
    blacklist[channel_id] = {
        'reason': reason,
        'timestamp': datetime.now().isoformat()
    }
    save_blacklist(blacklist)
    logger.info(f"Added channel {channel_id} to blacklist: {reason}")

def remove_from_blacklist(channel_id: str):
    """从黑名单中移除频道"""
    # 如果黑名单功能被禁用，直接返回
    if not ENABLE_BLACKLIST:
        return False
        
    blacklist = load_blacklist()
    if channel_id in blacklist:
        del blacklist[channel_id]
        save_blacklist(blacklist)
        logger.info(f"Removed channel {channel_id} from blacklist")
        return True
    return False

def is_blacklisted(channel_id: str) -> bool:
    """检查频道是否在黑名单中"""
    # 如果黑名单功能被禁用，始终返回False
    if not ENABLE_BLACKLIST:
        return False
        
    blacklist = load_blacklist()
    return channel_id in blacklist

def get_blacklist_info(channel_id: str) -> dict:
    """获取频道的黑名单信息"""
    # 如果黑名单功能被禁用，返回空字典
    if not ENABLE_BLACKLIST:
        return {}
        
    blacklist = load_blacklist()
    return blacklist.get(channel_id, {}) 