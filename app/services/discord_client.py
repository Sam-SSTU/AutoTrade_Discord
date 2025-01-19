import aiohttp
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
import os
from sqlalchemy.orm import Session
from pathlib import Path

from ..config.discord_config import (
    DISCORD_USER_TOKEN,
    DISCORD_USER_AGENT,
    REQUEST_DELAY,
    MAX_RETRIES,
    DISCORD_CHANNEL_IDS
)
from ..config.author_categories import get_author_category
from ..database import SessionLocal
from ..models.base import KOL, Message, Platform
from ..config.blacklist import (
    load_blacklist,
    add_to_blacklist,
    is_blacklisted,
    get_blacklist_info,
    ENABLE_BLACKLIST,
    CLEAR_ON_START
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DiscordClient:
    def __init__(self):
        self.api_base = "https://discord.com/api/v9"
        self.headers = {
            "Authorization": DISCORD_USER_TOKEN,
            "User-Agent": DISCORD_USER_AGENT,
            "Content-Type": "application/json"
        }
        self.session: Optional[aiohttp.ClientSession] = None
        self._last_request_time = 0
        
        # 添加权限错误计数器
        self.permission_error_counts = {}
        self.MAX_PERMISSION_ERRORS = 3
        
        # 验证配置
        if not DISCORD_USER_TOKEN:
            raise ValueError("Discord user token is not configured")
            
        # 从配置获取频道ID
        self.channel_ids = DISCORD_CHANNEL_IDS
        if not self.channel_ids or not self.channel_ids[0]:
            raise ValueError("No Discord channel IDs configured")
        
        # 显示黑名单配置状态
        logger.info(f"Channel blacklist status:")
        logger.info(f"- Enabled: {ENABLE_BLACKLIST}")
        logger.info(f"- Clear on start: {CLEAR_ON_START}")
        
        # 加载黑名单信息
        blacklist = load_blacklist()
        if blacklist:
            logger.info("Loaded blacklisted channels:")
            for channel_id, info in blacklist.items():
                logger.info(f"- Channel {channel_id}: {info['reason']} (since {info['timestamp']})")
        else:
            logger.info("No channels in blacklist")
        
        logger.info(f"Initialized Discord client with {len(self.channel_ids)} channels to monitor")

    async def _init_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession(headers=self.headers)

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def _handle_rate_limit(self):
        current_time = datetime.now().timestamp()
        time_since_last = current_time - self._last_request_time
        if time_since_last < REQUEST_DELAY:
            await asyncio.sleep(REQUEST_DELAY - time_since_last)
        self._last_request_time = datetime.now().timestamp()

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        await self._init_session()
        await self._handle_rate_limit()

        url = f"{self.api_base}{endpoint}"
        logger.info(f"Making {method} request to {url}")

        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Request attempt {attempt + 1}/{MAX_RETRIES}")
                async with self.session.request(method, url, **kwargs) as response:
                    response_text = await response.text()
                    logger.info(f"Response status: {response.status}")
                    logger.info(f"Response text: {response_text[:200]}...")  # Log first 200 chars
                    
                    try:
                        response_data = json.loads(response_text)
                        logger.info("Successfully parsed JSON response")
                    except json.JSONDecodeError:
                        response_data = response_text
                        logger.warning("Could not parse response as JSON, using raw text")
                    
                    if response.status == 429:  # Rate limited
                        retry_after = float(response_data.get("retry_after", 5))
                        logger.warning(f"Rate limited, waiting {retry_after} seconds")
                        await asyncio.sleep(retry_after)
                        continue
                    
                    if response.status == 401:
                        logger.error("Authentication failed. Token might be invalid or expired.")
                        raise Exception("Authentication failed")
                    
                    if response.status == 403:
                        error_msg = f"Permission denied: {response_data.get('message', 'No access to the requested resource')}"
                        logger.error(error_msg)
                        raise Exception(error_msg)
                    
                    if response.status == 404:
                        error_msg = f"Resource not found: {response_data.get('message', 'The requested resource does not exist')}"
                        logger.error(error_msg)
                        raise Exception(error_msg)
                    
                    response.raise_for_status()
                    return response_data
                    
            except aiohttp.ClientError as e:
                logger.error(f"Network error on attempt {attempt + 1}: {str(e)}")
                if attempt == MAX_RETRIES - 1:
                    raise
                await asyncio.sleep(1 * (attempt + 1))
            except Exception as e:
                logger.error(f"Error on attempt {attempt + 1}: {str(e)}")
                if attempt == MAX_RETRIES - 1:
                    raise
                await asyncio.sleep(1 * (attempt + 1))

    async def get_channel_messages(self, channel_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """获取频道的最新消息"""
        logger.info(f"Fetching messages from channel {channel_id}")
        try:
            return await self._make_request(
                "GET",
                f"/channels/{channel_id}/messages",
                params={"limit": limit}
            )
        except Exception as e:
            logger.error(f"Failed to fetch messages from channel {channel_id}: {str(e)}")
            raise

    async def get_message(self, channel_id: int, message_id: int) -> Dict[str, Any]:
        """获取特定消息的详细信息"""
        logger.info(f"Fetching message {message_id} from channel {channel_id}")
        return await self._make_request(
            "GET",
            f"/channels/{channel_id}/messages/{message_id}"
        )

    async def verify_token(self):
        """验证令牌是否有效并列出可用的频道"""
        try:
            user_data = await self._make_request("GET", "/users/@me")
            logger.info(f"成功验证身份: {user_data.get('username')}#{user_data.get('discriminator')}")
            
            # 获取用户所在的服务器列表
            guilds = await self.get_my_guilds()
            logger.info(f"\n=== 用户加入的服务器 ({len(guilds)}) ===")
            
            for guild in guilds:
                logger.info(f"\n服务器: {guild['name']} (ID: {guild['id']})")
                await self.list_guild_channels(guild['id'])
            
            return True
        except Exception as e:
            logger.error(f"Token 验证失败: {str(e)}")
            return False

    async def get_my_guilds(self) -> List[Dict]:
        """Get all guilds (servers) the bot has access to"""
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(f"{self.api_base}/users/@me/guilds") as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.error(f"Failed to get guilds: {response.status}")
                        return []
        except Exception as e:
            logger.error(f"Error getting guilds: {str(e)}")
            return []

    async def get_guild_channels(self, guild_id: str) -> List[Dict]:
        """Get all channels in a guild"""
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(f"{self.api_base}/guilds/{guild_id}/channels") as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.error(f"Failed to get channels for guild {guild_id}: {response.status}")
                        return []
        except Exception as e:
            logger.error(f"Error getting channels for guild {guild_id}: {str(e)}")
            return []

    async def verify_channel_access(self, channel_id: str) -> bool:
        try:
            # First get all guilds
            guilds = await self.get_my_guilds()
            
            # Log guilds found
            logger.info(f"Found {len(guilds)} guilds")
            for guild in guilds:
                logger.info(f"Guild: {guild['name']} (ID: {guild['id']}, Permissions: {guild.get('permissions', 'N/A')})")
                
                # Get channels for this guild
                channels = await self.get_guild_channels(guild['id'])
                logger.info(f"Found {len(channels)} channels in guild {guild['id']}")
                
                # Log all channels
                for channel in channels:
                    logger.info(f"Channel: {channel['name']} (ID: {channel['id']}, Type: {channel.get('type', 'N/A')})")
                    
                    # If we find our target channel, try to access it
                    if str(channel['id']) == channel_id:
                        try:
                            # Try to get channel info
                            channel_info = await self.get_channel_info(channel_id)
                            if channel_info:
                                logger.info(f"Successfully accessed channel {channel_info['name']} (ID: {channel_id})")
                                return True
                            else:
                                logger.error(f"Cannot access channel {channel_id} in guild {guild['name']} due to permission issues")
                                return False
                        except Exception as e:
                            logger.error(f"Cannot access channel {channel_id} in guild {guild['name']}: {str(e)}")
                            return False
            
            # If we get here, we didn't find the channel in any guild
            logger.error(f"Channel {channel_id} not found in any accessible guilds")
            return False
            
        except Exception as e:
            logger.error(f"Cannot access channel {channel_id}. Error: {str(e)}")
            return False

    async def get_channel_info(self, channel_id: str) -> Optional[Dict]:
        """Get information about a specific channel"""
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(f"{self.api_base}/channels/{channel_id}") as response:
                    response_text = await response.text()
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 403:
                        logger.error(f"Permission denied for channel {channel_id}. Response: {response_text}")
                        return None
                    else:
                        logger.error(f"Failed to get channel info for {channel_id}: Status {response.status}, Response: {response_text}")
                        return None
        except Exception as e:
            logger.error(f"Error getting channel info for {channel_id}: {str(e)}")
            return None

    async def store_message(self, message_data: Dict[str, Any], db: Session):
        """将消息存储到数据库"""
        try:
            # 获取或创建作者
            author_data = message_data["author"]
            author = db.query(KOL).filter(KOL.platform_user_id == author_data["id"]).first()
            if not author:
                author = KOL(
                    platform_user_id=author_data["id"],
                    name=f"{author_data['username']}#{author_data['discriminator']}",
                    platform=Platform.DISCORD,
                    category=get_author_category(message_data["channel_id"]),
                    is_active=True
                )
                db.add(author)
                db.commit()
                logger.info(f"Created new author: {author.name}")
            
            # 处理引用消息
            referenced_message_id = None
            referenced_content = None
            is_reply = False
            reply_content = None
            
            if message_data.get("referenced_message"):
                is_reply = True
                referenced_message = message_data["referenced_message"]
                referenced_message_id = referenced_message["id"]
                referenced_content = referenced_message.get("content", "")
                reply_content = message_data["content"]  # 当前消息是回复内容
                
                logger.info(f"Processing reply message:")
                logger.info(f"- Referenced message: {referenced_content[:100]}...")
                logger.info(f"- Reply content: {reply_content[:100]}...")
            
            # 创建消息记录
            message = Message(
                platform_message_id=message_data["id"],
                kol_id=author.id,
                platform=Platform.DISCORD,
                channel_id=message_data["channel_id"],
                content=message_data["content"],
                attachments=message_data.get("attachments", []),
                embeds=message_data.get("embeds", []),
                referenced_message_id=referenced_message_id,
                referenced_content=referenced_content,
                is_reply=is_reply,
                reply_content=reply_content,
                created_at=datetime.fromisoformat(message_data["timestamp"].rstrip("Z"))
            )
            
            db.add(message)
            db.commit()
            
            # 记录消息详情
            log_message = f"Stored message {message.platform_message_id} from {author.name}"
            if message.is_reply:
                log_message += f"\n引用消息: {message.referenced_content[:100]}..."
                log_message += f"\n回复内容: {message.reply_content[:100]}..."
            else:
                log_message += f"\n消息内容: {message.content[:100]}..."
            
            if message.attachments:
                log_message += f"\n附件: {len(message.attachments)} 个文件"
            if message.embeds:
                log_message += f"\n嵌入内容: {len(message.embeds)} 个"
            
            logger.info(log_message)
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error storing message: {str(e)}")
            raise

    async def monitor_channels(self, callback):
        """Monitor channels for new messages."""
        logger.info("Starting channel monitoring")
        while True:
            try:
                for channel_id in self.channel_ids:
                    # 检查黑名单
                    if is_blacklisted(channel_id):
                        info = get_blacklist_info(channel_id)
                        logger.debug(f"Skipping blacklisted channel {channel_id} ({info.get('reason', 'Unknown reason')})")
                        continue
                        
                    try:
                        logger.info(f"Checking channel {channel_id} for new messages")
                        
                        # Get the latest message from the channel
                        endpoint = f"/channels/{channel_id}/messages?limit=1"
                        logger.info(f"Making request to endpoint: {endpoint}")
                        
                        messages = await self._make_request("GET", endpoint)
                        logger.info(f"Retrieved {len(messages) if messages else 0} messages")
                        
                        # 成功访问后重置错误计数
                        self.permission_error_counts[channel_id] = 0
                        
                        if messages and len(messages) > 0:
                            logger.info(f"Processing message: {messages[0].get('id')}")
                            # Store the last message in database and call callback
                            await callback(messages[0])
                            logger.info(f"Successfully processed message from channel {channel_id}")
                        else:
                            logger.info(f"No new messages found in channel {channel_id}")
                            
                    except Exception as e:
                        if "403" in str(e) or "Permission denied" in str(e):
                            # 增加权限错误计数
                            self.permission_error_counts[channel_id] = self.permission_error_counts.get(channel_id, 0) + 1
                            
                            if self.permission_error_counts[channel_id] >= self.MAX_PERMISSION_ERRORS:
                                reason = f"Exceeded maximum permission errors ({self.MAX_PERMISSION_ERRORS})"
                                add_to_blacklist(channel_id, reason)
                                logger.warning(f"Channel {channel_id} has been blacklisted: {reason}")
                            else:
                                logger.warning(f"Permission denied for channel {channel_id} (Attempt {self.permission_error_counts[channel_id]}/{self.MAX_PERMISSION_ERRORS}): {str(e)}")
                                
                        elif "404" in str(e):
                            reason = "Channel not found (404)"
                            add_to_blacklist(channel_id, reason)
                            logger.warning(f"Channel {channel_id} has been blacklisted: {reason}")
                        else:
                            logger.error(f"Error accessing channel {channel_id}: {str(e)}")
                        continue
                
                logger.info("Completed channel check cycle, waiting 5 seconds before next cycle")
                await asyncio.sleep(5)  # Wait before next iteration
                
            except Exception as e:
                logger.error(f"Error in monitor_channels: {str(e)}")
                logger.info("Waiting 5 seconds before retrying")
                await asyncio.sleep(5)  # Wait before retrying

    @staticmethod
    def extract_message_data(message: Dict[str, Any]) -> Dict[str, Any]:
        """从Discord消息中提取关键信息"""
        return {
            "id": message.get("id"),
            "channel_id": message.get("channel_id"),
            "author": {
                "id": message.get("author", {}).get("id"),
                "username": message.get("author", {}).get("username"),
                "discriminator": message.get("author", {}).get("discriminator")
            },
            "content": message.get("content"),
            "timestamp": message.get("timestamp"),
            "referenced_message": message.get("referenced_message"),
            "attachments": message.get("attachments", []),
            "embeds": message.get("embeds", [])
        }

    async def list_guild_channels(self, guild_id: str):
        """列出指定服务器中的所有频道"""
        try:
            channels = await self._make_request("GET", f"/guilds/{guild_id}/channels")
            logger.info(f"\n=== 服务器 {guild_id} 中的频道列表 ===")
            logger.info(f"总计找到 {len(channels)} 个频道")
            
            # 按频道类型分类
            text_channels = [c for c in channels if c.get('type') == 0]  # 0 表示文字频道
            voice_channels = [c for c in channels if c.get('type') == 2]  # 2 表示语音频道
            category_channels = [c for c in channels if c.get('type') == 4]  # 4 表示分类
            
            # 打印分类信息
            logger.info(f"\n=== 分类 ({len(category_channels)}) ===")
            for channel in category_channels:
                logger.info(f"- {channel.get('name')} (ID: {channel.get('id')})")
            
            logger.info(f"\n=== 文字频道 ({len(text_channels)}) ===")
            for channel in text_channels:
                parent = next((c.get('name') for c in category_channels if c.get('id') == channel.get('parent_id')), "无分类")
                logger.info(f"- {channel.get('name')} (ID: {channel.get('id')}) [分类: {parent}]")
            
            logger.info(f"\n=== 语音频道 ({len(voice_channels)}) ===")
            for channel in voice_channels:
                parent = next((c.get('name') for c in category_channels if c.get('id') == channel.get('parent_id')), "无分类")
                logger.info(f"- {channel.get('name')} (ID: {channel.get('id')}) [分类: {parent}]")
            
            return channels
        except Exception as e:
            logger.error(f"获取服务器 {guild_id} 的频道列表失败: {str(e)}")
            return []

    def _load_blacklist(self) -> Dict[str, Dict[str, str]]:
        """加载黑名单"""
        if self.blacklist_file.exists():
            try:
                with open(self.blacklist_file, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.warning("Failed to load blacklist file, starting with empty blacklist")
        return {}

    def _save_blacklist(self):
        """保存黑名单"""
        with open(self.blacklist_file, "w") as f:
            json.dump(self.blacklist, f, indent=2)

    def get_blacklist(self) -> List[Dict[str, str]]:
        """获取黑名单列表"""
        return [
            {
                "channel_id": channel_id,
                "reason": info["reason"],
                "timestamp": info["timestamp"]
            }
            for channel_id, info in self.blacklist.items()
        ]

    def add_to_blacklist(self, channel_id: str, reason: str):
        """添加频道到黑名单"""
        self.blacklist[channel_id] = {
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat()
        }
        self._save_blacklist()
        logger.info(f"Added channel {channel_id} to blacklist: {reason}")

    def remove_from_blacklist(self, channel_id: str):
        """从黑名单中移除频道"""
        if channel_id in self.blacklist:
            del self.blacklist[channel_id]
            self._save_blacklist()
            logger.info(f"Removed channel {channel_id} from blacklist")

    def is_blacklisted(self, channel_id: str) -> bool:
        """检查频道是否在黑名单中"""
        return channel_id in self.blacklist 