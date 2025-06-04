#!/usr/bin/env python3
"""
多模态功能调试脚本
逐步检查各个组件是否正常工作
"""

import os
import sys
import base64
from typing import Dict, Any

# 添加项目根目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

print("=" * 60)
print("多模态功能调试脚本")
print("=" * 60)

# 步骤1: 检查环境变量加载
print("\n1. 检查环境变量...")
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(__file__), '../../.env')
    print(f"加载.env文件: {env_path}")
    load_dotenv(env_path)
    
    # 检查关键环境变量
    env_vars = [
        'OPENAI_API_KEY',
        'OPENAI_PROXY_URL', 
        'USE_OPENAI_PROXY',
        'POSTGRES_USER',
        'POSTGRES_PASSWORD',
        'POSTGRES_HOST',
        'POSTGRES_PORT',
        'POSTGRES_DB'
    ]
    
    for var in env_vars:
        value = os.getenv(var)
        if var == 'OPENAI_API_KEY':
            print(f"  {var}: {'存在' if value else '未设置'} ({value[:10] + '...' if value else 'None'})")
        else:
            print(f"  {var}: {value}")
    
    print("✅ 环境变量检查完成")
    
except Exception as e:
    print(f"❌ 环境变量检查失败: {str(e)}")
    sys.exit(1)

# 步骤2: 检查数据库连接
print("\n2. 检查数据库连接...")
try:
    from app.database import get_db, engine
    from app.models.base import Attachment
    from sqlalchemy.orm import Session
    
    # 测试数据库连接
    print("  测试数据库连接...")
    db = next(get_db())
    
    # 查询附件表
    print("  查询附件表...")
    attachment_count = db.query(Attachment).count()
    image_count = db.query(Attachment).filter(
        Attachment.content_type.like('image/%')
    ).count()
    
    print(f"  总附件数量: {attachment_count}")
    print(f"  图片附件数量: {image_count}")
    
    if image_count > 0:
        # 获取一个示例图片
        sample_image = db.query(Attachment).filter(
            Attachment.content_type.like('image/%')
        ).first()
        
        print(f"  示例图片: {sample_image.filename} ({sample_image.content_type})")
        print(f"  数据大小: {len(sample_image.file_data)} bytes")
        
        # 测试base64编码
        try:
            base64_data = base64.b64encode(sample_image.file_data).decode('utf-8')
            print(f"  Base64编码长度: {len(base64_data)} 字符")
            print("  ✅ Base64编码测试通过")
        except Exception as e:
            print(f"  ❌ Base64编码失败: {str(e)}")
    
    db.close()
    print("✅ 数据库连接检查完成")
    
except Exception as e:
    print(f"❌ 数据库连接检查失败: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 步骤3: 检查OpenAI客户端初始化
print("\n3. 检查OpenAI客户端初始化...")
try:
    from app.ai.openai_client import get_openai_client
    
    print("  初始化OpenAI客户端...")
    client = get_openai_client()
    
    print(f"  API Key: {'存在' if client.api_key else '未设置'}")
    print(f"  Base URL: {client.base_url}")
    print(f"  客户端类型: {type(client.client)}")
    
    print("✅ OpenAI客户端初始化检查完成")
    
except Exception as e:
    print(f"❌ OpenAI客户端初始化失败: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 步骤4: 测试简单的OpenAI API调用（非多模态）
print("\n4. 测试简单的OpenAI API调用...")
try:
    import openai
    
    # 创建简单的文本请求
    print("  发送简单文本请求...")
    response = client.client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "你是一个测试助手。"},
            {"role": "user", "content": "请回复'测试成功'"}
        ],
        temperature=0.3,
        max_tokens=50
    )
    
    if hasattr(response, 'choices') and response.choices:
        result = response.choices[0].message.content
        print(f"  API响应: {result}")
        print("✅ 简单API调用测试通过")
    else:
        print("❌ API响应格式异常")
        
except Exception as e:
    print(f"❌ 简单API调用失败: {str(e)}")
    import traceback
    traceback.print_exc()

# 步骤5: 测试多模态消息构造
print("\n5. 测试多模态消息构造...")
try:
    db = next(get_db())
    
    # 获取一个测试图片
    sample_image = db.query(Attachment).filter(
        Attachment.content_type.like('image/%')
    ).first()
    
    if sample_image:
        print(f"  使用测试图片: {sample_image.filename}")
        
        # 构造附件数据
        base64_data = base64.b64encode(sample_image.file_data).decode('utf-8')
        data_url = f"data:{sample_image.content_type};base64,{base64_data}"
        
        attachment = {
            "id": sample_image.id,
            "filename": sample_image.filename,
            "content_type": sample_image.content_type,
            "url": data_url,
            "size": len(sample_image.file_data)
        }
        
        # 构造多模态消息
        print("  构造多模态消息...")
        multimodal_messages = [
            {
                "role": "system",
                "content": "你是一个图片分析助手。请用JSON格式回复，包含 'description' 字段。"
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "请简单描述这张图片的内容。"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": data_url,
                            "detail": "low"
                        }
                    }
                ]
            }
        ]
        
        print(f"  消息结构: {len(multimodal_messages)} 个消息")
        print(f"  用户消息内容: {len(multimodal_messages[1]['content'])} 个部分")
        print("✅ 多模态消息构造完成")
        
        # 步骤6: 测试多模态API调用
        print("\n6. 测试多模态API调用...")
        try:
            print("  发送多模态请求...")
            response = client.client.chat.completions.create(
                model="gpt-4o",
                messages=multimodal_messages,
                temperature=0.3,
                max_tokens=200,
                response_format={"type": "json_object"}
            )
            
            if hasattr(response, 'choices') and response.choices:
                result = response.choices[0].message.content
                print(f"  多模态API响应: {result}")
                print("✅ 多模态API调用测试通过!")
            else:
                print("❌ 多模态API响应格式异常")
                
        except Exception as e:
            print(f"❌ 多模态API调用失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    else:
        print("❌ 没有找到测试图片")
    
    db.close()
    
except Exception as e:
    print(f"❌ 多模态消息构造失败: {str(e)}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("调试完成")
print("=" * 60) 