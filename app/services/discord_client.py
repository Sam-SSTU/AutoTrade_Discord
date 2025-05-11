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
        
        # 从环境变量读取代理配置
        self.http_proxy = os.getenv("HTTP_PROXY")
        self.https_proxy = os.getenv("HTTPS_PROXY")
        
        if self.http_proxy and self.https_proxy:
            message_logger.info("Discord客户端已初始化，代理配置如下：")
            message_logger.debug(f"[配置] HTTP代理: {self.http_proxy}")
            message_logger.debug(f"[配置] HTTPS代理: {self.https_proxy}")
        else:
            message_logger.info("Discord客户端已初始化，未配置代理，将使用直接连接")
        
    def _get_proxy_for_url(self, url: str) -> str:
        """根据URL选择合适的代理"""
        # 如果代理环境变量为空，返回None
        if not self.http_proxy and not self.https_proxy:
            return None
            
        if url.startswith('https://') or url.startswith('wss://'):
            return self.https_proxy
        return self.http_proxy
        
    async def _create_session(self):
        """创建 HTTP 会话"""
        message_logger.debug("[会话] 开始创建HTTP会话")
        try:
            if self.session is None:
                message_logger.debug("[会话] 创建新的HTTP会话")
                # 检查token是否存在
                if not self._token:
                    message_logger.error("[严重错误] Discord token不存在")
                    raise ValueError("Discord token not found in environment variables")
                
                # 确保token不是空字符串
                if self._token.strip() == "":
                    message_logger.error("[严重错误] Discord token为空")
                    raise ValueError("Discord token is empty")
                
                # 记录token长度进行检查（不记录token本身以保护安全）
                token_length = len(self._token)
                message_logger.debug(f"[会话] Token长度: {token_length}字符")
                
                if token_length < 50:  # Discord tokens通常很长
                    message_logger.warning(f"[警告] Discord token可能无效，长度过短: {token_length}字符")
                
                message_logger.debug("[会话] 准备创建aiohttp会话")
                
                # 设置更合理的超时时间，避免请求卡住
                timeout = aiohttp.ClientTimeout(total=60, connect=20, sock_connect=20, sock_read=20)
                message_logger.debug(f"[会话] 配置超时参数: 总超时=60秒, 连接超时=20秒")
                
                try:
                    # 尝试明确关闭之前的会话（如果存在）
                    if hasattr(self, 'session') and self.session:
                        message_logger.debug("[会话] 尝试关闭现有会话")
                        try:
                            if not self.session.closed:
                                await self.session.close()
                                message_logger.debug("[会话] 成功关闭现有会话")
                        except Exception as e:
                            message_logger.warning(f"[会话] 关闭现有会话时出错: {str(e)}")
                            pass
                    
                    # 创建新会话
                    self.session = aiohttp.ClientSession(
                        headers={
                            'Authorization': self._token,
                            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                            'Content-Type': 'application/json'
                        },
                        timeout=timeout
                    )
                    message_logger.info("[会话] HTTP会话创建成功")
                except Exception as e:
                    message_logger.error(f"[会话] 创建ClientSession对象失败: {str(e)}")
                    message_logger.debug(f"[会话错误详情] {traceback.format_exc()}")
                    raise
            else:
                message_logger.debug("[会话] 使用现有HTTP会话")
                # 检查现有会话是否已关闭
                if self.session.closed:
                    message_logger.warning("[会话] 现有会话已关闭，创建新会话")
                    # 重置会话并递归调用
                    self.session = None
                    await self._create_session()
        except Exception as e:
            message_logger.error(f"[严重错误] 创建HTTP会话失败: {str(e)}")
            message_logger.debug(f"[会话错误详情] {traceback.format_exc()}")
            raise
        
    async def _heartbeat(self):
        """发送心跳包"""
        # 简单直接的心跳实现，无复杂逻辑
        try:
            message_logger.info("[WebSocket] 启动心跳任务")
            
            # 无限循环发送心跳
            while True:
                # 检查连接状态
                if not self._running or not self.ws or self.ws.closed:
                    message_logger.debug("[WebSocket] 连接已关闭或不再运行，结束心跳任务")
                    return
                
                # 如果心跳间隔未设置，等待后再检查
                if not self._heartbeat_interval:
                    await asyncio.sleep(1)
                    continue
                
                try:
                    # 发送心跳
                    payload = {'op': 1, 'd': self._last_sequence}
                    message_logger.debug(f"[WebSocket] 发送心跳 (序列号: {self._last_sequence})")
                    message_logger.debug(f"[WebSocket] 心跳发送前连接状态: closed={self.ws.closed if self.ws else 'N/A'}")
                    
                    # 设置最后发送心跳的时间
                    self.last_heartbeat_sent = asyncio.get_event_loop().time()
                    
                    # 发送消息
                    await self.ws.send_json(payload)
                    message_logger.debug(f"[WebSocket] 心跳已发送，当前时间戳: {self.last_heartbeat_sent}")
                    
                    # 关键变化：不等待整个心跳周期，只等待一个较短的时间
                    # 然后立即发送一个新的心跳，以保持连接活跃
                    # 计算等待时间 - 使用心跳间隔的一半时间 
                    wait_time = min(self._heartbeat_interval / 1000 / 2, 15)  # 最多等待15秒
                    message_logger.debug(f"[WebSocket] 将等待 {wait_time} 秒后继续")
                    
                    # 等待指定时间
                    await asyncio.sleep(wait_time)
                    
                    # 检查是否收到了心跳确认
                    current_time = asyncio.get_event_loop().time()
                    time_since_heartbeat = current_time - self.last_heartbeat_sent
                    message_logger.debug(f"[WebSocket] 距离上次心跳已过 {time_since_heartbeat:.1f} 秒")
                    
                except asyncio.CancelledError:
                    # 任务被取消，直接退出
                    raise
                except Exception as e:
                    # 任何其他错误，记录详细信息后继续尝试
                    message_logger.error(f"[WebSocket] 心跳发送错误: {str(e)}")
                    message_logger.error(f"[WebSocket] 心跳错误详情: {traceback.format_exc()}")
                    
                    # 如果连接已关闭，退出心跳
                    if not self.ws or self.ws.closed:
                        message_logger.debug("[WebSocket] 连接已关闭，退出心跳循环")
                        break
                    
                    # 等待短暂时间后重试
                    await asyncio.sleep(1)
                    
        except asyncio.CancelledError:
            message_logger.debug("[WebSocket] 心跳任务被取消")
        except Exception as e:
            message_logger.error(f"[WebSocket] 心跳任务异常: {str(e)}")
            message_logger.error(f"[WebSocket] 心跳任务异常详情: {traceback.format_exc()}")
        finally:
            message_logger.info("[WebSocket] 心跳任务结束")

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
        retry_count = 0
        max_retries = 20
        retry_delay = 5
        
        # 初始化心跳追踪变量
        self.last_heartbeat_sent = 0
        self.last_heartbeat_ack = 0
        
        # 主循环
        while self._running:
            # 用于每次连接尝试的心跳任务
            heartbeat_task = None
            activity_tasks = []
            
            try:
                # 检查最大重试次数
                if retry_count >= max_retries:
                    message_logger.warn(f"达到最大重试次数 ({max_retries})，等待60秒后重置计数")
                    await asyncio.sleep(60)
                    retry_count = 0
                
                # 创建会话
                await self._create_session()
                
                # 更宽松的超时设置
                timeout = aiohttp.ClientTimeout(
                    total=None,
                    connect=30,
                    sock_connect=30,
                    sock_read=60  # 减少超时时间到1分钟
                )
                
                # 设置WebSocket URL和代理
                ws_url = 'wss://gateway.discord.gg/?v=9&encoding=json'
                ws_proxy = self._get_proxy_for_url(ws_url)
                if ws_proxy:
                    message_logger.info(f"[WebSocket] 使用代理连接Discord: {ws_proxy}")
                else:
                    message_logger.warning("[WebSocket] 未配置HTTPS代理，尝试直接连接")
                
                # 创建WebSocket连接
                message_logger.debug(f"[WebSocket] 开始连接 (重试次数: {retry_count})")
                
                # 执行连接
                self.ws = await self.session.ws_connect(
                    ws_url,
                    heartbeat=None,
                    proxy=ws_proxy,
                    timeout=timeout,
                    ssl=True,
                    max_msg_size=0
                )
                message_logger.info("[WebSocket] 连接成功")
                
                # 重置变量
                self._heartbeat_interval = None
                self._last_sequence = None
                connection_start_time = asyncio.get_event_loop().time()
                
                # 创建快速保活检查任务
                async def fast_watchdog():
                    try:
                        while self._running and self.ws and not self.ws.closed:
                            now = asyncio.get_event_loop().time()
                            # 如果心跳间隔已设置并且上次心跳已发送（表示心跳进程已启动）
                            if self._heartbeat_interval and self.last_heartbeat_sent > 0:
                                time_elapsed = now - self.last_heartbeat_sent
                                # 如果超过心跳间隔的80%没有活动，主动关闭连接以触发重连
                                if time_elapsed > (self._heartbeat_interval / 1000 * 0.8):
                                    message_logger.warning(f"[快速监控] 检测到心跳可能超时 ({time_elapsed:.1f}秒无活动)，主动关闭连接")
                                    if self.ws and not self.ws.closed:
                                        await self.ws.close(code=1000, message=b"Fast reconnect")
                                    return
                            # 每2秒检查一次
                            await asyncio.sleep(2)
                    except asyncio.CancelledError:
                        message_logger.debug("[快速监控] 监控任务被取消")
                    except Exception as e:
                        message_logger.error(f"[快速监控] 监控任务错误: {str(e)}")
                
                # 启动快速监控任务
                watchdog_task = asyncio.create_task(fast_watchdog())
                activity_tasks.append(watchdog_task)
                
                # 处理WebSocket消息
                try:
                    # 处理WebSocket消息
                    async for msg in self.ws:
                        # 更新活动时间
                        self.last_activity_time = asyncio.get_event_loop().time()
                        
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            op = data.get('op')
                            
                            # 详细记录所有收到的消息
                            message_logger.debug(f"[WebSocket] 收到消息: 类型={msg.type}, OP={op}, 完整数据={msg.data[:200]}{'...' if len(msg.data) > 200 else ''}")
                            
                            # 收到Hello消息
                            if op == 10:  # Hello
                                self._heartbeat_interval = data['d']['heartbeat_interval']
                                message_logger.info(f"[WebSocket] 收到Hello消息，心跳间隔: {self._heartbeat_interval/1000:.2f}秒")
                                
                                # 启动心跳任务
                                if heartbeat_task:
                                    heartbeat_task.cancel()
                                heartbeat_task = asyncio.create_task(self._heartbeat())
                                
                                # 发送身份验证
                                await self._identify()
                            
                            # 心跳确认
                            elif op == 11:  # Heartbeat ACK
                                message_logger.debug("[WebSocket] 收到心跳确认")
                                # 更新最后心跳确认时间
                                self.last_heartbeat_ack = asyncio.get_event_loop().time()
                            
                            # 数据分发
                            elif op == 0:  # Dispatch
                                self._last_sequence = data.get('s')
                                event_type = data.get('t')
                                
                                if event_type == 'MESSAGE_CREATE':
                                    if self.message_callback:
                                        asyncio.create_task(self.message_callback(data['d']))
                                elif event_type == 'READY':
                                    message_logger.info(f"[WebSocket] Discord连接就绪，用户: {data['d'].get('user', {}).get('username', 'Unknown')}")
                            
                            # 无效会话
                            elif op == 9:  # Invalid Session
                                resumable = data.get('d', False)
                                message_logger.warning(f"[WebSocket] 会话无效，{'可恢复' if resumable else '不可恢复'}，将重新连接")
                                self._last_sequence = None if not resumable else self._last_sequence
                                break
                            
                            # 服务器要求重连
                            elif op == 7:  # Reconnect
                                message_logger.info("[WebSocket] 收到服务器要求重连的指令")
                                break
                        
                        # 连接错误或关闭
                        elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE):
                            message_logger.warning(f"[WebSocket] 连接状态改变: {msg.type}")
                            # 详细记录关闭信息
                            if msg.type == aiohttp.WSMsgType.CLOSE:
                                message_logger.warning(f"[WebSocket] 连接关闭: 代码={msg.data}, 原因={msg.extra}")
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                message_logger.error(f"[WebSocket] 连接错误: {msg.data}")
                                if hasattr(msg, 'extra') and msg.extra:
                                    message_logger.error(f"[WebSocket] 错误详情: {msg.extra}")
                            break
                        # 记录其他类型的消息
                        else:
                            message_logger.warning(f"[WebSocket] 收到未处理的消息类型: {msg.type}, 数据: {str(msg.data)[:200]}")
                
                except asyncio.TimeoutError:
                    message_logger.error("[WebSocket] 连接超时")
                    # 记录连接状态
                    if self.ws:
                        message_logger.error(f"[WebSocket] 超时时连接状态: closed={self.ws.closed}, exception={self.ws.exception() if hasattr(self.ws, 'exception') else 'N/A'}")
                except aiohttp.ClientError as e:
                    message_logger.error(f"[WebSocket] 客户端错误: {str(e)}")
                    # 记录更详细的错误信息
                    if hasattr(e, '__dict__'):
                        message_logger.error(f"[WebSocket] 客户端错误详情: {e.__dict__}")
                except Exception as e:
                    message_logger.error(f"[WebSocket] 处理消息错误: {str(e)}")
                    message_logger.error(traceback.format_exc())
                
                # 计算连接持续时间
                connection_duration = asyncio.get_event_loop().time() - connection_start_time
                message_logger.info(f"[WebSocket] 连接持续了 {connection_duration:.1f} 秒")
                
            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                message_logger.error(f"[WebSocket] 连接失败: {type(e).__name__} - {str(e)}")
            except Exception as e:
                message_logger.error(f"[WebSocket] 未预期错误: {str(e)}")
                message_logger.error(traceback.format_exc())
            
            # 清理资源
            try:
                # 取消任务
                if heartbeat_task:
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass
                
                # 取消所有活动监控任务
                for task in activity_tasks:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                
                # 关闭WebSocket
                if self.ws and not self.ws.closed:
                    await self.ws.close()
            except Exception as e:
                message_logger.error(f"[WebSocket] 清理资源错误: {str(e)}")
            
            # 准备重连
            retry_count += 1
            
            # 根据重试次数调整延迟，但保持较短的延迟，以减少中断时间
            current_delay = min(retry_delay * (1.1 ** min(retry_count, 5)), 30)
            message_logger.info(f"[WebSocket] 将在 {current_delay:.1f} 秒后尝试重新连接 (第 {retry_count} 次)")
            await asyncio.sleep(current_delay)
        
        message_logger.info("消息监听服务已停止")

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
        message_logger.info("[验证] 开始验证Discord token")
        try:
            message_logger.debug("[验证] 准备验证token，创建会话")
            await self._create_session()
            message_logger.debug("[验证] 会话创建完成，发送验证请求")
            
            verification_url = 'https://discord.com/api/v9/users/@me'
            message_logger.debug(f"[请求] 验证token: URL={verification_url}")
            
            try:
                # 添加超时控制
                timeout = aiohttp.ClientTimeout(total=10)  # 设置10秒超时
                message_logger.debug(f"[请求] 设置请求超时时间: 10秒")
                
                async with self.session.get(verification_url, timeout=timeout, proxy=self._get_proxy_for_url(verification_url)) as response:
                    status_code = response.status
                    message_logger.debug(f"[响应] 验证token状态码: {status_code}")
                    
                    try:
                        # 尝试获取响应内容
                        response_text = await response.text()
                        message_logger.debug(f"[响应] 响应内容长度: {len(response_text)} 字符")
                        
                        # 尝试解析为JSON（如果是JSON格式）
                        try:
                            response_json = await response.json()
                            message_logger.debug(f"[响应] 响应JSON格式: {list(response_json.keys()) if isinstance(response_json, dict) else '非字典格式'}")
                        except:
                            message_logger.debug("[响应] 响应内容不是有效的JSON格式")
                    except Exception as e:
                        message_logger.error(f"[响应] 读取响应内容失败: {str(e)}")
                        response_text = "无法读取响应内容"
                    
                    if status_code == 200:
                        # 成功验证，获取用户信息
                        try:
                            user_data = await response.json()
                            username = user_data.get('username', '未知用户')
                            user_id = user_data.get('id', '未知ID')
                            message_logger.info(f"[验证成功] Discord token验证成功，用户: {username}, ID: {user_id}")
                            return True
                        except Exception as e:
                            message_logger.error(f"[验证] 解析用户数据失败: {str(e)}")
                            message_logger.debug(f"[验证错误详情] {traceback.format_exc()}")
                            return False
                    elif status_code == 401:
                        # 401 表示未授权，即token无效
                        message_logger.error(f"[验证失败] Discord token无效: HTTP 401 Unauthorized")
                        message_logger.debug(f"[验证错误详情] 响应内容: {response_text}")
                        return False
                    elif status_code == 403:
                        # 403 表示禁止访问，可能是token被禁用
                        message_logger.error(f"[验证失败] Discord token被禁用或受限: HTTP 403 Forbidden")
                        message_logger.debug(f"[验证错误详情] 响应内容: {response_text}")
                        return False
                    elif status_code == 429:
                        # 429 表示请求过多，被限流
                        message_logger.error(f"[验证失败] Discord API请求过多，被限流: HTTP 429 Too Many Requests")
                        message_logger.debug(f"[验证错误详情] 响应内容: {response_text}")
                        return False
                    else:
                        # 其他错误
                        message_logger.error(f"[验证失败] Discord token验证失败: HTTP {status_code}")
                        message_logger.debug(f"[验证错误详情] 响应内容: {response_text}")
                        return False
            except aiohttp.ClientConnectorError as e:
                message_logger.error(f"[验证失败] 连接Discord API失败: {str(e)}")
                message_logger.debug(f"[验证错误详情] {traceback.format_exc()}")
                return False
            except asyncio.TimeoutError:
                message_logger.error("[验证失败] Discord API请求超时")
                message_logger.debug(f"[验证错误详情] 请求URL: {verification_url} 超时")
                return False
            except aiohttp.ClientError as e:
                message_logger.error(f"[验证失败] 网络错误: {str(e)}")
                message_logger.debug(f"[验证错误详情] {traceback.format_exc()}")
                return False
        except Exception as e:
            message_logger.error(f"[验证失败] Discord token验证失败: {str(e)}")
            message_logger.debug(f"[验证错误详情] {traceback.format_exc()}")
            return False

    async def get_channel_info(self, channel_id: str) -> Dict[str, Any]:
        """获取频道信息"""
        try:
            await self._create_session()
            async with self.session.get(f'https://discord.com/api/v9/channels/{channel_id}', proxy=self._get_proxy_for_url(f'https://discord.com/api/v9/channels/{channel_id}')) as response:
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
            message_logger.info(f"[开始] 获取论坛频道 {channel_id} 的帖子")
            await self._create_session()
            message_logger.debug(f"[会话] 已创建会话准备获取论坛帖子")
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
                
                message_logger.debug(f"[请求] 获取论坛帖子: URL={url}, 参数={params}")
                try:
                    async with self.session.get(url, params=params, proxy=self._get_proxy_for_url(url)) as response:
                        status_code = response.status
                        message_logger.debug(f"[响应] 获取论坛帖子状态码: {status_code}")
                        
                        if status_code == 200:
                            threads_data = await response.json()
                            message_logger.debug(f"[数据] 获取到帖子数据结构: {list(threads_data.keys())}")
                            
                            threads = threads_data.get('threads', [])
                            total_results = threads_data.get('total_results', 0)
                            
                            message_logger.info(f"[结果] 当前批次获取到 {len(threads)} 个帖子, 总计 {total_results} 个结果")
                            
                            if not threads:
                                message_logger.info("[结束] 没有更多帖子，停止获取")
                                has_more = False
                                continue
                            
                            for thread in threads:
                                thread_id = thread.get('id', '未知ID')
                                thread_name = thread.get('name', '未知名称')
                                message_logger.debug(f"[帖子] 处理帖子: ID={thread_id}, 名称={thread_name}")
                                
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
                            old_offset = offset
                            offset += len(threads)
                            message_logger.debug(f"[分页] 更新offset: {old_offset} -> {offset}")
                            
                            # 如果已经获取了所有结果，停止
                            if offset >= total_results or len(threads) < 25:
                                message_logger.info(f"[结束] 已获取所有结果或结果不足一页，停止获取: offset={offset}, total={total_results}")
                                has_more = False
                        else:
                            response_text = await response.text()
                            error_msg = f"获取活跃帖子失败: 状态码={status_code}\n错误响应: {response_text}"
                            print(error_msg)
                            message_logger.error(error_msg)
                            message_logger.debug(f"[错误] 获取活跃帖子失败详情: URL={url}, 参数={params}, 状态码={status_code}, 响应={response_text}")
                            has_more = False
                except Exception as e:
                    message_logger.error(f"[异常] 获取活跃帖子时发生异常: {str(e)}")
                    message_logger.debug(f"[异常详情] {traceback.format_exc()}")
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
            
            message_logger.debug(f"[请求] 获取已归档帖子: URL={url}, 参数={params}")
            try:
                async with self.session.get(url, params=params, proxy=self._get_proxy_for_url(url)) as response:
                    status_code = response.status
                    message_logger.debug(f"[响应] 获取已归档帖子状态码: {status_code}")
                    
                    if status_code == 200:
                        archived_data = await response.json()
                        message_logger.debug(f"[数据] 获取到已归档帖子数据结构: {list(archived_data.keys())}")
                        
                        archived_threads = archived_data.get('threads', [])
                        message_logger.info(f"[结果] 获取到 {len(archived_threads)} 个已归档帖子")
                        
                        for thread in archived_threads:
                            thread_id = thread.get('id', '未知ID')
                            thread_name = thread.get('name', '未知名称')
                            message_logger.debug(f"[归档帖子] 处理归档帖子: ID={thread_id}, 名称={thread_name}")
                            
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
                        response_text = await response.text()
                        error_msg = f"获取已归档帖子失败: 状态码={status_code}\n错误响应: {response_text}"
                        print(error_msg)
                        message_logger.error(error_msg)
                        message_logger.debug(f"[错误] 获取已归档帖子失败详情: URL={url}, 参数={params}, 状态码={status_code}, 响应={response_text}")
            except Exception as e:
                message_logger.error(f"[异常] 获取已归档帖子时发生异常: {str(e)}")
                message_logger.debug(f"[异常详情] {traceback.format_exc()}")
            
            # 将JSON字符串转回字典
            result = [json.loads(t) for t in all_threads]
            message_logger.info(f"[完成] 总共获取到 {len(result)} 个帖子(包括活跃和已归档)")
            return result
            
        except Exception as e:
            error_msg = f"获取论坛帖子出错: {str(e)}"
            print(error_msg)
            message_logger.error(error_msg)
            message_logger.error(f"[严重错误] 获取论坛帖子完全失败: {traceback.format_exc()}")
            return []

    async def sync_channels_to_db(self, db: Session):
        """同步频道信息到数据库，检查权限并标记不可访问的频道"""
        try:
            # 发送开始同步通知到 Telegram
            start_msg = "🚀 开始同步 Discord 频道和帖子..."
            print(start_msg)
            message_logger.info(start_msg, extra={'startup_msg': True})
            message_logger.debug("[DEBUG] sync_channels_to_db: 开始创建session")
            
            # 1. 创建HTTP会话
            try:
                await self._create_session()
                message_logger.info("[会话] HTTP会话创建成功")
            except Exception as e:
                message_logger.error(f"[严重错误] 创建HTTP会话失败: {str(e)}")
                message_logger.debug(f"[会话错误详情] {traceback.format_exc()}")
                raise Exception(f"创建HTTP会话失败: {str(e)}")
                
            accessible_count = 0
            inaccessible_count = 0
            thread_count = 0
            
            # 2. 获取用户所在的所有服务器
            guild_msg = "正在获取服务器列表..."
            print(guild_msg)
            message_logger.info(guild_msg)
            message_logger.debug("[DEBUG] sync_channels_to_db: 请求 https://discord.com/api/v9/users/@me/guilds")
            
            guilds_url = 'https://discord.com/api/v9/users/@me/guilds'
            message_logger.debug(f"[请求] 获取服务器列表: URL={guilds_url}")
            
            try:
                async with self.session.get(guilds_url, proxy=self._get_proxy_for_url(guilds_url)) as response:
                    status_code = response.status
                    message_logger.debug(f"[响应] 获取服务器列表状态码: {status_code}")
                    
                    if status_code != 200:
                        response_text = await response.text()
                        error_msg = f"获取服务器列表失败: HTTP {status_code}\n响应: {response_text}"
                        print(error_msg)
                        message_logger.error(error_msg)
                        message_logger.debug(f"[错误] 获取服务器列表失败详情: URL={guilds_url}, 状态码={status_code}, 响应={response_text}")
                        raise Exception("Failed to fetch guilds")
                    
                    guilds = await response.json()
                    message_logger.debug(f"[数据] 获取到服务器列表格式: {list(guilds[0].keys()) if guilds else '空列表'}")
                    guild_found_msg = f"发现 {len(guilds)} 个服务器"
                    print(guild_found_msg)
                    message_logger.info(guild_found_msg)
            except Exception as e:
                message_logger.error(f"[严重错误] 获取服务器列表完全失败: {str(e)}")
                message_logger.debug(f"[服务器列表错误详情] {traceback.format_exc()}")
                raise Exception(f"获取服务器列表失败: {str(e)}")
            
            # 3. 处理每个服务器
            for guild_index, guild in enumerate(guilds):
                guild_id = guild['id']
                guild_name = guild['name']
                guild_process_msg = f"正在处理服务器 ({guild_index+1}/{len(guilds)}): {guild_name} (ID: {guild_id})"
                print(guild_process_msg)
                message_logger.info(guild_process_msg)
                
                # 4. 获取服务器中的所有频道
                channels_url = f'https://discord.com/api/v9/guilds/{guild_id}/channels'
                message_logger.debug(f"[请求] 获取服务器频道: URL={channels_url}")
                message_logger.debug(f"[DEBUG] sync_channels_to_db: 请求 {channels_url}")
                
                channel_list_msg = f"正在获取服务器 {guild_name} 的频道列表..."
                print(channel_list_msg)
                message_logger.info(channel_list_msg)
                
                try:
                    async with self.session.get(channels_url, proxy=self._get_proxy_for_url(channels_url)) as channels_response:
                        status_code = channels_response.status
                        message_logger.debug(f"[响应] 获取服务器频道状态码: {status_code}")
                        
                        if status_code != 200:
                            response_text = await channels_response.text()
                            error_msg = f"获取服务器 {guild_name} 的频道列表失败: HTTP {status_code}\n响应: {response_text}"
                            print(error_msg)
                            message_logger.error(error_msg)
                            message_logger.debug(f"[错误] 获取服务器频道失败详情: URL={channels_url}, 状态码={status_code}, 响应={response_text}")
                            continue
                        
                        channels = await channels_response.json()
                        message_logger.debug(f"[数据] 获取到频道列表格式: {list(channels[0].keys()) if channels else '空列表'}")
                        channels_found_msg = f"在服务器 {guild_name} 中发现 {len(channels)} 个频道"
                        print(channels_found_msg)
                        message_logger.info(channels_found_msg)
                except Exception as e:
                    message_logger.error(f"[错误] 获取服务器 {guild_name} 频道列表失败: {str(e)}")
                    message_logger.debug(f"[频道列表错误详情] {traceback.format_exc()}")
                    continue
                
                # 5. 处理频道分类
                message_logger.debug(f"[处理] 开始分析频道分类信息")
                categories = {}
                category_count = 0
                
                try:
                    for channel in channels:
                        if channel.get('type') == 4:  # Discord分类
                            categories[channel['id']] = channel
                            category_count += 1
                    
                    categories_msg = f"发现 {category_count} 个分类"
                    print(categories_msg)
                    message_logger.info(categories_msg)
                    message_logger.debug(f"[分类] 分类ID列表: {list(categories.keys())}")
                except Exception as e:
                    message_logger.error(f"[错误] 处理频道分类失败: {str(e)}")
                    message_logger.debug(f"[分类处理错误详情] {traceback.format_exc()}")
                
                # 6. 处理所有频道
                message_logger.info(f"[处理] 开始处理 {len(channels)} 个频道")
                for channel_index, channel_data in enumerate(channels):
                    try:
                        channel_id = channel_data.get('id')
                        channel_name = channel_data.get('name', '未知频道')
                        channel_type = channel_data.get('type', 0)
                        parent_id = channel_data.get('parent_id')
                        position = channel_data.get('position', 0)
                        
                        process_channel_msg = f"处理频道 ({channel_index+1}/{len(channels)}): {channel_name} (ID: {channel_id}, 类型: {channel_type})"
                        print(process_channel_msg)
                        message_logger.info(process_channel_msg)
                        message_logger.debug(f"[频道详情] 频道数据: ID={channel_id}, 名称={channel_name}, 类型={channel_type}, 父级={parent_id}")
                        
                        # 7. 跳过语音频道
                        if channel_type == 2:
                            skip_msg = f"跳过语音频道: {channel_name}"
                            print(skip_msg)
                            message_logger.info(skip_msg)
                            continue
                        
                        # 8. 检查频道权限
                        message_logger.debug(f"[权限] 开始检查频道 {channel_name} 的访问权限")
                        has_access = True if channel_type == 4 else await self._check_channel_access(channel_id)
                        access_msg = f"频道 {channel_name} 权限检查结果: {'有权限' if has_access else '无权限'}"
                        print(access_msg)
                        message_logger.info(access_msg)
                        
                        # 9. 获取分类名称
                        category_name = None
                        if parent_id and parent_id in categories:
                            category_name = categories[parent_id].get('name')
                            message_logger.debug(f"[分类] 频道 {channel_name} 属于分类: {category_name}")
                        
                        # 10. 更新或创建频道记录
                        message_logger.debug(f"[数据库] 查询频道 {channel_id} 是否存在于数据库")
                        channel = db.query(Channel).filter(
                            Channel.platform_channel_id == str(channel_id)
                        ).first()
                        
                        if not channel:
                            message_logger.debug(f"[数据库] 频道 {channel_name} 不存在，创建新记录")
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
                            message_logger.debug(f"[数据库] 更新已存在的频道 {channel_name}")
                            channel.name = channel_name
                            channel.guild_name = guild_name
                            channel.type = channel_type
                            channel.parent_id = str(parent_id) if parent_id else None
                            channel.category_name = category_name
                            channel.is_active = has_access
                            channel.position = position
                        
                        try:
                            db.commit()
                            message_logger.debug(f"[数据库] 成功提交频道 {channel_name} 的变更")
                        except Exception as e:
                            message_logger.error(f"[数据库错误] 提交频道 {channel_name} 变更失败: {str(e)}")
                            message_logger.debug(f"[数据库错误详情] {traceback.format_exc()}")
                            db.rollback()
                            continue
                        
                        # 11. 更新计数
                        if has_access:
                            accessible_count += 1
                            
                            # 12. 如果是论坛频道，同步帖子
                            if channel_type == 15:  # Discord论坛频道类型
                                forum_sync_msg = f"正在同步论坛 {channel_name} 的帖子..."
                                print(forum_sync_msg)
                                message_logger.info(forum_sync_msg)
                                
                                try:
                                    message_logger.debug(f"[论坛] 开始获取论坛 {channel_name} 的帖子")
                                    threads = await self.get_forum_threads(channel_id)
                                    message_logger.info(f"[论坛] 获取到 {len(threads)} 个帖子")
                                    
                                    # 13. 处理每个帖子
                                    for thread_index, thread_data in enumerate(threads):
                                        try:
                                            thread_id = thread_data.get('id')
                                            thread_name = thread_data.get('name', '未知帖子')
                                            is_archived = thread_data.get('archived', False)
                                            
                                            message_logger.debug(f"[帖子] 处理帖子 ({thread_index+1}/{len(threads)}): {thread_name}")
                                            
                                            # 14. 创建或更新帖子作为子频道
                                            thread = db.query(Channel).filter(
                                                Channel.platform_channel_id == str(thread_id)
                                            ).first()
                                            
                                            if not thread:
                                                message_logger.debug(f"[数据库] 帖子 {thread_name} 不存在，创建新记录")
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
                                                message_logger.debug(f"[数据库] 更新已存在的帖子 {thread_name}")
                                                thread.name = thread_name
                                                if is_archived:  # 如果是已归档帖子，直接设置为False
                                                    thread.is_active = False
                                            
                                            try:
                                                db.commit()
                                                message_logger.debug(f"[数据库] 成功提交帖子 {thread_name} 的变更")
                                            except Exception as e:
                                                message_logger.error(f"[数据库错误] 提交帖子 {thread_name} 变更失败: {str(e)}")
                                                message_logger.debug(f"[数据库错误详情] {traceback.format_exc()}")
                                                db.rollback()
                                        except Exception as e:
                                            message_logger.error(f"[错误] 处理帖子时出错: {str(e)}")
                                            message_logger.debug(f"[帖子错误详情] {traceback.format_exc()}")
                                            continue
                                    
                                    forum_threads_msg = f"论坛 {channel_name} 同步了 {len(threads)} 个帖子"
                                    print(forum_threads_msg)
                                    message_logger.info(forum_threads_msg)
                                except Exception as e:
                                    error_msg = f"同步论坛 {channel_name} 帖子失败: {str(e)}"
                                    print(error_msg)
                                    message_logger.error(error_msg)
                                    message_logger.debug(f"[论坛错误详情] {traceback.format_exc()}")
                        else:
                            inaccessible_count += 1
                    except Exception as e:
                        error_msg = f"处理频道 {channel_name} 时出错: {str(e)}"
                        print(error_msg)
                        message_logger.error(error_msg)
                        message_logger.debug(f"[频道处理错误详情] {traceback.format_exc()}")
                        continue
            
            # 15. 发送同步完成通知到 Telegram
            final_msg = f"""🎉 Discord 频道同步完成:
- {accessible_count} 个可访问频道
- {inaccessible_count} 个无权限频道
- {thread_count} 个论坛帖子"""
            print(final_msg)
            message_logger.info(final_msg, extra={'startup_msg': True})
            message_logger.debug(f"[完成] sync_channels_to_db 完成: accessible={accessible_count}, inaccessible={inaccessible_count}, threads={thread_count}")
            
            return {
                "accessible_count": accessible_count,
                "inaccessible_count": inaccessible_count,
                "thread_count": thread_count
            }
        except Exception as e:
            error_msg = f"同步频道时发生异常: {str(e)}"
            print(error_msg)
            message_logger.error(error_msg, extra={'startup_msg': True})
            message_logger.error(f"[严重错误] 同步频道完全失败: {traceback.format_exc()}")
            raise

    async def _check_channel_access(self, channel_id: str) -> bool:
        """检查是否有权限访问频道"""
        try:
            message_logger.debug(f"[权限] 检查频道 {channel_id} 的访问权限")
            # 尝试获取频道的一条消息来测试权限
            url = f'https://discord.com/api/v9/channels/{channel_id}/messages'
            params = {'limit': 1}
            message_logger.debug(f"[请求] 权限检查: URL={url}, 参数={params}")
            
            async with self.session.get(url, params=params, proxy=self._get_proxy_for_url(url)) as response:
                status_code = response.status
                message_logger.debug(f"[响应] 权限检查状态码: {status_code}")
                
                if status_code == 200:
                    message_logger.debug(f"[权限] 频道 {channel_id} 有访问权限")
                    return True
                elif status_code in [403, 401]:
                    message_logger.debug(f"[权限] 频道 {channel_id} 无访问权限: 状态码={status_code}")
                    return False
                else:
                    # 尝试解析响应内容
                    try:
                        response_data = await response.json()
                        message_logger.debug(f"[权限] 频道 {channel_id} 响应内容: {response_data}")
                        if response_data.get('code') == 50001:
                            message_logger.debug(f"[权限] 频道 {channel_id} 无访问权限: 错误码=50001")
                            return False
                    except Exception as e:
                        message_logger.debug(f"[权限] 解析响应内容失败: {str(e)}")
                    
                    # 其他错误视为无权限
                    message_logger.debug(f"[权限] 频道 {channel_id} 视为无权限: 其他错误 {status_code}")
                    return False
        except Exception as e:
            message_logger.debug(f"[权限] 检查频道 {channel_id} 权限时发生异常: {str(e)}")
            message_logger.debug(f"[权限异常详情] {traceback.format_exc()}")
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
                    params=params,
                    proxy=self._get_proxy_for_url(f'https://discord.com/api/v9/channels/{channel_id}/messages')
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
            async with self.session.get(f'https://discord.com/api/v9/guilds/{guild_id}/channels', proxy=self._get_proxy_for_url(f'https://discord.com/api/v9/guilds/{guild_id}/channels')) as response:
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
            async with self.session.get(f'https://discord.com/api/v9/guilds/{guild_id}', proxy=self._get_proxy_for_url(f'https://discord.com/api/v9/guilds/{guild_id}')) as response:
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
            async with self.session.get(f'https://discord.com/api/v9/users/{user_id}', proxy=self._get_proxy_for_url(f'https://discord.com/api/v9/users/{user_id}')) as response:
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
            async with self.session.get(attachment_data['url'], proxy=self._get_proxy_for_url(attachment_data['url'])) as response:
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