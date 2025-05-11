import asyncio
import sys
import os
import logging
import json
import traceback
from dotenv import load_dotenv
import aiohttp
import time

# 将项目根目录添加到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 应用HTTPS代理补丁
from app.utils.proxy_patch import apply_proxy_patch
apply_proxy_patch()

from app.services.discord_client import DiscordClient
from app.database import SessionLocal

# 设置日志记录
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("discord_debug.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("DiscordTokenTest")

# 设置代理
PROXY = "http://127.0.0.1:7890"

# 设置环境变量代理
os.environ["HTTP_PROXY"] = PROXY
os.environ["HTTPS_PROXY"] = PROXY

async def check_token_directly():
    """直接使用aiohttp检查token，不使用客户端类"""
    logger.info("直接检查Discord token")
    
    # 加载环境变量
    load_dotenv()
    
    # 获取token
    token = os.getenv("DISCORD_USER_TOKEN")
    if not token:
        logger.error("DISCORD_USER_TOKEN 环境变量未设置")
        return False
    
    logger.info(f"token长度: {len(token)}")
    logger.info(f"使用代理: {PROXY}")
    
    # 创建会话并请求
    try:
        headers = {
            'Authorization': token,
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Content-Type': 'application/json'
        }
        
        timeout = aiohttp.ClientTimeout(total=10)
        logger.info("创建aiohttp会话")
        
        async with aiohttp.ClientSession(
            headers=headers, 
            timeout=timeout
        ) as session:
            logger.info("发送请求到 https://discord.com/api/v9/users/@me")
            start_time = time.time()
            
            try:
                async with session.get('https://discord.com/api/v9/users/@me', proxy=PROXY) as response:
                    end_time = time.time()
                    logger.info(f"请求耗时: {end_time - start_time:.2f}秒")
                    
                    status = response.status
                    logger.info(f"响应状态码: {status}")
                    
                    try:
                        response_text = await response.text()
                        logger.info(f"响应内容长度: {len(response_text)}")
                        
                        if status == 200:
                            user_data = json.loads(response_text)
                            logger.info(f"验证成功: 用户={user_data.get('username')}, ID={user_data.get('id')}")
                            return True
                        else:
                            logger.error(f"验证失败: HTTP {status}")
                            logger.info(f"响应内容: {response_text}")
                            return False
                    except Exception as e:
                        logger.error(f"解析响应失败: {str(e)}")
                        logger.debug(traceback.format_exc())
                        return False
            except asyncio.TimeoutError:
                logger.error("请求超时")
                return False
            except Exception as e:
                logger.error(f"请求失败: {str(e)}")
                logger.debug(traceback.format_exc())
                return False
    except Exception as e:
        logger.error(f"创建会话失败: {str(e)}")
        logger.debug(traceback.format_exc())
        return False

async def test_discord_api_connectivity():
    """测试与Discord API的基本连接性"""
    logger.info("测试Discord API连接性")
    logger.info(f"使用代理: {PROXY}")
    
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:
            logger.info("尝试连接 https://discord.com/api/v9")
            start_time = time.time()
            
            try:
                async with session.get('https://discord.com/api/v9', proxy=PROXY) as response:
                    end_time = time.time()
                    logger.info(f"连接测试耗时: {end_time - start_time:.2f}秒")
                    logger.info(f"连接测试状态码: {response.status}")
                    
                    # Discord API即使没有认证也应该返回一个响应
                    return response.status < 500  # 如果不是服务器错误，认为连接正常
            except asyncio.TimeoutError:
                logger.error("Discord API连接超时")
                return False
            except Exception as e:
                logger.error(f"Discord API连接失败: {str(e)}")
                return False
    except Exception as e:
        logger.error(f"创建测试会话失败: {str(e)}")
        return False

async def test_token_verification():
    """测试Discord token验证"""
    logger.info("开始测试Discord token验证")
    
    # 先测试API连接性
    api_connected = await test_discord_api_connectivity()
    if not api_connected:
        logger.error("Discord API连接测试失败，可能是网络问题")
        return
    
    # 直接检查token
    direct_check = await check_token_directly()
    if not direct_check:
        logger.error("直接检查token失败，token可能无效")
        return
    
    # 加载环境变量
    load_dotenv()
    
    # 创建Discord客户端
    discord_client = DiscordClient()
    
    # 验证token
    logger.info("调用verify_token方法")
    is_valid = await discord_client.verify_token()
    
    if is_valid:
        logger.info("Token验证成功，开始测试同步频道")
        # 测试同步频道
        db = SessionLocal()
        try:
            logger.info("调用sync_channels_to_db方法")
            result = await discord_client.sync_channels_to_db(db)
            logger.info(f"同步结果: {result}")
        except Exception as e:
            logger.error(f"同步频道失败: {str(e)}")
            logger.debug(traceback.format_exc())
        finally:
            db.close()
    else:
        logger.error("Token验证失败，跳过同步测试")
    
    # 关闭客户端
    await discord_client.close()

if __name__ == "__main__":
    logger.info("开始执行Discord token测试脚本")
    asyncio.run(test_token_verification())
    logger.info("测试脚本执行完成") 