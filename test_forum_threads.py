import os
import asyncio
import aiohttp
from dotenv import load_dotenv
import json
from datetime import datetime

# 加载环境变量
load_dotenv()

# 打印环境变量信息
print("=== 环境变量检查 ===")
user_token = os.getenv('DISCORD_USER_TOKEN')
print(f"User Token: {'已设置' if user_token else '未设置'}")
if not user_token:
    print("错误：DISCORD_USER_TOKEN 环境变量未设置")
    exit(1)

async def get_thread_messages(session, thread_id, limit=5):
    """获取指定帖子的最新消息"""
    url = f'https://discord.com/api/v9/channels/{thread_id}/messages'
    params = {'limit': limit}
    
    async with session.get(url, params=params) as response:
        if response.status == 200:
            messages = await response.json()
            return messages
        else:
            print(f"获取帖子 {thread_id} 的消息失败: {response.status}")
            print(f"响应内容: {await response.text()}")
            return []

async def get_forum_threads():
    try:
        # 创建会话
        print("\n=== 创建会话 ===")
        headers = {
            'Authorization': user_token,
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Content-Type': 'application/json',
            'Origin': 'https://discord.com',
            'Referer': 'https://discord.com/channels/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'X-Discord-Locale': 'zh-CN',
            'X-Discord-Timezone': 'Asia/Shanghai',
            'X-Super-Properties': 'eyJvcyI6Ik1hYyBPUyBYIiwiYnJvd3NlciI6IkNocm9tZSIsImRldmljZSI6IiIsInN5c3RlbV9sb2NhbGUiOiJ6aC1DTiIsImJyb3dzZXJfdXNlcl9hZ2VudCI6Ik1vemlsbGEvNS4wIChNYWNpbnRvc2g7IEludGVsIE1hYyBPUyBYIDEwXzE1XzcpIEFwcGxlV2ViS2l0LzUzNy4zNiAoS0hUTUwsIGxpa2UgR2Vja28pIENocm9tZS8xMjAuMC4wLjAgU2FmYXJpLzUzNy4zNiIsImJyb3dzZXJfdmVyc2lvbiI6IjEyMC4wLjAuMCIsIm9zX3ZlcnNpb24iOiIxMC4xNS43IiwicmVmZXJyZXIiOiIiLCJyZWZlcnJpbmdfZG9tYWluIjoiIiwicmVmZXJyZXJfY3VycmVudCI6IiIsInJlZmVycmluZ19kb21haW5fY3VycmVudCI6IiIsInJlbGVhc2VfY2hhbm5lbCI6InN0YWJsZSIsImNsaWVudF9idWlsZF9udW1iZXIiOjI2MDY3MiwiY2xpZW50X2V2ZW50X3NvdXJjZSI6bnVsbH0='
        }
        
        async with aiohttp.ClientSession(headers=headers) as session:
            # 验证 token
            print("\n=== 验证 Token ===")
            async with session.get('https://discord.com/api/v9/users/@me') as response:
                if response.status != 200:
                    print(f"Token 验证失败: {response.status}")
                    return
                user_data = await response.json()
                print(f"Token 验证成功，用户名: {user_data.get('username')}")

            # 直接测试论坛频道
            forum_id = "1226090829878267904"
            print(f"\n=== 测试论坛频道 {forum_id} ===")

            # 1. 先获取频道信息
            print("\n获取频道信息...")
            async with session.get(f'https://discord.com/api/v9/channels/{forum_id}') as response:
                if response.status == 200:
                    channel_data = await response.json()
                    print(f"频道名称: {channel_data.get('name')}")
                    print(f"频道类型: {channel_data.get('type')}")
                    print(f"父级ID: {channel_data.get('parent_id')}")
                    guild_id = channel_data.get('guild_id')
                else:
                    print(f"获取频道信息失败: {response.status}")
                    print(f"响应内容: {await response.text()}")
                    return

            # 2. 获取所有帖子
            print("\n尝试获取所有帖子...")
            all_threads = []
            offset = 0
            has_more = True

            while has_more:
                url = f'https://discord.com/api/v9/channels/{forum_id}/threads/search'
                params = {
                    'limit': 25,  # Discord 限制最大为 25
                    'offset': offset,
                    'sort_by': 'last_message_time',
                    'sort_order': 'desc'
                }

                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        threads_data = await response.json()
                        threads = threads_data.get('threads', [])
                        total_results = threads_data.get('total_results', 0)
                        
                        if not threads:
                            has_more = False
                            continue
                            
                        all_threads.extend(threads)
                        
                        # 更新 offset
                        offset += len(threads)
                        # 如果已经获取了所有结果，停止
                        if offset >= total_results or len(threads) < 25:
                            has_more = False
                    else:
                        print(f"获取帖子失败: {response.status}")
                        print(f"响应内容: {await response.text()}")
                        has_more = False

            # 3. 获取已归档的帖子
            print("\n尝试获取已归档帖子...")
            async with session.get(
                f'https://discord.com/api/v9/channels/{forum_id}/threads/archived/public?limit=100'
            ) as response:
                if response.status == 200:
                    archived_data = await response.json()
                    archived_threads = archived_data.get('threads', [])
                    # 添加到总列表中，避免重复
                    for thread in archived_threads:
                        if thread.get('id') not in [t.get('id') for t in all_threads]:
                            all_threads.append(thread)
                else:
                    print(f"获取已归档帖子失败: {response.status}")
                    print(f"响应内容: {await response.text()}")

            # 分类显示帖子
            active_threads = [t for t in all_threads if not t.get('archived')]
            archived_threads = [t for t in all_threads if t.get('archived')]

            print(f"\n找到 {len(active_threads)} 个活跃帖子:")
            for thread in active_threads:
                print(f"  - {thread.get('name')} (ID: {thread.get('id')})")

            print(f"\n找到 {len(archived_threads)} 个已归档帖子:")
            for thread in archived_threads:
                print(f"  - {thread.get('name')} (ID: {thread.get('id')})")

            # 4. 获取每个活跃帖子的最新消息
            print("\n获取每个活跃帖子的最新消息...")
            for thread in active_threads:
                thread_id = thread.get('id')
                thread_name = thread.get('name')
                print(f"\n=== {thread_name} 的最新消息 ===")
                
                messages = await get_thread_messages(session, thread_id)
                for msg in messages:
                    timestamp = datetime.fromisoformat(msg.get('timestamp').rstrip('Z')).strftime('%Y-%m-%d %H:%M:%S')
                    author = msg.get('author', {}).get('username', 'Unknown')
                    content = msg.get('content', '')
                    print(f"[{timestamp}] {author}: {content}")

    except Exception as e:
        print(f"发生错误: {str(e)}")
        print(f"错误类型: {type(e)}")
        import traceback
        print(f"错误堆栈:\n{traceback.format_exc()}")

if __name__ == "__main__":
    asyncio.run(get_forum_threads()) 