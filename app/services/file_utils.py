import os
import aiohttp
import logging
from datetime import datetime
import hashlib
from typing import Optional
import traceback

message_logger = logging.getLogger("Message Logs")

class FileHandler:
    def __init__(self):
        # 创建存储目录
        self.base_dir = os.path.join(os.getcwd(), 'storage')
        os.makedirs(self.base_dir, exist_ok=True)
        
    async def download_and_save_file(self, url: str, filename: Optional[str] = None) -> Optional[str]:
        """
        下载文件并保存到本地
        返回本地存储路径（相对于storage目录）
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        message_logger.error(f"下载文件失败: {url}, 状态码: {response.status}")
                        return None
                    
                    # 读取文件内容
                    content = await response.read()
                    return await self.save_file(content, filename or self._generate_filename(url, response.headers.get('Content-Type', '')))
                    
        except Exception as e:
            message_logger.error(f"保存文件出错: {str(e)}")
            return None
            
    async def save_file(self, content: bytes, filename: str, save_dir: str = None) -> Optional[str]:
        """
        保存文件内容到本地
        :param content: 文件内容
        :param filename: 文件名
        :param save_dir: 保存目录（相对于storage目录）
        :return: 相对于storage目录的文件路径
        """
        try:
            # 确定保存目录
            if save_dir:
                full_save_dir = os.path.join(self.base_dir, save_dir)
            else:
                # 按年月组织文件夹
                year_month = datetime.now().strftime('%Y%m')
                full_save_dir = os.path.join(self.base_dir, 'attachments', year_month)
            
            os.makedirs(full_save_dir, exist_ok=True)
            message_logger.info(f"Saving file to directory: {full_save_dir}")
            
            # 保存文件
            file_path = os.path.join(full_save_dir, filename)
            with open(file_path, 'wb') as f:
                f.write(content)
            
            # 返回相对路径
            relative_path = os.path.relpath(file_path, self.base_dir)
            message_logger.info(f"File saved, relative path: {relative_path}")
            return relative_path
            
        except Exception as e:
            message_logger.error(f"保存文件出错: {str(e)}")
            message_logger.error(traceback.format_exc())
            return None

    def _generate_filename(self, url: str, content_type: str = '') -> str:
        """生成文件名"""
        hash_base = f"{url}{datetime.now().timestamp()}"
        filename = hashlib.md5(hash_base.encode()).hexdigest()
        
        if 'image' in content_type:
            ext = content_type.split('/')[-1]
            filename = f"{filename}.{ext}"
        else:
            # 从URL获取扩展名
            ext = os.path.splitext(url)[-1]
            if ext:
                filename = f"{filename}{ext}"
        
        return filename

    def get_file_url(self, relative_path: str) -> str:
        """
        将相对路径转换为可访问的URL
        """
        if not relative_path:
            return ''
        return f"/storage/{relative_path}" 