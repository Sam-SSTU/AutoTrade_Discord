from typing import Dict, List

# 监听的频道配置
MONITORED_CHANNELS: List[str] = [
    "1004716337219764274",  # 示例频道ID
    "1004710056127889509"   # 示例频道ID
]

# 频道分类映射
CHANNEL_CATEGORIES: Dict[str, str] = {
    "1004716337219764274": "news",
    "1004710056127889509": "discussion"
}

def is_monitored_channel(channel_id: str) -> bool:
    """检查是否是需要监听的频道"""
    return channel_id in MONITORED_CHANNELS

def get_author_category(channel_id: str) -> str:
    """获取作者分类"""
    return CHANNEL_CATEGORIES.get(channel_id, "default") 