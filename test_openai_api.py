#!/usr/bin/env python3
"""
OpenAI API 测试脚本
用于验证API配置是否正确
"""

import os
import openai
from dotenv import load_dotenv
import sys

# 加载环境变量
load_dotenv()

def test_api_configuration():
    """测试API配置"""
    print("=== OpenAI API 配置测试 ===")
    
    # 获取配置
    api_key = os.getenv("OPENAI_API_KEY")
    use_proxy_env = os.getenv("USE_OPENAI_PROXY", "false")
    proxy_url_env = os.getenv("OPENAI_PROXY_URL", "https://api.openai99.top/v1")
    
    # 清理环境变量中的注释（去掉 # 及其后面的内容）
    use_proxy_env = use_proxy_env.split('#')[0].strip()
    proxy_url_env = proxy_url_env.split('#')[0].strip()
    
    use_proxy = use_proxy_env.lower() == "true"
    
    print(f"API Key: {api_key[:10] if api_key else 'NOT SET'}...")
    print(f"原始代理设置: {os.getenv('USE_OPENAI_PROXY', 'NOT SET')}")
    print(f"清理后代理设置: {use_proxy_env}")
    print(f"使用代理: {use_proxy}")
    print(f"代理URL: {proxy_url_env}")
    
    if not api_key:
        print("❌ 错误: OPENAI_API_KEY 未设置")
        return False
    
    # 设置客户端
    if use_proxy:
        # 处理代理URL
        proxy_base = proxy_url_env.rstrip('/v1').rstrip('/')
        if 'openai99.top' in proxy_base:
            base_url = f"{proxy_base}/v1"
        else:
            base_url = proxy_base
    else:
        base_url = "https://api.openai.com"
    
    print(f"实际使用的base_url: {base_url}")
    
    client = openai.OpenAI(
        api_key=api_key,
        base_url=base_url
    )
    
    # 测试简单的请求
    try:
        print("\n测试简单的聊天请求...")
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # 使用更便宜的模型测试
            messages=[
                {"role": "user", "content": "Hello, please respond with just 'OK'"}
            ],
            max_tokens=10
        )
        
        if hasattr(response, 'choices') and response.choices:
            result = response.choices[0].message.content
            print(f"✅ API响应成功: {result}")
            return True
        else:
            print(f"❌ 未知响应格式: {type(response)}")
            return False
            
    except Exception as e:
        print(f"❌ API请求失败: {str(e)}")
        return False

def test_json_mode():
    """测试JSON模式"""
    print("\n=== 测试JSON模式 ===")
    
    api_key = os.getenv("OPENAI_API_KEY")
    use_proxy_env = os.getenv("USE_OPENAI_PROXY", "false")
    proxy_url_env = os.getenv("OPENAI_PROXY_URL", "https://api.openai99.top/v1")
    
    # 清理环境变量中的注释
    use_proxy_env = use_proxy_env.split('#')[0].strip()
    proxy_url_env = proxy_url_env.split('#')[0].strip()
    use_proxy = use_proxy_env.lower() == "true"
    
    if use_proxy:
        proxy_base = proxy_url_env.rstrip('/v1').rstrip('/')
        if 'openai99.top' in proxy_base:
            base_url = f"{proxy_base}/v1"
        else:
            base_url = proxy_base
    else:
        base_url = "https://api.openai.com"
    
    client = openai.OpenAI(
        api_key=api_key,
        base_url=base_url
    )
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "你是一个专业的JSON响应助手。请严格按照JSON格式返回结果。"},
                {"role": "user", "content": "请分析'BTC涨了'这条消息，返回JSON格式：{\"is_trading_related\": true/false, \"summary\": \"摘要\"}"}
            ],
            temperature=0.3,
            max_tokens=100,
            response_format={"type": "json_object"}
        )
        
        if hasattr(response, 'choices') and response.choices:
            result = response.choices[0].message.content
            print(f"✅ JSON模式响应: {result}")
            
            # 尝试解析JSON
            import json
            try:
                parsed = json.loads(result)
                print(f"✅ JSON解析成功: {parsed}")
                return True
            except json.JSONDecodeError as e:
                print(f"❌ JSON解析失败: {e}")
                return False
        else:
            print(f"❌ 未知响应格式: {type(response)}")
            return False
            
    except Exception as e:
        print(f"❌ JSON模式请求失败: {str(e)}")
        return False

if __name__ == "__main__":
    print("开始API配置测试...\n")
    
    # 基础配置测试
    basic_ok = test_api_configuration()
    
    if basic_ok:
        # JSON模式测试
        json_ok = test_json_mode()
        
        if json_ok:
            print("\n🎉 所有测试通过！API配置正确")
            sys.exit(0)
        else:
            print("\n⚠️  基础功能正常，但JSON模式有问题")
            sys.exit(1)
    else:
        print("\n❌ API配置有问题，请检查环境变量")
        sys.exit(1) 