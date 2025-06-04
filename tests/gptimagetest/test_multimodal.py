#!/usr/bin/env python3
"""
多模态图片分析测试脚本
测试OpenAI GPT-4o的图片分析功能
"""

import os
import sys
import asyncio
import base64
from typing import Dict, Any, List

# 添加项目根目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

from app.database import get_db
from app.models.base import Attachment
from app.ai.openai_client import get_openai_client
from sqlalchemy.orm import Session
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MultimodalTester:
    def __init__(self):
        # 检查环境变量
        api_key = os.getenv('OPENAI_API_KEY')
        proxy_url = os.getenv('OPENAI_BASE_URL')
        logger.info(f"API Key存在: {bool(api_key)}")
        logger.info(f"API Key前缀: {api_key[:10] if api_key else 'None'}...")
        logger.info(f"Proxy URL: {proxy_url}")
        
        self.openai_client = get_openai_client()
        
    def get_test_image_from_db(self, db: Session) -> Dict[str, Any]:
        """从数据库中获取一个测试图片"""
        try:
            # 查询一个图片附件
            attachment = db.query(Attachment).filter(
                Attachment.content_type.like('image/%')
            ).first()
            
            if not attachment:
                raise ValueError("数据库中没有找到图片附件")
            
            logger.info(f"找到测试图片: {attachment.filename} ({attachment.content_type})")
            
            # 将二进制数据转换为base64 URL
            base64_data = base64.b64encode(attachment.file_data).decode('utf-8')
            data_url = f"data:{attachment.content_type};base64,{base64_data}"
            
            return {
                "id": attachment.id,
                "filename": attachment.filename,
                "content_type": attachment.content_type,
                "url": data_url,  # 使用base64数据URL
                "size": len(attachment.file_data)
            }
            
        except Exception as e:
            logger.error(f"获取测试图片失败: {str(e)}")
            raise
    
    async def test_multimodal_analysis(self):
        """测试多模态分析功能"""
        logger.info("开始测试多模态分析功能...")
        
        # 获取数据库连接
        db = next(get_db())
        
        try:
            # 从数据库获取测试图片
            test_image = self.get_test_image_from_db(db)
            logger.info(f"使用测试图片: {test_image['filename']} (大小: {test_image['size']} bytes)")
            
            # 构造附件列表
            attachments = [test_image]
            
            # 测试消息内容
            test_message = "请分析这张图片中的内容，特别是如果包含加密货币相关的信息。"
            
            logger.info("开始调用OpenAI多模态分析...")
            
            # 调用多模态分析
            analysis_result = await self.openai_client.analyze_message(
                message_content=test_message,
                attachments=attachments
            )
            
            logger.info("多模态分析完成!")
            
            # 打印结果
            print("\n" + "="*50)
            print("多模态分析结果:")
            print("="*50)
            print(f"图片文件名: {test_image['filename']}")
            print(f"图片类型: {test_image['content_type']}")
            print(f"图片大小: {test_image['size']} bytes")
            print("-"*50)
            print("分析结果:")
            for key, value in analysis_result.items():
                print(f"  {key}: {value}")
            print("="*50)
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"测试失败: {str(e)}")
            print(f"\n测试失败: {str(e)}")
            return None
        finally:
            db.close()
    
    async def test_multiple_images(self, count: int = 3):
        """测试多张图片的分析"""
        logger.info(f"开始测试多张图片分析功能 (数量: {count})...")
        
        db = next(get_db())
        
        try:
            # 从数据库获取多张测试图片
            attachments_query = db.query(Attachment).filter(
                Attachment.content_type.like('image/%')
            ).limit(count)
            
            attachments = []
            for attachment in attachments_query:
                base64_data = base64.b64encode(attachment.file_data).decode('utf-8')
                data_url = f"data:{attachment.content_type};base64,{base64_data}"
                
                attachments.append({
                    "id": attachment.id,
                    "filename": attachment.filename,
                    "content_type": attachment.content_type,
                    "url": data_url,
                    "size": len(attachment.file_data)
                })
            
            if not attachments:
                print("数据库中没有足够的图片进行测试")
                return None
            
            logger.info(f"找到 {len(attachments)} 张图片进行测试")
            
            # 测试消息
            test_message = f"请分析这{len(attachments)}张图片，告诉我它们是否包含交易相关的信息。"
            
            # 调用分析
            analysis_result = await self.openai_client.analyze_message(
                message_content=test_message,
                attachments=attachments
            )
            
            # 打印结果
            print("\n" + "="*50)
            print(f"多图片分析结果 ({len(attachments)}张图片):")
            print("="*50)
            for i, att in enumerate(attachments, 1):
                print(f"图片{i}: {att['filename']} ({att['content_type']}, {att['size']} bytes)")
            print("-"*50)
            print("分析结果:")
            for key, value in analysis_result.items():
                print(f"  {key}: {value}")
            print("="*50)
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"多图片测试失败: {str(e)}")
            print(f"\n多图片测试失败: {str(e)}")
            return None
        finally:
            db.close()

async def main():
    """主测试函数"""
    print("开始OpenAI多模态功能测试...")
    
    tester = MultimodalTester()
    
    # 测试单张图片
    print("\n1. 测试单张图片分析...")
    single_result = await tester.test_multimodal_analysis()
    
    if single_result:
        print("✅ 单张图片测试成功!")
    else:
        print("❌ 单张图片测试失败!")
        return
    
    # 测试多张图片
    print("\n2. 测试多张图片分析...")
    multi_result = await tester.test_multiple_images(2)
    
    if multi_result:
        print("✅ 多张图片测试成功!")
    else:
        print("❌ 多张图片测试失败!")
    
    print("\n测试完成!")

if __name__ == "__main__":
    asyncio.run(main()) 