import aiohttp
import asyncio
import json
import logging
import os
from typing import Callable, Dict, Any, List
import traceback
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from ..config.author_categories import is_monitored_channel, get_author_category
from ..database import SessionLocal
from ..models.base import Message, KOL, Platform, Channel, Attachment, UnreadMessage
from ..services.message_utils import extract_message_content
from .file_utils import FileHandler

# 创建Message Logs记录器
message_logger = logging.getLogger("Message Logs")

class DiscordClient:
    def __init__(self):
        self._token = os.getenv("DISCORD_USER_TOKEN")
        if not self._token:
            raise ValueError("Discord token not found in environment variables")
        
        self.message_callback = None
        self.session = None
        self.ws = None
        self._heartbeat_interval = None
        self._last_sequence = None
        self._running = False
        self.file_handler = FileHandler()
        self.connected_websockets = set()
        
        message_logger.info("Discord客户端已初始化")
        
    async def _create_session(self):
        """创建 HTTP 会话"""
        if self.session is None:
            self.session = aiohttp.ClientSession(headers={
                'Authorization': self._token,  # 直接使用token，不需要加Bot前缀
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Content-Type': 'application/json'
            })
            
    async def _heartbeat(self):
        """发送心跳包"""
        while self._running:
            if self._heartbeat_interval:
                payload = {
                    'op': 1,
                    'd': self._last_sequence
                }
                try:
                    await self.ws.send_json(payload)
                except Exception as e:
                    message_logger.error(f"心跳包发送错误")
                    break
                await asyncio.sleep(self._heartbeat_interval / 1000)
                
    async def _identify(self):
        """发送身份验证信息"""
        payload = {
            'op': 2,
            'd': {
                'token': self._token,
                'capabilities': 16381,
                'properties': {
                    'os': 'Mac OS X',
                    'browser': 'Chrome',
                    'device': '',
                    'system_locale': 'zh-CN',
                    'browser_user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'browser_version': '120.0.0.0',
                    'os_version': '10.15.7',
                    'referrer': '',
                    'referring_domain': '',
                    'referrer_current': '',
                    'referring_domain_current': '',
                    'release_channel': 'stable',
                    'client_build_number': 260672,
                    'client_event_source': None
                },
                'presence': {
                    'status': 'online',
                    'since': 0,
                    'activities': [],
                    'afk': False
                },
                'compress': False,
                'client_state': {
                    'guild_versions': {},
                    'highest_last_message_id': '0',
                    'read_state_version': 0,
                    'user_guild_settings_version': -1,
                    'user_settings_version': -1,
                    'private_channels_version': '0',
                    'api_code_version': 0
                }
            }
        }
        await self.ws.send_json(payload)
        
    async def start_monitoring(self, callback: Callable):
        """开始监听消息"""
        message_logger.info("开始监听Discord消息")
        self.message_callback = callback
        self._running = True
        
        try:
            await self._create_session()
            
            async with self.session.ws_connect(
                'wss://gateway.discord.gg/?v=9&encoding=json',
                heartbeat=self._heartbeat_interval
            ) as self.ws:
                # 启动心跳
                heartbeat_task = asyncio.create_task(self._heartbeat())
                
                # 发送身份验证
                await self._identify()
                
                async for msg in self.ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        op = data.get('op')
                        
                        if op == 10:  # Hello
                            self._heartbeat_interval = data['d']['heartbeat_interval']
                        elif op == 0:  # Dispatch
                            self._last_sequence = data.get('s')
                            event_type = data.get('t')
                            
                            if event_type == 'MESSAGE_CREATE':
                                event_data = data.get('d')
                                try:
                                    if not event_data:
                                        message_logger.error("消息数据为空")
                                        return
                                    
                                    await self.message_callback(event_data)
                                except Exception as e:
                                    message_logger.error("消息处理错误")
                        
        except Exception as e:
            message_logger.error("WebSocket连接错误")
            raise
        finally:
            if heartbeat_task:
                heartbeat_task.cancel()
            if self.session:
                await self.session.close()
                
    async def close(self):
        """关闭客户端连接"""
        self._running = False
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()
        message_logger.info("Discord客户端已关闭")

    async def verify_token(self):
        """验证token是否有效"""
        try:
            await self._create_session()
            async with self.session.get('https://discord.com/api/v9/users/@me') as response:
                if response.status == 200:
                    message_logger.info("Discord token验证成功")
                    return True
                else:
                    message_logger.error("Discord token验证失败")
                    return False
        except Exception as e:
            message_logger.error("Discord token验证出错")
            return False

    async def get_channel_info(self, channel_id: str) -> Dict[str, Any]:
        """获取频道信息"""
        try:
            await self._create_session()
            async with self.session.get(f'https://discord.com/api/v9/channels/{channel_id}') as response:
                if response.status == 200:
                    data = await response.json()
                    message_logger.info(f"获取到频道信息: {data.get('name', '未知频道')}")
                    return data
                else:
                    message_logger.error("获取频道信息失败")
                    return {}
        except Exception as e:
            message_logger.error("获取频道信息出错")
            return {}

    async def sync_channels_to_db(self, db: Session):
        """同步频道信息到数据库，检查权限并标记不可访问的频道"""
        try:
            await self._create_session()
            accessible_count = 0
            inaccessible_count = 0
            
            # 获取用户所在的所有服务器
            async with self.session.get('https://discord.com/api/v9/users/@me/guilds') as response:
                if response.status != 200:
                    message_logger.error("获取服务器列表失败")
                    raise Exception("Failed to fetch guilds")
                    
                guilds = await response.json()
                message_logger.info(f"发现 {len(guilds)} 个服务器")
                
                for guild in guilds:
                    guild_id = guild['id']
                    guild_name = guild['name']
                    message_logger.info(f"正在处理服务器: {guild_name}")
                    
                    # 获取服务器中的所有频道
                    async with self.session.get(f'https://discord.com/api/v9/guilds/{guild_id}/channels') as channels_response:
                        if channels_response.status != 200:
                            message_logger.error(f"获取服务器 {guild_name} 的频道列表失败")
                            continue
                            
                        channels = await channels_response.json()
                        text_channels = [c for c in channels if c.get('type') == 0]
                        message_logger.info(f"服务器 {guild_name} 中发现 {len(text_channels)} 个文字频道")
                        
                        for channel_data in text_channels:
                            try:
                                channel_id = channel_data.get('id')
                                channel_name = channel_data.get('name', '未知频道')
                                
                                message_logger.info(f"正在检查频道权限: {channel_name}")
                                
                                # 检查频道权限
                                has_access = await self._check_channel_access(channel_id)
                                
                                # 检查频道是否已存在
                                channel = db.query(Channel).filter(
                                    Channel.platform_channel_id == str(channel_id)
                                ).first()
                                
                                if not channel:
                                    channel = Channel(
                                        platform_channel_id=str(channel_id),
                                        name=channel_name,
                                        guild_id=str(guild_id),
                                        guild_name=guild_name,
                                        is_active=has_access
                                    )
                                    db.add(channel)
                                    if has_access:
                                        message_logger.info(f"添加新频道: {channel_name}")
                                    else:
                                        message_logger.info(f"添加无权限频道: {channel_name}")
                                else:
                                    # 更新频道状态
                                    old_status = channel.is_active
                                    channel.is_active = has_access
                                    if old_status != has_access:
                                        if has_access:
                                            message_logger.info(f"频道已重新激活: {channel_name}")
                                        else:
                                            message_logger.info(f"频道已失去权限: {channel_name}")
                                    else:
                                        message_logger.info(f"频道状态未变: {channel_name} ({'有权限' if has_access else '无权限'})")
                                            
                                if has_access:
                                    accessible_count += 1
                                else:
                                    inaccessible_count += 1
                                
                                # 立即提交每个频道的更改
                                db.commit()
                                
                            except Exception as e:
                                message_logger.error(f"处理频道 {channel_name} 时出错: {str(e)}")
                                db.rollback()
                                continue
                    
                    # 每个服务器处理完后等待一下，避免触发限制
                    await asyncio.sleep(1)
                
                message_logger.info(f"频道同步完成: {accessible_count} 个可访问, {inaccessible_count} 个无权限")
                return {
                    "accessible_count": accessible_count,
                    "inaccessible_count": inaccessible_count
                }
                
        except Exception as e:
            message_logger.error(f"同步频道信息出错: {str(e)}")
            db.rollback()
            raise

    async def _check_channel_access(self, channel_id: str) -> bool:
        """检查是否有权限访问频道"""
        try:
            # 尝试获取频道的一条消息来测试权限
            async with self.session.get(
                f'https://discord.com/api/v9/channels/{channel_id}/messages',
                params={'limit': 1}
            ) as response:
                if response.status == 200:
                    return True
                elif response.status in [403, 401] or (await response.json()).get('code') == 50001:
                    return False
                else:
                    # 其他错误视为无权限
                    return False
        except Exception:
            return False

    async def store_message(self, message_data: dict, db: Session) -> None:
        """Store a Discord message in the database"""
        try:
            # Get channel
            channel = db.query(Channel).filter(
                Channel.platform_channel_id == str(message_data.get('channel_id'))
            ).first()
            
            if not channel:
                message_logger.error(f"Channel not found: {message_data.get('channel_id')}")
                return
            
            # Get or create KOL
            author = message_data.get('author', {})
            kol = db.query(KOL).filter(
                KOL.platform_user_id == str(author.get('id'))
            ).first()
            
            if not kol:
                kol = KOL(
                    name=author.get('username'),
                    platform=Platform.DISCORD.value,
                    platform_user_id=str(author.get('id')),
                    is_active=True
                )
                db.add(kol)
                db.commit()
            
            # Create message
            message = Message(
                platform_message_id=str(message_data.get('id')),
                channel_id=channel.id,
                kol_id=kol.id,
                content=message_data.get('content'),
                embeds=json.dumps(message_data.get('embeds', [])),
                referenced_message_id=str(message_data.get('referenced_message', {}).get('id')) if message_data.get('referenced_message') else None,
                referenced_content=message_data.get('referenced_message', {}).get('content') if message_data.get('referenced_message') else None,
                created_at=datetime.fromisoformat(message_data.get('timestamp').replace('Z', '+00:00'))
            )
            
            db.add(message)
            db.commit()
            
            # Handle attachments
            for attachment_data in message_data.get('attachments', []):
                await self._store_attachment(attachment_data, message.id, db)
            
            # Increment unread count
            unread = db.query(UnreadMessage).filter(UnreadMessage.channel_id == channel.id).first()
            if unread:
                unread.unread_count += 1
            else:
                unread = UnreadMessage(
                    channel_id=channel.id,
                    unread_count=1
                )
                db.add(unread)
            db.commit()
            
            # Send WebSocket notification
            await self.broadcast_message({
                'type': 'new_message',
                'channel_id': channel.platform_channel_id,
                'channel_name': channel.name,
                'author_name': kol.name,
                'content': message.content,
                'created_at': message.created_at.isoformat()
            })
            
        except Exception as e:
            message_logger.error(f"Error storing message: {str(e)}")
            message_logger.error(traceback.format_exc())
            db.rollback()
            raise

    async def get_channel_messages(self, channel_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取频道的历史消息，支持分页"""
        all_messages = []
        before_id = None
        
        try:
            await self._create_session()
            
            while len(all_messages) < limit:
                params = {'limit': min(100, limit - len(all_messages))}
                if before_id:
                    params['before'] = before_id
                
                async with self.session.get(
                    f'https://discord.com/api/v9/channels/{channel_id}/messages',
                    params=params
                ) as response:
                    if response.status == 200:
                        messages = await response.json()
                        if not messages:  # 没有更多消息了
                            break
                            
                        all_messages.extend(messages)
                        
                        # 获取最后一条消息的ID用于下一次请求
                        before_id = messages[-1]['id']
                        
                        message_logger.info(f"已获取 {len(all_messages)}/{limit} 条历史消息")
                        
                        # 添加延迟避免触发限制
                        await asyncio.sleep(1)
                    else:
                        error_data = await response.json()
                        if response.status == 403 or response.status == 401 or error_data.get('code') == 50001:
                            message_logger.info(f"频道无访问权限，已跳过")
                        else:
                            message_logger.error(f"获取历史消息失败: {error_data.get('message', '未知错误')}")
                        break
                        
            return all_messages[:limit]  # 确保不超过请求的数量
            
        except Exception as e:
            message_logger.error(f"获取历史消息出错: {str(e)}")
            return []

    async def get_guild_channels(self, guild_id: str) -> List[Dict[str, Any]]:
        """获取服务器的所有频道"""
        try:
            await self._create_session()
            async with self.session.get(f'https://discord.com/api/v9/guilds/{guild_id}/channels') as response:
                if response.status == 200:
                    channels = await response.json()
                    message_logger.info(f"获取到{len(channels)}个服务器频道")
                    return channels
                else:
                    message_logger.error("获取服务器频道失败")
                    return []
        except Exception as e:
            message_logger.error("获取服务器频道出错")
            return []

    async def get_guild_info(self, guild_id: str) -> Dict[str, Any]:
        """获取服务器信息"""
        try:
            await self._create_session()
            async with self.session.get(f'https://discord.com/api/v9/guilds/{guild_id}') as response:
                if response.status == 200:
                    data = await response.json()
                    message_logger.info(f"获取到服务器信息: {data.get('name', '未知服务器')}")
                    return data
                else:
                    message_logger.error("获取服务器信息失败")
                    return {}
        except Exception as e:
            message_logger.error("获取服务器信息出错")
            return {}

    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """获取用户信息"""
        try:
            await self._create_session()
            async with self.session.get(f'https://discord.com/api/v9/users/{user_id}') as response:
                if response.status == 200:
                    data = await response.json()
                    message_logger.info(f"获取到用户信息: {data.get('username', '未知用户')}")
                    return data
                else:
                    message_logger.error("获取用户信息失败")
                    return {}
        except Exception as e:
            message_logger.error("获取用户信息出错")
            return {}

    def register_websocket(self, websocket):
        """Register a WebSocket connection"""
        self.connected_websockets.add(websocket)
        
    def unregister_websocket(self, websocket):
        """Unregister a WebSocket connection"""
        self.connected_websockets.discard(websocket)
        
    async def broadcast_message(self, message: Dict[str, Any]):
        """Broadcast a message to all connected WebSocket clients"""
        if not self.connected_websockets:
            return
            
        # Convert message to JSON string
        message_str = json.dumps(message)
        
        # Send to all connected clients
        for websocket in self.connected_websockets.copy():
            try:
                await websocket.send_text(message_str)
            except Exception as e:
                message_logger.error(f"Error broadcasting message: {str(e)}")
                self.connected_websockets.discard(websocket) 