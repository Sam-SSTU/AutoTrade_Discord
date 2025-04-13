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
from ..ai import ai_message_handler
from ..ai.models import AIMessage

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

    async def get_forum_threads(self, channel_id: str) -> List[Dict[str, Any]]:
        """获取论坛频道的所有帖子"""
        try:
            await self._create_session()
            all_threads = set()  # 使用集合避免重复
            
            # 1. 通过搜索API获取活跃帖子
            start_msg = "尝试获取所有帖子..."
            print(start_msg)
            message_logger.info(start_msg)
            offset = 0
            has_more = True
            
            while has_more:
                url = f'https://discord.com/api/v9/channels/{channel_id}/threads/search'
                params = {
                    'limit': 25,  # Discord 限制最大为 25
                    'offset': offset,
                    'sort_by': 'last_message_time',
                    'sort_order': 'desc'
                }
                
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        threads_data = await response.json()
                        threads = threads_data.get('threads', [])
                        total_results = threads_data.get('total_results', 0)
                        
                        if not threads:
                            has_more = False
                            continue
                        
                        for thread in threads:
                            thread_data = {
                                'id': thread.get('id'),
                                'name': thread.get('name'),
                                'archived': thread.get('archived', False),
                                'created_at': thread.get('thread_metadata', {}).get('create_timestamp'),
                                'owner_id': thread.get('owner_id'),
                                'parent_id': channel_id
                            }
                            all_threads.add(json.dumps(thread_data))
                        
                        # 更新 offset
                        offset += len(threads)
                        # 如果已经获取了所有结果，停止
                        if offset >= total_results or len(threads) < 25:
                            has_more = False
                    else:
                        error_msg = f"获取活跃帖子失败: {response.status}\n错误响应: {await response.text()}"
                        print(error_msg)
                        message_logger.error(error_msg)
                        has_more = False
            
            threads_found_msg = f"从搜索中发现 {len(all_threads)} 个帖子"
            print(threads_found_msg)
            message_logger.info(threads_found_msg)
            
            # 2. 获取已归档帖子
            archive_msg = "尝试获取已归档帖子..."
            print(archive_msg)
            message_logger.info(archive_msg)
            url = f'https://discord.com/api/v9/channels/{channel_id}/threads/archived/public'
            params = {'limit': 100}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    archived_data = await response.json()
                    archived_threads = archived_data.get('threads', [])
                    for thread in archived_threads:
                        thread_data = {
                            'id': thread.get('id'),
                            'name': thread.get('name'),
                            'archived': True,
                            'created_at': thread.get('thread_metadata', {}).get('create_timestamp'),
                            'owner_id': thread.get('owner_id'),
                            'parent_id': channel_id
                        }
                        all_threads.add(json.dumps(thread_data))
                    archived_msg = f"获取到 {len(archived_threads)} 个已归档帖子"
                    print(archived_msg)
                    message_logger.info(archived_msg)
                else:
                    error_msg = f"获取已归档帖子失败: {response.status}\n错误响应: {await response.text()}"
                    print(error_msg)
                    message_logger.error(error_msg)
            
            # 将JSON字符串转回字典
            return [json.loads(t) for t in all_threads]
            
        except Exception as e:
            error_msg = f"获取论坛帖子出错: {str(e)}"
            print(error_msg)
            message_logger.error(error_msg)
            message_logger.error(traceback.format_exc())
            return []

    async def sync_channels_to_db(self, db: Session):
        """同步频道信息到数据库，检查权限并标记不可访问的频道"""
        try:
            # 发送开始同步通知到 Telegram
            start_msg = "🚀 开始同步 Discord 频道和帖子..."
            print(start_msg)
            message_logger.info(start_msg, extra={'startup_msg': True})
            
            await self._create_session()
            accessible_count = 0
            inaccessible_count = 0
            thread_count = 0
            
            # 获取用户所在的所有服务器
            guild_msg = "正在获取服务器列表..."
            print(guild_msg)
            message_logger.info(guild_msg)
            async with self.session.get('https://discord.com/api/v9/users/@me/guilds') as response:
                if response.status != 200:
                    error_msg = f"获取服务器列表失败: HTTP {response.status}"
                    print(error_msg)
                    message_logger.error(error_msg)
                    raise Exception("Failed to fetch guilds")
                    
                guilds = await response.json()
                guild_found_msg = f"发现 {len(guilds)} 个服务器"
                print(guild_found_msg)
                message_logger.info(guild_found_msg)
                
                for guild in guilds:
                    guild_id = guild['id']
                    guild_name = guild['name']
                    guild_process_msg = f"正在处理服务器: {guild_name} (ID: {guild_id})"
                    print(guild_process_msg)
                    message_logger.info(guild_process_msg)
                    
                    # 获取服务器中的所有频道
                    channel_list_msg = f"正在获取服务器 {guild_name} 的频道列表..."
                    print(channel_list_msg)
                    message_logger.info(channel_list_msg)
                    async with self.session.get(f'https://discord.com/api/v9/guilds/{guild_id}/channels') as channels_response:
                        if channels_response.status != 200:
                            error_msg = f"获取服务器 {guild_name} 的频道列表失败: HTTP {channels_response.status}"
                            print(error_msg)
                            message_logger.error(error_msg)
                            continue
                            
                        channels = await channels_response.json()
                        channels_found_msg = f"在服务器 {guild_name} 中发现 {len(channels)} 个频道"
                        print(channels_found_msg)
                        message_logger.info(channels_found_msg)
                        
                        # 创建一个映射来存储分类信息
                        categories = {}
                        
                        # 首先处理所有Discord分类
                        category_count = 0
                        for channel in channels:
                            if channel.get('type') == 4:  # Discord分类
                                categories[channel['id']] = channel
                                category_count += 1
                        
                        categories_msg = f"发现 {category_count} 个分类"
                        print(categories_msg)
                        message_logger.info(categories_msg)
                        
                        # 处理所有频道
                        for channel_data in channels:
                            try:
                                channel_id = channel_data.get('id')
                                channel_name = channel_data.get('name', '未知频道')
                                channel_type = channel_data.get('type', 0)
                                parent_id = channel_data.get('parent_id')
                                position = channel_data.get('position', 0)
                                
                                process_channel_msg = f"处理频道: {channel_name} (ID: {channel_id}, 类型: {channel_type})"
                                print(process_channel_msg)
                                message_logger.info(process_channel_msg)
                                
                                # 如果是语音频道，跳过
                                if channel_type == 2:
                                    skip_msg = f"跳过语音频道: {channel_name}"
                                    print(skip_msg)
                                    message_logger.info(skip_msg)
                                    continue
                                
                                # 检查频道权限（只检查文字频道和论坛频道）
                                has_access = True if channel_type == 4 else await self._check_channel_access(channel_id)
                                access_msg = f"频道 {channel_name} 权限检查结果: {'有权限' if has_access else '无权限'}"
                                print(access_msg)
                                message_logger.info(access_msg)
                                
                                # 获取分类名称
                                category_name = None
                                if parent_id and parent_id in categories:
                                    category_name = categories[parent_id].get('name')
                                
                                # 更新或创建频道记录
                                channel = db.query(Channel).filter(
                                    Channel.platform_channel_id == str(channel_id)
                                ).first()
                                
                                if not channel:
                                    channel = Channel(
                                        platform_channel_id=str(channel_id),
                                        name=channel_name,
                                        guild_id=str(guild_id),
                                        guild_name=guild_name,
                                        type=channel_type,
                                        parent_id=str(parent_id) if parent_id else None,
                                        category_name=category_name,
                                        is_active=has_access,
                                        position=position
                                    )
                                    db.add(channel)
                                else:
                                    channel.name = channel_name
                                    channel.guild_name = guild_name
                                    channel.type = channel_type
                                    channel.parent_id = str(parent_id) if parent_id else None
                                    channel.category_name = category_name
                                    channel.is_active = has_access
                                    channel.position = position
                                
                                db.commit()
                                
                                if has_access:
                                    accessible_count += 1
                                    
                                    # 如果是论坛频道，同步帖子
                                    if channel_type == 15:  # Discord论坛频道类型
                                        forum_sync_msg = f"正在同步论坛 {channel_name} 的帖子..."
                                        print(forum_sync_msg)
                                        message_logger.info(forum_sync_msg)
                                        try:
                                            threads = await self.get_forum_threads(channel_id)
                                            for thread_data in threads:
                                                thread_id = thread_data.get('id')
                                                thread_name = thread_data.get('name', '未知帖子')
                                                is_archived = thread_data.get('archived', False)
                                                
                                                # 创建或更新帖子作为子频道
                                                thread = db.query(Channel).filter(
                                                    Channel.platform_channel_id == str(thread_id)
                                                ).first()
                                                
                                                if not thread:
                                                    thread = Channel(
                                                        platform_channel_id=str(thread_id),
                                                        name=thread_name,
                                                        guild_id=str(guild_id),
                                                        guild_name=guild_name,
                                                        type=11,  # Discord 帖子类型
                                                        parent_id=str(channel_id),
                                                        category_name=channel_name,
                                                        is_active=False if is_archived else True,
                                                        position=0,
                                                        owner_id=thread_data.get('owner_id')  # 添加帖子创建者ID
                                                    )
                                                    db.add(thread)
                                                    thread_count += 1
                                                else:
                                                    thread.name = thread_name
                                                    if is_archived:  # 如果是已归档帖子，直接设置为False
                                                        thread.is_active = False
                                                
                                                db.commit()
                                            
                                            forum_threads_msg = f"论坛 {channel_name} 同步了 {len(threads)} 个帖子"
                                            print(forum_threads_msg)
                                            message_logger.info(forum_threads_msg)
                                        except Exception as e:
                                            error_msg = f"同步论坛 {channel_name} 帖子失败: {str(e)}"
                                            print(error_msg)
                                            message_logger.error(error_msg)
                                else:
                                    inaccessible_count += 1
                                
                            except Exception as e:
                                error_msg = f"处理频道 {channel_name} 时出错: {str(e)}"
                                print(error_msg)
                                message_logger.error(error_msg)
                                continue
            
            # 发送同步完成通知到 Telegram
            final_msg = f"""🎉 Discord 频道同步完成:
- {accessible_count} 个可访问频道
- {inaccessible_count} 个无权限频道
- {thread_count} 个论坛帖子"""
            print(final_msg)
            message_logger.info(final_msg, extra={'startup_msg': True})
            
            return {
                "accessible_count": accessible_count,
                "inaccessible_count": inaccessible_count,
                "thread_count": thread_count
            }
            
        except Exception as e:
            error_msg = f"❌ Discord 频道同步出错: {str(e)}"
            print(error_msg)
            message_logger.error(error_msg, extra={'startup_msg': True})
            message_logger.error(traceback.format_exc())
            raise e

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
            # Check if message already exists
            platform_message_id = str(message_data.get('id'))
            if not platform_message_id:
                message_logger.error("Message ID not found in message data")
                return
                
            existing_message = db.query(Message).filter(
                Message.platform_message_id == platform_message_id
            ).first()
            
            if existing_message:
                message_logger.info(f"消息已存在，跳过: {platform_message_id}")
                return
            
            # Get channel
            channel_id = str(message_data.get('channel_id'))
            if not channel_id:
                message_logger.error("Channel ID not found in message data")
                return
                
            channel = db.query(Channel).filter(
                Channel.platform_channel_id == channel_id
            ).first()
            
            if not channel:
                message_logger.error(f"Channel not found: {channel_id}")
                return

            # 如果是帖子类型的频道，使用帖子名称作为KOL名称
            if channel.type == 11:  # Discord帖子类型
                # 使用帖子名称作为KOL标识
                kol = db.query(KOL).filter(
                    KOL.platform == Platform.DISCORD.value,
                    KOL.name == channel.name  # 使用帖子名称作为KOL名称
                ).first()
                
                if not kol:
                    kol = KOL(
                        name=channel.name,  # 使用帖子名称
                        platform=Platform.DISCORD.value,
                        platform_user_id=channel.platform_channel_id,  # 使用帖子ID作为platform_user_id
                        is_active=True
                    )
                    db.add(kol)
                    db.commit()
            else:
                # 对于非帖子类型的频道，使用原来的作者逻辑
                author = message_data.get('author', {})
                if not author:
                    message_logger.error(f"Author data not found in message: {platform_message_id}")
                    return
                    
                author_id = str(author.get('id'))
                if not author_id:
                    message_logger.error(f"Author ID not found in message data: {platform_message_id}")
                    return
                    
                kol = db.query(KOL).filter(
                    KOL.platform == Platform.DISCORD.value,
                    KOL.platform_user_id == author_id
                ).first()
                
                if not kol:
                    kol = KOL(
                        name=f"{author.get('username')}#{author.get('discriminator', '0')}",
                        platform=Platform.DISCORD.value,
                        platform_user_id=author_id,
                        is_active=True
                    )
                    db.add(kol)
                    db.commit()
            
            # Create message
            message = Message(
                platform_message_id=platform_message_id,
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

            # Forward message to AI module if enabled
            if channel.is_forwarding:
                db.refresh(message)  # Refresh to get the attachments relationship
                # Store message in AI handler and broadcast
                await ai_message_handler.store_message(db, message)
            
            message_logger.info(f"消息存储成功: {platform_message_id}")
            
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

    async def _store_attachment(self, attachment_data: Dict[str, Any], message_id: int, db: Session) -> None:
        """Store a message attachment in the database"""
        try:
            # Download the attachment
            async with self.session.get(attachment_data['url']) as response:
                if response.status != 200:
                    message_logger.error(f"Failed to download attachment: {attachment_data['filename']}")
                    return
                
                file_data = await response.read()
                
                # Create new attachment record
                attachment = Attachment(
                    message_id=message_id,
                    filename=attachment_data['filename'],
                    content_type=attachment_data.get('content_type', 'application/octet-stream'),
                    file_data=file_data
                )
                
                db.add(attachment)
                db.commit()
                
                message_logger.info(f"Successfully stored attachment: {attachment_data['filename']}")
                
        except Exception as e:
            message_logger.error(f"Error storing attachment: {str(e)}")
            db.rollback()

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