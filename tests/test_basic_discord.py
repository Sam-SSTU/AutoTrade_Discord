#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
这是一个简单的Discord token测试脚本，使用requests库直接测试
不依赖于项目的任何代码，提供一个独立验证机制
"""

import os
import sys
import requests
import json
import logging
from dotenv import load_dotenv

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("Basic_Discord_Test")

# 设置全局代理
PROXIES = {
    'http': 'http://127.0.0.1:7890',
    'https': 'http://127.0.0.1:7890'
}

def test_discord_api():
    """测试基本Discord API连接"""
    logger.info("测试Discord API基本连接")
    try:
        # 设置环境变量代理
        os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
        os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7890"
        
        logger.info("使用代理: http://127.0.0.1:7890")
        
        response = requests.get(
            "https://discord.com/api/v9", 
            timeout=5,
            proxies=PROXIES
        )
        logger.info(f"API连接测试响应状态码: {response.status_code}")
        return response.status_code < 500  # 只要不是服务器错误就认为API正常
    except Exception as e:
        logger.error(f"API连接测试失败: {str(e)}")
        return False

def test_token():
    """测试Discord token"""
    # 加载环境变量
    load_dotenv()
    
    # 获取token
    token = os.getenv("DISCORD_USER_TOKEN")
    if not token:
        logger.error("DISCORD_USER_TOKEN 环境变量未设置")
        return
    
    logger.info(f"Token长度: {len(token)}")
    
    # 准备请求头
    headers = {
        "Authorization": token,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36"
    }
    
    # 测试获取用户信息
    logger.info("测试获取用户信息...")
    try:
        response = requests.get(
            "https://discord.com/api/v9/users/@me", 
            headers=headers,
            timeout=10,
            proxies=PROXIES
        )
        
        logger.info(f"响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            user_data = response.json()
            logger.info(f"Token验证成功! 用户: {user_data.get('username')}, ID: {user_data.get('id')}")
            logger.info("Token有效!")
        elif response.status_code == 401:
            logger.error("Token无效! 401 Unauthorized")
            logger.info(f"响应内容: {response.text}")
            logger.info("您需要获取新的Discord token")
        elif response.status_code == 403:
            logger.error("Token被禁用或受限! 403 Forbidden")
            logger.info(f"响应内容: {response.text}")
        elif response.status_code == 429:
            logger.error("请求过多，被限流! 429 Too Many Requests")
            logger.info(f"响应内容: {response.text}")
            logger.info("请稍后再试")
        else:
            logger.error(f"未知错误: {response.status_code}")
            logger.info(f"响应内容: {response.text}")
    
    except requests.exceptions.Timeout:
        logger.error("请求超时！检查您的网络连接")
    except requests.exceptions.ConnectionError:
        logger.error("连接错误！无法连接到Discord API")
    except Exception as e:
        logger.error(f"测试过程出现异常: {str(e)}")

def test_guilds():
    """测试获取用户的服务器列表"""
    # 加载环境变量
    load_dotenv()
    
    # 获取token
    token = os.getenv("DISCORD_USER_TOKEN")
    if not token:
        logger.error("DISCORD_USER_TOKEN 环境变量未设置")
        return
    
    # 准备请求头
    headers = {
        "Authorization": token,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36"
    }
    
    # 测试获取服务器列表
    logger.info("测试获取服务器列表...")
    try:
        response = requests.get(
            "https://discord.com/api/v9/users/@me/guilds", 
            headers=headers,
            timeout=10,
            proxies=PROXIES
        )
        
        logger.info(f"响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            guilds = response.json()
            logger.info(f"获取到 {len(guilds)} 个服务器")
            for guild in guilds[:3]:  # 只显示前3个
                logger.info(f"服务器: {guild.get('name')}, ID: {guild.get('id')}")
            
            if len(guilds) > 3:
                logger.info(f"... 以及 {len(guilds) - 3} 个其他服务器")
        else:
            logger.error(f"获取服务器列表失败: {response.status_code}")
            logger.info(f"响应内容: {response.text}")
    
    except Exception as e:
        logger.error(f"测试过程出现异常: {str(e)}")

if __name__ == "__main__":
    logger.info("开始基础Discord API测试...")
    
    # 测试API连接
    if test_discord_api():
        logger.info("Discord API连接测试通过!")
        
        # 测试Token
        test_token()
        
        # 如果需要，测试获取服务器列表
        test_guilds()
    else:
        logger.error("Discord API连接测试失败，无法继续测试!")
    
    logger.info("测试完成") 